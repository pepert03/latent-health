"""Rutas de la app del paciente: protocolo de orina en casa y otras medidas (tensión, pulso, glucosa).

Las rutas no guardan estado: cada petición lleva al paciente, sus muestras y la fecha de hoy, y
la respuesta sale entera de los modelos de ``src/latenthealth``. Los mensajes al paciente, las
notas para la historia y las alertas son los literales del modelo. Aquí solo se escriben las
etiquetas de la interfaz, los guiones de la demo y los errores de validación.

Todo son datos sintéticos.
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
    """Copia de ``value`` con NaN e infinitos escritos como texto, que es lo que JSON admite."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class _SafeErrorsRoute(APIRoute):
    """Ruta cuyo 422 se puede escribir siempre como JSON.

    Python acepta ``NaN`` e ``Infinity`` al leer el cuerpo de la petición. El 422 de FastAPI
    repite en ``input`` lo que no valía, y al escribir ese NaN como JSON la respuesta se rompía
    en un 500. Aquí se pasan a texto antes de responder.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise RequestValidationError(_json_safe(error.errors()), body=_json_safe(error.body)) from None

        return safe_handler


router = APIRouter(prefix="/api/home", tags=["En casa (app del paciente)"], route_class=_SafeErrorsRoute)

# --- Constantes de la demo y límites de la validación ---

DEMO_TODAY = dt.date(2026, 11, 16)  # lunes; la misma D0 de scripts/demo_casa.py
POPULATION = "espana"
DEFAULT_CHANNEL = Channel.APP
# Ventana por defecto con la que protocol.next_step cuenta las tiras y tubos gastados.
EPISODE_DAYS = 60
# Umbrales con los que assessment._alerts da por clara la alerta del pulso y la de la glucosa.
AF_ALERT_PROBABILITY = 0.5
GLUCOSE_ALERT_DAYS = 2

AGE_MIN, AGE_MAX = 18.0, 100.0
EGFR_MIN, EGFR_MAX = 5.0, 150.0  # ml/min/1,73 m²
UACR_MAX = 30_000.0  # mg/g; es el tope de la rejilla del filtro
URINE_CREATININE_MAX = 1_000.0  # mg/dl
MAX_SAMPLES = 30
MAX_READINGS = 200  # lecturas de tensión, pulso o glucosa por petición
SBP_MIN, SBP_MAX = 60.0, 300.0  # mmHg
DBP_MIN, DBP_MAX = 30.0, 200.0
GLUCOSE_MIN, GLUCOSE_MAX = 20.0, 600.0  # mg/dl; lo que llega a leer un glucómetro
DATE_MIN, DATE_MAX = dt.date(2000, 1, 1), dt.date(2100, 12, 31)

DIGITS = 6  # decimales de las respuestas: de sobra para pintar y estables entre ejecuciones

# Texto corto de cada acción del protocolo, para botones y cabeceras (el modelo no trae uno).
ACTION_LABELS = {
    "tira": "Tira en casa",
    "tubo": "Tubo al laboratorio",
    "esperar": "Esperar",
    "fin_normal": "Fin: prueba normal",
    "centro": "Fin: centro de salud",
    "repetir_cronicidad": "Repetir a los 3 meses",
}

Action = Literal["tira", "tubo", "esperar", "fin_normal", "centro", "repetir_cronicidad"]
Status = Literal["sin_medir", "descartada", "dudosa", "pendiente_cronicidad", "confirmada"]


# --- Entrada ---


class Answers(BaseModel):
    """Respuestas a las preguntas previas a la prueba. Ausente o ``null`` = sin contestar."""

    exercise_24h: bool | None = Field(None, description=urine_context.FACTORS["exercise_24h"].question)
    fever: bool | None = Field(None, description=urine_context.FACTORS["fever"].question)
    menstruation: bool | None = Field(
        None,
        description=(
            f"{urine_context.FACTORS['menstruation'].question} "
            f"Solo cuenta en mujeres menores de {urine_context.FACTORS['menstruation'].women_under:g} años."
        ),
    )
    uti_symptoms: bool | None = Field(None, description=urine_context.FACTORS["uti_symptoms"].question)


class PatientIn(BaseModel):
    """Lo que el filtro necesita saber del paciente."""

    age: float = Field(description=f"Edad en años (entre {AGE_MIN:g} y {AGE_MAX:g}).")
    female: bool = Field(description="Es mujer.")
    diabetes: bool = Field(description="Tiene diabetes diagnosticada.")
    egfr: float | None = Field(
        None,
        description=(
            f"Filtrado glomerular estimado (FG), en ml/min/1,73 m² (entre {EGFR_MIN:g} y {EGFR_MAX:g}). "
            "Si falta, el modelo supone un filtrado normal."
        ),
    )


class StripSampleIn(BaseModel):
    """Una tira hecha en casa: el nivel de color leído en cada almohadilla."""

    kind: Literal["tira"] = Field(description="Tipo de muestra.")
    date: dt.date = Field(description="Día en que se hizo (AAAA-MM-DD).")
    albumin_mg_l: float = Field(description="Nivel leído en la almohadilla de albúmina, en mg/l (uno de los de /config).")
    creatinine_mg_dl: float = Field(
        description="Nivel leído en la almohadilla de creatinina, en mg/dl (uno de los de /config)."
    )
    answers: Answers | None = Field(
        None, description="Respuestas del paciente sobre esta muestra. Se guardan con ella y cambian la probabilidad."
    )


class TubeSampleIn(BaseModel):
    """Un tubo enviado al laboratorio, que mide el cociente albúmina/creatinina."""

    kind: Literal["tubo"] = Field(description="Tipo de muestra.")
    date: dt.date = Field(description="Día en que se recogió (AAAA-MM-DD).")
    uacr: float = Field(description="Cociente albúmina/creatinina medido por el laboratorio, en mg/g (mayor que 0).")
    creatinine_mg_dl: float | None = Field(
        None, description="Creatinina en orina de la muestra, en mg/dl. Si falta, se supone una orina de dilución típica."
    )
    answers: Answers | None = Field(
        None, description="Respuestas del paciente sobre esta muestra. Se guardan con ella y cambian la probabilidad."
    )


SampleIn = Annotated[StripSampleIn | TubeSampleIn, Field(discriminator="kind")]


class StepIn(BaseModel):
    """Todo lo que hace falta para decidir el siguiente paso: el servidor no recuerda nada."""

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

    patient: PatientIn = Field(description="El paciente.")
    channel: Channel = Field(
        DEFAULT_CHANNEL,
        description="Canal por el que hace la prueba (el ``value`` de /config; también vale la ``key``). Por defecto, la aplicación.",
    )
    today: dt.date = Field(description="Fecha de hoy para el paciente (AAAA-MM-DD). La web la avanza; el servidor no usa el reloj.")
    samples: list[SampleIn] = Field(
        default_factory=list, description=f"Muestras hechas hasta hoy, tiras y tubos (como mucho {MAX_SAMPLES})."
    )
    answers: Answers | None = Field(
        None,
        description="Respuestas de HOY a las preguntas previas, si ya las ha contestado. Solo deciden si la prueba se aplaza.",
    )
    episode_start: dt.date | None = Field(
        None,
        description=(
            "Desde qué día cuentan las tiras y los tubos gastados del kit. "
            f"Por defecto, los últimos {EPISODE_DAYS} días."
        ),
    )

    @field_validator("channel", mode="before")
    @classmethod
    def _channel_by_key(cls, value: object) -> object:
        """Admite también la clave del canal ("APP"), además de su valor ("aplicación")."""
        if isinstance(value, str) and value in Channel.__members__:
            return Channel[value]
        return value


class BPReadingIn(BaseModel):
    """Una lectura del manguito en casa."""

    date: dt.date = Field(description="Día de la lectura (AAAA-MM-DD).")
    sbp: float = Field(description=f"Tensión sistólica, en mmHg (entre {SBP_MIN:g} y {SBP_MAX:g}).")
    dbp: float = Field(description=f"Tensión diastólica, en mmHg (entre {DBP_MIN:g} y {DBP_MAX:g}).")
    evening: bool = Field(False, description="Lectura de la noche (si no, de la mañana).")


class BPIn(BaseModel):
    """La automedida de la tensión de un paciente."""

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
        description=f"Lecturas de la automedida (entre 1 y {MAX_READINGS}). Lo ideal: 7 días, dos por la mañana y dos por la noche."
    )


class RhythmCheckIn(BaseModel):
    """Una comprobación del pulso con el móvil o el reloj."""

    date: dt.date = Field(description="Día de la comprobación (AAAA-MM-DD).")
    irregular: bool = Field(description="El pulso salió irregular.")


class RhythmIn(BaseModel):
    """Las comprobaciones del pulso de un paciente sin fibrilación auricular diagnosticada."""

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

    age: float = Field(description=f"Edad en años (entre {AGE_MIN:g} y {AGE_MAX:g}).")
    female: bool = Field(description="Es mujer.")
    checks: list[RhythmCheckIn] = Field(
        default_factory=list, description=f"Comprobaciones del pulso (como mucho {MAX_READINGS})."
    )


class GlucoseReadingIn(BaseModel):
    """Una glucosa capilar medida en casa con un glucómetro."""

    date: dt.date = Field(description="Día de la lectura (AAAA-MM-DD).")
    mg_dl: float = Field(description=f"Glucosa, en mg/dl (entre {GLUCOSE_MIN:g} y {GLUCOSE_MAX:g}).")
    fasting_hours: float = Field(
        FASTING_HOURS, description=f"Horas desde la última comida (entre 0 y 24). Con {FASTING_HOURS:g} o más cuenta como ayunas."
    )


class GlucoseIn(BaseModel):
    """Las glucosas capilares de un paciente sin diabetes diagnosticada."""

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
        default_factory=list, description=f"Lecturas del glucómetro (como mucho {MAX_READINGS})."
    )


# --- Salida ---


class ErrorOut(BaseModel):
    """Error de dominio (400)."""

    detail: str = Field(description="Qué dato no vale, en una frase.")


class QuestionOut(BaseModel):
    """Pregunta previa a la prueba."""

    key: str = Field(description="Clave de la pregunta; es el nombre del campo en las respuestas.")
    text: str = Field(description="Pregunta tal como la lee el paciente.")


class KitOut(BaseModel):
    """Material del kit y lo gastado en el episodio actual."""

    channel: Channel = Field(description="Canal del kit.")
    strips_total: int = Field(description="Tiras que trae el kit.")
    strips_used: int = Field(description="Tiras gastadas en el episodio.")
    tubes_total: int = Field(description="Tubos que trae el kit.")
    tubes_used: int = Field(description="Tubos gastados en el episodio.")


class TrajectoryPointOut(BaseModel):
    """Estimación del cociente en la fecha de una muestra, usando todas las muestras."""

    date: dt.date = Field(description="Fecha de la muestra.")
    median: float = Field(description="Mediana del cociente albúmina/creatinina verdadero, en mg/g.")
    low: float = Field(description="Percentil 10, en mg/g.")
    high: float = Field(description="Percentil 90, en mg/g.")
    p_a2_plus: float = Field(description="Probabilidad de albuminuria (cociente verdadero de 30 mg/g o más).")


class AssessmentOut(BaseModel):
    """Estado de la albuminuria según el filtro bayesiano."""

    as_of: dt.date | None = Field(description="Fecha a la que se refiere el estado.")
    status: Status = Field(description="Estado de la albuminuria.")
    status_label: str = Field(description="Estado, como lo nombra el modelo.")
    category: Literal["A1", "A2", "A3"] = Field(description="Categoría KDIGO más probable.")
    p_a1: float = Field(description="Probabilidad de A1 (menos de 30 mg/g).")
    p_a2: float = Field(description="Probabilidad de A2 (de 30 a 300 mg/g).")
    p_a3: float = Field(description="Probabilidad de A3 (más de 300 mg/g).")
    median: float = Field(description="Mediana del cociente verdadero, en mg/g.")
    low: float = Field(description="Percentil 10, en mg/g.")
    high: float = Field(description="Percentil 90, en mg/g.")
    chronicity_met: bool = Field(description="Se cumple el criterio de cronicidad (dos momentos altos separados más de 3 meses).")
    repeat_from: dt.date | None = Field(description="Fecha desde la que una muestra alta cumpliría la cronicidad.")
    trajectory: list[TrajectoryPointOut] = Field(description="Un punto por muestra, en orden cronológico.")


class SampleOut(BaseModel):
    """Una muestra de la petición, lista para enseñarla."""

    kind: Literal["tira", "tubo"] = Field(description="Tipo de muestra.")
    date: dt.date = Field(description="Fecha de la muestra.")
    label: str = Field(description="Lectura en una línea.")
    nominal_uacr: float = Field(
        description="Cociente que sugiere la lectura, en mg/g: el medido en el tubo o 100 × albúmina / creatinina en la tira."
    )


class StepOut(BaseModel):
    """Siguiente paso del paciente, con el estado que lo justifica."""

    action: Action = Field(description="Qué toca ahora.")
    action_label: str = Field(description="La acción, en pocas palabras.")
    on: dt.date = Field(description="Día en que toca.")
    finished: bool = Field(description="El episodio ha terminado (prueba normal o pasa al centro de salud).")
    patient_message: str = Field(description="Lo que lee el paciente, literal del modelo.")
    clinician_note: str = Field(description="Lo que queda en la historia, literal del modelo.")
    p_albuminuria: float = Field(description="Probabilidad de albuminuria (cociente verdadero de 30 mg/g o más).")
    resolve_probability: float | None = Field(
        description="Probabilidad de que la prueba que se pide resuelva la duda; ``null`` si no se pide ninguna."
    )
    questions: list[QuestionOut] = Field(description="Preguntas que hay que hacer al paciente antes de la prueba.")
    kit: KitOut = Field(description="Material del kit y lo gastado.")
    assessment: AssessmentOut = Field(description="Estado de la albuminuria.")
    samples: list[SampleOut] = Field(description="Las muestras de la petición, en orden cronológico (el de ``trajectory``).")


class ChannelOut(BaseModel):
    """Un canal para hacer la prueba y el kit que le corresponde."""

    key: str = Field(description="Clave del canal.")
    value: str = Field(description="Nombre del canal; es lo que se manda en ``channel``.")
    strips: int = Field(description="Tiras que trae el kit.")
    tubes: int = Field(description="Tubos que trae el kit.")
    uses_strip: bool = Field(description="El canal usa tiras (si no, solo tubo).")
    strip_name: str | None = Field(description="Cómo se lee la tira en este canal.")


class StripOut(BaseModel):
    """Niveles de color que se pueden leer en la tira."""

    albumin_levels_mg_l: list[float] = Field(description="Niveles de la almohadilla de albúmina, en mg/l.")
    creatinine_levels_mg_dl: list[float] = Field(description="Niveles de la almohadilla de creatinina, en mg/dl.")


class QuestionInfoOut(BaseModel):
    """Pregunta previa a la prueba y lo que pasa si la respuesta es que sí."""

    key: str = Field(description="Clave de la pregunta; es el nombre del campo en las respuestas.")
    text: str = Field(description="Pregunta tal como la lee el paciente.")
    wait_days: int = Field(description="Días que se aplaza la prueba si contesta que sí.")
    advice: str = Field(description="Consejo que recibe si contesta que sí.")
    audience: str = Field(description="A quién se le pregunta.")


class PatientPresetOut(BaseModel):
    """Paciente de ejemplo (inventado)."""

    id: str = Field(description="Identificador del paciente de ejemplo.")
    name: str = Field(description="Nombre inventado.")
    summary: str = Field(description="Quién es, en una línea.")
    age: float = Field(description="Edad en años.")
    female: bool = Field(description="Es mujer.")
    diabetes: bool = Field(description="Tiene diabetes diagnosticada.")
    egfr: float = Field(description="Filtrado glomerular estimado, en ml/min/1,73 m².")
    channel: Channel = Field(description="Canal por el que hace la prueba.")


class ScriptStepOut(BaseModel):
    """Un paso de un recorrido guiado: lo que hace el paciente."""

    kind: Literal["respuestas", "tira", "tubo"] = Field(
        description="``respuestas``: contesta las preguntas de hoy. ``tira`` o ``tubo``: hace la prueba el día que tocaba."
    )
    answers: Answers | None = Field(
        None, description="Las respuestas: las de hoy (``respuestas``) o las que se guardan con la muestra."
    )
    albumin_mg_l: float | None = Field(None, description="Lectura de albúmina de la tira, en mg/l.")
    creatinine_mg_dl: float | None = Field(None, description="Lectura de creatinina de la tira, en mg/dl.")
    uacr: float | None = Field(None, description="Resultado del tubo, en mg/g.")
    note: str = Field(description="Qué pasa en este paso, para quien presenta la demo.")


class ScriptOut(BaseModel):
    """Recorrido guiado de un paciente de ejemplo."""

    id: str = Field(description="Identificador del recorrido.")
    title: str = Field(description="Título corto.")
    patient_id: str = Field(description="Paciente de ejemplo que lo hace.")
    summary: str = Field(description="Qué enseña el recorrido, en una línea.")
    steps: list[ScriptStepOut] = Field(description="Lo que hace el paciente, en orden.")


class ConfigOut(BaseModel):
    """Lo que la app del paciente necesita antes de empezar."""

    today: dt.date = Field(description="Fecha en la que empieza la demo.")
    channels: list[ChannelOut] = Field(description="Canales por los que se puede hacer la prueba y su kit.")
    strip: StripOut = Field(description="Niveles de color de la tira.")
    questions: list[QuestionInfoOut] = Field(description="Preguntas previas a la prueba.")
    patients: list[PatientPresetOut] = Field(description="Pacientes de ejemplo (sintéticos).")
    scripts: list[ScriptOut] = Field(description="Recorridos guiados para la demo.")


class BPOut(BaseModel):
    """Resumen de la automedida de la tensión (se descarta el primer día)."""

    n: int = Field(description="Lecturas usadas.")
    days: int = Field(description="Días usados.")
    sbp: float = Field(description="Media de la sistólica, en mmHg.")
    dbp: float = Field(description="Media de la diastólica, en mmHg.")
    sbp_se: float = Field(description="Error típico de la media de la sistólica.")
    dbp_se: float = Field(description="Error típico de la media de la diastólica.")
    p_sbp_high: float = Field(
        description=f"Probabilidad de que la sistólica media verdadera sea de {HOME_SBP_LIMIT:g} mmHg o más."
    )
    p_dbp_high: float = Field(
        description=f"Probabilidad de que la diastólica media verdadera sea de {HOME_DBP_LIMIT:g} mmHg o más."
    )
    p_high: float = Field(description="Probabilidad de tensión alta en casa: la mayor de las dos anteriores.")
    valid: bool = Field(description="Hay lecturas suficientes para dar la media por buena.")
    message: str = Field(description="Conclusión, literal del modelo.")


class RhythmOut(BaseModel):
    """Probabilidad de fibrilación auricular sin diagnosticar."""

    prior: float = Field(description="Probabilidad de fibrilación auricular sin diagnosticar por edad y sexo (estudio OFRECE).")
    probability: float = Field(description="Probabilidad de fibrilación auricular tras las comprobaciones.")
    alert: bool = Field(description=f"La probabilidad llega a {AF_ALERT_PROBABILITY:g}: hay que avisar.")
    message: str | None = Field(description="Texto de la alerta, literal del modelo; ``null`` si no hay alerta.")


class GlucoseOut(BaseModel):
    """Resumen de las glucosas en ayunas medidas en casa."""

    fasting_mean_mg_dl: float | None = Field(
        description="Media geométrica de las lecturas en ayunas, en mg/dl; ``null`` si no hay ninguna."
    )
    fasting_readings: int = Field(description="Lecturas en ayunas.")
    days_above_126: int = Field(
        description=f"Días distintos con glucosa en ayunas de {DIABETES_FASTING_GLUCOSE:g} mg/dl o más."
    )
    alert: bool = Field(description=f"Hay {GLUCOSE_ALERT_DAYS} días o más por encima: hay que confirmar.")
    message: str | None = Field(description="Texto de la alerta, literal del modelo; ``null`` si no hay alerta.")


# --- Pacientes de ejemplo y recorridos guiados (inventados) ---

PATIENTS: tuple[PatientPresetOut, ...] = (
    PatientPresetOut(
        id="julian", name="Julián", age=62, female=False, diabetes=False, egfr=85, channel=Channel.APP,
        summary="62 años, sin diabetes, FG 85. Nunca se le ha mirado la albúmina en la orina.",
    ),
    PatientPresetOut(
        id="pilar", name="Pilar", age=58, female=True, diabetes=False, egfr=88, channel=Channel.APP,
        summary="58 años, sin diabetes, FG 88. Es su primer cribado.",
    ),
    PatientPresetOut(
        id="marta", name="Marta", age=47, female=True, diabetes=True, egfr=92, channel=Channel.APP,
        summary="47 años, con diabetes, FG 92. Le toca el cribado de este año.",
    ),
    PatientPresetOut(
        id="vicente", name="Vicente", age=73, female=False, diabetes=True, egfr=52, channel=Channel.APP,
        summary="73 años, con diabetes y filtrado bajo (FG 52). Parte de un riesgo alto.",
    ),
)  # fmt: skip
_PATIENT_BY_ID = {p.id: p for p in PATIENTS}


def _no_to_all(patient_id: str) -> Answers:
    """Contesta que no a las preguntas que el modelo hace a ese paciente."""
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


SCRIPTS: tuple[ScriptOut, ...] = (
    ScriptOut(
        id="normal",
        title="Normal a la primera",
        patient_id="julian",
        summary="Contesta que no a las preguntas previas, hace una tira y sale normal: hasta dentro de un año.",
        steps=[
            _answers_step("julian", "Antes de la prueba contesta que no a todas las preguntas."),
            _strip_step("julian", 10, 100, "Hace la tira: albúmina en el nivel más bajo (10 mg/l), con creatinina de 100 mg/dl."),
        ],
    ),
    ScriptOut(
        id="confirmada",
        title="De la duda a la confirmación",
        patient_id="pilar",
        summary="Dos tiras dudosas, dos tubos al laboratorio y, tres meses después, la repetición que lo confirma.",
        steps=[
            _strip_step("pilar", 30, 100, "Primera tira: algo de albúmina (30 mg/l), con creatinina de 100 mg/dl."),
            _strip_step("pilar", 30, 50, "Segunda tira: la misma albúmina (30 mg/l) en una orina más diluida (creatinina de 50 mg/dl)."),
            _tube_step("pilar", 58, "Primer tubo: el laboratorio mide 58 mg/g."),
            _tube_step("pilar", 64, "Segundo tubo: el laboratorio mide 64 mg/g."),
            _tube_step("pilar", 71, "Tres meses después, el tubo de la repetición: 71 mg/g."),
        ],
    ),
    ScriptOut(
        id="aplazada",
        title="Aplazada por fiebre",
        patient_id="marta",
        summary="Tiene fiebre: la prueba se aplaza en vez de gastar una tira en una muestra que no vale.",
        steps=[
            _answers_step("marta", "Antes de la prueba contesta que tiene fiebre.", fever=True),
            _strip_step("marta", 10, 100, "Pasada la espera hace la tira: albúmina de 10 mg/l, con creatinina de 100 mg/dl."),
        ],
    ),
    ScriptOut(
        id="laboratorio",
        title="Riesgo alto: de la tira al laboratorio",
        patient_id="vicente",
        summary="Parte de un riesgo alto: tras una tira dudosa no se pide otra, sino el tubo, y el laboratorio lo aclara.",
        steps=[
            _strip_step("vicente", 30, 100, "Primera tira: algo de albúmina (30 mg/l), con creatinina de 100 mg/dl."),
            _tube_step("vicente", 12, "El laboratorio mide 12 mg/g."),
        ],
    ),
)  # fmt: skip


# --- Piezas compartidas ---

_ERRORS = {400: {"model": ErrorOut, "description": "Algún dato no vale; ``detail`` dice cuál, en español."}}

# El filtro guarda en caché las tablas de la tira y no está pensado para varios hilos a la vez.
_MODEL_LOCK = threading.Lock()
# Respuestas de /step ya calculadas. La ruta es una función pura de la petición, así que
# repetir un recorrido (lo normal en la demo) no vuelve a calcular nada.
_STEP_CACHE: OrderedDict[str, StepOut] = OrderedDict()
_STEP_CACHE_SIZE = 512


@lru_cache(maxsize=1)
def _filter() -> AlbuminuriaFilter:
    """El filtro de albuminuria de la población de la demo, cargado una sola vez."""
    return load_default_filter(POPULATION)


def _require(condition: bool, message: str) -> None:
    """Error de dominio: 400 con una frase que se puede enseñar tal cual."""
    if not condition:
        raise HTTPException(status_code=400, detail=message)


def _require_date(day: dt.date, what: str) -> None:
    _require(DATE_MIN <= day <= DATE_MAX, f"{what} tiene que estar entre los años {DATE_MIN.year} y {DATE_MAX.year}.")


def _require_age(age: float) -> None:
    _require(AGE_MIN <= age <= AGE_MAX, f"La edad tiene que estar entre {AGE_MIN:g} y {AGE_MAX:g} años.")


def _levels(levels: tuple[float, ...], unit: str) -> str:
    """Los niveles de una almohadilla, para una frase: «10, 30, 80 y 150 mg/l»."""
    names = [f"{level:g}" for level in levels]
    return f"{', '.join(names[:-1])} y {names[-1]} {unit}"


def _context(answers: Answers | None) -> SampleContext | None:
    return None if answers is None else SampleContext(**answers.model_dump())


def _kit_size(kit: HomeKit) -> tuple[int, int]:
    """Tiras y tubos que el protocolo puede llegar a pedir con ese kit."""
    return (kit.strips if kit.strip is not None else 0), (kit.tubes if kit.tube else 0)


def _alert_text(*, glucose: list[GlucoseReading] | None = None, p_af: float | None = None) -> str | None:
    """Texto de la alerta de glucosa o de pulso tal como lo escribe el modelo.

    El modelo no expone esos literales: se redactan dentro de ``assessment._alerts``, una función
    interna. Se la llama con una historia vacía, de modo que solo pueda salir la alerta pedida.
    Si esa función cambiara, la ruta sigue respondiendo, sin texto.
    """
    record = clinical.ClinicalRecord(age=60.0, female=False, home_glucose=glucose or [])
    try:
        alerts = clinical._alerts(record, SimpleNamespace(status="sin_medir"), None, None, {}, p_af, None)
    except Exception:
        log.exception("No se pudo obtener el texto de la alerta del modelo")
        return None
    return alerts[0] if len(alerts) == 1 else None


# --- Configuración ---


@lru_cache(maxsize=1)
def _config() -> ConfigOut:
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
        audience = "todos" if factor.women_under is None else f"mujeres menores de {factor.women_under:g} años"
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
        patients=list(PATIENTS),
        scripts=list(SCRIPTS),
    )


@router.get("/config", response_model=ConfigOut, summary="Configuración de la app del paciente")
def config() -> ConfigOut:
    """Lo que la app necesita antes de empezar: fecha de la demo, canales, niveles de la tira,
    preguntas previas, pacientes de ejemplo y recorridos guiados.

    Un recorrido se reproduce contra ``/step`` así: se pide el primer paso con ``today`` y sin
    muestras, y después, por cada paso del recorrido,

    - ``respuestas``: se repite la petición con esas ``answers``. Si la respuesta es ``esperar``,
      se avanza ``today`` hasta su ``on`` y se vuelve a pedir, ya sin ``answers``.
    - ``tira`` o ``tubo``: se avanza ``today`` hasta el ``on`` de la última respuesta, se añade la
      muestra con esa fecha (y sus ``answers``) y se vuelve a pedir.
    """
    return _config()


# --- Protocolo de orina en casa ---


def _validate_step(body: StepIn, kit: HomeKit) -> None:
    """Errores de dominio de /step. Lanza un 400 con el primero que encuentra."""
    _require_age(body.patient.age)
    egfr = body.patient.egfr
    _require(
        egfr is None or EGFR_MIN <= egfr <= EGFR_MAX,
        f"El filtrado glomerular (FG) tiene que estar entre {EGFR_MIN:g} y {EGFR_MAX:g} ml/min/1,73 m².",
    )
    _require_date(body.today, "La fecha de hoy (today)")
    _require(
        body.episode_start is None or body.episode_start <= body.today,
        "El inicio del episodio (episode_start) no puede ser posterior a la fecha de hoy.",
    )
    _require(len(body.samples) <= MAX_SAMPLES, f"Se admiten como mucho {MAX_SAMPLES} muestras.")
    for number, sample in enumerate(body.samples, start=1):
        _require_date(sample.date, f"La fecha de la muestra {number}")
        _require(
            sample.date <= body.today,
            f"La muestra {number} es del {sample.date:%d/%m/%Y}, posterior a la fecha de hoy ({body.today:%d/%m/%Y}).",
        )
        if isinstance(sample, StripSampleIn):
            _require(kit.strip is not None, f"El canal «{kit.channel.value}» no usa tiras: solo admite muestras de tubo.")
            _require(
                sample.albumin_mg_l in kit.strip.albumin_levels,
                f"Muestra {number}: la tira no tiene el nivel de albúmina {sample.albumin_mg_l:g} mg/l. "
                f"Niveles posibles: {_levels(kit.strip.albumin_levels, 'mg/l')}.",
            )
            _require(
                sample.creatinine_mg_dl in kit.strip.creatinine_levels,
                f"Muestra {number}: la tira no tiene el nivel de creatinina {sample.creatinine_mg_dl:g} mg/dl. "
                f"Niveles posibles: {_levels(kit.strip.creatinine_levels, 'mg/dl')}.",
            )
        else:
            _require(
                0.0 < sample.uacr <= UACR_MAX,
                f"Muestra {number}: el resultado del laboratorio (uacr) tiene que ser mayor que 0 "
                f"y no pasar de {UACR_MAX:g} mg/g.",
            )
            creatinine = sample.creatinine_mg_dl
            _require(
                creatinine is None or 0.0 < creatinine <= URINE_CREATININE_MAX,
                f"Muestra {number}: la creatinina en orina tiene que ser mayor que 0 "
                f"y no pasar de {URINE_CREATININE_MAX:g} mg/dl.",
            )


def _model_sample(sample: StripSampleIn | TubeSampleIn, kit: HomeKit) -> StripSample | UrineSample:
    context = _context(sample.answers)
    if isinstance(sample, StripSampleIn):
        return StripSample(sample.date, kit.strip, sample.albumin_mg_l, sample.creatinine_mg_dl, context=context)
    return UrineSample(sample.date, sample.uacr, FIRST_MORNING, creatinine_mg_dl=sample.creatinine_mg_dl, context=context)


def _sample_out(sample: StripSample | UrineSample) -> SampleOut:
    """La muestra en una línea, con el formato de scripts/demo_casa.py."""
    if isinstance(sample, StripSample):
        label = f"Tira: albúmina {sample.albumin_mg_l:.0f} mg/l, creatinina {sample.creatinine_mg_dl:.0f} mg/dl"
        return SampleOut(kind="tira", date=sample.date, label=label, nominal_uacr=clean(sample.nominal_uacr, digits=DIGITS))
    return SampleOut(
        kind="tubo", date=sample.date, label=f"Tubo: {sample.uacr:.0f} mg/g", nominal_uacr=clean(sample.uacr, digits=DIGITS)
    )


_ASSESSMENT_INTERNALS = frozenset({"belief", "action", "next_sample_resolves", "log_evidence", "egfr_components"})


def _compute_step(body: StepIn) -> StepOut:
    kit = KITS[body.channel]
    _validate_step(body, kit)
    # Orden cronológico (estable): es el que usa el filtro y el de la trayectoria.
    samples = [_model_sample(s, kit) for s in sorted(body.samples, key=lambda s: s.date)]
    patient = Patient(body.patient.age, body.patient.female, body.patient.diabetes, body.patient.egfr, samples)
    # La ventana del episodio se pasa siempre de forma explícita: así el kit que se devuelve
    # se cuenta con la misma que usa el protocolo.
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
    """Respuesta de /step, sin repetir el cálculo de una petición ya vista."""
    key = body.model_dump_json()
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


@router.post("/step", response_model=StepOut, responses=_ERRORS, summary="Siguiente paso del protocolo de orina en casa")
def step(body: StepIn) -> StepOut:
    """Qué tiene que hacer el paciente ahora, dadas sus muestras hasta hoy.

    Es ``protocol.next_step`` sobre el filtro bayesiano de albuminuria: primero tiras, que son
    baratas; el tubo para el laboratorio solo si la duda sigue; y aplazar la prueba si las
    respuestas de hoy dicen que la muestra no valdría. El mensaje al paciente y la nota para la
    historia son los del modelo.
    """
    return _step(body)


# --- Otras medidas en casa ---


@router.post("/bp", response_model=BPOut, responses=_ERRORS, summary="Tensión medida en casa")
def blood_pressure(body: BPIn) -> BPOut:
    """Media de la automedida de la tensión y probabilidad de que esté alta (135/85 mmHg en casa).

    Sigue el protocolo habitual: se descarta el primer día y hacen falta al menos 12 lecturas en 3 días.
    """
    _require(len(body.readings) >= 1, "Hace falta al menos una lectura de tensión.")
    _require(len(body.readings) <= MAX_READINGS, f"Se admiten como mucho {MAX_READINGS} lecturas.")
    for number, reading in enumerate(body.readings, start=1):
        _require_date(reading.date, f"La fecha de la lectura {number}")
        _require(
            SBP_MIN <= reading.sbp <= SBP_MAX,
            f"Lectura {number}: la sistólica tiene que estar entre {SBP_MIN:g} y {SBP_MAX:g} mmHg.",
        )
        _require(
            DBP_MIN <= reading.dbp <= DBP_MAX,
            f"Lectura {number}: la diastólica tiene que estar entre {DBP_MIN:g} y {DBP_MAX:g} mmHg.",
        )
        _require(reading.sbp > reading.dbp, f"Lectura {number}: la sistólica tiene que ser mayor que la diastólica.")
    summary = summarize_home_bp([BPReading(r.date, r.sbp, r.dbp, r.evening) for r in body.readings])
    return BPOut(p_high=clean(summary.p_high, digits=DIGITS), **clean(summary, digits=DIGITS))


@router.post("/rhythm", response_model=RhythmOut, responses=_ERRORS, summary="Pulso irregular comprobado en casa")
def rhythm(body: RhythmIn) -> RhythmOut:
    """Probabilidad de fibrilación auricular sin diagnosticar tras las comprobaciones del pulso.

    Parte de la prevalencia española por edad y sexo (estudio OFRECE) y la actualiza con cada
    comprobación. Con una probabilidad de 0,5 o más salta la alerta.
    """
    _require_age(body.age)
    _require(len(body.checks) <= MAX_READINGS, f"Se admiten como mucho {MAX_READINGS} comprobaciones.")
    for number, check in enumerate(body.checks, start=1):
        _require_date(check.date, f"La fecha de la comprobación {number}")
    checks = [RhythmCheck(c.date, c.irregular) for c in body.checks]
    probability = af_probability(checks, body.age, female=body.female)
    alert = probability >= AF_ALERT_PROBABILITY
    return RhythmOut(
        prior=clean(af_prior(body.age, body.female), digits=DIGITS),
        probability=clean(probability, digits=DIGITS),
        alert=alert,
        message=_alert_text(p_af=probability) if alert else None,
    )


@router.post("/glucose", response_model=GlucoseOut, responses=_ERRORS, summary="Glucosa medida en casa")
def glucose(body: GlucoseIn) -> GlucoseOut:
    """Resumen de las glucosas capilares en ayunas (8 horas o más sin comer).

    Con 126 mg/dl o más en dos días distintos salta la alerta: es el criterio diagnóstico de
    diabetes, que hay que confirmar. La alerta supone que el paciente no tiene diabetes registrada.
    """
    _require(len(body.readings) <= MAX_READINGS, f"Se admiten como mucho {MAX_READINGS} lecturas.")
    for number, reading in enumerate(body.readings, start=1):
        _require_date(reading.date, f"La fecha de la lectura {number}")
        _require(
            GLUCOSE_MIN <= reading.mg_dl <= GLUCOSE_MAX,
            f"Lectura {number}: la glucosa tiene que estar entre {GLUCOSE_MIN:g} y {GLUCOSE_MAX:g} mg/dl.",
        )
        _require(
            0.0 <= reading.fasting_hours <= 24.0,
            f"Lectura {number}: las horas desde la última comida tienen que estar entre 0 y 24.",
        )
    readings = [GlucoseReading(r.date, r.mg_dl, r.fasting_hours) for r in body.readings]
    fasting = [r for r in readings if r.fasting_hours >= FASTING_HOURS]
    summary = summarize_glucose(fasting)  # con lecturas en ayunas, su media geométrica
    days = fasting_days_above(readings)
    alert = days >= GLUCOSE_ALERT_DAYS
    return GlucoseOut(
        fasting_mean_mg_dl=clean(summary[0], digits=DIGITS) if summary else None,
        fasting_readings=len(fasting),
        days_above_126=days,
        alert=alert,
        message=_alert_text(glucose=readings) if alert else None,
    )


# --- Precarga ---


def _play(script: ScriptOut) -> list[StepOut]:
    """Reproduce un recorrido guiado como lo hará la web (ver ``config``) y devuelve cada respuesta."""
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
    """Carga el filtro y deja calculados los recorridos guiados, para que la demo no espere.

    Recorrerlos llena la caché de respuestas y la de tablas de la tira de los pacientes de ejemplo.
    """
    _filter()
    _config()
    for script in SCRIPTS:
        _play(script)
