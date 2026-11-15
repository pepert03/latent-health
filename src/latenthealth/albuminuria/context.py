"""Context questions for a urine sample taken at home.

Intense exercise, fever, menstruation or a urinary tract infection raise a sample's albumin
without any kidney damage. The model already allows for these transient elevations without
knowing their cause; if the patient answers a few questions, the sample's elevation
probability goes up (if there is a cause) or down (if all causes are ruled out).

The effects are **reasonable assumptions, not fitted to data**: NHANES does not ask about
sample context. With usage data (repeated samples with their answers) they can be estimated
like the rest of the model.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from ..i18n import t


@dataclass(frozen=True)
class ContextFactor:
    odds_ratio: float  # how much it multiplies the odds of a transient elevation
    prevalence: float  # frequency among samples of people who can have it
    wait_days: int  # days to wait before testing
    question_text: tuple[str, str]  # (es, en)
    advice_text: tuple[str, str]  # (es, en)
    women_under: float | None = None  # only applies to women under this age

    @property
    def question(self) -> str:
        return t(*self.question_text)

    @property
    def advice(self) -> str:
        return t(*self.advice_text)


_REPEAT = ("Repite la prueba en unos días.", "Repeat the test in a few days.")
FACTORS: dict[str, ContextFactor] = {
    "exercise_24h": ContextFactor(
        3.0,
        0.10,
        2,
        ("¿Has hecho ejercicio intenso en las últimas 24 horas?", "Have you done intense exercise in the last 24 hours?"),
        ("Espera dos días sin ejercicio intenso.", "Wait two days without intense exercise."),
    ),
    "fever": ContextFactor(
        3.0,
        0.02,
        3,
        ("¿Tienes fiebre hoy o la has tenido ayer?", "Do you have a fever today, or did you have one yesterday?"),
        ("Espera tres días después de que pase la fiebre.", "Wait three days after the fever is gone."),
    ),
    "menstruation": ContextFactor(
        8.0,
        0.15,
        5,
        ("¿Tienes la regla?", "Are you on your period?"),
        ("Espera tres días después de que termine la regla.", "Wait three days after your period ends."),
        women_under=56.0,
    ),
    "uti_symptoms": ContextFactor(
        4.0,
        0.03,
        10,
        ("¿Notas escozor al orinar o tienes una infección de orina?", "Does it burn when you urinate, or do you have a urinary tract infection?"),
        (
            "Consulta en tu centro de salud y repite la prueba cuando la infección esté tratada.",
            "See your health center and repeat the test once the infection has been treated.",
        ),
    ),
    # Pads of a multi-parameter strip (not questions).
    "blood_pad": ContextFactor(6.0, 0.05, 5, ("Sangre en la tira", "Blood on the strip"), _REPEAT),
    "leukocytes_pad": ContextFactor(3.0, 0.07, 5, ("Leucocitos en la tira", "Leukocytes on the strip"), _REPEAT),
}
QUESTIONS = ("exercise_24h", "fever", "menstruation", "uti_symptoms")


@dataclass(frozen=True)
class SampleContext:
    """Patient answers about the sample. ``None`` = not answered."""

    exercise_24h: bool | None = None
    fever: bool | None = None
    menstruation: bool | None = None
    uti_symptoms: bool | None = None
    blood_pad: bool | None = None
    leukocytes_pad: bool | None = None


def applies(name: str, female: bool, age: float) -> bool:
    limit = FACTORS[name].women_under
    return limit is None or (bool(female) and age < limit)


def spike_offset(context: SampleContext | None, female: bool, age: float) -> float:
    """Shift of the sample's transient-elevation logit.

    Each answered factor adds ``log(OR)`` if present and always subtracts
    ``log(1 - π + π·OR)``: so the probability averaged over the context stays the one fitted
    without knowing it, and answering "no" to everything lowers the elevation probability.
    """
    if context is None:
        return 0.0
    total = 0.0
    for f in fields(context):
        answer = getattr(context, f.name)
        if answer is None or not applies(f.name, female, age):
            continue
        factor = FACTORS[f.name]
        total -= float(np.log(1.0 - factor.prevalence + factor.prevalence * factor.odds_ratio))
        if answer:
            total += float(np.log(factor.odds_ratio))
    return total


def deferral(context: SampleContext | None, female: bool, age: float) -> tuple[int, list[str]]:
    """Days to wait before the test and the advice that explains it."""
    if context is None:
        return 0, []
    days, advice = 0, []
    for name in QUESTIONS:
        if getattr(context, name) and applies(name, female, age):
            days = max(days, FACTORS[name].wait_days)
            advice.append(FACTORS[name].advice)
    return days, advice


def questions(female: bool, age: float) -> list[tuple[str, str]]:
    """Questions (key, text) to ask this patient before the test."""
    return [(name, FACTORS[name].question) for name in QUESTIONS if applies(name, female, age)]
