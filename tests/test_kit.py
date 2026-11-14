"""Kit por paciente y entrada de las medidas del reloj o de la cámara."""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from latenthealth import ejection, pulse, rhythm
from latenthealth.assessment import HOME_BP_HOW, HOME_BP_TEST, HOME_GLUCOSE_TEST, URINE_TEST, ClinicalRecord, Recommendation
from latenthealth.home import af_probability
from latenthealth.kit import LENT, NO_DEVICE, OWN, PHARMACY, SENT, Devices, add_checks, checks_from_ecg, checks_from_pulse, describe_kit, kit_for

DAY = date(2026, 11, 16)


def names(items) -> list[str]:
    return [item.name for item in items]


def by_name(items, name):
    return next(item for item in items if item.name == name)


def ficha(*tests) -> SimpleNamespace:
    """Una ficha que recomienda esas pruebas (el kit solo mira las recomendaciones)."""
    reasons = {URINE_TEST: "Sin medir.", HOME_GLUCOSE_TEST: "P(diabetes sin diagnosticar) estimada: 7%.", HOME_BP_TEST: f"Tensión en consulta de 150 mmHg. {HOME_BP_HOW}"}
    return SimpleNamespace(recommendations=[Recommendation(t, reasons[t]) for t in tests])


def test_the_kit_carries_what_the_record_says_is_missing():
    record = ClinicalRecord(age=62, female=False, hypertension=True, bp_meds=True, has_smartphone=True)
    assert names(kit_for(record, assessment=ficha())) == ["Cinco preguntas", "Pulso"]

    items = kit_for(record, assessment=ficha(URINE_TEST, HOME_GLUCOSE_TEST, HOME_BP_TEST))
    assert names(items) == ["Orina", "Cinco preguntas", "Glucosa", "Tensión", "Pulso"]
    assert by_name(items, "Orina").supply == SENT
    glucose, pressure = by_name(items, "Glucosa"), by_name(items, "Tensión")
    # Basta una medida: se hace en la farmacia, no se presta el aparato.
    assert glucose.supply == PHARMACY and "farmacia" in glucose.how and "7%" in glucose.why
    # Nadie compra nada: el manguito se presta una semana, tenga o no hipertensión diagnosticada.
    assert pressure.supply == LENT and "una semana" in pressure.how
    assert pressure.why == "Tensión en consulta de 150 mmHg. Hay que ver si está controlada con el tratamiento."

    undiagnosed = ClinicalRecord(age=59, female=True, has_smartphone=True)
    assert by_name(kit_for(undiagnosed, assessment=ficha(HOME_BP_TEST)), "Tensión").why.endswith("Hay que ver si es hipertensión.")

    owns = kit_for(record, Devices(cuff=True, glucometer=True), assessment=ficha(HOME_GLUCOSE_TEST, HOME_BP_TEST))
    assert by_name(owns, "Glucosa").supply == OWN and by_name(owns, "Tensión").supply == OWN


def test_the_cuff_follows_the_office_pressure_not_the_diagnosis():
    """Con la ficha de verdad: el manguito va a quien tiene la tensión de consulta alta, esté o no diagnosticado."""
    base = dict(age=62, female=False, bmi=27.0, has_smartphone=True, measured={"hba1c": 5.4, "egfr": 85, "total_cholesterol": 190, "hdl": 50})
    treated_high = ClinicalRecord(sbp=150, dbp=85, hypertension=True, bp_meds=True, **base)
    treated_fine = ClinicalRecord(sbp=128, dbp=78, hypertension=True, bp_meds=True, **base)
    unknown_high = ClinicalRecord(sbp=138, dbp=86, **base)
    healthy = ClinicalRecord(sbp=118, dbp=74, **base)
    assert "Tensión" in names(kit_for(treated_high, as_of=DAY))
    assert "Tensión" not in names(kit_for(treated_fine, as_of=DAY))
    assert "Tensión" in names(kit_for(unknown_high, as_of=DAY))
    assert "Tensión" not in names(kit_for(healthy, as_of=DAY))
    # Con una HbA1c reciente el glucómetro no aporta, y sin orina medida sí van las tiras.
    assert "Glucosa" not in names(kit_for(healthy, as_of=DAY))
    assert "Orina" in names(kit_for(healthy, as_of=DAY))


