"""Heart failure signal in the resting pulse.

When the heart fails, the nervous system compensates by speeding it up and the pulse loses its
normal beat-to-beat variation. Both are measured from inter-beat intervals, like atrial
fibrillation (``rhythm``): a watch, a pulse oximeter or a phone camera with a fingertip on it
for a few minutes will do.

Data: two open PhysioNet databases with 24-hour beat annotations, one of 29 people with heart
failure (chf2db) and one of 54 in normal sinus rhythm (nsr2db). They are few, from the 1990s,
and the controls are healthy: see ``scripts/fit_pulse_hf.py`` and its report.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .i18n import t
from .rhythm import FEATURES as INTERVAL_FEATURES
from .rhythm import MIN_INTERVALS, interval_features
from .wfdb import read_beats, read_header

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "rr"
MODEL_PATH = ROOT / "models" / "ritmo" / "ic_pulso.joblib"
EXTRA = ["rate", "sdnn", "rmssd", "dc", "ac"]
FEATURES = INTERVAL_FEATURES + EXTRA


def capacity(rr: np.ndarray) -> tuple[float, float]:
    """Deceleration and acceleration capacity (s): how much the interval lengthens or shortens
    around the beats where the pulse slows or speeds up. Falls when vagal control fails."""
    if rr.size < 8:
        return np.nan, np.nan
    ratio = rr[1:] / rr[:-1]
    out = []
    for anchors in (np.flatnonzero((ratio > 1.0) & (ratio < 1.05)) + 1, np.flatnonzero((ratio < 1.0) & (ratio > 0.95)) + 1):
        anchors = anchors[(anchors >= 2) & (anchors < rr.size - 1)]
        if anchors.size < 3:
            out.append(np.nan)
        else:
            out.append(float(np.mean(rr[anchors] + rr[anchors + 1] - rr[anchors - 1] - rr[anchors - 2]) / 4.0))
    return out[0], out[1]


def pulse_features(rr) -> dict[str, float]:
    """The irregularity features of ``rhythm`` plus the absolute ones that change in heart failure."""
    rr = np.asarray(rr, dtype=float)
    out = interval_features(rr)
    out.update(dict.fromkeys(EXTRA, np.nan))
    if rr.size < MIN_INTERVALS:
        return out
    out["rate"] = 60.0 / rr.mean()
    out["sdnn"] = rr.std()
    out["rmssd"] = float(np.sqrt(np.mean(np.diff(rr) ** 2)))
    out["dc"], out["ac"] = capacity(rr)
    return out


@dataclass
class Subject:
    record: str
    heart_failure: bool
    age: float
    female: bool | None
    nyha: int | None
    beats: np.ndarray  # time of each beat (s)
    normal: np.ndarray  # whether the beat is normal (not ectopic)


def load_subjects(root: Path = DATA) -> list[Subject]:
    """The people in chf2db (heart failure) and nsr2db (normal sinus rhythm)."""
    subjects = []
    for database, sick in (("chf2db", True), ("nsr2db", False)):
        for header in sorted((root / database).glob("*.hea")):
            info = read_header(header)
            beats, normal = read_beats(header.with_suffix(".ecg"), info["fs"])
            subjects.append(Subject(info["record"], sick, info["age"], info["female"], info["nyha"], beats, normal))
    return subjects


def window_intervals(beats: np.ndarray, start: float, seconds: float) -> np.ndarray:
    """Inter-beat intervals in a window, without impossible ones (as a pulse sensor would see them)."""
    inside = beats[(beats >= start) & (beats < start + seconds)]
    rr = np.diff(inside)
    return rr[(rr > 0.25) & (rr < 2.5)]


def window_starts(beats: np.ndarray, seconds: float, count: int) -> np.ndarray:
    """Start times of ``count`` windows spread over the whole recording."""
    if beats.size < 2 or beats[-1] - beats[0] <= seconds:
        return np.array([])
    return np.linspace(beats[0], beats[-1] - seconds, count)


@dataclass
class PulseResult:
    probability: float | None  # at the training-data share of patients
    likelihood_ratio: float  # how much it multiplies the prior odds
    flagged: bool
    usable: bool
    heart_rate: float | None


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def available() -> bool:
    return _bundle() is not None


def classify_pulse(measurements) -> PulseResult:
    """Result for one or more pulse measurements (each, its inter-beat intervals in s).

    With several measurements the score is averaged: a fast, flat pulse for a while says little;
    every day, it says a lot.
    """
    bundle = _bundle()
    if bundle is None:
        raise FileNotFoundError(t("Falta el modelo (scripts/fit_pulse_hf.py).", "Model missing (scripts/fit_pulse_hf.py)."))
    series = [np.asarray(m, dtype=float) for m in measurements]
    series = [rr for rr in series if rr.size >= bundle["min_intervals"]]
    if not series:
        return PulseResult(None, 1.0, False, False, None)
    x = pd.DataFrame([pulse_features(rr) for rr in series])[bundle["features"]]
    p = np.clip(bundle["model"].predict_proba(x)[:, 1], 1e-4, 1 - 1e-4)
    score = float(np.mean(np.log(p / (1 - p))))
    p_mean = 1.0 / (1.0 + np.exp(-score))
    prevalence = bundle["prevalence"]
    ratio = (p_mean / (1 - p_mean)) / (prevalence / (1 - prevalence))
    ratio = float(np.clip(ratio, bundle["min_ratio"], bundle["max_ratio"]))  # limits measured in treated Spanish patients
    rate = float(np.mean([60.0 / rr.mean() for rr in series]))
    return PulseResult(float(p_mean), ratio, p_mean >= bundle["threshold"], True, rate)
