"""Live model routes: albuminuria filter, eGFR trend and full patient assessment.

Each route calls the real models in ``src/latenthealth`` and returns their numbers and texts
as they are. They are stateless: the request carries everything needed and the same request
always gives the same response, so computed responses are reused (the web repeats many).

- ``POST /api/model/albuminuria``: the Bayesian filter over a patient's urine samples.
- ``POST /api/model/egfr-trend``: eGFR level and slope from the patient's lab tests.
- ``POST /api/model/assess``: full cardio-renal-metabolic assessment.
- ``GET /api/model/examples``: example bodies ready for the three routes above.

Errors: ``422`` if the body does not have the declared shape or limits (with a readable
message) and ``400`` if the shape is right but the data are inconsistent (dates, etc.).
"""

from __future__ import annotations

import calendar
import datetime as dt
import importlib.util
import math
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from scipy.optimize import brentq
from scipy.special import ndtr, ndtri
from threadpoolctl import threadpool_limits  # ships with scikit-learn

from latenthealth import assessment as panel
from latenthealth import cvrisk, kidney_trend
from latenthealth.albuminuria import (
    EYE_STRIP,
    PHONE_STRIP,
    AlbuminuriaAssessment,
    AlbuminuriaFilter,
    Patient,
    StripSample,
    UrineSample,
    load_default_filter,
)
from latenthealth.albuminuria.filter import SAMPLE_LABELS, STATUS_LABELS
from latenthealth.i18n import Labels, fmt_short_date, is_es, lang, t, use_lang

from ..serialize import clean

REPO_DIR = Path(__file__).resolve().parents[3]
DEMO_SCRIPT = REPO_DIR / "scripts" / "demo.py"
DEMO_TODAY = dt.date(2026, 11, 14)  # "today" in the examples

PROJECTION_MONTHS = (0, 3, 6, 12)  # albuminuria: uncertainty if not measured again
PROJECTION_YEARS = (1, 2, 3, 5)  # eGFR
BELIEF_POINTS = 200  # belief points sent (the filter's grid has 400)
STRIPS = {"movil": PHONE_STRIP, "ojo": EYE_STRIP}

# The filter keeps strip tables and the panel predicts with hundreds of trees: evaluate one at a
# time (in parallel it is slower and the model caches are not designed for it).
_FILTER_LOCK = threading.Lock()
_PANEL_LOCK = threading.Lock()


# --------------------------------------------------------------------------------------
# Shape errors (422) with a readable message
# --------------------------------------------------------------------------------------

_MESSAGES = Labels(
    {
        "missing": ("Falta este campo.", "This field is required."),
        "extra_forbidden": ("Campo desconocido.", "Unknown field."),
        "greater_than": ("Debe ser mayor que {gt}.", "Must be greater than {gt}."),
        "greater_than_equal": ("Debe ser como mínimo {ge}.", "Must be at least {ge}."),
        "less_than": ("Debe ser menor que {lt}.", "Must be less than {lt}."),
        "less_than_equal": ("Debe ser como máximo {le}.", "Must be at most {le}."),
        "too_long": (
            "Admite como mucho {max_length} elementos (hay {actual_length}).",
            "Allows at most {max_length} items (got {actual_length}).",
        ),
        "too_short": (
            "Necesita al menos {min_length} elementos (hay {actual_length}).",
            "Needs at least {min_length} items (got {actual_length}).",
        ),
        "literal_error": ("Valor no admitido. Debe ser {expected}.", "Value not allowed. Must be {expected}."),
        "union_tag_invalid": (
            "Tipo de muestra desconocido ({tag}). El campo «kind» debe ser {expected_tags}.",
            'Unknown sample type ({tag}). The "kind" field must be {expected_tags}.',
        ),
        "union_tag_not_found": (
            "Falta el campo «kind», que dice qué tipo de muestra es.",
            'The "kind" field is missing; it says what type of sample this is.',
        ),
        "finite_number": ("Debe ser un número finito.", "Must be a finite number."),
        "float_parsing": ("Debe ser un número.", "Must be a number."),
        "float_type": ("Debe ser un número.", "Must be a number."),
        "bool_parsing": ("Debe ser verdadero o falso.", "Must be true or false."),
        "bool_type": ("Debe ser verdadero o falso.", "Must be true or false."),
        "string_type": ("Debe ser un texto.", "Must be a string."),
        "list_type": ("Debe ser una lista.", "Must be a list."),
        "model_attributes_type": ("Debe ser un objeto con sus campos.", "Must be an object with its fields."),
        "json_invalid": ("El cuerpo de la petición no es JSON válido.", "The request body is not valid JSON."),
    }
)


def _date_message() -> str:
    return t("Fecha no válida: se espera AAAA-MM-DD.", "Invalid date: expected YYYY-MM-DD.")


def _plain(value: Any) -> Any:
    """Error context value as it reads best: 18 rather than 18.0; in Spanish, "o" rather than "or"."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and is_es():
        return value.replace(" or ", " o ")
    return value


def _readable(error: dict[str, Any]) -> None:
    """Rewrites a Pydantic validation error message in plain words (in place)."""
    kind = str(error.get("type", ""))
    template = _date_message() if kind.startswith("date_") else _MESSAGES.get(kind)
    if template is not None:
        try:
            error["msg"] = template.format(**{k: _plain(v) for k, v in (error.get("ctx") or {}).items()})
        except (KeyError, IndexError):
            pass  # keep the original message rather than lose it
    try:  # a NaN in the received body cannot be returned as JSON
        error["input"] = clean(error.get("input"))
    except TypeError:
        error["input"] = str(error.get("input"))


class ReadableErrorsRoute(APIRoute):
    """Route whose body validation errors (422) come out with a readable message."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                for error in exc.errors():
                    _readable(error)
                raise

        return handler


router = APIRouter(prefix="/api/model", tags=["Live model"], route_class=ReadableErrorsRoute)


class DomainError(BaseModel):
    detail: str = Field(description="What is inconsistent in the data sent.")


_ERROR_400: dict[int | str, dict[str, Any]] = {
    400: {"model": DomainError, "description": "The data are well formed but inconsistent with each other."}
}


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


# --------------------------------------------------------------------------------------
# Common inputs
# --------------------------------------------------------------------------------------

