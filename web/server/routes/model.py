"""Rutas del modelo en vivo: filtro de albuminuria, tendencia del filtrado y evaluación de un paciente.

Cada ruta llama a los modelos reales de ``src/latenthealth`` y devuelve sus números y sus textos
tal cual. No guardan estado: la petición lleva todo lo necesario y la misma petición da siempre
la misma respuesta, así que las respuestas ya calculadas se reutilizan (la web repite muchas).

- ``POST /api/model/albuminuria``: el filtro bayesiano con las muestras de orina de un paciente.
- ``POST /api/model/egfr-trend``: nivel y pendiente del filtrado glomerular con sus analíticas.
- ``POST /api/model/assess``: evaluación cardio-renal-metabólica completa.
- ``GET /api/model/examples``: cuerpos de ejemplo listos para las tres rutas anteriores.

Errores: ``422`` si el cuerpo no tiene la forma o los límites declarados (con el mensaje en
español) y ``400`` si la forma es correcta pero los datos no cuadran entre sí (fechas, etc.).
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
from threadpoolctl import threadpool_limits  # viene con scikit-learn

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

from ..serialize import clean

REPO_DIR = Path(__file__).resolve().parents[3]
DEMO_SCRIPT = REPO_DIR / "scripts" / "demo.py"
DEMO_TODAY = dt.date(2026, 11, 14)  # «hoy» de los ejemplos

PROJECTION_MONTHS = (0, 3, 6, 12)  # albuminuria: incertidumbre si no se vuelve a medir
PROJECTION_YEARS = (1, 2, 3, 5)  # filtrado glomerular
BELIEF_POINTS = 200  # puntos de la creencia que se envían (la rejilla del filtro tiene 400)
STRIPS = {"movil": PHONE_STRIP, "ojo": EYE_STRIP}

# El filtro guarda tablas de las tiras y el panel predice con cientos de árboles: se evalúa de
# uno en uno (en paralelo va más lento y las cachés de los modelos no están pensadas para ello).
_FILTER_LOCK = threading.Lock()
_PANEL_LOCK = threading.Lock()


# --------------------------------------------------------------------------------------
# Errores de forma (422) con el mensaje en español
# --------------------------------------------------------------------------------------

_MESSAGES = {
    "missing": "Falta este campo.",
    "extra_forbidden": "Campo desconocido.",
    "greater_than": "Debe ser mayor que {gt}.",
    "greater_than_equal": "Debe ser como mínimo {ge}.",
    "less_than": "Debe ser menor que {lt}.",
    "less_than_equal": "Debe ser como máximo {le}.",
    "too_long": "Admite como mucho {max_length} elementos (hay {actual_length}).",
    "too_short": "Necesita al menos {min_length} elementos (hay {actual_length}).",
    "literal_error": "Valor no admitido. Debe ser {expected}.",
    "union_tag_invalid": "Tipo de muestra desconocido ({tag}). El campo «kind» debe ser {expected_tags}.",
    "union_tag_not_found": "Falta el campo «kind», que dice qué tipo de muestra es.",
    "finite_number": "Debe ser un número finito.",
    "float_parsing": "Debe ser un número.",
    "float_type": "Debe ser un número.",
    "bool_parsing": "Debe ser verdadero o falso.",
    "bool_type": "Debe ser verdadero o falso.",
    "string_type": "Debe ser un texto.",
    "list_type": "Debe ser una lista.",
    "model_attributes_type": "Debe ser un objeto con sus campos.",
    "json_invalid": "El cuerpo de la petición no es JSON válido.",
}
_DATE_MESSAGE = "Fecha no válida: se espera AAAA-MM-DD."


def _plain(value: Any) -> Any:
    """Valor del contexto de un error tal como se lee mejor: 18 y no 18.0, «o» y no «or»."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return value.replace(" or ", " o ")
    return value


def _in_spanish(error: dict[str, Any]) -> None:
    """Traduce el mensaje de un error de validación de Pydantic (se modifica en el sitio)."""
    kind = str(error.get("type", ""))
    template = _DATE_MESSAGE if kind.startswith("date_") else _MESSAGES.get(kind)
    if template is not None:
        try:
            error["msg"] = template.format(**{k: _plain(v) for k, v in (error.get("ctx") or {}).items()})
        except (KeyError, IndexError):
            pass  # se deja el mensaje original antes que perderlo
    try:  # un NaN en el cuerpo recibido no se puede devolver como JSON
        error["input"] = clean(error.get("input"))
    except TypeError:
        error["input"] = str(error.get("input"))


