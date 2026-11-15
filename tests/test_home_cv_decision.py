"""Home measurements, cardiovascular risk and utility-based thresholds."""

from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from latenthealth.cvrisk import (
    HIGH,
    LOW,
    VERY_HIGH,
    assess_cv,
    category_matrix,
    score2,
    score_category,
)
from latenthealth.decision import Thresholds, Utilities, decision_curve, net_benefit, avoided_tests_per_100
from latenthealth.home import BPReading, HomeLab, RhythmCheck, af_probability, summarize_home_bp, update_pmf
from latenthealth.assessment import ClinicalRecord, _alerts
from latenthealth.cvrisk import CATEGORY_LABELS
from latenthealth.cvrisk import describe as describe_cv
from latenthealth.decision import threshold_from_tests_per_case
from latenthealth.i18n import use_lang
from latenthealth.kidney_trend import STATUS_TEXT, EgfrMeasurement, fit_trend
from latenthealth.kidney_trend import describe as describe_trend
from latenthealth.worklist import describe as describe_worklist
from latenthealth.worklist import row_for

D0 = date(2026, 5, 4)

# --- Blood pressure, finger-prick and rhythm ---


def week(sbp, dbp, days=7, first_day_extra=8):
    out = []
    for d in range(days):
        extra = first_day_extra if d == 0 else 0
        for evening in (False, False, True, True):
            out.append(BPReading(D0 + timedelta(days=d), sbp + extra + (2 if evening else -2), dbp + extra, evening))
    return out


def test_home_bp_discards_the_first_day_and_flags_high_values():
    high = summarize_home_bp(week(148, 88))
    assert high.valid and high.days == 6 and high.n == 24
    assert high.sbp == pytest.approx(148.0)
    assert high.p_high > 0.9 and "High blood pressure at home" in high.message
    assert high.office_sbp == pytest.approx(153.0)
    normal = summarize_home_bp(week(122, 76))
    assert normal.p_high < 0.1


def test_home_bp_with_few_readings_is_not_valid():
    few = summarize_home_bp(week(150, 90, days=2))
    assert not few.valid and "Not enough readings" in few.message
    assert summarize_home_bp([]) is None


def test_capillary_measurement_updates_but_does_not_replace():
    bounds = np.array([20.0, 45.0, 60.0, 75.0, 90.0, 120.0])
    prior = np.array([0.05, 0.15, 0.30, 0.30, 0.20])
    post = update_pmf(bounds, prior, 50.0, log_sd=0.13)
    assert post.sum() == pytest.approx(1.0)
    assert post[1] > prior[1] and post[4] < prior[4]
    assert post[2] > 0.05  # the reading has error: the neighbouring bin is still possible
    precise = update_pmf(bounds, prior, 50.0, log_sd=0.02)
    assert precise[1] > post[1]
    assert HomeLab(6.8).error("hba1c") == {"sd": 0.35}
    with pytest.raises(ValueError):
        HomeLab(4.4).error("potassium")


def test_rhythm_checks_move_the_probability_of_atrial_fibrillation():
    none = af_probability([], 74)
    one = af_probability([RhythmCheck(D0, True)], 74)
    two = af_probability([RhythmCheck(D0, True), RhythmCheck(D0 + timedelta(days=1), True)], 74)
    clean = af_probability([RhythmCheck(D0, False)], 74)
    assert clean < none < one < two
    assert two > 0.6
    assert af_probability([], 50) < af_probability([], 85)
    # OFRECE prevalence: ages 70-79, higher in men; 10% of cases undiagnosed.
    assert af_probability([], 74, female=False) > af_probability([], 74, female=True)
    assert af_probability([], 74, female=False) == pytest.approx(0.1 * 0.119 / (1 - 0.9 * 0.119))


# --- SCORE2 ---


def test_score2_matches_a_hand_computed_example():
    # Man aged 50, smoker, 140 mmHg, cholesterol 5.5 and HDL 1.3 mmol/l, low-risk region.
    lp = 0.3742 * -2 + 0.6012 + 0.2777 + 0.1458 * -0.5 + 0.0755 * 2 + 0.0255 * 2 - 0.0281 * -2 * -0.5
    raw = 1 - 0.9605 ** np.exp(lp)
    expected = 1 - np.exp(-np.exp(-0.5699 + 0.7476 * np.log(-np.log(1 - raw))))
    assert score2(50, False, True, 140, 5.5, 1.3, units="mmol/l") == pytest.approx(expected)
    assert 0.05 < expected < 0.07
    assert score2(50, False, True, 140, 5.5 * 38.67, 1.3 * 38.67) == pytest.approx(expected)


