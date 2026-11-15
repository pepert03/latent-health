"""Decision thresholds from clinical utility, and net benefit to check them.

A probability threshold is a judgement about costs: ordering a test when P ≥ 5% means
accepting up to 20 tests per case found. Thresholds are written that way here, so the clinical
team can discuss them in their own terms, and they are checked with decision curves
(``scripts/validate_robustness.py``): at that threshold, does the model beat testing everyone
or no one?
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .i18n import t


def threshold_from_tests_per_case(tests: float) -> float:
    """Probability threshold when ``tests`` tests per case found are accepted."""
    if tests < 1:
        raise ValueError(t("Hace falta al menos una prueba por caso.", "At least one test per case is required."))
    return 1.0 / tests


@dataclass(frozen=True)
class Utilities:
    """Costs and benefits in units of "one more test".

    - ``tests_*``: how many tests are accepted per case found.
    - ``missed_albuminuria``: how many strips or samples it is worth to not miss an albuminuria
      (sets the rule-out threshold).
    - ``false_label``: how many extra samples it is worth to not label someone without
      albuminuria as having it (sets the "very likely" threshold).
    """

    missed_albuminuria: float = 20.0
    false_label: float = 20.0
    tests_creatinine: float = 20.0
    # Hidden diabetes, in two steps (reports/diabetes_en_casa.md). First a capillary glucose, at the
    # pharmacy or with a meter, for those the record leaves with enough probability: at 50 readings
    # per case fewer than half of the undiagnosed are tested and they hold 85% of hidden diabetes.
    # Then the lab test, for those still above threshold with their glucose: at 50 the same number
    # of lab tests as with FINDRISC are ordered and 75% are found.
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
    """Probabilities above which to act. Defaults are those of ``Utilities()``."""

    albuminuria_discard: float = 0.05
    albuminuria_confirm: float = 0.95
    creatinine: float = 0.05  # order creatinine if P(eGFR < 60) exceeds it
    hba1c: float = 0.02  # order HbA1c if, with glucose already measured, P(undiagnosed diabetes) exceeds it
    nt_probnp: float = 0.30  # order NT-proBNP if P(≥ 125 pg/ml) exceeds it
    ecg: float = 0.10  # order an ECG if P(atrial fibrillation) exceeds it
    echo: float = 0.05  # order NT-proBNP and echocardiogram if P(low ejection fraction) exceeds it
    home_glucose: float = 0.02  # measure capillary glucose (pharmacy or meter) if P(undiagnosed diabetes) exceeds it


def net_benefit(y, p, threshold: float) -> float:
    """Net benefit of acting when p ≥ threshold: true positives minus weighted false positives."""
    y = np.asarray(y, dtype=bool)
    act = np.asarray(p, dtype=float) >= threshold
    n = y.size
    return float((act & y).sum() / n - (act & ~y).sum() / n * threshold / (1.0 - threshold))


def decision_curve(y, p, thresholds) -> dict[str, np.ndarray]:
    """Net benefit of the model, of treating all and of treating none, at each threshold.

    The dict keys ("umbral", "modelo", "todos", "nadie") are machine keys used by scripts and tests.
    """
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
    """Tests the model saves per 100 people versus testing everyone, without losing net benefit."""
    curve = decision_curve(y, p, [threshold])
    gain = curve["modelo"][0] - max(curve["todos"][0], 0.0)
    return float(100.0 * gain * (1.0 - threshold) / threshold)