Day = Annotated[dt.date, Field(ge=dt.date(1900, 1, 1), le=dt.date(2100, 12, 31))]
Age = Annotated[float, Field(ge=18, le=100, description="Age in years (18 to 100).")]
Population = Annotated[
    Literal["espana", "nhanes"],
    Field(
        description='Reference population: "espana" uses priors recalibrated to Spanish primary care; '
        '"nhanes" uses the models as they were fitted.'
    ),
]
SampleType = Literal["first_morning", "random"]

_ROUNDING = 1e-9  # rounding-error margin when summing floating-point masses


def _probability(value: float) -> float:
    """Removes rounding error from a probability: 1.0000000000000002 -> 1.0; -1e-17 and -0.0 -> 0.0.

    The model gets them by summing floating-point masses and sometimes overshoots 1 or dips below
    0 in the last digit (on screen, "-0%"). Nothing beyond that margin changes: a value clearly
    outside [0, 1] would be a model bug and is left as is so it shows.
    """
    if -_ROUNDING < value <= 0.0:
        return 0.0
    if 1.0 < value < 1.0 + _ROUNDING:
        return 1.0
    return value


# Output probability, as a fraction between 0 and 1.
Probability = Annotated[float, AfterValidator(_probability)]


class _Input(BaseModel):
    """Request body: no unknown fields and no non-finite numbers."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class UrineLabSampleIn(_Input):
    """Urine sample measured in the lab (quantitative)."""

    kind: Literal["laboratorio"] = Field(description="Sample type: measured in the lab.")
    date: Day = Field(description="Sample date (YYYY-MM-DD).")
    uacr: float = Field(
        gt=0,
        le=30000,
        description='Albumin/creatinine ratio in mg/g (greater than 0, up to 30000). If "censored" is true, '
        'it is the detection limit: the result was "less than" this value.',
    )
    sample_type: SampleType = Field(
        description='"first_morning": first morning urine; "random": random sample.'
    )
    creatinine_mg_dl: float | None = Field(
        None, gt=0, le=1000, description="Urine creatinine of that sample, in mg/dl: tells how diluted it was."
    )
    censored: bool = Field(False, description='The lab only reported "less than" the "uacr" value.')


class UrineStripSampleIn(_Input):
    """Dipstick done at home: color level of the albumin and creatinine pads."""

    kind: Literal["tira"] = Field(description="Sample type: dipstick done at home.")
    date: Day = Field(description="Strip date (YYYY-MM-DD).")
    albumin_mg_l: float = Field(
        gt=0,
        le=1000,
        description="Level read on the albumin pad, in mg/l (the strip has 10, 30, 80 and 150; "
        "any other value is taken as the nearest level).",
    )
    creatinine_mg_dl: float = Field(
        gt=0,
        le=1000,
        description="Level read on the creatinine pad, in mg/dl (the strip has 10, 50, 100, 200 and 300).",
    )
    reader: Literal["movil", "ojo"] = Field(
        "movil", description='Who reads the color: "movil" (photo with the app) or "ojo" (by eye, against the chart on the bottle).'
    )
    sample_type: SampleType = Field("first_morning", description="Type of urine the strip was done with.")


UrineSampleIn = Annotated[UrineLabSampleIn | UrineStripSampleIn, Field(discriminator="kind")]
ModelSample = UrineSample | StripSample


def _model_samples(samples: list[UrineLabSampleIn | UrineStripSampleIn]) -> list[ModelSample]:
    """Model samples, in the date order the filter walks through them."""
    out: list[ModelSample] = []
    for s in samples:
        if isinstance(s, UrineStripSampleIn):
            out.append(StripSample(s.date, STRIPS[s.reader], s.albumin_mg_l, s.creatinine_mg_dl, sample_type=s.sample_type))
        else:
            out.append(UrineSample(s.date, s.uacr, s.sample_type, s.censored, s.creatinine_mg_dl))
    return sorted(out, key=lambda s: s.date)


def _check_as_of(as_of: dt.date, dates: list[dt.date], what: tuple[str, str]) -> None:
    """The assessment date cannot be earlier than the last measurement (the model does not reject it)."""
    if dates and as_of < max(dates):
        raise _bad_request(
            t(
                f"La fecha de evaluación (as_of, {fmt_short_date(as_of)}) no puede ser anterior a la última "
                f"{what[0]} ({fmt_short_date(max(dates))}).",
                f"The assessment date (as_of, {fmt_short_date(as_of)}) cannot be earlier than the last "
                f"{what[1]} ({fmt_short_date(max(dates))}).",
            )
        )


def _add_months(day: dt.date, months: int) -> dt.date:
    """Same date ``months`` months later (the last day of the month if that day does not exist)."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


# --------------------------------------------------------------------------------------
# 1. Albuminuria filter
# --------------------------------------------------------------------------------------


class AlbuminuriaPatientIn(_Input):
    age: Age
    female: bool = Field(description="True if female.")
    diabetes: bool = Field(description="Diagnosed diabetes.")
    egfr: float | None = Field(
        None,
        ge=5,
        le=150,
        description="Measured eGFR, in ml/min/1.73 m² (5 to 150). If missing, the filter assumes 90.",
    )


class AlbuminuriaIn(_Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "patient": {"age": 62, "female": False, "diabetes": True, "egfr": 75},
                    "samples": [
                        {"kind": "tira", "date": "2026-10-28", "albumin_mg_l": 30, "creatinine_mg_dl": 100},
                        {
                            "kind": "laboratorio",
                            "date": "2026-11-02",
                            "uacr": 35,
                            "sample_type": "first_morning",
                            "creatinine_mg_dl": 120,
                        },
                    ],
                    "as_of": "2026-11-14",
                }
            ]
        }
    )

    patient: AlbuminuriaPatientIn = Field(description="What the filter knows about the patient before measuring.")
    samples: list[UrineSampleIn] = Field(
        default_factory=list, max_length=30, description="Urine samples, in any order (at most 30)."
    )
    as_of: Day = Field(description="Assessment date (YYYY-MM-DD). Cannot be earlier than the last sample.")
    population: Population = "espana"


