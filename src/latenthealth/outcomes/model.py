"""Riesgo acumulado de morir por una causa, con peligros anuales (supervivencia en tiempo discreto).

Cada persona se convierte en una fila por año de seguimiento. Dos clasificadores estiman, para
cada año, la probabilidad de morir por la causa de interés y la de morir por cualquier otra
(riesgos competitivos). El riesgo a 10 años es la suma, año a año, de morir por la causa
habiendo sobrevivido hasta entonces:

    riesgo(H) = Σ_k  h_causa(k) · Π_{j<k} (1 - h_causa(j) - h_otra(j))

Ventajas frente a una ecuación de riesgo clásica:
- Aprovecha a quien tiene un seguimiento más corto (cuenta los años que sí se le observaron).
- Con gradient boosting admite predictores que faltan: **da la mejor estimación con lo que
  haya**, sea solo un cuestionario o todo el kit. No hace falta un modelo por combinación.
- No supone efectos lineales ni proporcionales.

``kind="linear"`` usa una regresión logística agrupada (equivale a una ecuación tipo Cox con
interacciones con la edad, como SCORE2) para reajustar las ecuaciones clásicas con los mismos datos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def person_periods(df: pd.DataFrame, causes: tuple[int, ...], horizon: int):
    """Filas persona-año. Devuelve (índice de la persona, año, etiqueta): 0 sobrevive el año,
    1 muere por la causa, 2 muere por otra. El año incompleto de quien sigue vivo se descarta."""
    years = df.months.to_numpy(float) / 12.0
    died = df.dead.to_numpy(float) == 1
    whole = np.floor(years).astype(int)
    survived = np.minimum(whole, horizon)  # años completos sobrevividos dentro del horizonte
    event_year = np.where(died & (whole < horizon), whole, -1)
    counts = survived + (event_year >= 0)
    person = np.repeat(np.arange(len(df)), counts)
    year = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    is_cause = df.cause.isin(causes).to_numpy()
    label = np.zeros(person.size, dtype=int)
    at_event = year == event_year[person]
    label[at_event] = np.where(is_cause[person[at_event]], 1, 2)
    return person, year, label


class HazardModel:
    """Riesgo acumulado por una causa a partir de los predictores disponibles."""

    def __init__(self, features, horizon: int = 10, kind: str = "boosting", age_interactions: bool = True, **params):
        self.features = list(features)
        self.horizon = horizon
        self.kind = kind
        self.age_interactions = age_interactions
        self.params = params

    def _matrix(self, df: pd.DataFrame, person: np.ndarray, year: np.ndarray) -> np.ndarray:
        X = df[self.features].to_numpy(float)[person]
        if self.kind == "linear" and self.age_interactions and "age" in self.features:
            age = X[:, [self.features.index("age")]]
            others = np.delete(X, self.features.index("age"), axis=1)
            X = np.hstack([X, age**2, age * others])
        return np.column_stack([X, year])

    def _estimator(self):
        if self.kind == "linear":
            return make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                StandardScaler(),
                LogisticRegression(C=1.0, max_iter=1000),
            )
        settings = {
            "learning_rate": 0.05,
            "max_iter": 500,
            "max_leaf_nodes": 8,
            "min_samples_leaf": 300,
            "l2_regularization": 1.0,
            "early_stopping": True,
            "validation_fraction": 0.1,
            "n_iter_no_change": 20,
            "random_state": 0,
            **self.params,
        }
        return HistGradientBoostingClassifier(**settings)

    def fit(self, df: pd.DataFrame, causes: tuple[int, ...]) -> "HazardModel":
        person, year, label = person_periods(df, causes, self.horizon)
        X = self._matrix(df, person, year)
        self.cause_ = self._estimator().fit(X, label == 1)
        self.other_ = self._estimator().fit(X, label == 2)
        self.causes_ = tuple(causes)
        return self

    def hazards(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Probabilidad anual de morir por la causa y por otra, (N, horizonte) cada una."""
        n = len(df)
        person = np.repeat(np.arange(n), self.horizon)
        year = np.tile(np.arange(self.horizon), n)
        X = self._matrix(df, person, year)
        cause = self.cause_.predict_proba(X)[:, 1].reshape(n, self.horizon)
        other = self.other_.predict_proba(X)[:, 1].reshape(n, self.horizon)
        return cause, other

    def risk(self, df: pd.DataFrame, years: int | None = None) -> np.ndarray:
        """Probabilidad de morir por la causa antes de ``years`` años (por defecto, el horizonte)."""
        years = self.horizon if years is None else years
        cause, other = self.hazards(df)
        alive = np.cumprod(1.0 - cause - other, axis=1)
        alive_before = np.column_stack([np.ones(len(df)), alive[:, :-1]])
        return (cause * alive_before)[:, :years].sum(axis=1)