class SpanishErrorsRoute(APIRoute):
    """Ruta cuyos errores de validación del cuerpo (422) salen con el mensaje en español."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                for error in exc.errors():
                    _in_spanish(error)
                raise

        return handler


router = APIRouter(prefix="/api/model", tags=["Modelo en vivo"], route_class=SpanishErrorsRoute)


class DomainError(BaseModel):
    detail: str = Field(description="Qué no cuadra en los datos enviados, en español.")


_ERROR_400: dict[int | str, dict[str, Any]] = {
    400: {"model": DomainError, "description": "Los datos tienen buena forma pero no cuadran entre sí."}
}


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


# --------------------------------------------------------------------------------------
# Entradas comunes
# --------------------------------------------------------------------------------------

Day = Annotated[dt.date, Field(ge=dt.date(1900, 1, 1), le=dt.date(2100, 12, 31))]
Age = Annotated[float, Field(ge=18, le=100, description="Edad en años (de 18 a 100).")]
Population = Annotated[
    Literal["espana", "nhanes"],
    Field(
        description="Población de referencia: «espana» usa los priors recalibrados a atención primaria "
        "española; «nhanes», los modelos tal como se ajustaron."
    ),
]
SampleType = Literal["first_morning", "random"]

_ROUNDING = 1e-9  # margen del error de redondeo al sumar masas en coma flotante


def _probability(value: float) -> float:
    """Quita el error de redondeo de una probabilidad: 1.0000000000000002 -> 1.0; -1e-17 y -0.0 -> 0.0.

    El modelo las obtiene sumando masas en coma flotante y a veces se pasa del 1 o queda por debajo
    del 0 en el último decimal (en pantalla, «-0 %»). No cambia ningún valor más que ese margen: algo
    claramente fuera de [0, 1] sería un fallo del modelo y se deja como está para que se vea.
    """
    if -_ROUNDING < value <= 0.0:
        return 0.0
    if 1.0 < value < 1.0 + _ROUNDING:
        return 1.0
    return value


# Probabilidad de salida, como fracción entre 0 y 1.
Probability = Annotated[float, AfterValidator(_probability)]


class _Input(BaseModel):
    """Cuerpo de una petición: no admite campos desconocidos ni números no finitos."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class UrineLabSampleIn(_Input):
    """Muestra de orina medida en el laboratorio (cuantitativa)."""

    kind: Literal["laboratorio"] = Field(description="Tipo de muestra: medida en el laboratorio.")
    date: Day = Field(description="Fecha de la muestra (AAAA-MM-DD).")
    uacr: float = Field(
        gt=0,
        le=30000,
        description="Cociente albúmina/creatinina en mg/g (mayor que 0, hasta 30000). Si «censored» es "
        "verdadero, es el límite de detección: el resultado fue «menor que» este valor.",
    )
    sample_type: SampleType = Field(
        description="«first_morning»: primera orina de la mañana; «random»: muestra aleatoria."
    )
    creatinine_mg_dl: float | None = Field(
        None, gt=0, le=1000, description="Creatinina en orina de esa muestra, en mg/dl: dice lo diluida que estaba."
    )
    censored: bool = Field(False, description="El laboratorio solo informó «menor que» el valor de «uacr».")


class UrineStripSampleIn(_Input):
    """Tira reactiva hecha en casa: nivel de color de las almohadillas de albúmina y creatinina."""

    kind: Literal["tira"] = Field(description="Tipo de muestra: tira reactiva hecha en casa.")
    date: Day = Field(description="Fecha de la tira (AAAA-MM-DD).")
    albumin_mg_l: float = Field(
        gt=0,
        le=1000,
        description="Nivel leído en la almohadilla de albúmina, en mg/l (la tira tiene 10, 30, 80 y 150; "
        "otro valor se toma como el nivel más cercano).",
    )
    creatinine_mg_dl: float = Field(
        gt=0,
        le=1000,
        description="Nivel leído en la almohadilla de creatinina, en mg/dl (la tira tiene 10, 50, 100, 200 y 300).",
    )
    reader: Literal["movil", "ojo"] = Field(
        "movil", description="Quién lee el color: «movil» (foto con la aplicación) u «ojo» (comparando con el bote)."
    )
    sample_type: SampleType = Field("first_morning", description="Tipo de orina con la que se hizo la tira.")


UrineSampleIn = Annotated[UrineLabSampleIn | UrineStripSampleIn, Field(discriminator="kind")]
ModelSample = UrineSample | StripSample


def _model_samples(samples: list[UrineLabSampleIn | UrineStripSampleIn]) -> list[ModelSample]:
    """Muestras del modelo, en el orden de fechas en que el filtro las recorre."""
    out: list[ModelSample] = []
    for s in samples:
        if isinstance(s, UrineStripSampleIn):
            out.append(StripSample(s.date, STRIPS[s.reader], s.albumin_mg_l, s.creatinine_mg_dl, sample_type=s.sample_type))
        else:
            out.append(UrineSample(s.date, s.uacr, s.sample_type, s.censored, s.creatinine_mg_dl))
    return sorted(out, key=lambda s: s.date)


def _check_as_of(as_of: dt.date, dates: list[dt.date], what: str) -> None:
    """La fecha de evaluación no puede ser anterior a lo último medido (el modelo no lo descarta)."""
    if dates and as_of < max(dates):
        raise _bad_request(
            f"La fecha de evaluación (as_of, {as_of:%d/%m/%Y}) no puede ser anterior a la última {what} "
            f"({max(dates):%d/%m/%Y})."
        )


def _add_months(day: dt.date, months: int) -> dt.date:
    """Misma fecha ``months`` meses después (el último día del mes si ese día no existe)."""
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