class AlbuminuriaPointOut(BaseModel):
    date: dt.date = Field(description="Sample date.")
    median: float = Field(description="Median true UACR that day, in mg/g (using all samples).")
    low: float = Field(description="10th percentile, in mg/g.")
    high: float = Field(description="90th percentile, in mg/g.")
    p_a2_plus: Probability = Field(description="P(true UACR ≥ 30 mg/g) that day.")


class AlbuminuriaProjectionOut(BaseModel):
    months: int = Field(description="Months since the assessment date.")
    date: dt.date = Field(description="Date the point refers to.")
    median: float = Field(description="Median true UACR, in mg/g.")
    low: float = Field(description="10th percentile, in mg/g.")
    high: float = Field(description="90th percentile, in mg/g.")
    p_a2_plus: Probability = Field(description="P(true UACR ≥ 30 mg/g).")


class NextSampleResolvesOut(BaseModel):
    first_morning: Probability = Field(description="With one more first-morning urine sample.")
    random: Probability = Field(description="With one more random sample.")


class AlbuminuriaBeliefOut(BaseModel):
    uacr: list[float] = Field(description="Center of each grid cell, in mg/g (log scale).")
    mass: list[Probability] = Field(description="Probability that the true UACR is in that cell. Sums to 1.")


class UrineSampleOut(BaseModel):
    kind: Literal["laboratorio", "tira"] = Field(description="Sample type.")
    date: dt.date = Field(description="Sample date.")
    label: str = Field(description="Name the model gives that sample or strip type.")
    value_mg_g: float = Field(
        description='UACR in mg/g: the one measured in the lab (or its detection limit if "censored") or the '
        "approximate one suggested by the strip reading."
    )
    sample_type: SampleType = Field(description="First morning urine or random sample.")
    censored: bool = Field(
        description='The lab only reported "less than": "value_mg_g" is then the detection limit, '
        "not a measurement. Always false for strips."
    )


class AlbuminuriaSummaryOut(BaseModel):
    """Albuminuria status as returned by the filter."""

    as_of: dt.date = Field(description="Assessment date.")
    status: Literal["sin_medir", "descartada", "dudosa", "pendiente_cronicidad", "confirmada"] = Field(
        description="Albuminuria status."
    )
    status_label: str = Field(description="Display name of the status.")
    category: Literal["A1", "A2", "A3"] = Field(description="Most likely KDIGO category.")
    p_a1: Probability = Field(description="P(true UACR < 30 mg/g).")
    p_a2: Probability = Field(description="P(true UACR between 30 and 300 mg/g).")
    p_a3: Probability = Field(description="P(true UACR > 300 mg/g).")
    p_a2_plus: Probability = Field(description="P(true UACR ≥ 30 mg/g): the probability of albuminuria.")
    median: float = Field(description="Median true UACR, in mg/g.")
    low: float = Field(description="10th percentile, in mg/g.")
    high: float = Field(description="90th percentile, in mg/g.")
    action: str = Field(description="What to do, in the model's words.")
    chronicity_met: bool = Field(description="The chronicity criterion (more than three months) is met.")
    repeat_from: dt.date | None = Field(
        description="Date from which a high sample meets chronicity; null if no sample has come out high."
    )
    next_sample_resolves: NextSampleResolvesOut | None = Field(
        description="Probability that one more sample confirms or rules out albuminuria. Only if the status is "
        '"sin_medir" or "dudosa"; otherwise null.'
    )
    trajectory: list[AlbuminuriaPointOut] = Field(description="One point per sample, by date (smoothed).")
    samples: list[UrineSampleOut] = Field(
        description="The samples received, in the same order as the trajectory, with their value for plotting."
    )


class AlbuminuriaOut(AlbuminuriaSummaryOut):
    projection: list[AlbuminuriaProjectionOut] = Field(
        description="Uncertainty at 0, 3, 6 and 12 months if not measured again. Not a forecast: the band "
        "widens because the data get older."
    )
    belief: AlbuminuriaBeliefOut = Field(description="What the filter believes today about the true UACR.")
    prior: AlbuminuriaBeliefOut = Field(description="What it believed before seeing any sample.")


@lru_cache(maxsize=None)
def _filter(population: str) -> AlbuminuriaFilter:
    """Filter for each population, loaded only once."""
    return load_default_filter(population)


def _sample_echo(sample: ModelSample) -> UrineSampleOut:
    if isinstance(sample, StripSample):
        return UrineSampleOut(
            kind="tira",
            date=sample.date,
            label=sample.spec.name,
            value_mg_g=sample.nominal_uacr,
            sample_type=sample.sample_type,
            censored=False,
        )
    return UrineSampleOut(
        kind="laboratorio",
        date=sample.date,
        label=SAMPLE_LABELS[sample.sample_type],
        value_mg_g=sample.uacr,
        sample_type=sample.sample_type,
        censored=bool(sample.censored),
    )


def _albuminuria_fields(a: AlbuminuriaAssessment, samples: list[ModelSample]) -> dict[str, Any]:
    """Fields shared by ``/albuminuria`` and the albuminuria part of ``/assess``."""
    return {
        "as_of": a.as_of,
        "status": a.status,
        "status_label": STATUS_LABELS[a.status],
        "category": a.category,
        "p_a1": a.p_a1,
        "p_a2": a.p_a2,
        "p_a3": a.p_a3,
        "p_a2_plus": a.p_a2_plus,
        "median": float(a.median),
        "low": float(a.low),
        "high": float(a.high),
        "action": a.action,
        "chronicity_met": bool(a.chronicity_met),
        "repeat_from": a.repeat_from,
        "next_sample_resolves": a.next_sample_resolves or None,
        "trajectory": [clean(point) for point in a.trajectory],
        "samples": [_sample_echo(s) for s in samples],
    }


def _reduce_belief(filt: AlbuminuriaFilter, mass: np.ndarray, points: int = BELIEF_POINTS) -> AlbuminuriaBeliefOut:
    """Groups neighboring grid cells to send about ``points`` points without losing mass."""
    step = max(1, math.ceil(filt.x.size / points))
    starts = np.arange(0, filt.x.size, step)
    sizes = np.diff(np.r_[starts, filt.x.size])
    centers = np.add.reduceat(filt.x, starts) / sizes  # center of each group, in log
    grouped = np.add.reduceat(np.asarray(mass, dtype=float), starts)
    return AlbuminuriaBeliefOut(uacr=np.exp(centers).tolist(), mass=grouped.tolist())


