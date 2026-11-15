from datetime import date

import pytest

from latenthealth.albuminuria import FIRST_MORNING, RANDOM, UrineSample
from latenthealth.assessment import PANEL_DIR, ClinicalRecord, assess, describe, urine_test
from latenthealth.i18n import use_lang

pytestmark = pytest.mark.skipif(
    not PANEL_DIR.exists() or not any(PANEL_DIR.glob("*.joblib")),
    reason="panel models missing (scripts/fit_panel.py)",
)


def test_patient_without_urine_is_asked_for_uacr():
    a = assess(ClinicalRecord(age=62, female=False, hypertension=True, bp_meds=True, sbp=145, bmi=29))
    assert a.albuminuria.status == "sin_medir"
    assert any(r.test.startswith("UACR") for r in a.recommendations)
    assert all(not est.measured for est in a.blood.values())
    assert 0 <= a.p_ckd <= 1


def test_measured_values_replace_estimates():
    rec = ClinicalRecord(age=70, female=False, diabetes=True, measured={"egfr": 50.0, "hba1c": 7.2})
    a = assess(rec)
    assert a.blood["egfr"].measured and a.blood["egfr"].median == 50.0
    assert a.kdigo_g["G3a"] == pytest.approx(1.0)
    assert a.p_egfr_below_60 == pytest.approx(1.0)
    assert a.diabetes == "diagnosed"
    assert not any(r.test.startswith("Creatinine") for r in a.recommendations)
    # A single eGFR < 60 is not diagnostic: confirmation at three months is requested.
    assert any(r.test == "Repeat creatinine in three months" for r in a.recommendations)


def test_confirmed_albuminuria_with_low_egfr_is_high_kdigo_risk():
    rec = ClinicalRecord(
        age=70,
        female=False,
        diabetes=True,
        urine_samples=[
            UrineSample(date(2026, 3, 1), 150.0, FIRST_MORNING, creatinine_mg_dl=120),
            UrineSample(date(2026, 7, 1), 140.0, FIRST_MORNING, creatinine_mg_dl=110),
        ],
        measured={"egfr": 50.0},
    )
    a = assess(rec)
    assert a.albuminuria.status == "confirmada"
    assert a.kdigo_risk["alto"] + a.kdigo_risk["muy alto"] > 0.95
    assert any(r.test == "Potassium" for r in a.recommendations)


def test_describe_is_readable_text():
    rec = ClinicalRecord(age=50, female=True, urine_samples=[UrineSample(date(2026, 5, 1), 20.0, RANDOM)])
    text = describe(assess(rec))
    assert "ALBUMINURIA" in text and "RECOMMENDED TESTS" in text


def test_spanish_output_is_the_original_text():
    rec = ClinicalRecord(age=70, female=False, diabetes=True, measured={"egfr": 50.0, "hba1c": 7.2})
    with use_lang("es"):
        a = assess(rec)
        text = describe(a)
        assert urine_test() == "UACR (primera orina de la mañana)"
    assert a.diabetes == "diagnosticada"
    egfr = a.blood["egfr"]
    assert (egfr.name, egfr.unit, egfr.source) == ("FG", "ml/min/1,73 m²", "medido")
    reasons = {r.test: r.reason for r in a.recommendations}
    assert reasons["Repetir creatinina a los tres meses"] == (
        "Un FG por debajo de 60 aislado no basta para el diagnóstico: hay que confirmarlo pasados tres meses."
    )
    assert "  FG: 50 ml/min/1,73 m² (medido)" in text and "  HbA1c: 7,2 % (medido)" in text
    assert "DIAGNÓSTICOS" in text and "PRUEBAS RECOMENDADAS" in text and "RIESGO CARDIOVASCULAR" in text
    # The default language is still English.
    assert assess(rec).diabetes == "diagnosed"
