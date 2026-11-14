"""Muestra del ensayo español PREDIMED: validación externa en españoles con eventos no mortales.

6.324 participantes (el 85 % del ensayo, elegido al azar) de alto riesgo cardiovascular y sin
enfermedad cardiovascular al entrar, reclutados en atención primaria en España desde 2003 y
seguidos hasta 2010. Desenlace: infarto, ictus o muerte cardiovascular. Viene como ejemplo en
el paquete de R compareGroups (Estruch et al., N Engl J Med 2013).

Tiene pocas variables: no hay tensión, colesterol, orina ni síntomas, solo diagnósticos, tabaco,
peso y cintura. Sirve para comprobar si un modelo entrenado con muertes en EE. UU. ordena bien
el riesgo en españoles, con eventos no mortales incluidos.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .rdata import read_rda

PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "predimed" / "predimed.rda"
# Predictores que PREDIMED comparte con la cohorte de NHANES.
SHARED = ["age", "female", "bmi", "waist", "dx_diabetes", "dx_hypertension", "dx_high_cholesterol", "smoker_now", "smoker_ever"]


def load_predimed(path: Path = PATH) -> pd.DataFrame:
    """La muestra con los nombres de la cohorte: predictores de ``SHARED``, ``family_history``
    (enfermedad coronaria precoz en la familia), ``group`` (rama del ensayo), ``years`` de
    seguimiento y ``event`` (infarto, ictus o muerte cardiovascular)."""
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
    """Columnas de seguimiento con el formato de ``outcomes.model`` (meses, muerte, causa)."""
    out = d.copy()
    out["months"] = d.years * 12.0
    out["dead"] = d.event.astype(float)
    out["cause"] = np.where(d.event, 1.0, np.nan)
    return out
