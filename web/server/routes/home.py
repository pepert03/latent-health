"""Patient app routes: at-home urine protocol and other measurements (blood pressure, pulse, glucose).

The routes are stateless: each request carries the patient, their samples and today's date, and
the response comes entirely from the models in ``src/latenthealth``. Patient messages, record
notes and alerts are the model's own text. Only UI labels, demo scripts and validation errors
are written here.

All data is synthetic.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from functools import lru_cache
from types import SimpleNamespace
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator

from latenthealth import assessment as clinical
from latenthealth.albuminuria import (
    FIRST_MORNING,
    KITS,
    PHONE_STRIP,
    Channel,
    HomeKit,
    Patient,
    SampleContext,
    StripSample,
    UrineSample,
    load_default_filter,
    next_step,
)
from latenthealth.albuminuria import context as urine_context
from latenthealth.albuminuria.filter import STATUS_LABELS, AlbuminuriaFilter
from latenthealth.diabetes import (
    DIABETES_FASTING_GLUCOSE,
    FASTING_HOURS,
    GlucoseReading,
    fasting_days_above,
    summarize_glucose,
)
from latenthealth.i18n import LANGS, Labels, fmt_date, is_es, lang, t, use_lang
from latenthealth.home import (
    HOME_DBP_LIMIT,
    HOME_SBP_LIMIT,
    BPReading,
    RhythmCheck,
    af_prior,
    af_probability,
    summarize_home_bp,
)

from ..serialize import clean

log = logging.getLogger("latenthealth.web.home")


def _json_safe(value: Any) -> Any:
    """Copy of ``value`` with NaN and infinities written as text, which is what JSON allows."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class _SafeErrorsRoute(APIRoute):
    """Route whose 422 can always be written as JSON.

    Python accepts ``NaN`` and ``Infinity`` when reading the request body. FastAPI's 422 echoes
    the invalid value in ``input``, and writing that NaN as JSON turned the response into a 500.
    Here they are converted to text before responding.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise RequestValidationError(_json_safe(error.errors()), body=_json_safe(error.body)) from None

        return safe_handler


router = APIRouter(prefix="/api/home", tags=["At home (patient app)"], route_class=_SafeErrorsRoute)

# --- Demo constants and validation limits ---

DEMO_TODAY = dt.date(2026, 11, 16)  # a Monday; same D0 as scripts/demo_casa.py
POPULATION = "espana"
DEFAULT_CHANNEL = Channel.APP
# Default window protocol.next_step uses to count strips and tubes used.
EPISODE_DAYS = 60
# Thresholds at which assessment._alerts raises the pulse and glucose alerts.
AF_ALERT_PROBABILITY = 0.5
GLUCOSE_ALERT_DAYS = 2

AGE_MIN, AGE_MAX = 18.0, 100.0
EGFR_MIN, EGFR_MAX = 5.0, 150.0  # ml/min/1.73 m²
UACR_MAX = 30_000.0  # mg/g; the top of the filter's grid
URINE_CREATININE_MAX = 1_000.0  # mg/dl
MAX_SAMPLES = 30
MAX_READINGS = 200  # BP, pulse or glucose readings per request
SBP_MIN, SBP_MAX = 60.0, 300.0  # mmHg
DBP_MIN, DBP_MAX = 30.0, 200.0
GLUCOSE_MIN, GLUCOSE_MAX = 20.0, 600.0  # mg/dl; what a glucose meter can read
DATE_MIN, DATE_MAX = dt.date(2000, 1, 1), dt.date(2100, 12, 31)

DIGITS = 6  # decimals in responses: plenty for plotting and stable across runs

# Short text for each protocol action, for buttons and headers (the model has none).
# The keys are machine values the web front end compares against: keep them in Spanish.
ACTION_LABELS = Labels(
    {
        "tira": ("Tira en casa", "Strip at home"),
        "tubo": ("Tubo al laboratorio", "Tube to the lab"),
        "esperar": ("Esperar", "Wait"),
        "fin_normal": ("Fin: prueba normal", "Done: normal test"),
        "centro": ("Fin: centro de salud", "Done: health center"),
        "repetir_cronicidad": ("Repetir a los 3 meses", "Repeat in 3 months"),
    }
)

Action = Literal["tira", "tubo", "esperar", "fin_normal", "centro", "repetir_cronicidad"]
Status = Literal["sin_medir", "descartada", "dudosa", "pendiente_cronicidad", "confirmada"]


# --- Input ---


class Answers(BaseModel):
    """Answers to the pre-test questions. Missing or ``null`` = not answered."""

    exercise_24h: bool | None = Field(None, description=urine_context.FACTORS["exercise_24h"].question)
    fever: bool | None = Field(None, description=urine_context.FACTORS["fever"].question)
    menstruation: bool | None = Field(
        None,
        description=(
            f"{urine_context.FACTORS['menstruation'].question} "
            f"Only counts for women under {urine_context.FACTORS['menstruation'].women_under:g}."
        ),
    )
    uti_symptoms: bool | None = Field(None, description=urine_context.FACTORS["uti_symptoms"].question)


class PatientIn(BaseModel):
    """What the filter needs to know about the patient."""

    age: float = Field(description=f"Age in years (between {AGE_MIN:g} and {AGE_MAX:g}).")
    female: bool = Field(description="Is female.")
    diabetes: bool = Field(description="Has diagnosed diabetes.")
    egfr: float | None = Field(
        None,
        description=(
            f"Estimated glomerular filtration rate (eGFR), in ml/min/1.73 m² (between {EGFR_MIN:g} and {EGFR_MAX:g}). "
            "If missing, the model assumes normal filtration."
        ),
    )


class StripSampleIn(BaseModel):
    """A strip done at home: the color level read on each pad."""

    kind: Literal["tira"] = Field(description="Sample type (``tira`` = strip).")
    date: dt.date = Field(description="Day it was done (YYYY-MM-DD).")
    albumin_mg_l: float = Field(description="Level read on the albumin pad, in mg/l (one of those in /config).")
    creatinine_mg_dl: float = Field(
        description="Level read on the creatinine pad, in mg/dl (one of those in /config)."
    )
    answers: Answers | None = Field(
        None, description="Patient answers about this sample. Stored with it; they change the probability."
    )


class TubeSampleIn(BaseModel):
    """A tube sent to the lab, which measures the albumin-to-creatinine ratio (UACR)."""

    kind: Literal["tubo"] = Field(description="Sample type (``tubo`` = tube).")
    date: dt.date = Field(description="Day it was collected (YYYY-MM-DD).")
    uacr: float = Field(description="Albumin-to-creatinine ratio measured by the lab, in mg/g (greater than 0).")
    creatinine_mg_dl: float | None = Field(
        None, description="Urine creatinine of the sample, in mg/dl. If missing, typical urine dilution is assumed."
    )
    answers: Answers | None = Field(
        None, description="Patient answers about this sample. Stored with it; they change the probability."
    )


SampleIn = Annotated[StripSampleIn | TubeSampleIn, Field(discriminator="kind")]


class StepIn(BaseModel):
    """Everything needed to decide the next step: the server remembers nothing."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "patient": {"age": 58, "female": True, "diabetes": False, "egfr": 88},
                    "channel": "aplicación",
                    "today": "2026-11-17",
                    "samples": [
                        {
                            "kind": "tira",
                            "date": "2026-11-17",
                            "albumin_mg_l": 30,
                            "creatinine_mg_dl": 100,
                            "answers": {"exercise_24h": False, "fever": False, "uti_symptoms": False},
                        }
                    ],
                }
            ]
        }
    )

    patient: PatientIn = Field(description="The patient.")
    channel: Channel = Field(
        DEFAULT_CHANNEL,
        description="Channel used for the test (the ``value`` from /config; the ``key`` also works). Defaults to the app.",
    )
    today: dt.date = Field(
        description="Today's date for the patient (YYYY-MM-DD). The web app advances it; the server does not use the clock."
    )
    samples: list[SampleIn] = Field(
        default_factory=list, description=f"Samples taken up to today, strips and tubes (at most {MAX_SAMPLES})."
    )
    answers: Answers | None = Field(
        None,
        description="TODAY's answers to the pre-test questions, if already given. They only decide whether the test is postponed.",
    )
    episode_start: dt.date | None = Field(
        None,
        description=(
            "Day from which the kit's used strips and tubes are counted. "
            f"Defaults to the last {EPISODE_DAYS} days."
        ),
    )

    @field_validator("channel", mode="before")
    @classmethod
    def _channel_by_key(cls, value: object) -> object:
        """Also accepts the channel key ("APP"), besides its value ("aplicación")."""
        if isinstance(value, str) and value in Channel.__members__:
            return Channel[value]
        return value


