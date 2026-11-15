"""Contract tests for /api/home (patient app), with the real models.

    uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests/test_home.py -q

Expected numbers come from the model survey (walkthroughs in scripts/demo_casa.py and variants
run with the "espana" population). They mount their own app with only these routes.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from latenthealth.albuminuria import (
    FIRST_MORNING,
    KITS,
    PHONE_STRIP,
    Channel,
    Patient,
    SampleContext,
    StripSample,
    UrineSample,
    load_default_filter,
    next_step,
)
from latenthealth.albuminuria import context as urine_context
from server.main import LanguageMiddleware
from server.routes import home

app = FastAPI()
app.include_router(home.router)
app.add_middleware(LanguageMiddleware)  # same language selection as the real server

TOL = 2e-3  # probability tolerance against the report (which gives four decimals)
STEP = "/api/home/step"

# Patient messages, verbatim from the model (protocol.py).
T1 = "Tomorrow, with your first urine of the day, dip a strip and take a photo of it with the app."
T2 = "The result is not conclusive; this is normal. " + T1
TB1 = "Tomorrow, fill the tube with your first urine of the day and mail it in the kit's envelope."
TB2 = "To settle it, it has to be measured in the lab. " + TB1
FN = "Your test is normal: there is no albumin in your urine. We'll remind you to repeat it in a year."
CF = "We have found albumin in your urine more than once. Your health center will call you to make an appointment."
CK = "The home tests could not settle it. Your health center will call you to arrange a urine test."
RC = (
    "We have seen albumin in your urine. To confirm it, the test has to be repeated after three months. "
    "We'll send you what you need. On {when}, fill the tube with your first urine of the day and mail it in the kit's envelope."
)

JULIAN = {"age": 62, "female": False, "diabetes": False, "egfr": 85}
PILAR = {"age": 58, "female": True, "diabetes": False, "egfr": 88}
MARTA = {"age": 47, "female": True, "diabetes": True, "egfr": 92}
NO3 = {"exercise_24h": False, "fever": False, "uti_symptoms": False}  # a man's three questions
NO4 = {**NO3, "menstruation": False}

SEEN: list[str] = []  # body of every 200 response, for the final test


@pytest.fixture(scope="module")
def api():
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def config(api) -> dict:
    return get(api, "/api/home/config")


def get(api, path: str) -> dict:
    response = api.get(path)
    assert response.status_code == 200, response.text
    SEEN.append(response.text)
    return response.json()


def post(api, path: str, payload: dict) -> dict:
    response = api.post(path, json=payload)
    assert response.status_code == 200, response.text
    SEEN.append(response.text)
    return response.json()


def rejected(api, path: str, payload: dict, status: int):
    """The request is rejected with that code; returns ``detail``."""
    response = api.post(path, json=payload)
    assert response.status_code == status, response.text
    return response.json()["detail"]


def step(api, patient: dict, today: str, samples=(), **extra) -> dict:
    result = post(api, STEP, {"patient": patient, "today": today, "samples": list(samples), **extra})
    check_invariants(result)
    return result


def strip(day: str, albumin: float, creatinine: float, answers: dict | None = None) -> dict:
    sample = {"kind": "tira", "date": day, "albumin_mg_l": albumin, "creatinine_mg_dl": creatinine}
    return sample if answers is None else {**sample, "answers": answers}


def tube(day: str, uacr: float, answers: dict | None = None) -> dict:
    sample = {"kind": "tubo", "date": day, "uacr": uacr}
    return sample if answers is None else {**sample, "answers": answers}


def replay(api, config: dict, script_id: str) -> list[dict]:
    """Replays a guided walkthrough as the /config docs say, just like the web app.

    Returns the /step responses in order: the initial one and one per request.
    """
    script = next(s for s in config["scripts"] if s["id"] == script_id)
    preset = next(p for p in config["patients"] if p["id"] == script["patient_id"])
    patient = {key: preset[key] for key in ("age", "female", "diabetes", "egfr")}
    today, samples = config["today"], []

    def ask(**extra) -> dict:
        return step(api, patient, today, samples, channel=preset["channel"], **extra)

    seen = [ask()]
    for item in script["steps"]:
        if item["kind"] == "respuestas":
            seen.append(ask(answers=item["answers"]))
            if seen[-1]["action"] == "esperar":
                today = seen[-1]["on"]  # the day arrives
                seen.append(ask())
            continue
        today = seen[-1]["on"]  # the test is done on the day it was due
        if item["kind"] == "tira":
            sample = strip(today, item["albumin_mg_l"], item["creatinine_mg_dl"], item["answers"])
        else:
            sample = tube(today, item["uacr"], item["answers"])
        samples = [*samples, sample]
        seen.append(ask())
    return seen


def check(result: dict, action: str, on: str, p: float, message: str) -> None:
    assert result["action"] == action
    assert result["on"] == on
    assert result["p_albuminuria"] == pytest.approx(p, abs=TOL)
    assert result["patient_message"] == message


def check_invariants(result: dict) -> None:
    """What any /step response must satisfy."""
    a, kit = result["assessment"], result["kit"]
    assert result["action_label"] == home.ACTION_LABELS[result["action"]]
    assert result["finished"] == (result["action"] in ("fin_normal", "centro"))
    assert a["p_a1"] + a["p_a2"] + a["p_a3"] == pytest.approx(1.0, abs=1e-5)
    assert result["p_albuminuria"] == pytest.approx(a["p_a2"] + a["p_a3"], abs=1e-5)
    assert a["low"] <= a["median"] <= a["high"]
    assert (result["resolve_probability"] is not None) == (result["action"] in ("tira", "tubo"))
    assert bool(result["questions"]) == (not result["finished"])
    assert [t["date"] for t in a["trajectory"]] == [s["date"] for s in result["samples"]]
    assert (a["status"] == "sin_medir") == (not result["samples"])
    if result["action"] == "tira":  # the kit is counted with the same window as the protocol
        assert f"({kit['strips_used'] + 1} of {kit['strips_total']})" in result["clinician_note"]
    if result["action"] in ("tira", "tubo"):
        used, total = ("strips_used", "strips_total") if result["action"] == "tira" else ("tubes_used", "tubes_total")
        assert kit[used] < kit[total]


# --- /config ---


def test_config_is_coherent(config):
    assert config["today"] == "2026-11-16"
    assert date.fromisoformat(config["today"]).weekday() == 0  # Monday

    assert [c["key"] for c in config["channels"]] == [channel.name for channel in KITS]
    assert config["channels"][0] == {
        "key": "APP", "value": "aplicación", "strips": 3, "tubes": 2, "uses_strip": True,
        "strip_name": "strip read with the phone",
    }  # fmt: skip
    mail = next(c for c in config["channels"] if c["key"] == "MAIL")
    assert mail == {"key": "MAIL", "value": "correo", "strips": 0, "tubes": 2, "uses_strip": False, "strip_name": None}

    assert config["strip"] == {
        "albumin_levels_mg_l": [10, 30, 80, 150],
        "creatinine_levels_mg_dl": [10, 50, 100, 200, 300],
    }
    assert config["strip"]["albumin_levels_mg_l"] == list(PHONE_STRIP.albumin_levels)
    assert config["strip"]["creatinine_levels_mg_dl"] == list(PHONE_STRIP.creatinine_levels)

    questions = {q["key"]: q for q in config["questions"]}
    assert list(questions) == list(urine_context.QUESTIONS) == list(home.Answers.model_fields)
    assert questions["fever"] == {
        "key": "fever",
        "text": "Do you have a fever today, or did you have one yesterday?",
        "wait_days": 3,
        "advice": "Wait three days after the fever is gone.",
        "audience": "everyone",
    }
    assert [q["wait_days"] for q in config["questions"]] == [2, 3, 5, 10]
    assert [q["audience"] for q in config["questions"]] == ["everyone", "everyone", "women under 56", "everyone"]


def test_config_patients_and_scripts(api, config):
    patients = {p["id"]: p for p in config["patients"]}
    assert len(patients) == len(config["patients"]) == 4
    profiles = {(p["age"], p["female"], p["diabetes"], p["egfr"]) for p in patients.values()}
    assert {(62, False, False, 85), (58, True, False, 88), (47, True, True, 92)} <= profiles
    assert len(profiles) == 4
    channels = {c["value"] for c in config["channels"]}
    for p in patients.values():
        assert p["name"] and p["summary"] and "\n" not in p["summary"]
        assert p["channel"] in channels

    scripts = {s["id"]: s for s in config["scripts"]}
    assert len(scripts) == len(config["scripts"])
    assert {"normal", "confirmada", "aplazada"} <= set(scripts)
    assert {s["patient_id"] for s in scripts.values()} == set(patients)  # every patient has a walkthrough
    levels = config["strip"]
    for script in scripts.values():
        assert script["title"] and script["summary"] and script["steps"]
        patient = patients[script["patient_id"]]
        asked = {key for key, _ in urine_context.questions(patient["female"], patient["age"])}
        for item in script["steps"]:
            assert item["note"]
            # The script answers are exactly those for the questions the model asks that patient.
            assert {key for key, value in item["answers"].items() if value is not None} == asked
            if item["kind"] == "tira":
                assert item["albumin_mg_l"] in levels["albumin_levels_mg_l"]
                assert item["creatinine_mg_dl"] in levels["creatinine_levels_mg_dl"]
                assert item["uacr"] is None
            elif item["kind"] == "tubo":
                assert item["uacr"] > 0 and item["albumin_mg_l"] is None
            else:
                assert item["kind"] == "respuestas"


# --- Guided walkthroughs: the numbers and messages from the report ---


def test_script_normal_at_first_strip(api, config):
    start, answered, done = replay(api, config, "normal")

    check(start, "tira", "2026-11-17", 0.0379, T1)
    assert start["resolve_probability"] == pytest.approx(0.929, abs=TOL)
    assert start["clinician_note"] == "P(albuminuria) = 4%. Strip requested (1 of 3); probability of resolving: 93%."
    assert [q["key"] for q in start["questions"]] == ["exercise_24h", "fever", "uti_symptoms"]
    assert start["assessment"]["status_label"] == "Not measured"

    assert answered == start  # answering no to everything changes nothing

    check(done, "fin_normal", "2027-11-17", 0.0009, FN)
    assert done["finished"] and done["action_label"] == "Done: normal test"
    assert done["clinician_note"] == "Albuminuria ruled out (P = 0%). Next screening in one year."
    a = done["assessment"]
    assert (a["status"], a["status_label"], a["category"]) == ("descartada", "Ruled out", "A1")
    assert (a["median"], a["low"], a["high"]) == pytest.approx((3.9, 2.6, 7.5), abs=0.06)
    assert done["kit"] == {"channel": "aplicación", "strips_total": 3, "strips_used": 1, "tubes_total": 2, "tubes_used": 0}
    assert done["samples"] == [
        {"kind": "tira", "date": "2026-11-17", "label": "Strip: albumin 10 mg/l, creatinine 100 mg/dl", "nominal_uacr": 10.0}
    ]


def test_script_doubt_to_confirmation(api, config):
    start, strip1, strip2, tube1, tube2, repeat = replay(api, config, "confirmada")

    check(start, "tira", "2026-11-17", 0.0168, T1)
    assert start["resolve_probability"] == pytest.approx(0.930, abs=TOL)

    check(strip1, "tira", "2026-11-18", 0.0739, T2)
    assert strip1["resolve_probability"] == pytest.approx(0.734, abs=TOL)
    assert strip1["assessment"]["status"] == "dudosa"
    assert "Strip requested (2 of 3)" in strip1["clinician_note"]
    a = strip1["assessment"]
    assert (a["median"], a["low"], a["high"]) == pytest.approx((12.2, 4.4, 26.7), abs=0.06)

    check(strip2, "tubo", "2026-11-19", 0.2923, TB2)
    assert strip2["resolve_probability"] == pytest.approx(0.313, abs=TOL)

    check(tube1, "tubo", "2026-11-20", 0.7574, TB2)
    assert tube1["resolve_probability"] == pytest.approx(0.299, abs=TOL)
    assert tube1["kit"]["tubes_used"] == 1

    check(tube2, "repetir_cronicidad", "2027-02-18", 0.9681, RC.format(when="Thursday, February 18, 2027"))
    a = tube2["assessment"]
    assert (a["status"], a["status_label"]) == ("pendiente_cronicidad", "Very likely, chronicity pending")
    assert (a["repeat_from"], a["chronicity_met"]) == ("2027-02-18", False)
    assert (a["median"], a["low"], a["high"]) == pytest.approx((51.6, 38.0, 65.0), abs=0.06)
    assert tube2["clinician_note"] == (
        "A2 albuminuria very likely. Repeat from February 18, 2027 to meet the chronicity criterion (more than 3 months)."
    )
    assert not tube2["finished"] and tube2["questions"]

    check(repeat, "centro", "2027-02-18", 0.9961, CF)
    a = repeat["assessment"]
    assert (a["status"], a["category"], a["chronicity_met"]) == ("confirmada", "A2", True)
    assert (a["median"], a["low"], a["high"]) == pytest.approx((59.8, 46.0, 75.1), abs=0.06)
    assert repeat["clinician_note"] == (
        "Persistent A2 albuminuria: record CKD (category A2) and review kidney-protective treatment as per guidelines."
    )
    # The repeat is another episode: only one tube of the new kit has been used.
    assert (repeat["kit"]["strips_used"], repeat["kit"]["tubes_used"]) == (0, 1)
    assert [s["label"] for s in repeat["samples"]] == [
        "Strip: albumin 30 mg/l, creatinine 100 mg/dl",
        "Strip: albumin 30 mg/l, creatinine 50 mg/dl",
        "Tube: 58 mg/g",
        "Tube: 64 mg/g",
        "Tube: 71 mg/g",
    ]
    assert [s["nominal_uacr"] for s in repeat["samples"]] == [30, 60, 58, 64, 71]
    assert len(repeat["assessment"]["trajectory"]) == 5


def test_script_deferred_by_fever(api, config):
    start, deferred, the_day, done = replay(api, config, "aplazada")

    check(start, "tira", "2026-11-17", 0.0648, T1)
    assert start["resolve_probability"] == pytest.approx(0.859, abs=TOL)
    assert [q["key"] for q in start["questions"]] == ["exercise_24h", "fever", "menstruation", "uti_symptoms"]

    check(deferred, "esperar", "2026-11-19", 0.0648, "Today the test would not be reliable. Wait three days after the fever is gone.")
    assert deferred["clinician_note"] == "Test postponed 3 days because of the sample context."
    assert deferred["action_label"] == "Wait" and not deferred["finished"]
    assert deferred["kit"]["strips_used"] == 0  # no strip has been used

    check(the_day, "tira", "2026-11-20", 0.0648, T1)
    check(done, "fin_normal", "2027-11-20", 0.0019, FN)


def test_fourth_patient_goes_straight_to_the_lab(api, config):
    start, doubtful, done = replay(api, config, "laboratorio")

    check(start, "tira", "2026-11-17", 0.4568, T1)
    # With the same doubtful strip, a high-risk patient is asked for the tube; Pilar, for another strip.
    check(doubtful, "tubo", "2026-11-18", 0.4130, TB2)
    assert doubtful["resolve_probability"] == pytest.approx(0.245, abs=TOL)
    same_strip = step(api, PILAR, "2026-11-17", [strip("2026-11-17", 30, 100, NO3)])
    assert same_strip["action"] == "tira"
    check(done, "fin_normal", "2027-11-18", 0.0208, FN)
    assert (done["kit"]["strips_used"], done["kit"]["tubes_used"]) == (1, 1)


# --- Protocol: postponements, kit, channels ---


def test_deferral_by_exercise(api):
    deferred = step(api, MARTA, "2026-11-16", answers={**NO4, "exercise_24h": True})
    check(deferred, "esperar", "2026-11-18", 0.0648, "Today the test would not be reliable. Wait two days without intense exercise.")
    assert deferred["clinician_note"] == "Test postponed 2 days because of the sample context."

    the_day = step(api, MARTA, "2026-11-18")
    check(the_day, "tira", "2026-11-19", 0.0648, T1)
    done = step(api, MARTA, "2026-11-19", [strip("2026-11-19", 10, 100, NO4)])
    check(done, "fin_normal", "2027-11-19", 0.0019, FN)


def test_deferral_takes_the_longest_wait_and_joins_the_advice(api):
    both = step(api, MARTA, "2026-11-16", answers={**NO4, "exercise_24h": True, "fever": True})
    assert (both["action"], both["on"]) == ("esperar", "2026-11-19")
    assert both["patient_message"] == (
        "Today the test would not be reliable. Wait two days without intense exercise. Wait three days after the fever is gone."
    )
    # Menstruation only counts for women under 56.
    assert step(api, MARTA, "2026-11-16", answers={"menstruation": True})["on"] == "2026-11-21"
    assert step(api, JULIAN, "2026-11-16", answers={"menstruation": True})["action"] == "tira"
    assert step(api, PILAR, "2026-11-16", answers={"menstruation": True})["action"] == "tira"


def test_today_answers_only_defer_but_sample_answers_change_the_probability(api):
    day = "2026-11-17"
    assert step(api, MARTA, day, [strip(day, 30, 100)])["p_albuminuria"] == pytest.approx(0.1158, abs=TOL)
    assert step(api, MARTA, day, [strip(day, 30, 100, NO4)])["p_albuminuria"] == pytest.approx(0.1358, abs=TOL)
    with_exercise = step(api, MARTA, day, [strip(day, 30, 100, {**NO4, "exercise_24h": True})])
    assert with_exercise["p_albuminuria"] == pytest.approx(0.1139, abs=TOL)
    # Today's answers do not touch the probability: they only postpone.
    deferred = step(api, MARTA, day, [strip(day, 30, 100, NO4)], answers={"fever": True})
    assert deferred["action"] == "esperar"
    assert deferred["p_albuminuria"] == pytest.approx(0.1358, abs=TOL)


def test_exhausted_kit_goes_to_the_health_centre(api):
    days = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21"]
    samples = [
        strip(days[0], 30, 100, NO3),
        strip(days[1], 30, 100, NO3),
        tube(days[2], 31, NO3),
        tube(days[3], 29, NO3),
        strip(days[4], 30, 100, NO3),
    ]
    # Step by step, always doing the requested test on the due day.
    actions = []
    for n, day in enumerate(days, start=1):
        result = step(api, JULIAN, day, samples[:n])
        actions.append(result["action"])
        if n < len(days):
            assert result["on"] == days[n]
            assert result["action"] == samples[n]["kind"]
    assert actions == ["tira", "tubo", "tubo", "tira", "centro"]

    check(result, "centro", "2026-11-21", 0.3411, CK)
    assert result["finished"] and result["action_label"] == "Done: health center"
    assert result["clinician_note"] == "Albuminuria doubtful after the kit (P = 34%). Order UACR on a first morning urine sample."
    assert result["kit"] == {"channel": "aplicación", "strips_total": 3, "strips_used": 3, "tubes_total": 2, "tubes_used": 2}
    assert result["assessment"]["status"] == "dudosa"


def test_kit_is_counted_over_the_episode_window_of_the_protocol(api):
    today = date(2026, 11, 16)

    def old_strip(days_ago: int) -> dict:
        return strip((today - timedelta(days=days_ago)).isoformat(), 30, 100)

    assert step(api, JULIAN, today.isoformat(), [old_strip(60)])["kit"]["strips_used"] == 1
    outside = step(api, JULIAN, today.isoformat(), [old_strip(61)])
    assert outside["kit"]["strips_used"] == 0
    explicit = step(api, JULIAN, today.isoformat(), [old_strip(61)], episode_start="2026-09-01")
    assert explicit["kit"]["strips_used"] == 1

    # The route's default window is the model's: same note as calling it without episode_start.
    filt, kit = load_default_filter("espana"), KITS[Channel.APP]
    for days_ago, result in ((61, outside), (60, step(api, JULIAN, today.isoformat(), [old_strip(60)]))):
        patient = Patient(62, False, False, 85, [StripSample(today - timedelta(days=days_ago), kit.strip, 30, 100)])
        direct = next_step(filt, patient, kit, today)
        assert result["clinician_note"] == direct.clinician_note
        assert result["patient_message"] == direct.patient_message
        assert result["p_albuminuria"] == pytest.approx(direct.p_albuminuria, abs=1e-6)


def test_other_channels(api):
    # Strip read by eye: the same reading weighs less than with the phone and changes the next step.
    day = "2026-11-17"
    by_phone = step(api, MARTA, day, [strip(day, 30, 100, NO4)])
    by_eye = step(api, MARTA, day, [strip(day, 30, 100, NO4)], channel="carta")
    assert (by_phone["action"], by_eye["action"]) == ("tubo", "tira")
    assert by_eye["p_albuminuria"] == pytest.approx(0.1117, abs=TOL)
    assert by_eye["kit"]["channel"] == "carta"
    assert step(api, MARTA, day, [strip(day, 30, 100, NO4)], channel="PAPER") == by_eye  # the key also works

    pharmacy = step(api, MARTA, "2026-11-16", channel="farmacia")
    assert pharmacy["patient_message"] == "Tomorrow, take a container with your first urine of the day to your pharmacy."

    # By mail there are no strips: it starts with the tube.
    antonio = {"age": 81, "female": False, "diabetes": False, "egfr": 61}
    start = step(api, antonio, "2026-11-16", channel="correo")
    check(start, "tubo", "2026-11-17", 0.1216, TB1)
    assert start["kit"] == {"channel": "correo", "strips_total": 0, "strips_used": 0, "tubes_total": 2, "tubes_used": 0}
    done = step(api, antonio, "2026-11-17", [tube("2026-11-17", 11)], channel="correo")
    check(done, "fin_normal", "2027-11-17", 0.0013, FN)
    detail = rejected(api, STEP, {"patient": antonio, "today": day, "channel": "correo", "samples": [strip(day, 10, 100)]}, 400)
    assert detail == 'The "correo" channel does not use strips: it only accepts tube samples.'


def test_samples_come_back_in_chronological_order(api):
    samples = [tube("2026-11-19", 31.4), strip("2026-11-17", 30, 50)]
    result = step(api, JULIAN, "2026-11-20", samples)
    assert result["samples"] == [
        {"kind": "tira", "date": "2026-11-17", "label": "Strip: albumin 30 mg/l, creatinine 50 mg/dl", "nominal_uacr": 60.0},
        {"kind": "tubo", "date": "2026-11-19", "label": "Tube: 31 mg/g", "nominal_uacr": 31.4},
    ]
    assert result == step(api, JULIAN, "2026-11-20", samples[::-1])
    # Without eGFR the model assumes normal filtration, and the tube creatinine is optional.
    assert step(api, {"age": 62, "female": False, "diabetes": False}, "2026-11-16")["action"] == "tira"
    with_creatinine = [{**tube("2026-11-19", 31.4), "creatinine_mg_dl": 100}, strip("2026-11-17", 30, 50)]
    assert step(api, JULIAN, "2026-11-20", with_creatinine)["p_albuminuria"] == result["p_albuminuria"]


# --- Validation ---

VALID = {"patient": JULIAN, "today": "2026-11-17", "samples": [strip("2026-11-17", 30, 100)]}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"patient": {**JULIAN, "age": 17}}, "Age must be between 18 and 100 years."),
        ({"patient": {**JULIAN, "age": 101}}, "Age must be between 18 and 100 years."),
        ({"patient": {**JULIAN, "egfr": 3}}, "eGFR must be between 5 and 150 ml/min/1.73 m²."),
        ({"patient": {**JULIAN, "egfr": 151}}, "eGFR must be between 5 and 150 ml/min/1.73 m²."),
        (
            {"samples": [strip("2026-11-17", 27, 100)]},
            "Sample 1: the strip has no albumin level of 27 mg/l. Possible levels: 10, 30, 80 and 150 mg/l.",
        ),
        (
            {"samples": [strip("2026-11-17", 30, 100), strip("2026-11-17", 30, 75)]},
            "Sample 2: the strip has no creatinine level of 75 mg/dl. Possible levels: 10, 50, 100, 200 and 300 mg/dl.",
        ),
        (
            {"samples": [tube("2026-11-17", 0)]},
            "Sample 1: the lab result (uacr) must be greater than 0 and no more than 30000 mg/g.",
        ),
        (
            {"samples": [tube("2026-11-17", -5)]},
            "Sample 1: the lab result (uacr) must be greater than 0 and no more than 30000 mg/g.",
        ),
        (
            {"samples": [{**tube("2026-11-17", 40), "creatinine_mg_dl": 0}]},
            "Sample 1: urine creatinine must be greater than 0 and no more than 1000 mg/dl.",
        ),
        (
            {"samples": [strip("2026-11-18", 30, 100)]},
            "Sample 1 is dated November 18, 2026, after today's date (November 17, 2026).",
        ),
        ({"samples": [strip("2026-11-17", 10, 100)] * 31}, "At most 30 samples are allowed."),
        ({"episode_start": "2026-11-18"}, "The episode start (episode_start) cannot be after today's date."),
        ({"today": "1999-12-31", "samples": []}, "Today's date (today) must be between the years 2000 and 2100."),
    ],
)
def test_domain_errors_are_400_with_a_readable_message(api, change, message):
    assert rejected(api, STEP, {**VALID, **change}, 400) == message


def test_limits_are_inclusive(api):
    assert step(api, {**JULIAN, "age": 18, "egfr": 5}, "2026-11-17")["action"] == "tira"
    assert step(api, {**JULIAN, "age": 100, "egfr": 150}, "2026-11-17")["action"] == "tira"
    thirty = step(api, JULIAN, "2026-11-17", [strip("2026-11-17", 10, 100)] * 30)
    assert len(thirty["samples"]) == 30


@pytest.mark.parametrize(
    ("payload", "where"),
    [
        ({"today": "2026-11-17"}, "patient"),
        ({"patient": JULIAN}, "today"),
        ({"patient": {"age": 62, "female": False}, "today": "2026-11-17"}, "diabetes"),
        ({"patient": {**JULIAN, "age": "muchos"}, "today": "2026-11-17"}, "age"),
        ({"patient": JULIAN, "today": "17/11/2026"}, "today"),
        ({"patient": JULIAN, "today": "2026-11-17", "channel": "fax"}, "channel"),
        ({"patient": JULIAN, "today": "2026-11-17", "samples": [{"kind": "sangre", "date": "2026-11-17"}]}, "samples"),
        ({"patient": JULIAN, "today": "2026-11-17", "samples": [{"kind": "tira", "date": "2026-11-17"}]}, "albumin_mg_l"),
        ({"patient": JULIAN, "today": "2026-11-17", "samples": [{"kind": "tubo", "date": "2026-11-17"}]}, "uacr"),
        ({"patient": JULIAN, "today": "2026-11-17", "answers": {"fever": "a veces"}}, "fever"),
    ],
)
def test_malformed_requests_are_422_and_say_where(api, payload, where):
    detail = rejected(api, STEP, payload, 422)
    assert isinstance(detail, list) and detail
    assert any(where in error["loc"] for error in detail)
    assert all(error["msg"] for error in detail)


def test_not_a_number_is_rejected(api):
    """Python accepts ``NaN`` and ``Infinity`` when reading JSON: they must not reach the model."""
    headers = {"content-type": "application/json"}
    body = '{"patient": {"age": NaN, "female": true, "diabetes": false}, "today": "2026-11-16"}'
    assert api.post(STEP, content=body, headers=headers).status_code == 400
    body = (
        '{"patient": {"age": 50, "female": true, "diabetes": false}, "today": "2026-11-16", '
        '"samples": [{"kind": "tubo", "date": "2026-11-16", "uacr": Infinity}]}'
    )
    assert api.post(STEP, content=body, headers=headers).status_code == 400


# --- Determinism and warm-up ---


def test_same_request_gives_the_same_answer(api):
    payload = {
        "patient": PILAR,
        "today": "2026-11-19",
        "samples": [strip("2026-11-17", 30, 100, NO3), strip("2026-11-18", 30, 50, NO3), tube("2026-11-19", 58, NO3)],
    }
    first = post(api, STEP, payload)
    assert post(api, STEP, payload) == first  # served from the response cache
    home._STEP_CACHE.clear()
    assert post(api, STEP, payload) == first  # and recomputed with the model
    # Another request in between leaves no trace: the server is stateless.
    post(api, STEP, {**payload, "patient": MARTA})
    home._STEP_CACHE.clear()
    assert post(api, STEP, payload) == first


def test_warm_up_leaves_the_guided_scripts_computed(api, config):
    home._STEP_CACHE.clear()
    home.warm_up()
    warmed = len(home._STEP_CACHE)
    assert warmed >= 16
    by_http = {script["id"]: replay(api, config, script["id"]) for script in config["scripts"]}
    assert len(home._STEP_CACHE) == warmed  # the web app requests nothing that was not already computed
    for script in home.scripts():
        assert [s.model_dump(mode="json") for s in home._play(script)] == by_http[script.id]


# --- Blood pressure, pulse and glucose ---


def week_of_bp(sbp: float, dbp: float, days: int = 7) -> list[dict]:
    """A week of home monitoring like scripts/demo_casa.py: two in the morning and two in the evening."""
    start = date(2026, 11, 6)
    return [
        {
            "date": (start + timedelta(days=d)).isoformat(),
            "sbp": sbp + (3 if d == 0 else 0) + (2 if evening else -2),
            "dbp": dbp + (1 if evening else -1),
            "evening": evening,
        }
        for d in range(days)
        for evening in (False, False, True, True)
    ]


def test_home_blood_pressure(api):
    high = post(api, "/api/home/bp", {"readings": week_of_bp(149, 91)})
    assert set(high) == {
        "n", "days", "sbp", "dbp", "sbp_se", "dbp_se", "p_sbp_high", "p_dbp_high", "p_high", "valid", "message",
    }  # fmt: skip
    assert (high["n"], high["days"], high["sbp"], high["dbp"], high["valid"]) == (24, 6, 149.0, 91.0, True)  # without the first day
    assert high["message"] == "High blood pressure at home: average 149/91 mmHg (limit 135/85)."
    assert high["p_high"] == max(high["p_sbp_high"], high["p_dbp_high"]) >= 0.9
    assert high["sbp_se"] == pytest.approx(1.5275, abs=1e-3)

    controlled = post(api, "/api/home/bp", {"readings": week_of_bp(124, 78)})
    assert controlled["message"] == "Blood pressure controlled at home: average 124/78 mmHg."
    assert controlled["p_high"] <= 0.1

    borderline = post(api, "/api/home/bp", {"readings": week_of_bp(136, 84)})
    assert borderline["message"] == "Borderline blood pressure: average 136/84 mmHg. Repeating the week of readings is advisable."
    assert borderline["p_sbp_high"] == pytest.approx(0.7437, abs=TOL)
    assert borderline["p_high"] == borderline["p_sbp_high"] > borderline["p_dbp_high"]

    short = post(api, "/api/home/bp", {"readings": week_of_bp(149, 91, days=2)})
    assert not short["valid"]
    assert short["message"] == "Not enough readings: 4 over 1 days (not counting the first). At least 12 over 3 days are needed."


def test_home_blood_pressure_validation(api):
    assert rejected(api, "/api/home/bp", {"readings": []}, 400) == "At least one blood pressure reading is needed."
    reading = {"date": "2026-11-10", "sbp": 150, "dbp": 90}
    assert (
        rejected(api, "/api/home/bp", {"readings": [reading, {**reading, "sbp": 400}]}, 400)
        == "Reading 2: systolic must be between 60 and 300 mmHg."
    )
    assert (
        rejected(api, "/api/home/bp", {"readings": [{**reading, "dbp": 10}]}, 400)
        == "Reading 1: diastolic must be between 30 and 200 mmHg."
    )
    assert (
        rejected(api, "/api/home/bp", {"readings": [{**reading, "sbp": 80}]}, 400)
        == "Reading 1: systolic must be higher than diastolic."
    )
    assert rejected(api, "/api/home/bp", {"readings": [reading] * 201}, 400) == "At most 200 readings are allowed."
    assert rejected(api, "/api/home/bp", {}, 422)[0]["loc"] == ["body", "readings"]


def test_home_rhythm(api):
    def rhythm(*irregular: bool) -> dict:
        checks = [{"date": f"2026-11-{12 + n}", "irregular": flag} for n, flag in enumerate(irregular)]
        return post(api, "/api/home/rhythm", {"age": 77, "female": False, "checks": checks})

    nothing = rhythm()
    assert set(nothing) == {"prior", "probability", "alert", "message"}
    assert nothing["prior"] == nothing["probability"] == pytest.approx(0.0133, abs=1e-4)
    assert (nothing["alert"], nothing["message"]) == (False, None)

    one = rhythm(True)
    assert one["probability"] == pytest.approx(0.1601, abs=TOL)
    assert (one["alert"], one["message"]) == (False, None)

    two = rhythm(True, True)
    assert two["probability"] == pytest.approx(0.7290, abs=TOL)
    assert two["alert"] is True
    assert two["message"] == "Repeated irregular pulse at home (P(atrial fibrillation) = 73%)."

    assert rhythm(False)["probability"] == pytest.approx(0.0018, abs=1e-4)
    assert rhythm(True, False)["probability"] < one["probability"]

    # The starting point depends on age and sex (OFRECE study).
    woman = post(api, "/api/home/rhythm", {"age": 77, "female": True})
    assert woman["prior"] < nothing["prior"]
    assert rejected(api, "/api/home/rhythm", {"age": 17, "female": True}, 400) == "Age must be between 18 and 100 years."
    assert rejected(api, "/api/home/rhythm", {"female": True}, 422)[0]["loc"] == ["body", "age"]


def test_home_glucose(api):
    def glucose(*readings: tuple) -> dict:
        """Readings as (date, mg/dl) or (date, mg/dl, fasting hours)."""
        items = [{"date": r[0], "mg_dl": r[1], **({"fasting_hours": r[2]} if len(r) > 2 else {})} for r in readings]
        return post(api, "/api/home/glucose", {"readings": items})

    three = glucose(("2026-11-10", 134, 10), ("2026-11-12", 141, 10), ("2026-11-14", 129, 10))
    assert three == {
        "fasting_mean_mg_dl": pytest.approx(134.58, abs=0.01),
        "fasting_readings": 3,
        "days_above_126": 3,
        "alert": True,
        "message": (
            "Fasting glucose of 126 mg/dl or more on two different days, measured at home, with no diabetes on record: "
            "confirm with HbA1c."
        ),
    }

    # Two high readings on the same day are a single day: no alert.
    same_day = glucose(("2026-11-10", 134, 10), ("2026-11-10", 141, 9))
    assert (same_day["days_above_126"], same_day["alert"], same_day["message"]) == (1, False, None)

    # Without fasting there is no fasting mean and no alert; without hours the reading is assumed fasting (8 h).
    fed = glucose(("2026-11-10", 180, 2), ("2026-11-12", 175, 1.5))
    assert fed == {"fasting_mean_mg_dl": None, "fasting_readings": 0, "days_above_126": 0, "alert": False, "message": None}
    assert glucose(("2026-11-10", 126), ("2026-11-12", 126))["alert"] is True
    assert glucose(("2026-11-10", 125.9), ("2026-11-12", 126))["alert"] is False
    assert glucose() == fed

    reading = {"date": "2026-11-10", "mg_dl": 100}
    assert (
        rejected(api, "/api/home/glucose", {"readings": [{**reading, "mg_dl": 700}]}, 400)
        == "Reading 1: glucose must be between 20 and 600 mg/dl."
    )
    assert (
        rejected(api, "/api/home/glucose", {"readings": [{**reading, "fasting_hours": 30}]}, 400)
        == "Reading 1: hours since the last meal must be between 0 and 24."
    )
    assert rejected(api, "/api/home/glucose", {"readings": [{"date": "2026-11-10"}]}, 422)[0]["loc"][-1] == "mg_dl"


# --- Regressions from the adversarial review ---

RAW = {"content-type": "application/json"}


def strict_json(text: str):
    """Reads the response as the browser will: ``NaN`` and ``Infinity`` are not JSON."""

    def no_constants(name: str):
        raise AssertionError(f"The response contains {name}")

    return json.loads(text, parse_constant=no_constants)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("step", "NaN"),
        ("bp", "NaN"),
        ("rhythm", "-Infinity"),
        ("glucose", "Infinity"),
        ("step", '{"patient": {"age": NaN, "female": true}, "today": "2026-11-16"}'),
        ("step", '{"patient": {"age": 50, "female": true, "diabetes": false}, "today": NaN}'),
        ("step", '{"patient": {"age": 50, "female": true, "diabetes": false, "peso": Infinity}, "today": "ayer"}'),
        (
            "step",
            '{"patient": {"age": 50, "female": true, "diabetes": false}, "today": "2026-11-16", '
            '"samples": [{"kind": NaN, "date": "2026-11-16", "uacr": 40}]}',
        ),
        ("bp", '{"readings": [{"date": "2026-11-16", "sbp": NaN}]}'),
        ("rhythm", '{"age": Infinity}'),
        ("glucose", '{"readings": [{"date": "2026-11-16", "mg_dl": [NaN, {"x": -Infinity}]}]}'),
    ],
)
def test_nan_next_to_a_shape_error_is_a_422_not_a_500(api, path, body):
    """The 422 echoes the invalid input; with a raw NaN inside it could not be written and a 500 came out."""
    response = api.post(f"/api/home/{path}", content=body, headers=RAW)
    assert response.status_code == 422, response.text
    detail = strict_json(response.text)["detail"]
    assert isinstance(detail, list) and all(error["msg"] and error["loc"] for error in detail)


def model_sample(sample: dict, kit):
    """A request sample, as built by someone calling the model by hand."""
    context = SampleContext(**sample["answers"]) if "answers" in sample else None
    day = date.fromisoformat(sample["date"])
    if sample["kind"] == "tira":
        return StripSample(day, kit.strip, sample["albumin_mg_l"], sample["creatinine_mg_dl"], context=context)
    return UrineSample(day, sample["uacr"], FIRST_MORNING, creatinine_mg_dl=sample.get("creatinine_mg_dl"), context=context)


EQUIVALENCE_CASES = {
    # Strip read by eye at the pharmacy, answers on the samples and today, explicit episode, no eGFR.
    "farmacia": {
        "patient": {"age": 30, "female": True, "diabetes": True},
        "channel": "farmacia",
        "today": "2026-11-16",
        "episode_start": "2026-11-12",
        "answers": {"exercise_24h": True, "uti_symptoms": True},
        "samples": [
            {**tube("2026-11-13", 45.5, NO4), "creatinine_mg_dl": 180},
            strip("2026-11-10", 80, 50, {"menstruation": True, "exercise_24h": False}),
        ],
    },
    # Tube only, by mail: two very high results in a row (A3, chronicity missing).
    "correo_a3": {
        "patient": {"age": 81, "female": False, "diabetes": False, "egfr": 38},
        "channel": "correo",
        "today": "2026-11-16",
        "samples": [tube("2026-11-16", 2500), tube("2026-11-15", 1900)],
    },
    # Two tubes more than three months apart: confirmed.
    "correo_cronica": {
        "patient": {"age": 81, "female": False, "diabetes": False, "egfr": 38},
        "channel": "correo",
        "today": "2026-11-16",
        "samples": [tube("2026-11-10", 310), {**tube("2026-07-01", 220), "creatinine_mg_dl": 60}],
    },
    # eGFR at the edge of the model's range, unordered samples with two strips on the same day and
    # today months later: all fall outside the default episode window.
    "carta_antiguas": {
        "patient": {"age": 55, "female": False, "diabetes": False, "egfr": 150},
        "channel": "carta",
        "today": "2027-05-01",
        "samples": [
            strip("2026-12-01", 80, 200),
            tube("2026-11-20", 33),
            strip("2026-12-01", 30, 10),
            strip("2026-11-17", 150, 300),
        ],
    },
}


@pytest.mark.parametrize("name", list(EQUIVALENCE_CASES))
def test_step_equals_the_library_field_by_field(api, name):
    body = EQUIVALENCE_CASES[name]
    got = post(api, STEP, body)
    check_invariants(got)

    # The model, called by hand with another filter and its defaults.
    kit = KITS[Channel(body["channel"])]
    samples = sorted((model_sample(s, kit) for s in body["samples"]), key=lambda s: s.date)
    person = body["patient"]
    patient = Patient(person["age"], person["female"], person["diabetes"], person.get("egfr"), samples)
    today = date.fromisoformat(body["today"])
    options = {"episode_start": date.fromisoformat(body["episode_start"])} if "episode_start" in body else {}
    context = SampleContext(**body["answers"]) if "answers" in body else None
    want = next_step(load_default_filter("espana"), patient, kit, today, context=context, **options)
    a = want.assessment

    def iso(day):
        return None if day is None else day.isoformat()

    assert (got["action"], got["on"], got["finished"]) == (want.action, iso(want.on), want.finished)
    assert got["patient_message"] == want.patient_message
    assert got["clinician_note"] == want.clinician_note
    assert got["p_albuminuria"] == pytest.approx(want.p_albuminuria, abs=1e-6)
    assert got["resolve_probability"] == (
        None if want.resolve_probability is None else pytest.approx(want.resolve_probability, abs=1e-6)
    )
    assert got["questions"] == [{"key": key, "text": text} for key, text in want.questions]

    ga = got["assessment"]
    assert (ga["as_of"], ga["status"], ga["category"]) == (iso(a.as_of), a.status, a.category)
    assert (ga["chronicity_met"], ga["repeat_from"]) == (a.chronicity_met, iso(a.repeat_from))
    for field in ("p_a1", "p_a2", "p_a3", "median", "low", "high"):
        assert ga[field] == pytest.approx(float(getattr(a, field)), abs=1e-6), field
    assert len(ga["trajectory"]) == len(a.trajectory) == len(samples)
    for point, model_point in zip(ga["trajectory"], a.trajectory):
        assert point["date"] == iso(model_point.date)
        for field in ("median", "low", "high", "p_a2_plus"):
            assert point[field] == pytest.approx(float(getattr(model_point, field)), abs=1e-6), field

    start = options.get("episode_start", today - timedelta(days=60))
    recent = [s for s in samples if s.date >= start]
    assert got["kit"]["strips_used"] == sum(isinstance(s, StripSample) for s in recent)
    assert got["kit"]["tubes_used"] == sum(isinstance(s, UrineSample) for s in recent)
    assert [s["date"] for s in got["samples"]] == [iso(s.date) for s in samples]


def test_contradictory_samples_on_the_same_day_do_not_break_the_filter(api):
    """Thirty contradictory results: the belief does not collapse to zero nor become NaN."""
    day = "2026-11-17"
    for samples in (
        [tube(day, 30000 if n % 2 else 0.01) for n in range(30)],
        [strip(day, 150, 10)] * 15 + [tube(day, 0.01)] * 15,
        [strip(day, 10, 300)] * 15 + [tube(day, 30000)] * 15,
    ):
        response = api.post(STEP, json={"patient": JULIAN, "today": day, "samples": samples})
        assert response.status_code == 200, response.text
        result = strict_json(response.text)
        check_invariants(result)
        assert 0.0 <= result["p_albuminuria"] <= 1.0
        assert len(result["assessment"]["trajectory"]) == 30


def test_alert_thresholds_are_the_ones_of_the_model():
    """``alert`` uses two thresholds copied from ``assessment._alerts``; if the model changes them, this catches it."""
    for p in (0.0, 0.3, 0.49, 0.499999, 0.5, 0.500001, 0.73, 1.0):
        assert (home._alert_text(p_af=p) is not None) == (p >= home.AF_ALERT_PROBABILITY), p
    for days in range(5):
        readings = [home.GlucoseReading(date(2026, 11, 10 + n), 130.0, 10.0) for n in range(days)]
        assert (home._alert_text(glucose=readings) is not None) == (days >= home.GLUCOSE_ALERT_DAYS), days


def test_concurrent_requests_give_the_same_answers_as_one_by_one(api):
    """Requests share the filter and the cache; concurrently they must give the same as one by one."""
    day = "2026-11-17"
    bodies = [
        {"patient": {**patient, "age": patient["age"] + extra}, "today": day, "samples": samples, "channel": channel}
        for extra, (patient, channel) in enumerate(((JULIAN, "aplicación"), (MARTA, "carta"), (PILAR, "farmacia")))
        for samples in ([], [strip(day, 30, 100, NO3)], [strip(day, 80, 50), tube(day, 44)])
    ]

    def call(body: dict) -> tuple[int, str]:
        response = api.post(STEP, json=body)
        return response.status_code, response.text

    home._STEP_CACHE.clear()
    one_by_one = [call(body) for body in bodies]
    assert all(status == 200 for status, _ in one_by_one)
    home._STEP_CACHE.clear()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(call, bodies * 3)) == one_by_one * 3


# --- Response shape and documentation ---

INTERNAL_KEYS ={"belief", "next_sample_resolves", "log_evidence", "egfr_components", "spec", "context"}


def keys_of(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(keys_of(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(keys_of(item) for item in value))
    return set()


def test_no_response_has_nan_or_internal_keys(api, config):
    for script in config["scripts"]:
        replay(api, config, script["id"])
    post(api, "/api/home/bp", {"readings": week_of_bp(149, 91)})
    post(api, "/api/home/bp", {"readings": [{"date": "2026-11-10", "sbp": 150, "dbp": 90}]})
    post(api, "/api/home/rhythm", {"age": 77, "female": False, "checks": [{"date": "2026-11-12", "irregular": True}] * 200})
    post(api, "/api/home/glucose", {"readings": []})
    extreme = {"age": 100, "female": True, "diabetes": True, "egfr": 5}
    post(api, STEP, {"patient": extreme, "today": "2100-12-31", "samples": [tube("2000-01-01", 30000), tube("2100-12-31", 1e-4)]})
    assert len(SEEN) > 20

    for text in SEEN:
        body = strict_json(text)  # NaN, Infinity and -Infinity are not JSON
        assert not keys_of(body) & INTERNAL_KEYS
        if "assessment" in body:
            assert set(body) == {
                "action", "action_label", "on", "finished", "patient_message", "clinician_note", "p_albuminuria",
                "resolve_probability", "questions", "kit", "assessment", "samples",
            }  # fmt: skip
            assert set(body["assessment"]) == {
                "as_of", "status", "status_label", "category", "p_a1", "p_a2", "p_a3", "median", "low", "high",
                "chronicity_met", "repeat_from", "trajectory",
            }  # fmt: skip
            for point in body["assessment"]["trajectory"]:
                assert set(point) == {"date", "median", "low", "high", "p_a2_plus"}


def test_docs_describe_every_route_and_field():
    schema = app.openapi()
    assert set(schema["paths"]) == {f"/api/home/{name}" for name in ("config", "step", "bp", "rhythm", "glucose")}
    for path, methods in schema["paths"].items():
        for operation in methods.values():
            assert operation["summary"] and operation["description"], path
            assert "$ref" in operation["responses"]["200"]["content"]["application/json"]["schema"], path
    for name, component in schema["components"]["schemas"].items():
        if name in ("HTTPValidationError", "ValidationError"):  # added by FastAPI
            continue
        for field, spec in component.get("properties", {}).items():
            assert spec.get("description"), f"{name}.{field} has no description"


# --- Spanish (X-Lang: es or Accept-Language: es-*) ---

ES = {"X-Lang": "es"}


def post_es(api, path: str, payload: dict, status: int = 200):
    response = api.post(path, json=payload, headers=ES)
    assert response.status_code == status, response.text
    assert response.headers["content-language"] == "es"
    return response.json()


def test_step_in_spanish_has_the_original_texts(api):
    start = post_es(api, STEP, {"patient": JULIAN, "today": "2026-11-16"})
    assert start["action"] == "tira"  # machine values do not change
    assert start["action_label"] == "Tira en casa"
    assert start["patient_message"] == "Mañana, con la primera orina del día, haz una tira y hazle la foto con la aplicación."
    assert start["assessment"]["status_label"] == "Sin medir"

    done = post_es(api, STEP, {"patient": JULIAN, "today": "2026-11-17", "samples": [strip("2026-11-17", 10, 100, NO3)]})
    assert (done["action"], done["action_label"]) == ("fin_normal", "Fin: prueba normal")
    assert done["patient_message"] == FN_ES
    assert (done["assessment"]["status"], done["assessment"]["status_label"]) == ("descartada", "Descartada")
    assert done["samples"][0]["label"] == "Tira: albúmina 10 mg/l, creatinina 100 mg/dl"
    tube_label = post_es(api, STEP, {"patient": JULIAN, "today": "2026-11-17", "samples": [tube("2026-11-17", 31.4)]})
    assert tube_label["samples"][0]["label"] == "Tubo: 31 mg/g"

    # Same request in English: the cache keeps the two languages apart.
    english = post(api, STEP, {"patient": JULIAN, "today": "2026-11-17", "samples": [strip("2026-11-17", 10, 100, NO3)]})
    assert (english["action_label"], english["patient_message"]) == ("Done: normal test", FN)


FN_ES = "Tu prueba es normal: no hay albúmina en la orina. Te avisaremos para repetirla dentro de un año."


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"patient": {**JULIAN, "age": 17}}, "La edad tiene que estar entre 18 y 100 años."),
        ({"patient": {**JULIAN, "egfr": 3}}, "El filtrado glomerular (FG) tiene que estar entre 5 y 150 ml/min/1,73 m²."),
        (
            {"samples": [strip("2026-11-17", 27, 100)]},
            "Muestra 1: la tira no tiene el nivel de albúmina 27 mg/l. Niveles posibles: 10, 30, 80 y 150 mg/l.",
        ),
        (
            {"samples": [tube("2026-11-17", 0)]},
            "Muestra 1: el resultado del laboratorio (uacr) tiene que ser mayor que 0 y no pasar de 30000 mg/g.",
        ),
        (
            {"samples": [strip("2026-11-18", 30, 100)]},
            "La muestra 1 es del 18/11/2026, posterior a la fecha de hoy (17/11/2026).",
        ),
        ({"samples": [strip("2026-11-17", 10, 100)] * 31}, "Se admiten como mucho 30 muestras."),
        ({"episode_start": "2026-11-18"}, "El inicio del episodio (episode_start) no puede ser posterior a la fecha de hoy."),
        ({"today": "1999-12-31", "samples": []}, "La fecha de hoy (today) tiene que estar entre los años 2000 y 2100."),
        (
            {"channel": "correo", "samples": [strip("2026-11-17", 10, 100)]},
            "El canal «correo» no usa tiras: solo admite muestras de tubo.",
        ),
    ],
)
def test_domain_errors_in_spanish(api, change, message):
    assert post_es(api, STEP, {**VALID, **change}, status=400)["detail"] == message


def test_measurement_errors_in_spanish(api):
    reading = {"date": "2026-11-10", "sbp": 150, "dbp": 90}
    assert post_es(api, "/api/home/bp", {"readings": []}, 400)["detail"] == "Hace falta al menos una lectura de tensión."
    assert (
        post_es(api, "/api/home/bp", {"readings": [{**reading, "sbp": 80}]}, 400)["detail"]
        == "Lectura 1: la sistólica tiene que ser mayor que la diastólica."
    )
    assert post_es(api, "/api/home/bp", {"readings": [reading] * 201}, 400)["detail"] == "Se admiten como mucho 200 lecturas."
    assert (
        post_es(api, "/api/home/glucose", {"readings": [{"date": "2026-11-10", "mg_dl": 100, "fasting_hours": 30}]}, 400)["detail"]
        == "Lectura 1: las horas desde la última comida tienen que estar entre 0 y 24."
    )
    assert (
        post_es(api, "/api/home/rhythm", {"age": 17, "female": True}, 400)["detail"]
        == "La edad tiene que estar entre 18 y 100 años."
    )


def test_config_in_spanish(api):
    response = api.get("/api/home/config", headers=ES)
    assert response.status_code == 200 and response.headers["content-language"] == "es"
    config_es = response.json()
    assert [q["audience"] for q in config_es["questions"]] == ["todos", "todos", "mujeres menores de 56 años", "todos"]
    julian = next(p for p in config_es["patients"] if p["id"] == "julian")
    assert julian["summary"] == "62 años, sin diabetes, FG 85. Nunca se le ha mirado la albúmina en la orina."
    normal = next(s for s in config_es["scripts"] if s["id"] == "normal")
    assert normal["title"] == "Normal a la primera"
    assert normal["steps"][0]["kind"] == "respuestas"  # machine value
    assert normal["steps"][0]["note"] == "Antes de la prueba contesta que no a todas las preguntas."
    # The English config is still English (separate cache entry per language).
    english = get(api, "/api/home/config")
    assert next(s for s in english["scripts"] if s["id"] == "normal")["title"] == "Normal on the first try"
    assert [p["id"] for p in english["patients"]] == [p["id"] for p in config_es["patients"]]


def test_language_comes_from_accept_language_and_defaults_to_english(api):
    payload = {"patient": JULIAN, "today": "2026-11-16"}
    spain = api.post(STEP, json=payload, headers={"Accept-Language": "es-ES,es;q=0.9"})
    assert spain.status_code == 200 and spain.headers["content-language"] == "es"
    assert spain.json()["action_label"] == "Tira en casa"

    default = api.post(STEP, json=payload)
    assert default.status_code == 200 and default.headers["content-language"] == "en"
    assert default.json()["action_label"] == "Strip at home"

    other = api.post(STEP, json=payload, headers={"Accept-Language": "fr-FR,fr;q=0.9"})
    assert other.headers["content-language"] == "en" and other.json()["action_label"] == "Strip at home"
    # X-Lang wins over Accept-Language.
    forced = api.post(STEP, json=payload, headers={"X-Lang": "en", "Accept-Language": "es-ES"})
    assert forced.headers["content-language"] == "en" and forced.json()["action_label"] == "Strip at home"
