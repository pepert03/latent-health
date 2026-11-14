"""Tira en casa, preguntas de contexto y protocolo de repetición."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from latenthealth.albuminuria import (
    DEFAULT_PARAMS_PATH,
    EYE_STRIP,
    FIRST_MORNING,
    KITS,
    PHONE_STRIP,
    RATIO_STRIP,
    AlbuminuriaFilter,
    AlbuminuriaParams,
    Channel,
    Patient,
    SampleContext,
    StripSample,
    StripSpec,
    UrineSample,
    choose_channel,
    fit_strip_spec,
    next_step,
)
from latenthealth.albuminuria.context import deferral, spike_offset
from latenthealth.albuminuria.model import covariates, spike_prob
from latenthealth.albuminuria.strip import dilution_grid, outcome_table, simulate_reading

D0 = date(2026, 3, 2)


@pytest.fixture(scope="module")
def flt():
    if not DEFAULT_PARAMS_PATH.exists():
        pytest.skip("faltan los parámetros ajustados (scripts/fit_albuminuria.py)")
    return AlbuminuriaFilter(AlbuminuriaParams.load(DEFAULT_PARAMS_PATH))


def person(*samples, female=False, age=66, diabetes=True):
    return Patient(age=age, female=female, diabetes=diabetes, egfr=78, samples=list(samples))


def strip(days, albumin, creatinine, spec=PHONE_STRIP, context=None):
    return StripSample(D0 + timedelta(days=days), spec, albumin, creatinine, context=context)


# --- Tira ---


@pytest.mark.parametrize("spec", [PHONE_STRIP, EYE_STRIP, RATIO_STRIP])
def test_strip_outcomes_are_a_probability_distribution(flt, spec):
    z = covariates([66], [0], [1], [78])
    table = outcome_table(flt.p, z, FIRST_MORNING, spec, flt.x)
    assert table.sum(axis=(0, 1)) == pytest.approx(np.ones(flt.x.size), abs=1e-6)
    expected = (3, 1) if spec.ratio_only else (len(spec.albumin_levels), len(spec.creatinine_levels))
    assert table.shape[:2] == expected


def test_dilution_grid_keeps_the_stored_quantiles_range(flt):
    stored = np.asarray(flt.p.dilution_quantiles[FIRST_MORNING])
    grid = dilution_grid(flt.p, FIRST_MORNING, 20)
    assert np.all(np.diff(grid) > 0)
    assert grid.mean() == pytest.approx(stored.mean(), abs=0.03)


def test_higher_albumin_pad_means_more_albuminuria(flt):
    probs = [flt.assess(person(strip(0, level, 100))).p_a2_plus for level in PHONE_STRIP.albumin_levels]
    assert np.all(np.diff(probs) > 0)
    assert probs[0] < 0.05 and probs[-1] > 0.9


def test_same_albumin_in_diluted_urine_means_more_albuminuria(flt):
    diluted = flt.assess(person(strip(0, 30, 50))).p_a2_plus
    concentrated = flt.assess(person(strip(0, 30, 300))).p_a2_plus
    assert diluted > concentrated


def test_strip_is_less_informative_than_the_laboratory(flt):
    # Tira "30 mg/l, 100 mg/dl" ≈ 30 mg/g; el laboratorio con 30 mg/g exactos estrecha más.
    by_strip = flt.assess(person(strip(0, 30, 100)))
    by_lab = flt.assess(person(UrineSample(D0, 30.0, FIRST_MORNING, creatinine_mg_dl=100)))
    assert (by_strip.high / by_strip.low) > (by_lab.high / by_lab.low)


def test_strip_calibration_recovers_bias_and_noise():
    rng = np.random.default_rng(1)
    truth = replace(PHONE_STRIP, albumin_log_bias=0.3, albumin_log_sd=0.5, creatinine_log_bias=-0.2, creatinine_log_sd=0.35)
    n = 3000
    log_creat = np.log(100.0) + 0.6 * rng.standard_normal(n)
    log_uacr = np.log(20.0) + 1.3 * rng.standard_normal(n)
    a_idx, c_idx = simulate_reading(truth, log_uacr, log_creat - np.log(100.0), rng)
    fitted = fit_strip_spec(
        PHONE_STRIP,
        np.exp(log_uacr + log_creat - np.log(100.0)),
        np.exp(log_creat),
        np.asarray(truth.albumin_levels)[a_idx],
        np.asarray(truth.creatinine_levels)[c_idx],
    )
    assert fitted.albumin_log_bias == pytest.approx(0.3, abs=0.06)
    assert fitted.albumin_log_sd == pytest.approx(0.5, abs=0.06)
    assert fitted.creatinine_log_bias == pytest.approx(-0.2, abs=0.05)
    assert fitted.creatinine_log_sd == pytest.approx(0.35, abs=0.05)


def test_strip_sample_needs_the_readings_its_kind_gives():
    with pytest.raises(ValueError):
        StripSample(D0, PHONE_STRIP)
    with pytest.raises(ValueError):
        StripSample(D0, RATIO_STRIP, albumin_mg_l=30, creatinine_mg_dl=100)
    assert StripSample(D0, RATIO_STRIP, ratio_category=1).outcome == (1, 0)
    assert StripSpec("x").albumin_index(27) == 1


# --- Contexto ---


def test_context_keeps_the_average_and_moves_each_answer(flt):
    assert spike_offset(None, True, 40) == 0.0
    assert spike_offset(SampleContext(), True, 40) == 0.0
    yes = spike_offset(SampleContext(exercise_24h=True), False, 60)
    no = spike_offset(SampleContext(exercise_24h=False), False, 60)
    assert yes > 0 > no
    # La media sobre el contexto reproduce la probabilidad ajustada sin conocerlo.
    z = covariates([60], [0], [0], [90])
    base = spike_prob(flt.p, z, FIRST_MORNING, 0.0)[0]
    mixed = 0.10 * spike_prob(flt.p, z, FIRST_MORNING, 0.0, yes)[0] + 0.90 * spike_prob(flt.p, z, FIRST_MORNING, 0.0, no)[0]
    assert mixed == pytest.approx(base, rel=0.05)


def test_menstruation_only_counts_for_women_of_that_age():
    ctx = SampleContext(menstruation=True)
    assert spike_offset(ctx, True, 35) > 0
    assert spike_offset(ctx, False, 35) == 0.0
    assert spike_offset(ctx, True, 70) == 0.0
    assert deferral(ctx, True, 35)[0] > 0
    assert deferral(ctx, False, 35) == (0, [])


def test_a_high_sample_with_a_cause_counts_less_than_one_without(flt):
    def p_with(context):
        s = UrineSample(D0, 60.0, FIRST_MORNING, creatinine_mg_dl=110, context=context)
        return flt.assess(person(s, female=True, age=40, diabetes=False)).p_a2_plus

    explained = p_with(SampleContext(exercise_24h=True, fever=False, menstruation=True, uti_symptoms=False))
    unknown = p_with(None)
    clean = p_with(SampleContext(exercise_24h=False, fever=False, menstruation=False, uti_symptoms=False))
    assert explained < unknown < clean


# --- Filtrado glomerular incierto ---


def test_egfr_mixture_reduces_to_the_single_value_and_mixes_otherwise(flt):
    samples = [UrineSample(D0, 45.0, FIRST_MORNING, creatinine_mg_dl=100)]
    single = flt.assess(Patient(70, False, True, 50, samples))
    as_mixture = flt.assess(Patient(70, False, True, None, samples), egfr_mixture=[(50.0, 1.0)])
    assert as_mixture.p_a2_plus == pytest.approx(single.p_a2_plus)
    low = flt.assess(Patient(70, False, True, 35, samples)).p_a2_plus
    high = flt.assess(Patient(70, False, True, 95, samples)).p_a2_plus
    mixed = flt.assess(Patient(70, False, True, None, samples), egfr_mixture=[(35.0, 0.5), (95.0, 0.5)])
    assert min(low, high) < mixed.p_a2_plus < max(low, high)
    assert len(mixed.egfr_components) == 2
    assert sum(c.weight for c in mixed.egfr_components) == pytest.approx(1.0)


def test_high_albuminuria_makes_low_egfr_more_likely(flt):
    samples = [UrineSample(D0, 900.0, FIRST_MORNING, creatinine_mg_dl=100)]
    a = flt.assess(Patient(70, False, True, None, samples), egfr_mixture=[(35.0, 0.5), (95.0, 0.5)])
    weights = {c.egfr: c.weight for c in a.egfr_components}
    assert weights[35.0] > 0.5


# --- Protocolo ---


def test_first_step_is_a_strip_and_a_clean_strip_ends_the_episode(flt):
    kit = KITS[Channel.APP]
    first = next_step(flt, person(), kit, D0)
    assert first.action == "tira" and first.on == D0 + timedelta(days=1)
    assert first.questions
    done = next_step(flt, person(strip(1, 10, 100)), kit, D0 + timedelta(days=1))
    assert done.action == "fin_normal" and done.finished


def test_context_defers_the_test_instead_of_wasting_a_strip(flt):
    step = next_step(flt, person(), KITS[Channel.APP], D0, context=SampleContext(fever=True))
    assert step.action == "esperar"
    assert step.on > D0 + timedelta(days=1)


def test_doubt_after_the_strips_escalates_to_the_tube_and_then_to_the_centre(flt):
    kit = KITS[Channel.APP]
    doubtful = [strip(d, 30, 100) for d in (1, 2, 3)]
    step = next_step(flt, person(*doubtful), kit, D0 + timedelta(days=3))
    assert step.action == "tubo"
    tubes = [UrineSample(D0 + timedelta(days=d), 31.0, FIRST_MORNING, creatinine_mg_dl=100) for d in (5, 8)]
    last = next_step(flt, person(*doubtful, *tubes), kit, D0 + timedelta(days=8))
    assert last.action in ("centro", "fin_normal", "repetir_cronicidad")
    assert last.action != "tubo"


def test_clear_positive_waits_three_months_then_goes_to_the_centre(flt):
    kit = KITS[Channel.APP]
    high = [strip(d, 150, 50) for d in (1, 2)]
    step = next_step(flt, person(*high), kit, D0 + timedelta(days=2))
    assert step.action == "repetir_cronicidad"
    assert (step.on - D0).days >= 90
    confirm = UrineSample(D0 + timedelta(days=100), 320.0, FIRST_MORNING, creatinine_mg_dl=60)
    end = next_step(flt, person(*high, confirm), kit, D0 + timedelta(days=100))
    assert end.action == "centro" and end.finished


def test_mail_channel_never_asks_for_a_strip(flt):
    kit = KITS[Channel.MAIL]
    step = next_step(flt, person(), kit, D0)
    assert step.action == "tubo"
    assert "tubo" in step.patient_message


def test_channel_choice_and_instructions_fit_the_patient(flt):
    assert choose_channel(55, has_smartphone=True) is Channel.APP
    assert choose_channel(82) is Channel.MAIL
    assert choose_channel(60, has_smartphone=False) is Channel.MAIL
    assert choose_channel(60, prefers_in_person=True) is Channel.PHARMACY
    message = next_step(flt, person(), KITS[Channel.PHARMACY], D0).patient_message
    assert "farmacia" in message
