"""Asistente de la app: sin credenciales de Anthropic contesta en modo guiado, con los datos del modelo."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes import chat

PILAR = {"age": 58, "female": True, "diabetes": False, "egfr": 88}


@pytest.fixture()
def client(monkeypatch):
    # Los tests no llaman a ningún modelo de lenguaje: se fuerza el modo guiado.
    monkeypatch.setattr(chat, "_ask_claude", lambda body, facts: None)
    app = FastAPI()
    app.include_router(chat.router)
    return TestClient(app)


def ask(client, text, samples=(), today="2026-11-16"):
    body = {"patient": PILAR, "today": today, "samples": list(samples), "messages": [{"role": "user", "content": text}]}
    return client.post("/api/home/chat", json=body)


def test_next_test_date_comes_from_the_protocol(client):
    response = ask(client, "¿Cuándo me toca la próxima prueba?")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "guiado" and body["model"] is None
    assert "martes 17 de noviembre de 2026" in body["reply"]


def test_summary_uses_the_model_estimate(client):
    samples = [{"kind": "tira", "date": "2026-11-17", "albumin_mg_l": 30, "creatinine_mg_dl": 100}]
    reply = ask(client, "¿Cómo voy?", samples, today="2026-11-17").json()["reply"]
    assert "no es concluyente" in reply
    assert "mg/g" in reply


def test_treatment_questions_go_to_the_doctor(client):
    reply = ask(client, "¿Qué pastilla tengo que tomar?").json()["reply"]
    assert "médica" in reply


def test_emergencies_point_to_112(client):
    assert "112" in ask(client, "Me duele el pecho y tengo ahogo").json()["reply"]


def test_last_message_must_be_from_the_patient(client):
    body = {"patient": PILAR, "today": "2026-11-16", "messages": [{"role": "assistant", "content": "Hola"}]}
    assert client.post("/api/home/chat", json=body).status_code == 400


def test_facts_contain_what_the_assistant_may_say():
    body = chat.ChatIn(patient=PILAR, today="2026-11-16", messages=[{"role": "user", "content": "hola"}])
    step = chat.home._step(chat.home.StepIn(patient=body.patient, today=body.today))
    facts = chat._facts(body, step)
    assert "Mujer de 58 años, sin diabetes" in facts
    assert "Siguiente paso: Tira en casa" in facts