def _compute_albuminuria(body: AlbuminuriaIn) -> AlbuminuriaOut:
    samples = _model_samples(body.samples)
    _check_as_of(body.as_of, [s.date for s in samples], ("muestra", "sample"))
    filt = _filter(body.population)
    patient = Patient(body.patient.age, body.patient.female, body.patient.diabetes, body.patient.egfr, samples)
    with _FILTER_LOCK:
        current = filt.assess(patient, as_of=body.as_of)
        projection = []
        for months in PROJECTION_MONTHS:
            day = _add_months(body.as_of, months)
            # Without samples nothing gets older: the point does not change. The projected action
            # and status are not exposed, so the slow computation (detail) is not needed.
            future = current if (months == 0 or not samples) else filt.assess(patient, as_of=day, detail=False)
            projection.append(
                AlbuminuriaProjectionOut(
                    months=months,
                    date=day,
                    median=float(future.median),
                    low=float(future.low),
                    high=float(future.high),
                    p_a2_plus=future.p_a2_plus,
                )
            )
        prior = filt.prior(patient)
    return AlbuminuriaOut(
        **_albuminuria_fields(current, samples),
        projection=projection,
        belief=_reduce_belief(filt, current.belief),
        prior=_reduce_belief(filt, prior),
    )


@lru_cache(maxsize=256)
def _albuminuria_cached(key: str, lang_code: str = "en") -> AlbuminuriaOut:
    with use_lang(lang_code):
        return _compute_albuminuria(AlbuminuriaIn.model_validate_json(key))


@router.post(
    "/albuminuria",
    response_model=AlbuminuriaOut,
    responses=_ERROR_400,
    summary="Bayesian albuminuria filter",
)
def albuminuria(body: AlbuminuriaIn) -> AlbuminuriaOut:
    """Combines a patient's urine samples (lab and home strips) and returns what is known about
    their true albuminuria: probabilities, status, what to do, the full belief over the grid and
    how that belief ages if not measured again."""
    return _albuminuria_cached(body.model_dump_json(), lang())


# --------------------------------------------------------------------------------------
# 2. eGFR trend
# --------------------------------------------------------------------------------------


class EgfrMeasurementIn(_Input):
    date: Day = Field(description="Blood test date (YYYY-MM-DD).")
    egfr: float = Field(ge=5, le=150, description="Estimated GFR, in ml/min/1.73 m² (5 to 150).")
    source: Literal["laboratorio", "capilar"] = Field(
        "laboratorio", description='"laboratorio" (lab) or "capilar" (finger prick, noisier).'
    )
    above: bool = Field(
        False, description='The report only says "greater than" that value (many labs cap at 90).'
    )


class TreatmentStartIn(_Input):
    date: Day = Field(description="Date the treatment started (YYYY-MM-DD).")
    kind: Literal["isglt2", "ieca_ara2"] = Field(description='"isglt2" (SGLT2 inhibitor) or "ieca_ara2" (ACE inhibitor or ARB).')


class EgfrTrendIn(_Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "age": 68,
                    "female": True,
                    "diabetes": True,
                    "measurements": [
                        {"date": "2022-10-28", "egfr": 88},
                        {"date": "2023-10-28", "egfr": 79},
                        {"date": "2024-10-27", "egfr": 68},
                        {"date": "2025-10-27", "egfr": 60},
                        {"date": "2026-10-27", "egfr": 49},
                    ],
                    "as_of": "2026-11-14",
                }
            ]
        }
    )

    age: Age
    female: bool = Field(description="True if female.")
    diabetes: bool = Field(False, description="Diagnosed diabetes: makes a rapid decline more likely.")
    p_a2: float = Field(0.0, ge=0, le=1, description="Probability of albuminuria of 30 to 300 mg/g (from the filter).")
    p_a3: float = Field(0.0, ge=0, le=1, description="Probability of albuminuria above 300 mg/g.")
    measurements: list[EgfrMeasurementIn] = Field(
        default_factory=list, max_length=40, description="eGFR lab tests, in any order (at most 40)."
    )
    treatments: list[TreatmentStartIn] = Field(
        default_factory=list,
        max_length=10,
        description="Treatment starts: they explain an initial eGFR dip that is not a decline.",
    )
    as_of: Day | None = Field(
        None,
        description="Assessment date (YYYY-MM-DD). If missing, that of the last lab test. "
        "Cannot be earlier than it.",
    )


class EgfrTrendPointOut(BaseModel):
    date: dt.date = Field(description="Blood test date.")
    level: float = Field(description="Estimated eGFR that day (smoothed), in ml/min/1.73 m².")
    low: float = Field(description="Lower bound of the 80% interval.")
    high: float = Field(description="Upper bound of the 80% interval.")


class EgfrProjectionOut(BaseModel):
    years: int = Field(description="Years since the assessment date.")
    date: dt.date = Field(description="Date the point refers to.")
    level: float = Field(description="Expected eGFR if the trend continues, in ml/min/1.73 m² (never below 0).")
    low: float = Field(description="10th percentile (never below 0).")
    high: float = Field(description="90th percentile (never below 0).")


class EgfrMeasurementOut(BaseModel):
    date: dt.date = Field(description="Blood test date.")
    egfr: float = Field(description="Reported value, in ml/min/1.73 m².")
    source: Literal["laboratorio", "capilar"] = Field(description="Lab or finger prick.")
    above: bool = Field(description='The report only said "greater than" that value.')


