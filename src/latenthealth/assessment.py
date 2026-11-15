"""Cardio-renal-metabolic assessment of a patient from their clinical record and home measurements.

Brings all the pieces together:
- the albuminuria filter (lab samples and home strips, with their uncertainty),
- the virtual panel (eGFR, HbA1c, glucose, potassium, non-HDL, hemoglobin and NT-proBNP estimated
  from the clinical record and the last urine sample when there are no recent labs),
- the eGFR trend from previous lab tests and treatments,
- home measurements (blood pressure, finger-prick, heart rhythm), and
- cardiovascular risk (SCORE2 and the European guideline categories).

Returns the probability of each diagnosis in the challenge (CKD by KDIGO category, diabetes,
heart failure), the cardiovascular risk category and what each pending test would change, the
findings that already call for action and which tests are worth ordering.

A recent lab value (``measured``) always replaces the estimate. A home finger-prick measurement
(``home_labs``) updates it, because it has more error.

eGFR and albuminuria are **not treated as independent**: when eGFR is not measured, the
albuminuria filter is solved for each eGFR category and the results are combined.
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
from .i18n import Labels, fmt_num, is_es, t
from .kidney_trend import EgfrMeasurement, EgfrTrend, TreatmentStart, fit_trend
from .kidney_trend import describe as describe_trend
from .outcomes import risk as outcome_risk
from .recalibration import load_recalibration, shift_below

PANEL_DIR = Path(__file__).resolve().parents[2] / "models" / "panel"
# Home tests the patient record can recommend; ``kit`` reads them to decide what to send.
# Functions, not constants: the text depends on the request language (``i18n``).


def urine_test() -> str:
    return t("UACR (primera orina de la mañana)", "UACR (first morning urine)")


def home_glucose_test() -> str:
    return t("Glucosa capilar en ayunas (en la farmacia o en casa)", "Fasting capillary glucose (at the pharmacy or at home)")


def home_bp_test() -> str:
    return t("Tensión en casa", "Home blood pressure")


def home_bp_how() -> str:
    return t("Una semana de automedida con manguito validado.", "One week of self-measurement with a validated cuff.")


def egfr_unit() -> str:
    return t("ml/min/1,73 m²", "ml/min/1.73 m²")


# variable -> (model name, inverse transform, unit, label, decimals). The display label is taken
# from ``BLOOD_LABELS`` and the eGFR unit from ``egfr_unit()`` (both depend on the language).
BLOOD = {
    "egfr": ("egfr", lambda v: v, "ml/min/1.73 m²", "eGFR", 0),
    "hba1c": ("hba1c", lambda v: v, "%", "HbA1c", 1),
    "glucose": ("glucose", lambda v: v, "mg/dl", "Glucose (non-fasting)", 0),
    "potassium": ("potassium", lambda v: v, "mmol/l", "Potassium", 1),
    "non_hdl": ("non_hdl", lambda v: v, "mg/dl", "Non-HDL cholesterol", 0),
    "hemoglobin": ("hemoglobin", lambda v: v, "g/dl", "Hemoglobin", 1),
    "nt_probnp": ("log_nt_probnp", np.exp, "pg/ml", "NT-proBNP", 0),
}
BLOOD_LABELS = Labels(
    {
        "egfr": ("FG", "eGFR"),
        "hba1c": ("HbA1c", "HbA1c"),
        "glucose": ("Glucosa (sin ayuno)", "Glucose (non-fasting)"),
        "potassium": ("Potasio", "Potassium"),
        "non_hdl": ("Colesterol no-HDL", "Non-HDL cholesterol"),
        "hemoglobin": ("Hemoglobina", "Hemoglobin"),
        "nt_probnp": ("NT-proBNP", "NT-proBNP"),
    }
)

# KDIGO risk by eGFR category (rows) and albuminuria (columns A1, A2, A3).
# The level names are machine keys (``kdigo_risk`` in the API); ``KDIGO_RISK_LABELS`` gives the text.
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
KDIGO_RISK_LABELS = Labels(
    {"bajo": ("bajo", "low"), "moderado": ("moderado", "moderate"), "alto": ("alto", "high"), "muy alto": ("muy alto", "very high")}
)
# HDL when not measured: median (mg/dl) and SD of the log in adults aged 40 or over in
# NHANES 2009-2018 (men, women). The estimate integrates over that distribution.
TYPICAL_HDL = {False: (46.6, 0.289), True: (56.3, 0.278)}


@dataclass
class ClinicalRecord:
    """What is in the primary care clinical record and what the patient measures at home."""

    age: float
    female: bool
    bmi: float | None = None
    waist: float | None = None  # cm
    sbp: float | None = None  # mean office systolic blood pressure, mmHg
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
    urine_samples: list[Sample] = field(default_factory=list)  # lab samples or home strips
    # Recent labs: egfr, hba1c, glucose, potassium, non_hdl, hemoglobin, nt_probnp,
    # total_cholesterol and hdl (mg/dl).
    measured: dict[str, float] = field(default_factory=dict)
    atrial_fibrillation: bool = False
    diabetes_low_risk: bool = False  # under 10 years, well controlled and no other risk factors
    egfr_history: list[EgfrMeasurement] = field(default_factory=list)  # previous eGFR lab tests
    treatments: list[TreatmentStart] = field(default_factory=list)  # SGLT2 inhibitor or ACEi/ARB starts
    home_bp: list[BPReading] = field(default_factory=list)  # home blood pressure self-measurement
    home_labs: dict[str, HomeLab] = field(default_factory=dict)  # finger-prick: egfr, hba1c...
    rhythm_checks: list[RhythmCheck] = field(default_factory=list)
    heart_checks: list[HeartCheck] = field(default_factory=list)  # home heart recordings already scored
    has_smartphone: bool | None = None
    home_glucose: list[GlucoseReading] = field(default_factory=list)  # home glucose meter
    family_diabetes: bool | None = None  # parents or siblings with diabetes
    # Home questionnaire (None = not answered) and pulse.
    self_rated_health: int | None = None  # 1 excellent, 2 very good, 3 good, 4 fair, 5 poor
    dyspnea_on_stairs: bool | None = None  # short of breath walking uphill or on stairs
    walk_difficulty: int | None = None  # walking 400 m: 0 none, 1 some, 2 much, 3 unable
    stairs_difficulty: int | None = None  # climbing 10 steps, same scale
    hospitalized_last_year: bool | None = None
    pulse: float | None = None  # resting beats per minute
    pulse_irregular: bool | None = None


@dataclass
class BloodEstimate:
    name: str
    unit: str
    median: float
    low: float  # 10th percentile
    high: float  # 90th percentile
    measured: bool
    decimals: int = 0
    source: str = "estimated"  # "measured", "finger-prick at home" or "estimated"


@dataclass
class Recommendation:
    test: str
    reason: str


@dataclass
class PatientAssessment:
    albuminuria: AlbuminuriaAssessment
    blood: dict[str, BloodEstimate]
    p_egfr_below_60: float
    kdigo_g: dict[str, float]  # probability of each G category
    kdigo_risk: dict[str, float]  # probability of each KDIGO risk level
    p_ckd: float  # eGFR < 60 or albuminuria ≥ 30 (chronicity not yet required)
    diabetes: str
    p_diabetes: float | None
    heart_failure: str
    p_nt_probnp_high: float | None
    recommendations: list[Recommendation]
    kdigo_joint: np.ndarray = field(default=None, repr=False)  # P(G category, A category), (6, 3)
    egfr_trend: EgfrTrend | None = None
    cv: cvrisk.CvRisk | None = None
    home_bp: HomeBP | None = None
    p_af: float | None = None  # atrial fibrillation, if there are rhythm checks
    p_low_ef: float | None = None  # low ejection fraction, if there are heart recordings
    alerts: list[str] = field(default_factory=list)  # findings that already call for action
    # Probability that the pending tests give a new finding (higher risk category, unrecorded
    # kidney disease or undiagnosed diabetes), overall and per test.
    p_new_finding: float = 0.0
    finding_by_test: dict[str, float] = field(default_factory=dict)
    channel: str = ""  # proposed channel for the home tests
    # Risk of cardiovascular death from home measurements (model fitted on real outcomes).
    home_risk: outcome_risk.HomeRisk | None = None


@lru_cache(maxsize=None)
def _panel_model(target: str, with_urine: bool):
    name = "historia_clínica_y_orina" if with_urine else "historia_clínica"
    if target == "log_nt_probnp":
        # If present, the model that also uses the patient's symptoms and pulse
        # (scripts/fit_heart_home.py). Its predictors follow the cohort's conventions.
        home = PANEL_DIR / f"{target}__{'casa_y_orina' if with_urine else 'casa'}.joblib"
        if home.exists():
            return {**joblib.load(home), "home": True}
    if target == "hba1c":
        # If present, the model that also uses meter glucose and family history
        # (scripts/fit_diabetes_home.py). Works with or without urine and glucose.
        home = PANEL_DIR / "hba1c__casa.joblib"
        if home.exists():
            return {**joblib.load(home), "home": True}
    return joblib.load(PANEL_DIR / f"{target}__{name}.joblib")


@lru_cache(maxsize=None)
def _filter(population: str, confirm: float, discard: float):
    return load_default_filter(population, confirm=confirm, discard=discard)


@lru_cache(maxsize=None)
def _egfr_shift(population: str) -> float:
    """Offset of the eGFR < 60 event for the population (0 with the raw NHANES models)."""
    recal = load_recalibration() if population == "espana" else None
    return float(recal["egfr"]["constante_fg_menor_60"]) if recal else 0.0


# Cached panel predictions: (variable, with urine, predictors) -> distribution.
# Predicting patient by patient is slow (hundreds of trees per variable); ``warm_up``
# computes them in one go for a whole practice list.
_PMF_CACHE: dict = {}


def _predict_pmf(target: str, with_urine: bool, X: np.ndarray) -> np.ndarray:
    key = (target, with_urine, X.tobytes())
    if key not in _PMF_CACHE:
        if len(_PMF_CACHE) > 200_000:
            _PMF_CACHE.clear()
        _PMF_CACHE[key] = _panel_model(target, with_urine)["model"].predict_pmf(X)
    return _PMF_CACHE[key]


def _blood_pressure(record: ClinicalRecord) -> tuple[HomeBP | None, float | None, float | None]:
    """Blood pressure to use: valid home self-measurement is more reliable than an office reading."""
    home_bp = summarize_home_bp(record.home_bp)
    if home_bp is not None and home_bp.valid:
        return home_bp, home_bp.office_sbp, home_bp.office_dbp
    return home_bp, record.sbp, record.dbp


def warm_up(records, population: str = "espana") -> None:
    """Computes the panel predictions for many patients in one go.

    Afterwards ``assess`` for each one is almost instant. Used by the practice-list worklist.
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
        # NHANES only asks about treatment when there is a diagnosis.
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
        if isinstance(last, StripSample):  # a strip gives an approximate value
            uacr = last.nominal_uacr
            creatinine = None if last.spec.ratio_only else last.creatinine_mg_dl
        else:
            uacr, creatinine = last.uacr, last.creatinine_mg_dl
        log_uacr = np.log(uacr)
        if last.sample_type != RANDOM:  # the panel was trained on random (spot) samples
            log_uacr = log_uacr + float(filt.p.bias_at(RANDOM, log_uacr))
        f["log_uacr"] = log_uacr
        if creatinine is not None:
            f["log_urine_creatinine"] = np.log(creatinine)
            f["log_urine_albumin"] = log_uacr + np.log(creatinine / 100.0)
    return f