class BPReadingIn(BaseModel):
    """One home cuff reading."""

    date: dt.date = Field(description="Day of the reading (YYYY-MM-DD).")
    sbp: float = Field(description=f"Systolic pressure, in mmHg (between {SBP_MIN:g} and {SBP_MAX:g}).")
    dbp: float = Field(description=f"Diastolic pressure, in mmHg (between {DBP_MIN:g} and {DBP_MAX:g}).")
    evening: bool = Field(False, description="Evening reading (otherwise, morning).")


class BPIn(BaseModel):
    """A patient's home blood pressure monitoring."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "readings": [
                        {"date": "2026-11-09", "sbp": 151, "dbp": 92, "evening": False},
                        {"date": "2026-11-10", "sbp": 147, "dbp": 90, "evening": False},
                        {"date": "2026-11-10", "sbp": 151, "dbp": 92, "evening": True},
                    ]
                }
            ]
        }
    )

    readings: list[BPReadingIn] = Field(
        description=f"Home monitoring readings (between 1 and {MAX_READINGS}). Ideally 7 days, two in the morning and two in the evening."
    )


class RhythmCheckIn(BaseModel):
    """A pulse check with the phone or the watch."""

    date: dt.date = Field(description="Day of the check (YYYY-MM-DD).")
    irregular: bool = Field(description="The pulse was irregular.")


class RhythmIn(BaseModel):
    """Pulse checks of a patient without diagnosed atrial fibrillation."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "age": 77,
                    "female": False,
                    "checks": [{"date": "2026-11-12", "irregular": True}, {"date": "2026-11-13", "irregular": True}],
                }
            ]
        }
    )

    age: float = Field(description=f"Age in years (between {AGE_MIN:g} and {AGE_MAX:g}).")
    female: bool = Field(description="Is female.")
    checks: list[RhythmCheckIn] = Field(
        default_factory=list, description=f"Pulse checks (at most {MAX_READINGS})."
    )


class GlucoseReadingIn(BaseModel):
    """A capillary glucose measured at home with a glucose meter."""

    date: dt.date = Field(description="Day of the reading (YYYY-MM-DD).")
    mg_dl: float = Field(description=f"Glucose, in mg/dl (between {GLUCOSE_MIN:g} and {GLUCOSE_MAX:g}).")
    fasting_hours: float = Field(
        FASTING_HOURS, description=f"Hours since the last meal (between 0 and 24). {FASTING_HOURS:g} or more counts as fasting."
    )


