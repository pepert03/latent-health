"""Minimal reader for R data files (.rda) holding tables of numbers and factors.

Covers only what is needed to read a data.frame saved with ``save()``: integer, double,
logical and string vectors, lists, factors and attributes. Avoids depending on R or an
external package for a single data file.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import struct
from pathlib import Path

import numpy as np
import pandas as pd

_NA_INT = -2147483648


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.pos, self.refs = data, 0, []

    def take(self, n: int) -> bytes:
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def int(self) -> int:
        return struct.unpack(">i", self.take(4))[0]

    def length(self) -> int:
        n = self.int()
        if n == -1:  # long vector: two integers
            high, low = struct.unpack(">II", self.take(8))
            n = (high << 32) + low
        return n

    def attributes(self, flags: int) -> dict:
        if not flags & (1 << 9):
            return {}
        return {tag: value for tag, value in (self.item() or [])}

    def item(self):
        flags = self.int()
        kind = flags & 0xFF
        if kind in (254, 253, 252, 251, 250, 242, 241):  # NULL and special environments
            return None
        if kind == 255:  # reference to an already-read symbol
            index = flags >> 8 or self.int()
            return self.refs[index - 1]
        if kind == 1:  # symbol
            name = self.item()
            self.refs.append(name)
            return name
        if kind in (2, 6):  # pairlist (attributes, or the file contents)
            pairs = []
            while kind in (2, 6):
                if flags & (1 << 9):
                    self.item()
                tag = self.item() if flags & (1 << 10) else None
                pairs.append((tag, self.item()))
                flags = self.int()
                kind = flags & 0xFF
            if kind != 254:
                raise ValueError("Pairlist with an unexpected terminator")
            return pairs
        if kind == 9:  # string
            n = self.int()
            if n == -1:
                return None
            raw = self.take(n)
            return raw.decode("latin-1" if flags >> 12 & 4 else "utf-8", errors="replace")
        if kind in (10, 13):  # logicals or integers
            n = self.length()
            values = np.frombuffer(self.take(4 * n), dtype=">i4").astype(np.int64)
            return _Vector(values, self.attributes(flags), integer=True)
        if kind == 14:  # doubles
            n = self.length()
            values = np.frombuffer(self.take(8 * n), dtype=">f8").astype(float)
            return _Vector(values, self.attributes(flags))
        if kind == 16:  # string vector
            values = [self.item() for _ in range(self.length())]
            return _Vector(np.array(values, dtype=object), self.attributes(flags))
        if kind in (19, 20):  # list
            values = [self.item() for _ in range(self.length())]
            return _Vector(values, self.attributes(flags))
        if kind == 238:  # compact representation (ALTREP): class, state and attributes
            info, state, attributes = self.item(), self.item(), self.item()
            name = info[0][1] if info else ""
            if name == "compact_intseq":  # (n, start, step)
                n, start, step = (int(v) for v in state.values)
                return _Vector(np.arange(n) * step + start, {}, integer=True)
            if isinstance(state, _Vector) and isinstance(state.values, list):  # wrapper: (values, metadata)
                state = state.values[0]
            if isinstance(state, _Vector):
                state.attributes.update({tag: value for tag, value in (attributes or [])})
            return state
        raise ValueError(f"Unexpected R object type: {kind}")


class _Vector:
    def __init__(self, values, attributes: dict, integer: bool = False):
        self.values, self.attributes, self.integer = values, attributes, integer

    def column(self):
        levels = self.attributes.get("levels")
        if levels is not None:  # factor: integers pointing to labels
            labels = np.asarray(levels.values, dtype=object)
            codes = self.values
            return pd.Categorical.from_codes(np.where(codes == _NA_INT, -1, codes - 1), categories=list(labels))
        if self.integer:
            return np.where(self.values == _NA_INT, np.nan, self.values.astype(float))
        return self.values


def read_rda(path) -> dict[str, pd.DataFrame]:
    """Tables stored in an R .rda file, by name."""
    raw = Path(path).read_bytes()
    for magic, opener in ((b"\x1f\x8b", gzip.decompress), (b"BZh", bz2.decompress), (b"\xfd7zXZ", lzma.decompress)):
        if raw.startswith(magic):
            raw = opener(raw)
            break
    if raw[:5] not in (b"RDX2\n", b"RDX3\n") or raw[5:7] != b"X\n":
        raise ValueError("Not an XDR-format .rda file")
    reader = _Reader(raw)
    reader.pos = 7
    version = reader.int()
    reader.int(), reader.int()  # R version that wrote it and minimum version to read it
    if version >= 3:
        reader.take(reader.int())  # native encoding
    tables = {}
    for name, obj in reader.item():
        if isinstance(obj, _Vector) and isinstance(obj.values, list) and "names" in obj.attributes:
            names = list(obj.attributes["names"].values)
            tables[name] = pd.DataFrame({n: v.column() for n, v in zip(names, obj.values)})
    return tables