class EgfrTrendOut(BaseModel):
    as_of: dt.date = Field(description="Assessment date.")
    n: int = Field(description="Blood tests used.")
    span_years: float = Field(description="Years between the first and the last lab test.")
    level: float = Field(description="Estimated current eGFR, in ml/min/1.73 m².")
    level_low: float = Field(description="Lower bound of the 80% interval of the level.")
    level_high: float = Field(description="Upper bound of the 80% interval of the level.")
    slope: float = Field(description="Slope, in ml/min/1.73 m² per year (negative if falling).")
    slope_low: float = Field(description="Lower bound of the 80% interval of the slope.")
    slope_high: float = Field(description="Upper bound of the 80% interval of the slope.")
    p_decline: Probability = Field(description="P(loses more than 3 ml/min/1.73 m² per year).")
    p_rapid: Probability = Field(description="P(loses more than 5 per year): rapid decline per KDIGO.")
    p_below_60: Probability = Field(description="P(current eGFR < 60).")
    p_below_30_in_5y: Probability = Field(description="P(eGFR < 30 within five years).")
    status: Literal["sin_datos", "insuficiente", "estable", "descenso", "descenso_rapido", "incierto"] = Field(
        description="Reading of the trend."
    )
    status_label: str = Field(description="Display name of the status.")
    chronic_below_60: bool = Field(
        description="Two lab tests more than three months apart with eGFR below 60 very likely."
    )
    measured_drop_explained: float = Field(
        description="Expected dip from the treatments started, in ml/min/1.73 m² (0 if none)."
    )
    trajectory: list[EgfrTrendPointOut] = Field(description="One point per lab test, by date (smoothed).")
    projection: list[EgfrProjectionOut] = Field(
        description="At 1, 2, 3 and 5 years with the model's own formula. Empty if there are no lab tests."
    )
    measurements: list[EgfrMeasurementOut] = Field(description="The lab tests received, by date.")


Mixture = list[tuple[float, float, float]]


def _level_ahead(trend: kidney_trend.EgfrTrend, years: float, params: kidney_trend.TrendParams | None = None) -> Mixture:
    """eGFR level in ``years`` years: (weight, mean, sd) of each mixture component.

    It is the formula ``fit_trend`` uses for ``p_below_30_in_5y``: mean ``m0 + m1·t`` and
    variance ``[1, t]·P·[1, t]ᵀ`` plus the process noise accumulated over ``t`` years.
    """
    params = params or kidney_trend.TrendParams()
    ahead = np.array([1.0, float(years)])
    noise = params.level_noise**2 * years + params.slope_noise**2 * years**3 / 3.0
    return [(float(w), float(ahead @ m), float(np.sqrt(ahead @ P @ ahead + noise))) for w, m, P in trend.components]


def _mixture_cdf(mixture: Mixture, value: float) -> float:
    return float(sum(w * ndtr((value - mean) / sd) for w, mean, sd in mixture))


def _mixture_quantile(mixture: Mixture, q: float) -> float:
    """Quantile of a normal mixture: it lies between the quantiles of its components."""
    candidates = [mean + float(ndtri(q)) * sd for _, mean, sd in mixture]
    lo, hi = min(candidates), max(candidates)
    if _mixture_cdf(mixture, lo) >= q:  # a single weighted component: the quantile is its own
        return lo
    if _mixture_cdf(mixture, hi) <= q:
        return hi
    return float(brentq(lambda v: _mixture_cdf(mixture, v) - q, lo, hi, xtol=1e-10))


def _trend_projection(trend: kidney_trend.EgfrTrend, years: int) -> EgfrProjectionOut:
    mixture = _level_ahead(trend, years)
    mean = sum(w * m for w, m, _ in mixture)
    return EgfrProjectionOut(
        years=years,
        date=_add_months(trend.as_of, 12 * years),
        level=max(mean, 0.0),  # a negative eGFR does not exist
        low=max(_mixture_quantile(mixture, 0.1), 0.0),
        high=max(_mixture_quantile(mixture, 0.9), 0.0),
    )


def _compute_egfr_trend(body: EgfrTrendIn) -> EgfrTrendOut:
    measurements = sorted(
        (kidney_trend.EgfrMeasurement(m.date, m.egfr, m.source, m.above) for m in body.measurements),
        key=lambda m: m.date,
    )
    if body.as_of is None and not measurements:
        raise _bad_request(
            t(
                "Sin analíticas hay que indicar la fecha de evaluación (as_of).",
                "Without lab tests the assessment date (as_of) must be given.",
            )
        )
    as_of = body.as_of or measurements[-1].date
    _check_as_of(as_of, [m.date for m in measurements], ("analítica", "lab test"))
    if body.p_a2 + body.p_a3 > 1.0 + 1e-9:
        raise _bad_request(
            t(
                "Las probabilidades de albuminuria p_a2 y p_a3 no pueden sumar más de 1.",
                "The albuminuria probabilities p_a2 and p_a3 cannot add up to more than 1.",
            )
        )
    treatments = [kidney_trend.TreatmentStart(t.date, t.kind) for t in body.treatments]
    trend = kidney_trend.fit_trend(
        measurements, body.age, body.female, body.diabetes, body.p_a2, body.p_a3, treatments, as_of
    )
    level_low, level_high = trend.interval("level")
    slope_low, slope_high = trend.interval("slope")
    return EgfrTrendOut(
        as_of=trend.as_of,
        n=trend.n,
        span_years=trend.span_years,
        level=trend.level,
        level_low=level_low,
        level_high=level_high,
        slope=trend.slope,
        slope_low=slope_low,
        slope_high=slope_high,
        p_decline=trend.p_decline,
        p_rapid=trend.p_rapid,
        p_below_60=trend.p_below_60,
        p_below_30_in_5y=trend.p_below_30_in_5y,
        status=trend.status,
        status_label=kidney_trend.STATUS_TEXT[trend.status],
        chronic_below_60=bool(trend.chronic_below_60),
        measured_drop_explained=trend.measured_drop_explained,
        trajectory=[clean(point) for point in trend.trajectory],
        # With no lab tests there is only the prior: nothing to project.
        projection=[_trend_projection(trend, years) for years in PROJECTION_YEARS] if measurements else [],
        measurements=[clean(m) for m in measurements],
    )


@lru_cache(maxsize=256)
def _egfr_trend_cached(key: str, lang_code: str = "en") -> EgfrTrendOut:
    with use_lang(lang_code):
        return _compute_egfr_trend(EgfrTrendIn.model_validate_json(key))