# --------------------------------------------------------------------------------------
# 1. Filtro de albuminuria
# --------------------------------------------------------------------------------------


class AlbuminuriaPatientIn(_Input):
    age: Age
    female: bool = Field(description="Verdadero si es mujer.")
    diabetes: bool = Field(description="Diabetes diagnosticada.")
    egfr: float | None = Field(
        None,
        ge=5,
        le=150,
        description="Filtrado glomerular medido, en ml/min/1,73 m² (de 5 a 150). Si falta, el filtro supone 90.",
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

    patient: AlbuminuriaPatientIn = Field(description="Lo que el filtro sabe del paciente antes de medir.")
    samples: list[UrineSampleIn] = Field(
        default_factory=list, max_length=30, description="Muestras de orina, en cualquier orden (como mucho 30)."
    )
    as_of: Day = Field(description="Fecha de evaluación (AAAA-MM-DD). No puede ser anterior a la última muestra.")
    population: Population = "espana"


class AlbuminuriaPointOut(BaseModel):
    date: dt.date = Field(description="Fecha de la muestra.")
    median: float = Field(description="Mediana del UACR verdadero ese día, en mg/g (con todas las muestras).")
    low: float = Field(description="Percentil 10, en mg/g.")
    high: float = Field(description="Percentil 90, en mg/g.")
    p_a2_plus: Probability = Field(description="P(UACR verdadero ≥ 30 mg/g) ese día.")


class AlbuminuriaProjectionOut(BaseModel):
    months: int = Field(description="Meses desde la fecha de evaluación.")
    date: dt.date = Field(description="Fecha a la que corresponde el punto.")
    median: float = Field(description="Mediana del UACR verdadero, en mg/g.")
    low: float = Field(description="Percentil 10, en mg/g.")
    high: float = Field(description="Percentil 90, en mg/g.")
    p_a2_plus: Probability = Field(description="P(UACR verdadero ≥ 30 mg/g).")


class NextSampleResolvesOut(BaseModel):
    first_morning: Probability = Field(description="Con una muestra más de primera orina de la mañana.")
    random: Probability = Field(description="Con una muestra aleatoria más.")


class AlbuminuriaBeliefOut(BaseModel):
    uacr: list[float] = Field(description="Centro de cada celda de la rejilla, en mg/g (escala logarítmica).")
    mass: list[Probability] = Field(description="Probabilidad de que el UACR verdadero esté en esa celda. Suma 1.")


class UrineSampleOut(BaseModel):
    kind: Literal["laboratorio", "tira"] = Field(description="Tipo de muestra.")
    date: dt.date = Field(description="Fecha de la muestra.")
    label: str = Field(description="Nombre que el modelo da a ese tipo de muestra o de tira.")
    value_mg_g: float = Field(
        description="UACR en mg/g: el medido en el laboratorio (o su límite de detección si «censored») o el "
        "aproximado que sugiere la lectura de la tira."
    )
    sample_type: SampleType = Field(description="Primera orina de la mañana o muestra aleatoria.")
    censored: bool = Field(
        description="El laboratorio solo informó «menor que»: «value_mg_g» es entonces el límite de detección, "
        "no una medida. Siempre falso en las tiras."
    )


class AlbuminuriaSummaryOut(BaseModel):
    """Estado de la albuminuria tal como lo devuelve el filtro."""

    as_of: dt.date = Field(description="Fecha de evaluación.")
    status: Literal["sin_medir", "descartada", "dudosa", "pendiente_cronicidad", "confirmada"] = Field(
        description="Estado de la albuminuria."
    )
    status_label: str = Field(description="Nombre del estado para mostrarlo.")
    category: Literal["A1", "A2", "A3"] = Field(description="Categoría KDIGO más probable.")
    p_a1: Probability = Field(description="P(UACR verdadero < 30 mg/g).")
    p_a2: Probability = Field(description="P(UACR verdadero entre 30 y 300 mg/g).")
    p_a3: Probability = Field(description="P(UACR verdadero > 300 mg/g).")
    p_a2_plus: Probability = Field(description="P(UACR verdadero ≥ 30 mg/g): la probabilidad de albuminuria.")
    median: float = Field(description="Mediana del UACR verdadero, en mg/g.")
    low: float = Field(description="Percentil 10, en mg/g.")
    high: float = Field(description="Percentil 90, en mg/g.")
    action: str = Field(description="Qué hacer, con las palabras del modelo.")
    chronicity_met: bool = Field(description="Se cumple el criterio de cronicidad (más de tres meses).")
    repeat_from: dt.date | None = Field(
        description="Fecha desde la que una muestra alta cumple la cronicidad; nulo si ninguna muestra ha salido alta."
    )
    next_sample_resolves: NextSampleResolvesOut | None = Field(
        description="Probabilidad de que una muestra más confirme o descarte la albuminuria. Solo si el estado es "
        "«sin_medir» o «dudosa»; si no, nulo."
    )
    trajectory: list[AlbuminuriaPointOut] = Field(description="Un punto por muestra, por fecha (suavizado).")
    samples: list[UrineSampleOut] = Field(
        description="Las muestras recibidas, en el mismo orden que la trayectoria, con su valor para dibujarlas."
    )


class AlbuminuriaOut(AlbuminuriaSummaryOut):
    projection: list[AlbuminuriaProjectionOut] = Field(
        description="Incertidumbre a 0, 3, 6 y 12 meses si no se vuelve a medir. No es un pronóstico: la banda se "
        "ensancha porque el dato envejece."
    )
    belief: AlbuminuriaBeliefOut = Field(description="Lo que el filtro cree hoy sobre el UACR verdadero.")
    prior: AlbuminuriaBeliefOut = Field(description="Lo que creía antes de ver ninguna muestra.")


@lru_cache(maxsize=None)
def _filter(population: str) -> AlbuminuriaFilter:
    """Filtro de cada población, cargado una sola vez."""
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
    """Campos comunes a ``/albuminuria`` y a la parte de albuminuria de ``/assess``."""
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
    """Agrupa celdas vecinas de la rejilla para enviar unos ``points`` puntos sin perder masa."""
    step = max(1, math.ceil(filt.x.size / points))
    starts = np.arange(0, filt.x.size, step)
    sizes = np.diff(np.r_[starts, filt.x.size])
    centers = np.add.reduceat(filt.x, starts) / sizes  # centro de cada grupo, en log
    grouped = np.add.reduceat(np.asarray(mass, dtype=float), starts)
    return AlbuminuriaBeliefOut(uacr=np.exp(centers).tolist(), mass=grouped.tolist())


def _compute_albuminuria(body: AlbuminuriaIn) -> AlbuminuriaOut:
    samples = _model_samples(body.samples)
    _check_as_of(body.as_of, [s.date for s in samples], "muestra")
    filt = _filter(body.population)
    patient = Patient(body.patient.age, body.patient.female, body.patient.diabetes, body.patient.egfr, samples)
    with _FILTER_LOCK:
        current = filt.assess(patient, as_of=body.as_of)
        projection = []
        for months in PROJECTION_MONTHS:
            day = _add_months(body.as_of, months)
            # Sin muestras no hay nada que envejezca: el punto no cambia. La acción y el estado
            # proyectados no se exponen, así que no hace falta el cálculo lento (detail).
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
def _albuminuria_cached(key: str) -> AlbuminuriaOut:
    return _compute_albuminuria(AlbuminuriaIn.model_validate_json(key))


@router.post(
    "/albuminuria",
    response_model=AlbuminuriaOut,
    responses=_ERROR_400,
    summary="Filtro bayesiano de la albuminuria",
)
def albuminuria(body: AlbuminuriaIn) -> AlbuminuriaOut:
    """Combina las muestras de orina de un paciente (laboratorio y tiras de casa) y devuelve lo que se
    sabe de su albuminuria verdadera: probabilidades, estado, qué hacer, la creencia completa sobre
    la rejilla y cómo envejece esa creencia si no se vuelve a medir."""
    return _albuminuria_cached(body.model_dump_json())


# --------------------------------------------------------------------------------------
# 2. Tendencia del filtrado glomerular
# --------------------------------------------------------------------------------------


class EgfrMeasurementIn(_Input):
    date: Day = Field(description="Fecha de la analítica (AAAA-MM-DD).")
    egfr: float = Field(ge=5, le=150, description="Filtrado glomerular estimado, en ml/min/1,73 m² (de 5 a 150).")
    source: Literal["laboratorio", "capilar"] = Field(
        "laboratorio", description="«laboratorio» o «capilar» (punción en el dedo, con más ruido)."
    )
    above: bool = Field(
        False, description="El informe solo dice «mayor que» ese valor (muchos laboratorios cortan en 90)."
    )


class TreatmentStartIn(_Input):
    date: Day = Field(description="Fecha en que empezó el tratamiento (AAAA-MM-DD).")
    kind: Literal["isglt2", "ieca_ara2"] = Field(description="«isglt2» o «ieca_ara2» (IECA o ARA-II).")


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
    female: bool = Field(description="Verdadero si es mujer.")
    diabetes: bool = Field(False, description="Diabetes diagnosticada: hace más probable un descenso rápido.")
    p_a2: float = Field(0.0, ge=0, le=1, description="Probabilidad de albuminuria de 30 a 300 mg/g (del filtro).")
    p_a3: float = Field(0.0, ge=0, le=1, description="Probabilidad de albuminuria de más de 300 mg/g.")
    measurements: list[EgfrMeasurementIn] = Field(
        default_factory=list, max_length=40, description="Analíticas de filtrado, en cualquier orden (como mucho 40)."
    )
    treatments: list[TreatmentStartIn] = Field(
        default_factory=list,
        max_length=10,
        description="Inicios de tratamiento: explican una caída inicial del filtrado que no es un deterioro.",
    )
    as_of: Day | None = Field(
        None,
        description="Fecha de evaluación (AAAA-MM-DD). Si falta, la de la última analítica. "
        "No puede ser anterior a ella.",
    )


class EgfrTrendPointOut(BaseModel):
    date: dt.date = Field(description="Fecha de la analítica.")
    level: float = Field(description="Filtrado estimado ese día (suavizado), en ml/min/1,73 m².")
    low: float = Field(description="Límite inferior del intervalo del 80 %.")
    high: float = Field(description="Límite superior del intervalo del 80 %.")


class EgfrProjectionOut(BaseModel):
    years: int = Field(description="Años desde la fecha de evaluación.")
    date: dt.date = Field(description="Fecha a la que corresponde el punto.")
    level: float = Field(description="Filtrado esperado si la tendencia sigue, en ml/min/1,73 m² (nunca menos de 0).")
    low: float = Field(description="Percentil 10 (nunca menos de 0).")
    high: float = Field(description="Percentil 90 (nunca menos de 0).")


class EgfrMeasurementOut(BaseModel):
    date: dt.date = Field(description="Fecha de la analítica.")
    egfr: float = Field(description="Valor informado, en ml/min/1,73 m².")
    source: Literal["laboratorio", "capilar"] = Field(description="Laboratorio o punción capilar.")
    above: bool = Field(description="El informe solo decía «mayor que» ese valor.")


class EgfrTrendOut(BaseModel):
    as_of: dt.date = Field(description="Fecha de evaluación.")
    n: int = Field(description="Analíticas usadas.")
    span_years: float = Field(description="Años entre la primera y la última analítica.")
    level: float = Field(description="Filtrado actual estimado, en ml/min/1,73 m².")
    level_low: float = Field(description="Límite inferior del intervalo del 80 % del nivel.")
    level_high: float = Field(description="Límite superior del intervalo del 80 % del nivel.")
    slope: float = Field(description="Pendiente, en ml/min/1,73 m² por año (negativa si baja).")
    slope_low: float = Field(description="Límite inferior del intervalo del 80 % de la pendiente.")
    slope_high: float = Field(description="Límite superior del intervalo del 80 % de la pendiente.")
    p_decline: Probability = Field(description="P(pierde más de 3 ml/min/1,73 m² al año).")
    p_rapid: Probability = Field(description="P(pierde más de 5 al año): descenso rápido según KDIGO.")
    p_below_60: Probability = Field(description="P(filtrado actual < 60).")
    p_below_30_in_5y: Probability = Field(description="P(filtrado < 30 dentro de cinco años).")
    status: Literal["sin_datos", "insuficiente", "estable", "descenso", "descenso_rapido", "incierto"] = Field(
        description="Lectura de la tendencia."
    )
    status_label: str = Field(description="Nombre del estado para mostrarlo.")
    chronic_below_60: bool = Field(
        description="Dos analíticas separadas más de tres meses con filtrado menor de 60 muy probable."
    )
    measured_drop_explained: float = Field(
        description="Caída esperada por los tratamientos iniciados, en ml/min/1,73 m² (0 si no hay ninguno)."
    )
    trajectory: list[EgfrTrendPointOut] = Field(description="Un punto por analítica, por fecha (suavizado).")
    projection: list[EgfrProjectionOut] = Field(
        description="A 1, 2, 3 y 5 años con la fórmula del propio modelo. Vacía si no hay ninguna analítica."
    )
    measurements: list[EgfrMeasurementOut] = Field(description="Las analíticas recibidas, por fecha.")


Mixture = list[tuple[float, float, float]]


def _level_ahead(trend: kidney_trend.EgfrTrend, years: float, params: kidney_trend.TrendParams | None = None) -> Mixture:
    """Nivel del filtrado dentro de ``years`` años: (peso, media, desviación) de cada grupo de la mezcla.

    Es la fórmula con la que ``fit_trend`` calcula ``p_below_30_in_5y``: media ``m0 + m1·t`` y
    varianza ``[1, t]·P·[1, t]ᵀ`` más el ruido del proceso acumulado en ``t`` años.
    """
    params = params or kidney_trend.TrendParams()
    ahead = np.array([1.0, float(years)])
    noise = params.level_noise**2 * years + params.slope_noise**2 * years**3 / 3.0
    return [(float(w), float(ahead @ m), float(np.sqrt(ahead @ P @ ahead + noise))) for w, m, P in trend.components]


def _mixture_cdf(mixture: Mixture, value: float) -> float:
    return float(sum(w * ndtr((value - mean) / sd) for w, mean, sd in mixture))


def _mixture_quantile(mixture: Mixture, q: float) -> float:
    """Cuantil de una mezcla de normales: está entre los cuantiles de sus componentes."""
    candidates = [mean + float(ndtri(q)) * sd for _, mean, sd in mixture]
    lo, hi = min(candidates), max(candidates)
    if _mixture_cdf(mixture, lo) >= q:  # un solo grupo con peso: el cuantil es el suyo
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
        level=max(mean, 0.0),  # un filtrado negativo no existe
        low=max(_mixture_quantile(mixture, 0.1), 0.0),
        high=max(_mixture_quantile(mixture, 0.9), 0.0),
    )


