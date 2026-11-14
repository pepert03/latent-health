"""Detector de fibrilación auricular a partir de los intervalos entre latidos.

En la fibrilación auricular el pulso es "irregularmente irregular": los intervalos entre
latidos varían sin patrón. Eso se puede medir con cualquier cosa que marque cada latido: un
electrocardiógrafo de bolsillo, un reloj o la cámara del móvil apoyada en el dedo. Por eso el
detector usa **solo los intervalos**, no la forma de la onda.

Se entrena y se valida con los 8.528 registros del PhysioNet/CinC Challenge 2017 (una
derivación, 9-60 s, electrocardiógrafo de bolsillo, etiquetados por expertos como ritmo normal,
fibrilación auricular, otro ritmo o ruido). Ver ``scripts/fit_rhythm.py``.

Para acercarlo a la cámara del móvil, que marca cada latido con menos precisión y se salta
alguno, hay una función que degrada los intervalos (``degrade``). Es una simulación: no hay
registros de cámara etiquetados en abierto.
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

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "ritmo" / "fa_intervalos.joblib"
MIN_INTERVALS = 8
FEATURES = [
    "n", "mean", "cv", "rmssd_rel", "pnn50", "pnn_rel", "mad_rel", "range_rel", "short", "long",
    "sd1_sd2", "sd1_rel", "turning", "autocorr", "entropy", "sample_entropy", "lorenz",
]  # fmt: skip


def detect_beats(signal, fs: float) -> np.ndarray:
    """Instantes de los latidos (s) en un electrocardiograma de una derivación.

    Versión simplificada del método de Pan y Tompkins: se filtra la banda del complejo QRS, se
    deriva, se eleva al cuadrado, se integra en una ventana corta y se buscan los picos.
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
    # Umbral relativo a los picos grandes típicos: descarta ondas T y ruido sin depender de la amplitud.
    threshold = 0.25 * np.median(heights[heights >= np.median(heights)])
    return peaks[heights >= threshold] / fs


def intervals_from_beats(beats) -> np.ndarray:
    """Intervalos entre latidos (s), sin los que son imposibles (menos de 0,25 s o más de 2,5 s)."""
    rr = np.diff(np.asarray(beats, dtype=float))
    return rr[(rr > 0.25) & (rr < 2.5)]


def _sample_entropy(x: np.ndarray, m: int = 1, tolerance: float = 0.03) -> float:
    """Entropía muestral con tolerancia fija en segundos (regularidad de la serie)."""
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
    """Medidas de irregularidad de una serie de intervalos entre latidos (s)."""
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
    out["short"] = np.mean(rr < 0.8 * median)  # latidos adelantados (extrasístoles)
    out["long"] = np.mean(rr > 1.2 * median)  # pausas
    sd1 = np.std(d) / np.sqrt(2.0)
    sd2 = np.sqrt(max(2.0 * rr.var() - sd1**2, 1e-12))
    out["sd1_sd2"] = sd1 / sd2  # forma de la nube de Poincaré: redonda en la fibrilación
    out["sd1_rel"] = sd1 / mean
    out["turning"] = np.mean((d[:-1] * d[1:]) < 0)  # cambios de sentido: muchos si no hay patrón
    out["autocorr"] = np.corrcoef(rr[:-1], rr[1:])[0, 1] if rr.std() > 0 else 1.0
    counts = np.histogram(d / mean, bins=np.linspace(-0.6, 0.6, 17))[0]
    p = counts[counts > 0] / max(counts.sum(), 1)
    out["entropy"] = float(-(p * np.log(p)).sum())
    out["sample_entropy"] = _sample_entropy(rr)
    # Ocupación del plano (cambio actual, cambio siguiente): la fibrilación lo llena.
    grid = np.linspace(-0.6, 0.6, 13)
    cells = np.histogram2d(d[:-1] / mean, d[1:] / mean, bins=[grid, grid])[0]
    out["lorenz"] = float((cells > 0).mean())
    return out


def degrade(beats, rng, jitter: float = 0.02, missed: float = 0.03) -> np.ndarray:
    """Latidos como los marcaría una cámara: con imprecisión (s) y saltándose una parte."""
    beats = np.asarray(beats, dtype=float)
    keep = rng.random(beats.size) >= missed
    return np.sort(beats[keep] + jitter * rng.standard_normal(int(keep.sum())))


@dataclass
class RhythmResult:
    probability: float | None  # P(fibrilación auricular) con la prevalencia de los datos de entrenamiento
    likelihood_ratio: float  # cuánto multiplica la odds de partida
    irregular: bool
    usable: bool  # hay latidos suficientes para opinar
    heart_rate: float | None


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def available() -> bool:
    return _bundle() is not None


def classify_intervals(rr) -> RhythmResult:
    """Resultado del detector para una serie de intervalos entre latidos (s)."""
    bundle = _bundle()
    if bundle is None:
        raise FileNotFoundError("Falta el detector (scripts/fit_rhythm.py).")
    rr = np.asarray(rr, dtype=float)
    feats = interval_features(rr)
    if rr.size < MIN_INTERVALS:
        return RhythmResult(None, 1.0, False, False, None)
    x = pd.DataFrame([feats])[FEATURES]
    p = float(np.clip(bundle["model"].predict_proba(x)[0, 1], 1e-4, 1 - 1e-4))
    prevalence = bundle["prevalence"]
    ratio = (p / (1.0 - p)) / (prevalence / (1.0 - prevalence))
    ratio = float(np.clip(ratio, 1.0 / bundle["max_ratio"], bundle["max_ratio"]))  # una sola medida no puede decidirlo todo
    return RhythmResult(p, ratio, p >= bundle["threshold"], True, 60.0 / float(np.mean(rr)))


def classify_ecg(signal, fs: float) -> RhythmResult:
    return classify_intervals(intervals_from_beats(detect_beats(signal, fs)))


def check_from_intervals(day: date, rr):
    """Comprobación del ritmo para la ficha del paciente a partir de los intervalos entre latidos."""
    from .home import RhythmCheck

    result = classify_intervals(rr)
    return RhythmCheck(day, result.irregular, likelihood_ratio=result.likelihood_ratio if result.usable else 1.0)
