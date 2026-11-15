"""Patient-app assistant: answers questions about how the patient is doing.

Two modes, and the reply always says which one was used:

- ``ia``: a language model (Claude) writes the answer from what the clinical model computed for
  this patient. Needs Anthropic credentials in the environment (``ANTHROPIC_API_KEY``).
- ``guiado``: without credentials, or if the call fails, it answers with fixed sentences filled in
  with the same data. The demo never depends on the network.

In both cases the numbers and the date of the next test come from the home protocol
(``routes/home.py``); the assistant explains, it does not diagnose or prescribe.

Replies come in the request language (Spanish or English, see ``latenthealth.i18n``).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import unicodedata
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from latenthealth.i18n import Labels, fmt_date, is_es, t

from . import home

log = logging.getLogger("latenthealth.web.chat")

router = APIRouter(prefix="/api/home", tags=["At home (patient app)"])

CHAT_MODEL = os.environ.get("LATENTHEALTH_CHAT_MODEL", "claude-opus-5-5")
MAX_MESSAGES = 30
MAX_CHARS = 1200

SYSTEM_PROMPT_ES = """Eres el asistente de la aplicación LatentHealth, que acompaña a una persona mientras se hace en casa \
pruebas de orina para detectar pronto un daño del riñón. Hablas con el paciente, no con un profesional sanitario.

Para qué sirves: explicarle con palabras sencillas en qué punto está, qué significa su último resultado, por qué a \
veces hay que repetir una prueba y cuándo le toca la siguiente. Mucha gente se asusta al leer «no concluyente» o \
«repetir»; tu trabajo es que lo entienda sin alarmarse y sin quitarle importancia.

De dónde sale lo que sabes: del bloque DATOS DEL PACIENTE que acompaña a cada conversación. Lo ha calculado el \
modelo clínico de LatentHealth. Usa solo esos datos: no inventes cifras, fechas ni resultados, y si te preguntan \
algo que no está ahí, dilo con naturalidad.

Límites, y por qué existen: esto es un prototipo de apoyo, no un médico. No diagnostiques, no recomiendes ni \
ajustes medicación y no interpretes síntomas. Si la persona pregunta por tratamiento, describe síntomas o quiere \
una opinión clínica, dile que eso lo valora su médico y que puede escribirle desde la pestaña «Mi médico» de la \
aplicación. Si describe algo que suena a urgencia (dolor en el pecho, falta de aire intensa, pérdida de fuerza o \
del habla), dile que llame al 112.

Cómo escribes: español de España, tuteando, cálido y directo. Respuestas cortas: dos a cuatro frases, sin listas, \
sin títulos y sin tecnicismos (di «albúmina en la orina», no «albuminuria»; «filtrado del riñón», no «FG»). \
Fechas como «martes 17 de noviembre». Si das una probabilidad, redondéala y explica qué quiere decir."""

SYSTEM_PROMPT_EN = """You are the assistant in the LatentHealth app, which supports a person while they do urine tests \
at home to catch kidney damage early. You are talking to the patient, not to a healthcare professional.

What you are for: explaining in simple words where they stand, what their latest result means, why a test \
sometimes has to be repeated and when the next one is due. Many people get scared when they read "inconclusive" or \
"repeat"; your job is to help them understand it without alarming them and without brushing it off.

Where your knowledge comes from: the PATIENT DATA block that comes with each conversation. It was computed by the \
LatentHealth clinical model. Use only that data: do not make up numbers, dates or results, and if you are asked \
something that is not there, say so naturally.

Limits, and why they exist: this is a support prototype, not a doctor. Do not diagnose, do not recommend or adjust \
medication and do not interpret symptoms. If the person asks about treatment, describes symptoms or wants a \
clinical opinion, tell them that is for their doctor to assess and that they can write to them from the "My doctor" \
tab in the app. If they describe something that sounds like an emergency (chest pain, severe shortness of breath, \
loss of strength or speech), tell them to call 112.