def _compute_egfr_trend(body: EgfrTrendIn) -> EgfrTrendOut:
    measurements = sorted(
        (kidney_trend.EgfrMeasurement(m.date, m.egfr, m.source, m.above) for m in body.measurements),
        key=lambda m: m.date,
    )
    if body.as_of is None and not measurements:
        raise _bad_request("Sin analíticas hay que indicar la fecha de evaluación (as_of).")
    as_of = body.as_of or measurements[-1].date
    _check_as_of(as_of, [m.date for m in measurements], "analítica")
    if body.p_a2 + body.p_a3 > 1.0 + 1e-9:
        raise _bad_request("Las probabilidades de albuminuria p_a2 y p_a3 no pueden sumar más de 1.")
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
        # Sin ninguna analítica solo hay prior: no hay nada que proyectar.
        projection=[_trend_projection(trend, years) for years in PROJECTION_YEARS] if measurements else [],
        measurements=[clean(m) for m in measurements],
    )


@lru_cache(maxsize=256)
def _egfr_trend_cached(key: str) -> EgfrTrendOut:
    return _compute_egfr_trend(EgfrTrendIn.model_validate_json(key))


@router.post(
    "/egfr-trend",
    response_model=EgfrTrendOut,
    responses=_ERROR_400,
    summary="Tendencia del filtrado glomerular",
)
def egfr_trend(body: EgfrTrendIn) -> EgfrTrendOut:
    """Nivel y pendiente del filtrado con las analíticas previas, separando el descenso real del ruido
    de la creatinina y descontando la caída esperada al empezar un tratamiento. Con menos de dos
    analíticas devuelve el estado «sin_datos» o «insuficiente». Los parámetros del modelo son
    supuestos de la literatura: está comprobado solo en simulación."""
    return _egfr_trend_cached(body.model_dump_json())


