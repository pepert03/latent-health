"""Preguntas de contexto de una muestra de orina hecha en casa.

El ejercicio intenso, la fiebre, la regla o una infección de orina elevan la albúmina de
una muestra sin que haya daño renal. El modelo ya contempla esas elevaciones transitorias
sin saber su causa; si el paciente contesta unas preguntas, la probabilidad de elevación
de esa muestra sube (si hay una causa) o baja (si las descarta todas).

Los efectos son **supuestos razonables, no están ajustados con datos**: NHANES no pregunta
por el contexto de la muestra. Con los datos de uso (muestras repetidas con sus respuestas)
se pueden estimar igual que el resto del modelo.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np


@dataclass(frozen=True)
class ContextFactor:
    odds_ratio: float  # cuánto multiplica la odds de elevación transitoria
    prevalence: float  # frecuencia entre las muestras de quien puede tenerlo
    wait_days: int  # días que conviene esperar antes de hacer la prueba
    question: str
    advice: str
    women_under: float | None = None  # solo aplica a mujeres por debajo de esta edad


FACTORS: dict[str, ContextFactor] = {
    "exercise_24h": ContextFactor(
        3.0, 0.10, 2, "¿Has hecho ejercicio intenso en las últimas 24 horas?", "Espera dos días sin ejercicio intenso."
    ),
    "fever": ContextFactor(3.0, 0.02, 3, "¿Tienes fiebre hoy o la has tenido ayer?", "Espera tres días después de que pase la fiebre."),
    "menstruation": ContextFactor(
        8.0, 0.15, 5, "¿Tienes la regla?", "Espera tres días después de que termine la regla.", women_under=56.0
    ),
    "uti_symptoms": ContextFactor(
        4.0,
        0.03,
        10,
        "¿Notas escozor al orinar o tienes una infección de orina?",
        "Consulta en tu centro de salud y repite la prueba cuando la infección esté tratada.",
    ),
    # Almohadillas de una tira multiparamétrica (no son preguntas).
    "blood_pad": ContextFactor(6.0, 0.05, 5, "Sangre en la tira", "Repite la prueba en unos días."),
    "leukocytes_pad": ContextFactor(3.0, 0.07, 5, "Leucocitos en la tira", "Repite la prueba en unos días."),
}
QUESTIONS = ("exercise_24h", "fever", "menstruation", "uti_symptoms")


@dataclass(frozen=True)
class SampleContext:
    """Respuestas del paciente sobre la muestra. ``None`` = no contestado."""

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
    """Desplazamiento del logit de elevación transitoria de la muestra.

    Cada factor contestado suma ``log(OR)`` si está presente y, en todo caso, resta
    ``log(1 - π + π·OR)``: así la probabilidad media sobre el contexto sigue siendo la que
    se ajustó sin conocerlo, y contestar "no" a todo baja la probabilidad de elevación.
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
    """Días que conviene esperar antes de la prueba y los consejos que lo explican."""
    if context is None:
        return 0, []
    days, advice = 0, []
    for name in QUESTIONS:
        if getattr(context, name) and applies(name, female, age):
            days = max(days, FACTORS[name].wait_days)
            advice.append(FACTORS[name].advice)
    return days, advice


def questions(female: bool, age: float) -> list[tuple[str, str]]:
    """Preguntas (clave, texto) que hay que hacer a este paciente antes de la prueba."""
    return [(name, FACTORS[name].question) for name in QUESTIONS if applies(name, female, age)]
