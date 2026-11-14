"""Señal de insuficiencia cardíaca en el pulso en reposo.

Cuando el corazón falla, el sistema nervioso lo compensa acelerándolo y el pulso pierde su
variación normal de un latido a otro. Las dos cosas se miden con los intervalos entre latidos,
igual que la fibrilación auricular (``rhythm``): sirve un reloj, un pulsioxímetro o la cámara
del móvil apoyada en el dedo durante unos minutos.

Datos: dos bases abiertas de PhysioNet con los latidos de 24 horas, una de 29 personas con
insuficiencia cardíaca (chf2db) y otra de 54 en ritmo sinusal normal (nsr2db). Son pocos, de
los años noventa y los controles están sanos: ver ``scripts/fit_pulse_hf.py`` y su informe.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .rhythm import FEATURES as INTERVAL_FEATURES
from .rhythm import MIN_INTERVALS, interval_features
from .wfdb import read_beats, read_header

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "rr"
MODEL_PATH = ROOT / "models" / "ritmo" / "ic_pulso.joblib"
EXTRA = ["rate", "sdnn", "rmssd", "dc", "ac"]
FEATURES = INTERVAL_FEATURES + EXTRA


def capacity(rr: np.ndarray) -> tuple[float, float]:
    """Capacidad de deceleración y de aceleración (s): cuánto se alarga o acorta el intervalo
    alrededor de los latidos en que el pulso frena o acelera. Baja cuando falla el control vagal."""
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
    """Las medidas de irregularidad de ``rhythm`` más las absolutas que cambian en la insuficiencia cardíaca."""
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
    beats: np.ndarray  # instante de cada latido (s)
    normal: np.ndarray  # si el latido es normal (no extrasístole)


def load_subjects(root: Path = DATA) -> list[Subject]:
    """Las personas de chf2db (insuficiencia cardíaca) y nsr2db (ritmo sinusal normal)."""
    subjects = []
    for database, sick in (("chf2db", True), ("nsr2db", False)):
        for header in sorted((root / database).glob("*.hea")):
            info = read_header(header)
            beats, normal = read_beats(header.with_suffix(".ecg"), info["fs"])
            subjects.append(Subject(info["record"], sick, info["age"], info["female"], info["nyha"], beats, normal))
    return subjects


def window_intervals(beats: np.ndarray, start: float, seconds: float) -> np.ndarray:
    """Intervalos entre los latidos de un tramo, sin los imposibles (como los vería un sensor de pulso)."""
    inside = beats[(beats >= start) & (beats < start + seconds)]
    rr = np.diff(inside)
    return rr[(rr > 0.25) & (rr < 2.5)]


def window_starts(beats: np.ndarray, seconds: float, count: int) -> np.ndarray:
    """Comienzos de ``count`` tramos repartidos por todo el registro."""
    if beats.size < 2 or beats[-1] - beats[0] <= seconds:
        return np.array([])
    return np.linspace(beats[0], beats[-1] - seconds, count)


@dataclass
class PulseResult:
    probability: float | None  # con la proporción de enfermos de los datos de entrenamiento
    likelihood_ratio: float  # cuánto multiplica la odds de partida
    flagged: bool
    usable: bool
    heart_rate: float | None


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def available() -> bool:
    return _bundle() is not None


def classify_pulse(measurements) -> PulseResult:
    """Resultado para una o varias medidas del pulso (cada una, sus intervalos entre latidos en s).

    Con varias medidas se promedia la puntuación: un rato de pulso rápido y plano no dice mucho,
    que lo sea todos los días sí.
    """
    bundle = _bundle()
    if bundle is None:
        raise FileNotFoundError("Falta el modelo (scripts/fit_pulse_hf.py).")
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
    ratio = float(np.clip(ratio, bundle["min_ratio"], bundle["max_ratio"]))  # límites medidos en pacientes españoles tratados
    rate = float(np.mean([60.0 / rr.mean() for rr in series]))
    return PulseResult(float(p_mean), ratio, p_mean >= bundle["threshold"], True, rate)