# --------------------------------------------------------------------------------------
# 3. Evaluación completa de un paciente
# --------------------------------------------------------------------------------------


class MeasuredLabsIn(_Input):
    """Analítica reciente. Lo medido siempre sustituye a la estimación del modelo."""

    egfr: float | None = Field(None, ge=5, le=150, description="Filtrado glomerular, en ml/min/1,73 m² (de 5 a 150).")
    hba1c: float | None = Field(None, ge=3, le=20, description="HbA1c, en % (de 3 a 20).")
    glucose: float | None = Field(None, ge=20, le=1000, description="Glucosa sin ayuno, en mg/dl.")
    potassium: float | None = Field(None, ge=1.5, le=9, description="Potasio, en mmol/l.")
    non_hdl: float | None = Field(None, ge=20, le=600, description="Colesterol no-HDL, en mg/dl.")
    hemoglobin: float | None = Field(None, ge=3, le=25, description="Hemoglobina, en g/dl.")
    nt_probnp: float | None = Field(None, gt=0, le=100000, description="NT-proBNP, en pg/ml.")
    total_cholesterol: float | None = Field(None, ge=50, le=700, description="Colesterol total, en mg/dl.")
    hdl: float | None = Field(None, ge=5, le=200, description="Colesterol HDL, en mg/dl.")


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
    female: bool = Field(description="Verdadero si es mujer.")
    bmi: float | None = Field(None, ge=10, le=80, description="Índice de masa corporal, en kg/m².")
    waist: float | None = Field(None, ge=40, le=200, description="Perímetro de cintura, en cm.")
    sbp: float | None = Field(None, ge=60, le=260, description="Tensión sistólica media en consulta, en mmHg.")
    dbp: float | None = Field(None, ge=30, le=160, description="Tensión diastólica media en consulta, en mmHg.")
    diabetes: bool = Field(False, description="Diabetes diagnosticada.")
    prediabetes: bool = Field(False, description="Prediabetes diagnosticada.")
    insulin: bool = Field(False, description="En tratamiento con insulina.")
    diabetes_pills: bool = Field(False, description="Toma antidiabéticos orales.")
    hypertension: bool = Field(False, description="Hipertensión diagnosticada.")
    bp_meds: bool = Field(False, description="Toma fármacos para la tensión.")
    high_cholesterol: bool = Field(False, description="Colesterol alto diagnosticado.")
    cholesterol_meds: bool = Field(False, description="Toma fármacos para el colesterol.")
    heart_failure: bool = Field(False, description="Insuficiencia cardíaca diagnosticada.")
    coronary: bool = Field(False, description="Cardiopatía isquémica.")
    stroke: bool = Field(False, description="Ictus previo.")
    kidney_disease: bool = Field(False, description="Enfermedad renal crónica ya registrada.")
    smoker_now: bool = Field(False, description="Fuma ahora.")
    smoker_ever: bool = Field(False, description="Ha fumado alguna vez.")
    measured: MeasuredLabsIn = Field(default_factory=MeasuredLabsIn, description="Analítica reciente (solo lo que haya).")
    urine_samples: list[UrineSampleIn] = Field(
        default_factory=list, max_length=30, description="Muestras de orina, en cualquier orden (como mucho 30)."
    )
    as_of: Day = Field(description="Fecha de evaluación (AAAA-MM-DD). No puede ser anterior a la última muestra de orina.")
    population: Population = "espana"


