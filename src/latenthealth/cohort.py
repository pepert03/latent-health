"""Test patients from NHANES: a panel row turned into a clinical record.

Used to validate the full assessment and the practice list on real people: the system gets
only what the doctor would have (history, and optionally a urine sample or part of the
blood panel) and is compared with what NHANES actually measured.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from .albuminuria import RANDOM, UrineSample
from .assessment import ClinicalRecord

SAMPLE_DATE = date(2010, 6, 1)  # fictitious NHANES sample date


def _flag(v) -> bool:
    return bool(v == 1)


def _value(v) -> float | None:
    return float(v) if np.isfinite(v) else None


def record_from_row(row, urine: bool = True, labs: tuple[str, ...] = (), censored: bool = False) -> ClinicalRecord:
    """Clinical record of one NHANES participant (a row of ``panel.load_panel``).

    ``urine`` adds their random urine sample; ``labs`` are the lab variables given as
    measured (e.g. ``("total_cholesterol", "hdl")``). Anything not given stays hidden.
    """
    record = ClinicalRecord(
        age=float(row.age),
        female=_flag(row.female),
        bmi=_value(row.bmi),
        waist=_value(row.waist),
        sbp=_value(row.sbp),
        dbp=_value(row.dbp),
        diabetes=_flag(row.dx_diabetes),
        prediabetes=_flag(row.dx_prediabetes),
        insulin=_flag(row.insulin),
        diabetes_pills=_flag(row.diabetes_pills),
        hypertension=_flag(row.dx_hypertension),
        bp_meds=_flag(row.bp_meds),
        high_cholesterol=_flag(row.dx_high_cholesterol),
        cholesterol_meds=_flag(row.cholesterol_meds),
        heart_failure=_flag(row.dx_heart_failure),
        coronary=_flag(row.dx_coronary),
        stroke=_flag(row.dx_stroke),
        kidney_disease=_flag(getattr(row, "dx_kidney", 0)),
        smoker_now=_flag(row.smoker_now),
        smoker_ever=_flag(row.smoker_ever),
    )
    if urine and np.isfinite(row.log_uacr):
        record.urine_samples = [
            UrineSample(
                SAMPLE_DATE,
                float(np.exp(row.log_uacr)),
                RANDOM,
                censored=censored,
                creatinine_mg_dl=float(np.exp(row.log_urine_creatinine)),
            )
        ]
    for name in labs:
        value = getattr(row, name)
        if np.isfinite(value):
            record.measured[name] = float(value)
    return record