class GlucoseIn(BaseModel):
    """Capillary glucose readings of a patient without diagnosed diabetes."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "readings": [
                        {"date": "2026-11-10", "mg_dl": 134, "fasting_hours": 10},
                        {"date": "2026-11-12", "mg_dl": 141, "fasting_hours": 10},
                        {"date": "2026-11-14", "mg_dl": 129, "fasting_hours": 10},
                    ]
                }
            ]
        }
    )

    readings: list[GlucoseReadingIn] = Field(
        default_factory=list, description=f"Glucose meter readings (at most {MAX_READINGS})."
    )


# --- Output ---


class ErrorOut(BaseModel):
    """Domain error (400)."""

    detail: str = Field(description="Which value is invalid, in one sentence.")


class QuestionOut(BaseModel):
    """Pre-test question."""

    key: str = Field(description="Question key; it is the field name in the answers.")
    text: str = Field(description="Question as the patient reads it.")


class KitOut(BaseModel):
    """Kit contents and what has been used in the current episode."""

    channel: Channel = Field(description="Kit channel.")
    strips_total: int = Field(description="Strips in the kit.")
    strips_used: int = Field(description="Strips used in the episode.")
    tubes_total: int = Field(description="Tubes in the kit.")
    tubes_used: int = Field(description="Tubes used in the episode.")


class TrajectoryPointOut(BaseModel):
    """Ratio estimate at the date of a sample, using all samples."""

    date: dt.date = Field(description="Sample date.")
    median: float = Field(description="Median of the true albumin-to-creatinine ratio, in mg/g.")
    low: float = Field(description="10th percentile, in mg/g.")
    high: float = Field(description="90th percentile, in mg/g.")
    p_a2_plus: float = Field(description="Probability of albuminuria (true ratio of 30 mg/g or more).")


class AssessmentOut(BaseModel):
    """Albuminuria status according to the Bayesian filter."""

    as_of: dt.date | None = Field(description="Date the status refers to.")
    status: Status = Field(description="Albuminuria status.")
    status_label: str = Field(description="Status, as the model names it.")
    category: Literal["A1", "A2", "A3"] = Field(description="Most likely KDIGO category.")
    p_a1: float = Field(description="Probability of A1 (under 30 mg/g).")
    p_a2: float = Field(description="Probability of A2 (30 to 300 mg/g).")
    p_a3: float = Field(description="Probability of A3 (over 300 mg/g).")
    median: float = Field(description="Median of the true ratio, in mg/g.")
    low: float = Field(description="10th percentile, in mg/g.")
    high: float = Field(description="90th percentile, in mg/g.")
    chronicity_met: bool = Field(
        description="The chronicity criterion is met (two high results more than 3 months apart)."
    )
    repeat_from: dt.date | None = Field(description="Date from which a high sample would meet chronicity.")
    trajectory: list[TrajectoryPointOut] = Field(description="One point per sample, in chronological order.")


class SampleOut(BaseModel):
    """A sample from the request, ready to display."""

    kind: Literal["tira", "tubo"] = Field(description="Sample type (``tira`` = strip, ``tubo`` = tube).")
    date: dt.date = Field(description="Sample date.")
    label: str = Field(description="Reading in one line.")
    nominal_uacr: float = Field(
        description="Ratio suggested by the reading, in mg/g: the one measured in the tube, or 100 × albumin / creatinine on the strip."
    )


class StepOut(BaseModel):
    """The patient's next step, with the status that justifies it."""

    action: Action = Field(description="What is due now.")
    action_label: str = Field(description="The action, in a few words.")
    on: dt.date = Field(description="Day it is due.")
    finished: bool = Field(description="The episode has ended (normal test or referred to the health center).")
    patient_message: str = Field(description="What the patient reads, verbatim from the model.")
    clinician_note: str = Field(description="What goes into the medical record, verbatim from the model.")
    p_albuminuria: float = Field(description="Probability of albuminuria (true ratio of 30 mg/g or more).")
    resolve_probability: float | None = Field(
        description="Probability that the requested test resolves the doubt; ``null`` if none is requested."
    )
    questions: list[QuestionOut] = Field(description="Questions to ask the patient before the test.")
    kit: KitOut = Field(description="Kit contents and what has been used.")
    assessment: AssessmentOut = Field(description="Albuminuria status.")
    samples: list[SampleOut] = Field(description="The request's samples, in chronological order (that of ``trajectory``).")


class ChannelOut(BaseModel):
    """A channel for doing the test and its matching kit."""

    key: str = Field(description="Channel key.")
    value: str = Field(description="Channel name; it is what is sent in ``channel``.")
    strips: int = Field(description="Strips in the kit.")
    tubes: int = Field(description="Tubes in the kit.")
    uses_strip: bool = Field(description="The channel uses strips (otherwise, tube only).")
    strip_name: str | None = Field(description="How the strip is read in this channel.")


class StripOut(BaseModel):
    """Color levels that can be read on the strip."""

    albumin_levels_mg_l: list[float] = Field(description="Albumin pad levels, in mg/l.")
    creatinine_levels_mg_dl: list[float] = Field(description="Creatinine pad levels, in mg/dl.")


class QuestionInfoOut(BaseModel):
    """Pre-test question and what happens if the answer is yes."""

    key: str = Field(description="Question key; it is the field name in the answers.")
    text: str = Field(description="Question as the patient reads it.")
    wait_days: int = Field(description="Days the test is postponed if the answer is yes.")
    advice: str = Field(description="Advice given if the answer is yes.")
    audience: str = Field(description="Who is asked.")


class PatientPresetOut(BaseModel):
    """Example patient (made up)."""

    id: str = Field(description="Example patient identifier.")
    name: str = Field(description="Made-up name.")
    summary: str = Field(description="Who they are, in one line.")
    age: float = Field(description="Age in years.")
    female: bool = Field(description="Is female.")
    diabetes: bool = Field(description="Has diagnosed diabetes.")
    egfr: float = Field(description="Estimated glomerular filtration rate (eGFR), in ml/min/1.73 m².")
    channel: Channel = Field(description="Channel used for the test.")


class ScriptStepOut(BaseModel):
    """One step of a guided walkthrough: what the patient does."""

    kind: Literal["respuestas", "tira", "tubo"] = Field(
        description=(
            "``respuestas``: answers today's questions. "
            "``tira`` (strip) or ``tubo`` (tube): does the test on the day it was due."
        )
    )
    answers: Answers | None = Field(
        None, description="The answers: today's (``respuestas``) or those stored with the sample."
    )
    albumin_mg_l: float | None = Field(None, description="Strip albumin reading, in mg/l.")
    creatinine_mg_dl: float | None = Field(None, description="Strip creatinine reading, in mg/dl.")
    uacr: float | None = Field(None, description="Tube result, in mg/g.")
    note: str = Field(description="What happens in this step, for the demo presenter.")