How you write: always answer in English, plain, warm and direct, addressing the patient as "you". Keep replies \
short: two to four sentences, no lists, no headings and no jargon (say "albumin in the urine", not "albuminuria"; \
"kidney filtering", not "eGFR"). Write dates like "Tuesday, November 17". If you give a probability, round it and \
explain what it means."""

# Kept for compatibility: the English prompt.
SYSTEM_PROMPT = SYSTEM_PROMPT_EN

_STATUS_PLAIN = Labels(
    {
        "sin_medir": (
            "Todavía no tienes ninguna prueba de orina registrada.",
            "You don't have any urine tests recorded yet.",
        ),
        "descartada": ("Tus pruebas no muestran albúmina en la orina.", "Your tests show no albumin in the urine."),
        "dudosa": (
            "El resultado todavía no es concluyente: hace falta otra prueba para aclararlo.",
            "The result is not conclusive yet: another test is needed to clear it up.",
        ),
        "pendiente_cronicidad": (
            "Se ha visto albúmina en la orina. Para confirmarlo falta repetir la prueba pasados tres meses.",
            "Albumin has been found in the urine. To confirm it, the test needs to be repeated after three months.",
        ),
        "confirmada": (
            "Se ha encontrado albúmina en la orina de forma repetida.",
            "Albumin has been found in the urine more than once.",
        ),
    }
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(description="Who is speaking: the patient or the assistant.")
    content: str = Field(description="Message text.")


class ChatIn(BaseModel):
    """The conversation and what is needed to know how the patient is doing (the server remembers nothing)."""

    patient: home.PatientIn = Field(description="The patient.")
    channel: home.Channel = Field(home.DEFAULT_CHANNEL, description="Channel used for the test.")
    today: dt.date = Field(description="Today's date for the patient (YYYY-MM-DD).")
    samples: list[home.SampleIn] = Field(default_factory=list, description="Samples taken so far.")
    messages: list[ChatMessage] = Field(description="The conversation; the last message is from the patient.")


class ChatOut(BaseModel):
    reply: str = Field(description="The assistant's reply.")
    mode: Literal["ia", "guiado"] = Field(
        description='"ia": written by a language model; "guiado": fixed sentences with the clinical model\'s data.'
    )
    model: str | None = Field(description="Language model that answered, if any.")


def _long_date(day: dt.date) -> str:
    return fmt_date(day)


def _pct(p: float) -> str:
    v = p * 100
    if 0 < v < 1:
        return t("menos del 1 %", "less than 1%")
    if 99 < v < 100:
        return t("más del 99 %", "more than 99%")
    return t(f"{v:.0f} %", f"{v:.0f}%")


def _num(v: float) -> str:
    if v >= 10:
        return f"{v:.0f}"
    return f"{v:.1f}".replace(".", ",") if is_es() else f"{v:.1f}"


def _system_prompt() -> str:
    return t(SYSTEM_PROMPT_ES, SYSTEM_PROMPT_EN)


def _facts(body: ChatIn, step: home.StepOut) -> str:
    """What the clinical model computed, as text: everything the assistant knows."""
    p, a = body.patient, step.assessment
    if is_es():
        who = f"{'Mujer' if p.female else 'Hombre'} de {p.age:.0f} años, {'con' if p.diabetes else 'sin'} diabetes."
    else:
        who = f"{'Woman' if p.female else 'Man'}, {p.age:.0f} years old, {'with' if p.diabetes else 'without'} diabetes."
    today, prob = _long_date(body.today), _pct(step.p_albuminuria)
    lines = [
        t(f"Paciente: {who}", f"Patient: {who}"),
        t(f"Hoy es {today}.", f"Today is {today}."),
        t(
            f"Estado de la albúmina en orina: {a.status_label}. {_STATUS_PLAIN.get(a.status, '')}",
            f"Urine albumin status: {a.status_label}. {_STATUS_PLAIN.get(a.status, '')}",
        ),
        t(
            f"Probabilidad de que haya albúmina en la orina de forma mantenida: {prob}.",
            f"Probability of persistent albumin in the urine: {prob}.",
        ),
    ]
    if step.samples:
        median, low, high = _num(a.median), _num(a.low), _num(a.high)
        lines.append(
            t(
                f"Valor estimado (cociente albúmina/creatinina): {median} mg/g, "
                f"con un intervalo del 80 % entre {low} y {high} mg/g. Por debajo de 30 mg/g es normal.",
                f"Estimated value (albumin/creatinine ratio): {median} mg/g, "
                f"with an 80% interval between {low} and {high} mg/g. Below 30 mg/g is normal.",
            )
        )
        lines.append(t("Pruebas hechas:", "Tests done:"))
        lines += [f"- {_long_date(s.date)}: {s.label}" for s in step.samples]
    else:
        lines.append(t("Pruebas hechas: ninguna todavía.", "Tests done: none yet."))
    on, kit = _long_date(step.on), step.kit
    lines += [
        (
            t(
                f"Siguiente paso: {step.action_label}. Próximo aviso: {on}.",
                f"Next step: {step.action_label}. Next reminder: {on}.",
            )
            if step.finished
            else t(f"Siguiente paso: {step.action_label}, el {on}.", f"Next step: {step.action_label}, on {on}.")
        ),
        t(
            f"Mensaje que la aplicación le ha dado al paciente: «{step.patient_message}»",
            f'Message the app showed the patient: "{step.patient_message}"',
        ),
        t(
            f"Material del kit: {kit.strips_used} de {kit.strips_total} tiras usadas y "
            f"{kit.tubes_used} de {kit.tubes_total} tubos usados.",
            f"Kit supplies: {kit.strips_used} of {kit.strips_total} strips used and "
            f"{kit.tubes_used} of {kit.tubes_total} tubes used.",
        ),
    ]
    return "\n".join(lines)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _guided(body: ChatIn, step: home.StepOut) -> str:
    """Reply without a language model: fixed sentences with the clinical model's data."""
    q = _plain(body.messages[-1].content)
    a = step.assessment
    status = _STATUS_PLAIN.get(a.status, "")
    on = _long_date(step.on)
    if step.action == "fin_normal":
        nxt = t(
            f"No tienes pruebas pendientes. Te avisaremos para repetirla el {on}.",
            f"You have no tests pending. We'll remind you to repeat it on {on}.",
        )
    elif step.action == "centro":
        nxt = t(
            "No tienes más pruebas pendientes en casa: tu centro de salud te llamará.",
            "You have no more tests to do at home: your health center will call you.",
        )
    else:
        action = step.action_label.lower()
        nxt = t(f"Tu siguiente paso es el {on}: {action}.", f"Your next step is on {on}: {action}.")

    def has(*words: str) -> bool:
        return any(re.search(rf"\b{w}", q) for w in words)

    # Spanish and English keywords, so questions in either language find their answer.
    if has("pecho", "ahogo", "falta de aire", "urgen", "desmay", "chest", "breath", "emergenc", "faint"):
        return t(
            "Si lo que notas puede ser una urgencia, llama al 112. Para cualquier otra duda sobre síntomas, escribe a tu médico desde la pestaña «Mi médico».",
            'If what you feel could be an emergency, call 112. For any other question about symptoms, write to your doctor from the "My doctor" tab.',
        )
    if has(
        "medic", "tratamiento", "pastilla", "farmaco", "dolor", "sintoma", "dieta", "tomar",
        "treatment", "pill", "drug", "dose", "pain", "symptom", "diet",
    ):  # fmt: skip
        return t(
            "Eso tiene que valorarlo tu médico: yo solo puedo explicarte tus pruebas de casa. Puedes escribirle desde la pestaña «Mi médico».",
            'That is something your doctor needs to assess: I can only explain your home tests. You can write to them from the "My doctor" tab.',
        )
    if has("cuando", "proxim", "toca", "recordatorio", "siguiente", "fecha", "when", "next", "remind", "date", "due"):
        return f"{nxt} {step.patient_message}"
    if has("repet", "otra vez", "por que", "porque", "repeat", "again", "why"):
        return t(
            "Una sola medida puede salir alta por causas pasajeras: ejercicio intenso, fiebre, la regla o una infección de orina. "
            f"Por eso se repite solo cuando el resultado no es concluyente. {nxt}",
            "A single test can come out high for passing reasons: hard exercise, fever, your period or a urine infection. "
            f"That's why it is repeated only when the result is not conclusive. {nxt}",
        )
    if has("albumin", "que es", "que mide", "tira", "rinon", "strip", "kidney", "what is"):
        return t(
            "La albúmina es una proteína de la sangre. Un riñón sano casi no la deja pasar a la orina, "
            "así que encontrarla de forma repetida es una señal temprana de que sus filtros están sufriendo. "
            "La tira mide cuánta hay.",
            "Albumin is a protein in the blood. A healthy kidney lets almost none of it into the urine, "
            "so finding it more than once is an early sign that its filters are struggling. "
            "The strip measures how much there is.",
        )
    if has("dudos", "concluyente", "significa", "probab", "doubt", "conclusive", "inconclusive", "mean", "likely"):
        prob = _pct(step.p_albuminuria)
        return t(
            f"{status} Ahora mismo la probabilidad de que haya albúmina de forma mantenida es del {prob}. "
            "Cuando está entre el 5 % y el 95 % hace falta otra medida para decidir.",
            f"{status} Right now the probability of persistent albumin is {prob}. "
            "When it is between 5% and 95%, another test is needed to decide.",
        )
    if has("tubo", "laboratorio", "tube", "lab"):
        return t(
            "El tubo va al laboratorio, que mide el valor exacto. Solo se pide cuando una tira más ya no aclararía la duda.",
            "The tube goes to the lab, which measures the exact value. It is only requested when one more strip would no longer clear up the doubt.",
        )
    if has("gracias", "vale", "ok", "perfecto", "thank", "great", "perfect"):
        return t("A ti. Aquí estoy si te surge otra duda.", "You're welcome. I'm here if you have any other questions.")
    # "How am I doing?", progress, results and anything else: the summary.
    if step.samples:
        median = _num(a.median)
        estimate = t(
            f" El valor estimado es de {median} mg/g (por debajo de 30 es normal).",
            f" The estimated value is {median} mg/g (below 30 is normal).",
        )
    else:
        estimate = ""
    return f"{status}{estimate} {nxt}"


