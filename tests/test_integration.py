"""Evaluación integrada, lista del cupo, recalibración y pacientes de prueba."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from latenthealth.albuminuria import (
    DEFAULT_PARAMS_PATH,
    FIRST_MORNING,
    PHONE_STRIP,
    RANDOM,
    AlbuminuriaParams,
    StripSample,
    UrineSample,
)
from latenthealth.albuminuria.model import covariates
from latenthealth.assessment import PANEL_DIR, ClinicalRecord, assess, describe
from latenthealth.cohort import record_from_row
from latenthealth.cvrisk import HIGH, VERY_HIGH
from latenthealth.decision import Utilities
from latenthealth.home import BPReading, HomeLab, RhythmCheck
from latenthealth.kidney_trend import EgfrMeasurement, TreatmentStart
from latenthealth.recalibration import (
    age_group,
    cdf_from_pmf,
    egfr_2009_cut_in_2021_scale,
    fit_prior_offset,
    fit_shift,
    reference_weights,
    sample_prevalence,
    shift_below,
)
from latenthealth.worklist import ACT, MEASURE, NOTHING, rank_cupo
from latenthealth.worklist import describe as describe_worklist

needs_models = pytest.mark.skipif(
    not PANEL_DIR.exists() or not any(PANEL_DIR.glob("*.joblib")) or not DEFAULT_PARAMS_PATH.exists(),
    reason="faltan los modelos (scripts/fit_albuminuria.py y scripts/fit_panel.py)",
)
D0 = date(2026, 11, 16)


def yearly(values):
    n = len(values)
    return [EgfrMeasurement(D0 - timedelta(days=365 * (n - 1 - i)), v) for i, v in enumerate(values)]


# --- Evaluación integrada ---


@needs_models
def test_home_strips_feed_the_assessment():
    strips = [StripSample(D0 - timedelta(days=d), PHONE_STRIP, 150, 50) for d in (2, 1)]
    a = assess(ClinicalRecord(age=66, female=False, diabetes=True, urine_samples=strips), as_of=D0)
    assert a.albuminuria.status == "pendiente_cronicidad"
    assert a.p_ckd > 0.9
    assert "ALBUMINURIA" in describe(a)


@needs_models
def test_egfr_history_gives_a_trend_and_an_alert():
    falling = ClinicalRecord(age=68, female=True, diabetes=True, egfr_history=yearly([88, 79, 68, 60, 49]))
    a = assess(falling, as_of=D0)
    assert a.egfr_trend.status == "descenso_rapido"
    assert any("Descenso" in alert for alert in a.alerts)
    assert a.kdigo_g["G3a"] > 0.5
    assert "TENDENCIA DEL FG" in describe(a)
    stable = assess(replace(falling, egfr_history=yearly([75, 77, 74, 76, 75])), as_of=D0)
    assert stable.egfr_trend.status == "estable" and not stable.alerts


@needs_models
def test_known_treatment_start_avoids_a_false_decline_alert():
    base = ClinicalRecord(age=66, female=False, diabetes=True, egfr_history=yearly([74, 73, 67, 66]))
    start = [TreatmentStart(D0 - timedelta(days=365 + 150), "isglt2")]
    blind, aware = assess(base, as_of=D0), assess(replace(base, treatments=start), as_of=D0)
    assert aware.egfr_trend.p_decline < blind.egfr_trend.p_decline


@needs_models
def test_capillary_result_updates_the_estimate_without_replacing_it():
    base = ClinicalRecord(age=74, female=True, hypertension=True, bp_meds=True, bmi=31)
    without = assess(base)
    with_lab = assess(replace(base, home_labs={"egfr": HomeLab(48.0)}))
    assert with_lab.blood["egfr"].source == "capilar en casa" and not with_lab.blood["egfr"].measured
    assert with_lab.p_egfr_below_60 > without.p_egfr_below_60
    assert with_lab.blood["egfr"].high - with_lab.blood["egfr"].low < without.blood["egfr"].high - without.blood["egfr"].low
    assert any(r.test.startswith("Creatinina") for r in with_lab.recommendations)


@needs_models
def test_home_blood_pressure_and_rhythm_reach_alerts_and_recommendations():
    readings = [
        BPReading(D0 - timedelta(days=10 - d), 150 + (2 if evening else -2), 92, evening)
        for d in range(7)
        for evening in (False, False, True, True)
    ]
    checks = [RhythmCheck(D0 - timedelta(days=2), True), RhythmCheck(D0 - timedelta(days=1), True)]
    a = assess(ClinicalRecord(age=72, female=False, sbp=132, home_bp=readings, rhythm_checks=checks), as_of=D0)
    assert a.home_bp.valid and a.home_bp.p_high > 0.9
    assert any("Tensión alta en casa" in alert for alert in a.alerts)
    assert a.p_af > 0.5 and any(r.test == "ECG" for r in a.recommendations)
    quiet = assess(ClinicalRecord(age=72, female=False, sbp=128, rhythm_checks=[RhythmCheck(D0, False)]), as_of=D0)
    assert quiet.p_af < 0.05 and not any(r.test == "ECG" for r in quiet.recommendations)


@needs_models
def test_cardiovascular_category_and_what_the_urine_would_change():
    # FG 50 medido y lípidos conocidos; sin orina. La albuminuria subiría la categoría.
    rec = ClinicalRecord(age=52, female=True, sbp=118, measured={"egfr": 50.0, "total_cholesterol": 180, "hdl": 65, "hba1c": 5.3})
    a = assess(rec)
    assert a.cv.recorded == 0
    assert a.cv.p_up == pytest.approx(a.albuminuria.p_a2_plus, abs=0.02)
    assert a.cv.best_test == "orina"
    assert 0 < a.p_new_finding < 1
    confirmed = replace(
        rec,
        urine_samples=[
            UrineSample(D0 - timedelta(days=120), 150.0, FIRST_MORNING, creatinine_mg_dl=110),
            UrineSample(D0, 140.0, FIRST_MORNING, creatinine_mg_dl=100),
        ],
    )
    b = assess(confirmed, as_of=D0)
    assert b.cv.recorded == HIGH and b.cv.p_up < 0.01
    assert assess(replace(rec, coronary=True)).cv.recorded == VERY_HIGH


@needs_models
def test_unknown_egfr_and_albuminuria_are_not_treated_as_independent():
    # Una albuminuria muy alta hace más probable un FG bajo, y al revés.
    high = [UrineSample(D0, 900.0, RANDOM, creatinine_mg_dl=90)]
    rec = ClinicalRecord(age=71, female=False, diabetes=True, hypertension=True, urine_samples=high)
    together = assess(rec, population="nhanes", joint="bayes")
    apart = assess(rec, population="nhanes", joint="independent")
    assert together.kdigo_joint.sum() == pytest.approx(1.0)
    assert together.kdigo_joint.shape == (6, 3)
    assert together.albuminuria.egfr_components
    # La probabilidad conjunta de FG < 60 y albuminuria no es el producto de las marginales.
    j = together.kdigo_joint
    assert j[2:, 1:].sum() != pytest.approx(j[2:].sum() * j[:, 1:].sum(), abs=1e-4)
    assert apart.kdigo_joint[2:, 1:].sum() == pytest.approx(apart.kdigo_joint[2:].sum() * apart.kdigo_joint[:, 1:].sum(), abs=1e-6)


@needs_models
def test_spanish_recalibration_lowers_the_chance_of_low_egfr():
    rec = ClinicalRecord(age=72, female=True, hypertension=True, bp_meds=True)
    assert assess(rec, population="espana").p_egfr_below_60 < assess(rec, population="nhanes").p_egfr_below_60


@needs_models
def test_thresholds_change_what_is_recommended():
    rec = ClinicalRecord(age=55, female=False, bmi=27)
    relaxed = assess(rec, thresholds=Utilities(tests_creatinine=2, tests_hba1c=2).thresholds())
    eager = assess(rec, thresholds=Utilities(tests_creatinine=200, tests_hba1c=200).thresholds())
    names = lambda a: {r.test for r in a.recommendations}  # noqa: E731
    glucose = "Glucosa capilar en ayunas (en casa)"
    assert glucose in names(eager) and glucose not in names(relaxed)


# --- Lista del cupo ---


@needs_models
def test_worklist_puts_clear_findings_first_and_leaves_out_the_well_studied():
    cupo = {
        "sana": ClinicalRecord(
            age=45, female=True, sbp=116,
            measured={"egfr": 101, "hba1c": 5.2, "total_cholesterol": 180, "hdl": 65},
            urine_samples=[UrineSample(D0 - timedelta(days=30), 4.0, FIRST_MORNING, creatinine_mg_dl=110)],
        ),
        "sin estudiar": ClinicalRecord(age=79, female=False, hypertension=True, bp_meds=True, sbp=150, diabetes=True),
        "algo pendiente": ClinicalRecord(age=58, female=False, sbp=128, measured={"egfr": 88, "total_cholesterol": 190, "hdl": 50}),
        "albuminuria confirmada": ClinicalRecord(
            age=70, female=False, diabetes=True,
            urine_samples=[
                UrineSample(D0 - timedelta(days=130), 140.0, FIRST_MORNING, creatinine_mg_dl=110),
                UrineSample(D0 - timedelta(days=10), 120.0, FIRST_MORNING, creatinine_mg_dl=120),
            ],
            measured={"egfr": 52.0, "hba1c": 7.9},
        ),
    }  # fmt: skip
    rows = rank_cupo(cupo, as_of=D0)
    assert [r.patient_id for r in rows][0] == "albuminuria confirmada"
    groups = {r.patient_id: r.group for r in rows}
    assert groups == {"albuminuria confirmada": ACT, "sin estudiar": MEASURE, "algo pendiente": MEASURE, "sana": NOTHING}
    measure = [r for r in rows if r.group == MEASURE]
    assert measure[0].patient_id == "sin estudiar" and measure[0].p_finding > measure[1].p_finding
    assert measure[0].test in ("orina", "creatinina", "glucosa")
    text = describe_worklist(rows)
    assert "ACTUAR" in text and "MEDIR" in text and "Sin pendientes: 1 de 4" in text


# --- Recalibración ---


def test_shift_below_moves_only_the_event_odds():
    bounds = np.array([10.0, 30.0, 45.0, 60.0, 90.0, 120.0])
    pmf = np.array([[0.05, 0.10, 0.15, 0.40, 0.30]])
    shifted = shift_below(pmf, bounds, 60.0, np.log(0.5))
    before, after = pmf[0, :3].sum(), shifted[0, :3].sum()
    assert after / (1 - after) == pytest.approx(0.5 * before / (1 - before))
    assert shifted[0, 3] / shifted[0, 4] == pytest.approx(pmf[0, 3] / pmf[0, 4])
    assert shifted[0, 0] / shifted[0, 2] == pytest.approx(pmf[0, 0] / pmf[0, 2])
    assert cdf_from_pmf(pmf, bounds, 60.0)[0] == pytest.approx(0.30)


def test_fit_shift_hits_the_target_prevalence():
    rng = np.random.default_rng(0)
    bounds = np.array([10.0, 30.0, 45.0, 60.0, 90.0, 120.0])
    pmf = rng.dirichlet([1, 2, 3, 8, 6], size=500)
    weights = np.full(500, 1 / 500)
    delta = fit_shift(pmf, bounds, 60.0, np.full(500, 60.0), weights, 0.15)
    assert weights @ cdf_from_pmf(shift_below(pmf, bounds, 60.0, delta), bounds, 60.0) == pytest.approx(0.15, abs=1e-3)


def test_reference_weights_match_age_and_sex_margins():
    rng = np.random.default_rng(1)
    age, female = rng.uniform(20, 80, 5000), rng.random(5000) < 0.5
    w = reference_weights(age, female)
    assert w.sum() == pytest.approx(1.0)
    assert w[female].sum() == pytest.approx(0.58, abs=1e-3)
    share_old = w[age_group(age) == 2].sum()
    assert share_old == pytest.approx(4937 / (1533 + 3370 + 4937), abs=1e-3)


def test_2009_equation_cut_is_a_bit_higher_on_the_2021_scale():
    cuts = egfr_2009_cut_in_2021_scale([40, 60, 80], [True, False, True])
    assert np.all((cuts > 60) & (cuts < 68))


@pytest.mark.skipif(not DEFAULT_PARAMS_PATH.exists(), reason="faltan los parámetros ajustados")
def test_prior_offset_is_recovered_from_the_prevalence_it_produces():
    params = AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)
    rng = np.random.default_rng(2)
    n = 300
    Z = covariates(rng.uniform(30, 80, n), rng.random(n) < 0.5, rng.random(n) < 0.15, rng.uniform(40, 110, n))
    weights = np.full(n, 1 / n)
    target = float(weights @ sample_prevalence(replace(params, prior_logit_offset=0.6), Z, RANDOM))
    assert fit_prior_offset(params, Z, weights, target, RANDOM) == pytest.approx(0.6, abs=0.01)
    assert target > float(weights @ sample_prevalence(params, Z, RANDOM))


# --- Pacientes de prueba ---


def test_record_from_a_nhanes_row_hides_what_is_not_given():
    row = pd.Series(
        dict(
            age=63.0, female=1.0, bmi=30.1, waist=np.nan, sbp=141.0, dbp=82.0, dx_diabetes=1.0, dx_prediabetes=0.0,
            insulin=np.nan, diabetes_pills=1.0, dx_hypertension=1.0, bp_meds=1.0, dx_high_cholesterol=0.0,
            cholesterol_meds=np.nan, dx_heart_failure=0.0, dx_coronary=0.0, dx_stroke=0.0, dx_kidney=0.0,
            smoker_now=0.0, smoker_ever=1.0, log_uacr=np.log(42.0), log_urine_creatinine=np.log(95.0),
            egfr=71.0, total_cholesterol=205.0, hdl=np.nan,
        )
    )  # fmt: skip
    rec = record_from_row(row, urine=True, labs=("total_cholesterol", "hdl"))
    assert rec.female and rec.diabetes and rec.diabetes_pills and not rec.insulin and rec.waist is None
    assert rec.urine_samples[0].uacr == pytest.approx(42.0) and rec.urine_samples[0].sample_type == RANDOM
    assert rec.measured == {"total_cholesterol": 205.0}
    assert record_from_row(row, urine=False).urine_samples == []
