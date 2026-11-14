"""Riesgo cardiovascular: SCORE2, SCORE2-OP y categorías de la guía europea de prevención (ESC 2021).

El reto pide detectar y priorizar el **riesgo cardiovascular**. La guía europea lo clasifica en
tres categorías (bajo o moderado, alto, muy alto) y la enfermedad renal las cambia por sí sola:
un filtrado bajo o una albuminuria suben de categoría a un paciente aunque su SCORE2 sea
bajo. Por eso medir la orina puede cambiar el riesgo de alguien que hoy parece de bajo riesgo.

Aquí se calcula:
- SCORE2 (40-69 años) y SCORE2-OP (70 o más): riesgo a 10 años de infarto, ictus o muerte
  cardiovascular. España es región de riesgo bajo. Coeficientes publicados (Eur Heart J 2021;
  42:2439 y 42:2455), comprobados contra una implementación abierta.
- La categoría ESC 2021 con la enfermedad renal, la diabetes y la enfermedad cardiovascular.
- La **probabilidad de cada categoría** cuando faltan datos, propagando la incertidumbre del
  filtrado, de la albuminuria y del colesterol, y la probabilidad de que completar las
  pruebas suba al paciente de categoría (lo que ordena la lista del cupo).

Límites: en diabéticos la guía actual usa SCORE2-Diabetes, que no está implementado; se usan
las categorías de 2021 (daño de órgano diana). El "complemento de ERC" para SCORE2, que
ajusta el riesgo de forma continua con el filtrado y la albuminuria, tampoco.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MGDL_PER_MMOL = 38.67
LOW, HIGH, VERY_HIGH = 0, 1, 2
CATEGORY_LABELS = ("bajo o moderado", "alto", "muy alto")
G_LABELS = ("G1", "G2", "G3a", "G3b", "G4", "G5")
A_LABELS = ("A1", "A2", "A3")

# (edad, tabaco, tensión, colesterol total, HDL, diabetes; interacciones con la edad en el mismo orden)
_SCORE2 = {
    False: dict(main=(0.3742, 0.6012, 0.2777, 0.1458, -0.2698, 0.6457), inter=(-0.0755, -0.0255, -0.0281, 0.0426, -0.0983), s0=0.9605),
    True: dict(main=(0.4648, 0.7744, 0.3131, 0.1002, -0.2606, 0.8096), inter=(-0.1088, -0.0277, -0.0226, 0.0613, -0.1272), s0=0.9776),
}
_SCORE2_OP = {
    False: dict(main=(0.0634, 0.3524, 0.0094, 0.0850, -0.3564, 0.4245), inter=(-0.0247, -0.0005, 0.0073, 0.0091, -0.0174), s0=0.7576, mean=0.0929),
    True: dict(main=(0.0789, 0.4921, 0.0102, 0.0605, -0.3040, 0.6010), inter=(-0.0255, -0.0004, -0.0009, 0.0154, -0.0107), s0=0.8082, mean=0.229),
}
# Recalibración por región: (escala 1, escala 2) para hombres (False) y mujeres (True).
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
    """Riesgo cardiovascular a 10 años (fracción entre 0 y 1). Admite arrays en tensión y colesterol.

    Usa SCORE2 hasta los 69 años y SCORE2-OP desde los 70. La edad se acota a 40-89. En
    diabéticos el valor es orientativo: la guía no recomienda SCORE2 para ellos.
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
    """Categoría ESC 2021 por el SCORE2 según la edad (0 bajo o moderado, 1 alto, 2 muy alto)."""
    risk = np.asarray(risk, dtype=float)
    high, very_high = (0.025, 0.075) if age < 50 else (0.05, 0.10) if age < 70 else (0.075, 0.15)
    return (risk >= high).astype(int) + (risk >= very_high).astype(int)


# Categoría que da la enfermedad renal por sí sola (filas G1...G5, columnas A1, A2, A3).
# ESC 2021: ERC grave (FG < 30, o FG 30-44 con albuminuria) = muy alto; ERC moderada (FG 30-44
# sin albuminuria, FG 45-59 con 30-300 mg/g, o FG ≥ 60 con > 300 mg/g) = alto. La guía no nombra
# FG 45-59 con > 300 mg/g: se pone muy alto, como en el mapa de riesgo de KDIGO.
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
# Diabetes tipo 2 (ESC 2021): alto, salvo daño grave de órgano diana (FG < 45, FG 45-59 con
# albuminuria, o proteinuria), que es muy alto.
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
    """Categoría mínima por la enfermedad renal, la diabetes y la enfermedad cardiovascular, (6, 3)."""
    if ascvd:
        return np.full((6, 3), VERY_HIGH)
    out = CKD_CATEGORY.copy()
    if diabetes:
        dm = DIABETES_CATEGORY.copy()
        if diabetes_low_risk:  # menos de 10 años de evolución, bien controlada y sin otros factores
            dm = np.where(dm == HIGH, LOW, dm)
            dm = np.maximum(dm, CKD_CATEGORY)
        out = np.maximum(out, dm)
    return out


