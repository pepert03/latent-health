"""Per-patient kit and intake of watch or camera measurements."""

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from latenthealth import ejection, pulse, rhythm
from latenthealth.assessment import ClinicalRecord, Recommendation, home_bp_how, home_bp_test, home_glucose_test, urine_test
from latenthealth.home import af_probability
from latenthealth.i18n import t, use_lang
from latenthealth.kit import LENT, NO_DEVICE, OWN, PHARMACY, SENT, Devices, add_checks, checks_from_ecg, checks_from_pulse, describe_kit, kit_for

DAY = date(2026, 11, 16)


def names(items) -> list[str]:
    return [item.name for item in items]


def by_name(items, name):
    return next(item for item in items if item.name == name)


def ficha(*tests) -> SimpleNamespace:
    """A record that recommends those tests (the kit only looks at the recommendations)."""
    reasons = {
        urine_test(): t("Sin medir.", "Not measured."),
        home_glucose_test(): t("P(diabetes sin diagnosticar) estimada: 7%.", "Estimated P(undiagnosed diabetes): 7%."),
        home_bp_test(): t("Tensión en consulta de 150 mmHg.", "Office blood pressure of 150 mmHg.") + f" {home_bp_how()}",
    }
    return SimpleNamespace(recommendations=[Recommendation(test, reasons[test]) for test in tests])


def test_the_kit_carries_what_the_record_says_is_missing():
    record = ClinicalRecord(age=62, female=False, hypertension=True, bp_meds=True, has_smartphone=True)
    assert names(kit_for(record, assessment=ficha())) == ["Five questions", "Pulse"]

    items = kit_for(record, assessment=ficha(urine_test(), home_glucose_test(), home_bp_test()))
    assert names(items) == ["Urine", "Five questions", "Glucose", "Blood pressure", "Pulse"]
    assert by_name(items, "Urine").supply == SENT
    glucose, pressure = by_name(items, "Glucose"), by_name(items, "Blood pressure")
    # One reading is enough: it is done at the pharmacy, no device is lent.
    assert glucose.supply == PHARMACY and "pharmacy" in glucose.how and "7%" in glucose.why
    # Nobody buys anything: the cuff is lent for a week, with or without diagnosed hypertension.
    assert pressure.supply == LENT and "one week" in pressure.how
    assert pressure.why == "Office blood pressure of 150 mmHg. We need to see whether it is controlled on treatment."

    undiagnosed = ClinicalRecord(age=59, female=True, has_smartphone=True)
    assert by_name(kit_for(undiagnosed, assessment=ficha(home_bp_test())), "Blood pressure").why.endswith("We need to see whether it is hypertension.")

    owns = kit_for(record, Devices(cuff=True, glucometer=True), assessment=ficha(home_glucose_test(), home_bp_test()))
    assert by_name(owns, "Glucose").supply == OWN and by_name(owns, "Blood pressure").supply == OWN


def test_the_cuff_follows_the_office_pressure_not_the_diagnosis():
    """With a real record: the cuff goes to whoever has high office blood pressure, diagnosed or not."""
    base = dict(age=62, female=False, bmi=27.0, has_smartphone=True, measured={"hba1c": 5.4, "egfr": 85, "total_cholesterol": 190, "hdl": 50})
    treated_high = ClinicalRecord(sbp=150, dbp=85, hypertension=True, bp_meds=True, **base)
    treated_fine = ClinicalRecord(sbp=128, dbp=78, hypertension=True, bp_meds=True, **base)
    unknown_high = ClinicalRecord(sbp=138, dbp=86, **base)
    healthy = ClinicalRecord(sbp=118, dbp=74, **base)
    assert "Blood pressure" in names(kit_for(treated_high, as_of=DAY))
    assert "Blood pressure" not in names(kit_for(treated_fine, as_of=DAY))
    assert "Blood pressure" in names(kit_for(unknown_high, as_of=DAY))
    assert "Blood pressure" not in names(kit_for(healthy, as_of=DAY))
    # With a recent HbA1c the glucometer adds nothing, and without measured urine the strips do go.
    assert "Glucose" not in names(kit_for(healthy, as_of=DAY))
    assert "Urine" in names(kit_for(healthy, as_of=DAY))


