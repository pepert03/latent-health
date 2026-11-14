"""Evaluación cardio-renal-metabólica de un paciente a partir de su historia clínica y lo medido en casa.

Une todas las piezas:
- el filtro de albuminuria (muestras de laboratorio y tiras hechas en casa, con su incertidumbre),
- el panel virtual (FG, HbA1c, glucosa, potasio, no-HDL, hemoglobina y NT-proBNP estimados
  con la historia clínica y la última orina cuando no hay analítica reciente),
- la tendencia del FG con las analíticas previas y los tratamientos,
- las medidas hechas en casa (tensión, punción capilar, ritmo cardíaco), y
- el riesgo cardiovascular (SCORE2 y categorías de la guía europea).

Devuelve probabilidades de cada diagnóstico del reto (ERC por categorías KDIGO, diabetes,
insuficiencia cardíaca), la categoría de riesgo cardiovascular con lo que cambiaría cada
prueba pendiente, los hallazgos que ya piden actuar y qué pruebas merece la pena pedir.

Un valor de laboratorio reciente (``measured``) siempre sustituye a la estimación. Una medida
capilar hecha en casa (``home_labs``) la actualiza, porque tiene más error.

El FG y la albuminuria **no se tratan como independientes**: cuando el FG no está medido, el
filtro de albuminuria se resuelve para cada categoría de FG y se combinan.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import ndtri

from . import cvrisk
from .albuminuria import AlbuminuriaAssessment, Patient, StripSample, choose_channel, load_default_filter
from .albuminuria import describe as describe_albuminuria
from .albuminuria.filter import Sample
from .albuminuria.model import RANDOM
from .decision import Thresholds
from .diabetes import DIABETES_FASTING_GLUCOSE, GlucoseReading, fasting_days_above, summarize_glucose
from .home import BPReading, HeartCheck, HomeBP, HomeLab, RhythmCheck, af_probability, low_ef_probability, summarize_home_bp, update_pmf
from .kidney_trend import EgfrMeasurement, EgfrTrend, TreatmentStart, fit_trend
from .kidney_trend import describe as describe_trend
from .outcomes import risk as outcome_risk
from .recalibration import load_recalibration, shift_below

PANEL_DIR = Path(__file__).resolve().parents[2] / "models" / "panel"
# Pruebas de casa que puede recomendar la ficha; ``kit`` las lee para decidir qué se le manda.
URINE_TEST = "UACR (primera orina de la mañana)"
HOME_GLUCOSE_TEST = "Glucosa capilar en ayunas (en la farmacia o en casa)"
HOME_BP_TEST = "Tensión en casa"
HOME_BP_HOW = "Una semana de automedida con manguito validado."

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

# Riesgo KDIGO por categorías de FG (filas) y albuminuria (columnas A1, A2, A3).
G_EDGES = [90, 60, 45, 30, 15]  # G1 ≥ 90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 < 15
G_LABELS = ["G1", "G2", "G3a", "G3b", "G4", "G5"]
G_RANGES = [(90.0, 200.0), (60.0, 90.0), (45.0, 60.0), (30.0, 45.0), (15.0, 30.0), (0.0, 15.0)]
KDIGO_RISK = {
    "G1": ["bajo", "moderado", "alto"],
    "G2": ["bajo", "moderado", "alto"],
    "G3a": ["moderado", "alto", "muy alto"],
    "G3b": ["alto", "muy alto", "muy alto"],
    "G4": ["muy alto", "muy alto", "muy alto"],
    "G5": ["muy alto", "muy alto", "muy alto"],
}
# HDL si no está medido: mediana (mg/dl) y desviación del logaritmo en adultos de 40 años o
# más de NHANES 2009-2018 (hombre, mujer). Se integra sobre esa distribución.
TYPICAL_HDL = {False: (46.6, 0.289), True: (56.3, 0.278)}


@dataclass
class ClinicalRecord:
    """Lo que hay en la historia clínica de atención primaria y lo que el paciente mide en casa."""

    age: float
    female: bool
    bmi: float | None = None
    waist: float | None = None  # cm
    sbp: float | None = None  # tensión sistólica media en consulta, mmHg
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
    urine_samples: list[Sample] = field(default_factory=list)  # de laboratorio o tiras de casa
    # Analítica reciente: egfr, hba1c, glucose, potassium, non_hdl, hemoglobin, nt_probnp,
    # total_cholesterol y hdl (mg/dl).
    measured: dict[str, float] = field(default_factory=dict)
    atrial_fibrillation: bool = False
    diabetes_low_risk: bool = False  # menos de 10 años, bien controlada y sin otros factores
    egfr_history: list[EgfrMeasurement] = field(default_factory=list)  # analíticas previas de FG
    treatments: list[TreatmentStart] = field(default_factory=list)  # inicios de iSGLT2 o IECA/ARA-II
    home_bp: list[BPReading] = field(default_factory=list)  # automedida de la tensión
    home_labs: dict[str, HomeLab] = field(default_factory=dict)  # punción capilar: egfr, hba1c...
    rhythm_checks: list[RhythmCheck] = field(default_factory=list)
    heart_checks: list[HeartCheck] = field(default_factory=list)  # grabaciones del corazón en casa ya valoradas
    has_smartphone: bool | None = None
    home_glucose: list[GlucoseReading] = field(default_factory=list)  # glucómetro en casa
    family_diabetes: bool | None = None  # padres o hermanos con diabetes
    # Cuestionario de casa (None = no contestado) y pulso.
    self_rated_health: int | None = None  # 1 excelente, 2 muy buena, 3 buena, 4 regular, 5 mala
    dyspnea_on_stairs: bool | None = None  # le falta el aire al subir cuestas o escaleras
    walk_difficulty: int | None = None  # caminar 400 m: 0 ninguna, 1 alguna, 2 mucha, 3 no puede
    stairs_difficulty: int | None = None  # subir 10 escalones, misma escala
    hospitalized_last_year: bool | None = None
    pulse: float | None = None  # latidos por minuto en reposo
    pulse_irregular: bool | None = None


@dataclass
class BloodEstimate:
    name: str
    unit: str
    median: float
    low: float  # percentil 10
    high: float  # percentil 90
    measured: bool
    decimals: int = 0
    source: str = "estimado"  # "medido", "capilar en casa" o "estimado"


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
    kdigo_joint: np.ndarray = field(default=None, repr=False)  # P(categoría G, categoría A), (6, 3)
    egfr_trend: EgfrTrend | None = None
    cv: cvrisk.CvRisk | None = None
    home_bp: HomeBP | None = None
    p_af: float | None = None  # fibrilación auricular, si hay comprobaciones del ritmo
    p_low_ef: float | None = None  # fracción de eyección baja, si hay grabaciones del corazón
    alerts: list[str] = field(default_factory=list)  # hallazgos que ya piden actuar
    # Probabilidad de que las pruebas pendientes den un hallazgo nuevo (subir de categoría de
    # riesgo, enfermedad renal que no consta o diabetes sin diagnosticar), y la de cada prueba.
    p_new_finding: float = 0.0
    finding_by_test: dict[str, float] = field(default_factory=dict)
    channel: str = ""  # canal propuesto para las pruebas en casa
    # Riesgo de muerte cardiovascular con lo medido en casa (modelo con desenlaces reales).
    home_risk: outcome_risk.HomeRisk | None = None


@lru_cache(maxsize=None)
def _panel_model(target: str, with_urine: bool):
    name = "historia_clínica_y_orina" if with_urine else "historia_clínica"
    if target == "log_nt_probnp":
        # Si existe, el modelo que además usa los síntomas y el pulso que da el paciente
        # (scripts/fit_heart_home.py). Sus predictores siguen las convenciones de la cohorte.
        home = PANEL_DIR / f"{target}__{'casa_y_orina' if with_urine else 'casa'}.joblib"
        if home.exists():
            return {**joblib.load(home), "home": True}
    if target == "hba1c":
        # Si existe, el modelo que además usa la glucosa del glucómetro y los antecedentes
        # familiares (scripts/fit_diabetes_home.py). Sirve con y sin orina y con y sin glucosa.
        home = PANEL_DIR / "hba1c__casa.joblib"
        if home.exists():
            return {**joblib.load(home), "home": True}
    return joblib.load(PANEL_DIR / f"{target}__{name}.joblib")


@lru_cache(maxsize=None)
def _filter(population: str, confirm: float, discard: float):
    return load_default_filter(population, confirm=confirm, discard=discard)


@lru_cache(maxsize=None)
def _egfr_shift(population: str) -> float:
    """Constante del suceso FG < 60 para la población (0 con los modelos tal cual, de NHANES)."""
    recal = load_recalibration() if population == "espana" else None
    return float(recal["egfr"]["constante_fg_menor_60"]) if recal else 0.0


# Predicciones del panel ya calculadas: (variable, con orina, predictores) -> distribución.
# Predecir paciente a paciente es lento (cientos de árboles por variable); ``warm_up`` las
# calcula de una vez para todo un cupo.
_PMF_CACHE: dict = {}


def _predict_pmf(target: str, with_urine: bool, X: np.ndarray) -> np.ndarray:
    key = (target, with_urine, X.tobytes())
    if key not in _PMF_CACHE:
        if len(_PMF_CACHE) > 200_000:
            _PMF_CACHE.clear()
        _PMF_CACHE[key] = _panel_model(target, with_urine)["model"].predict_pmf(X)
    return _PMF_CACHE[key]


def _blood_pressure(record: ClinicalRecord) -> tuple[HomeBP | None, float | None, float | None]:
    """Tensión que se usa: la automedida válida es más fiable que una lectura de consulta."""
    home_bp = summarize_home_bp(record.home_bp)
    if home_bp is not None and home_bp.valid:
        return home_bp, home_bp.office_sbp, home_bp.office_dbp
    return home_bp, record.sbp, record.dbp


def warm_up(records, population: str = "espana") -> None:
    """Calcula de una vez las predicciones del panel de muchos pacientes.

    Después, ``assess`` de cada uno es casi inmediato. Lo usa la lista del cupo.
    """
    filt = _filter(population, 0.95, 0.05)
    rows: dict[tuple[str, bool], list[np.ndarray]] = {}
    for record in records:
        _, sbp, dbp = _blood_pressure(record)
        plain = _features(record, filt, sbp, dbp)
        feats, home_feats = pd.DataFrame([plain]), pd.DataFrame([_home_features(record, plain)])
        has_urine = bool(record.urine_samples)
        wanted = {(BLOOD[v][0], has_urine) for v in BLOOD} | {("egfr", False)}
        for target, with_urine in wanted:
            bundle = _panel_model(target, with_urine)
            X = (home_feats if bundle.get("home") else feats)[bundle["features"]].to_numpy(float)
            if (target, with_urine, X.tobytes()) not in _PMF_CACHE:
                rows.setdefault((target, with_urine), []).append(X)
    for (target, with_urine), xs in rows.items():
        X = np.vstack(xs)
        pmf = _panel_model(target, with_urine)["model"].predict_pmf(X)
        for i in range(len(xs)):
            _PMF_CACHE[(target, with_urine, X[i : i + 1].tobytes())] = pmf[i : i + 1]


def _features(record: ClinicalRecord, filt, sbp: float | None, dbp: float | None) -> dict:
    nan = np.nan
    f = {
        "age": record.age,
        "female": float(record.female),
        "bmi": nan if record.bmi is None else record.bmi,
        "waist": nan if record.waist is None else record.waist,
        "sbp": nan if sbp is None else sbp,
        "dbp": nan if dbp is None else dbp,
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
        if isinstance(last, StripSample):  # la tira da un valor aproximado
            uacr = last.nominal_uacr
            creatinine = None if last.spec.ratio_only else last.creatinine_mg_dl
        else:
            uacr, creatinine = last.uacr, last.creatinine_mg_dl
        log_uacr = np.log(uacr)
        if last.sample_type != RANDOM:  # el panel se entrenó con muestras aleatorias
            log_uacr = log_uacr + float(filt.p.bias_at(RANDOM, log_uacr))
        f["log_uacr"] = log_uacr
        if creatinine is not None:
            f["log_urine_creatinine"] = np.log(creatinine)
            f["log_urine_albumin"] = log_uacr + np.log(creatinine / 100.0)
    return f


def _home_features(record: ClinicalRecord, feats: dict) -> dict:
    """Predictores con las convenciones de la cohorte con seguimiento (``outcomes.data``).

    Parte de los del panel y añade el cuestionario de casa y el pulso. Los fármacos valen 0 si
    no se toman (en el panel quedan vacíos si no hay diagnóstico) y la edad se acota en 80.
    """
    nan = np.nan

    def answer(value) -> float:
        return nan if value is None else float(value)

    def difficulty(value) -> float:
        # A los menores de 60 sin limitaciones NHANES no les pregunta: cuenta como ninguna.
        return float(value) if value is not None else (0.0 if record.age < 60 else nan)

    glucose = summarize_glucose(record.home_glucose)
    return {
        **feats,
        "glucose_home": nan if glucose is None else glucose[0],
        "fasting_hours": nan if glucose is None else glucose[1],
        "family_diabetes": answer(record.family_diabetes),
        "age": min(record.age, 80.0),
        "diabetes_pills": float(record.diabetes_pills),
        "bp_meds": float(record.bp_meds),
        "cholesterol_meds": float(record.cholesterol_meds),
        "health": answer(record.self_rated_health),
        "dyspnea": answer(record.dyspnea_on_stairs) if record.age >= 40 else nan,  # solo se preguntó desde los 40
        "walk_difficulty": difficulty(record.walk_difficulty),
        "stairs_difficulty": difficulty(record.stairs_difficulty),
        "hospitalized": answer(record.hospitalized_last_year),
        "pulse": answer(record.pulse),
        "pulse_irregular": answer(record.pulse_irregular),
    }


class _Variable:
    """Distribución de una variable de la analítica para un paciente: medida, capilar o estimada."""

    def __init__(
        self,
        variable: str,
        record: ClinicalRecord,
        feats: dict,
        population: str,
        with_urine: bool | None = None,
        home_feats: dict | None = None,
    ):
        target, self.inverse, unit, label, decimals = BLOOD[variable]
        self.log = target.startswith("log_")
        with_urine = bool(record.urine_samples) if with_urine is None else with_urine
        bundle = _panel_model(target, with_urine)
        self.model = bundle["model"]
        source_feats = home_feats if (bundle.get("home") and home_feats is not None) else feats
        self.X = pd.DataFrame([source_feats])[bundle["features"]].to_numpy(float)
        self.bounds = self.model.bin_bounds
        self.pmf = _predict_pmf(target, with_urine, self.X)
        if variable == "egfr" and _egfr_shift(population):
            self.pmf = shift_below(self.pmf, self.bounds, 60.0, _egfr_shift(population))
        self.value = record.measured.get(variable)
        source = "medido" if self.value is not None else "estimado"
        if self.value is None and variable in record.home_labs and not self.log:
            lab = record.home_labs[variable]
            error = {k: v for k, v in lab.error(variable).items() if v is not None}
            self.pmf = update_pmf(self.bounds, self.pmf[0], lab.value, **error)[None, :]
            source = "capilar en casa"
        if self.value is None and variable == "hba1c" and bundle.get("home") and record.home_glucose:
            source = "estimado con la glucosa de casa"
        if self.value is not None:
            v = float(self.value)
            self.estimate = BloodEstimate(label, unit, v, v, v, True, decimals, source)
        else:
            q = self.inverse(self.model.quantiles(self.X, [0.1, 0.5, 0.9], pmf=self.pmf)[0])
            self.estimate = BloodEstimate(label, unit, float(q[1]), float(q[0]), float(q[2]), False, decimals, source)

    def p_below(self, threshold: float) -> float:
        """P(variable < umbral); exacta (0 o 1) si el valor está medido en el laboratorio."""
        if self.value is not None:
            return float(self.value < threshold)
        t = np.log(threshold) if self.log else threshold
        return float(self.model.cdf(self.X, t, pmf=self.pmf)[0])

    def quantiles(self, qs) -> np.ndarray:
        if self.value is not None:
            return np.full(len(qs), float(self.value))
        return self.inverse(self.model.quantiles(self.X, list(qs), pmf=self.pmf)[0])

    def mean_sd(self) -> tuple[float, float]:
        mids = (self.bounds[:-1] + self.bounds[1:]) / 2.0
        mean = float(self.pmf[0] @ mids)
        return mean, float(np.sqrt(self.pmf[0] @ (mids - mean) ** 2 + (np.diff(self.bounds) ** 2 / 12.0) @ self.pmf[0]))

    def range_mean(self, lo: float, hi: float) -> float:
        """Media de la variable dentro de [lo, hi) (reparto uniforme dentro de cada tramo)."""
        a = np.clip(self.bounds[:-1], lo, hi)
        b = np.clip(self.bounds[1:], lo, hi)
        mass = self.pmf[0] * (b - a) / np.diff(self.bounds)
        return float((mass @ ((a + b) / 2.0)) / mass.sum()) if mass.sum() > 0 else (lo + hi) / 2.0


def _g_probs(below: list[float]) -> np.ndarray:
    probs = np.clip(np.r_[1.0 - below[0], -np.diff(below), below[-1]], 0.0, 1.0)  # G1 ... G5
    return probs / probs.sum()


def assess(
    record: ClinicalRecord,
    as_of: date | None = None,
    population: str = "espana",
    thresholds: Thresholds | None = None,
    joint: str = "panel",
    detail: bool = True,
) -> PatientAssessment:
    """Evaluación completa de un paciente.

    - ``population``: ``"espana"`` usa los priors recalibrados a atención primaria española (si
      existen; ver ``recalibration``); ``"nhanes"``, los modelos tal como se ajustaron.
    - ``thresholds``: probabilidades a partir de las que se actúa (ver ``decision``).
    - ``joint``: cómo se combinan FG y albuminuria cuando el FG no está medido. ``"panel"``
      (por defecto): el panel da la distribución del FG y el filtro de albuminuria se resuelve
      para cada categoría; ``"bayes"``: además, las muestras de orina actualizan esa
      distribución; ``"independent"``: como si no tuvieran relación. En NHANES las tres dan
      resultados que no se distinguen (``reports/robustez.md``); se usa la primera porque es
      coherente y no empeora.
    - ``detail=False`` omite cuánto ayudaría otra muestra de orina (más rápido, para todo un cupo).
    """
    thresholds = thresholds or Thresholds()
    filt = _filter(population, thresholds.albuminuria_confirm, thresholds.albuminuria_discard)

    home_bp, sbp, dbp = _blood_pressure(record)

    feats = _features(record, filt, sbp, dbp)
    home_feats = _home_features(record, feats)
    variables = {v: _Variable(v, record, feats, population, home_feats=home_feats) for v in BLOOD}
    blood = {v: var.estimate for v, var in variables.items()}
    egfr = variables["egfr"]
    samples = list(record.urine_samples)

    # --- Filtrado glomerular: medido, con historia (tendencia) o estimado ---
    trend = None
    measured_egfr = record.measured.get("egfr")
    history = list(record.egfr_history)
    if history:
        if measured_egfr is not None and as_of is not None and all(m.date != as_of for m in history):
            history.append(EgfrMeasurement(as_of, measured_egfr))
        # Albuminuria provisional con la última analítica, solo para el prior de la pendiente.
        last = max(history, key=lambda m: m.date)
        rough = filt.assess(Patient(record.age, record.female, record.diabetes, last.egfr, samples), as_of=as_of, detail=False)
        prior_var = _Variable("egfr", replace(record, measured={}, home_labs={}), feats, population)
        trend = fit_trend(
            history,
            record.age,
            record.female,
            record.diabetes,
            rough.p_a2,
            rough.p_a3,
            record.treatments,
            as_of,
            prior_level=prior_var.mean_sd(),
        )
        g_probs = np.array([trend.category_probs()[g] for g in G_LABELS])
        # Valor representativo de cada categoría: el más cercano al nivel estimado.
        g_values = [float(np.clip(trend.level, lo, hi - 0.5)) for lo, hi in G_RANGES]
        lo, hi = trend.interval("level")
        blood["egfr"] = BloodEstimate("FG", "ml/min/1,73 m²", trend.level, lo, hi, False, 0, f"tendencia de {trend.n} analíticas")
    elif measured_egfr is not None:
        g_probs = _g_probs([float(measured_egfr < e) for e in G_EDGES])
        g_values = [float(measured_egfr)] * 6
    else:
        source = egfr
        if joint == "bayes" and samples:
            # Se parte del panel sin orina (con la punción capilar, si la hay) y la orina lo actualiza.
            source = _Variable("egfr", record, feats, population, with_urine=False)
        g_probs = _g_probs([source.p_below(e) for e in G_EDGES])
        g_values = [source.range_mean(lo, hi) for lo, hi in G_RANGES]

    # --- Albuminuria, condicionada a cada categoría de FG ---
    known_g = measured_egfr is not None and not history
    if known_g or joint == "independent":
        center = float(measured_egfr) if known_g else float(np.dot(g_probs, g_values))
        alb = filt.assess(Patient(record.age, record.female, record.diabetes, center, samples), as_of=as_of, detail=detail)
        joint_ga = np.outer(g_probs, [alb.p_a1, alb.p_a2, alb.p_a3])
    else:
        keep = [i for i in range(6) if g_probs[i] >= 0.002]
        mixture = [(g_values[i], g_probs[i]) for i in keep]
        alb = filt.assess(
            Patient(record.age, record.female, record.diabetes, None, samples),
            as_of=as_of,
            egfr_mixture=mixture,
            update_weights=(joint == "bayes"),
            detail=detail,
        )
        joint_ga = np.zeros((6, 3))
        comps = alb.egfr_components or [None]
        if len(mixture) == 1:
            joint_ga[keep[0]] = [alb.p_a1, alb.p_a2, alb.p_a3]
        else:
            for i, c in zip(keep, comps):
                joint_ga[i] = c.weight * np.array([c.p_a1, c.p_a2, c.p_a3])
        joint_ga = joint_ga / joint_ga.sum()
        g_probs = joint_ga.sum(axis=1)

    kdigo_g = dict(zip(G_LABELS, g_probs.tolist()))
    risk: dict[str, float] = {"bajo": 0.0, "moderado": 0.0, "alto": 0.0, "muy alto": 0.0}
    for i, g in enumerate(G_LABELS):
        for level, p in zip(KDIGO_RISK[g], joint_ga[i]):
            risk[level] += float(p)
    p_g3 = float(g_probs[2:].sum())
    p_ckd = float(1.0 - joint_ga[:2, 0].sum())

    # --- Diabetes ---
    if record.diabetes:
        diabetes, p_diabetes = "diagnosticada", None
    else:
        p_diabetes = 1.0 - variables["hba1c"].p_below(6.5)
        diabetes = "probable" if p_diabetes >= 0.5 else "posible" if p_diabetes >= 0.1 else "poco probable"

    # --- Insuficiencia cardíaca: NT-proBNP ≥ 125 pg/ml (umbral de exclusión en consulta) ---
    if record.heart_failure:
        heart, p_bnp = "diagnosticada", None
    else:
        p_bnp = 1.0 - variables["nt_probnp"].p_below(125.0)
        heart = "a descartar" if p_bnp >= thresholds.nt_probnp else "poco probable"

    # --- Grabación del corazón en casa: fracción de eyección baja ---
    p_low_ef = None
    if record.heart_checks and not record.heart_failure:
        p_low_ef = low_ef_probability(record.heart_checks, record.age, coronary=record.coronary)
        if p_low_ef >= thresholds.echo:
            heart = "a descartar"

    # --- Ritmo ---
    p_af = None
    if record.rhythm_checks and not record.atrial_fibrillation:
        p_af = af_probability(record.rhythm_checks, record.age, female=record.female)

    cv = _cv_risk(record, variables, joint_ga, alb, sbp, known_g or bool(history))
    finding_by_test = dict(cv.finding_by_test)
    p_diabetes_pending = p_diabetes if (p_diabetes is not None and "hba1c" not in record.measured) else 0.0
    if p_diabetes_pending:
        # Sin glucosa de casa, lo primero es el glucómetro; con ella, lo que queda es confirmar con la HbA1c.
        finding_by_test["HbA1c" if record.home_glucose else "glucosa"] = p_diabetes_pending
    # La diabetes oculta se toma como independiente del hallazgo renal o cardiovascular.
    p_new_finding = 1.0 - (1.0 - cv.p_finding) * (1.0 - p_diabetes_pending)
    if p_low_ef is not None and p_low_ef >= thresholds.echo:
        finding_by_test["ecocardiograma"] = p_low_ef
        p_new_finding = 1.0 - (1.0 - p_new_finding) * (1.0 - p_low_ef)
    alerts = _alerts(record, alb, trend, home_bp, variables, p_af, thresholds)
    recs = _recommendations(record, alb, p_g3, p_diabetes, p_bnp, cv, home_bp, sbp, p_af, thresholds, bool(history), p_low_ef)
    channel = choose_channel(record.age, record.has_smartphone).value
    home = outcome_risk.home_risk(home_feats)
    # Las preguntas sobre síntomas no cambian el orden del riesgo de muerte cardiovascular, pero sí
    # afinan quién tendrá el NT-proBNP alto en mayores de 60 años (reports/insuficiencia_cardiaca.md).
    symptoms_unknown = record.dyspnea_on_stairs is None or record.walk_difficulty is None
    if record.age >= 60 and p_bnp is not None and p_bnp >= thresholds.nt_probnp and symptoms_unknown:
        recs.append(
            Recommendation(
                "Preguntas sobre síntomas",
                "Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha "
                "de insuficiencia cardíaca antes de pedir el NT-proBNP.",
            )
        )
    return PatientAssessment(
        alb, blood, p_g3, kdigo_g, risk, p_ckd, diabetes, p_diabetes, heart, p_bnp, recs,
        kdigo_joint=joint_ga, egfr_trend=trend, cv=cv, home_bp=home_bp, p_af=p_af, p_low_ef=p_low_ef, alerts=alerts, channel=channel,
        p_new_finding=p_new_finding, finding_by_test=finding_by_test, home_risk=home,
    )  # fmt: skip


def _cv_risk(record, variables, joint_ga, alb, sbp, egfr_known: bool) -> cvrisk.CvRisk:
    """Categoría de riesgo cardiovascular con la incertidumbre de lo que falta por medir."""
    approximate = record.age < 40  # SCORE2 empieza a los 40 años: por debajo se calcula como si los tuviera
    sbp_known = sbp is not None
    if not sbp_known:
        sbp, approximate = (140.0 if record.hypertension else 125.0), True
    m = record.measured
    if "total_cholesterol" in m and "hdl" in m:
        tc, hdl, weights, lipids_known = np.array([m["total_cholesterol"]]), np.array([m["hdl"]]), np.array([1.0]), True
    else:
        qs = (np.arange(10) + 0.5) / 10.0
        non_hdl = variables["non_hdl"].quantiles(qs)
        lipids_known = "non_hdl" in m and "hdl" in m
        if "non_hdl" in m:
            non_hdl = non_hdl[:1]
        if "hdl" in m:
            hdl_values = np.array([m["hdl"]])
        else:  # sin HDL medido: cinco valores equiprobables de su distribución por sexo
            median, sd_log = TYPICAL_HDL[bool(record.female)]
            hdl_values = median * np.exp(sd_log * ndtri((np.arange(5) + 0.5) / 5.0))
            approximate = True
        non_hdl, hdl = (g.ravel() for g in np.meshgrid(non_hdl, hdl_values))
        tc = non_hdl + hdl
        weights = np.full(tc.size, 1.0 / tc.size)
    scores = cvrisk.score2(record.age, record.female, record.smoker_now, sbp, tc, hdl, record.diabetes)
    score_pending = not (lipids_known and sbp_known)
    score_recorded = float(np.median(scores))

    recorded_g = int(np.argmax(joint_ga.sum(axis=1))) if egfr_known else None
    if alb.status == "descartada":
        recorded_a = 0
    elif alb.status in ("confirmada", "pendiente_cronicidad"):
        recorded_a = 2 if alb.p_a3 > alb.p_a2 else 1
    else:
        recorded_a = None
    return cvrisk.assess_cv(
        record.age,
        joint_ga,
        scores,
        weights,
        record.diabetes,
        record.coronary or record.stroke,
        recorded_g,
        recorded_a,
        score_recorded,
        score_pending=score_pending,
        approximate=approximate,
        diabetes_low_risk=record.diabetes_low_risk,
        ckd_recorded=record.kidney_disease,
    )


def _alerts(record, alb, trend, home_bp, variables, p_af, thresholds) -> list[str]:
    """Hallazgos ya suficientemente claros como para actuar (no hace falta otra prueba para verlos)."""
    out = []
    if alb.status == "confirmada" and not record.kidney_disease:
        out.append("Albuminuria persistente sin enfermedad renal crónica registrada.")
    if not record.kidney_disease:
        if trend is not None and trend.chronic_below_60:
            out.append("FG por debajo de 60 en analíticas separadas más de tres meses, sin enfermedad renal crónica registrada.")
    if trend is not None and trend.status == "descenso_rapido":
        out.append(f"Descenso rápido del FG: {_num(trend.slope, 1)} ml/min/1,73 m² al año.")
    elif trend is not None and trend.status == "descenso":
        out.append(f"Descenso sostenido del FG: {_num(trend.slope, 1)} ml/min/1,73 m² al año.")
    if home_bp is not None and home_bp.valid and home_bp.p_high >= 0.9:
        out.append(home_bp.message + (" Sin hipertensión registrada." if not record.hypertension else ""))
    if not record.diabetes and fasting_days_above(record.home_glucose) >= 2:
        out.append(
            f"Glucosa en ayunas de {DIABETES_FASTING_GLUCOSE:.0f} mg/dl o más en dos días distintos, medida en casa, sin "
            "diabetes registrada: confirmar con HbA1c."
        )
    hba1c = record.measured.get("hba1c")
    if hba1c is not None and hba1c >= 6.5 and not record.diabetes:
        out.append(f"HbA1c de {_num(hba1c, 1)} % sin diabetes registrada (confirmar con una segunda determinación).")
    bnp = record.measured.get("nt_probnp")
    if bnp is not None and bnp >= 125 and not record.heart_failure:
        out.append(f"NT-proBNP de {_num(bnp)} pg/ml sin insuficiencia cardíaca registrada: pedir ecocardiograma.")
    if p_af is not None and p_af >= 0.5:
        out.append(f"Pulso irregular repetido en casa (P(fibrilación auricular) = {p_af:.0%}).")
    return out


def _recommendations(record, alb, p_g3, p_diabetes, p_bnp, cv, home_bp, sbp, p_af, thresholds, has_history, p_low_ef=None) -> list[Recommendation]:
    recs = []
    if alb.status in ("sin_medir", "dudosa", "pendiente_cronicidad"):
        recs.append(Recommendation(URINE_TEST, alb.action))
    egfr_pending = "egfr" not in record.measured and not has_history
    if egfr_pending and p_g3 > thresholds.creatinine:
        how = " Ya hay una punción capilar; conviene confirmarla en el laboratorio." if "egfr" in record.home_labs else ""
        recs.append(Recommendation("Creatinina (FG)", f"P(FG < 60) estimada: {p_g3:.0%}; hay que medirlo para estadificar la ERC.{how}"))
    single_egfr = record.measured.get("egfr")
    if single_egfr is not None and single_egfr < 60 and not has_history and not record.kidney_disease:
        recs.append(
            Recommendation(
                "Repetir creatinina a los tres meses",
                "Un FG por debajo de 60 aislado no basta para el diagnóstico: hay que confirmarlo pasados tres meses.",
            )
        )
    if p_diabetes is not None and "hba1c" not in record.measured:
        # Dos pasos: la glucosa capilar se mide con poca sospecha; el análisis se pide si esa glucosa la mantiene.
        if record.home_glucose:
            if p_diabetes > thresholds.hba1c:
                recs.append(
                    Recommendation("HbA1c", f"P(diabetes sin diagnosticar) con la glucosa capilar: {p_diabetes:.0%}. Confirmar con análisis.")
                )
        elif p_diabetes > thresholds.home_glucose:
            recs.append(
                Recommendation(
                    HOME_GLUCOSE_TEST,
                    f"P(diabetes sin diagnosticar) estimada: {p_diabetes:.0%}. Una medida de glucosa lo aclara casi siempre sin análisis.",
                )
            )
    if p_bnp is not None and "nt_probnp" not in record.measured and p_bnp >= thresholds.nt_probnp:
        recs.append(
            Recommendation("NT-proBNP", f"P(NT-proBNP ≥ 125) estimada: {p_bnp:.0%}; si sale alto, ecocardiograma.")
        )
    treat_kidney = alb.status in ("confirmada", "pendiente_cronicidad") or p_g3 >= 0.5
    if treat_kidney and "potassium" not in record.measured:
        recs.append(Recommendation("Potasio", "Antes de iniciar o subir IECA/ARA-II o finerenona."))
    if cv is not None and cv.p_up_by_test.get("lípidos", 0.0) >= 0.05:
        recs.append(
            Recommendation(
                "Colesterol total y HDL",
                f"Sin ellos no se puede calcular el SCORE2; probabilidad de que suba de categoría: {cv.p_up_by_test['lípidos']:.0%}.",
            )
        )
    if home_bp is not None and not home_bp.valid:
        recs.append(Recommendation(HOME_BP_TEST, home_bp.message))
    elif home_bp is None and (sbp is None or (sbp >= 135 and not record.hypertension) or (sbp >= 140 and record.hypertension)):
        why = "No hay tensión registrada." if sbp is None else f"Tensión en consulta de {sbp:.0f} mmHg."
        recs.append(Recommendation(HOME_BP_TEST, f"{why} {HOME_BP_HOW}"))
    if p_af is not None and p_af >= thresholds.ecg:
        recs.append(Recommendation("ECG", f"P(fibrilación auricular) tras las comprobaciones en casa: {p_af:.0%}."))
    if p_low_ef is not None and p_low_ef >= thresholds.echo:
        recs.append(
            Recommendation(
                "Ecocardiograma",
                f"P(fracción de eyección ≤ 40 %) tras la grabación del corazón en casa: {p_low_ef:.0%}. "
                "Pedir antes el NT-proBNP si hay lista de espera: si sale alto, el ecocardiograma es preferente.",
            )
        )
    return recs


def _num(v: float, decimals: int = 0) -> str:
    """Número en formato español: coma decimal y punto de miles (3.333; 5,8)."""
    return f"{v:,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))


def describe(a: PatientAssessment) -> str:
    """Resumen en texto para el médico."""
    lines = []
    if a.alerts:
        lines += ["HALLAZGOS QUE PIDEN ACTUAR", *("  - " + alert for alert in a.alerts)]
    lines += ["ALBUMINURIA", *("  " + line for line in describe_albuminuria(a.albuminuria).splitlines())]
    lines.append("ANALÍTICA (medida o estimada con la historia y la orina; 80 % de probabilidad)")
    for est in a.blood.values():
        median, low, high = (_num(v, est.decimals) for v in (est.median, est.low, est.high))
        if est.measured:
            lines.append(f"  {est.name}: {median} {est.unit} (medido)")
        else:
            lines.append(f"  {est.name}: {median} {est.unit} (entre {low} y {high}, {est.source})")
    if a.egfr_trend is not None:
        lines += ["TENDENCIA DEL FG", *("  " + line for line in describe_trend(a.egfr_trend).splitlines())]
    if a.home_bp is not None:
        lines += ["EN CASA", f"  {a.home_bp.message}"]
    risk = ", ".join(f"{k} {v:.0%}" for k, v in a.kdigo_risk.items())
    lines += [
        "DIAGNÓSTICOS",
        f"  Enfermedad renal crónica: P(FG < 60 o albuminuria ≥ 30) = {a.p_ckd:.0%}; riesgo KDIGO: {risk}",
        f"  Diabetes: {a.diabetes}" + (f" (P = {a.p_diabetes:.0%})" if a.p_diabetes is not None else ""),
        f"  Insuficiencia cardíaca: {a.heart_failure}"
        + (f" (P(NT-proBNP ≥ 125) = {a.p_nt_probnp_high:.0%})" if a.p_nt_probnp_high is not None else ""),
    ]
    if a.p_af is not None:
        lines.append(f"  Fibrilación auricular: P = {a.p_af:.0%} tras las comprobaciones del ritmo en casa")
    if a.p_low_ef is not None:
        lines.append(f"  Fracción de eyección baja: P = {a.p_low_ef:.0%} tras la grabación del corazón en casa")
    if a.cv is not None:
        lines += ["RIESGO CARDIOVASCULAR", *("  " + line for line in cvrisk.describe(a.cv).splitlines())]
    if a.home_risk is not None:
        lines += ["RIESGO CON LO MEDIDO EN CASA", *("  " + line for line in outcome_risk.describe(a.home_risk).splitlines())]
    if a.p_new_finding >= 0.005:
        by_test = sorted(a.finding_by_test.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{t} {p:.0%}" for t, p in by_test if p >= 0.005)
        lines.append(
            f"HALLAZGO NUEVO SI SE COMPLETAN LAS PRUEBAS: {a.p_new_finding:.0%}" + (f" ({detail})" if detail else "")
        )
    lines.append("PRUEBAS RECOMENDADAS")
    lines += [f"  - {r.test}: {r.reason}" for r in a.recommendations] or ["  (ninguna)"]
    return "\n".join(lines)
