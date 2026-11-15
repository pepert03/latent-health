"""App assistant: without Anthropic credentials it answers in guided mode, with the model's data."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from latenthealth.i18n import use_lang
from server.main import LanguageMiddleware
from server.routes import chat

PILAR = {"age": 58, "female": True, "diabetes": False, "egfr": 88}


@pytest.fixture()
def client(monkeypatch):
    # The tests never call a language model: guided mode is forced.
    monkeypatch.setattr(chat, "_ask_claude", lambda body, facts: None)
    app = FastAPI()
    app.include_router(chat.router)
    app.add_middleware(LanguageMiddleware)  # X-Lang: es -> Spanish replies
    return TestClient(app)


def ask(client, text, samples=(), today="2026-11-16", lang=None):
    body = {"patient": PILAR, "today": today, "samples": list(samples), "messages": [{"role": "user", "content": text}]}
    return client.post("/api/home/chat", json=body, headers={"X-Lang": lang} if lang else None)


def test_next_test_date_comes_from_the_protocol(client):
    response = ask(client, "When is my next test?")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "guiado" and body["model"] is None
    assert "Tuesday, November 17, 2026" in body["reply"]


def test_spanish_questions_still_match(client):
    assert "Tuesday, November 17, 2026" in ask(client, "¿Cuándo me toca la próxima prueba?").json()["reply"]


def test_summary_uses_the_model_estimate(client):
    samples = [{"kind": "tira", "date": "2026-11-17", "albumin_mg_l": 30, "creatinine_mg_dl": 100}]
    reply = ask(client, "How am I doing?", samples, today="2026-11-17").json()["reply"]
    assert "not conclusive" in reply
    assert "mg/g" in reply


def test_treatment_questions_go_to_the_doctor(client):
    reply = ask(client, "Which pill should I take?").json()["reply"]
    assert "doctor" in reply


def test_emergencies_point_to_112(client):
    assert "112" in ask(client, "My chest hurts and I'm short of breath").json()["reply"]


def test_last_message_must_be_from_the_patient(client):
    body = {"patient": PILAR, "today": "2026-11-16", "messages": [{"role": "assistant", "content": "Hello"}]}
    response = client.post("/api/home/chat", json=body)
    assert response.status_code == 400
    assert response.json() == {"detail": "The last message in the conversation must be from the patient."}


def test_facts_contain_what_the_assistant_may_say():
    body = chat.ChatIn(patient=PILAR, today="2026-11-16", messages=[{"role": "user", "content": "hello"}])
    step = chat.home._step(chat.home.StepIn(patient=body.patient, today=body.today))
    facts = chat._facts(body, step)
    assert "Woman, 58 years old, without diabetes" in facts
    assert f"Next step: {chat.home.ACTION_LABELS['tira']}" in facts


# Spanish (X-Lang: es): the original texts, exactly.


def test_guided_replies_in_spanish(client):
    reply = ask(client, "¿Cuándo me toca la próxima prueba?", lang="es").json()["reply"]
    assert reply.startswith("Tu siguiente paso es el martes 17 de noviembre de 2026: ")
    assert ask(client, "¿Qué pastilla tengo que tomar?", lang="es").json()["reply"] == (
        "Eso tiene que valorarlo tu médico: yo solo puedo explicarte tus pruebas de casa. "
        "Puedes escribirle desde la pestaña «Mi médico»."
    )
    samples = [{"kind": "tira", "date": "2026-11-17", "albumin_mg_l": 30, "creatinine_mg_dl": 100}]
    summary = ask(client, "¿Cómo voy?", samples, today="2026-11-17", lang="es").json()["reply"]
    assert summary.startswith(
        "El resultado todavía no es concluyente: hace falta otra prueba para aclararlo. El valor estimado es de "
    )
    assert "mg/g (por debajo de 30 es normal)." in summary
    doubt = ask(client, "¿Qué significa dudoso?", samples, today="2026-11-17", lang="es").json()["reply"]
    assert "Cuando está entre el 5 % y el 95 % hace falta otra medida para decidir." in doubt
    assert " %. " in doubt  # the probability with the Spanish space before the sign


def test_errors_in_spanish(client):
    body = {"patient": PILAR, "today": "2026-11-16", "messages": [{"role": "assistant", "content": "Hola"}]}
    response = client.post("/api/home/chat", json=body, headers={"X-Lang": "es"})
    assert response.status_code == 400
    assert response.json() == {"detail": "El último mensaje de la conversación tiene que ser del paciente."}


def test_facts_and_prompt_in_spanish():
    body = chat.ChatIn(patient=PILAR, today="2026-11-16", messages=[{"role": "user", "content": "hola"}])
    with use_lang("es"):
        step = chat.home._step(chat.home.StepIn(patient=body.patient, today=body.today))
        facts = chat._facts(body, step)
        assert chat._system_prompt() == chat.SYSTEM_PROMPT_ES
        assert chat._pct(0.004) == "menos del 1 %" and chat._num(5.84) == "5,8"
    assert "Paciente: Mujer de 58 años, sin diabetes." in facts
    assert "Hoy es lunes 16 de noviembre de 2026." in facts
    assert "Pruebas hechas: ninguna todavía." in facts
    assert chat._system_prompt() == chat.SYSTEM_PROMPT_EN and "answer in English" in chat.SYSTEM_PROMPT_EN
