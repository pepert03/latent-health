"""Atrial fibrillation detector from inter-beat intervals.

In atrial fibrillation the pulse is "irregularly irregular": the intervals between beats vary
with no pattern. That can be measured with anything that marks each beat: a pocket ECG, a watch
or a phone camera with a fingertip on it. So the detector uses **only the intervals**, not the
waveform.

Trained and validated on the 8,528 recordings of the PhysioNet/CinC Challenge 2017 (single
lead, 9-60 s, pocket ECG, labelled by experts as normal rhythm, atrial fibrillation, other
rhythm or noise). See ``scripts/fit_rhythm.py``.

To bring it closer to a phone camera, which marks each beat less precisely and misses some,
there is a function that degrades the intervals (``degrade``). It is a simulation: there are no
open labelled camera recordings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks

from .i18n import t

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "ritmo" / "fa_intervalos.joblib"
MIN_INTERVALS = 8
FEATURES = [
    "n", "mean", "cv", "rmssd_rel", "pnn50", "pnn_rel", "mad_rel", "range_rel", "short", "long",
    "sd1_sd2", "sd1_rel", "turning", "autocorr", "entropy", "sample_entropy", "lorenz",
]  # fmt: skip


def detect_beats(signal, fs: float) -> np.ndarray:
    """Beat times (s) in a single-lead electrocardiogram.

    Simplified Pan-Tompkins: band-pass the QRS band, differentiate, square, integrate over a
    short window and find the peaks.
    """
    x = np.asarray(signal, dtype=float)
    x = x - np.median(x)
    b, a = butter(2, [5.0, 15.0], btype="band", fs=fs)
    filtered = filtfilt(b, a, x)
    energy = np.gradient(filtered) ** 2
    window = max(int(0.12 * fs), 1)
    integrated = np.convolve(energy, np.ones(window) / window, mode="same")
    peaks, props = find_peaks(integrated, distance=int(0.25 * fs), height=0)
    if peaks.size < 3:
        return np.array([])
    heights = props["peak_heights"]
    # Threshold relative to typical large peaks: drops T waves and noise regardless of amplitude.
    threshold = 0.25 * np.median(heights[heights >= np.median(heights)])
    return peaks[heights >= threshold] / fs


def intervals_from_beats(beats) -> np.ndarray:
    """Inter-beat intervals (s), without impossible ones (under 0.25 s or over 2.5 s)."""
    rr = np.diff(np.asarray(beats, dtype=float))
    return rr[(rr > 0.25) & (rr < 2.5)]


def _sample_entropy(x: np.ndarray, m: int = 1, tolerance: float = 0.03) -> float:
    """Sample entropy with a fixed tolerance in seconds (regularity of the series)."""
    n = x.size
    if n < m + 3:
        return np.nan

    def matches(length: int) -> float:
        templates = np.lib.stride_tricks.sliding_window_view(x, length)
        distance = np.abs(templates[:, None, :] - templates[None, :, :]).max(axis=2)
        return (distance <= tolerance).sum() - len(templates)

    b, a = matches(m), matches(m + 1)
    return float(-np.log((a + 1.0) / (b + 1.0)))


def interval_features(rr) -> dict[str, float]:
    """Irregularity features of a series of inter-beat intervals (s)."""
    rr = np.asarray(rr, dtype=float)
    out = dict.fromkeys(FEATURES, np.nan)
    out["n"] = float(rr.size)
    if rr.size < MIN_INTERVALS:
        return out
    mean, median = rr.mean(), np.median(rr)
    d = np.diff(rr)
    out["mean"] = mean
    out["cv"] = rr.std() / mean
    out["rmssd_rel"] = np.sqrt(np.mean(d**2)) / mean
    out["pnn50"] = np.mean(np.abs(d) > 0.05)
    out["pnn_rel"] = np.mean(np.abs(d) > 0.1 * mean)
    out["mad_rel"] = np.median(np.abs(d)) / median
    out["range_rel"] = (np.percentile(rr, 95) - np.percentile(rr, 5)) / median
    out["short"] = np.mean(rr < 0.8 * median)  # early beats (ectopics)
    out["long"] = np.mean(rr > 1.2 * median)  # pauses
    sd1 = np.std(d) / np.sqrt(2.0)
    sd2 = np.sqrt(max(2.0 * rr.var() - sd1**2, 1e-12))
    out["sd1_sd2"] = sd1 / sd2  # Poincaré cloud shape: round in fibrillation
    out["sd1_rel"] = sd1 / mean
    out["turning"] = np.mean((d[:-1] * d[1:]) < 0)  # direction changes: many if there is no pattern
    out["autocorr"] = np.corrcoef(rr[:-1], rr[1:])[0, 1] if rr.std() > 0 else 1.0
    counts = np.histogram(d / mean, bins=np.linspace(-0.6, 0.6, 17))[0]
    p = counts[counts > 0] / max(counts.sum(), 1)
    out["entropy"] = float(-(p * np.log(p)).sum())
    out["sample_entropy"] = _sample_entropy(rr)
    # Occupancy of the (current change, next change) plane: fibrillation fills it.
    grid = np.linspace(-0.6, 0.6, 13)
    cells = np.histogram2d(d[:-1] / mean, d[1:] / mean, bins=[grid, grid])[0]
    out["lorenz"] = float((cells > 0).mean())
    return out


def degrade(beats, rng, jitter: float = 0.02, missed: float = 0.03) -> np.ndarray:
    """Beats as a camera would mark them: with jitter (s) and missing a share."""
    beats = np.asarray(beats, dtype=float)
    keep = rng.random(beats.size) >= missed
    return np.sort(beats[keep] + jitter * rng.standard_normal(int(keep.sum())))


@dataclass
class RhythmResult:
    probability: float | None  # P(atrial fibrillation) at the training-data prevalence
    likelihood_ratio: float  # how much it multiplies the prior odds
    irregular: bool
    usable: bool  # enough beats to give an opinion
    heart_rate: float | None


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def available() -> bool:
    return _bundle() is not None


def classify_intervals(rr) -> RhythmResult:
    """Detector result for a series of inter-beat intervals (s)."""
    bundle = _bundle()
    if bundle is None:
        raise FileNotFoundError(t("Falta el detector (scripts/fit_rhythm.py).", "Detector missing (scripts/fit_rhythm.py)."))
    rr = np.asarray(rr, dtype=float)
    feats = interval_features(rr)
    if rr.size < MIN_INTERVALS:
        return RhythmResult(None, 1.0, False, False, None)
    x = pd.DataFrame([feats])[FEATURES]
    p = float(np.clip(bundle["model"].predict_proba(x)[0, 1], 1e-4, 1 - 1e-4))
    prevalence = bundle["prevalence"]
    ratio = (p / (1.0 - p)) / (prevalence / (1.0 - prevalence))
    ratio = float(np.clip(ratio, 1.0 / bundle["max_ratio"], bundle["max_ratio"]))  # one reading cannot decide everything
    return RhythmResult(p, ratio, p >= bundle["threshold"], True, 60.0 / float(np.mean(rr)))


def classify_ecg(signal, fs: float) -> RhythmResult:
    return classify_intervals(intervals_from_beats(detect_beats(signal, fs)))


def check_from_intervals(day: date, rr):
    """Rhythm check for the patient record from inter-beat intervals."""
    from .home import RhythmCheck

    result = classify_intervals(rr)
    return RhythmCheck(day, result.irregular, likelihood_ratio=result.likelihood_ratio if result.usable else 1.0)
