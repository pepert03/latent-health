"""Riesgo de muerte cardiovascular de un paciente con lo que ha medido en casa.

Usa el modelo entrenado por ``scripts/fit_outcomes.py`` con desenlaces reales. Admite que
falten datos: da la mejor estimación con lo que haya y dice qué faltaría por contestar o medir.

El riesgo absoluto es el de la población con la que se entrenó (EE. UU.). Para un paciente
español lo que se traslada es el **riesgo relativo**: cuántas veces el de alguien de su edad y
sexo. Es lo que se enseña primero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "outcomes"
# Lo que el paciente puede aportar desde casa, con el nombre con que se le pide.
HOME_ITEMS = {
    "health": "salud percibida",
    "dyspnea": "falta de aire al subir cuestas",
    "walk_difficulty": "dificultad para caminar 400 metros",
    "stairs_difficulty": "dificultad para subir 10 escalones",
    "hospitalized": "ingreso en el último año",
    "bmi": "peso y talla",
    "waist": "cintura",
    "sbp": "tensión",
    "pulse": "pulso",
    "log_uacr": "orina",
}


@dataclass
class HomeRisk:
    risk: float  # P(muerte por corazón o ictus en 10 años), población de entrenamiento
    reference: float  # la de alguien de su edad y sexo
    missing: list[str] = field(default_factory=list)  # datos de casa que faltan

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
    """Riesgo con los predictores disponibles (los que falten, como NaN). None si no hay modelos."""
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
    ratio = f"{r.ratio:.1f}".replace(".", ",")
    lines = [
        f"Muerte por corazón o ictus en 10 años: {ratio} veces la de alguien de su edad y sexo",
        f"Riesgo absoluto del modelo (población de EE. UU., sin recalibrar a España): {r.risk:.0%}; de su edad y sexo: {r.reference:.0%}",
    ]
    if r.missing:
        lines.append("Faltan por contestar o medir: " + ", ".join(r.missing) + ".")
    return "\n".join(lines)
