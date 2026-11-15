"""A patient's risk of cardiovascular death from what they measured at home.

Uses the model trained by ``scripts/fit_outcomes.py`` on real outcomes. Tolerates missing
data: gives the best estimate with what is available and says what is left to answer or measure.

The absolute risk is that of the training population (US). For a Spanish patient what
transfers is the **relative risk**: how many times that of someone of the same age and sex.
That is what is shown first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..i18n import Labels, t

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "outcomes"
# What the patient can provide from home, with the name used to ask for it (es, en).
HOME_ITEMS = Labels(
    {
        "health": ("salud percibida", "self-rated health"),
        "dyspnea": ("falta de aire al subir cuestas", "shortness of breath walking uphill"),
        "walk_difficulty": ("dificultad para caminar 400 metros", "difficulty walking 400 meters"),
        "stairs_difficulty": ("dificultad para subir 10 escalones", "difficulty climbing 10 steps"),
        "hospitalized": ("ingreso en el último año", "hospital admission in the last year"),
        "bmi": ("peso y talla", "weight and height"),
        "waist": ("cintura", "waist"),
        "sbp": ("tensión", "blood pressure"),
        "pulse": ("pulso", "pulse"),
        "log_uacr": ("orina", "urine"),
    }
)


@dataclass
class HomeRisk:
    risk: float  # P(death from heart disease or stroke in 10 years), training population
    reference: float  # same for someone of the same age and sex
    missing: list[str] = field(default_factory=list)  # missing home data

    @property
    def ratio(self) -> float:
        return self.risk / self.reference if self.reference > 0 else float("nan")


@lru_cache(maxsize=None)
def _model(name: str):
    path = MODELS_DIR / f"muerte_cardiovascular__{name}.joblib"
    return joblib.load(path) if path.exists() else None


def available() -> bool:
    return _model("casa") is not None and _model("edad_y_sexo") is not None


def home_risk(features: dict) -> HomeRisk | None:
    """Risk from the available predictors (missing ones as NaN). None if no models are present."""
    if not available():
        return None
    row = pd.DataFrame([features])
    home, reference = _model("casa"), _model("edad_y_sexo")
    for name in home["features"]:
        if name not in row:
            row[name] = np.nan
    risk = float(home["model"].risk(row)[0])
    base = float(reference["model"].risk(row)[0])
    missing = [label for key, label in HOME_ITEMS.items() if not np.isfinite(row[key].iloc[0])]
    return HomeRisk(risk, base, missing)


def describe(r: HomeRisk) -> str:
    ratio_es = f"{r.ratio:.1f}".replace(".", ",")
    lines = [
        t(
            f"Muerte por corazón o ictus en 10 años: {ratio_es} veces la de alguien de su edad y sexo",
            f"Death from heart disease or stroke in 10 years: {r.ratio:.1f} times that of someone of the same age and sex",
        ),
        t(
            f"Riesgo absoluto del modelo (población de EE. UU., sin recalibrar a España): {r.risk:.0%}; de su edad y sexo: {r.reference:.0%}",
            f"Absolute model risk (US population, not recalibrated to Spain): {r.risk:.0%}; same age and sex: {r.reference:.0%}",
        ),
    ]
    if r.missing:
        lines.append(t("Faltan por contestar o medir: ", "Still to answer or measure: ") + ", ".join(r.missing) + ".")
    return "\n".join(lines)