def _home_features(record: ClinicalRecord, feats: dict) -> dict:
    """Predictors following the conventions of the follow-up cohort (``outcomes.data``).

    Starts from the panel's and adds the home questionnaire and pulse. Drugs are 0 when not
    taken (in the panel they are blank without a diagnosis) and age is capped at 80.
    """
    nan = np.nan

    def answer(value) -> float:
        return nan if value is None else float(value)

    def difficulty(value) -> float:
        # NHANES does not ask under-60s without limitations: counts as none.
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
        "dyspnea": answer(record.dyspnea_on_stairs) if record.age >= 40 else nan,  # only asked from age 40
        "walk_difficulty": difficulty(record.walk_difficulty),
        "stairs_difficulty": difficulty(record.stairs_difficulty),
        "hospitalized": answer(record.hospitalized_last_year),
        "pulse": answer(record.pulse),
        "pulse_irregular": answer(record.pulse_irregular),
    }


class _Variable:
    """Distribution of a lab variable for one patient: measured, finger-prick or estimated."""

    def __init__(
        self,
        variable: str,
        record: ClinicalRecord,
        feats: dict,
        population: str,
        with_urine: bool | None = None,
        home_feats: dict | None = None,
    ):
        target, self.inverse, unit, _, decimals = BLOOD[variable]
        label = BLOOD_LABELS[variable]
        unit = egfr_unit() if variable == "egfr" else unit
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
        source = t("medido", "measured") if self.value is not None else t("estimado", "estimated")
        if self.value is None and variable in record.home_labs and not self.log:
            lab = record.home_labs[variable]
            error = {k: v for k, v in lab.error(variable).items() if v is not None}
            self.pmf = update_pmf(self.bounds, self.pmf[0], lab.value, **error)[None, :]
            source = t("capilar en casa", "finger-prick at home")
        if self.value is None and variable == "hba1c" and bundle.get("home") and record.home_glucose:
            source = t("estimado con la glucosa de casa", "estimated with home glucose")
        if self.value is not None:
            v = float(self.value)
            self.estimate = BloodEstimate(label, unit, v, v, v, True, decimals, source)
        else:
            q = self.inverse(self.model.quantiles(self.X, [0.1, 0.5, 0.9], pmf=self.pmf)[0])
            self.estimate = BloodEstimate(label, unit, float(q[1]), float(q[0]), float(q[2]), False, decimals, source)

    def p_below(self, threshold: float) -> float:
        """P(variable < threshold); exact (0 or 1) if the value was measured in the lab."""
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
        """Mean of the variable within [lo, hi) (uniform within each bin)."""
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
    """Full assessment of one patient.

    - ``population``: ``"espana"`` uses the priors recalibrated to Spanish primary care (if
      available; see ``recalibration``); ``"nhanes"``, the models as fitted.
    - ``thresholds``: probabilities above which to act (see ``decision``).
    - ``joint``: how eGFR and albuminuria are combined when eGFR is not measured. ``"panel"``
      (default): the panel gives the eGFR distribution and the albuminuria filter is solved for
      each category; ``"bayes"``: in addition, the urine samples update that distribution;
      ``"independent"``: as if unrelated. On NHANES the three are indistinguishable
      (``reports/robustez.md``); the first is used because it is coherent and no worse.
    - ``detail=False`` skips how much another urine sample would help (faster, for a whole list).
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

    # --- eGFR: measured, from history (trend) or estimated ---
    trend = None
    measured_egfr = record.measured.get("egfr")
    history = list(record.egfr_history)
    if history:
        if measured_egfr is not None and as_of is not None and all(m.date != as_of for m in history):
            history.append(EgfrMeasurement(as_of, measured_egfr))
        # Provisional albuminuria with the latest lab test, only for the slope prior.
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
        # Representative value of each category: the closest to the estimated level.
        g_values = [float(np.clip(trend.level, lo, hi - 0.5)) for lo, hi in G_RANGES]
        lo, hi = trend.interval("level")
        source = t(f"tendencia de {trend.n} analíticas", f"trend from {trend.n} lab tests")
        blood["egfr"] = BloodEstimate(BLOOD_LABELS["egfr"], egfr_unit(), trend.level, lo, hi, False, 0, source)
    elif measured_egfr is not None:
        g_probs = _g_probs([float(measured_egfr < e) for e in G_EDGES])
        g_values = [float(measured_egfr)] * 6
    else:
        source = egfr
        if joint == "bayes" and samples:
            # Start from the panel without urine (with the finger-prick, if any) and let urine update it.
            source = _Variable("egfr", record, feats, population, with_urine=False)
        g_probs = _g_probs([source.p_below(e) for e in G_EDGES])
        g_values = [source.range_mean(lo, hi) for lo, hi in G_RANGES]

    # --- Albuminuria, conditioned on each eGFR category ---
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
        diabetes, p_diabetes = t("diagnosticada", "diagnosed"), None
    else:
        p_diabetes = 1.0 - variables["hba1c"].p_below(6.5)
        if p_diabetes >= 0.5:
            diabetes = t("probable", "likely")
        elif p_diabetes >= 0.1:
            diabetes = t("posible", "possible")
        else:
            diabetes = t("poco probable", "unlikely")

    # --- Heart failure: NT-proBNP ≥ 125 pg/ml (rule-out threshold in primary care) ---
    if record.heart_failure:
        heart, p_bnp = t("diagnosticada", "diagnosed"), None
    else:
        p_bnp = 1.0 - variables["nt_probnp"].p_below(125.0)
        heart = t("a descartar", "to rule out") if p_bnp >= thresholds.nt_probnp else t("poco probable", "unlikely")

    # --- Home heart recording: low ejection fraction ---
    p_low_ef = None
    if record.heart_checks and not record.heart_failure:
        p_low_ef = low_ef_probability(record.heart_checks, record.age, coronary=record.coronary)
        if p_low_ef >= thresholds.echo:
            heart = t("a descartar", "to rule out")

    # --- Rhythm ---
    p_af = None
    if record.rhythm_checks and not record.atrial_fibrillation:
        p_af = af_probability(record.rhythm_checks, record.age, female=record.female)

    cv = _cv_risk(record, variables, joint_ga, alb, sbp, known_g or bool(history))
    finding_by_test = dict(cv.finding_by_test)
    p_diabetes_pending = p_diabetes if (p_diabetes is not None and "hba1c" not in record.measured) else 0.0
    if p_diabetes_pending:
        # Without home glucose the first step is the meter; with it, what remains is confirming with HbA1c.
        # (Keys of ``finding_by_test`` are machine values read by the web front end.)
        finding_by_test["HbA1c" if record.home_glucose else "glucosa"] = p_diabetes_pending
    # Hidden diabetes is taken as independent of the kidney or cardiovascular finding.
    p_new_finding = 1.0 - (1.0 - cv.p_finding) * (1.0 - p_diabetes_pending)
    if p_low_ef is not None and p_low_ef >= thresholds.echo:
        finding_by_test["ecocardiograma"] = p_low_ef
        p_new_finding = 1.0 - (1.0 - p_new_finding) * (1.0 - p_low_ef)
    alerts = _alerts(record, alb, trend, home_bp, variables, p_af, thresholds)
    recs = _recommendations(record, alb, p_g3, p_diabetes, p_bnp, cv, home_bp, sbp, p_af, thresholds, bool(history), p_low_ef)
    channel = choose_channel(record.age, record.has_smartphone).value
    home = outcome_risk.home_risk(home_feats)
    # Symptom questions do not change the ranking of cardiovascular death risk, but they do
    # sharpen who will have a high NT-proBNP over age 60 (reports/insuficiencia_cardiaca.md).
    symptoms_unknown = record.dyspnea_on_stairs is None or record.walk_difficulty is None
    if record.age >= 60 and p_bnp is not None and p_bnp >= thresholds.nt_probnp and symptoms_unknown:
        recs.append(
            Recommendation(
                t("Preguntas sobre síntomas", "Symptom questions"),
                t(
                    "Falta de aire al subir cuestas y dificultad para caminar, contestadas desde casa: afinan la sospecha "
                    "de insuficiencia cardíaca antes de pedir el NT-proBNP.",
                    "Shortness of breath walking uphill and difficulty walking, answered from home: they sharpen the "
                    "suspicion of heart failure before ordering NT-proBNP.",
                ),
            )
        )
    return PatientAssessment(
        alb, blood, p_g3, kdigo_g, risk, p_ckd, diabetes, p_diabetes, heart, p_bnp, recs,
        kdigo_joint=joint_ga, egfr_trend=trend, cv=cv, home_bp=home_bp, p_af=p_af, p_low_ef=p_low_ef, alerts=alerts, channel=channel,
        p_new_finding=p_new_finding, finding_by_test=finding_by_test, home_risk=home,
    )  # fmt: skip


def _cv_risk(record, variables, joint_ga, alb, sbp, egfr_known: bool) -> cvrisk.CvRisk:
    """Cardiovascular risk category with the uncertainty of what is still unmeasured."""
    approximate = record.age < 40  # SCORE2 starts at 40: younger patients are scored as if they were 40
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
        else:  # no measured HDL: five equally likely values from its sex-specific distribution
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
    """Findings already clear enough to act on (no further test is needed to see them)."""
    out = []
    if alb.status == "confirmada" and not record.kidney_disease:
        out.append(t("Albuminuria persistente sin enfermedad renal crónica registrada.", "Persistent albuminuria with no chronic kidney disease on record."))
    if not record.kidney_disease:
        if trend is not None and trend.chronic_below_60:
            out.append(
                t(
                    "FG por debajo de 60 en analíticas separadas más de tres meses, sin enfermedad renal crónica registrada.",
                    "eGFR below 60 in lab tests more than three months apart, with no chronic kidney disease on record.",
                )
            )
    if trend is not None and trend.status == "descenso_rapido":
        slope = _num(trend.slope, 1)
        out.append(t(f"Descenso rápido del FG: {slope} ml/min/1,73 m² al año.", f"Rapid eGFR decline: {slope} ml/min/1.73 m² per year."))
    elif trend is not None and trend.status == "descenso":
        slope = _num(trend.slope, 1)
        out.append(t(f"Descenso sostenido del FG: {slope} ml/min/1,73 m² al año.", f"Sustained eGFR decline: {slope} ml/min/1.73 m² per year."))
    if home_bp is not None and home_bp.valid and home_bp.p_high >= 0.9:
        out.append(home_bp.message + (t(" Sin hipertensión registrada.", " No hypertension on record.") if not record.hypertension else ""))
    if not record.diabetes and fasting_days_above(record.home_glucose) >= 2:
        out.append(
            t(
                f"Glucosa en ayunas de {DIABETES_FASTING_GLUCOSE:.0f} mg/dl o más en dos días distintos, medida en casa, sin "
                "diabetes registrada: confirmar con HbA1c.",
                f"Fasting glucose of {DIABETES_FASTING_GLUCOSE:.0f} mg/dl or more on two different days, measured at home, with no "
                "diabetes on record: confirm with HbA1c.",
            )
        )
    hba1c = record.measured.get("hba1c")
    if hba1c is not None and hba1c >= 6.5 and not record.diabetes:
        value = _num(hba1c, 1)
        out.append(
            t(
                f"HbA1c de {value} % sin diabetes registrada (confirmar con una segunda determinación).",
                f"HbA1c of {value}% with no diabetes on record (confirm with a second test).",
            )
        )
    bnp = record.measured.get("nt_probnp")
    if bnp is not None and bnp >= 125 and not record.heart_failure:
        value = _num(bnp)
        out.append(
            t(
                f"NT-proBNP de {value} pg/ml sin insuficiencia cardíaca registrada: pedir ecocardiograma.",
                f"NT-proBNP of {value} pg/ml with no heart failure on record: order an echocardiogram.",
            )
        )
    if p_af is not None and p_af >= 0.5:
        out.append(
            t(
                f"Pulso irregular repetido en casa (P(fibrilación auricular) = {p_af:.0%}).",
                f"Repeated irregular pulse at home (P(atrial fibrillation) = {p_af:.0%}).",
            )
        )
    return out


def _recommendations(record, alb, p_g3, p_diabetes, p_bnp, cv, home_bp, sbp, p_af, thresholds, has_history, p_low_ef=None) -> list[Recommendation]:
    recs = []
    if alb.status in ("sin_medir", "dudosa", "pendiente_cronicidad"):
        recs.append(Recommendation(urine_test(), alb.action))
    egfr_pending = "egfr" not in record.measured and not has_history
    if egfr_pending and p_g3 > thresholds.creatinine:
        how = (
            t(" Ya hay una punción capilar; conviene confirmarla en el laboratorio.", " There is already a finger-prick result; it should be confirmed in the lab.")
            if "egfr" in record.home_labs
            else ""
        )
        recs.append(
            Recommendation(
                t("Creatinina (FG)", "Creatinine (eGFR)"),
                t(
                    f"P(FG < 60) estimada: {p_g3:.0%}; hay que medirlo para estadificar la ERC.{how}",
                    f"Estimated P(eGFR < 60): {p_g3:.0%}; it must be measured to stage CKD.{how}",
                ),
            )
        )
    single_egfr = record.measured.get("egfr")
    if single_egfr is not None and single_egfr < 60 and not has_history and not record.kidney_disease:
        recs.append(
            Recommendation(
                t("Repetir creatinina a los tres meses", "Repeat creatinine in three months"),
                t(
                    "Un FG por debajo de 60 aislado no basta para el diagnóstico: hay que confirmarlo pasados tres meses.",
                    "A single eGFR below 60 is not enough for the diagnosis: it must be confirmed after three months.",
                ),
            )
        )
    if p_diabetes is not None and "hba1c" not in record.measured:
        # Two steps: capillary glucose is measured on low suspicion; the lab test follows if that glucose keeps it up.
        if record.home_glucose:
            if p_diabetes > thresholds.hba1c:
                recs.append(
                    Recommendation(
                        "HbA1c",
                        t(
                            f"P(diabetes sin diagnosticar) con la glucosa capilar: {p_diabetes:.0%}. Confirmar con análisis.",
                            f"P(undiagnosed diabetes) with the capillary glucose: {p_diabetes:.0%}. Confirm with a lab test.",
                        ),
                    )
                )
        elif p_diabetes > thresholds.home_glucose:
            recs.append(
                Recommendation(
                    home_glucose_test(),
                    t(
                        f"P(diabetes sin diagnosticar) estimada: {p_diabetes:.0%}. Una medida de glucosa lo aclara casi siempre sin análisis.",
                        f"Estimated P(undiagnosed diabetes): {p_diabetes:.0%}. A glucose reading almost always settles it without a lab test.",
                    ),
                )
            )
    if p_bnp is not None and "nt_probnp" not in record.measured and p_bnp >= thresholds.nt_probnp:
        recs.append(
            Recommendation(
                "NT-proBNP",
                t(f"P(NT-proBNP ≥ 125) estimada: {p_bnp:.0%}; si sale alto, ecocardiograma.", f"Estimated P(NT-proBNP ≥ 125): {p_bnp:.0%}; if high, echocardiogram."),
            )
        )
    treat_kidney = alb.status in ("confirmada", "pendiente_cronicidad") or p_g3 >= 0.5
    if treat_kidney and "potassium" not in record.measured:
        recs.append(
            Recommendation(
                t("Potasio", "Potassium"),
                t("Antes de iniciar o subir IECA/ARA-II o finerenona.", "Before starting or increasing an ACE inhibitor/ARB or finerenone."),
            )
        )
    if cv is not None and cv.p_up_by_test.get("lípidos", 0.0) >= 0.05:
        recs.append(
            Recommendation(
                t("Colesterol total y HDL", "Total and HDL cholesterol"),
                t(
                    f"Sin ellos no se puede calcular el SCORE2; probabilidad de que suba de categoría: {cv.p_up_by_test['lípidos']:.0%}.",
                    f"SCORE2 cannot be calculated without them; probability of moving up a category: {cv.p_up_by_test['lípidos']:.0%}.",
                ),
            )
        )
    if home_bp is not None and not home_bp.valid:
        recs.append(Recommendation(home_bp_test(), home_bp.message))
    elif home_bp is None and (sbp is None or (sbp >= 135 and not record.hypertension) or (sbp >= 140 and record.hypertension)):
        if sbp is None:
            why = t("No hay tensión registrada.", "No blood pressure on record.")
        else:
            why = t(f"Tensión en consulta de {sbp:.0f} mmHg.", f"Office blood pressure of {sbp:.0f} mmHg.")
        recs.append(Recommendation(home_bp_test(), f"{why} {home_bp_how()}"))
    if p_af is not None and p_af >= thresholds.ecg:
        recs.append(
            Recommendation(
                "ECG",
                t(f"P(fibrilación auricular) tras las comprobaciones en casa: {p_af:.0%}.", f"P(atrial fibrillation) after the home checks: {p_af:.0%}."),
            )
        )
    if p_low_ef is not None and p_low_ef >= thresholds.echo:
        recs.append(
            Recommendation(
                t("Ecocardiograma", "Echocardiogram"),
                t(
                    f"P(fracción de eyección ≤ 40 %) tras la grabación del corazón en casa: {p_low_ef:.0%}. "
                    "Pedir antes el NT-proBNP si hay lista de espera: si sale alto, el ecocardiograma es preferente.",
                    f"P(ejection fraction ≤ 40%) after the home heart recording: {p_low_ef:.0%}. "
                    "Order NT-proBNP first if there is a waiting list: if it is high, the echocardiogram is a priority.",
                ),
            )
        )
    return recs


def _num(v: float, decimals: int = 0) -> str:
    """Number in the current language: "3.333; 5,8" in Spanish, "3,333; 5.8" in English."""
    return fmt_num(v, decimals)


def describe(a: PatientAssessment) -> str:
    """Plain-text summary for the clinician."""
    lines = []
    if a.alerts:
        lines += [t("HALLAZGOS QUE PIDEN ACTUAR", "FINDINGS THAT CALL FOR ACTION"), *("  - " + alert for alert in a.alerts)]
    lines += ["ALBUMINURIA", *("  " + line for line in describe_albuminuria(a.albuminuria).splitlines())]
    lines.append(
        t(
            "ANALÍTICA (medida o estimada con la historia y la orina; 80 % de probabilidad)",
            "LABS (measured, or estimated from the record and urine; 80% probability)",
        )
    )
    for est in a.blood.values():
        median, low, high = (_num(v, est.decimals) for v in (est.median, est.low, est.high))
        unit = f" {est.unit}" if (est.unit != "%" or is_es()) else est.unit
        if est.measured:
            lines.append(f"  {est.name}: {median}{unit} " + t("(medido)", "(measured)"))
        else:
            lines.append(f"  {est.name}: {median}{unit} " + t(f"(entre {low} y {high}, {est.source})", f"(between {low} and {high}, {est.source})"))
    if a.egfr_trend is not None:
        lines += [t("TENDENCIA DEL FG", "eGFR TREND"), *("  " + line for line in describe_trend(a.egfr_trend).splitlines())]
    if a.home_bp is not None:
        lines += [t("EN CASA", "AT HOME"), f"  {a.home_bp.message}"]
    risk = ", ".join(f"{KDIGO_RISK_LABELS.get(k, k)} {v:.0%}" for k, v in a.kdigo_risk.items())
    p_dm = f" (P = {a.p_diabetes:.0%})" if a.p_diabetes is not None else ""
    p_bnp = f" (P(NT-proBNP ≥ 125) = {a.p_nt_probnp_high:.0%})" if a.p_nt_probnp_high is not None else ""
    lines += [
        t("DIAGNÓSTICOS", "DIAGNOSES"),
        t(
            f"  Enfermedad renal crónica: P(FG < 60 o albuminuria ≥ 30) = {a.p_ckd:.0%}; riesgo KDIGO: {risk}",
            f"  Chronic kidney disease: P(eGFR < 60 or albuminuria ≥ 30) = {a.p_ckd:.0%}; KDIGO risk: {risk}",
        ),
        f"  Diabetes: {a.diabetes}" + p_dm,
        t(f"  Insuficiencia cardíaca: {a.heart_failure}", f"  Heart failure: {a.heart_failure}") + p_bnp,
    ]
    if a.p_af is not None:
        lines.append(
            t(
                f"  Fibrilación auricular: P = {a.p_af:.0%} tras las comprobaciones del ritmo en casa",
                f"  Atrial fibrillation: P = {a.p_af:.0%} after the home rhythm checks",
            )
        )
    if a.p_low_ef is not None:
        lines.append(
            t(
                f"  Fracción de eyección baja: P = {a.p_low_ef:.0%} tras la grabación del corazón en casa",
                f"  Low ejection fraction: P = {a.p_low_ef:.0%} after the home heart recording",
            )
        )
    if a.cv is not None:
        lines += [t("RIESGO CARDIOVASCULAR", "CARDIOVASCULAR RISK"), *("  " + line for line in cvrisk.describe(a.cv).splitlines())]
    if a.home_risk is not None:
        lines += [
            t("RIESGO CON LO MEDIDO EN CASA", "RISK FROM HOME MEASUREMENTS"),
            *("  " + line for line in outcome_risk.describe(a.home_risk).splitlines()),
        ]
    if a.p_new_finding >= 0.005:
        by_test = sorted(a.finding_by_test.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{cvrisk.TEST_LABELS.get(test, test)} {p:.0%}" for test, p in by_test if p >= 0.005)
        heading = t("HALLAZGO NUEVO SI SE COMPLETAN LAS PRUEBAS", "NEW FINDING IF THE TESTS ARE COMPLETED")
        lines.append(f"{heading}: {a.p_new_finding:.0%}" + (f" ({detail})" if detail else ""))
    lines.append(t("PRUEBAS RECOMENDADAS", "RECOMMENDED TESTS"))
    lines += [f"  - {r.test}: {r.reason}" for r in a.recommendations] or [t("  (ninguna)", "  (none)")]
    return "\n".join(lines)