@router.post(
    "/egfr-trend",
    response_model=EgfrTrendOut,
    responses=_ERROR_400,
    summary="eGFR trend",
)
def egfr_trend(body: EgfrTrendIn) -> EgfrTrendOut:
    """eGFR level and slope from previous lab tests, separating real decline from creatinine
    noise and discounting the expected dip when a treatment starts. With fewer than two blood
    tests it returns the status "sin_datos" or "insuficiente". The model parameters are
    assumptions from the literature: it has only been checked in simulation."""
    return _egfr_trend_cached(body.model_dump_json(), lang())


# --------------------------------------------------------------------------------------
# 3. Full patient assessment
# --------------------------------------------------------------------------------------


class MeasuredLabsIn(_Input):
    """Recent lab test. What is measured always replaces the model's estimate."""

    egfr: float | None = Field(None, ge=5, le=150, description="eGFR, in ml/min/1.73 m² (5 to 150).")
    hba1c: float | None = Field(None, ge=3, le=20, description="HbA1c, in % (3 to 20).")
    glucose: float | None = Field(None, ge=20, le=1000, description="Non-fasting glucose, in mg/dl.")
    potassium: float | None = Field(None, ge=1.5, le=9, description="Potassium, in mmol/l.")
    non_hdl: float | None = Field(None, ge=20, le=600, description="Non-HDL cholesterol, in mg/dl.")
    hemoglobin: float | None = Field(None, ge=3, le=25, description="Hemoglobin, in g/dl.")
    nt_probnp: float | None = Field(None, gt=0, le=100000, description="NT-proBNP, in pg/ml.")
    total_cholesterol: float | None = Field(None, ge=50, le=700, description="Total cholesterol, in mg/dl.")
    hdl: float | None = Field(None, ge=5, le=200, description="HDL cholesterol, in mg/dl.")


class AssessIn(_Input):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "age": 58,
                    "female": True,
                    "bmi": 31.0,
                    "waist": 99,
                    "sbp": 132,
                    "dbp": 80,
                    "diabetes": True,
                    "diabetes_pills": True,
                    "hypertension": True,
                    "bp_meds": True,
                    "measured": {"hba1c": 7.4},
                    "urine_samples": [
                        {
                            "kind": "laboratorio",
                            "date": "2026-10-02",
                            "uacr": 38.0,
                            "sample_type": "random",
                            "creatinine_mg_dl": 85,
                        }
                    ],
                    "as_of": "2026-11-14",
                }
            ]
        }
    )

    age: Age
    female: bool = Field(description="True if female.")
    bmi: float | None = Field(None, ge=10, le=80, description="Body mass index, in kg/m².")
    waist: float | None = Field(None, ge=40, le=200, description="Waist circumference, in cm.")
    sbp: float | None = Field(None, ge=60, le=260, description="Mean office systolic blood pressure, in mmHg.")
    dbp: float | None = Field(None, ge=30, le=160, description="Mean office diastolic blood pressure, in mmHg.")
    diabetes: bool = Field(False, description="Diagnosed diabetes.")
    prediabetes: bool = Field(False, description="Diagnosed prediabetes.")
    insulin: bool = Field(False, description="On insulin.")
    diabetes_pills: bool = Field(False, description="Takes oral diabetes medication.")
    hypertension: bool = Field(False, description="Diagnosed hypertension.")
    bp_meds: bool = Field(False, description="Takes blood pressure medication.")
    high_cholesterol: bool = Field(False, description="Diagnosed high cholesterol.")
    cholesterol_meds: bool = Field(False, description="Takes cholesterol medication.")
    heart_failure: bool = Field(False, description="Diagnosed heart failure.")
    coronary: bool = Field(False, description="Ischemic heart disease.")
    stroke: bool = Field(False, description="Previous stroke.")
    kidney_disease: bool = Field(False, description="Chronic kidney disease already on record.")
    smoker_now: bool = Field(False, description="Currently smokes.")
    smoker_ever: bool = Field(False, description="Has ever smoked.")
    measured: MeasuredLabsIn = Field(default_factory=MeasuredLabsIn, description="Recent lab test (only what is available).")
    urine_samples: list[UrineSampleIn] = Field(
        default_factory=list, max_length=30, description="Urine samples, in any order (at most 30)."
    )
    as_of: Day = Field(description="Assessment date (YYYY-MM-DD). Cannot be earlier than the last urine sample.")
    population: Population = "espana"


_RECORD_FIELDS = tuple(
    name for name in AssessIn.model_fields if name not in ("measured", "urine_samples", "as_of", "population")
)


class BloodEstimateOut(BaseModel):
    key: str = Field(description="Variable key (egfr, hba1c, glucose, potassium, non_hdl, hemoglobin, nt_probnp).")
    name: str = Field(description="Display name.")
    unit: str = Field(description="Unit.")
    median: float = Field(description="Measured value or median of the estimate.")
    low: float = Field(description="10th percentile (equal to the value if measured).")
    high: float = Field(description="90th percentile (equal to the value if measured).")
    measured: bool = Field(description="True if it comes from the lab test; false if the model estimates it.")
    decimals: int = Field(description="Decimals to display it with.")
    source: str = Field(description="Where the value comes from (measured, estimated...), in the model's words.")


class KdigoCellOut(BaseModel):
    a: Literal["A1", "A2", "A3"] = Field(description="Albuminuria category.")
    p: Probability = Field(description="Probability that the patient is in that cell.")
    risk: Literal["bajo", "moderado", "alto", "muy alto"] = Field(description="KDIGO risk level of the cell, as a machine value: bajo (low), moderado (moderate), alto (high), muy alto (very high).")


class KdigoRowOut(BaseModel):
    g: Literal["G1", "G2", "G3a", "G3b", "G4", "G5"] = Field(description="eGFR category.")
    cells: list[KdigoCellOut] = Field(description="The three cells of the row: A1, A2 and A3.")


class CvRiskOut(BaseModel):
    score: Probability = Field(description="10-year SCORE2 or SCORE2-OP (median if data are missing), as a fraction.")
    score_low: Probability = Field(description="10th percentile of SCORE2 given what is still unmeasured.")
    score_high: Probability = Field(description="90th percentile.")
    probs: list[Probability] = Field(description="Probability of each true category: low or moderate, high, very high.")
    recorded: int = Field(description="Category from what is already on record: 0, 1 or 2 (same order).")
    recorded_label: str = Field(description="Name of that category.")
    category: int = Field(description="Most likely true category: 0, 1 or 2.")
    category_label: str = Field(description="Name of that category.")
    approximate: bool = Field(description="Missing data were assumed (blood pressure or HDL).")


