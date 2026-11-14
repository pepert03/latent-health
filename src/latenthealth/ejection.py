"""Fracción de eyección baja a partir de 30 segundos de ECG de una derivación y sonido cardíaco.

La insuficiencia cardíaca con fracción de eyección reducida (el ventrículo izquierdo expulsa el
40 % o menos de la sangre que contiene) se confirma con un ecocardiograma. Aquí se estima con
lo que recoge un aparato de mano apoyado en el pecho: un electrocardiograma de una derivación
y el sonido del corazón. De esas dos señales salen tres grupos de medidas, de menos a más
aparato:

- **Pulso**: solo los intervalos entre latidos (lo que da la cámara del móvil o un reloj).
- **ECG**: la forma del latido promedio (anchura y voltaje del QRS, onda T, segmento ST).
- **Sonido**: el fonocardiograma promediado latido a latido con el ECG como reloj: cuánto
  tarda el primer ruido tras el QRS, cuánto dura la sístole, la fuerza relativa de los ruidos
  y la energía entre ellos (soplos y tercer ruido).

Datos: Zenodo 16934966 (CC-BY 4.0), 620 personas de dos hospitales de Wuhan con la fracción de
eyección medida por ecocardiograma y cuatro grabaciones de 30 s con un Eko DUO. Ver
``scripts/fit_ejection.py``.
"""

from __future__ import annotations

import io
import wave
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath

import joblib
import numpy as np
import pandas as pd
from scipy.signal import butter, hilbert, sosfiltfilt

from .pulse import FEATURES as PULSE
from .pulse import pulse_features
from .rhythm import detect_beats

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "hfref"
MAIN_ZIP = DATA / "HFrEF_5_folds.zip"
COMMUNITY_ZIP = DATA / "HFrEF_community_scenario_test_set.zip"
MODEL_PATH = ROOT / "models" / "ritmo" / "fe_baja.joblib"
SITES = ["APEX", "LLSB", "LUSB", "RUSB"]  # foco mitral, tricuspídeo, pulmonar y aórtico
REDUCED = 0.40

ECG = [
    "qrs_width", "qrs_equivalent", "qrs_amplitude", "qrs_slope", "t_amplitude", "t_time", "t_time_rel", "st_level",
    "p_amplitude", "template_corr", "template_corr_low", "odd_beats", "noise",
]  # fmt: skip
BANDS = {"low": (25.0, 60.0), "mid": (60.0, 150.0), "high": (150.0, 400.0)}
SOUND = [
    "s1_time", "s2_time", "systole", "s1_systole", "s1_rel", "systole_rel", "s1_s2", "s1_level", "s2_level", "s1_width",
    "s2_width", "murmur_mid", "murmur_high", "s3_low", "s4_low", "diastole_mid", "low_share", "high_share", "sound_quality",
]  # fmt: skip
GROUPS = {"pulso": PULSE, "ecg": ECG, "sonido": SOUND}
TEMPLATE = (-0.30, 0.50)  # ventana del latido promedio alrededor del pico R (s)
GATE = (-0.20, 0.70)  # ventana del sonido promediado alrededor del pico R (s)


# --- Lectura ---


def read_wav(data: bytes) -> tuple[float, np.ndarray]:
    with wave.open(io.BytesIO(data)) as handle:
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[handle.getsampwidth()]
        signal = np.frombuffer(handle.readframes(handle.getnframes()), dtype=dtype).astype(float)
        if handle.getnchannels() > 1:
            signal = signal.reshape(-1, handle.getnchannels())[:, 0]
        return float(handle.getframerate()), signal


def read_labels(path: Path) -> pd.DataFrame:
    """Una fila por persona: identificador, fracción de eyección (0-1) y parte de la validación cruzada.

    En el conjunto comunitario la parte es -1.
    """
    rows = {}
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.endswith("_label.csv"):
                continue
            name = PurePosixPath(member).name
            fold = int(name.split("_")[1]) if name.startswith("fold_") else -1
            for line in archive.read(member).decode("utf-8", errors="replace").splitlines():
                if "," not in line:
                    continue
                key, value = line.rsplit(",", 1)
                try:
                    rows[key.split("_")[0].strip()] = (float(value), fold)
                except ValueError:
                    continue  # cabecera
    return pd.DataFrame([(k, *v) for k, v in rows.items()], columns=["subject", "lvef", "fold"])