class ScriptOut(BaseModel):
    """Guided walkthrough of an example patient."""

    id: str = Field(description="Walkthrough identifier.")
    title: str = Field(description="Short title.")
    patient_id: str = Field(description="Example patient who does it.")
    summary: str = Field(description="What the walkthrough shows, in one line.")
    steps: list[ScriptStepOut] = Field(description="What the patient does, in order.")


class ConfigOut(BaseModel):
    """What the patient app needs before starting."""

    today: dt.date = Field(description="Date the demo starts.")
    channels: list[ChannelOut] = Field(description="Channels through which the test can be done, and their kit.")
    strip: StripOut = Field(description="Strip color levels.")
    questions: list[QuestionInfoOut] = Field(description="Pre-test questions.")
    patients: list[PatientPresetOut] = Field(description="Example patients (synthetic).")
    scripts: list[ScriptOut] = Field(description="Guided walkthroughs for the demo.")


class BPOut(BaseModel):
    """Summary of home blood pressure monitoring (the first day is discarded)."""

    n: int = Field(description="Readings used.")
    days: int = Field(description="Days used.")
    sbp: float = Field(description="Mean systolic, in mmHg.")
    dbp: float = Field(description="Mean diastolic, in mmHg.")
    sbp_se: float = Field(description="Standard error of the mean systolic.")
    dbp_se: float = Field(description="Standard error of the mean diastolic.")
    p_sbp_high: float = Field(
        description=f"Probability that the true mean systolic is {HOME_SBP_LIMIT:g} mmHg or more."
    )
    p_dbp_high: float = Field(
        description=f"Probability that the true mean diastolic is {HOME_DBP_LIMIT:g} mmHg or more."
    )
    p_high: float = Field(description="Probability of high blood pressure at home: the larger of the two above.")
    valid: bool = Field(description="There are enough readings for the mean to be valid.")
    message: str = Field(description="Conclusion, verbatim from the model.")


class RhythmOut(BaseModel):
    """Probability of undiagnosed atrial fibrillation."""

    prior: float = Field(description="Probability of undiagnosed atrial fibrillation by age and sex (OFRECE study).")
    probability: float = Field(description="Probability of atrial fibrillation after the checks.")
    alert: bool = Field(description=f"The probability reaches {AF_ALERT_PROBABILITY:g}: an alert is needed.")
    message: str | None = Field(description="Alert text, verbatim from the model; ``null`` if there is no alert.")


class GlucoseOut(BaseModel):
    """Summary of fasting glucose readings taken at home."""

    fasting_mean_mg_dl: float | None = Field(
        description="Geometric mean of the fasting readings, in mg/dl; ``null`` if there are none."
    )
    fasting_readings: int = Field(description="Fasting readings.")
    days_above_126: int = Field(
        description=f"Distinct days with fasting glucose of {DIABETES_FASTING_GLUCOSE:g} mg/dl or more."
    )
    alert: bool = Field(description=f"{GLUCOSE_ALERT_DAYS} or more days above: needs confirmation.")
    message: str | None = Field(description="Alert text, verbatim from the model; ``null`` if there is no alert.")


# --- Example patients and guided walkthroughs (made up) ---

# Built per language (the summaries and notes are display text); use ``patients()`` / ``scripts()``.


def patients() -> tuple[PatientPresetOut, ...]:
    """Example patients, with their summary in the current language."""
    return (
        PatientPresetOut(
            id="julian", name="Julián", age=62, female=False, diabetes=False, egfr=85, channel=Channel.APP,
            summary=t(
                "62 años, sin diabetes, FG 85. Nunca se le ha mirado la albúmina en la orina.",
                "62 years old, no diabetes, eGFR 85. His urine albumin has never been checked.",
            ),
        ),
        PatientPresetOut(
            id="pilar", name="Pilar", age=58, female=True, diabetes=False, egfr=88, channel=Channel.APP,
            summary=t("58 años, sin diabetes, FG 88. Es su primer cribado.", "58 years old, no diabetes, eGFR 88. Her first screening."),
        ),
        PatientPresetOut(
            id="marta", name="Marta", age=47, female=True, diabetes=True, egfr=92, channel=Channel.APP,
            summary=t(
                "47 años, con diabetes, FG 92. Le toca el cribado de este año.",
                "47 years old, with diabetes, eGFR 92. Due for this year's screening.",
            ),
        ),
        PatientPresetOut(
            id="vicente", name="Vicente", age=73, female=False, diabetes=True, egfr=52, channel=Channel.APP,
            summary=t(
                "73 años, con diabetes y filtrado bajo (FG 52). Parte de un riesgo alto.",
                "73 years old, with diabetes and low filtration (eGFR 52). Starts from a high risk.",
            ),
        ),
    )  # fmt: skip


# Only the numeric fields are read from here, so the language it was built in does not matter.
_PATIENT_BY_ID = {p.id: p for p in patients()}


def _no_to_all(patient_id: str) -> Answers:
    """Answers no to the questions the model asks that patient."""
    patient = _PATIENT_BY_ID[patient_id]
    return Answers(**{key: False for key, _ in urine_context.questions(patient.female, patient.age)})


def _answers_step(patient_id: str, note: str, **yes: bool) -> ScriptStepOut:
    return ScriptStepOut(kind="respuestas", answers=_no_to_all(patient_id).model_copy(update=yes), note=note)


def _strip_step(patient_id: str, albumin_mg_l: float, creatinine_mg_dl: float, note: str) -> ScriptStepOut:
    return ScriptStepOut(
        kind="tira", answers=_no_to_all(patient_id), albumin_mg_l=albumin_mg_l, creatinine_mg_dl=creatinine_mg_dl, note=note
    )


def _tube_step(patient_id: str, uacr: float, note: str) -> ScriptStepOut:
    return ScriptStepOut(kind="tubo", answers=_no_to_all(patient_id), uacr=uacr, note=note)


