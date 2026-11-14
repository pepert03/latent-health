"""Regresión distribucional por tramos.

Para cada variable se parte su rango en tramos (cuantiles del entrenamiento más los
umbrales clínicos, para que las probabilidades en esos umbrales sean exactas) y un
clasificador de gradient boosting predice la probabilidad de cada tramo. Dentro de cada
tramo se asume reparto uniforme. Así se obtiene la distribución completa de la variable:
mediana, intervalos y P(variable < umbral), sin suponer que sea normal.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier


class BinnedDistributionRegressor:
    def __init__(self, thresholds=(), n_bins: int = 24, random_state: int = 0, **hgb_kwargs):
        self.thresholds = tuple(thresholds)
        self.n_bins = n_bins
        self.hgb_kwargs = {
            "max_iter": 400,
            "learning_rate": 0.05,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 30,
            "l2_regularization": 1.0,
            "early_stopping": True,
            "validation_fraction": 0.15,
            "n_iter_no_change": 25,
            "random_state": random_state,
            **hgb_kwargs,
        }

    def fit(self, X, y) -> "BinnedDistributionRegressor":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        keep = np.isfinite(y)
        X, y = X[keep], y[keep]
        self.lo_, self.hi_ = float(np.quantile(y, 0.0005)), float(np.quantile(y, 0.9995))
        quantile_edges = np.quantile(y, np.linspace(0, 1, self.n_bins + 1)[1:-1])
        edges = np.unique(np.concatenate([quantile_edges, [t for t in self.thresholds if self.lo_ < t < self.hi_]]))
        min_gap = 1e-3 * (self.hi_ - self.lo_)
        edges = edges[np.r_[True, np.diff(edges) > min_gap]]
        self.edges_ = edges
        labels = np.searchsorted(edges, y, side="right")
        self.n_classes_ = len(edges) + 1
        self.clf_ = HistGradientBoostingClassifier(**self.hgb_kwargs).fit(X, labels)
        return self

    def predict_pmf(self, X) -> np.ndarray:
        proba = self.clf_.predict_proba(np.asarray(X, dtype=float))
        pmf = np.zeros((proba.shape[0], self.n_classes_))
        pmf[:, self.clf_.classes_] = proba
        return pmf

    @property
    def bin_bounds(self) -> np.ndarray:
        """Límites de los tramos: [lo, e1, ..., ek, hi]."""
        return np.concatenate([[self.lo_], self.edges_, [self.hi_]])

    def cdf(self, X, t, pmf=None) -> np.ndarray:
        """P(Y ≤ t) para cada fila; ``t`` puede ser un escalar o un array (una por fila)."""
        pmf = self.predict_pmf(X) if pmf is None else pmf
        bounds = self.bin_bounds
        t = np.broadcast_to(np.asarray(t, dtype=float), (pmf.shape[0],))
        frac = np.clip((t[:, None] - bounds[None, :-1]) / np.diff(bounds)[None, :], 0.0, 1.0)
        return (pmf * frac).sum(axis=1)

    def quantiles(self, X, qs, pmf=None) -> np.ndarray:
        """Cuantiles (N, len(qs)) interpolando la función de distribución por tramos."""
        pmf = self.predict_pmf(X) if pmf is None else pmf
        bounds = self.bin_bounds
        cum = np.concatenate([np.zeros((pmf.shape[0], 1)), np.cumsum(pmf, axis=1)], axis=1)
        out = np.empty((pmf.shape[0], len(qs)))
        for i in range(pmf.shape[0]):
            out[i] = np.interp(qs, cum[i], bounds)
        return out

    def mean(self, X, pmf=None) -> np.ndarray:
        pmf = self.predict_pmf(X) if pmf is None else pmf
        bounds = self.bin_bounds
        return pmf @ ((bounds[:-1] + bounds[1:]) / 2.0)

    def crps(self, X, y, pmf=None, n_grid: int = 400) -> np.ndarray:
        """CRPS de cada observación (misma unidad que la variable; más bajo es mejor)."""
        pmf = self.predict_pmf(X) if pmf is None else pmf
        y = np.asarray(y, dtype=float)
        grid = np.linspace(min(self.lo_, np.nanmin(y)), max(self.hi_, np.nanmax(y)), n_grid)
        bounds = self.bin_bounds
        frac = np.clip((grid[None, :, None] - bounds[None, None, :-1]) / np.diff(bounds)[None, None, :], 0, 1)
        F = (pmf[:, None, :] * frac).sum(axis=2)  # (N, n_grid)
        step = (grid[None, :] >= y[:, None]).astype(float)
        return ((F - step) ** 2).sum(axis=1) * (grid[1] - grid[0])
