"""Diabetes sin diagnosticar: qué aporta una glucosa capilar hecha en casa.

Hoy, para buscar diabetes oculta sin análisis, en España se usa el cuestionario FINDRISC. Un
glucómetro cuesta poco y el paciente puede repetir la medida. Aquí están los datos para
comparar las dos cosas con personas reales: NHANES 2005-2018, que tiene de cada persona la
glucosa en sangre, cuántas horas llevaba sin comer y la HbA1c (la referencia: 6,5 % o más es
diabetes).

La glucosa de NHANES es de laboratorio. Para que cuente como la de un glucómetro se le añade
el error que admite la norma de los glucómetros (ISO 15197: el 95 % de las lecturas dentro
del ±15 %), es decir, una desviación del 7,5 %.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .nhanes import read_xpt
from .outcomes.data import BASE_DIR, SUFFIX, _col, _yes_no, load_cohort

CYCLES = tuple(c for c in SUFFIX if int(c[:4]) >= 2005)
METER_LOG_SD = 0.075  # error de un glucómetro doméstico (ISO 15197:2013)
DIABETES_HBA1C = 6.5

# Lo que ya consta en la historia (como en el panel de sangre) más los antecedentes familiares.
HISTORY = [
    "age", "female", "bmi", "waist", "sbp", "dbp", "dx_prediabetes", "dx_hypertension", "bp_meds",
    "dx_high_cholesterol", "cholesterol_meds", "dx_heart_failure", "dx_coronary", "dx_stroke",
    "smoker_now", "smoker_ever", "family_diabetes",
]  # fmt: skip
URINE = ["log_uacr", "log_urine_creatinine"]
GLUCOSE = ["glucose_home", "fasting_hours"]
BLOCKS = {
    "glucosa": GLUCOSE,
    "orina": URINE,
    "peso y cintura": ["bmi", "waist"],
    "manguito": ["sbp", "dbp"],
    "antecedentes familiares": ["family_diabetes"],
}
FASTING_HOURS = 8.0
DIABETES_FASTING_GLUCOSE = 126.0  # mg/dl en ayunas: criterio diagnóstico, que exige confirmación


@dataclass
class GlucoseReading:
    """Glucosa capilar medida en casa con un glucómetro."""

    date: date
    mg_dl: float
    fasting_hours: float = 8.0  # horas desde la última comida


def summarize_glucose(readings: list[GlucoseReading]) -> tuple[float, float] | None:
    """Glucosa y horas de ayuno que se pasan al modelo.

    Si hay lecturas en ayunas (8 horas o más) se usa su media geométrica, que reduce el error
    del glucómetro; si no, la lectura más reciente.
    """
    if not readings:
        return None
    fasting = [r for r in readings if r.fasting_hours >= FASTING_HOURS]
    if fasting:
        value = float(np.exp(np.mean([np.log(r.mg_dl) for r in fasting])))
        return value, float(np.clip(np.mean([r.fasting_hours for r in fasting]), 0.0, 24.0))
    last = max(readings, key=lambda r: r.date)
    return float(last.mg_dl), float(np.clip(last.fasting_hours, 0.0, 24.0))


def fasting_days_above(readings: list[GlucoseReading], threshold: float = DIABETES_FASTING_GLUCOSE) -> int:
    """Días distintos con glucosa en ayunas por encima del umbral."""
    return len({r.date for r in readings if r.fasting_hours >= FASTING_HOURS and r.mg_dl >= threshold})


def load_diabetes(base_dir: Path = BASE_DIR, seed: int = 0) -> pd.DataFrame:
    """Adultos de NHANES 2005-2018 con HbA1c, glucosa y horas de ayuno.

    Añade a la cohorte: ``glucose`` (mg/dl, de laboratorio), ``glucose_home`` (la misma con el
    error de un glucómetro), ``fasting_hours``, ``family_diabetes`` (padres o hermanos),
    ``told_high_glucose`` (le han dicho que tiene prediabetes o riesgo de diabetes) y
    ``active`` (hace ejercicio moderado o intenso en su tiempo libre).
    """
    d = load_cohort(base_dir, cycles=CYCLES)
    extra = []
    for cycle in CYCLES:
        s, directory = SUFFIX[cycle], Path(base_dir) / cycle
        frame = read_xpt(f"BIOPRO{s}", directory)[["SEQN", "LBXSGL"]]
        for name in ("FASTQX", "MCQ", "DIQ", "PAQ"):
            frame = frame.merge(read_xpt(f"{name}{s}", directory), on="SEQN", how="outer", suffixes=("", "_dup"))
        out = pd.DataFrame({"seqn": frame.SEQN.astype(int).to_numpy()})
        out["glucose"] = _col(frame, "LBXSGL")
        out["fasting_hours"] = np.clip(_col(frame, "PHAFSTHR") + np.nan_to_num(_col(frame, "PHAFSTMN")) / 60.0, 0.0, 24.0)
        out["family_diabetes"] = _yes_no(_col(frame, "MCQ300C"))
        told = np.fmax(_yes_no(_col(frame, "DIQ160")), _yes_no(_col(frame, "DIQ170")))
        out["told_high_glucose"] = told
        # Actividad en el tiempo libre: en 2005-2006 se pregunta por los últimos 30 días; después, por una semana normal.
        vigorous, moderate = _col(frame, "PAQ650", "PAD200"), _col(frame, "PAQ665", "PAD320")
        out["active"] = np.where((vigorous == 1) | (moderate == 1), 1.0, np.where(np.isfinite(vigorous) | np.isfinite(moderate), 0.0, np.nan))
        extra.append(out)
    d = d.merge(pd.concat(extra, ignore_index=True), on="seqn", how="left")
    rng = np.random.default_rng(seed)
    d["glucose_home"] = d.glucose * np.exp(METER_LOG_SD * rng.standard_normal(len(d)))
    return d


def findrisc(d: pd.DataFrame) -> np.ndarray:
    """Puntuación FINDRISC (Lindström y Tuomilehto, 2003), sin la pregunta de fruta y verdura.

    NHANES no tiene esa pregunta, que vale como mucho 1 punto de 26. "Glucosa alta alguna vez"
    se toma de que le hayan dicho que tiene prediabetes o riesgo de diabetes; los antecedentes
    familiares son de padres o hermanos (5 puntos).
    """
    age, bmi, waist = d.age.to_numpy(), d.bmi.to_numpy(), d.waist.to_numpy()
    female = d.female.to_numpy() == 1
    points = np.select([age < 45, age < 55, age < 65], [0, 2, 3], default=4).astype(float)
    points += np.select([bmi < 25, bmi <= 30], [0, 1], default=3)
    points += np.where(female, np.select([waist < 80, waist <= 88], [0, 3], default=4), np.select([waist < 94, waist <= 102], [0, 3], default=4))
    points += np.where(d.active.to_numpy() == 1, 0, 2)
    points += np.where(d.bp_meds.to_numpy() == 1, 2, 0)
    high_glucose = (d.told_high_glucose.to_numpy() == 1) | (d.dx_prediabetes.to_numpy() == 1)
    points += np.where(high_glucose, 5, 0)
    points += np.where(d.family_diabetes.to_numpy() == 1, 5, 0)
    return np.where(np.isfinite(bmi) & np.isfinite(waist), points, np.nan)


def undiagnosed(d: pd.DataFrame) -> np.ndarray:
    """Sin diabetes diagnosticada ni tratamiento para la glucosa."""
    return ((d.dx_diabetes != 1) & (d.insulin != 1) & (d.diabetes_pills != 1)).to_numpy()