def scripts() -> tuple[ScriptOut, ...]:
    """Guided walkthroughs, with their texts in the current language."""
    first_strip = t(
        "Primera tira: algo de albúmina (30 mg/l), con creatinina de 100 mg/dl.",
        "First strip: some albumin (30 mg/l), with creatinine at 100 mg/dl.",
    )
    return (
        ScriptOut(
            id="normal",
            title=t("Normal a la primera", "Normal on the first try"),
            patient_id="julian",
            summary=t(
                "Contesta que no a las preguntas previas, hace una tira y sale normal: hasta dentro de un año.",
                "Answers no to the pre-test questions, does one strip and it is normal: see you in a year.",
            ),
            steps=[
                _answers_step("julian", t(
                    "Antes de la prueba contesta que no a todas las preguntas.",
                    "Before the test, he answers no to every question.",
                )),
                _strip_step("julian", 10, 100, t(
                    "Hace la tira: albúmina en el nivel más bajo (10 mg/l), con creatinina de 100 mg/dl.",
                    "Does the strip: albumin at the lowest level (10 mg/l), with creatinine at 100 mg/dl.",
                )),
            ],
        ),
        ScriptOut(
            id="confirmada",
            title=t("De la duda a la confirmación", "From doubt to confirmation"),
            patient_id="pilar",
            summary=t(
                "Dos tiras dudosas, dos tubos al laboratorio y, tres meses después, la repetición que lo confirma.",
                "Two doubtful strips, two tubes to the lab and, three months later, the repeat test that confirms it.",
            ),
            steps=[
                _strip_step("pilar", 30, 100, first_strip),
                _strip_step("pilar", 30, 50, t(
                    "Segunda tira: la misma albúmina (30 mg/l) en una orina más diluida (creatinina de 50 mg/dl).",
                    "Second strip: the same albumin (30 mg/l) in more dilute urine (creatinine at 50 mg/dl).",
                )),
                _tube_step("pilar", 58, t("Primer tubo: el laboratorio mide 58 mg/g.", "First tube: the lab measures 58 mg/g.")),
                _tube_step("pilar", 64, t("Segundo tubo: el laboratorio mide 64 mg/g.", "Second tube: the lab measures 64 mg/g.")),
                _tube_step("pilar", 71, t(
                    "Tres meses después, el tubo de la repetición: 71 mg/g.",
                    "Three months later, the repeat tube: 71 mg/g.",
                )),
            ],
        ),
        ScriptOut(
            id="aplazada",
            title=t("Aplazada por fiebre", "Postponed due to fever"),
            patient_id="marta",
            summary=t(
                "Tiene fiebre: la prueba se aplaza en vez de gastar una tira en una muestra que no vale.",
                "She has a fever: the test is postponed instead of wasting a strip on an unreliable sample.",
            ),
            steps=[
                _answers_step("marta", t(
                    "Antes de la prueba contesta que tiene fiebre.",
                    "Before the test, she answers that she has a fever.",
                ), fever=True),
                _strip_step("marta", 10, 100, t(
                    "Pasada la espera hace la tira: albúmina de 10 mg/l, con creatinina de 100 mg/dl.",
                    "After the wait she does the strip: albumin at 10 mg/l, with creatinine at 100 mg/dl.",
                )),
            ],
        ),
        ScriptOut(
            id="laboratorio",
            title=t("Riesgo alto: de la tira al laboratorio", "High risk: from the strip to the lab"),
            patient_id="vicente",
            summary=t(
                "Parte de un riesgo alto: tras una tira dudosa no se pide otra, sino el tubo, y el laboratorio lo aclara.",
                "Starts from a high risk: after a doubtful strip the tube is requested, not another strip, and the lab settles it.",
            ),
            steps=[
                _strip_step("vicente", 30, 100, first_strip),
                _tube_step("vicente", 12, t("El laboratorio mide 12 mg/g.", "The lab measures 12 mg/g.")),
            ],
        ),
    )  # fmt: skip


# --- Shared pieces ---

_ERRORS = {400: {"model": ErrorOut, "description": "Some value is invalid; ``detail`` says which one."}}

# The filter caches the strip tables and is not meant for several threads at once.
_MODEL_LOCK = threading.Lock()
# Already computed /step responses. The route is a pure function of the request and the
# language, so replaying a walkthrough (the usual case in the demo) recomputes nothing.
_STEP_CACHE: OrderedDict[str, StepOut] = OrderedDict()
_STEP_CACHE_SIZE = 512


@lru_cache(maxsize=1)
def _filter() -> AlbuminuriaFilter:
    """The albuminuria filter for the demo population, loaded once."""
    return load_default_filter(POPULATION)


def _require(condition: bool, message: str) -> None:
    """Domain error: 400 with a sentence that can be shown as is."""
    if not condition:
        raise HTTPException(status_code=400, detail=message)


def _require_date(day: dt.date, what: str) -> None:
    _require(
        DATE_MIN <= day <= DATE_MAX,
        t(
            f"{what} tiene que estar entre los años {DATE_MIN.year} y {DATE_MAX.year}.",
            f"{what} must be between the years {DATE_MIN.year} and {DATE_MAX.year}.",
        ),
    )


def _require_age(age: float) -> None:
    _require(
        AGE_MIN <= age <= AGE_MAX,
        t(
            f"La edad tiene que estar entre {AGE_MIN:g} y {AGE_MAX:g} años.",
            f"Age must be between {AGE_MIN:g} and {AGE_MAX:g} years.",
        ),
    )


def _levels(levels: tuple[float, ...], unit: str) -> str:
    """A pad's levels, for a sentence: "10, 30, 80 and 150 mg/l" ("10, 30, 80 y 150 mg/l")."""
    names = [f"{level:g}" for level in levels]
    return f"{', '.join(names[:-1])} {t('y', 'and')} {names[-1]} {unit}"


def _error_date(day: dt.date) -> str:
    """Date in an error message: "18/11/2026" in Spanish (as before), "November 18, 2026" in English."""
    return f"{day:%d/%m/%Y}" if is_es() else fmt_date(day, weekday=False)


def _context(answers: Answers | None) -> SampleContext | None:
    return None if answers is None else SampleContext(**answers.model_dump())


def _kit_size(kit: HomeKit) -> tuple[int, int]:
    """Strips and tubes the protocol may request with that kit."""
    return (kit.strips if kit.strip is not None else 0), (kit.tubes if kit.tube else 0)