def test_score2_op_uses_its_own_coefficients_from_70():
    # Woman aged 75, non-smoker, 150 mmHg, cholesterol 6 and HDL 1.4: only the age term remains.
    raw = 1 - 0.8082 ** np.exp(0.0789 * 2 - 0.229)
    expected = 1 - np.exp(-np.exp(-0.52 + 1.01 * np.log(-np.log(1 - raw))))
    assert score2(75, True, False, 150, 6.0, 1.4, units="mmol/l") == pytest.approx(expected)


def test_score2_moves_in_the_expected_direction():
    base = score2(60, False, False, 130, 200, 50)
    assert score2(60, False, True, 130, 200, 50) > base
    assert score2(60, False, False, 160, 200, 50) > base
    assert score2(60, False, False, 130, 200, 70) < base
    assert score2(60, True, False, 130, 200, 50) < base
    assert score2(60, False, False, 130, 200, 50, region="high") > base
    assert score2(60, False, False, [120, 140, 160], 200, 50).shape == (3,)


def test_score_category_uses_age_specific_thresholds():
    assert score_category(45, 0.03) == HIGH
    assert score_category(60, 0.03) == LOW
    assert score_category(60, 0.12) == VERY_HIGH
    assert score_category(75, 0.12) == HIGH


# --- ESC categories and what each test would change ---


def test_kidney_disease_and_diabetes_set_a_minimum_category():
    healthy = category_matrix(False, False)
    assert healthy[0, 0] == LOW and healthy[0, 2] == HIGH  # normal eGFR with > 300 mg/g
    assert healthy[2, 1] == HIGH and healthy[3, 1] == VERY_HIGH and healthy[4, 0] == VERY_HIGH
    diabetic = category_matrix(True, False)
    assert diabetic[0, 0] == HIGH and diabetic[2, 1] == VERY_HIGH and diabetic[0, 2] == VERY_HIGH
    assert category_matrix(True, False, diabetes_low_risk=True)[0, 0] == LOW
    assert np.all(category_matrix(False, True) == VERY_HIGH)


def joint_of(p_g, p_a):
    return np.outer(p_g, p_a)


def test_unmeasured_urine_can_hide_a_higher_category():
    # eGFR 50 measured (G3a), urine unmeasured with 30% probability of A2 and 5% of A3.
    joint = joint_of([0, 0, 1, 0, 0, 0], [0.65, 0.30, 0.05])
    risk = assess_cv(62, joint, [0.03], [1.0], False, False, recorded_g=2, recorded_a=None, score_recorded=0.03)
    assert risk.recorded == LOW
    assert risk.p_up == pytest.approx(0.35)
    assert risk.p_up_by_test == {"orina": pytest.approx(0.35)}
    assert risk.best_test == "orina"
    assert risk.probs == pytest.approx([0.65, 0.30, 0.05])


def test_nothing_to_gain_when_everything_is_measured_or_already_very_high():
    joint = joint_of([0, 1, 0, 0, 0, 0], [1, 0, 0])
    done = assess_cv(62, joint, [0.03], [1.0], False, False, recorded_g=1, recorded_a=0, score_recorded=0.03)
    assert done.p_up == 0 and done.best_test is None
    uncertain = joint_of([0.2, 0.4, 0.2, 0.1, 0.1, 0], [0.6, 0.3, 0.1])
    ascvd = assess_cv(70, uncertain, [0.1], [1.0], True, True, None, None, 0.1)
    assert ascvd.recorded == VERY_HIGH and ascvd.p_up == 0


def test_missing_lipids_count_as_a_pending_test():
    joint = joint_of([1, 0, 0, 0, 0, 0], [1, 0, 0])
    risk = assess_cv(58, joint, [0.02, 0.06, 0.12], [0.5, 0.3, 0.2], False, False, 0, 0, 0.02, score_pending=True, approximate=True)
    assert risk.recorded == LOW
    assert risk.p_up == pytest.approx(0.5)
    assert risk.best_test == "lípidos"
    assert risk.score_low <= risk.score <= risk.score_high
    known = assess_cv(58, joint, [0.02], [1.0], False, False, 0, 0, 0.02)
    assert known.p_up == 0 and "lípidos" not in known.p_up_by_test


# --- Thresholds ---