def _ask_claude(body: ChatIn, facts: str) -> tuple[str, str] | None:
    """Asks Claude for the reply. Returns (text, model), or None without credentials or on failure.

    Runs in the request's context, so the language set by the middleware picks the prompt.
    """
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(timeout=30.0, max_retries=1)
        response = client.beta.messages.create(
            model=CHAT_MODEL,
            max_tokens=4000,
            # If a safety classifier declines the request, the API retries it on another model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},  # short replies: speed matters most
            system=[
                {"type": "text", "text": _system_prompt()},
                {"type": "text", "text": t("DATOS DEL PACIENTE", "PATIENT DATA") + f"\n{facts}"},
            ],
            messages=[{"role": m.role, "content": m.content} for m in body.messages],
        )
    except anthropic.AuthenticationError:
        log.info("Assistant in guided mode: invalid Anthropic credentials.")
        return None
    except anthropic.APIStatusError as exc:
        log.warning("Assistant in guided mode: the API returned %s (%s).", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("Assistant in guided mode: no connection to the API.")
        return None
    except anthropic.AnthropicError as exc:  # e.g. no credentials configured at all
        log.info("Assistant in guided mode: %s", exc)
        return None
    except TypeError as exc:  # no credentials at all, or an SDK that doesn't know some parameter
        log.info("Assistant in guided mode: %s", exc)
        return None

    if response.stop_reason == "refusal":
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return (text, response.model) if text else None


@router.post("/chat", response_model=ChatOut, summary="Patient assistant")
def chat(body: ChatIn) -> ChatOut:
    """Answers the patient's last question with what the clinical model knows about them."""
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(
            status_code=400,
            detail=t(
                "El último mensaje de la conversación tiene que ser del paciente.",
                "The last message in the conversation must be from the patient.",
            ),
        )
    if len(body.messages) > MAX_MESSAGES:
        raise HTTPException(
            status_code=400,
            detail=t(
                f"La conversación admite como mucho {MAX_MESSAGES} mensajes.",
                f"The conversation allows at most {MAX_MESSAGES} messages.",
            ),
        )
    if any(not m.content.strip() or len(m.content) > MAX_CHARS for m in body.messages):
        raise HTTPException(
            status_code=400,
            detail=t(
                f"Cada mensaje debe tener entre 1 y {MAX_CHARS} caracteres.",
                f"Each message must be between 1 and {MAX_CHARS} characters long.",
            ),
        )

    step = home._step(
        home.StepIn(patient=body.patient, channel=body.channel, today=body.today, samples=body.samples)
    )
    answer = _ask_claude(body, _facts(body, step))
    if answer is not None:
        return ChatOut(reply=answer[0], mode="ia", model=answer[1])
    return ChatOut(reply=_guided(body, step), mode="guiado", model=None)