def _alert_text(*, glucose: list[GlucoseReading] | None = None, p_af: float | None = None) -> str | None:
    """Glucose or pulse alert text exactly as the model writes it.

    The model does not expose those strings: they are built inside ``assessment._alerts``, an
    internal function. It is called with an empty record so only the requested alert can come out.
    If that function changed, the route still responds, without text.
    """
    record = clinical.ClinicalRecord(age=60.0, female=False, home_glucose=glucose or [])
    try:
        alerts = clinical._alerts(record, SimpleNamespace(status="sin_medir"), None, None, {}, p_af, None)
    except Exception:
        log.exception("Could not get the alert text from the model")
        return None
    return alerts[0] if len(alerts) == 1 else None


# --- Configuration ---


def _config() -> ConfigOut:
    return _config_in(lang())


@lru_cache(maxsize=2)
def _config_in(language: str) -> ConfigOut:
    """/config in one language (``language`` is the cache key; the texts read the current one)."""
    channels = [
        ChannelOut(
            key=channel.name,
            value=channel.value,
            strips=_kit_size(kit)[0],
            tubes=_kit_size(kit)[1],
            uses_strip=kit.strip is not None,
            strip_name=kit.strip.name if kit.strip is not None else None,
        )
        for channel, kit in KITS.items()
    ]
    questions = []
    for key in urine_context.QUESTIONS:
        factor = urine_context.FACTORS[key]
        if factor.women_under is None:
            audience = t("todos", "everyone")
        else:
            audience = t(f"mujeres menores de {factor.women_under:g} años", f"women under {factor.women_under:g}")
        questions.append(
            QuestionInfoOut(key=key, text=factor.question, wait_days=factor.wait_days, advice=factor.advice, audience=audience)
        )
    return ConfigOut(
        today=DEMO_TODAY,
        channels=channels,
        strip=StripOut(
            albumin_levels_mg_l=list(PHONE_STRIP.albumin_levels),
            creatinine_levels_mg_dl=list(PHONE_STRIP.creatinine_levels),
        ),
        questions=questions,
        patients=list(patients()),
        scripts=list(scripts()),
    )


@router.get("/config", response_model=ConfigOut, summary="Patient app configuration")
def config() -> ConfigOut:
    """What the app needs before starting: demo date, channels, strip levels, pre-test
    questions, example patients and guided walkthroughs.

    A walkthrough is replayed against ``/step`` like this: request the first step with ``today``
    and no samples, then, for each walkthrough step,

    - ``respuestas`` (answers): repeat the request with those ``answers``. If the response is
      ``esperar`` (wait), advance ``today`` to its ``on`` and request again, without ``answers``.
    - ``tira`` (strip) or ``tubo`` (tube): advance ``today`` to the ``on`` of the last response,
      add the sample with that date (and its ``answers``) and request again.
    """
    return _config()


# --- At-home urine protocol ---


def _validate_step(body: StepIn, kit: HomeKit) -> None:
    """Domain errors of /step. Raises a 400 with the first one found."""
    _require_age(body.patient.age)
    egfr = body.patient.egfr
    _require(
        egfr is None or EGFR_MIN <= egfr <= EGFR_MAX,
        t(
            f"El filtrado glomerular (FG) tiene que estar entre {EGFR_MIN:g} y {EGFR_MAX:g} ml/min/1,73 m².",
            f"eGFR must be between {EGFR_MIN:g} and {EGFR_MAX:g} ml/min/1.73 m².",
        ),
    )
    _require_date(body.today, t("La fecha de hoy (today)", "Today's date (today)"))
    _require(
        body.episode_start is None or body.episode_start <= body.today,
        t(
            "El inicio del episodio (episode_start) no puede ser posterior a la fecha de hoy.",
            "The episode start (episode_start) cannot be after today's date.",
        ),
    )
    _require(
        len(body.samples) <= MAX_SAMPLES,
        t(f"Se admiten como mucho {MAX_SAMPLES} muestras.", f"At most {MAX_SAMPLES} samples are allowed."),
    )
    for number, sample in enumerate(body.samples, start=1):
        _require_date(sample.date, t(f"La fecha de la muestra {number}", f"The date of sample {number}"))
        _require(
            sample.date <= body.today,
            t(
                f"La muestra {number} es del {_error_date(sample.date)}, posterior a la fecha de hoy ({_error_date(body.today)}).",
                f"Sample {number} is dated {_error_date(sample.date)}, after today's date ({_error_date(body.today)}).",
            ),
        )
        if isinstance(sample, StripSampleIn):
            _require(
                kit.strip is not None,
                t(
                    f"El canal «{kit.channel.value}» no usa tiras: solo admite muestras de tubo.",
                    f'The "{kit.channel.value}" channel does not use strips: it only accepts tube samples.',
                ),
            )
            _require(
                sample.albumin_mg_l in kit.strip.albumin_levels,
                t(
                    f"Muestra {number}: la tira no tiene el nivel de albúmina {sample.albumin_mg_l:g} mg/l. "
                    f"Niveles posibles: {_levels(kit.strip.albumin_levels, 'mg/l')}.",
                    f"Sample {number}: the strip has no albumin level of {sample.albumin_mg_l:g} mg/l. "
                    f"Possible levels: {_levels(kit.strip.albumin_levels, 'mg/l')}.",
                ),
            )
            _require(
                sample.creatinine_mg_dl in kit.strip.creatinine_levels,
                t(
                    f"Muestra {number}: la tira no tiene el nivel de creatinina {sample.creatinine_mg_dl:g} mg/dl. "
                    f"Niveles posibles: {_levels(kit.strip.creatinine_levels, 'mg/dl')}.",
                    f"Sample {number}: the strip has no creatinine level of {sample.creatinine_mg_dl:g} mg/dl. "
                    f"Possible levels: {_levels(kit.strip.creatinine_levels, 'mg/dl')}.",
                ),
            )
        else:
            _require(
                0.0 < sample.uacr <= UACR_MAX,
                t(
                    f"Muestra {number}: el resultado del laboratorio (uacr) tiene que ser mayor que 0 "
                    f"y no pasar de {UACR_MAX:g} mg/g.",
                    f"Sample {number}: the lab result (uacr) must be greater than 0 "
                    f"and no more than {UACR_MAX:g} mg/g.",
                ),
            )
            creatinine = sample.creatinine_mg_dl
            _require(
                creatinine is None or 0.0 < creatinine <= URINE_CREATININE_MAX,
                t(
                    f"Muestra {number}: la creatinina en orina tiene que ser mayor que 0 "
                    f"y no pasar de {URINE_CREATININE_MAX:g} mg/dl.",
                    f"Sample {number}: urine creatinine must be greater than 0 "
                    f"and no more than {URINE_CREATININE_MAX:g} mg/dl.",
                ),
            )


