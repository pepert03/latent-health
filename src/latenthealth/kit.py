"""Qué lleva el kit de cada paciente y cómo entran las medidas del reloj o de la cámara.

El kit no es igual para todos ni depende de qué enfermedad tiene el paciente: lleva **lo que
su ficha dice que falta** (las recomendaciones de ``assessment``). Nadie compra nada: las tiras
se mandan y los aparatos se prestan.

- **Tiras de orina**: quien no tiene la albuminuria medida o la tiene dudosa.
- **Cinco preguntas**: todos; no cuestan nada.
- **Glucosa capilar**: quien no tiene diabetes diagnosticada y sale con probabilidad suficiente
  de tenerla oculta. Basta una medida, así que se hace en la farmacia más cercana (o con su
  glucómetro, si lo tiene) y no hay aparato que prestar. Al diabético ya diagnosticado no le
  descubre nada.
- **Manguito, una semana**: quien tiene la tensión de consulta alta o sin registrar, tenga o no
  hipertensión diagnosticada. En el primero se mira si está controlada; en el segundo, si es
  hipertensión. Para ordenar el riesgo no hace falta (``reports/kit_en_casa.md``).
- **Pulso**: no hay aparato que mandar. La aplicación lo toma del reloj si el paciente lo
  conecta y, si no, lo mide con la cámara del móvil.
- **ECG de una derivación**: el del reloj si lo tiene. Si no, un electrocardiógrafo de bolsillo
  prestado solo tras un infarto, donde la fracción de eyección baja es mucho más frecuente.

La gota de sangre en papel por correo (creatinina, HbA1c) no va en el kit: se pide cuando la
lista del cupo dice que la creatinina es la prueba que más aporta.

Conectar el reloj es cosa de la aplicación (Apple Health, Health Connect o la del fabricante).
Aquí está la entrada de esos datos: ``checks_from_pulse`` recibe los intervalos entre latidos y
``checks_from_ecg`` la señal del ECG, y devuelven las comprobaciones que guarda la ficha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import ejection, pulse, rhythm
from .albuminuria import Channel, choose_channel
from .assessment import HOME_BP_HOW, HOME_BP_TEST, HOME_GLUCOSE_TEST, URINE_TEST, ClinicalRecord, PatientAssessment, assess
from .home import LOW_EF_AFTER_INFARCTION, LOW_EF_PREVALENCE, RHYTHM_SOURCES, HeartCheck, RhythmCheck

SENT, LENT, OWN, NO_DEVICE, PHARMACY = "se le manda", "se le presta", "ya lo tiene", "sin aparato", "en la farmacia"


@dataclass
class Devices:
    """Lo que el paciente ya tiene en casa y puede usar o conectar a la aplicación."""

    watch_pulse: bool = False  # reloj o pulsera que registra el pulso latido a latido
    watch_ecg: bool = False  # reloj que graba un ECG de una derivación
    cuff: bool = False  # manguito propio
    glucometer: bool = False


@dataclass
class KitItem:
    name: str
    how: str  # con qué se hace
    why: str
    supply: str  # "se le manda", "se le presta", "ya lo tiene", "sin aparato" o "en la farmacia"


def _pct(value: float, decimals: int) -> str:
    return f"{100 * value:.{decimals}f} %".replace(".", ",")


def kit_for(
    record: ClinicalRecord,
    devices: Devices | None = None,
    assessment: PatientAssessment | None = None,
    as_of: date | None = None,
) -> list[KitItem]:
    """Lo que tiene que hacer este paciente en casa y con qué.

    Sale de las recomendaciones de su ficha (``assessment``; si no se pasa, se calcula).
    """
    devices = devices or Devices()
    if assessment is None:
        assessment = assess(record, as_of=as_of, detail=False)
    asked = {r.test: r.reason for r in assessment.recommendations}
    phone = choose_channel(record.age, record.has_smartphone) is Channel.APP
    items = []
    if URINE_TEST in asked:
        items.append(
            KitItem(
                "Orina",
                "tiras de albúmina y creatinina, leídas con la cámara del móvil" if phone else "tubo por correo al laboratorio",
                "La albuminuria no se adivina con la historia, y es lo único de casa que mejora el orden del riesgo.",
                SENT,
            )
        )
    items.append(KitItem("Cinco preguntas", "en la aplicación" if phone else "por teléfono o en papel", "No cuestan nada.", NO_DEVICE))
    if HOME_GLUCOSE_TEST in asked:
        # Basta una medida, así que no hace falta prestar el aparato: se hace en la farmacia.
        items.append(
            KitItem(
                "Glucosa",
                "una medida en ayunas con su glucómetro" if devices.glucometer else "una medida en ayunas en la farmacia más cercana, sin cita",
                asked[HOME_GLUCOSE_TEST],
                OWN if devices.glucometer else PHARMACY,
            )
        )
    if HOME_BP_TEST in asked:
        treated = record.hypertension or record.bp_meds
        purpose = "Hay que ver si está controlada con el tratamiento." if treated else "Hay que ver si es hipertensión."
        items.append(
            KitItem(
                "Tensión",
                ("su manguito" if devices.cuff else "manguito validado") + ", una semana: dos medidas por la mañana y dos por la noche",
                f"{asked[HOME_BP_TEST].removesuffix(HOME_BP_HOW).strip()} {purpose}",
                OWN if devices.cuff else LENT,
            )
        )
    if not record.atrial_fibrillation:
        why = "Un pulso irregular repetido hace sospechar fibrilación auricular."
        if devices.watch_pulse or devices.watch_ecg:
            items.append(KitItem("Pulso", "su reloj, conectado a la aplicación", why, OWN))
        elif phone:
            items.append(KitItem("Pulso", "la cámara del móvil, con el dedo sobre la lente", why, NO_DEVICE))
    if not record.heart_failure:
        if devices.watch_ecg:
            items.append(
                KitItem(
                    "ECG de 30 segundos",
                    "su reloj, conectado a la aplicación",
                    "Hace sospechar un corazón que bombea poco. Con la derivación del reloj está sin validar.",
                    OWN,
                )
            )
        elif record.coronary:
            items.append(
                KitItem(
                    "ECG de 30 segundos",
                    "electrocardiógrafo de bolsillo",
                    f"Tras un infarto, el {_pct(LOW_EF_AFTER_INFARCTION, 0)} tiene la fracción de eyección baja "
                    f"(el {_pct(LOW_EF_PREVALENCE, 1)} de los mayores de 45 años).",
                    LENT,
                )
            )
    return items


def describe_kit(items: list[KitItem], reasons: bool = True) -> str:
    return "\n".join(f"  - {item.name}: {item.how} ({item.supply})." + (f" {item.why}" if reasons else "") for item in items)


# --- Medidas del reloj o de la cámara ---


def checks_from_pulse(day: date, rr, source: str = "reloj") -> tuple[RhythmCheck, HeartCheck | None]:
    """Una medida del pulso: los intervalos entre latidos (s) que da el reloj o la cámara del móvil.

    Devuelve la comprobación del ritmo (fibrilación auricular) y la del corazón (con solo el
    pulso apenas mueve la probabilidad de fracción de eyección baja; ver ``pulse``).
    """
    if source not in ("reloj", "cámara"):
        raise ValueError("El pulso viene del reloj o de la cámara.")
    rhythm_check = rhythm.check_from_intervals(day, rr)
    rhythm_check.source = source
    heart_check = None
    if pulse.available():
        result = pulse.classify_pulse([rr])
        heart_check = HeartCheck(day, result.likelihood_ratio if result.usable else 1.0, "pulso")
    return rhythm_check, heart_check


def checks_from_ecg(day: date, signal, fs: float) -> tuple[RhythmCheck, HeartCheck | None]:
    """Un ECG de una derivación (unos 30 s) del reloj o de un electrocardiógrafo de bolsillo.

    El ritmo se valora con los latidos del ECG, que es con lo que se validó el detector. La
    fracción de eyección baja, con el modelo de ECG de ``ejection``, entrenado con el aparato
    apoyado en el pecho: con la derivación de muñeca a dedo de un reloj está sin validar.
    """
    rhythm_check = rhythm.check_from_intervals(day, rhythm.intervals_from_beats(rhythm.detect_beats(signal, fs)))
    rhythm_check.source = "ecg"
    heart_check = None
    if ejection.available():
        heart_check = ejection.check_from_recordings(day, [ejection.recording_features(signal, fs, profiles=True)], tier="ecg")
    return rhythm_check, heart_check


def add_checks(record: ClinicalRecord, checks: tuple[RhythmCheck, HeartCheck | None]) -> None:
    """Guarda en la ficha las comprobaciones de una medida."""
    rhythm_check, heart_check = checks
    if rhythm_check.source not in RHYTHM_SOURCES:
        raise ValueError(f"Origen del pulso desconocido: {rhythm_check.source}.")
    record.rhythm_checks.append(rhythm_check)
    if heart_check is not None:
        record.heart_checks.append(heart_check)
