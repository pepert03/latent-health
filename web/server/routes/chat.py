"""Asistente de la app del paciente: responde preguntas sobre su evolución.

Dos modos, y la respuesta dice siempre cuál se ha usado:

- ``ia``: un modelo de lenguaje (Claude) redacta la respuesta a partir de lo que ha calculado el
  modelo clínico para ese paciente. Necesita credenciales de Anthropic en el entorno
  (``ANTHROPIC_API_KEY`` o un perfil de ``ant auth login``).
- ``guiado``: sin credenciales, o si la llamada falla, contesta con frases fijas rellenadas con
  los mismos datos. La demo nunca depende de la red.

En los dos casos los números y la fecha de la próxima prueba salen del protocolo de casa
(``routes/home.py``); el asistente explica, no diagnostica ni pauta tratamientos.
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

from . import home

log = logging.getLogger("latenthealth.web.chat")

router = APIRouter(prefix="/api/home", tags=["En casa (app del paciente)"])

CHAT_MODEL = os.environ.get("LATENTHEALTH_CHAT_MODEL", "claude-opus-5-5")
MAX_MESSAGES = 30
MAX_CHARS = 1200

SYSTEM_PROMPT = """Eres el asistente de la aplicación LatentHealth, que acompaña a una persona mientras se hace en casa \
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

_STATUS_PLAIN = {
    "sin_medir": "Todavía no tienes ninguna prueba de orina registrada.",
    "descartada": "Tus pruebas no muestran albúmina en la orina.",
    "dudosa": "El resultado todavía no es concluyente: hace falta otra prueba para aclararlo.",
    "pendiente_cronicidad": (
        "Se ha visto albúmina en la orina. Para confirmarlo falta repetir la prueba pasados tres meses."
    ),
    "confirmada": "Se ha encontrado albúmina en la orina de forma repetida.",
}

_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(description="Quién habla: el paciente o el asistente.")
    content: str = Field(description="Texto del mensaje.")


class ChatIn(BaseModel):
    """La conversación y lo necesario para saber cómo va el paciente (el servidor no recuerda nada)."""

    patient: home.PatientIn = Field(description="El paciente.")
    channel: home.Channel = Field(home.DEFAULT_CHANNEL, description="Canal por el que hace la prueba.")
    today: dt.date = Field(description="Fecha de hoy para el paciente (AAAA-MM-DD).")
    samples: list[home.SampleIn] = Field(default_factory=list, description="Muestras hechas hasta hoy.")
    messages: list[ChatMessage] = Field(description="La conversación; el último mensaje es del paciente.")


class ChatOut(BaseModel):
    reply: str = Field(description="Respuesta del asistente.")
    mode: Literal["ia", "guiado"] = Field(
        description="«ia»: redactada por un modelo de lenguaje; «guiado»: frases fijas con los datos del modelo clínico."
    )
    model: str | None = Field(description="Modelo de lenguaje que ha contestado, si lo hubo.")


def _long_date(day: dt.date) -> str:
    return f"{_WEEKDAYS[day.weekday()]} {day.day} de {_MONTHS[day.month - 1]} de {day.year}"


def _pct(p: float) -> str:
    v = p * 100
    if 0 < v < 1:
        return "menos del 1 %"
    if 99 < v < 100:
        return "más del 99 %"
    return f"{v:.0f} %"


def _num(v: float) -> str:
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}".replace(".", ",")