class RecommendationOut(BaseModel):
    test: str = Field(description="Test worth ordering.")
    reason: str = Field(description="Why, in the model's words.")


class AssessOut(BaseModel):
    albuminuria: AlbuminuriaSummaryOut = Field(description="Albuminuria status (the filter, inside the assessment).")
    blood: list[BloodEstimateOut] = Field(description="Blood panel: what is measured and what is estimated from the record and the urine.")
    p_egfr_below_60: Probability = Field(description="P(eGFR < 60).")
    kdigo_g: dict[str, Probability] = Field(description="Probability of each eGFR category: G1, G2, G3a, G3b, G4 and G5.")
    kdigo_risk: dict[str, Probability] = Field(
        description='Probability of each KDIGO risk level, keyed "bajo" (low), "moderado" (moderate), "alto" (high) and "muy alto" (very high).'
    )
    kdigo_joint: list[KdigoRowOut] = Field(
        description="KDIGO map: joint probability of eGFR (6 rows) and albuminuria (3 columns). Sums to 1."
    )
    p_ckd: Probability = Field(description="P(eGFR < 60 or albuminuria ≥ 30 mg/g), without requiring chronicity yet.")
    diabetes: str = Field(description="Diabetes reading, in the model's words (diagnosed, likely, possible or unlikely).")
    p_diabetes: Probability | None = Field(description="P(undiagnosed diabetes); null if already diagnosed.")
    heart_failure: str = Field(description="Heart failure reading, in the model's words (diagnosed, to rule out or unlikely).")
    p_nt_probnp_high: Probability | None = Field(description="P(NT-proBNP ≥ 125 pg/ml); null if already diagnosed.")
    cv: CvRiskOut | None = Field(description="Cardiovascular risk with the uncertainty of what is still unmeasured.")
    p_new_finding: Probability = Field(description="Probability of a new finding if the pending tests are completed.")
    finding_by_test: dict[str, Probability] = Field(description="That probability if only each test were done.")
    recommendations: list[RecommendationOut] = Field(description="Tests worth ordering, in order.")
    alerts: list[str] = Field(description="Findings that already call for action, in the model's words.")


def _compute_assess(body: AssessIn) -> AssessOut:
    samples = _model_samples(body.urine_samples)
    _check_as_of(body.as_of, [s.date for s in samples], ("muestra de orina", "urine sample"))
    record = panel.ClinicalRecord(
        **{name: getattr(body, name) for name in _RECORD_FIELDS},
        urine_samples=samples,
        measured=body.measured.model_dump(exclude_none=True),
    )
    # With a single patient, spreading the panel's trees across threads costs more than it
    # saves (measured: from 500-800 ms to about 420). The result is the same.
    with _PANEL_LOCK, threadpool_limits(limits=1, user_api="openmp"):
        a = panel.assess(record, as_of=body.as_of, population=body.population, detail=True)

    joint = np.asarray(a.kdigo_joint, dtype=float)
    kdigo_joint = [
        KdigoRowOut(
            g=g,
            cells=[
                # With a measured eGFR the model leaves negative zeros: the ``Probability`` type cleans them.
                KdigoCellOut(a=label, p=float(joint[i, j]), risk=panel.KDIGO_RISK[g][j])
                for j, label in enumerate(cvrisk.A_LABELS)
            ],
        )
        for i, g in enumerate(panel.G_LABELS)
    ]
    cv = None
    if a.cv is not None:
        cv = CvRiskOut(
            score=a.cv.score,
            score_low=a.cv.score_low,
            score_high=a.cv.score_high,
            probs=[float(p) for p in a.cv.probs],
            recorded=int(a.cv.recorded),
            recorded_label=cvrisk.CATEGORY_LABELS[int(a.cv.recorded)],
            category=a.cv.category,
            category_label=cvrisk.CATEGORY_LABELS[a.cv.category],
            approximate=bool(a.cv.approximate),
        )
    return AssessOut(
        albuminuria=AlbuminuriaSummaryOut(**_albuminuria_fields(a.albuminuria, samples)),
        blood=[BloodEstimateOut(key=key, **clean(estimate)) for key, estimate in a.blood.items()],
        p_egfr_below_60=a.p_egfr_below_60,
        kdigo_g={g: float(p) for g, p in a.kdigo_g.items()},
        kdigo_risk={level: float(p) for level, p in a.kdigo_risk.items()},
        kdigo_joint=kdigo_joint,
        p_ckd=a.p_ckd,
        diabetes=a.diabetes,
        p_diabetes=a.p_diabetes,
        heart_failure=a.heart_failure,
        p_nt_probnp_high=a.p_nt_probnp_high,
        cv=cv,
        p_new_finding=a.p_new_finding,
        finding_by_test={test: float(p) for test, p in a.finding_by_test.items()},
        recommendations=[clean(r) for r in a.recommendations],
        alerts=list(a.alerts),
    )


@lru_cache(maxsize=256)
def _assess_cached(key: str, lang_code: str = "en") -> AssessOut:
    with use_lang(lang_code):
        return _compute_assess(AssessIn.model_validate_json(key))


@router.post(
    "/assess",
    response_model=AssessOut,
    responses=_ERROR_400,
    summary="Full patient assessment",
)
def assess(body: AssessIn) -> AssessOut:
    """Combines the albuminuria filter, the virtual blood panel and cardiovascular risk: probability
    of each KDIGO category, of diabetes and of heart failure, findings that already call for action
    and which tests are worth ordering. Decision support on synthetic data: it does not diagnose."""
    return _assess_cached(body.model_dump_json(), lang())


# --------------------------------------------------------------------------------------
# 4. Examples
# --------------------------------------------------------------------------------------


class PatientExampleOut(BaseModel):
    id: str = Field(description="Stable example identifier: p1 to p5.")
    title: str = Field(description="Description of the made-up patient.")
    assess: AssessIn = Field(description="Body ready for POST /api/model/assess.")
    albuminuria: AlbuminuriaIn = Field(description="Body ready for POST /api/model/albuminuria.")


