"""Home albuminuria screening protocol.

Decides a patient's next step after each sample and says it in plain words: "all done",
"repeat tomorrow", "send the tube" or "your health center will call you".

- **Two stages.** First home strips, which are cheap and already in the kit. Only if the
  doubt remains (strips run out, or one more strip is unlikely to settle it) is a tube for
  the lab requested, which measures the exact value.
- **Questions before the test.** With intense exercise, fever, menstruation or infection
  symptoms, the test is postponed instead of wasting a strip on a sample that is not valid.
- **Channels.** Not everyone has a smartphone: the same logic works with the strip read by
  eye, at the pharmacy, with the nurse, or with just the tube by mail. Only the reading error
  (``StripSpec``) and the instruction text change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .context import SampleContext, deferral, questions
from ..i18n import Labels, fmt_date, t
from .filter import AlbuminuriaAssessment, AlbuminuriaFilter, Patient, UrineSample
from .model import FIRST_MORNING
from .strip import EYE_STRIP, PHONE_STRIP, StripSample, StripSpec


class Channel(str, Enum):
    # Values are machine keys shared with the web API; keep them as they are.
    APP = "aplicación"  # strip read with the phone camera
    PAPER = "carta"  # strip read by eye; the patient reports the two numbers by phone or text
    PHARMACY = "farmacia"  # the patient brings the urine and the strip is read there
    NURSE = "enfermería"  # same, at the health center, no appointment
    MAIL = "correo"  # no strip: tube to the lab


@dataclass(frozen=True)
class HomeKit:
    channel: Channel
    strip: StripSpec | None  # None: the channel uses no strips
    strips: int = 3  # strips in the kit
    tube: bool = True  # a tube for the lab can be requested
    tubes: int = 2
    # Expected participation of those invited. Only known from the THOMAS trial (Netherlands,
    # ages 45-80): 59.4% with a tube by mail and 44.3% with the app. The rest is an assumption.
    participation: float = 0.5
    participation_measured: bool = False


KITS: dict[Channel, HomeKit] = {
    Channel.APP: HomeKit(Channel.APP, PHONE_STRIP, participation=0.443, participation_measured=True),
    Channel.PAPER: HomeKit(Channel.PAPER, EYE_STRIP, participation=0.45),
    Channel.PHARMACY: HomeKit(Channel.PHARMACY, EYE_STRIP, participation=0.5),
    Channel.NURSE: HomeKit(Channel.NURSE, EYE_STRIP, participation=0.5),
    Channel.MAIL: HomeKit(Channel.MAIL, None, strips=0, participation=0.594, participation_measured=True),
}


def choose_channel(age: float, has_smartphone: bool | None = None, prefers_in_person: bool = False) -> Channel:
    """Default channel for a patient. Without smartphone data, assume none from age 75."""
    if prefers_in_person:
        return Channel.PHARMACY
    if has_smartphone is None:
        has_smartphone = age < 75
    return Channel.APP if has_smartphone else Channel.MAIL


_STRIP_TEXT = Labels(
    {
        Channel.APP: (
            "con la primera orina del día, haz una tira y hazle la foto con la aplicación",
            "with your first urine of the day, dip a strip and take a photo of it with the app",
        ),
        Channel.PAPER: (
            "con la primera orina del día, haz una tira, compárala con los colores del bote y "
            "apunta los dos números; mándalos por SMS o llama al teléfono de la carta",
            "with your first urine of the day, dip a strip, compare it with the colors on the bottle and "
            "write down the two numbers; text them or call the phone number in the letter",
        ),
        Channel.PHARMACY: (
            "lleva a tu farmacia un bote con la primera orina del día",
            "take a container with your first urine of the day to your pharmacy",
        ),
        Channel.NURSE: (
            "lleva a tu centro de salud un bote con la primera orina del día; no necesitas cita",
            "take a container with your first urine of the day to your health center; no appointment needed",
        ),
    }
)


def _tube_text() -> str:
    return t(
        "llena el tubo con la primera orina del día y échalo al buzón en el sobre del kit",
        "fill the tube with your first urine of the day and mail it in the kit's envelope",
    )


@dataclass
class Step:
    """The patient's next step."""

    # Machine values (kept in Spanish, shared with the web API): "tira" (strip), "tubo" (tube),
    # "esperar" (wait), "fin_normal" (done, normal), "centro" (health center),
    # "repetir_cronicidad" (repeat in 3 months).
    action: str
    on: date | None  # day it is due
    patient_message: str  # what the patient reads or hears
    clinician_note: str  # what goes into the medical record
    p_albuminuria: float
    resolve_probability: float | None = None  # of the requested test
    questions: list[tuple[str, str]] = field(default_factory=list)  # questions before the test
    assessment: AlbuminuriaAssessment | None = field(default=None, repr=False)

    @property
    def finished(self) -> bool:
        return self.action in ("fin_normal", "centro")