def test_thresholds_come_from_tests_per_case():
    t = Utilities().thresholds()
    assert t == Thresholds()
    careful = Utilities(missed_albuminuria=50, tests_creatinine=40).thresholds()
    assert careful.albuminuria_discard == pytest.approx(0.02)
    assert careful.creatinine == pytest.approx(0.025)
    with pytest.raises(ValueError):
        Utilities(tests_hba1c=0.5).thresholds()


def test_net_benefit_rewards_a_model_that_separates():
    rng = np.random.default_rng(0)
    y = rng.random(4000) < 0.1
    good = np.clip(np.where(y, 0.5, 0.05) + 0.05 * rng.standard_normal(4000), 0.001, 0.999)
    curve = decision_curve(y, good, [0.05, 0.1, 0.2])
    assert np.all(curve["modelo"] >= curve["todos"] - 1e-9)
    assert np.all(curve["modelo"] > 0)
    assert net_benefit(y, np.full(4000, 0.5), 0.9) == 0.0
    assert avoided_tests_per_100(y, good, 0.1) > 0


# --- Spanish output (the original texts) ---


def test_alerts_in_spanish_keep_the_original_wording():
    record = ClinicalRecord(age=60.0, female=False, measured={"hba1c": 6.8})
    with use_lang("es"):
        alerts = _alerts(record, SimpleNamespace(status="sin_medir"), None, None, {}, 0.73, None)
    assert alerts == [
        "HbA1c de 6,8 % sin diabetes registrada (confirmar con una segunda determinación).",
        "Pulso irregular repetido en casa (P(fibrilación auricular) = 73%).",
    ]
    english = _alerts(record, SimpleNamespace(status="sin_medir"), None, None, {}, 0.73, None)
    assert english[1] == "Repeated irregular pulse at home (P(atrial fibrillation) = 73%)."


def test_kidney_trend_and_cv_risk_in_spanish():
    values = [88, 76, 65, 53, 42]
    steep = fit_trend([EgfrMeasurement(D0 + timedelta(days=365 * i), v) for i, v in enumerate(values)], 66, False, diabetes=True)
    joint = joint_of([0, 0, 1, 0, 0, 0], [0.65, 0.30, 0.05])
    risk = assess_cv(62, joint, [0.03], [1.0], False, False, recorded_g=2, recorded_a=None, score_recorded=0.03)
    with use_lang("es"):
        assert STATUS_TEXT[steep.status] == "descenso rápido"
        text = describe_trend(steep)
        labels = list(CATEGORY_LABELS)
        cv = describe_cv(risk)
        with pytest.raises(ValueError, match="Hace falta al menos una prueba por caso."):
            threshold_from_tests_per_case(0.5)
    assert text.splitlines()[1].startswith("Tendencia: descenso rápido; pendiente -")
    assert "ml/min/1,73 m² (80 %: " in text and " años" in text.splitlines()[0]
    assert labels == ["bajo o moderado", "alto", "muy alto"] and list(CATEGORY_LABELS)[2] == "very high"
    assert cv.splitlines()[0] == "SCORE2 a 10 años: 3%"
    assert cv.splitlines()[1] == "Categoría con lo que consta hoy: bajo o moderado"
    assert cv.splitlines()[3] == "Probabilidad de subir de categoría al completar las pruebas: 35% (orina 35%)"


def test_worklist_row_in_spanish_and_english():
    fake = SimpleNamespace(
        cv=SimpleNamespace(recorded=0, category=1, p_up=0.2),
        finding_by_test={"orina": 0.25, "creatinina": 0.05},
        channel="aplicación",
        alerts=[],
        p_new_finding=0.3,
        home_risk=None,
    )
    with use_lang("es"):
        row = row_for("p1", fake)
        text = describe_worklist([row])
    assert row.reasons == ["Hallazgo nuevo por prueba: orina 25%, creatinina 5%."]
    assert (row.recorded, row.probable, row.how) == ("bajo o moderado", "alto", "kit de orina en casa (aplicación)")
    assert text == (
        "MEDIR: probabilidad de un hallazgo nuevo si se completan las pruebas\n"
        "  p1 · riesgo que consta: bajo o moderado · hallazgo nuevo 30% (sube de categoría 20%) · pedir primero: orina "
        "(kit de orina en casa (aplicación))\n"
        "      - Hallazgo nuevo por prueba: orina 25%, creatinina 5%.\n"
        "\n"
        "Sin pendientes: 0 de 1 pacientes."
    )
    english = row_for("p1", fake)
    assert english.reasons == ["New finding by test: urine 25%, creatinine 5%."]
    assert english.how == "home urine kit (app)" and english.group == "medir"
