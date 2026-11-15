"""Undiagnosed diabetes: what a capillary glucose measured at home adds.

Today, to look for hidden diabetes without a lab test, Spain uses the FINDRISC questionnaire. A
glucose meter is cheap and the patient can repeat the reading. These are the data to compare
both on real people: NHANES 2005-2018, which has each person's blood glucose, how many hours
since they last ate and HbA1c (the reference: 6.5% or more is diabetes).

NHANES glucose is a lab value. To make it count as a meter reading, the error allowed by the
glucose meter standard is added (ISO 15197: 95% of readings within ±15%), i.e. an SD of 7.5%.
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
METER_LOG_SD = 0.075  # error of a home glucose meter (ISO 15197:2013)
DIABETES_HBA1C = 6.5

# What is already in the record (as in the blood panel) plus family history.
HISTORY = [
    "age", "female", "bmi", "waist", "sbp", "dbp", "dx_prediabetes", "dx_hypertension", "bp_meds",
    "dx_high_cholesterol", "cholesterol_meds", "dx_heart_failure", "dx_coronary", "dx_stroke",
    "smoker_now", "smoker_ever", "family_diabetes",
]  # fmt: skip
URINE = ["log_uacr", "log_urine_creatinine"]
GLUCOSE = ["glucose_home", "fasting_hours"]
# Predictor blocks; the keys are machine names used by the fitting scripts.
BLOCKS = {
    "glucosa": GLUCOSE,
    "orina": URINE,
    "peso y cintura": ["bmi", "waist"],
    "manguito": ["sbp", "dbp"],
    "antecedentes familiares": ["family_diabetes"],
}
FASTING_HOURS = 8.0
DIABETES_FASTING_GLUCOSE = 126.0  # fasting mg/dl: diagnostic criterion, needs confirmation


@dataclass
class GlucoseReading:
    """Capillary glucose measured at home with a meter."""

    date: date
    mg_dl: float
    fasting_hours: float = 8.0  # hours since the last meal


def summarize_glucose(readings: list[GlucoseReading]) -> tuple[float, float] | None:
    """Glucose and fasting hours passed to the model.

    If there are fasting readings (8 hours or more) their geometric mean is used, which reduces
    meter error; otherwise, the most recent reading.
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
    """Distinct days with fasting glucose above the threshold."""
    return len({r.date for r in readings if r.fasting_hours >= FASTING_HOURS and r.mg_dl >= threshold})


def load_diabetes(base_dir: Path = BASE_DIR, seed: int = 0) -> pd.DataFrame:
    """NHANES 2005-2018 adults with HbA1c, glucose and fasting hours.

    Adds to the cohort: ``glucose`` (mg/dl, lab), ``glucose_home`` (the same with glucose meter
    error), ``fasting_hours``, ``family_diabetes`` (parents or siblings),
    ``told_high_glucose`` (told they have prediabetes or diabetes risk) and ``active``
    (moderate or vigorous leisure-time exercise).
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
        # Leisure-time activity: 2005-2006 asks about the last 30 days; later cycles, about a typical week.
        vigorous, moderate = _col(frame, "PAQ650", "PAD200"), _col(frame, "PAQ665", "PAD320")
        out["active"] = np.where((vigorous == 1) | (moderate == 1), 1.0, np.where(np.isfinite(vigorous) | np.isfinite(moderate), 0.0, np.nan))
        extra.append(out)
    d = d.merge(pd.concat(extra, ignore_index=True), on="seqn", how="left")
    rng = np.random.default_rng(seed)
    d["glucose_home"] = d.glucose * np.exp(METER_LOG_SD * rng.standard_normal(len(d)))
    return d


def findrisc(d: pd.DataFrame) -> np.ndarray:
    """FINDRISC score (Lindström and Tuomilehto, 2003), without the fruit and vegetable question.

    NHANES lacks that question, worth at most 1 point out of 26. "High glucose ever" is taken
    from being told they have prediabetes or diabetes risk; family history is parents or
    siblings (5 points).
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
    """No diagnosed diabetes and no glucose-lowering treatment."""
    return ((d.dx_diabetes != 1) & (d.insulin != 1) & (d.diabetes_pills != 1)).to_numpy()
