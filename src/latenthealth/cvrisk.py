"""Cardiovascular risk: SCORE2, SCORE2-OP and the European prevention guideline categories (ESC 2021).

The challenge asks to detect and prioritise **cardiovascular risk**. The European guideline has
three categories (low or moderate, high, very high) and kidney disease changes them on its own:
a low eGFR or albuminuria moves a patient up a category even with a low SCORE2. That is why
testing the urine can change the risk of someone who looks low-risk today.

Computed here:
- SCORE2 (ages 40-69) and SCORE2-OP (70 or over): 10-year risk of myocardial infarction, stroke
  or cardiovascular death. Spain is a low-risk region. Published coefficients (Eur Heart J 2021;
  42:2439 and 42:2455), checked against an open implementation.
- The ESC 2021 category with kidney disease, diabetes and cardiovascular disease.
- The **probability of each category** when data are missing, propagating the uncertainty of
  eGFR, albuminuria and cholesterol, and the probability that completing the tests moves the
  patient up a category (which orders the practice-list worklist).

Limitations: for people with diabetes the current guideline uses SCORE2-Diabetes, which is not
implemented; the 2021 categories (target-organ damage) are used. The SCORE2 "CKD add-on", which
adjusts risk continuously with eGFR and albuminuria, is not implemented either.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .i18n import Labels, t

MGDL_PER_MMOL = 38.67
LOW, HIGH, VERY_HIGH = 0, 1, 2
class _LabelSeq(Sequence):
    """Read-only tuple of (es, en) pairs that resolves to the current language on access."""

    def __init__(self, *pairs: tuple[str, str]):
        self._pairs = pairs

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(t(es, en) for es, en in self._pairs[index])
        es, en = self._pairs[index]
        return t(es, en)

    def __len__(self) -> int:
        return len(self._pairs)


# Indexed by category (LOW, HIGH, VERY_HIGH).
CATEGORY_LABELS = _LabelSeq(("bajo o moderado", "low or moderate"), ("alto", "high"), ("muy alto", "very high"))
G_LABELS = ("G1", "G2", "G3a", "G3b", "G4", "G5")
A_LABELS = ("A1", "A2", "A3")
# Display names for the pending-test keys of ``p_up_by_test``/``finding_by_test``. The keys are
# machine values read by the web front end and the worklist: do not translate them.
TEST_LABELS = Labels(
    {
        "orina": ("orina", "urine"),
        "creatinina": ("creatinina", "creatinine"),
        "lípidos": ("lípidos", "lipids"),
        "glucosa": ("glucosa", "glucose"),
        "HbA1c": ("HbA1c", "HbA1c"),
        "ecocardiograma": ("ecocardiograma", "echocardiogram"),
    }
)

# (age, smoking, blood pressure, total cholesterol, HDL, diabetes; age interactions in the same order)
_SCORE2 = {
    False: dict(main=(0.3742, 0.6012, 0.2777, 0.1458, -0.2698, 0.6457), inter=(-0.0755, -0.0255, -0.0281, 0.0426, -0.0983), s0=0.9605),
    True: dict(main=(0.4648, 0.7744, 0.3131, 0.1002, -0.2606, 0.8096), inter=(-0.1088, -0.0277, -0.0226, 0.0613, -0.1272), s0=0.9776),
}
_SCORE2_OP = {
    False: dict(main=(0.0634, 0.3524, 0.0094, 0.0850, -0.3564, 0.4245), inter=(-0.0247, -0.0005, 0.0073, 0.0091, -0.0174), s0=0.7576, mean=0.0929),
    True: dict(main=(0.0789, 0.4921, 0.0102, 0.0605, -0.3040, 0.6010), inter=(-0.0255, -0.0004, -0.0009, 0.0154, -0.0107), s0=0.8082, mean=0.229),
}
# Regional recalibration: (scale 1, scale 2) for men (False) and women (True).
_SCALES = {
    "low": {False: (-0.5699, 0.7476), True: (-0.7380, 0.7019)},
    "moderate": {False: (-0.1565, 0.8009), True: (-0.3143, 0.7701)},
    "high": {False: (0.3207, 0.9360), True: (0.5710, 0.9369)},
    "very_high": {False: (0.5836, 0.8294), True: (0.9412, 0.8329)},
}
_SCALES_OP = {
    "low": {False: (-0.34, 1.19), True: (-0.52, 1.01)},
    "moderate": {False: (0.01, 1.25), True: (-0.10, 1.10)},
    "high": {False: (0.08, 1.15), True: (0.38, 1.09)},
    "very_high": {False: (0.05, 0.70), True: (0.38, 0.69)},
}


def score2(age, female, smoker, sbp, total_cholesterol, hdl, diabetes=False, region="low", units="mg/dl"):
    """10-year cardiovascular risk (fraction 0-1). Accepts arrays for blood pressure and cholesterol.

    Uses SCORE2 up to age 69 and SCORE2-OP from 70. Age is clipped to 40-89. For people with
    diabetes the value is indicative only: the guideline does not recommend SCORE2 for them.
    """
    female, smoker, diabetes = bool(female), float(bool(smoker)), float(bool(diabetes))
    age = float(np.clip(age, 40.0, 89.0))
    sbp = np.asarray(sbp, dtype=float)
    tc = np.asarray(total_cholesterol, dtype=float)
    hdl = np.asarray(hdl, dtype=float)
    if units == "mg/dl":
        tc, hdl = tc / MGDL_PER_MMOL, hdl / MGDL_PER_MMOL
    if age < 70:
        c = _SCORE2[female]
        a, s, t, h = (age - 60.0) / 5.0, (sbp - 120.0) / 20.0, tc - 6.0, (hdl - 1.3) / 0.5
        scale1, scale2 = _SCALES[region][female]
        shift = 0.0
    else:
        c = _SCORE2_OP[female]
        a, s, t, h = age - 73.0, sbp - 150.0, tc - 6.0, hdl - 1.4
        scale1, scale2 = _SCALES_OP[region][female]
        shift = c["mean"]
    b_age, b_smoke, b_sbp, b_tc, b_hdl, b_dm = c["main"]
    i_smoke, i_sbp, i_tc, i_hdl, i_dm = c["inter"]
    lp = (
        b_age * a
        + b_smoke * smoker
        + b_sbp * s
        + b_tc * t
        + b_hdl * h
        + b_dm * diabetes
        + a * (i_smoke * smoker + i_sbp * s + i_tc * t + i_hdl * h + i_dm * diabetes)
    )
    uncalibrated = 1.0 - c["s0"] ** np.exp(lp - shift)
    uncalibrated = np.clip(uncalibrated, 1e-9, 1 - 1e-9)
    return 1.0 - np.exp(-np.exp(scale1 + scale2 * np.log(-np.log(1.0 - uncalibrated))))


def score_category(age: float, risk) -> np.ndarray:
    """ESC 2021 category from SCORE2 by age (0 low or moderate, 1 high, 2 very high)."""
    risk = np.asarray(risk, dtype=float)
    high, very_high = (0.025, 0.075) if age < 50 else (0.05, 0.10) if age < 70 else (0.075, 0.15)
    return (risk >= high).astype(int) + (risk >= very_high).astype(int)


# Category given by kidney disease alone (rows G1...G5, columns A1, A2, A3).
# ESC 2021: severe CKD (eGFR < 30, or eGFR 30-44 with albuminuria) = very high; moderate CKD (eGFR
# 30-44 without albuminuria, eGFR 45-59 with 30-300 mg/g, or eGFR ≥ 60 with > 300 mg/g) = high. The
# guideline does not name eGFR 45-59 with > 300 mg/g: set to very high, as in the KDIGO heat map.
CKD_CATEGORY = np.array(
    [
        [LOW, LOW, HIGH],  # G1
        [LOW, LOW, HIGH],  # G2
        [LOW, HIGH, VERY_HIGH],  # G3a
        [HIGH, VERY_HIGH, VERY_HIGH],  # G3b
        [VERY_HIGH, VERY_HIGH, VERY_HIGH],  # G4
        [VERY_HIGH, VERY_HIGH, VERY_HIGH],  # G5
    ]
)
# Type 2 diabetes (ESC 2021): high, except severe target-organ damage (eGFR < 45, eGFR 45-59 with
# albuminuria, or proteinuria), which is very high.
DIABETES_CATEGORY = np.array(
    [
        [HIGH, HIGH, VERY_HIGH],
        [HIGH, HIGH, VERY_HIGH],
        [HIGH, VERY_HIGH, VERY_HIGH],
        [VERY_HIGH, VERY_HIGH, VERY_HIGH],
        [VERY_HIGH, VERY_HIGH, VERY_HIGH],
        [VERY_HIGH, VERY_HIGH, VERY_HIGH],
    ]
)


def category_matrix(diabetes: bool, ascvd: bool, diabetes_low_risk: bool = False) -> np.ndarray:
    """Minimum category from kidney disease, diabetes and cardiovascular disease, (6, 3)."""
    if ascvd:
        return np.full((6, 3), VERY_HIGH)
    out = CKD_CATEGORY.copy()
    if diabetes:
        dm = DIABETES_CATEGORY.copy()
        if diabetes_low_risk:  # under 10 years' duration, well controlled and no other risk factors
            dm = np.where(dm == HIGH, LOW, dm)
            dm = np.maximum(dm, CKD_CATEGORY)
        out = np.maximum(out, dm)
    return out


@dataclass
class CvRisk:
    score: float  # SCORE2 or SCORE2-OP (median if data are missing), fraction
    score_low: float
    score_high: float
    probs: np.ndarray  # P(true category) given everything that is unknown
    recorded: int  # category from what is already on record
    p_up: float  # P(true category is higher than the recorded one)
    p_up_by_test: dict[str, float] = field(default_factory=dict)  # if only that test were done
    approximate: bool = False  # some data were assumed (blood pressure or HDL)
    # New finding: moves up a category or reveals unrecorded kidney disease
    # (eGFR < 60 or albuminuria in a test still to be done).
    p_finding: float = 0.0
    finding_by_test: dict[str, float] = field(default_factory=dict)

    @property
    def category(self) -> int:
        return int(np.argmax(self.probs))

    @property
    def best_test(self) -> str | None:
        """The pending test most likely to give a new finding."""
        by_test = self.finding_by_test or self.p_up_by_test
        if not by_test:
            return None
        test = max(by_test, key=by_test.get)
        return test if by_test[test] > 0 else None


def assess_cv(
    age: float,
    joint: np.ndarray,
    score_values,
    score_weights,
    diabetes: bool,
    ascvd: bool,
    recorded_g: int | None,
    recorded_a: int | None,
    score_recorded: float,
    score_pending: bool = False,
    approximate: bool = False,
    diabetes_low_risk: bool = False,
    ckd_recorded: bool = False,
) -> CvRisk:
    """Risk category with its uncertainty and what each test would change.

    - ``joint``: P(G category, A category), (6, 3).
    - ``score_values`` and ``score_weights``: SCORE2 distribution (a single value if lipids and
      blood pressure are measured).
    - ``recorded_g`` and ``recorded_a``: categories already on record (None if not measured; they
      are then taken as normal, which is what happens in practice: no test, no kidney diagnosis).
    - ``score_recorded``: SCORE2 with the recorded data. If lipids or blood pressure are missing
      (``score_pending``), it is the most likely value with typical data: the doctor can
      approximate it, and completing the labs only matters if it would change the category.
    - ``ckd_recorded``: chronic kidney disease is already a recorded diagnosis.

    Besides moving up a category it computes the probability of a **new finding**: moving up or
    finding unrecorded kidney disease (eGFR < 60 or albuminuria ≥ 30 mg/g in a pending test).
    Albuminuria with normal eGFR does not change the guideline category, but it does change the
    diagnosis and treatment, so the worklist ranks by new finding.
    """
    joint = np.asarray(joint, dtype=float)
    joint = joint / joint.sum()
    values = np.atleast_1d(np.asarray(score_values, dtype=float))
    weights = np.atleast_1d(np.asarray(score_weights, dtype=float))
    weights = weights / weights.sum()
    organ = category_matrix(diabetes, ascvd, diabetes_low_risk)  # (6, 3)
    by_score = score_category(age, values)  # (S,)

    g0 = 0 if recorded_g is None else recorded_g
    a0 = 0 if recorded_a is None else recorded_a
    s0 = int(score_category(age, score_recorded))
    recorded = int(max(organ[g0, a0], s0))

    true_cat = np.maximum(organ[:, :, None], by_score[None, None, :])  # (6, 3, S)
    mass = joint[:, :, None] * weights[None, None, :]
    probs = np.array([mass[true_cat == k].sum() for k in (LOW, HIGH, VERY_HIGH)])
    p_up = float(mass[true_cat > recorded].sum())

    # Unrecorded kidney disease that a pending test would uncover.
    new_g = np.arange(6) >= 2 if (recorded_g is None and not ckd_recorded) else np.zeros(6, bool)
    new_a = np.arange(3) >= 1 if (recorded_a is None and not ckd_recorded) else np.zeros(3, bool)
    new_ckd = new_g[:, None] | new_a[None, :]
    p_finding = float(mass[(true_cat > recorded) | new_ckd[:, :, None]].sum())

    by_test, finding_by_test = {}, {}
    if recorded_a is None:  # urine only
        p_a = joint.sum(axis=0)
        up = np.maximum(organ[g0, :], s0) > recorded
        by_test["orina"] = float(p_a[up].sum())
        finding_by_test["orina"] = float(p_a[up | new_a].sum())
    if recorded_g is None:  # creatinine only
        p_g = joint.sum(axis=1)
        up = np.maximum(organ[:, a0], s0) > recorded
        by_test["creatinina"] = float(p_g[up].sum())
        finding_by_test["creatinina"] = float(p_g[up | new_g].sum())
    if score_pending:  # only lipids and blood pressure are completed
        by_test["lípidos"] = float(weights[np.maximum(by_score, organ[g0, a0]) > recorded].sum())
        finding_by_test["lípidos"] = by_test["lípidos"]

    order = np.argsort(values)
    cum = np.cumsum(weights[order])
    q = np.interp([0.1, 0.5, 0.9], cum, values[order]) if values.size > 1 else np.repeat(values[0], 3)
    return CvRisk(
        float(q[1]), float(q[0]), float(q[2]), probs, recorded, p_up, by_test, approximate, p_finding, finding_by_test
    )


def describe(risk: CvRisk) -> str:
    probs = ", ".join(f"{label} {p:.0%}" for label, p in zip(CATEGORY_LABELS, risk.probs))
    score = f"{risk.score:.0%}"
    if f"{risk.score_low:.0%}" != f"{risk.score_high:.0%}":
        score += t(f" (80 %: {risk.score_low:.0%}-{risk.score_high:.0%})", f" (80%: {risk.score_low:.0%}-{risk.score_high:.0%})")
    lines = [
        t(f"SCORE2 a 10 años: {score}", f"10-year SCORE2: {score}")
        + (t(" · con datos supuestos", " · with assumed data") if risk.approximate else ""),
        t("Categoría con lo que consta hoy: ", "Category from what is on record today: ") + CATEGORY_LABELS[risk.recorded],
        t("Categoría real probable: ", "Likely true category: ") + probs,
    ]
    if risk.p_up >= 0.005:
        by_test = sorted(risk.p_up_by_test.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{TEST_LABELS.get(test, test)} {p:.0%}" for test, p in by_test if p >= 0.005)
        lines.append(
            t("Probabilidad de subir de categoría al completar las pruebas: ", "Probability of moving up a category once the tests are done: ")
            + f"{risk.p_up:.0%}"
            + (f" ({detail})" if detail else "")
        )
    return "\n".join(lines)
