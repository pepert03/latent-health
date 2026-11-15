"""What goes into each patient's kit, and how watch or camera measurements come in.

The kit is not the same for everyone and does not depend on the patient's disease: it holds
**what their record says is missing** (the recommendations from ``assessment``). Nobody buys
anything: strips are sent and devices are lent.

- **Urine strips**: anyone whose albuminuria is not measured or is doubtful.
- **Five questions**: everyone; they cost nothing.
- **Capillary glucose**: anyone without diagnosed diabetes whose probability of hidden
  diabetes is high enough. One reading is enough, so it is done at the nearest pharmacy (or
  with their own glucometer, if they have one) and there is no device to lend. It tells
  nothing new about an already diagnosed diabetic.
- **Cuff, one week**: anyone whose office blood pressure is high or not recorded, whether or
  not they have diagnosed hypertension. In the first case we check whether it is controlled;
  in the second, whether it is hypertension. Not needed to rank risk (``reports/kit_en_casa.md``).
- **Pulse**: no device to send. The app takes it from the watch if the patient connects one
  and, if not, measures it with the phone camera.
- **Single-lead ECG**: the watch's, if they have one. Otherwise a pocket ECG device, lent only
  after a heart attack, where low ejection fraction is much more common.

The dried blood spot by mail (creatinine, HbA1c) is not in the kit: it is requested when the
practice-list worklist says creatinine is the most informative test.

Connecting the watch is the app's job (Apple Health, Health Connect or the manufacturer's).
Here is where that data comes in: ``checks_from_pulse`` takes the inter-beat intervals and
``checks_from_ecg`` the ECG signal, and they return the checks stored in the record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import ejection, pulse, rhythm
from .albuminuria import Channel, choose_channel
from .assessment import ClinicalRecord, PatientAssessment, assess, home_bp_how, home_bp_test, home_glucose_test, urine_test
from .home import LOW_EF_AFTER_INFARCTION, LOW_EF_PREVALENCE, RHYTHM_SOURCES, HeartCheck, RhythmCheck
from .i18n import Labels, fmt_pct, t

# How each item reaches the patient: stable keys, shown through SUPPLY_LABELS.
SENT, LENT, OWN, NO_DEVICE, PHARMACY = "sent", "lent", "own", "no_device", "pharmacy"
SUPPLY_LABELS = Labels(
    {
        SENT: ("se le manda", "sent"),
        LENT: ("se le presta", "lent"),
        OWN: ("ya lo tiene", "already has it"),
        NO_DEVICE: ("sin aparato", "no device"),
        PHARMACY: ("en la farmacia", "at the pharmacy"),
    }
)


@dataclass
class Devices:
    """What the patient already has at home and can use or connect to the app."""

    watch_pulse: bool = False  # watch or band that records the pulse beat by beat
    watch_ecg: bool = False  # watch that records a single-lead ECG
    cuff: bool = False  # own blood pressure cuff
    glucometer: bool = False


@dataclass
class KitItem:
    name: str
    how: str  # what it is done with
    why: str
    supply: str  # SENT, LENT, OWN, NO_DEVICE or PHARMACY (key)

    @property
    def supply_label(self) -> str:
        return SUPPLY_LABELS[self.supply]


def kit_for(
    record: ClinicalRecord,
    devices: Devices | None = None,
    assessment: PatientAssessment | None = None,
    as_of: date | None = None,
) -> list[KitItem]:
    """What this patient has to do at home, and with what.

    Comes from the recommendations in their record (``assessment``; computed if not given).
    """
    devices = devices or Devices()
    if assessment is None:
        assessment = assess(record, as_of=as_of, detail=False)
    asked = {r.test: r.reason for r in assessment.recommendations}
    phone = choose_channel(record.age, record.has_smartphone) is Channel.APP
    items = []
    if urine_test() in asked:
        items.append(
            KitItem(
                t("Orina", "Urine"),
                t("tiras de albúmina y creatinina, leídas con la cámara del móvil", "albumin and creatinine strips, read with the phone camera")
                if phone
                else t("tubo por correo al laboratorio", "tube by mail to the lab"),
                t(
                    "La albuminuria no se adivina con la historia, y es lo único de casa que mejora el orden del riesgo.",
                    "Albuminuria cannot be guessed from the medical history, and it is the only home test that improves the risk ranking.",
                ),
                SENT,
            )
        )
    items.append(
        KitItem(
            t("Cinco preguntas", "Five questions"),
            t("en la aplicación", "in the app") if phone else t("por teléfono o en papel", "by phone or on paper"),
            t("No cuestan nada.", "They cost nothing."),
            NO_DEVICE,
        )
    )
    if home_glucose_test() in asked:
        # One reading is enough, so no device needs to be lent: it is done at the pharmacy.
        items.append(
            KitItem(
                t("Glucosa", "Glucose"),
                t("una medida en ayunas con su glucómetro", "one fasting reading with their own glucometer")
                if devices.glucometer
                else t(
                    "una medida en ayunas en la farmacia más cercana, sin cita",
                    "one fasting reading at the nearest pharmacy, no appointment",
                ),
                asked[home_glucose_test()],
                OWN if devices.glucometer else PHARMACY,
            )
        )
    if home_bp_test() in asked:
        treated = record.hypertension or record.bp_meds
        purpose = (
            t("Hay que ver si está controlada con el tratamiento.", "We need to see whether it is controlled on treatment.")
            if treated
            else t("Hay que ver si es hipertensión.", "We need to see whether it is hypertension.")
        )
        items.append(
            KitItem(
                t("Tensión", "Blood pressure"),
                (t("su manguito", "their own cuff") if devices.cuff else t("manguito validado", "validated cuff"))
                + t(
                    ", una semana: dos medidas por la mañana y dos por la noche",
                    ", one week: two readings in the morning and two in the evening",
                ),
                f"{asked[home_bp_test()].removesuffix(home_bp_how()).strip()} {purpose}",
                OWN if devices.cuff else LENT,
            )
        )
    if not record.atrial_fibrillation:
        why = t(
            "Un pulso irregular repetido hace sospechar fibrilación auricular.",
            "A repeatedly irregular pulse raises suspicion of atrial fibrillation.",
        )
        name = t("Pulso", "Pulse")
        if devices.watch_pulse or devices.watch_ecg:
            items.append(KitItem(name, t("su reloj, conectado a la aplicación", "their watch, connected to the app"), why, OWN))
        elif phone:
            how = t("la cámara del móvil, con el dedo sobre la lente", "the phone camera, with a finger on the lens")
            items.append(KitItem(name, how, why, NO_DEVICE))
    if not record.heart_failure:
        if devices.watch_ecg:
            items.append(
                KitItem(
                    t("ECG de 30 segundos", "30-second ECG"),
                    t("su reloj, conectado a la aplicación", "their watch, connected to the app"),
                    t(
                        "Hace sospechar un corazón que bombea poco. Con la derivación del reloj está sin validar.",
                        "Raises suspicion of a heart that pumps poorly. With the watch lead it is not yet validated.",
                    ),
                    OWN,
                )
            )
        elif record.coronary:
            items.append(
                KitItem(
                    t("ECG de 30 segundos", "30-second ECG"),
                    t("electrocardiógrafo de bolsillo", "pocket ECG device"),
                    t(
                        f"Tras un infarto, el {fmt_pct(LOW_EF_AFTER_INFARCTION, 0)} tiene la fracción de eyección baja "
                        f"(el {fmt_pct(LOW_EF_PREVALENCE, 1)} de los mayores de 45 años).",
                        f"After a heart attack, {fmt_pct(LOW_EF_AFTER_INFARCTION, 0)} have a low ejection fraction "
                        f"({fmt_pct(LOW_EF_PREVALENCE, 1)} of people over 45).",
                    ),
                    LENT,
                )
            )
    return items


def describe_kit(items: list[KitItem], reasons: bool = True) -> str:
    return "\n".join(f"  - {item.name}: {item.how} ({item.supply_label})." + (f" {item.why}" if reasons else "") for item in items)


# --- Watch or camera measurements ---


def checks_from_pulse(day: date, rr, source: str = "reloj") -> tuple[RhythmCheck, HeartCheck | None]:
    """One pulse measurement: the inter-beat intervals (s) from the watch or the phone camera.

    ``source`` is a machine value: "reloj" (watch) or "cámara" (camera). Returns the rhythm
    check (atrial fibrillation) and the heart check (the pulse alone barely moves the
    probability of low ejection fraction; see ``pulse``).
    """
    if source not in ("reloj", "cámara"):
        raise ValueError(
            t("El pulso viene del reloj o de la cámara.", 'The pulse comes from the watch ("reloj") or the camera ("cámara").')
        )
    rhythm_check = rhythm.check_from_intervals(day, rr)
    rhythm_check.source = source
    heart_check = None
    if pulse.available():
        result = pulse.classify_pulse([rr])
        heart_check = HeartCheck(day, result.likelihood_ratio if result.usable else 1.0, "pulso")
    return rhythm_check, heart_check


def checks_from_ecg(day: date, signal, fs: float) -> tuple[RhythmCheck, HeartCheck | None]:
    """A single-lead ECG (about 30 s) from the watch or a pocket ECG device.

    Rhythm is scored with the ECG beats, which is what the detector was validated with. Low
    ejection fraction uses the ECG model in ``ejection``, trained with the device held against
    the chest: with a watch's wrist-to-finger lead it is not validated.
    """
    rhythm_check = rhythm.check_from_intervals(day, rhythm.intervals_from_beats(rhythm.detect_beats(signal, fs)))
    rhythm_check.source = "ecg"
    heart_check = None
    if ejection.available():
        heart_check = ejection.check_from_recordings(day, [ejection.recording_features(signal, fs, profiles=True)], tier="ecg")
    return rhythm_check, heart_check


def add_checks(record: ClinicalRecord, checks: tuple[RhythmCheck, HeartCheck | None]) -> None:
    """Stores the checks from one measurement in the record."""
    rhythm_check, heart_check = checks
    if rhythm_check.source not in RHYTHM_SOURCES:
        raise ValueError(t(f"Origen del pulso desconocido: {rhythm_check.source}.", f"Unknown pulse source: {rhythm_check.source}."))
    record.rhythm_checks.append(rhythm_check)
    if heart_check is not None:
        record.heart_checks.append(heart_check)
