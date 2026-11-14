"""Umbrales de decisión a partir de la utilidad clínica, y beneficio neto para comprobarlos.

Un umbral de probabilidad es un juicio sobre costes: pedir una prueba si P ≥ 5 % equivale a
aceptar hasta 20 pruebas por cada caso encontrado. Aquí los umbrales se escriben así, de forma
que el equipo clínico puede discutirlos en sus términos, y se comprueban con curvas de
decisión (``scripts/validate_robustness.py``): con ese umbral, ¿el modelo ayuda más que
pedir la prueba a todos o a nadie?
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def threshold_from_tests_per_case(tests: float) -> float:
    """Umbral de probabilidad si se aceptan ``tests`` pruebas por cada caso encontrado."""
    if tests < 1:
        raise ValueError("Hace falta al menos una prueba por caso.")
    return 1.0 / tests


@dataclass(frozen=True)
class Utilities:
    """Costes y beneficios en unidades de "una prueba más".

    - ``tests_*``: cuántas pruebas se aceptan por cada caso que se encuentre.
    - ``missed_albuminuria``: cuántas tiras o muestras vale no dejar escapar una albuminuria
      (fija el umbral para descartar).
    - ``false_label``: cuántas muestras más vale no etiquetar de albuminuria a alguien que no la
      tiene (fija el umbral para darla por muy probable).
    """

    missed_albuminuria: float = 20.0
    false_label: float = 20.0
    tests_creatinine: float = 20.0
    # Diabetes oculta, en dos pasos (reports/diabetes_en_casa.md). Primero una glucosa capilar, en
    # la farmacia o con glucómetro, a quien la historia deja con probabilidad suficiente: con 50
    # medidas por caso se la hace menos de la mitad de quienes no tienen diagnóstico y ahí está el
    # 85 % de la diabetes oculta. Después el análisis, a quien sigue con probabilidad suficiente ya
    # con su glucosa: con 50 se piden los mismos análisis que con FINDRISC y se encuentra el 75 %.
    tests_home_glucose: float = 50.0
    tests_hba1c: float = 50.0
    tests_nt_probnp: float = 10.0 / 3.0
    tests_ecg: float = 10.0
    tests_echo: float = 20.0

    def thresholds(self) -> "Thresholds":
        return Thresholds(
            albuminuria_discard=1.0 / self.missed_albuminuria,
            albuminuria_confirm=1.0 - 1.0 / self.false_label,
            creatinine=threshold_from_tests_per_case(self.tests_creatinine),
            hba1c=threshold_from_tests_per_case(self.tests_hba1c),
            nt_probnp=threshold_from_tests_per_case(self.tests_nt_probnp),
            ecg=threshold_from_tests_per_case(self.tests_ecg),
            echo=threshold_from_tests_per_case(self.tests_echo),
            home_glucose=threshold_from_tests_per_case(self.tests_home_glucose),
        )


@dataclass(frozen=True)
class Thresholds:
    """Probabilidades a partir de las cuales se actúa. Por defecto, las de ``Utilities()``."""

    albuminuria_discard: float = 0.05
    albuminuria_confirm: float = 0.95
    creatinine: float = 0.05  # pedir creatinina si P(FG < 60) la supera
    hba1c: float = 0.02  # pedir HbA1c si, ya con la glucosa medida, P(diabetes sin diagnosticar) la supera
    nt_probnp: float = 0.30  # pedir NT-proBNP si P(≥ 125 pg/ml) la supera
    ecg: float = 0.10  # pedir ECG si P(fibrilación auricular) la supera
    echo: float = 0.05  # pedir NT-proBNP y ecocardiograma si P(fracción de eyección baja) la supera
    home_glucose: float = 0.02  # medir la glucosa capilar (farmacia o glucómetro) si P(diabetes sin diagnosticar) la supera


def net_benefit(y, p, threshold: float) -> float:
    """Beneficio neto de actuar cuando p ≥ umbral: verdaderos positivos menos falsos ponderados."""
    y = np.asarray(y, dtype=bool)
    act = np.asarray(p, dtype=float) >= threshold
    n = y.size
    return float((act & y).sum() / n - (act & ~y).sum() / n * threshold / (1.0 - threshold))


def decision_curve(y, p, thresholds) -> dict[str, np.ndarray]:
    """Beneficio neto del modelo, de actuar con todos y de no actuar con nadie, para cada umbral."""
    y = np.asarray(y, dtype=bool)
    thresholds = np.asarray(thresholds, dtype=float)
    prevalence = y.mean()
    return {
        "umbral": thresholds,
        "modelo": np.array([net_benefit(y, p, t) for t in thresholds]),
        "todos": prevalence - (1.0 - prevalence) * thresholds / (1.0 - thresholds),
        "nadie": np.zeros_like(thresholds),
    }


def avoided_tests_per_100(y, p, threshold: float) -> float:
    """Pruebas que el modelo ahorra por cada 100 personas, frente a pedirla a todos, sin perder beneficio neto."""
    curve = decision_curve(y, p, [threshold])
    gain = curve["modelo"][0] - max(curve["todos"][0], 0.0)
    return float(100.0 * gain * (1.0 - threshold) / threshold)