_RECORD_FIELDS = tuple(
    name for name in AssessIn.model_fields if name not in ("measured", "urine_samples", "as_of", "population")
)


class BloodEstimateOut(BaseModel):
    key: str = Field(description="Clave de la variable (egfr, hba1c, glucose, potassium, non_hdl, hemoglobin, nt_probnp).")
    name: str = Field(description="Nombre para mostrar.")
    unit: str = Field(description="Unidad.")
    median: float = Field(description="Valor medido o mediana de la estimación.")
    low: float = Field(description="Percentil 10 (igual al valor si está medido).")
    high: float = Field(description="Percentil 90 (igual al valor si está medido).")
    measured: bool = Field(description="Verdadero si viene de la analítica; falso si lo estima el modelo.")
    decimals: int = Field(description="Decimales con los que conviene mostrarlo.")
    source: str = Field(description="De dónde sale el valor: «medido», «estimado»...")


class KdigoCellOut(BaseModel):
    a: Literal["A1", "A2", "A3"] = Field(description="Categoría de albuminuria.")
    p: Probability = Field(description="Probabilidad de que el paciente esté en esa casilla.")
    risk: Literal["bajo", "moderado", "alto", "muy alto"] = Field(description="Nivel de riesgo KDIGO de la casilla.")


class KdigoRowOut(BaseModel):
    g: Literal["G1", "G2", "G3a", "G3b", "G4", "G5"] = Field(description="Categoría de filtrado glomerular.")
    cells: list[KdigoCellOut] = Field(description="Las tres casillas de la fila: A1, A2 y A3.")


