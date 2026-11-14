"""Modelo de riesgo con desenlaces: filas persona-año, riesgo acumulado y métricas."""

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from latenthealth.albuminuria import PHONE_STRIP, VISION_STRIP
from latenthealth.assessment import ClinicalRecord, assess, describe
from latenthealth.outcomes import BLOCKS, add_strip, complete_home, mask_blocks
from latenthealth.outcomes import risk as outcome_risk
from latenthealth.outcomes.data import _difficulty, _taking
from latenthealth.outcomes.evaluation import auc, brier, c_index, calibration_table, capture, difference_interval
from latenthealth.outcomes.model import HazardModel, person_periods

CV = (1, 5)


def people(months, dead, cause):
    return pd.DataFrame({"months": months, "dead": dead, "cause": cause})


def test_person_periods_count_years_and_label_the_event_year():
    # Vivo a los 3,5 años; muere del corazón a los 2,2; muere de otra cosa a los 0,4; vivo a los 12.
    d = people([42, 26, 5, 144], [0, 1, 1, 0], [np.nan, 1, 2, np.nan])
    person, year, label = person_periods(d, CV, horizon=10)
    assert np.bincount(person).tolist() == [3, 3, 1, 10]  # el año incompleto del vivo no cuenta
    assert year[person == 1].tolist() == [0, 1, 2] and label[person == 1].tolist() == [0, 0, 1]
    assert label[person == 2].tolist() == [2]
    assert label[person == 0].sum() == 0 and label[person == 3].sum() == 0


def test_deaths_after_the_horizon_are_not_events():
    d = people([150], [1], [1])
    _, year, label = person_periods(d, CV, horizon=10)
    assert year.tolist() == list(range(10)) and label.sum() == 0


def simulated(n, rng):
    """Riesgo anual constante que depende de dos predictores; un tercero es ruido."""
    x = rng.standard_normal((n, 3))
    x[rng.random((n, 3)) < 0.1] = np.nan  # faltan datos
    lp = np.nan_to_num(x[:, 0]) * 0.9 + np.nan_to_num(x[:, 1]) * 0.5
    h_cv = 0.012 * np.exp(lp)
    h_other = np.full(n, 0.02)
    t_cv = rng.exponential(1.0 / h_cv)
    t_other = rng.exponential(1.0 / h_other)
    t_end = rng.uniform(4.0, 16.0, n)  # fin del seguimiento
    t = np.minimum.reduce([t_cv, t_other, t_end])
    dead = (t < t_end).astype(float)
    cause = np.where(dead == 0, np.nan, np.where(t_cv < t_other, 1.0, 2.0))
    d = pd.DataFrame({"a": x[:, 0], "b": x[:, 1], "noise": x[:, 2], "months": t * 12.0, "dead": dead, "cause": cause})
    true_risk = h_cv / (h_cv + h_other) * (1.0 - np.exp(-(h_cv + h_other) * 10.0))
    return d, true_risk


@pytest.mark.parametrize("kind", ["boosting", "linear"])
def test_hazard_model_recovers_the_ten_year_risk(kind):
    rng = np.random.default_rng(0)
    train, _ = simulated(12000, rng)
    test, true_risk = simulated(4000, rng)
    model = HazardModel(["a", "b", "noise"], kind=kind, min_samples_leaf=100).fit(train, CV) if kind == "boosting" else HazardModel(["a", "b", "noise"], kind=kind).fit(train, CV)
    risk = model.risk(test)
    assert np.all((risk >= 0) & (risk <= 1))
    assert np.corrcoef(risk, true_risk)[0, 1] > 0.85
    assert risk.mean() == pytest.approx(true_risk.mean(), rel=0.2)  # calibrado con riesgos competitivos y censura
    assert np.all(np.diff([model.risk(test, years=y).mean() for y in (2, 5, 10)]) > 0)


def test_auc_matches_sklearn_and_helpers_behave():
    rng = np.random.default_rng(1)
    y = rng.random(500) < 0.2
    s = rng.standard_normal(500) + y
    assert auc(y, s) == pytest.approx(roc_auc_score(y, s))
    assert np.isnan(auc(np.zeros(5, bool), np.arange(5)))
    assert brier([1, 0], [1.0, 0.0]) == 0.0
    table = calibration_table(y, 1 / (1 + np.exp(-s)), bins=5)
    assert len(table) == 5 and sum(n for n, _, _ in table) == 500
    rate, share = capture(y, s, 0.2)
    assert rate > y.mean() and 0 < share <= 1
    mean, lo, hi = difference_interval(np.array([0.8, 0.82, 0.81]), np.array([0.7, 0.71, 0.72]))
    assert lo <= mean <= hi and lo > 0


def test_c_index_counts_only_comparable_pairs():
    # Quien muere antes debe tener más puntuación que quien sigue más tiempo en seguimiento.
    months = np.array([10.0, 20.0, 30.0, 40.0])
    event = np.array([True, False, True, False])
    assert c_index(months, event, np.array([4.0, 3.0, 2.0, 1.0])) == 1.0
    assert c_index(months, event, np.array([1.0, 2.0, 3.0, 4.0])) == 0.0
    assert np.isnan(c_index(months, np.zeros(4, bool), months))