@dataclass
class CvRisk:
    score: float  # SCORE2 o SCORE2-OP (mediana si faltan datos), fracción
    score_low: float
    score_high: float
    probs: np.ndarray  # P(categoría real) con todo lo que no se sabe
    recorded: int  # categoría con lo que ya consta en la historia
    p_up: float  # P(la categoría real es mayor que la registrada)
    p_up_by_test: dict[str, float] = field(default_factory=dict)  # si solo se hiciera esa prueba
    approximate: bool = False  # se han supuesto datos (tensión o HDL)
    # Hallazgo nuevo: sube de categoría o aparece una enfermedad renal que no consta
    # (FG < 60 o albuminuria en una prueba que falta por hacer).
    p_finding: float = 0.0
    finding_by_test: dict[str, float] = field(default_factory=dict)

    @property
    def category(self) -> int:
        return int(np.argmax(self.probs))

    @property
    def best_test(self) -> str | None:
        """La prueba pendiente con más probabilidad de dar un hallazgo nuevo."""
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
    """Categoría de riesgo con su incertidumbre y lo que cambiaría cada prueba.

    - ``joint``: P(categoría G, categoría A), (6, 3).
    - ``score_values`` y ``score_weights``: distribución del SCORE2 (un solo valor si los
      lípidos y la tensión están medidos).
    - ``recorded_g`` y ``recorded_a``: categorías que ya constan (None si no se han medido; se
      toman entonces como normales, que es lo que ocurre en la práctica: sin prueba no hay
      diagnóstico de enfermedad renal).
    - ``score_recorded``: SCORE2 con los datos que constan. Si faltan los lípidos o la tensión
      (``score_pending``), es el valor más probable con datos típicos: el médico puede
      aproximarlo, y completar la analítica solo importa si lo cambiaría de categoría.
    - ``ckd_recorded``: la enfermedad renal crónica ya consta como diagnóstico.

    Además de la subida de categoría calcula la probabilidad de un **hallazgo nuevo**: subir de
    categoría o encontrar una enfermedad renal que no consta (FG < 60 o albuminuria ≥ 30 mg/g en
    una prueba pendiente). Una albuminuria con FG normal no cambia la categoría de la guía, pero
    sí el diagnóstico y el tratamiento, así que la lista del cupo ordena por el hallazgo nuevo.
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

    # Enfermedad renal que no consta y que descubriría una prueba pendiente.
    new_g = np.arange(6) >= 2 if (recorded_g is None and not ckd_recorded) else np.zeros(6, bool)
    new_a = np.arange(3) >= 1 if (recorded_a is None and not ckd_recorded) else np.zeros(3, bool)
    new_ckd = new_g[:, None] | new_a[None, :]
    p_finding = float(mass[(true_cat > recorded) | new_ckd[:, :, None]].sum())

    by_test, finding_by_test = {}, {}
    if recorded_a is None:  # solo se mide la orina
        p_a = joint.sum(axis=0)
        up = np.maximum(organ[g0, :], s0) > recorded
        by_test["orina"] = float(p_a[up].sum())
        finding_by_test["orina"] = float(p_a[up | new_a].sum())
    if recorded_g is None:  # solo se mide la creatinina
        p_g = joint.sum(axis=1)
        up = np.maximum(organ[:, a0], s0) > recorded
        by_test["creatinina"] = float(p_g[up].sum())
        finding_by_test["creatinina"] = float(p_g[up | new_g].sum())
    if score_pending:  # solo se completan los lípidos y la tensión
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
        score += f" (80 %: {risk.score_low:.0%}-{risk.score_high:.0%})"
    lines = [
        f"SCORE2 a 10 años: {score}" + (" · con datos supuestos" if risk.approximate else ""),
        f"Categoría con lo que consta hoy: {CATEGORY_LABELS[risk.recorded]}",
        f"Categoría real probable: {probs}",
    ]
    if risk.p_up >= 0.005:
        detail = ", ".join(f"{t} {p:.0%}" for t, p in sorted(risk.p_up_by_test.items(), key=lambda kv: -kv[1]) if p >= 0.005)
        lines.append(f"Probabilidad de subir de categoría al completar las pruebas: {risk.p_up:.0%}" + (f" ({detail})" if detail else ""))
    return "\n".join(lines)
