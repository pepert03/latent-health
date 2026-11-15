"""Metrics for comparing risk models against real outcomes."""

from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def auc(event, score) -> float:
    """Area under the ROC curve: probability that a case scores higher than a non-case."""
    event = np.asarray(event, dtype=bool)
    n1, n0 = int(event.sum()), int((~event).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = rankdata(score)
    return float((ranks[event].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def bootstrap_auc(event, scores: dict[str, np.ndarray], n: int = 500, seed: int = 0) -> dict[str, np.ndarray]:
    """AUC of several models on the same bootstrap resamples (for paired comparison)."""
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
    """Mean AUC difference (a - b) with its 95% bootstrap interval."""
    diff = samples_a - samples_b
    lo, hi = np.nanpercentile(diff, [2.5, 97.5])
    return float(np.nanmean(diff)), float(lo), float(hi)


def c_index(months, event, score) -> float:
    """Harrell's concordance index with censoring.

    Over each person with the event and everyone still followed up for longer, the share of
    pairs in which the model gives more risk to the one with the earlier event.
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
    """Equal-size groups by predicted risk: (people, mean predicted risk, observed)."""
    event = np.asarray(event, dtype=float)
    risk = np.asarray(risk, dtype=float)
    order = np.argsort(risk)
    return [(len(g), float(risk[g].mean()), float(event[g].mean())) for g in np.array_split(order, bins)]


def capture(event, score, share: float) -> tuple[float, float]:
    """In the top ``share`` by risk: event rate, and fraction of all events captured."""
    event = np.asarray(event, dtype=bool)
    k = max(int(round(share * event.size)), 1)
    top = np.argsort(-np.asarray(score, dtype=float), kind="stable")[:k]
    return float(event[top].mean()), float(event[top].sum() / max(event.sum(), 1))