class CvRiskOut(BaseModel):
    score: Probability = Field(description="SCORE2 o SCORE2-OP a 10 años (mediana si faltan datos), como fracción.")
    score_low: Probability = Field(description="Percentil 10 del SCORE2 con lo que falta por medir.")
    score_high: Probability = Field(description="Percentil 90.")
    probs: list[Probability] = Field(description="Probabilidad de cada categoría real: bajo o moderado, alto, muy alto.")
    recorded: int = Field(description="Categoría con lo que ya consta en la historia: 0, 1 o 2 (mismo orden).")
    recorded_label: str = Field(description="Nombre de esa categoría.")
    category: int = Field(description="Categoría real más probable: 0, 1 o 2.")
    category_label: str = Field(description="Nombre de esa categoría.")
    approximate: bool = Field(description="Se han supuesto datos que faltan (tensión o HDL).")


class RecommendationOut(BaseModel):
    test: str = Field(description="Prueba que merece la pena pedir.")
    reason: str = Field(description="Por qué, con las palabras del modelo.")


class AssessOut(BaseModel):
    albuminuria: AlbuminuriaSummaryOut = Field(description="Estado de la albuminuria (el filtro, dentro de la evaluación).")
    blood: list[BloodEstimateOut] = Field(description="Panel de sangre: lo medido y lo estimado con la historia y la orina.")
    p_egfr_below_60: Probability = Field(description="P(filtrado glomerular < 60).")
    kdigo_g: dict[str, Probability] = Field(description="Probabilidad de cada categoría de filtrado: G1, G2, G3a, G3b, G4 y G5.")
    kdigo_risk: dict[str, Probability] = Field(
        description="Probabilidad de cada nivel de riesgo KDIGO: bajo, moderado, alto y «muy alto»."
    )
    kdigo_joint: list[KdigoRowOut] = Field(
        description="Mapa KDIGO: probabilidad conjunta de filtrado (6 filas) y albuminuria (3 columnas). Suma 1."
    )
    p_ckd: Probability = Field(description="P(filtrado < 60 o albuminuria ≥ 30 mg/g), sin exigir aún la cronicidad.")
    diabetes: str = Field(description="«diagnosticada», «probable», «posible» o «poco probable».")
    p_diabetes: Probability | None = Field(description="P(diabetes sin diagnosticar); nulo si ya está diagnosticada.")
    heart_failure: str = Field(description="«diagnosticada», «a descartar» o «poco probable».")
    p_nt_probnp_high: Probability | None = Field(description="P(NT-proBNP ≥ 125 pg/ml); nulo si ya está diagnosticada.")
    cv: CvRiskOut | None = Field(description="Riesgo cardiovascular con la incertidumbre de lo que falta por medir.")
    p_new_finding: Probability = Field(description="Probabilidad de un hallazgo nuevo si se completan las pruebas pendientes.")
    finding_by_test: dict[str, Probability] = Field(description="Esa probabilidad si solo se hiciera cada prueba.")
    recommendations: list[RecommendationOut] = Field(description="Pruebas que merece la pena pedir, por orden.")
    alerts: list[str] = Field(description="Hallazgos que ya piden actuar, con las palabras del modelo.")


