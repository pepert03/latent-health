"""Minimal, dependency-free reader for MIT-format (PhysioNet) beat annotations.

An annotation file is a sequence of 16-bit words: the top 6 bits give the type and the low 10
the samples elapsed since the previous annotation. Special codes handle long skips and text.
Here we only care about when each beat occurs and what type it is.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

SKIP, NUM, SUB, CHN, AUX = 59, 60, 61, 62, 63
# Types that are a beat (QRS complex) in the PhysioNet table.
BEAT_CODES = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 25, 30, 34, 35, 38, 41})
NORMAL = 1


def read_annotations(path) -> tuple[np.ndarray, np.ndarray]:
    """Sample index and type of each annotation in an MIT-format file."""
    words = np.frombuffer(Path(path).read_bytes(), dtype="<u2")
    samples, codes = [], []
    time = 0
    i = 0
    while i < words.size:
        word = int(words[i])
        code, interval = word >> 10, word & 0x3FF
        i += 1
        if code == 0 and interval == 0:
            break  # end of file
        if code == SKIP:
            if i + 1 >= words.size:
                break
            jump = (int(words[i]) << 16) | int(words[i + 1])
            time += jump - (1 << 32) if jump >= (1 << 31) else jump
            i += 2
        elif code in (NUM, SUB, CHN):
            continue  # modify the neighbouring annotation, do not advance time
        elif code == AUX:
            i += (interval + 1) // 2  # attached text, padded to even length
        else:
            time += interval
            samples.append(time)
            codes.append(code)
    return np.asarray(samples, dtype=np.int64), np.asarray(codes, dtype=np.int16)


def read_beats(path, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Time (s) of each beat and whether it is normal."""
    samples, codes = read_annotations(path)
    keep = np.isin(codes, list(BEAT_CODES))
    return samples[keep] / fs, codes[keep] == NORMAL


def read_header(path) -> dict:
    """Sampling rate and the subject data found in the header comments."""
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
