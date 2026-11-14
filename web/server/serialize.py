"""Conversión de los resultados de los modelos a valores que JSON admite.

Los modelos devuelven dataclasses con fechas, escalares y matrices de numpy y, a veces, NaN.
Nada de eso pasa por ``json.dumps`` (o pasa mal: ``NaN`` rompe ``JSON.parse`` en el navegador).
"""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

import numpy as np


def clean(value: Any, *, exclude: frozenset[str] = frozenset(), digits: int | None = None) -> Any:
    """Devuelve ``value`` con solo tipos de JSON.

    - ``date`` y ``datetime`` -> texto ISO (``2026-11-16``).
    - Escalares y matrices de numpy -> ``float`` / ``int`` / ``bool`` / listas.
    - ``NaN`` e infinitos -> ``None``.
    - Dataclasses -> ``dict`` con sus campos (no sus propiedades), sin los nombres de ``exclude``.
    - ``Enum`` -> su valor; tuplas y conjuntos -> listas.

    ``exclude`` se aplica a los campos de dataclass y a las claves de dict en cualquier nivel
    (por ejemplo ``belief``, la distribución de 400 puntos del filtro). ``digits`` redondea los
    decimales para aligerar la respuesta; ``None`` los deja como están.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, digits) if digits is not None else number
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return clean(value.value, exclude=exclude, digits=digits)
    if isinstance(value, np.ndarray):
        return clean(value.tolist(), exclude=exclude, digits=digits)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: clean(getattr(value, f.name), exclude=exclude, digits=digits)
            for f in fields(value)
            if f.name not in exclude
        }
    if isinstance(value, dict):
        return {
            str(key): clean(item, exclude=exclude, digits=digits)
            for key, item in value.items()
            if key not in exclude
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [clean(item, exclude=exclude, digits=digits) for item in value]
    raise TypeError(f"No sé convertir a JSON un valor de tipo {type(value).__name__}")