def next_step(
    filt: AlbuminuriaFilter,
    patient: Patient,
    kit: HomeKit,
    today: date,
    context: SampleContext | None = None,
    episode_start: date | None = None,
    escalate_below: float = 0.3,
    assessment: AlbuminuriaAssessment | None = None,
) -> Step:
    """What the patient has to do now.

    ``context`` holds today's answers to the pre-test questions (if already answered).
    ``episode_start`` marks from when used strips and tubes count (default: 60 days back).
    It escalates to the tube when one more strip would settle the doubt with probability
    below ``escalate_below``. ``assessment`` avoids recomputing the state if already known.
    """
    a = assessment or filt.assess(patient, as_of=today, detail=False)
    p = a.p_a2_plus
    tomorrow = today + timedelta(days=1)
    start = episode_start or today - timedelta(days=60)
    recent = [s for s in patient.samples if s.date >= start]
    strips_used = sum(isinstance(s, StripSample) for s in recent)
    tubes_used = sum(isinstance(s, UrineSample) for s in recent)
    qs = questions(patient.female, patient.age)

    if a.status == "descartada":
        return Step(
            "fin_normal",
            today + timedelta(days=365),
            t(
                "Tu prueba es normal: no hay albúmina en la orina. Te avisaremos para repetirla dentro de un año.",
                "Your test is normal: there is no albumin in your urine. We'll remind you to repeat it in a year.",
            ),
            t(
                f"Albuminuria descartada (P = {p:.0%}). Próximo cribado en un año.",
                f"Albuminuria ruled out (P = {p:.0%}). Next screening in one year.",
            ),
            p,
            assessment=a,
        )
    if a.status == "confirmada":
        return Step(
            "centro",
            today,
            t(
                "Hemos encontrado albúmina en la orina de forma repetida. Tu centro de salud te llamará para darte cita.",
                "We have found albumin in your urine more than once. Your health center will call you to make an appointment.",
            ),
            a.action,
            p,
            assessment=a,
        )

    use_tube = kit.tube and tubes_used < kit.tubes
    use_strip = kit.strip is not None and strips_used < kit.strips

    if a.status == "pendiente_cronicidad":
        # The repeat is a new episode: new supplies are sent by then.
        when = max(tomorrow, a.repeat_from or tomorrow)
        how = _tube_text() if kit.tube or kit.strip is None else _STRIP_TEXT[kit.channel]
        return Step(
            "repetir_cronicidad",
            when,
            t(
                f"Hemos visto albúmina en la orina. Para confirmarlo hay que repetir la prueba pasados tres meses. "
                f"Te mandaremos el material. El {when:%d/%m/%Y}, {how}.",
                f"We have seen albumin in your urine. To confirm it, the test has to be repeated after three months. "
                f"We'll send you what you need. On {fmt_date(when)}, {how}.",
            ),
            a.action,
            p,
            questions=qs,
            assessment=a,
        )

    # Not measured or doubtful: another sample is needed.
    wait, advice = deferral(context, patient.female, patient.age)
    if wait:
        return Step(
            "esperar",
            today + timedelta(days=wait),
            t("Hoy la prueba no sería fiable. ", "Today the test would not be reliable. ") + " ".join(advice),
            t(
                f"Prueba aplazada {wait} días por el contexto de la muestra.",
                f"Test postponed {wait} days because of the sample context.",
            ),
            p,
            questions=qs,
            assessment=a,
        )

    z = filt.covariates(patient)
    r_strip = filt.resolve_probability(a.belief, z, FIRST_MORNING, strip=kit.strip) if use_strip else None
    first = a.status == "sin_medir"
    if use_strip and (first or not use_tube or r_strip >= escalate_below):
        lead = (
            t("Mañana", "Tomorrow")
            if first
            else t(
                "El resultado no es concluyente, es normal que pase. Mañana",
                "The result is not conclusive; this is normal. Tomorrow",
            )
        )
        return Step(
            "tira",
            tomorrow,
            f"{lead}, {_STRIP_TEXT[kit.channel]}.",
            t(
                f"P(albuminuria) = {p:.0%}. Se pide una tira ({strips_used + 1} de {kit.strips}); "
                f"probabilidad de resolver: {r_strip:.0%}.",
                f"P(albuminuria) = {p:.0%}. Strip requested ({strips_used + 1} of {kit.strips}); "
                f"probability of resolving: {r_strip:.0%}.",
            ),
            p,
            r_strip,
            qs,
            a,
        )
    if use_tube:
        r_tube = filt.resolve_probability(a.belief, z, FIRST_MORNING)
        lead = (
            t("Mañana", "Tomorrow")
            if first
            else t(
                "Para salir de dudas hace falta medirlo en el laboratorio. Mañana",
                "To settle it, it has to be measured in the lab. Tomorrow",
            )
        )
        return Step(
            "tubo",
            tomorrow,
            f"{lead}, {_tube_text()}.",
            t(
                f"P(albuminuria) = {p:.0%}. Se pide muestra para laboratorio; probabilidad de resolver: {r_tube:.0%}.",
                f"P(albuminuria) = {p:.0%}. Lab sample requested; probability of resolving: {r_tube:.0%}.",
            ),
            p,
            r_tube,
            qs,
            a,
        )
    return Step(
        "centro",
        today,
        t(
            "Con las pruebas de casa no hemos podido aclararlo. Tu centro de salud te llamará para hacerte un análisis de orina.",
            "The home tests could not settle it. Your health center will call you to arrange a urine test.",
        ),
        t(
            f"Albuminuria dudosa tras el kit (P = {p:.0%}). Pedir UACR en primera orina de la mañana.",
            f"Albuminuria doubtful after the kit (P = {p:.0%}). Order UACR on a first morning urine sample.",
        ),
        p,
        assessment=a,
    )
