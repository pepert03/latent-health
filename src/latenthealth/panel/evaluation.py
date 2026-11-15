"""Metrics for evaluating the panel's predicted distributions.

Result keys of ``evaluate`` are kept in Spanish: scripts/fit_panel.py looks them up by name.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score

from .model import BinnedDistributionRegressor


def event_probability(model, X, d, decision, pmf=None):
    """Predicted probability and threshold of a decision ``(label, threshold(d), below)``."""
    label, thr, below = decision
    pmf = model.predict_pmf(X) if pmf is None else pmf
    t = np.broadcast_to(np.asarray(thr(d), dtype=float), (pmf.shape[0],))
    p_below = model.cdf(X, t, pmf=pmf)
    return (p_below if below else 1.0 - p_below), t


def evaluate(model, X, d, y, decisions) -> dict:
    pmf = model.predict_pmf(X)
    q = model.quantiles(X, [0.1, 0.5, 0.9], pmf=pmf)
    med = q[:, 1]
    res = {
        "R² (mediana)": 1 - np.mean((y - med) ** 2) / np.var(y),
        "Error absoluto medio": np.mean(np.abs(y - med)),
        "CRPS": float(np.mean(model.crps(X, y, pmf=pmf))),
        "Cobertura 80 %": np.mean((y >= q[:, 0]) & (y <= q[:, 2])),
        "Anchura 80 %": np.mean(q[:, 2] - q[:, 0]),
    }
    for decision in decisions:
        label, _, below = decision
        p, t = event_probability(model, X, d, decision, pmf=pmf)
        event = (y < t) if below else (y >= t)
        res[f"{label}: AUC"] = roc_auc_score(event, p) if 0 < event.sum() < len(event) else np.nan
        res[f"{label}: Brier"] = brier_score_loss(event, p)
        res[f"{label}: prevalencia / media predicha"] = f"{event.mean():.1%} / {p.mean():.1%}"
    return res


def marginal_crps(y_train, y_test, n_bins: int = 24) -> float:
    """CRPS of always predicting the population distribution (ignoring the patient)."""
    m = BinnedDistributionRegressor()
    m.lo_, m.hi_ = float(np.quantile(y_train, 0.0005)), float(np.quantile(y_train, 0.9995))
    m.edges_ = np.unique(np.quantile(y_train, np.linspace(0, 1, n_bins + 1)[1:-1]))
    m.n_classes_ = len(m.edges_) + 1
    counts = np.bincount(np.searchsorted(m.edges_, y_train, side="right"), minlength=m.n_classes_)
    pmf = np.tile(counts / counts.sum(), (len(y_test), 1))
    return float(np.mean(m.crps(None, y_test, pmf=pmf)))


def fmt(v) -> str:
    if isinstance(v, str):
        return v
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:.3f}" if abs(v) < 10 else f"{v:.1f}"