def _model_sample(sample: StripSampleIn | TubeSampleIn, kit: HomeKit) -> StripSample | UrineSample:
    context = _context(sample.answers)
    if isinstance(sample, StripSampleIn):
        return StripSample(sample.date, kit.strip, sample.albumin_mg_l, sample.creatinine_mg_dl, context=context)
    return UrineSample(sample.date, sample.uacr, FIRST_MORNING, creatinine_mg_dl=sample.creatinine_mg_dl, context=context)


def _sample_out(sample: StripSample | UrineSample) -> SampleOut:
    """The sample in one line, in the format of scripts/demo_casa.py."""
    if isinstance(sample, StripSample):
        label = t(
            f"Tira: albúmina {sample.albumin_mg_l:.0f} mg/l, creatinina {sample.creatinine_mg_dl:.0f} mg/dl",
            f"Strip: albumin {sample.albumin_mg_l:.0f} mg/l, creatinine {sample.creatinine_mg_dl:.0f} mg/dl",
        )
        return SampleOut(kind="tira", date=sample.date, label=label, nominal_uacr=clean(sample.nominal_uacr, digits=DIGITS))
    return SampleOut(
        kind="tubo", date=sample.date, label=t(f"Tubo: {sample.uacr:.0f} mg/g", f"Tube: {sample.uacr:.0f} mg/g"), nominal_uacr=clean(sample.uacr, digits=DIGITS)
    )


_ASSESSMENT_INTERNALS = frozenset({"belief", "action", "next_sample_resolves", "log_evidence", "egfr_components"})


def _compute_step(body: StepIn) -> StepOut:
    kit = KITS[body.channel]
    _validate_step(body, kit)
    # Chronological (stable) order: the one the filter and the trajectory use.
    samples = [_model_sample(s, kit) for s in sorted(body.samples, key=lambda s: s.date)]
    patient = Patient(body.patient.age, body.patient.female, body.patient.diabetes, body.patient.egfr, samples)
    # The episode window is always passed explicitly, so the returned kit is counted
    # with the same window the protocol uses.
    start = body.episode_start or body.today - dt.timedelta(days=EPISODE_DAYS)
    step = next_step(_filter(), patient, kit, body.today, context=_context(body.answers), episode_start=start)

    recent = [s for s in samples if s.date >= start]
    strips_total, tubes_total = _kit_size(kit)
    assessment = clean(step.assessment, exclude=_ASSESSMENT_INTERNALS, digits=DIGITS)
    return StepOut(
        action=step.action,
        action_label=ACTION_LABELS[step.action],
        on=step.on,
        finished=step.finished,
        patient_message=step.patient_message,
        clinician_note=step.clinician_note,
        p_albuminuria=clean(step.p_albuminuria, digits=DIGITS),
        resolve_probability=clean(step.resolve_probability, digits=DIGITS),
        questions=[QuestionOut(key=key, text=text) for key, text in step.questions],
        kit=KitOut(
            channel=kit.channel,
            strips_total=strips_total,
            strips_used=sum(isinstance(s, StripSample) for s in recent),
            tubes_total=tubes_total,
            tubes_used=sum(isinstance(s, UrineSample) for s in recent),
        ),
        assessment=AssessmentOut(status_label=STATUS_LABELS[step.assessment.status], **assessment),
        samples=[_sample_out(s) for s in samples],
    )


def _step(body: StepIn) -> StepOut:
    """/step response, without recomputing a request already seen (in the same language)."""
    key = f"{lang()}:{body.model_dump_json()}"
    with _MODEL_LOCK:
        cached = _STEP_CACHE.get(key)
        if cached is not None:
            _STEP_CACHE.move_to_end(key)
            return cached
        result = _compute_step(body)
        _STEP_CACHE[key] = result
        if len(_STEP_CACHE) > _STEP_CACHE_SIZE:
            _STEP_CACHE.popitem(last=False)
        return result


@router.post("/step", response_model=StepOut, responses=_ERRORS, summary="Next step of the at-home urine protocol")
def step(body: StepIn) -> StepOut:
    """What the patient has to do now, given their samples up to today.

    It is ``protocol.next_step`` on the Bayesian albuminuria filter: strips first, since they are
    cheap; the tube for the lab only if the doubt remains; and the test is postponed if today's
    answers say the sample would not be reliable. The patient message and the record note are
    the model's.
    """
    return _step(body)


# --- Other measurements at home ---


def _too_many_readings() -> str:
    return t(f"Se admiten como mucho {MAX_READINGS} lecturas.", f"At most {MAX_READINGS} readings are allowed.")


def _reading_date(number: int) -> str:
    return t(f"La fecha de la lectura {number}", f"The date of reading {number}")