def recording_names(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Ficheros de cada grabación: {(persona, foco): {"ECG": nombre, "PCG": nombre}}."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.endswith(".wav"):
                continue
            parts = PurePosixPath(member).stem.split("_")
            if len(parts) == 3 and parts[1] in SITES and parts[2] in ("ECG", "PCG"):
                out.setdefault((parts[0], parts[1]), {})[parts[2]] = member
    return out


# --- Electrocardiograma ---


def clean_ecg(ecg, fs: float) -> np.ndarray:
    sos = butter(2, [0.67, 40.0], btype="band", fs=fs, output="sos")
    return sosfiltfilt(sos, np.asarray(ecg, dtype=float))


def r_peaks(ecg: np.ndarray, fs: float) -> tuple[np.ndarray, float]:
    """Muestra del pico del QRS de cada latido y su polaridad (+1 o -1).

    ``detect_beats`` da el centro de la energía del QRS; aquí se afina al extremo de la señal
    para poder promediar latidos alineados.
    """
    beats = np.round(detect_beats(ecg, fs) * fs).astype(int)
    if beats.size < 3:
        return np.array([], dtype=int), 1.0
    half = int(0.07 * fs)
    spans = [ecg[max(b - half, 0) : b + half + 1] for b in beats]
    local = np.array([np.median(s) for s in spans])
    up = np.median([s.max() - m for s, m in zip(spans, local)])
    down = np.median([m - s.min() for s, m in zip(spans, local)])
    polarity = 1.0 if up >= down else -1.0
    peaks = np.array([max(b - half, 0) + int(np.argmax(polarity * s)) for b, s in zip(beats, spans)])
    return np.unique(peaks), polarity


def _stack(signal: np.ndarray, peaks: np.ndarray, fs: float, window: tuple[float, float]) -> np.ndarray:
    before, after = int(round(-window[0] * fs)), int(round(window[1] * fs))
    inside = peaks[(peaks >= before) & (peaks + after <= signal.size)]
    if inside.size == 0:
        return np.empty((0, before + after))
    return signal[inside[:, None] + np.arange(-before, after)[None, :]]


def ecg_features(ecg: np.ndarray, fs: float, peaks: np.ndarray, polarity: float) -> dict[str, float]:
    """Medidas de la forma del latido promedio. ``ecg`` ya filtrado."""
    out = dict.fromkeys(ECG, np.nan)
    beats = _stack(polarity * ecg, peaks, fs, TEMPLATE)
    if len(beats) < 5:
        return out
    template = np.median(beats, axis=0)
    t = np.arange(template.size) / fs + TEMPLATE[0]

    def at(lo: float, hi: float) -> slice:
        return slice(int(round((lo - TEMPLATE[0]) * fs)), int(round((hi - TEMPLATE[0]) * fs)))

    iso = float(np.median(template[at(-0.12, -0.07)]))
    x = template - iso
    amplitude = float(x[at(-0.06, 0.06)].max() - x[at(-0.06, 0.06)].min())
    if amplitude <= 0:
        return out
    slope = np.abs(np.gradient(x)) * fs
    slope = np.convolve(slope, np.ones(5) / 5, mode="same")
    zero = int(round(-TEMPLATE[0] * fs))
    quiet = 0.08 * slope[at(-0.06, 0.06)].max()
    run = max(int(0.016 * fs), 1)
    onset = zero - int(0.12 * fs)
    for i in range(zero, zero - int(0.12 * fs), -1):
        if np.all(slope[i - run : i] < quiet):
            onset = i
            break
    offset = zero + int(0.16 * fs)
    for i in range(zero, zero + int(0.16 * fs)):
        if np.all(slope[i : i + run] < quiet):
            offset = i
            break
    rr = float(np.median(np.diff(peaks))) / fs if peaks.size > 1 else np.nan
    out["qrs_width"] = (offset - onset) / fs
    out["qrs_equivalent"] = float(np.abs(x[at(-0.10, 0.12)]).sum() / fs / np.abs(x[at(-0.06, 0.06)]).max())
    out["qrs_amplitude"] = float(np.log(amplitude))
    out["qrs_slope"] = float(slope[at(-0.06, 0.06)].max() / amplitude)
    end = float(np.clip(0.7 * rr if np.isfinite(rr) else 0.45, 0.25, 0.45))
    t_window = slice(offset + int(0.06 * fs), int(round((end - TEMPLATE[0]) * fs)))
    if t_window.stop - t_window.start > 5:
        segment = x[t_window]
        peak = int(np.argmax(np.abs(segment)))
        out["t_amplitude"] = float(segment[peak] / amplitude)  # con signo: negativa si va contra el QRS
        out["t_time"] = float(t[t_window][peak])
        out["t_time_rel"] = out["t_time"] / np.sqrt(rr) if np.isfinite(rr) else np.nan
    out["st_level"] = float(np.mean(x[offset + int(0.04 * fs) : offset + int(0.08 * fs)]) / amplitude)
    p_window = template[at(-0.26, -0.26 + max((onset - zero) / fs + 0.24, 0.04))]
    out["p_amplitude"] = float((p_window.max() - p_window.min()) / amplitude)
    core = at(-0.10, 0.30)
    centred = beats[:, core] - beats[:, core].mean(axis=1, keepdims=True)
    reference = template[core] - template[core].mean()
    corr = centred @ reference / (np.linalg.norm(centred, axis=1) * np.linalg.norm(reference) + 1e-12)
    out["template_corr"] = float(np.mean(corr))
    out["template_corr_low"] = float(np.percentile(corr, 10))
    out["odd_beats"] = float(np.mean(corr < 0.7))
    out["noise"] = float(np.log(np.median(np.std(beats - template, axis=1)) / amplitude + 1e-6))
    return out


# --- Fonocardiograma ---


def envelopes(pcg, fs_pcg: float, fs_out: float) -> dict[str, np.ndarray]:
    """Envolvente del sonido en tres bandas, muestreada como el ECG y en unidades de su mediana."""
    step = int(round(fs_pcg / fs_out))
    smooth = butter(2, 25.0, btype="low", fs=fs_pcg, output="sos")
    out = {}
    for name, (lo, hi) in BANDS.items():
        band = butter(3, [lo, hi], btype="band", fs=fs_pcg, output="sos")
        envelope = np.abs(hilbert(sosfiltfilt(band, np.asarray(pcg, dtype=float))))
        envelope = np.maximum(sosfiltfilt(smooth, envelope), 0.0)[::step]
        out[name] = envelope / (np.median(envelope) + 1e-9)
    return out


def _width(curve: np.ndarray, peak: int, fs: float) -> float:
    half = curve[peak] / 2.0
    left = peak
    while left > 0 and curve[left] > half:
        left -= 1
    right = peak
    while right < curve.size - 1 and curve[right] > half:
        right += 1
    return (right - left) / fs


def sound_features(pcg, fs_pcg: float, peaks: np.ndarray, fs: float) -> dict[str, float]:
    """Medidas del sonido cardíaco promediado alrededor de cada QRS."""
    out = dict.fromkeys(SOUND, np.nan)
    if peaks.size < 5:
        return out
    gated = {}
    for name, envelope in envelopes(pcg, fs_pcg, fs).items():
        stack = _stack(envelope, peaks, fs, GATE)
        if len(stack) < 5:
            return out
        gated[name] = np.median(stack, axis=0)
    rr = float(np.median(np.diff(peaks))) / fs
    zero = int(round(-GATE[0] * fs))

    def index(seconds: float) -> int:
        return int(np.clip(zero + round(seconds * fs), 0, gated["mid"].size - 1))

    mid, low, high = gated["mid"], gated["low"], gated["high"]
    s1 = index(0.0) + int(np.argmax(mid[index(0.0) : index(0.18)]))
    last = min(0.50, max(rr - 0.12, 0.30))
    start = s1 + int(0.14 * fs)
    stop = max(index(last), start + 3)
    s2 = start + int(np.argmax(mid[start:stop]))
    t1, t2 = (s1 - zero) / fs, (s2 - zero) / fs
    systole = t2 - t1
    out["s1_time"], out["s2_time"], out["systole"] = t1, t2, systole
    out["s1_systole"] = t1 / systole  # equivalente al cociente activación/eyección de la cardiografía acústica
    out["s1_rel"], out["systole_rel"] = t1 / rr, systole / rr
    out["s1_s2"] = float(np.log(mid[s1] / mid[s2]))
    out["s1_level"], out["s2_level"] = float(np.log(mid[s1])), float(np.log(mid[s2]))
    out["s1_width"], out["s2_width"] = _width(mid, s1, fs), _width(mid, s2, fs)
    between = slice(s1 + int(0.07 * fs), max(s2 - int(0.05 * fs), s1 + int(0.07 * fs) + 2))
    reference = (mid[s1] + mid[s2]) / 2.0
    out["murmur_mid"] = float(np.log(np.mean(mid[between]) / reference))
    out["murmur_high"] = float(np.log(np.mean(high[between]) / ((high[s1] + high[s2]) / 2.0 + 1e-9)))
    third = slice(s2 + int(0.10 * fs), min(s2 + int(0.22 * fs), low.size))
    if third.stop - third.start > 2:
        out["s3_low"] = float(np.log(np.mean(low[third]) / (low[s2] + 1e-9)))
        out["diastole_mid"] = float(np.log(np.mean(mid[third]) / reference))
    out["s4_low"] = float(np.log(np.mean(low[index(-0.14) : index(-0.04)]) / (low[s1] + 1e-9)))
    total = low[s1] + mid[s1] + high[s1]
    out["low_share"], out["high_share"] = float(low[s1] / total), float(high[s1] / total)
    out["sound_quality"] = float(np.log(reference))  # los ruidos frente al fondo
    return out


# --- Perfiles completos (para comprobar si las medidas resumidas se dejan algo) ---

ECG_PROFILE = [f"tpl_{i:02d}" for i in range(32)]  # latido promedio de -200 a +440 ms, cada 20 ms
SOUND_PROFILE = [f"env_{band}_{i:02d}" for band in BANDS for i in range(16)]  # sonido de -200 a +600 ms, cada 50 ms


def profile_features(ecg: np.ndarray, fs: float, peaks: np.ndarray, polarity: float, pcg=None, fs_pcg: float | None = None) -> dict[str, float]:
    out = dict.fromkeys(ECG_PROFILE + SOUND_PROFILE, np.nan)
    beats = _stack(polarity * ecg, peaks, fs, (-0.20, 0.44))
    if len(beats) < 5:
        return out
    template = np.median(beats, axis=0)
    template = template - np.median(template[int(0.08 * fs) : int(0.13 * fs)])
    scale = np.abs(template).max()
    step = int(0.02 * fs)
    for i, value in enumerate(template[: 32 * step].reshape(32, step).mean(axis=1) / (scale + 1e-9)):
        out[f"tpl_{i:02d}"] = float(value)
    if pcg is not None and fs_pcg:
        step = int(0.05 * fs)
        for band, envelope in envelopes(pcg, fs_pcg, fs).items():
            stack = _stack(envelope, peaks, fs, (-0.20, 0.60))
            if len(stack) < 5:
                continue
            gated = np.median(stack, axis=0)
            for i, value in enumerate(np.log(gated[: 16 * step].reshape(16, step).mean(axis=1) + 1e-6)):
                out[f"env_{band}_{i:02d}"] = float(value)
    return out


# --- Una grabación ---


def recording_features(ecg, fs_ecg: float, pcg=None, fs_pcg: float | None = None, profiles: bool = False) -> dict[str, float]:
    """Todas las medidas de una grabación. Sin sonido, las de ese grupo quedan vacías."""
    ecg = clean_ecg(ecg, fs_ecg)
    peaks, polarity = r_peaks(ecg, fs_ecg)
    rr = np.diff(peaks) / fs_ecg
    out = pulse_features(rr[(rr > 0.25) & (rr < 2.5)])
    out.update(ecg_features(ecg, fs_ecg, peaks, polarity))
    if pcg is not None and fs_pcg:
        out.update(sound_features(pcg, fs_pcg, peaks, fs_ecg))
    else:
        out.update(dict.fromkeys(SOUND, np.nan))
    if profiles:
        out.update(profile_features(ecg, fs_ecg, peaks, polarity, pcg, fs_pcg))
    return out


def features_from_zip(path: Path, subjects: list[str] | None = None, profiles: bool = False) -> pd.DataFrame:
    """Tabla de medidas, una fila por grabación (persona y foco)."""
    names = recording_names(path)
    rows = []
    with zipfile.ZipFile(path) as archive:
        for (subject, site), files in sorted(names.items()):
            if subjects is not None and subject not in subjects:
                continue
            if "ECG" not in files:
                continue
            fs_ecg, ecg = read_wav(archive.read(files["ECG"]))
            fs_pcg, pcg = read_wav(archive.read(files["PCG"])) if "PCG" in files else (None, None)
            row = recording_features(ecg, fs_ecg, pcg, fs_pcg, profiles=profiles)
            row.update(subject=subject, site=site)
            rows.append(row)
    return pd.DataFrame(rows)


# --- Modelo ---


@dataclass
class EjectionResult:
    probability: float | None  # P(fracción de eyección ≤ 40 %) con la proporción de los datos de entrenamiento
    likelihood_ratio: float
    flagged: bool
    usable: bool


@lru_cache(maxsize=1)
def _bundle():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def available() -> bool:
    return _bundle() is not None


def classify(recordings: list[dict[str, float]], tier: str = "sonido") -> EjectionResult:
    """Resultado para una o varias grabaciones de una persona (medidas de ``recording_features``).

    ``tier`` es lo que se tiene: "pulso", "ecg" o "sonido" (ECG y sonido).
    """
    bundle = _bundle()
    if bundle is None:
        raise FileNotFoundError("Falta el modelo (scripts/fit_ejection.py).")
    model = bundle["models"][tier]
    table = pd.DataFrame(recordings)
    table = table[table["n"] >= bundle["min_intervals"]]
    if table.empty:
        return EjectionResult(None, 1.0, False, False)
    if "site_code" not in table:
        table["site_code"] = 0  # sin indicar el foco se supone la punta del corazón
    table = table.reindex(columns=model["features"])  # lo que falte (perfiles, sonido) queda vacío
    p = np.clip(model["model"].predict_proba(table[model["features"]])[:, 1], 1e-4, 1 - 1e-4)
    score = float(np.mean(np.log(p / (1 - p))))
    p_mean = 1.0 / (1.0 + np.exp(-score))
    prevalence = bundle["prevalence"]
    ratio = (p_mean / (1 - p_mean)) / (prevalence / (1 - prevalence))
    ratio = float(np.clip(ratio, 1.0 / bundle["max_ratio"], bundle["max_ratio"]))
    return EjectionResult(float(p_mean), ratio, score >= model["threshold"], True)


def check_from_recordings(day, recordings: list[dict[str, float]], tier: str = "sonido"):
    """Grabación del corazón valorada, para la ficha del paciente."""
    from .home import HeartCheck

    result = classify(recordings, tier)
    source = {"pulso": "pulso", "ecg": "ecg", "sonido": "ecg y sonido"}[tier]
    return HeartCheck(day, result.likelihood_ratio if result.usable else 1.0, source)
