"""Métricas para comparar modelos de riesgo con desenlaces reales."""

from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def auc(event, score) -> float:
    """Área bajo la curva ROC: probabilidad de que un caso tenga más puntuación que un no caso."""
    event = np.asarray(event, dtype=bool)
    n1, n0 = int(event.sum()), int((~event).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = rankdata(score)
    return float((ranks[event].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def bootstrap_auc(event, scores: dict[str, np.ndarray], n: int = 500, seed: int = 0) -> dict[str, np.ndarray]:
    """AUC de varios modelos sobre las mismas remuestras (para comparar por parejas)."""
    rng = np.random.default_rng(seed)
    event = np.asarray(event, dtype=bool)
    out = {name: np.empty(n) for name in scores}
    size = event.size
    for b in range(n):
        idx = rng.integers(0, size, size)
        for name, s in scores.items():
            out[name][b] = auc(event[idx], np.asarray(s)[idx])
    return out


def difference_interval(samples_a: np.ndarray, samples_b: np.ndarray) -> tuple[float, float, float]:
    """Diferencia media de AUC (a - b) con su intervalo del 95 % por remuestreo."""
    diff = samples_a - samples_b
    lo, hi = np.nanpercentile(diff, [2.5, 97.5])
    return float(np.nanmean(diff)), float(lo), float(hi)


def c_index(months, event, score) -> float:
    """Índice de concordancia de Harrell con censura.

    Entre cada persona que sufre el suceso y todas las que seguían en seguimiento más tiempo,
    proporción de parejas en las que el modelo da más riesgo a la que lo sufre antes.
    """
    months = np.asarray(months, dtype=float)
    event = np.asarray(event, dtype=bool)
    score = np.asarray(score, dtype=float)
    concordant = comparable = 0.0
    for i in np.flatnonzero(event):
        later = months > months[i]
        comparable += later.sum()
        concordant += (score[i] > score[later]).sum() + 0.5 * (score[i] == score[later]).sum()
    return float(concordant / comparable) if comparable else float("nan")


def brier(event, risk) -> float:
    return float(np.mean((np.asarray(risk, dtype=float) - np.asarray(event, dtype=float)) ** 2))


def calibration_table(event, risk, bins: int = 10) -> list[tuple[int, float, float]]:
    """Por grupos de igual tamaño según el riesgo predicho: (personas, riesgo medio predicho, observado)."""
    event = np.asarray(event, dtype=float)
    risk = np.asarray(risk, dtype=float)
    order = np.argsort(risk)
    return [(len(g), float(risk[g].mean()), float(event[g].mean())) for g in np.array_split(order, bins)]


def capture(event, score, share: float) -> tuple[float, float]:
    """En el ``share`` de más riesgo: proporción con el suceso y parte de todos los sucesos que recoge."""
    event = np.asarray(event, dtype=bool)
    k = max(int(round(share * event.size)), 1)
    top = np.argsort(-np.asarray(score, dtype=float), kind="stable")[:k]
    return float(event[top].mean()), float(event[top].sum() / max(event.sum(), 1))