def _facts(body: ChatIn, step: home.StepOut) -> str:
    """Lo que ha calculado el modelo clínico, en texto: es todo lo que el asistente sabe."""
    p, a = body.patient, step.assessment
    who = f"{'Mujer' if p.female else 'Hombre'} de {p.age:.0f} años, {'con' if p.diabetes else 'sin'} diabetes."
    lines = [
        f"Paciente: {who}",
        f"Hoy es {_long_date(body.today)}.",
        f"Estado de la albúmina en orina: {a.status_label}. {_STATUS_PLAIN.get(a.status, '')}",
        f"Probabilidad de que haya albúmina en la orina de forma mantenida: {_pct(step.p_albuminuria)}.",
    ]
    if step.samples:
        lines.append(
            f"Valor estimado (cociente albúmina/creatinina): {_num(a.median)} mg/g, "
            f"con un intervalo del 80 % entre {_num(a.low)} y {_num(a.high)} mg/g. Por debajo de 30 mg/g es normal."
        )
        lines.append("Pruebas hechas:")
        lines += [f"- {_long_date(s.date)}: {s.label}" for s in step.samples]
    else:
        lines.append("Pruebas hechas: ninguna todavía.")
    lines += [
        (
            f"Siguiente paso: {step.action_label}. Próximo aviso: {_long_date(step.on)}."
            if step.finished
            else f"Siguiente paso: {step.action_label}, el {_long_date(step.on)}."
        ),
        f"Mensaje que la aplicación le ha dado al paciente: «{step.patient_message}»",
        f"Material del kit: {step.kit.strips_used} de {step.kit.strips_total} tiras usadas y "
        f"{step.kit.tubes_used} de {step.kit.tubes_total} tubos usados.",
    ]
    return "\n".join(lines)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _guided(body: ChatIn, step: home.StepOut) -> str:
    """Respuesta sin modelo de lenguaje: frases fijas con los datos del modelo clínico."""
    q = _plain(body.messages[-1].content)
    a = step.assessment
    status = _STATUS_PLAIN.get(a.status, "")
    if step.action == "fin_normal":
        nxt = f"No tienes pruebas pendientes. Te avisaremos para repetirla el {_long_date(step.on)}."
    elif step.action == "centro":
        nxt = "No tienes más pruebas pendientes en casa: tu centro de salud te llamará."
    else:
        nxt = f"Tu siguiente paso es el {_long_date(step.on)}: {step.action_label.lower()}."

    def has(*words: str) -> bool:
        return any(re.search(rf"\b{w}", q) for w in words)

    if has("pecho", "ahogo", "falta de aire", "urgen", "desmay"):
        return "Si lo que notas puede ser una urgencia, llama al 112. Para cualquier otra duda sobre síntomas, escribe a tu médico desde la pestaña «Mi médico»."
    if has("medic", "tratamiento", "pastilla", "farmaco", "dolor", "sintoma", "dieta", "tomar"):
        return "Eso tiene que valorarlo tu médico: yo solo puedo explicarte tus pruebas de casa. Puedes escribirle desde la pestaña «Mi médico»."
    if has("cuando", "proxim", "toca", "recordatorio", "siguiente", "fecha"):
        return f"{nxt} {step.patient_message}"
    if has("repet", "otra vez", "por que", "porque"):
        return (
            "Una sola medida puede salir alta por causas pasajeras: ejercicio intenso, fiebre, la regla o una infección de orina. "
            f"Por eso se repite solo cuando el resultado no es concluyente. {nxt}"
        )
    if has("albumin", "que es", "que mide", "tira", "rinon"):
        return (
            "La albúmina es una proteína de la sangre. Un riñón sano casi no la deja pasar a la orina, "
            "así que encontrarla de forma repetida es una señal temprana de que sus filtros están sufriendo. "
            "La tira mide cuánta hay."
        )
    if has("dudos", "concluyente", "significa", "probab"):
        return (
            f"{status} Ahora mismo la probabilidad de que haya albúmina de forma mantenida es del {_pct(step.p_albuminuria)}. "
            "Cuando está entre el 5 % y el 95 % hace falta otra medida para decidir."
        )
    if has("tubo", "laboratorio"):
        return "El tubo va al laboratorio, que mide el valor exacto. Solo se pide cuando una tira más ya no aclararía la duda."
    if has("gracias", "vale", "ok", "perfecto"):
        return "A ti. Aquí estoy si te surge otra duda."
    # «¿Cómo voy?», evolución, resultados y cualquier otra cosa: el resumen.
    if step.samples:
        estimate = f" El valor estimado es de {_num(a.median)} mg/g (por debajo de 30 es normal)."
    else:
        estimate = ""
    return f"{status}{estimate} {nxt}"


def _ask_claude(body: ChatIn, facts: str) -> tuple[str, str] | None:
    """Pide la respuesta a Claude. Devuelve (texto, modelo) o None si no hay credenciales o falla."""
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(timeout=30.0, max_retries=1)
        response = client.beta.messages.create(
            model=CHAT_MODEL,
            max_tokens=4000,
            # Si un clasificador de seguridad declina la petición, la API la reintenta en otro modelo.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},  # respuestas cortas: prima la rapidez
            system=[
                {"type": "text", "text": SYSTEM_PROMPT},
                {"type": "text", "text": f"DATOS DEL PACIENTE\n{facts}"},
            ],
            messages=[{"role": m.role, "content": m.content} for m in body.messages],
        )
    except anthropic.AuthenticationError:
        log.info("Asistente en modo guiado: credenciales de Anthropic no válidas.")
        return None
    except anthropic.APIStatusError as exc:
        log.warning("Asistente en modo guiado: la API devolvió %s (%s).", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("Asistente en modo guiado: sin conexión con la API.")
        return None
    except anthropic.AnthropicError as exc:  # p. ej. no hay ninguna credencial configurada
        log.info("Asistente en modo guiado: %s", exc)
        return None
    except TypeError as exc:  # sin ninguna credencial, o un SDK que no conoce algún parámetro
        log.info("Asistente en modo guiado: %s", exc)
        return None

    if response.stop_reason == "refusal":
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return (text, response.model) if text else None


@router.post("/chat", response_model=ChatOut, summary="Asistente del paciente")
def chat(body: ChatIn) -> ChatOut:
    """Contesta la última pregunta del paciente con lo que el modelo clínico sabe de él."""
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="El último mensaje de la conversación tiene que ser del paciente.")
    if len(body.messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail=f"La conversación admite como mucho {MAX_MESSAGES} mensajes.")
    if any(not m.content.strip() or len(m.content) > MAX_CHARS for m in body.messages):
        raise HTTPException(status_code=400, detail=f"Cada mensaje debe tener entre 1 y {MAX_CHARS} caracteres.")

    step = home._step(
        home.StepIn(patient=body.patient, channel=body.channel, today=body.today, samples=body.samples)
    )
    answer = _ask_claude(body, _facts(body, step))
    if answer is not None:
        return ChatOut(reply=answer[0], mode="ia", model=answer[1])
    return ChatOut(reply=_guided(body, step), mode="guiado", model=None)
