"""Recalibración de los priors a atención primaria española.

Los modelos se ajustaron con NHANES (EE. UU.). El modelo de **medida** de la orina (tipo de
muestra, ruido, elevaciones) debería valer igual aquí; lo que cambia es la **población**:
cuánta albuminuria y cuánto filtrado bajo hay antes de medir. Eso se corrige moviendo solo los
interceptos, sin reentrenar:

- **Albuminuria:** se suma una constante al logit de las componentes elevadas del prior
  (``AlbuminuriaParams.prior_logit_offset``) hasta que la proporción de muestras ≥ 30 mg/g que
  predice el modelo coincide con la observada.
- **Filtrado glomerular:** se mueve el intercepto del suceso "FG < 60" en la distribución del
  panel (``shift_below``) hasta que su proporción coincide con la observada.

Referencia: estudio ONDAAS (Clin Kidney J 2025;18:sfaf123; Burgos, febrero-mayo de 2024):
adultos a los que su médico de familia pidió una analítica. La población de comparación es
NHANES repesada a su reparto por edad y sexo.

Cautelas, todas recogidas en el informe que genera ``scripts/fit_recalibration.py``:
- ONDAAS no es todo el cupo: son pacientes a los que se pidió analítica (más enfermos).
- No dice si la orina era la primera de la mañana; se recogió en el centro. Se asume muestra
  aleatoria y se da también el resultado si fuera primera de la mañana.
- Usó CKD-EPI 2009; aquí se usa la de 2021, que da valores algo más altos. El objetivo de
  FG < 60 se traduce a la escala de 2021 persona a persona.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from .albuminuria.model import RANDOM, AlbuminuriaParams, log_prior, make_grid, new_sample_survival
from .egfr import ckd_epi_2021

RECALIBRATION_PATH = Path(__file__).resolve().parents[2] / "models" / "recalibracion_espana.json"

ONDAAS = {
    "fuente": "ONDAAS, Clin Kidney J 2025;18(5):sfaf123 (Burgos, febrero-mayo de 2024)",
    "poblacion": "adultos (≥ 18 años) a los que su médico de familia pidió una analítica",
    "n": 9526,
    "albuminuria": 0.1404,  # UACR ≥ 30 mg/g en una sola muestra
    "a2": 0.130,
    "a3": 0.011,
    "fg_menor_60": 0.128,  # con CKD-EPI 2009
    "g": {"G1": 0.364, "G2": 0.508, "G3a": 0.083, "G3b": 0.036, "G4": 0.009, "G5": 0.0003},
    "mujeres": 0.58,
    # Personas con UACR por grupo de edad y cuántas tenían albuminuria (tabla 3 del artículo).
    "edad": {"18-44": (1533, 46), "45-64": (3370, 275), "65+": (4937, 1016)},
}
AGE_GROUPS = (("18-44", 0, 45), ("45-64", 45, 65), ("65+", 65, 200))


def age_group(age) -> np.ndarray:
    age = np.asarray(age, dtype=float)
    return np.select([age < 45, age < 65], [0, 1], default=2)


def reference_weights(age, female, target=ONDAAS, iterations: int = 50) -> np.ndarray:
    """Pesos que dan a una muestra el reparto por edad y sexo de la población de referencia."""
    group = age_group(age)
    female = np.asarray(female, dtype=bool)
    counts = np.array([target["edad"][name][0] for name, _, _ in AGE_GROUPS], dtype=float)
    age_share = counts / counts.sum()
    w = np.ones(group.size)
    for _ in range(iterations):  # ajuste proporcional iterativo sobre las dos marginales
        for g in range(3):
            w[group == g] *= age_share[g] / w[group == g].sum() * w.sum()
        for sex, share in ((True, target["mujeres"]), (False, 1.0 - target["mujeres"])):
            w[female == sex] *= share / w[female == sex].sum() * w.sum()
    return w / w.sum()


def sample_prevalence(params: AlbuminuriaParams, Z: np.ndarray, sample_type: str, grid_n: int = 200) -> np.ndarray:
    """P(una muestra de ese tipo salga ≥ 30 mg/g) de cada persona antes de medirle nada, (N,)."""
    x, _ = make_grid(grid_n)
    lp = log_prior(params, Z, x)
    prior = np.exp(lp - lp.max(axis=1, keepdims=True))
    prior /= prior.sum(axis=1, keepdims=True)
    return (prior * new_sample_survival(params, Z, sample_type, np.log(30.0), x)).sum(axis=1)


def fit_prior_offset(params: AlbuminuriaParams, Z, weights, target: float, sample_type: str = RANDOM) -> float:
    """Constante del prior que iguala la proporción de muestras ≥ 30 predicha con la observada."""

    def gap(offset: float) -> float:
        p = sample_prevalence(replace(params, prior_logit_offset=offset), Z, sample_type)
        return float(weights @ p) - target

    return float(brentq(gap, -4.0, 4.0, xtol=1e-4))


def egfr_2009_cut_in_2021_scale(age, female, cut: float = 60.0) -> np.ndarray:
    """FG de 2021 que tiene quien da justo ``cut`` con la ecuación de 2009 (misma creatinina)."""
    age = np.asarray(age, dtype=float)
    female = np.asarray(female, dtype=bool)
    kappa = np.where(female, 0.7, 0.9)
    # CKD-EPI 2009 sin el término de raza, para creatinina por encima de κ (siempre a FG 60 en adultos).
    creatinine = kappa * (141.0 * 0.993**age * np.where(female, 1.018, 1.0) / cut) ** (1.0 / 1.209)
    return ckd_epi_2021(creatinine, age, female)


def shift_below(pmf, bounds, cut: float, delta: float) -> np.ndarray:
    """Mueve el intercepto del suceso "valor < corte": multiplica su odds por exp(δ).

    Los tramos por debajo del corte se multiplican por exp(δ) y se renormaliza. El reparto
    dentro de cada lado no cambia. ``cut`` debe ser un límite de tramo (los umbrales clínicos lo son).
    """
    pmf = np.atleast_2d(np.asarray(pmf, dtype=float))
    below = np.asarray(bounds[1:], dtype=float) <= cut + 1e-9
    w = pmf * np.where(below, np.exp(delta), 1.0)[None, :]
    return w / w.sum(axis=1, keepdims=True)


def cdf_from_pmf(pmf, bounds, t) -> np.ndarray:
    """P(Y ≤ t) con reparto uniforme dentro de cada tramo; ``t`` es un escalar o un valor por fila."""
    pmf = np.atleast_2d(pmf)
    bounds = np.asarray(bounds, dtype=float)
    t = np.broadcast_to(np.asarray(t, dtype=float), (pmf.shape[0],))
    frac = np.clip((t[:, None] - bounds[None, :-1]) / np.diff(bounds)[None, :], 0.0, 1.0)
    return (pmf * frac).sum(axis=1)


def fit_shift(pmf, bounds, cut: float, cuts, weights, target: float) -> float:
    """δ que iguala la proporción predicha por debajo de ``cuts`` (uno por persona) con la observada."""

    def gap(delta: float) -> float:
        return float(weights @ cdf_from_pmf(shift_below(pmf, bounds, cut, delta), bounds, cuts)) - target

    return float(brentq(gap, -5.0, 5.0, xtol=1e-4))


def load_recalibration(path: Path = RECALIBRATION_PATH) -> dict | None:
    """Lo que guardó ``scripts/fit_recalibration.py``, o None si aún no se ha ejecutado."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
