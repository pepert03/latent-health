"""Diagnóstico en casa: glucómetro, detector de ritmo y muestra española."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from latenthealth import rhythm
from latenthealth.assessment import PANEL_DIR, ClinicalRecord, assess, describe
from latenthealth.diabetes import GlucoseReading, fasting_days_above, findrisc, summarize_glucose, undiagnosed
from latenthealth.home import RhythmCheck, af_probability
from latenthealth.predimed import PATH as PREDIMED_PATH
from latenthealth.predimed import SHARED, as_followup, load_predimed

D0 = date(2026, 11, 16)

# --- Diabetes ---


def person(**overrides) -> pd.DataFrame:
    base = dict(
        age=40.0, female=0.0, bmi=23.0, waist=85.0, active=1.0, bp_meds=0.0, told_high_glucose=0.0, dx_prediabetes=0.0,
        family_diabetes=0.0, dx_diabetes=0.0, insulin=0.0, diabetes_pills=0.0,
    )  # fmt: skip
    return pd.DataFrame([{**base, **overrides}])


def test_findrisc_adds_the_published_points():
    assert findrisc(person())[0] == 0
    # 58 años (3), IMC 31 (3), cintura de hombre 104 (4), sedentario (2), pastillas de tensión (2),
    # glucosa alta alguna vez (5) y padre diabético (5) = 24.
    high = person(age=58, bmi=31, waist=104, active=0, bp_meds=1, told_high_glucose=1, family_diabetes=1)
    assert findrisc(high)[0] == 24
    assert findrisc(person(female=1.0, waist=85))[0] == 3  # en mujeres la cintura puntúa desde 80 cm
    assert findrisc(person(age=70, bmi=27))[0] == 5
    assert np.isnan(findrisc(person(waist=np.nan))[0])


def test_undiagnosed_excludes_diagnosis_and_treatment():
    d = pd.concat([person(), person(dx_diabetes=1.0), person(diabetes_pills=1.0), person(insulin=1.0)], ignore_index=True)
    assert undiagnosed(d).tolist() == [True, False, False, False]


def test_fasting_readings_are_averaged_and_counted_by_day():
    assert summarize_glucose([]) is None
    readings = [
        GlucoseReading(D0, 130.0, 10.0),
        GlucoseReading(D0 + timedelta(days=1), 120.0, 9.0),
        GlucoseReading(D0 + timedelta(days=1), 180.0, 1.5),  # después de comer: no entra en la media
    ]
    value, hours = summarize_glucose(readings)
    assert value == pytest.approx(np.sqrt(130.0 * 120.0)) and hours == pytest.approx(9.5)
    assert summarize_glucose([GlucoseReading(D0, 165.0, 2.0)]) == (165.0, 2.0)
    assert fasting_days_above(readings) == 1
    assert fasting_days_above(readings + [GlucoseReading(D0 + timedelta(days=2), 131.0, 12.0)]) == 2


@pytest.mark.skipif(not (PANEL_DIR / "hba1c__casa.joblib").exists(), reason="falta el modelo (scripts/fit_diabetes_home.py)")
def test_home_glucose_moves_the_diabetes_estimate():
    base = ClinicalRecord(age=58, female=False, bmi=31, waist=106, sbp=138, hypertension=True, bp_meds=True)
    unknown = assess(base)
    normal = assess(ClinicalRecord(**{**base.__dict__, "home_glucose": [GlucoseReading(D0, 88.0, 10.0)]}))
    high_days = [GlucoseReading(D0 - timedelta(days=i), 142.0 + i, 10.0) for i in range(3)]
    high = assess(ClinicalRecord(**{**base.__dict__, "home_glucose": high_days}))
    assert normal.p_diabetes < unknown.p_diabetes < high.p_diabetes
    assert high.p_diabetes > 0.25 and normal.p_diabetes < 0.02  # la glucosa y la HbA1c no siempre coinciden
    assert high.blood["hba1c"].source == "estimado con la glucosa de casa"
    # Sin glucosa se pide el glucómetro; con ella alta, la HbA1c; y dos días en ayunas altos son un hallazgo.
    assert any(r.test.startswith("Glucosa capilar") for r in unknown.recommendations)
    assert any(r.test == "HbA1c" for r in high.recommendations)
    assert not any(r.test in ("HbA1c",) or r.test.startswith("Glucosa capilar") for r in normal.recommendations)
    assert any("Glucosa en ayunas" in alert for alert in high.alerts)
    assert "glucosa" in unknown.finding_by_test and "HbA1c" in high.finding_by_test
    assert "con la glucosa de casa" in describe(high)


# --- Ritmo ---


def regular(n=40, rate=70.0, wobble=0.02, seed=0):
    rng = np.random.default_rng(seed)
    return 60.0 / rate * (1.0 + wobble * rng.standard_normal(n))


def fibrillating(n=40, rate=95.0, seed=0):
    rng = np.random.default_rng(seed)
    return np.clip(60.0 / rate * np.exp(0.25 * rng.standard_normal(n)), 0.3, 1.6)


def test_interval_features_separate_regular_from_irregular():
    calm, chaotic = rhythm.interval_features(regular()), rhythm.interval_features(fibrillating())
    for name in ("cv", "rmssd_rel", "pnn_rel", "sd1_rel", "lorenz", "entropy"):
        assert chaotic[name] > calm[name], name
    assert calm["mean"] == pytest.approx(60.0 / 70.0, rel=0.02)
    short = rhythm.interval_features([0.8, 0.82, 0.79])
    assert short["n"] == 3 and np.isnan(short["cv"])


def test_beats_are_found_in_a_synthetic_trace():
    fs, seconds = 300.0, 30
    rng = np.random.default_rng(1)
    beats = np.cumsum(regular(34, rate=66.0, seed=1))
    beats = beats[beats < seconds - 1]
    t = np.arange(int(fs * seconds)) / fs
    signal = sum(np.exp(-0.5 * ((t - b) / 0.012) ** 2) for b in beats) * 800 + 30 * rng.standard_normal(t.size) + 100 * np.sin(2 * np.pi * 0.3 * t)
    found = rhythm.detect_beats(signal, fs)
    assert abs(found.size - beats.size) <= 1
    rr = rhythm.intervals_from_beats(found)
    assert np.mean(rr) == pytest.approx(60.0 / 66.0, rel=0.03)
    assert rhythm.detect_beats(np.zeros(3000), fs).size == 0


def test_camera_degradation_drops_and_blurs_beats():
    rng = np.random.default_rng(2)
    beats = np.cumsum(regular(200))
    worse = rhythm.degrade(beats, rng, jitter=0.02, missed=0.1)
    assert 160 <= worse.size < 200 and np.all(np.diff(worse) > 0)
    assert np.std(np.diff(worse)) > np.std(np.diff(beats))


@pytest.mark.skipif(not rhythm.available(), reason="falta el detector (scripts/fit_rhythm.py)")
def test_detector_flags_irregular_rhythm_and_feeds_the_patient_record():
    calm, chaotic = rhythm.classify_intervals(regular()), rhythm.classify_intervals(fibrillating())
    assert chaotic.probability > 0.5 > calm.probability
    assert chaotic.irregular and not calm.irregular
    assert chaotic.likelihood_ratio > 5 and calm.likelihood_ratio < 0.5
    assert calm.heart_rate == pytest.approx(70.0, rel=0.03)
    unusable = rhythm.classify_intervals([0.8, 0.9])
    assert not unusable.usable and unusable.likelihood_ratio == 1.0
    # La ficha usa la razón de verosimilitud del detector, no un sí o no con valores fijos.
    check = rhythm.check_from_intervals(D0, fibrillating())
    assert check.likelihood_ratio == pytest.approx(chaotic.likelihood_ratio)
    assert af_probability([check], 76, female=False) > af_probability([], 76, female=False)
    assert af_probability([rhythm.check_from_intervals(D0, regular())], 76) < af_probability([], 76)


def test_plain_rhythm_checks_use_measured_sensitivity_and_specificity():
    prior = af_probability([], 76, female=False)
    odds = prior / (1 - prior) * (0.875 / (1 - 0.938))
    assert af_probability([RhythmCheck(D0, True)], 76, female=False) == pytest.approx(odds / (1 + odds))
    assert af_probability([RhythmCheck(D0, True, likelihood_ratio=1.0)], 76, female=False) == pytest.approx(prior)


# --- Muestra española ---


@pytest.mark.skipif(not PREDIMED_PATH.exists(), reason="falta la muestra PREDIMED (scripts/download_open_data.py)")
def test_predimed_sample_is_read_from_the_r_file():
    d = load_predimed()
    assert len(d) == 6324 and int(d.event.sum()) == 252
    assert set(SHARED) <= set(d.columns) and not d[SHARED].isna().any().any()
    assert d.age.between(45, 90).all() and d.years.between(0, 7.01).all()
    assert set(np.unique(d.female)) == {0.0, 1.0} and 0.5 < d.female.mean() < 0.65
    assert (d.smoker_ever >= d.smoker_now).all()
    followup = as_followup(d)
    assert followup.dead.sum() == 252 and followup.months.max() == pytest.approx(84.0, abs=0.2)
