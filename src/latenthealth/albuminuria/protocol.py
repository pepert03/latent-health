"""Protocolo de cribado de la albuminuria en casa.

Decide el siguiente paso de un paciente después de cada muestra y lo dice con palabras
sencillas: "ya está", "repite mañana", "manda el tubo" o "te llamarán de tu centro".

- **Dos etapas.** Primero tiras en casa, que son baratas y ya están en el kit. Solo si la
  duda sigue (se acaban las tiras o una tira más tiene poca probabilidad de resolverla) se
  pide un tubo para el laboratorio, que mide el valor exacto.
- **Preguntas antes de la prueba.** Si hay ejercicio intenso, fiebre, regla o síntomas de
  infección, la prueba se aplaza en vez de gastar una tira en una muestra que no vale.
- **Canales.** No todo el mundo tiene móvil: la misma lógica sirve con la tira leída a ojo,
  en la farmacia, en enfermería o solo con el tubo por correo. Cambia el error de lectura
  (``StripSpec``) y el texto de las instrucciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from .context import SampleContext, deferral, questions
from .filter import AlbuminuriaAssessment, AlbuminuriaFilter, Patient, UrineSample
from .model import FIRST_MORNING
from .strip import EYE_STRIP, PHONE_STRIP, StripSample, StripSpec


class Channel(str, Enum):
    APP = "aplicación"  # tira leída con la cámara del móvil
    PAPER = "carta"  # tira leída a ojo; el paciente comunica los dos números por teléfono o SMS
    PHARMACY = "farmacia"  # el paciente lleva la orina y la tira se lee allí
    NURSE = "enfermería"  # igual, en el centro de salud y sin cita
    MAIL = "correo"  # sin tira: tubo al laboratorio


@dataclass(frozen=True)
class HomeKit:
    channel: Channel
    strip: StripSpec | None  # None: el canal no usa tiras
    strips: int = 3  # tiras que trae el kit
    tube: bool = True  # se puede pedir un tubo para el laboratorio
    tubes: int = 2
    # Participación esperada de los invitados. Solo se conoce la del ensayo THOMAS (Países
    # Bajos, 45-80 años): 59,4 % con tubo por correo y 44,3 % con aplicación. El resto es un supuesto.
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
    """Canal por defecto para un paciente. Sin dato del móvil, se asume que no a partir de 75 años."""
    if prefers_in_person:
        return Channel.PHARMACY
    if has_smartphone is None:
        has_smartphone = age < 75
    return Channel.APP if has_smartphone else Channel.MAIL


_STRIP_TEXT = {
    Channel.APP: "con la primera orina del día, haz una tira y hazle la foto con la aplicación",
    Channel.PAPER: (
        "con la primera orina del día, haz una tira, compárala con los colores del bote y "
        "apunta los dos números; mándalos por SMS o llama al teléfono de la carta"
    ),
    Channel.PHARMACY: "lleva a tu farmacia un bote con la primera orina del día",
    Channel.NURSE: "lleva a tu centro de salud un bote con la primera orina del día; no necesitas cita",
}
_TUBE_TEXT = "llena el tubo con la primera orina del día y échalo al buzón en el sobre del kit"


@dataclass
class Step:
    """Siguiente paso del paciente."""

    action: str  # "tira", "tubo", "esperar", "fin_normal", "centro", "repetir_cronicidad"
    on: date | None  # día en que toca
    patient_message: str  # lo que lee o escucha el paciente
    clinician_note: str  # lo que queda en la historia
    p_albuminuria: float
    resolve_probability: float | None = None  # de la prueba que se pide
    questions: list[tuple[str, str]] = field(default_factory=list)  # preguntas antes de la prueba
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
    """Qué tiene que hacer el paciente ahora.

    ``context`` son sus respuestas de hoy a las preguntas previas (si ya las ha contestado).
    ``episode_start`` marca desde cuándo cuentan las tiras y tubos gastados (por defecto, 60 días).
    Se pasa al tubo cuando una tira más resolvería la duda con probabilidad menor que
    ``escalate_below``. ``assessment`` evita recalcular el estado si ya se tiene.
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
            "Tu prueba es normal: no hay albúmina en la orina. Te avisaremos para repetirla dentro de un año.",
            f"Albuminuria descartada (P = {p:.0%}). Próximo cribado en un año.",
            p,
            assessment=a,
        )
    if a.status == "confirmada":
        return Step(
            "centro",
            today,
            "Hemos encontrado albúmina en la orina de forma repetida. Tu centro de salud te llamará para darte cita.",
            a.action,
            p,
            assessment=a,
        )

    use_tube = kit.tube and tubes_used < kit.tubes
    use_strip = kit.strip is not None and strips_used < kit.strips

    if a.status == "pendiente_cronicidad":
        # La repetición es otro episodio: para entonces se manda material nuevo.
        when = max(tomorrow, a.repeat_from or tomorrow)
        how = _TUBE_TEXT if kit.tube or kit.strip is None else _STRIP_TEXT[kit.channel]
        return Step(
            "repetir_cronicidad",
            when,
            f"Hemos visto albúmina en la orina. Para confirmarlo hay que repetir la prueba pasados tres meses. "
            f"Te mandaremos el material. El {when:%d/%m/%Y}, {how}.",
            a.action,
            p,
            questions=qs,
            assessment=a,
        )

    # Sin medir o dudosa: hace falta otra muestra.
    wait, advice = deferral(context, patient.female, patient.age)
    if wait:
        return Step(
            "esperar",
            today + timedelta(days=wait),
            "Hoy la prueba no sería fiable. " + " ".join(advice),
            f"Prueba aplazada {wait} días por el contexto de la muestra.",
            p,
            questions=qs,
            assessment=a,
        )

    z = filt.covariates(patient)
    r_strip = filt.resolve_probability(a.belief, z, FIRST_MORNING, strip=kit.strip) if use_strip else None
    first = a.status == "sin_medir"
    if use_strip and (first or not use_tube or r_strip >= escalate_below):
        lead = "Mañana" if first else "El resultado no es concluyente, es normal que pase. Mañana"
        return Step(
            "tira",
            tomorrow,
            f"{lead}, {_STRIP_TEXT[kit.channel]}.",
            f"P(albuminuria) = {p:.0%}. Se pide una tira ({strips_used + 1} de {kit.strips}); "
            f"probabilidad de resolver: {r_strip:.0%}.",
            p,
            r_strip,
            qs,
            a,
        )
    if use_tube:
        r_tube = filt.resolve_probability(a.belief, z, FIRST_MORNING)
        lead = "Mañana" if first else "Para salir de dudas hace falta medirlo en el laboratorio. Mañana"
        return Step(
            "tubo",
            tomorrow,
            f"{lead}, {_TUBE_TEXT}.",
            f"P(albuminuria) = {p:.0%}. Se pide muestra para laboratorio; probabilidad de resolver: {r_tube:.0%}.",
            p,
            r_tube,
            qs,
            a,
        )
    return Step(
        "centro",
        today,
        "Con las pruebas de casa no hemos podido aclararlo. Tu centro de salud te llamará para hacerte un análisis de orina.",
        f"Albuminuria dudosa tras el kit (P = {p:.0%}). Pedir UACR en primera orina de la mañana.",
        p,
        assessment=a,
    )