def test_questionnaire_harmonisation_rules():
    age = np.array([45.0, 70.0, 70.0])
    assert _difficulty(np.array([np.nan, np.nan, 3.0]), age).tolist()[0] == 0.0  # joven sin limitaciones: no se pregunta
    assert np.isnan(_difficulty(np.array([np.nan, np.nan, 3.0]), age)[1])
    assert _difficulty(np.array([np.nan, np.nan, 3.0]), age)[2] == 2.0
    assert _taking(np.array([1.0, 0.0, np.nan]), np.array([1.0, np.nan, np.nan])).tolist()[:2] == [1.0, 0.0]


def test_empty_answers_mean_not_provided_rather_than_frail():
    rng = np.random.default_rng(0)
    n = 400
    d = pd.DataFrame({c: rng.random(n) for cols in BLOCKS.values() for c in cols})
    d["age"] = rng.uniform(25, 80, n)
    d.loc[0, "waist"] = np.nan  # no se le pudo medir: fuera del entrenamiento
    d.loc[1, "dyspnea"] = np.nan
    d.loc[1, "age"] = 30.0  # a los menores de 40 no se les pregunta la disnea: cuenta como completo
    d.loc[2, "dyspnea"] = np.nan
    d.loc[2, "age"] = 60.0
    ok = complete_home(d)
    assert ok.tolist()[:3] == [False, True, False] and ok[3:].all()
    augmented = mask_blocks(d[ok], rng, copies=2, p=0.5)
    assert len(augmented) == 3 * ok.sum()
    copies = augmented.iloc[ok.sum() :]
    for cols in BLOCKS.values():  # cada bloque se borra entero, en torno a la mitad de las veces
        empty = copies[cols].isna()
        assert 0.35 < empty[cols[0]].mean() < 0.65
        assert (empty.nunique(axis=1) == 1).mean() > 0.99


def test_strip_reading_is_added_from_the_lab_urine():
    d = pd.DataFrame({"log_uacr": np.log([5.0, 400.0, np.nan]), "log_urine_creatinine": np.log([100.0, 100.0, 100.0])})
    out = add_strip(d, PHONE_STRIP)
    assert out.strip_albumin[1] > out.strip_albumin[0]
    assert np.isnan(out.strip_albumin[2])
    assert set(np.exp(out.strip_creatinine.dropna()).round()) <= set(PHONE_STRIP.creatinine_levels)


def test_vision_strip_has_finer_levels_in_the_same_chemical_range():
    assert len(VISION_STRIP.albumin_levels) > len(PHONE_STRIP.albumin_levels)
    assert VISION_STRIP.albumin_levels[0] == PHONE_STRIP.albumin_levels[0]
    assert VISION_STRIP.albumin_levels[-1] == pytest.approx(PHONE_STRIP.albumin_levels[-1])


@pytest.mark.skipif(not outcome_risk.available(), reason="faltan los modelos de riesgo (scripts/fit_outcomes.py)")
def test_home_risk_uses_what_the_patient_reports():
    base = ClinicalRecord(age=68, female=False, sbp=138, bmi=28)
    well = assess(ClinicalRecord(age=68, female=False, sbp=138, bmi=28, self_rated_health=1, dyspnea_on_stairs=False, walk_difficulty=0, hospitalized_last_year=False))
    unwell = assess(
        ClinicalRecord(
            age=68, female=False, sbp=138, bmi=28, self_rated_health=5, dyspnea_on_stairs=True, walk_difficulty=2,
            stairs_difficulty=2, hospitalized_last_year=True, heart_failure=True, diabetes=True,
        )
    )  # fmt: skip
    unknown = assess(base)
    assert well.home_risk.ratio < unknown.home_risk.ratio < unwell.home_risk.ratio
    assert unwell.home_risk.ratio > 1.5 and well.home_risk.ratio < 1.0
    assert "salud percibida" in unknown.home_risk.missing and "salud percibida" not in well.home_risk.missing
    assert "RIESGO CON LO MEDIDO EN CASA" in describe(unwell)
    # Un dato sin contestar no debe contar como señal de fragilidad: quien no ha aportado nada
    # queda cerca del riesgo de su edad y sexo.
    assert 0.6 < unknown.home_risk.ratio < 1.6
    # Las preguntas de síntomas solo se piden a mayores con sospecha de insuficiencia cardíaca.
    older = ClinicalRecord(age=78, female=False, hypertension=True, bp_meds=True, coronary=True, sbp=150, bmi=31)
    asked = assess(older)
    assert asked.p_nt_probnp_high >= 0.3 and any(r.test == "Preguntas sobre síntomas" for r in asked.recommendations)
    assert not any(r.test == "Preguntas sobre síntomas" for r in unknown.recommendations + well.recommendations)
