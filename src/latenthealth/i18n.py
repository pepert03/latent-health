"""Two-language user-facing text (Spanish for Spain, English for everyone else).

The language lives in a context variable so each web request can set its own
without threading a parameter through every function. Default: English.

    from latenthealth.i18n import t, fmt_num, fmt_pct, fmt_date
    msg = t("Repite mañana", "Repeat tomorrow")
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token

LANGS = ("es", "en")
DEFAULT_LANG = "en"
LANG: ContextVar[str] = ContextVar("latenthealth_lang", default=DEFAULT_LANG)

_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip
_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def normalize(code: str | None) -> str:
    """'es', 'es-ES', 'ES' -> 'es'; anything else -> 'en'."""
    return "es" if code and code.strip().lower().startswith("es") else "en"


def lang() -> str:
    """Current language: 'es' or 'en'."""
    return LANG.get()


def is_es() -> bool:
    return LANG.get() == "es"


def set_lang(code: str | None) -> Token:
    """Set the language for the current context; returns a token for `reset_lang`."""
    return LANG.set(normalize(code))


def reset_lang(token: Token) -> None:
    LANG.reset(token)


@contextmanager
def use_lang(code: str | None) -> Iterator[None]:
    """`with use_lang("es"): ...` runs the block in that language."""
    token = set_lang(code)
    try:
        yield
    finally:
        LANG.reset(token)


def t(es: str, en: str) -> str:
    """Pick the Spanish or English version of a text."""
    return es if LANG.get() == "es" else en


def lang_from_headers(x_lang: str | None, accept_language: str | None) -> str:
    """Language of an HTTP request: `X-Lang` (es|en) wins; else the first `Accept-Language` entry."""
    if x_lang and x_lang.strip():
        return normalize(x_lang)
    if accept_language:
        first = accept_language.split(",")[0].split(";")[0]
        return normalize(first)
    return DEFAULT_LANG


def fmt_num(value: float, decimals: int = 0, signed: bool = False) -> str:
    """Number with thousands separator: '3.333' / '5,8' in Spanish, '3,333' / '5.8' in English."""
    text = f"{value:+,.{decimals}f}" if signed else f"{value:,.{decimals}f}"
    if is_es():
        text = text.translate(str.maketrans({",": ".", ".": ","}))
    return text


def fmt_pct(fraction: float, decimals: int = 0) -> str:
    """Percentage from a fraction: '14 %' / '1,8 %' in Spanish, '14%' / '1.8%' in English."""
    number = f"{100 * fraction:.{decimals}f}"
    return f"{number.replace('.', ',')} %" if is_es() else f"{number}%"


def fmt_date(day: dt.date, weekday: bool = True, year: bool = True) -> str:
    """Long date: 'martes 17 de noviembre de 2026' / 'Tuesday, November 17, 2026'."""
    if is_es():
        text = f"{day.day} de {_MONTHS_ES[day.month - 1]}"
        if year:
            text += f" de {day.year}"
        return f"{_WEEKDAYS_ES[day.weekday()]} {text}" if weekday else text
    text = f"{_MONTHS_EN[day.month - 1]} {day.day}"
    if year:
        text += f", {day.year}"
    return f"{_WEEKDAYS_EN[day.weekday()]}, {text}" if weekday else text


def fmt_short_date(day: dt.date) -> str:
    """Numeric date: '17/11/2026' / '11/17/2026'."""
    return day.strftime("%d/%m/%Y") if is_es() else day.strftime("%m/%d/%Y")


class Labels(Mapping[str, str]):
    """Read-only mapping whose values resolve to the current language on access.

    For module-level label tables (evaluated at import, before any request sets the language):

        ACTION_LABELS = Labels({"tira": ("Tira de orina", "Urine strip"), ...})
        ACTION_LABELS["tira"]  # -> "Urine strip" or "Tira de orina"
    """

    def __init__(self, pairs: Mapping[str, tuple[str, str]]):
        self._pairs = dict(pairs)

    def __getitem__(self, key: str) -> str:
        es, en = self._pairs[key]
        return t(es, en)

    def __iter__(self):
        return iter(self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)

    def pair(self, key: str) -> tuple[str, str]:
        """Both versions: (es, en)."""
        return self._pairs[key]
