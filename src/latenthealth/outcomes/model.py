"""Cumulative risk of dying from a cause, from yearly hazards (discrete-time survival).

Each person becomes one row per year of follow-up. Two classifiers estimate, for each year,
the probability of dying from the cause of interest and of dying from anything else
(competing risks). The 10-year risk is the sum, year by year, of dying from the cause having
survived until then:

    risk(H) = sum_k  h_cause(k) * prod_{j<k} (1 - h_cause(j) - h_other(j))

Advantages over a classic risk equation:
- Uses people with shorter follow-up (counts the years they were actually observed).
- With gradient boosting it accepts missing predictors: **it gives the best estimate with
  whatever is available**, from just a questionnaire to the whole kit. No model per combination.
- Assumes neither linear nor proportional effects.

``kind="linear"`` uses pooled logistic regression (equivalent to a Cox-type equation with age
interactions, like SCORE2) to refit the classic equations on the same data.
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
    """Person-year rows. Returns (person index, year, label): 0 survives the year,
    1 dies from the cause, 2 dies from another. The incomplete year of survivors is dropped."""
    years = df.months.to_numpy(float) / 12.0
    died = df.dead.to_numpy(float) == 1
    whole = np.floor(years).astype(int)
    survived = np.minimum(whole, horizon)  # whole years survived within the horizon
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
    """Cumulative risk for a cause from the available predictors."""

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
        """Yearly probability of dying from the cause and from another, (N, horizon) each."""
        n = len(df)
        person = np.repeat(np.arange(n), self.horizon)
        year = np.tile(np.arange(self.horizon), n)
        X = self._matrix(df, person, year)
        cause = self.cause_.predict_proba(X)[:, 1].reshape(n, self.horizon)
        other = self.other_.predict_proba(X)[:, 1].reshape(n, self.horizon)
        return cause, other

    def risk(self, df: pd.DataFrame, years: int | None = None) -> np.ndarray:
        """Probability of dying from the cause within ``years`` years (default: the horizon)."""
        years = self.horizon if years is None else years
        cause, other = self.hazards(df)
        alive = np.cumprod(1.0 - cause - other, axis=1)
        alive_before = np.column_stack([np.ones(len(df)), alive[:, :-1]])
        return (cause * alive_before)[:, :years].sum(axis=1)