class TrendExampleOut(BaseModel):
    id: str = Field(description="Stable example identifier.")
    title: str = Field(description="Description of the series.")
    egfr_trend: EgfrTrendIn = Field(description="Body ready for POST /api/model/egfr-trend.")


class ExamplesOut(BaseModel):
    as_of: dt.date = Field(description="Assessment date of all the examples.")
    patients: list[PatientExampleOut] = Field(description="The five made-up patients from scripts/demo.py.")
    egfr_trends: list[TrendExampleOut] = Field(description="Two eGFR series: one falling fast and one stable.")


def _demo_patients() -> dict[str, panel.ClinicalRecord]:
    """Patients from ``scripts/demo.py``. Importing it runs nothing: it only defines the dict."""
    spec = importlib.util.spec_from_file_location("latenthealth_web_demo_patients", DEMO_SCRIPT)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.PATIENTS)


def _sample_in(sample: ModelSample) -> UrineLabSampleIn | UrineStripSampleIn:
    """Model sample -> API sample (the reverse of ``_model_samples``)."""
    if isinstance(sample, StripSample):
        reader = next((name for name, spec in STRIPS.items() if spec == sample.spec), None)
        if reader is None:
            raise ValueError(
                t(f"La API no admite la tira «{sample.spec.name}».", f'The API does not support the strip "{sample.spec.name}".')
            )
        return UrineStripSampleIn(
            kind="tira",
            date=sample.date,
            albumin_mg_l=sample.albumin_mg_l,
            creatinine_mg_dl=sample.creatinine_mg_dl,
            reader=reader,
            sample_type=sample.sample_type,
        )
    return UrineLabSampleIn(
        kind="laboratorio",
        date=sample.date,
        uacr=sample.uacr,
        sample_type=sample.sample_type,
        creatinine_mg_dl=sample.creatinine_mg_dl,
        censored=sample.censored,
    )


def _yearly(values: list[float], last: dt.date) -> list[EgfrMeasurementIn]:
    """One lab test a year (every 365 days) ending on ``last``."""
    n = len(values)
    return [EgfrMeasurementIn(date=last - dt.timedelta(days=365 * (n - 1 - i)), egfr=v) for i, v in enumerate(values)]


@lru_cache(maxsize=2)
def _examples(lang_code: str = "en") -> ExamplesOut:
    with use_lang(lang_code):
        return _build_examples()


# Titles of the demo patients in Spanish (scripts/demo.py keeps the English ones), in the same order.
_TITLES_ES = (
    "Hipertenso de 62 años, nunca se le ha pedido UACR",
    "Diabética de 58 años con una muestra aleatoria de 38 mg/g",
    "Diabético de 70 años, FG 52, tres muestras en cuatro meses",
    "Mujer de 45 años, una muestra aleatoria de 260 mg/g en orina muy diluida",
    "Hombre de 78 años, obeso, hipertenso y con cardiopatía isquémica, sin analítica reciente",
)


def _build_examples() -> ExamplesOut:
    patients = []
    for number, (title, record) in enumerate(_demo_patients().items(), start=1):
        samples = [_sample_in(s) for s in record.urine_samples]
        patients.append(
            PatientExampleOut(
                id=f"p{number}",
                title=_TITLES_ES[number - 1] if is_es() and number <= len(_TITLES_ES) else re.sub(r"^\d+\.\s*", "", title),
                assess=AssessIn(
                    **{name: getattr(record, name) for name in _RECORD_FIELDS},
                    measured=MeasuredLabsIn(**record.measured),
                    urine_samples=samples,
                    as_of=DEMO_TODAY,
                ),
                albuminuria=AlbuminuriaIn(
                    patient=AlbuminuriaPatientIn(
                        age=record.age,
                        female=record.female,
                        diabetes=record.diabetes,
                        egfr=record.measured.get("egfr"),
                    ),
                    samples=samples,
                    as_of=DEMO_TODAY,
                ),
            )
        )
    last = dt.date(2026, 10, 27)
    series = [
        (
            "descenso_rapido",
            t("Mujer de 68 años, diabética: el filtrado baja año tras año", "Woman aged 68 with diabetes: eGFR falls year after year"),
            [88, 79, 68, 60, 49],
        ),
        (
            "estable",
            t("Mujer de 68 años, diabética: el filtrado se mantiene", "Woman aged 68 with diabetes: eGFR holds steady"),
            [75, 77, 74, 76, 75],
        ),
    ]
    trends = [
        TrendExampleOut(
            id=trend_id,
            title=title,
            egfr_trend=EgfrTrendIn(age=68, female=True, diabetes=True, measurements=_yearly(values, last), as_of=DEMO_TODAY),
        )
        for trend_id, title, values in series
    ]
    return ExamplesOut(as_of=DEMO_TODAY, patients=patients, egfr_trends=trends)


@router.get(
    "/examples",
    response_model=ExamplesOut,
    response_model_exclude_none=True,
    summary="Example inputs for the model routes",
)
def examples() -> ExamplesOut:
    """Five made-up patients (not real patients) with their body for ``/assess`` and for
    ``/albuminuria``, and two eGFR series for ``/egfr-trend``. All dated November 14, 2026."""
    try:
        return _examples(lang())
    except (OSError, ImportError, AttributeError, ValueError) as exc:
        detail = t(
            "No se han podido cargar los ejemplos de scripts/demo.py.",
            "The examples from scripts/demo.py could not be loaded.",
        )
        raise HTTPException(status_code=503, detail=detail) from exc


# --------------------------------------------------------------------------------------
# Warm-up
# --------------------------------------------------------------------------------------


def warm_up() -> None:
    """Loads the filter and the panel models by evaluating the examples.

    That way the demo's first request takes the usual time and the examples, the first thing
    people click, are already computed. Goes from fast to slow so the filter is available while
    the panel models load.
    """
    loaded = _examples("en")
    for patient in loaded.patients:
        _albuminuria_cached(patient.albuminuria.model_dump_json(), "en")
    for trend in loaded.egfr_trends:
        _egfr_trend_cached(trend.egfr_trend.model_dump_json(), "en")
    for patient in loaded.patients:
        _assess_cached(patient.assess.model_dump_json(), "en")
