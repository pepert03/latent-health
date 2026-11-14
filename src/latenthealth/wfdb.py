"""Lector mínimo de anotaciones de latidos en formato MIT (PhysioNet), sin dependencias.

Un fichero de anotaciones es una lista de palabras de 16 bits: los 6 bits altos dicen el tipo
y los 10 bajos, las muestras transcurridas desde la anotación anterior. Hay códigos especiales
para saltos largos y texto. Aquí solo interesa cuándo cae cada latido y de qué tipo es.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

SKIP, NUM, SUB, CHN, AUX = 59, 60, 61, 62, 63
# Tipos que son un latido (complejo QRS) en la tabla de PhysioNet.
BEAT_CODES = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 25, 30, 34, 35, 38, 41})
NORMAL = 1


def read_annotations(path) -> tuple[np.ndarray, np.ndarray]:
    """Muestra y tipo de cada anotación de un fichero en formato MIT."""
    words = np.frombuffer(Path(path).read_bytes(), dtype="<u2")
    samples, codes = [], []
    time = 0
    i = 0
    while i < words.size:
        word = int(words[i])
        code, interval = word >> 10, word & 0x3FF
        i += 1
        if code == 0 and interval == 0:
            break  # fin del fichero
        if code == SKIP:
            if i + 1 >= words.size:
                break
            jump = (int(words[i]) << 16) | int(words[i + 1])
            time += jump - (1 << 32) if jump >= (1 << 31) else jump
            i += 2
        elif code in (NUM, SUB, CHN):
            continue  # modifican la anotación vecina, no avanzan el tiempo
        elif code == AUX:
            i += (interval + 1) // 2  # texto adjunto, relleno a longitud par
        else:
            time += interval
            samples.append(time)
            codes.append(code)
    return np.asarray(samples, dtype=np.int64), np.asarray(codes, dtype=np.int16)


def read_beats(path, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Instante (s) de cada latido y si es normal."""
    samples, codes = read_annotations(path)
    keep = np.isin(codes, list(BEAT_CODES))
    return samples[keep] / fs, codes[keep] == NORMAL


def read_header(path) -> dict:
    """Frecuencia de muestreo y los datos de la persona que traen los comentarios de la cabecera."""
    lines = Path(path).read_text(encoding="ascii", errors="replace").splitlines()
    fields = lines[0].split()
    out: dict = {"record": fields[0], "fs": float(fields[2].split("/")[0]) if len(fields) > 2 else None}
    comments = " ".join(line.lstrip("#").strip() for line in lines[1:] if line.startswith("#"))
    age = re.search(r"Age:\s*([\d.]+)", comments)
    sex = re.search(r"Sex:\s*([MF])", comments)
    nyha = re.search(r"NYHA class:\s*([IV]+)", comments)
    out["age"] = float(age.group(1)) if age else np.nan
    out["female"] = (sex.group(1) == "F") if sex else None
    out["nyha"] = {"I": 1, "II": 2, "III": 3, "IV": 4}.get(nyha.group(1)) if nyha else None
    return out