def test_pulse_comes_from_the_watch_if_connected_and_from_the_camera_otherwise():
    record = ClinicalRecord(age=62, female=False, hypertension=True, diabetes=True, has_smartphone=True)
    camera = by_name(kit_for(record, assessment=ficha()), "Pulse")
    assert "camera" in camera.how and camera.supply == NO_DEVICE
    watch = by_name(kit_for(record, Devices(watch_pulse=True), assessment=ficha()), "Pulse")
    assert "watch" in watch.how and watch.supply == OWN

    no_phone = kit_for(ClinicalRecord(age=81, female=False, hypertension=True, diabetes=True, has_smartphone=False), assessment=ficha(urine_test()))
    assert names(no_phone) == ["Urine", "Five questions"]
    assert "tube" in by_name(no_phone, "Urine").how

    known = ClinicalRecord(age=77, female=False, hypertension=True, diabetes=True, atrial_fibrillation=True, has_smartphone=True)
    assert "Pulse" not in names(kit_for(known, assessment=ficha()))


def test_ecg_is_only_asked_with_a_watch_or_after_an_infarction():
    plain = ClinicalRecord(age=62, female=False, hypertension=True, diabetes=True, has_smartphone=True)
    assert "30-second ECG" not in names(kit_for(plain, assessment=ficha()))
    watch = by_name(kit_for(plain, Devices(watch_ecg=True), assessment=ficha()), "30-second ECG")
    assert watch.supply == OWN and "not yet validated" in watch.why

    infarction = ClinicalRecord(age=64, female=False, hypertension=True, diabetes=True, coronary=True, has_smartphone=True)
    lent = by_name(kit_for(infarction, assessment=ficha()), "30-second ECG")
    assert lent.supply == LENT and "22%" in lent.why and "1.8%" in lent.why
    assert by_name(kit_for(infarction, Devices(watch_ecg=True), assessment=ficha()), "30-second ECG").supply == OWN

    failing = ClinicalRecord(age=64, female=False, hypertension=True, diabetes=True, coronary=True, heart_failure=True, has_smartphone=True)
    assert "30-second ECG" not in names(kit_for(failing, Devices(watch_ecg=True), assessment=ficha()))
    assert "Five questions: " in describe_kit(kit_for(failing, assessment=ficha()))


@pytest.mark.skipif(not rhythm.available(), reason="rhythm detector missing")
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
    if pulse.available():  # the pulse alone barely moves the suspicion of a weak heart
        assert [c.source for c in record.heart_checks] == ["pulso", "pulso"]
        assert all(0.5 < c.likelihood_ratio < 3.0 for c in record.heart_checks)

    with pytest.raises(ValueError):
        checks_from_pulse(DAY, regular, "cuff")


@pytest.mark.skipif(not rhythm.available(), reason="rhythm detector missing")
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


def test_the_kit_speaks_spanish_with_the_original_texts():
    record = ClinicalRecord(age=62, female=False, hypertension=True, bp_meds=True, coronary=True, has_smartphone=True)
    with use_lang("es"):
        items = kit_for(record, assessment=ficha(urine_test(), home_glucose_test(), home_bp_test()))
        assert names(items) == ["Orina", "Cinco preguntas", "Glucosa", "Tensión", "Pulso", "ECG de 30 segundos"]
        assert by_name(items, "Orina").how == "tiras de albúmina y creatinina, leídas con la cámara del móvil"
        assert by_name(items, "Glucosa").how == "una medida en ayunas en la farmacia más cercana, sin cita"
        assert by_name(items, "Tensión").why == "Tensión en consulta de 150 mmHg. Hay que ver si está controlada con el tratamiento."
        ecg = by_name(items, "ECG de 30 segundos")
        assert ecg.why == "Tras un infarto, el 22 % tiene la fracción de eyección baja (el 1,8 % de los mayores de 45 años)."
        text = describe_kit(items)
        assert "  - Cinco preguntas: en la aplicación (sin aparato). No cuestan nada." in text
        assert "  - Tensión: manguito validado, una semana: dos medidas por la mañana y dos por la noche (se le presta)." in text
        with pytest.raises(ValueError, match="El pulso viene del reloj o de la cámara."):
            checks_from_pulse(DAY, [0.8] * 40, "cuff")