def test_pulse_comes_from_the_watch_if_connected_and_from_the_camera_otherwise():
    record = ClinicalRecord(age=62, female=False, hypertension=True, diabetes=True, has_smartphone=True)
    camera = by_name(kit_for(record, assessment=ficha()), "Pulso")
    assert "cámara" in camera.how and camera.supply == NO_DEVICE
    watch = by_name(kit_for(record, Devices(watch_pulse=True), assessment=ficha()), "Pulso")
    assert "reloj" in watch.how and watch.supply == OWN

    no_phone = kit_for(ClinicalRecord(age=81, female=False, hypertension=True, diabetes=True, has_smartphone=False), assessment=ficha(URINE_TEST))
    assert names(no_phone) == ["Orina", "Cinco preguntas"]
    assert "tubo" in by_name(no_phone, "Orina").how

    known = ClinicalRecord(age=77, female=False, hypertension=True, diabetes=True, atrial_fibrillation=True, has_smartphone=True)
    assert "Pulso" not in names(kit_for(known, assessment=ficha()))


def test_ecg_is_only_asked_with_a_watch_or_after_an_infarction():
    plain = ClinicalRecord(age=62, female=False, hypertension=True, diabetes=True, has_smartphone=True)
    assert "ECG de 30 segundos" not in names(kit_for(plain, assessment=ficha()))
    watch = by_name(kit_for(plain, Devices(watch_ecg=True), assessment=ficha()), "ECG de 30 segundos")
    assert watch.supply == OWN and "sin validar" in watch.why

    infarction = ClinicalRecord(age=64, female=False, hypertension=True, diabetes=True, coronary=True, has_smartphone=True)
    lent = by_name(kit_for(infarction, assessment=ficha()), "ECG de 30 segundos")
    assert lent.supply == LENT and "22 %" in lent.why and "1,8 %" in lent.why
    assert by_name(kit_for(infarction, Devices(watch_ecg=True), assessment=ficha()), "ECG de 30 segundos").supply == OWN

    failing = ClinicalRecord(age=64, female=False, hypertension=True, diabetes=True, coronary=True, heart_failure=True, has_smartphone=True)
    assert "ECG de 30 segundos" not in names(kit_for(failing, Devices(watch_ecg=True), assessment=ficha()))
    assert "Cinco preguntas: " in describe_kit(kit_for(failing, assessment=ficha()))


@pytest.mark.skipif(not rhythm.available(), reason="falta el detector de ritmo")
def test_a_pulse_measure_from_watch_or_camera_feeds_the_record():
    rng = np.random.default_rng(0)
    regular = 0.85 + 0.02 * rng.standard_normal(70)
    irregular = rng.uniform(0.45, 1.15, 80)
    record = ClinicalRecord(age=77, female=False)

    calm = checks_from_pulse(DAY, regular, "reloj")
    wild = checks_from_pulse(DAY, irregular, "cámara")
    assert calm[0].source == "reloj" and wild[0].source == "cámara"
    assert calm[0].likelihood_ratio < 1.0 < wild[0].likelihood_ratio
    assert af_probability([wild[0]], 77, female=False) > af_probability([calm[0]], 77, female=False)

    add_checks(record, calm)
    add_checks(record, wild)
    assert len(record.rhythm_checks) == 2
    if pulse.available():  # el pulso solo apenas mueve la sospecha de corazón débil
        assert [c.source for c in record.heart_checks] == ["pulso", "pulso"]
        assert all(0.5 < c.likelihood_ratio < 3.0 for c in record.heart_checks)

    with pytest.raises(ValueError):
        checks_from_pulse(DAY, regular, "manguito")


@pytest.mark.skipif(not rhythm.available(), reason="falta el detector de ritmo")
def test_a_single_lead_ecg_gives_rhythm_and_heart_checks():
    fs, seconds = 500.0, 30.0
    t = np.arange(int(seconds * fs)) / fs
    ecg = 5.0 * np.random.default_rng(0).standard_normal(t.size)
    for beat in np.arange(1.0, seconds - 1.0, 0.8):
        ecg += 1000.0 * np.exp(-0.5 * ((t - beat) / 0.012) ** 2) + 200.0 * np.exp(-0.5 * ((t - beat - 0.28) / 0.04) ** 2)

    rhythm_check, heart_check = checks_from_ecg(DAY, ecg, fs)
    assert rhythm_check.source == "ecg" and not rhythm_check.irregular
    assert rhythm_check.likelihood_ratio < 1.0
    if ejection.available():
        assert heart_check.source == "ecg"
        assert 0.1 <= heart_check.likelihood_ratio <= 10.0
    else:
        assert heart_check is None
