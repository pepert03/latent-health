"""Conversion of model results into values JSON accepts.

The models return dataclasses with dates, numpy scalars and arrays and, sometimes, NaN.
None of that goes through ``json.dumps`` (or it goes badly: ``NaN`` breaks ``JSON.parse`` in the browser).
"""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

import numpy as np


def clean(value: Any, *, exclude: frozenset[str] = frozenset(), digits: int | None = None) -> Any:
    """Returns ``value`` using only JSON types.

    - ``date`` and ``datetime`` -> ISO text (``2026-11-16``).
    - numpy scalars and arrays -> ``float`` / ``int`` / ``bool`` / lists.
    - ``NaN`` and infinities -> ``None``.
    - Dataclasses -> ``dict`` of their fields (not their properties), without the names in ``exclude``.
    - ``Enum`` -> its value; tuples and sets -> lists.

    ``exclude`` applies to dataclass fields and dict keys at any level (for example ``belief``,
    the filter's 400-point distribution). ``digits`` rounds decimals to lighten the response;
    ``None`` leaves them as they are.
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
    raise TypeError(f"Cannot convert a value of type {type(value).__name__} to JSON")
