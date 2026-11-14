"""Evaluación cardio-renal-metabólica de un paciente a partir de su historia clínica y su orina.

Une las dos piezas:
- el filtro de albuminuria (todas las muestras de orina del paciente, con su incertidumbre), y
- el panel virtual (FG, HbA1c, glucosa, potasio, no-HDL, hemoglobina y NT-proBNP estimados
  con la historia clínica y la última orina cuando no hay analítica reciente).

Devuelve probabilidades de cada diagnóstico del reto (ERC por categorías KDIGO, diabetes,
insuficiencia cardíaca) y qué pruebas merece la pena pedir. Un valor medido reciente
siempre sustituye a la estimación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .albuminuria import AlbuminuriaAssessment, Patient, UrineSample, load_default_filter
from .albuminuria import describe as describe_albuminuria
from .albuminuria.model import RANDOM

PANEL_DIR = Path(__file__).resolve().parents[2] / "models" / "panel"

# variable -> (nombre del modelo, transformación inversa, unidad, etiqueta, decimales)
BLOOD = {
    "egfr": ("egfr", lambda v: v, "ml/min/1,73 m²", "FG", 0),
    "hba1c": ("hba1c", lambda v: v, "%", "HbA1c", 1),
    "glucose": ("glucose", lambda v: v, "mg/dl", "Glucosa (sin ayuno)", 0),
    "potassium": ("potassium", lambda v: v, "mmol/l", "Potasio", 1),
    "non_hdl": ("non_hdl", lambda v: v, "mg/dl", "Colesterol no-HDL", 0),
    "hemoglobin": ("hemoglobin", lambda v: v, "g/dl", "Hemoglobina", 1),
    "nt_probnp": ("log_nt_probnp", np.exp, "pg/ml", "NT-proBNP", 0),
}
_LOG_TARGETS = {"log_nt_probnp"}

# Riesgo KDIGO por categorías de FG (filas) y albuminuria (columnas A1, A2, A3).
G_EDGES = [90, 60, 45, 30, 15]  # G1 ≥ 90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 < 15
G_LABELS = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
KDIGO_RISK = {
    "G1": ["bajo", "moderado", "alto"],
    "G2": ["bajo", "moderado", "alto"],
    "G3a": ["moderado", "alto", "muy alto"],
    "G3b": ["alto", "muy alto", "muy alto"],
    "G4": ["muy alto", "muy alto", "muy alto"],
    "G5": ["muy alto", "muy alto", "muy alto"],
}


@dataclass
class ClinicalRecord:
    """Lo que hay en la historia clínica de atención primaria."""

    age: float
    female: bool
    bmi: float | None = None
    waist: float | None = None  # cm
    sbp: float | None = None  # tensión sistólica media, mmHg
    dbp: float | None = None
    diabetes: bool = False
    prediabetes: bool = False
    insulin: bool = False
    diabetes_pills: bool = False
    hypertension: bool = False
    bp_meds: bool = False
    high_cholesterol: bool = False
    cholesterol_meds: bool = False
    heart_failure: bool = False
    coronary: bool = False
    stroke: bool = False
    kidney_disease: bool = False
    smoker_now: bool = False
    smoker_ever: bool = False
    urine_samples: list[UrineSample] = field(default_factory=list)
    measured: dict[str, float] = field(default_factory=dict)  # analítica reciente: egfr, hba1c, nt_probnp...


@dataclass
class BloodEstimate:
    name: str
    unit: str
    median: float
    low: float  # percentil 10
    high: float  # percentil 90
    measured: bool
    decimals: int = 0


@dataclass
class Recommendation:
    test: str
    reason: str


@dataclass
class PatientAssessment:
    albuminuria: AlbuminuriaAssessment
    blood: dict[str, BloodEstimate]
    p_egfr_below_60: float
    kdigo_g: dict[str, float]  # probabilidad de cada categoría G
    kdigo_risk: dict[str, float]  # probabilidad de cada nivel de riesgo KDIGO
    p_ckd: float  # FG < 60 o albuminuria ≥ 30 (sin exigir aún la cronicidad)
    diabetes: str
    p_diabetes: float | None
    heart_failure: str
    p_nt_probnp_high: float | None
    recommendations: list[Recommendation]


@lru_cache(maxsize=None)
def _panel_model(target: str, with_urine: bool):
    name = "historia_clínica_y_orina" if with_urine else "historia_clínica"
    return joblib.load(PANEL_DIR / f"{target}__{name}.joblib")


def _features(record: ClinicalRecord, filt) -> dict:
    nan = np.nan
    f = {
        "age": record.age,
        "female": float(record.female),
        "bmi": nan if record.bmi is None else record.bmi,
        "waist": nan if record.waist is None else record.waist,
        "sbp": nan if record.sbp is None else record.sbp,
        "dbp": nan if record.dbp is None else record.dbp,
        "dx_diabetes": float(record.diabetes),
        "dx_prediabetes": float(record.prediabetes),
        "insulin": float(record.insulin),
        # En NHANES el tratamiento solo se pregunta a quien tiene el diagnóstico.
        "diabetes_pills": float(record.diabetes_pills) if record.diabetes else nan,
        "dx_hypertension": float(record.hypertension),
        "bp_meds": float(record.bp_meds) if record.hypertension else nan,
        "dx_high_cholesterol": float(record.high_cholesterol),
        "cholesterol_meds": float(record.cholesterol_meds) if record.high_cholesterol else nan,
        "dx_heart_failure": float(record.heart_failure),
        "dx_coronary": float(record.coronary),
        "dx_stroke": float(record.stroke),
        "dx_kidney": float(record.kidney_disease),
        "smoker_now": float(record.smoker_now),
        "smoker_ever": float(record.smoker_ever or record.smoker_now),
        "log_uacr": nan,
        "log_urine_albumin": nan,
        "log_urine_creatinine": nan,
        "urine_volume": nan,
        "urine_flow": nan,
        "hours_since_void": nan,
    }
    if record.urine_samples:
        last = max(record.urine_samples, key=lambda s: s.date)
        log_uacr = np.log(last.uacr)
        if last.sample_type != RANDOM:  # el panel se entrenó con muestras aleatorias
            log_uacr = log_uacr + float(filt.p.bias_at(RANDOM, log_uacr))
        f["log_uacr"] = log_uacr
        if last.creatinine_mg_dl is not None:
            f["log_urine_creatinine"] = np.log(last.creatinine_mg_dl)
            f["log_urine_albumin"] = log_uacr + np.log(last.creatinine_mg_dl / 100.0)
    return f


def _estimate(variable: str, record: ClinicalRecord, feats: dict) -> tuple[BloodEstimate, object, np.ndarray]:
    target, inverse, unit, label, decimals = BLOOD[variable]
    with_urine = bool(record.urine_samples)
    bundle = _panel_model(target, with_urine)
    X = pd.DataFrame([feats])[bundle["features"]].to_numpy(float)
    model = bundle["model"]
    if variable in record.measured:
        v = float(record.measured[variable])
        return BloodEstimate(label, unit, v, v, v, True, decimals), model, X
    q = inverse(model.quantiles(X, [0.1, 0.5, 0.9])[0])
    return BloodEstimate(label, unit, float(q[1]), float(q[0]), float(q[2]), False, decimals), model, X


def _prob(model, X, threshold, measured_value=None, below=True, log=False):
    """P(variable < umbral) (o ≥ si below=False); exacta (0/1) si el valor está medido."""
    if measured_value is not None:
        hit = measured_value < threshold
        return float(hit if below else not hit)
    t = np.log(threshold) if log else threshold
    p_below = float(model.cdf(X, t)[0])
    return p_below if below else 1.0 - p_below


def assess(record: ClinicalRecord, as_of: date | None = None) -> PatientAssessment:
    filt = load_default_filter()
    feats = _features(record, filt)
    blood, models = {}, {}
    for variable in BLOOD:
        est, model, X = _estimate(variable, record, feats)
        blood[variable] = est
        models[variable] = (model, X)

    # Albuminuria: el filtro usa el FG medido o, si no hay, el estimado.
    egfr_for_filter = record.measured.get("egfr", blood["egfr"].median)
    alb = filt.assess(
        Patient(record.age, record.female, record.diabetes, egfr_for_filter, list(record.urine_samples)),
        as_of=as_of,
    )

    # Categorías G de KDIGO.
    model, X = models["egfr"]
    measured_egfr = record.measured.get("egfr")
    below = [_prob(model, X, edge, measured_egfr) for edge in G_EDGES]  # P(FG < 90), P(< 60), ...
    g_probs = np.clip(np.r_[1.0 - below[0], -np.diff(below), below[-1]], 0.0, 1.0)  # G1 ... G5
    kdigo_g = dict(zip(G_LABELS, g_probs.tolist()))
    a_probs = [alb.p_a1, alb.p_a2, alb.p_a3]
    risk: dict[str, float] = {"bajo": 0.0, "moderado": 0.0, "alto": 0.0, "muy alto": 0.0}
    for g, pg in kdigo_g.items():
        for level, pa in zip(KDIGO_RISK[g], a_probs):
            risk[level] += pg * pa  # FG y albuminuria verdadera, independientes dado lo observado
    p_g3 = below[1]
    p_ckd = 1.0 - (1.0 - p_g3) * (1.0 - alb.p_a2_plus)

    # Diabetes.
    model, X = models["hba1c"]
    if record.diabetes:
        diabetes, p_diabetes = "diagnosticada", None
    else:
        p_diabetes = _prob(model, X, 6.5, record.measured.get("hba1c"), below=False)
        diabetes = "probable" if p_diabetes >= 0.5 else "posible" if p_diabetes >= 0.1 else "poco probable"

    # Insuficiencia cardíaca: NT-proBNP ≥ 125 pg/ml (umbral de exclusión en consulta).
    model, X = models["nt_probnp"]
    if record.heart_failure:
        heart, p_bnp = "diagnosticada", None
    else:
        p_bnp = _prob(model, X, 125.0, record.measured.get("nt_probnp"), below=False, log=True)
        heart = "a descartar" if p_bnp >= 0.3 else "poco probable"

    recs = _recommendations(record, alb, p_g3, p_diabetes, p_bnp, blood)
    return PatientAssessment(alb, blood, p_g3, kdigo_g, risk, p_ckd, diabetes, p_diabetes, heart, p_bnp, recs)


def _recommendations(record, alb, p_g3, p_diabetes, p_bnp, blood) -> list[Recommendation]:
    recs = []
    if alb.status in ("sin_medir", "dudosa", "pendiente_cronicidad"):
        recs.append(Recommendation("UACR (primera orina de la mañana)", alb.action))
    if "egfr" not in record.measured and 0.05 < p_g3:
        recs.append(Recommendation("Creatinina (FG)", f"P(FG < 60) estimada: {p_g3:.0%}; hay que medirlo para estadificar la ERC."))
    if p_diabetes is not None and "hba1c" not in record.measured and p_diabetes > 0.05:
        recs.append(Recommendation("HbA1c", f"P(diabetes sin diagnosticar) estimada: {p_diabetes:.0%}."))
    if p_bnp is not None and "nt_probnp" not in record.measured and p_bnp >= 0.3:
        recs.append(
            Recommendation("NT-proBNP", f"P(NT-proBNP ≥ 125) estimada: {p_bnp:.0%}; si sale alto, ecocardiograma.")
        )
    treat_kidney = alb.status in ("confirmada", "pendiente_cronicidad") or p_g3 >= 0.5
    if treat_kidney and "potassium" not in record.measured:
        recs.append(Recommendation("Potasio", "Antes de iniciar o subir IECA/ARA-II o finerenona."))
    return recs


def _num(v: float, decimals: int = 0) -> str:
    """Número en formato español: coma decimal y punto de miles (3.333; 5,8)."""
    return f"{v:,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))


def describe(a: PatientAssessment) -> str:
    """Resumen en texto para el médico."""
    lines = ["ALBUMINURIA", *("  " + line for line in describe_albuminuria(a.albuminuria).splitlines())]
    lines.append("ANALÍTICA (medida o estimada con la historia y la orina; 80 % de probabilidad)")
    for est in a.blood.values():
        median, low, high = (_num(v, est.decimals) for v in (est.median, est.low, est.high))
        if est.measured:
            lines.append(f"  {est.name}: {median} {est.unit} (medido)")
        else:
            lines.append(f"  {est.name}: {median} {est.unit} (entre {low} y {high}, estimado)")
    risk = ", ".join(f"{k} {v:.0%}" for k, v in a.kdigo_risk.items())
    lines += [
        "DIAGNÓSTICOS",
        f"  Enfermedad renal crónica: P(FG < 60 o albuminuria ≥ 30) = {a.p_ckd:.0%}; riesgo KDIGO: {risk}",
        f"  Diabetes: {a.diabetes}" + (f" (P = {a.p_diabetes:.0%})" if a.p_diabetes is not None else ""),
        f"  Insuficiencia cardíaca: {a.heart_failure}"
        + (f" (P(NT-proBNP ≥ 125) = {a.p_nt_probnp_high:.0%})" if a.p_nt_probnp_high is not None else ""),
        "PRUEBAS RECOMENDADAS",
    ]
    lines += [f"  - {r.test}: {r.reason}" for r in a.recommendations] or ["  (ninguna)"]
    return "\n".join(lines)
