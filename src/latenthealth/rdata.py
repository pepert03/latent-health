"""Lector mínimo de ficheros de datos de R (.rda) con tablas de números y factores.

Solo cubre lo necesario para leer una tabla (data.frame) guardada con ``save()``: vectores de
enteros, reales, lógicos y cadenas, listas, factores y atributos. Evita depender de R o de un
paquete externo para un único fichero de datos.
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
        if n == -1:  # vector largo: dos enteros
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
        if kind in (254, 253, 252, 251, 250, 242, 241):  # NULL y entornos especiales
            return None
        if kind == 255:  # referencia a un símbolo ya leído
            index = flags >> 8 or self.int()
            return self.refs[index - 1]
        if kind == 1:  # símbolo
            name = self.item()
            self.refs.append(name)
            return name
        if kind in (2, 6):  # lista de pares (atributos, o el contenido del fichero)
            pairs = []
            while kind in (2, 6):
                if flags & (1 << 9):
                    self.item()
                tag = self.item() if flags & (1 << 10) else None
                pairs.append((tag, self.item()))
                flags = self.int()
                kind = flags & 0xFF
            if kind != 254:
                raise ValueError("Lista de pares con un final no previsto")
            return pairs
        if kind == 9:  # cadena
            n = self.int()
            if n == -1:
                return None
            raw = self.take(n)
            return raw.decode("latin-1" if flags >> 12 & 4 else "utf-8", errors="replace")
        if kind in (10, 13):  # lógicos o enteros
            n = self.length()
            values = np.frombuffer(self.take(4 * n), dtype=">i4").astype(np.int64)
            return _Vector(values, self.attributes(flags), integer=True)
        if kind == 14:  # reales
            n = self.length()
            values = np.frombuffer(self.take(8 * n), dtype=">f8").astype(float)
            return _Vector(values, self.attributes(flags))
        if kind == 16:  # vector de cadenas
            values = [self.item() for _ in range(self.length())]
            return _Vector(np.array(values, dtype=object), self.attributes(flags))
        if kind in (19, 20):  # lista
            values = [self.item() for _ in range(self.length())]
            return _Vector(values, self.attributes(flags))
        if kind == 238:  # representación compacta (ALTREP): clase, estado y atributos
            info, state, attributes = self.item(), self.item(), self.item()
            name = info[0][1] if info else ""
            if name == "compact_intseq":  # (n, inicio, paso)
                n, start, step = (int(v) for v in state.values)
                return _Vector(np.arange(n) * step + start, {}, integer=True)
            if isinstance(state, _Vector) and isinstance(state.values, list):  # envoltorio: (valores, metadatos)
                state = state.values[0]
            if isinstance(state, _Vector):
                state.attributes.update({tag: value for tag, value in (attributes or [])})
            return state
        raise ValueError(f"Tipo de objeto de R no previsto: {kind}")


class _Vector:
    def __init__(self, values, attributes: dict, integer: bool = False):
        self.values, self.attributes, self.integer = values, attributes, integer

    def column(self):
        levels = self.attributes.get("levels")
        if levels is not None:  # factor: enteros que apuntan a etiquetas
            labels = np.asarray(levels.values, dtype=object)
            codes = self.values
            return pd.Categorical.from_codes(np.where(codes == _NA_INT, -1, codes - 1), categories=list(labels))
        if self.integer:
            return np.where(self.values == _NA_INT, np.nan, self.values.astype(float))
        return self.values


def read_rda(path) -> dict[str, pd.DataFrame]:
    """Tablas guardadas en un fichero .rda de R, por nombre."""
    raw = Path(path).read_bytes()
    for magic, opener in ((b"\x1f\x8b", gzip.decompress), (b"BZh", bz2.decompress), (b"\xfd7zXZ", lzma.decompress)):
        if raw.startswith(magic):
            raw = opener(raw)
            break
    if raw[:5] not in (b"RDX2\n", b"RDX3\n") or raw[5:7] != b"X\n":
        raise ValueError("No es un fichero .rda en formato XDR")
    reader = _Reader(raw)
    reader.pos = 7
    version = reader.int()
    reader.int(), reader.int()  # versión de R que lo escribió y mínima para leerlo
    if version >= 3:
        reader.take(reader.int())  # codificación nativa
    tables = {}
    for name, obj in reader.item():
        if isinstance(obj, _Vector) and isinstance(obj.values, list) and "names" in obj.attributes:
            names = list(obj.attributes["names"].values)
            tables[name] = pd.DataFrame({n: v.column() for n, v in zip(names, obj.values)})
    return tables