@router.post("/bp", response_model=BPOut, responses=_ERRORS, summary="Blood pressure measured at home")
def blood_pressure(body: BPIn) -> BPOut:
    """Mean of home blood pressure monitoring and probability that it is high (135/85 mmHg at home).

    Follows the usual protocol: the first day is discarded and at least 12 readings over 3 days are needed.
    """
    _require(len(body.readings) >= 1, t("Hace falta al menos una lectura de tensión.", "At least one blood pressure reading is needed."))
    _require(len(body.readings) <= MAX_READINGS, _too_many_readings())
    for number, reading in enumerate(body.readings, start=1):
        _require_date(reading.date, _reading_date(number))
        _require(
            SBP_MIN <= reading.sbp <= SBP_MAX,
            t(
                f"Lectura {number}: la sistólica tiene que estar entre {SBP_MIN:g} y {SBP_MAX:g} mmHg.",
                f"Reading {number}: systolic must be between {SBP_MIN:g} and {SBP_MAX:g} mmHg.",
            ),
        )
        _require(
            DBP_MIN <= reading.dbp <= DBP_MAX,
            t(
                f"Lectura {number}: la diastólica tiene que estar entre {DBP_MIN:g} y {DBP_MAX:g} mmHg.",
                f"Reading {number}: diastolic must be between {DBP_MIN:g} and {DBP_MAX:g} mmHg.",
            ),
        )
        _require(
            reading.sbp > reading.dbp,
            t(
                f"Lectura {number}: la sistólica tiene que ser mayor que la diastólica.",
                f"Reading {number}: systolic must be higher than diastolic.",
            ),
        )
    summary = summarize_home_bp([BPReading(r.date, r.sbp, r.dbp, r.evening) for r in body.readings])
    return BPOut(p_high=clean(summary.p_high, digits=DIGITS), **clean(summary, digits=DIGITS))


@router.post("/rhythm", response_model=RhythmOut, responses=_ERRORS, summary="Irregular pulse checked at home")
def rhythm(body: RhythmIn) -> RhythmOut:
    """Probability of undiagnosed atrial fibrillation after the pulse checks.

    Starts from the Spanish prevalence by age and sex (OFRECE study) and updates it with each
    check. With a probability of 0.5 or more the alert fires.
    """
    _require_age(body.age)
    _require(
        len(body.checks) <= MAX_READINGS,
        t(f"Se admiten como mucho {MAX_READINGS} comprobaciones.", f"At most {MAX_READINGS} checks are allowed."),
    )
    for number, check in enumerate(body.checks, start=1):
        _require_date(check.date, t(f"La fecha de la comprobación {number}", f"The date of check {number}"))
    checks = [RhythmCheck(c.date, c.irregular) for c in body.checks]
    probability = af_probability(checks, body.age, female=body.female)
    alert = probability >= AF_ALERT_PROBABILITY
    return RhythmOut(
        prior=clean(af_prior(body.age, body.female), digits=DIGITS),
        probability=clean(probability, digits=DIGITS),
        alert=alert,
        message=_alert_text(p_af=probability) if alert else None,
    )


@router.post("/glucose", response_model=GlucoseOut, responses=_ERRORS, summary="Glucose measured at home")
def glucose(body: GlucoseIn) -> GlucoseOut:
    """Summary of fasting capillary glucose readings (8 hours or more without eating).

    With 126 mg/dl or more on two different days the alert fires: it is the diagnostic criterion
    for diabetes, which must be confirmed. The alert assumes the patient has no recorded diabetes.
    """
    _require(len(body.readings) <= MAX_READINGS, _too_many_readings())
    for number, reading in enumerate(body.readings, start=1):
        _require_date(reading.date, _reading_date(number))
        _require(
            GLUCOSE_MIN <= reading.mg_dl <= GLUCOSE_MAX,
            t(
                f"Lectura {number}: la glucosa tiene que estar entre {GLUCOSE_MIN:g} y {GLUCOSE_MAX:g} mg/dl.",
                f"Reading {number}: glucose must be between {GLUCOSE_MIN:g} and {GLUCOSE_MAX:g} mg/dl.",
            ),
        )
        _require(
            0.0 <= reading.fasting_hours <= 24.0,
            t(
                f"Lectura {number}: las horas desde la última comida tienen que estar entre 0 y 24.",
                f"Reading {number}: hours since the last meal must be between 0 and 24.",
            ),
        )
    readings = [GlucoseReading(r.date, r.mg_dl, r.fasting_hours) for r in body.readings]
    fasting = [r for r in readings if r.fasting_hours >= FASTING_HOURS]
    summary = summarize_glucose(fasting)  # with fasting readings, their geometric mean
    days = fasting_days_above(readings)
    alert = days >= GLUCOSE_ALERT_DAYS
    return GlucoseOut(
        fasting_mean_mg_dl=clean(summary[0], digits=DIGITS) if summary else None,
        fasting_readings=len(fasting),
        days_above_126=days,
        alert=alert,
        message=_alert_text(glucose=readings) if alert else None,
    )


# --- Warm-up ---


def _play(script: ScriptOut) -> list[StepOut]:
    """Replays a guided walkthrough as the web app will (see ``config``) and returns each response."""
    preset = _PATIENT_BY_ID[script.patient_id]
    patient = PatientIn(age=preset.age, female=preset.female, diabetes=preset.diabetes, egfr=preset.egfr)
    today, samples = DEMO_TODAY, []

    def ask(answers: Answers | None = None) -> StepOut:
        return _step(StepIn(patient=patient, channel=preset.channel, today=today, samples=samples, answers=answers))

    seen = [ask()]
    for item in script.steps:
        if item.kind == "respuestas":
            seen.append(ask(item.answers))
            if seen[-1].action == "esperar":
                today = seen[-1].on
                seen.append(ask())
            continue
        today = seen[-1].on
        if item.kind == "tira":
            sample = StripSampleIn(
                kind="tira", date=today, albumin_mg_l=item.albumin_mg_l, creatinine_mg_dl=item.creatinine_mg_dl,
                answers=item.answers,
            )  # fmt: skip
        else:
            sample = TubeSampleIn(kind="tubo", date=today, uacr=item.uacr, answers=item.answers)
        samples = [*samples, sample]
        seen.append(ask())
    return seen


def warm_up() -> None:
    """Loads the filter and precomputes the guided walkthroughs in both languages, so the demo does not wait.

    Replaying them fills the response cache and the strip-table cache for the example patients.
    """
    _filter()
    for language in LANGS:
        with use_lang(language):
            _config()
            for script in scripts():
                _play(script)
