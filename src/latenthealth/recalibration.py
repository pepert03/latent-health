"""Recalibration of the priors to Spanish primary care.

The models were fitted on NHANES (US). The urine **measurement** model (sample type, noise,
transient elevations) should hold here too; what changes is the **population**: how much
albuminuria and low eGFR there is before measuring. That is corrected by moving only the
intercepts, without retraining:

- **Albuminuria:** a constant is added to the logit of the elevated prior components
  (``AlbuminuriaParams.prior_logit_offset``) until the predicted share of samples >= 30 mg/g
  matches the observed one.
- **eGFR:** the intercept of the event "eGFR < 60" in the panel distribution is shifted
  (``shift_below``) until its share matches the observed one.

Reference: the ONDAAS study (Clin Kidney J 2025;18:sfaf123; Burgos, February-May 2024):
adults whose family doctor ordered blood work. The comparison population is NHANES
reweighted to its age and sex mix.

Caveats, all listed in the report produced by ``scripts/fit_recalibration.py``:
- ONDAAS is not the whole practice list: these are patients sent for blood work (sicker).
- It does not say whether urine was first-morning; it was collected at the health center.
  A random sample is assumed, and the first-morning result is also given.
- It used CKD-EPI 2009; here the 2021 equation is used, which gives somewhat higher values.
  The eGFR < 60 target is translated to the 2021 scale person by person.
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
    "fuente": "ONDAAS, Clin Kidney J 2025;18(5):sfaf123 (Burgos, February-May 2024)",
    "poblacion": "adults (>= 18 years) whose family doctor ordered blood work",
    "n": 9526,
    "albuminuria": 0.1404,  # UACR >= 30 mg/g in a single sample
    "a2": 0.130,
    "a3": 0.011,
    "fg_menor_60": 0.128,  # with CKD-EPI 2009
    "g": {"G1": 0.364, "G2": 0.508, "G3a": 0.083, "G3b": 0.036, "G4": 0.009, "G5": 0.0003},
    "mujeres": 0.58,
    # People with UACR per age group and how many had albuminuria (table 3 of the paper).
    "edad": {"18-44": (1533, 46), "45-64": (3370, 275), "65+": (4937, 1016)},
}
AGE_GROUPS = (("18-44", 0, 45), ("45-64", 45, 65), ("65+", 65, 200))


def age_group(age) -> np.ndarray:
    age = np.asarray(age, dtype=float)
    return np.select([age < 45, age < 65], [0, 1], default=2)


def reference_weights(age, female, target=ONDAAS, iterations: int = 50) -> np.ndarray:
    """Weights that give a sample the age and sex mix of the reference population."""
    group = age_group(age)
    female = np.asarray(female, dtype=bool)
    counts = np.array([target["edad"][name][0] for name, _, _ in AGE_GROUPS], dtype=float)
    age_share = counts / counts.sum()
    w = np.ones(group.size)
    for _ in range(iterations):  # iterative proportional fitting over the two margins
        for g in range(3):
            w[group == g] *= age_share[g] / w[group == g].sum() * w.sum()
        for sex, share in ((True, target["mujeres"]), (False, 1.0 - target["mujeres"])):
            w[female == sex] *= share / w[female == sex].sum() * w.sum()
    return w / w.sum()


def sample_prevalence(params: AlbuminuriaParams, Z: np.ndarray, sample_type: str, grid_n: int = 200) -> np.ndarray:
    """P(a sample of that type reads >= 30 mg/g) for each person before any measurement, (N,)."""
    x, _ = make_grid(grid_n)
    lp = log_prior(params, Z, x)
    prior = np.exp(lp - lp.max(axis=1, keepdims=True))
    prior /= prior.sum(axis=1, keepdims=True)
    return (prior * new_sample_survival(params, Z, sample_type, np.log(30.0), x)).sum(axis=1)


def fit_prior_offset(params: AlbuminuriaParams, Z, weights, target: float, sample_type: str = RANDOM) -> float:
    """Prior offset that matches the predicted share of samples >= 30 to the observed one."""

    def gap(offset: float) -> float:
        p = sample_prevalence(replace(params, prior_logit_offset=offset), Z, sample_type)
        return float(weights @ p) - target

    return float(brentq(gap, -4.0, 4.0, xtol=1e-4))


def egfr_2009_cut_in_2021_scale(age, female, cut: float = 60.0) -> np.ndarray:
    """2021 eGFR of someone at exactly ``cut`` with the 2009 equation (same creatinine)."""
    age = np.asarray(age, dtype=float)
    female = np.asarray(female, dtype=bool)
    kappa = np.where(female, 0.7, 0.9)
    # CKD-EPI 2009 without the race term, for creatinine above kappa (always so at eGFR 60 in adults).
    creatinine = kappa * (141.0 * 0.993**age * np.where(female, 1.018, 1.0) / cut) ** (1.0 / 1.209)
    return ckd_epi_2021(creatinine, age, female)


def shift_below(pmf, bounds, cut: float, delta: float) -> np.ndarray:
    """Shift the intercept of the event "value < cut": multiply its odds by exp(delta).

    Bins below the cut are multiplied by exp(delta) and renormalized. The split within each
    side is unchanged. ``cut`` must be a bin edge (clinical thresholds are).
    """
    pmf = np.atleast_2d(np.asarray(pmf, dtype=float))
    below = np.asarray(bounds[1:], dtype=float) <= cut + 1e-9
    w = pmf * np.where(below, np.exp(delta), 1.0)[None, :]
    return w / w.sum(axis=1, keepdims=True)


def cdf_from_pmf(pmf, bounds, t) -> np.ndarray:
    """P(Y <= t) assuming uniform mass within each bin; ``t`` is a scalar or one value per row."""
    pmf = np.atleast_2d(pmf)
    bounds = np.asarray(bounds, dtype=float)
    t = np.broadcast_to(np.asarray(t, dtype=float), (pmf.shape[0],))
    frac = np.clip((t[:, None] - bounds[None, :-1]) / np.diff(bounds)[None, :], 0.0, 1.0)
    return (pmf * frac).sum(axis=1)


def fit_shift(pmf, bounds, cut: float, cuts, weights, target: float) -> float:
    """delta that matches the predicted share below ``cuts`` (one per person) to the observed one."""

    def gap(delta: float) -> float:
        return float(weights @ cdf_from_pmf(shift_below(pmf, bounds, cut, delta), bounds, cuts)) - target

    return float(brentq(gap, -5.0, 5.0, xtol=1e-4))


def load_recalibration(path: Path = RECALIBRATION_PATH) -> dict | None:
    """What ``scripts/fit_recalibration.py`` saved, or None if it has not been run yet."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
