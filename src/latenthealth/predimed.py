"""Sample of the Spanish PREDIMED trial: external validation in Spaniards with non-fatal events.

6,324 participants (a random 85% of the trial) at high cardiovascular risk and free of
cardiovascular disease at entry, recruited in Spanish primary care from 2003 and followed up
to 2010. Outcome: myocardial infarction, stroke or cardiovascular death. Shipped as an example
in the R package compareGroups (Estruch et al., N Engl J Med 2013).

Few variables: no blood pressure, cholesterol, urine or symptoms, only diagnoses, smoking,
weight and waist. Used to check whether a model trained on US deaths ranks risk well in
Spaniards, non-fatal events included.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .rdata import read_rda

PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "predimed" / "predimed.rda"
# Predictors PREDIMED shares with the NHANES cohort.
SHARED = ["age", "female", "bmi", "waist", "dx_diabetes", "dx_hypertension", "dx_high_cholesterol", "smoker_now", "smoker_ever"]


def load_predimed(path: Path = PATH) -> pd.DataFrame:
    """The sample with cohort column names: ``SHARED`` predictors, ``family_history``
    (premature coronary disease in the family), ``group`` (trial arm), ``years`` of
    follow-up and ``event`` (myocardial infarction, stroke or cardiovascular death)."""
    raw = read_rda(path)["predimed"]
    yes = lambda column: (raw[column].astype(str) == "Yes").to_numpy(float)  # noqa: E731
    smoke = raw.smoke.astype(str)
    return pd.DataFrame(
        {
            "age": raw.age.to_numpy(float),
            "female": (raw.sex.astype(str) == "Female").to_numpy(float),
            "bmi": raw.bmi.to_numpy(float),
            "waist": raw.waist.to_numpy(float),
            "dx_diabetes": yes("diab"),
            "dx_hypertension": yes("htn"),
            "dx_high_cholesterol": yes("hyperchol"),
            "smoker_now": (smoke == "Current").to_numpy(float),
            "smoker_ever": smoke.isin(["Current", "Former"]).to_numpy(float),
            "family_history": yes("famhist"),
            "group": raw.group.astype(str).to_numpy(),
            "years": raw.toevent.to_numpy(float),
            "event": (raw.event.astype(str) == "Yes").to_numpy(),
        }
    )


def as_followup(d: pd.DataFrame) -> pd.DataFrame:
    """Follow-up columns in the ``outcomes.model`` format (months, death, cause)."""
    out = d.copy()
    out["months"] = d.years * 12.0
    out["dead"] = d.event.astype(float)
    out["cause"] = np.where(d.event, 1.0, np.nan)
    return out