def _compute_assess(body: AssessIn) -> AssessOut:
    samples = _model_samples(body.urine_samples)
    _check_as_of(body.as_of, [s.date for s in samples], "muestra de orina")
    record = panel.ClinicalRecord(
        **{name: getattr(body, name) for name in _RECORD_FIELDS},
        urine_samples=samples,
        measured=body.measured.model_dump(exclude_none=True),
    )
    # Con un solo paciente, repartir los árboles del panel entre hilos cuesta más de lo que
    # ahorra (medido: de 500-800 ms a unos 420). El resultado es el mismo.
    with _PANEL_LOCK, threadpool_limits(limits=1, user_api="openmp"):
        a = panel.assess(record, as_of=body.as_of, population=body.population, detail=True)

    joint = np.asarray(a.kdigo_joint, dtype=float)
    kdigo_joint = [
        KdigoRowOut(
            g=g,
            cells=[
                # Con el FG medido el modelo deja ceros negativos: los limpia el tipo ``Probability``.
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
def _assess_cached(key: str) -> AssessOut:
    return _compute_assess(AssessIn.model_validate_json(key))


@router.post(
    "/assess",
    response_model=AssessOut,
    responses=_ERROR_400,
    summary="Evaluación completa de un paciente",
)
def assess(body: AssessIn) -> AssessOut:
    """Une el filtro de albuminuria, el panel virtual de sangre y el riesgo cardiovascular: probabilidad
    de cada categoría KDIGO, de diabetes y de insuficiencia cardíaca, hallazgos que ya piden actuar y
    qué pruebas merece la pena pedir. Apoyo a la decisión con datos sintéticos: no diagnostica."""
    return _assess_cached(body.model_dump_json())


# --------------------------------------------------------------------------------------
# 4. Ejemplos
# --------------------------------------------------------------------------------------


class PatientExampleOut(BaseModel):
    id: str = Field(description="Identificador estable del ejemplo: p1 a p5.")
    title: str = Field(description="Descripción del paciente inventado.")
    assess: AssessIn = Field(description="Cuerpo listo para POST /api/model/assess.")
    albuminuria: AlbuminuriaIn = Field(description="Cuerpo listo para POST /api/model/albuminuria.")


class TrendExampleOut(BaseModel):
    id: str = Field(description="Identificador estable del ejemplo.")
    title: str = Field(description="Descripción de la serie.")
    egfr_trend: EgfrTrendIn = Field(description="Cuerpo listo para POST /api/model/egfr-trend.")


class ExamplesOut(BaseModel):
    as_of: dt.date = Field(description="Fecha de evaluación de todos los ejemplos.")
    patients: list[PatientExampleOut] = Field(description="Los cinco pacientes inventados de scripts/demo.py.")
    egfr_trends: list[TrendExampleOut] = Field(description="Dos series de filtrado: una que baja deprisa y una estable.")


def _demo_patients() -> dict[str, panel.ClinicalRecord]:
    """Pacientes de ``scripts/demo.py``. Importarlo no ejecuta nada: solo define el diccionario."""
    spec = importlib.util.spec_from_file_location("latenthealth_web_demo_patients", DEMO_SCRIPT)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.PATIENTS)


def _sample_in(sample: ModelSample) -> UrineLabSampleIn | UrineStripSampleIn:
    """Muestra del modelo -> muestra de la API (lo contrario de ``_model_samples``)."""
    if isinstance(sample, StripSample):
        reader = next((name for name, spec in STRIPS.items() if spec == sample.spec), None)
        if reader is None:
            raise ValueError(f"La API no admite la tira «{sample.spec.name}».")
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
    """Una analítica al año (cada 365 días) que termina en ``last``."""
    n = len(values)
    return [EgfrMeasurementIn(date=last - dt.timedelta(days=365 * (n - 1 - i)), egfr=v) for i, v in enumerate(values)]


@lru_cache(maxsize=1)
def _examples() -> ExamplesOut:
    patients = []
    for number, (title, record) in enumerate(_demo_patients().items(), start=1):
        samples = [_sample_in(s) for s in record.urine_samples]
        patients.append(
            PatientExampleOut(
                id=f"p{number}",
                title=re.sub(r"^\d+\.\s*", "", title),
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
        ("descenso_rapido", "Mujer de 68 años, diabética: el filtrado baja año tras año", [88, 79, 68, 60, 49]),
        ("estable", "Mujer de 68 años, diabética: el filtrado se mantiene", [75, 77, 74, 76, 75]),
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
    summary="Entradas de ejemplo para las rutas del modelo",
)
def examples() -> ExamplesOut:
    """Cinco pacientes inventados (no son pacientes reales) con su cuerpo para ``/assess`` y para
    ``/albuminuria``, y dos series de filtrado para ``/egfr-trend``. Todos con fecha 14/11/2026."""
    try:
        return _examples()
    except (OSError, ImportError, AttributeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="No se han podido cargar los ejemplos de scripts/demo.py.") from exc


# --------------------------------------------------------------------------------------
# Precarga
# --------------------------------------------------------------------------------------


def warm_up() -> None:
    """Carga el filtro y los modelos del panel evaluando los ejemplos.

    Así la primera petición de la demo tarda lo normal y los ejemplos, que es lo primero que se
    pulsa, ya están calculados. Va de lo rápido a lo lento para que el filtro esté disponible
    mientras se cargan los modelos del panel.
    """
    loaded = _examples()
    for patient in loaded.patients:
        _albuminuria_cached(patient.albuminuria.model_dump_json())
    for trend in loaded.egfr_trends:
        _egfr_trend_cached(trend.egfr_trend.model_dump_json())
    for patient in loaded.patients:
        _assess_cached(patient.assess.model_dump_json())
