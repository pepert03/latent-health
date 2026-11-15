"""End-to-end check over real HTTP.

Starts the server the way ``web/start.ps1`` does (``uv run ... uvicorn server.main:app``) on a
free port, waits for the models to warm up and calls every route with the inputs the server
itself publishes: ``/api/model/examples`` and ``/api/home/config``.

    uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests/test_http.py -q -s

With ``-s`` you see how long the warm-up took. It cannot hang: each request has a time limit,
so does the startup wait, and a timer shuts the server down if the whole module exceeds
``TOTAL_LIMIT`` seconds. The server is always shut down, whatever happens.
"""

from __future__ import annotations

import atexit
import datetime as dt
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_DIR = Path(__file__).resolve().parents[3]

STARTUP_LIMIT = 300.0  # s: startup plus model warm-up (usually about 30 s)
REQUEST_LIMIT = 60.0  # s per request (the slowest measured, /assess, takes 1.5 s)
TOTAL_LIMIT = 600.0  # s for the whole module; after that the server is shut down

# If pytest-timeout is installed, let it cut too; without the plugin the mark would only warn.
if importlib.util.find_spec("pytest_timeout") is not None:
    pytestmark = pytest.mark.timeout(TOTAL_LIMIT + 60)


# --------------------------------------------------------------------------------------
# Minimal HTTP client (standard library): what comes over the wire, with no middlemen
# --------------------------------------------------------------------------------------

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a proxy


def _reject_constant(name: str) -> Any:
    raise ValueError(f"The JSON contains {name}, which is not strict JSON.")


def strict_json(raw: bytes) -> Any:
    """Reads JSON as a browser does: NaN, Infinity and -Infinity are an error."""
    return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)


@dataclass(frozen=True)
class Reply:
    status: int
    content_type: str
    raw: bytes

    def json(self) -> Any:
        return strict_json(self.raw)


@dataclass(frozen=True)
class Server:
    base: str
    seconds_to_listen: float  # from process start to the first /api/health
    seconds_to_ready: float  # from process start to models_ready

    def call(self, path: str, body: Any = None) -> Reply:
        """GET without a body; POST with JSON if there is one. A 4xx or 5xx is returned, not raised."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers={} if data is None else {"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        try:
            with _OPENER.open(request, timeout=REQUEST_LIMIT) as response:
                return Reply(response.status, response.headers.get("content-type", ""), response.read())
        except urllib.error.HTTPError as error:
            return Reply(error.code, error.headers.get("content-type", ""), error.read())

    def ok(self, path: str, body: Any = None) -> Any:
        """Calls and requires a 200 with strict JSON; returns the JSON."""
        reply = self.call(path, body)
        assert reply.status == 200, f"{path} -> {reply.status}: {reply.raw[:400]!r}"
        assert reply.content_type.startswith("application/json"), f"{path}: {reply.content_type}"
        return reply.json()


# --------------------------------------------------------------------------------------
# Server startup and shutdown
# --------------------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Shuts down the server and its children (``uv run`` starts uvicorn in a child process). Idempotent."""
    if process.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30, check=False
                )
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (OSError, subprocess.SubprocessError):
            process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def _tail(path: Path, lines: int = 30) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not on the PATH: cannot start the server as in the demo.")

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("server") / "uvicorn.log"

    env = dict(os.environ)
    # uv decides the server's environment from the root, not the one running these tests.
    env.pop("VIRTUAL_ENV", None)
    # The tests call no language model: with no credentials and the API pointing to a closed
    # port on this machine, the assistant always answers in guided mode.
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(name, None)
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:9"

    command = [
        uv, "run", "--with-requirements", "web/server/requirements.txt",
        "uvicorn", "server.main:app", "--app-dir", "web", "--host", "127.0.0.1", "--port", str(port),
    ]  # fmt: skip
    group: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    )
    with log_path.open("wb") as log:
        started = time.monotonic()
        process = subprocess.Popen(
            command, cwd=REPO_DIR, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **group
        )
        atexit.register(_stop, process)  # in case pytest dies without reaching the finally
        watchdog = threading.Timer(TOTAL_LIMIT, _stop, args=(process,))
        watchdog.daemon = True
        watchdog.start()
        try:
            probe = Server(base, 0.0, 0.0)
            listening: float | None = None
            while True:
                elapsed = time.monotonic() - started
                if process.poll() is not None:
                    pytest.fail(f"The server exited on its own (code {process.returncode}):\n{_tail(log_path)}")
                if elapsed > STARTUP_LIMIT:
                    pytest.fail(f"The server was not ready within {STARTUP_LIMIT:.0f} s:\n{_tail(log_path)}")
                try:
                    reply = probe.call("/api/health")
                except (urllib.error.URLError, OSError):
                    time.sleep(0.25)  # not listening yet
                    continue
                assert reply.status == 200, f"/api/health -> {reply.status}"
                if listening is None:
                    listening = time.monotonic() - started
                if reply.json()["models_ready"] is True:
                    break
                time.sleep(0.25)
            ready = time.monotonic() - started
            print(
                f"\n[test_http] server at {base}: listening after {listening:.1f} s, "
                f"models warmed up after {ready:.1f} s"
            )
            yield Server(base, listening, ready)
        finally:
            watchdog.cancel()
            _stop(process)
            atexit.unregister(_stop)


# --------------------------------------------------------------------------------------
# Status, docs and site
# --------------------------------------------------------------------------------------

EXPECTED_PATHS = {
    "/api/health",
    "/api/home/config",
    "/api/home/step",
    "/api/home/bp",
    "/api/home/rhythm",
    "/api/home/glucose",
    "/api/home/chat",
    "/api/model/albuminuria",
    "/api/model/egfr-trend",
    "/api/model/assess",
    "/api/model/examples",
}


def test_health_reports_models_ready(server: Server):
    body = server.ok("/api/health")
    assert body["status"] == "ok" and body["models_ready"] is True
    assert server.seconds_to_ready < STARTUP_LIMIT


def test_openapi_lists_every_route_and_docs_are_served(server: Server):
    paths = set(server.ok("/api/openapi.json")["paths"])
    # If a new route appears, this test flags that it must be called here (and typed in the web app).
    assert paths == EXPECTED_PATHS
    docs = server.call("/api/docs")
    assert docs.status == 200 and docs.content_type.startswith("text/html")


def test_site_is_served_from_the_same_port(server: Server):
    if not server.ok("/api/health")["site_built"]:
        pytest.skip("No site to serve (web/site/index.html is missing).")
    page = server.call("/")
    assert page.status == 200 and page.content_type.startswith("text/html")
    assert b"<html" in page.raw.lower()


def test_unknown_api_route_is_a_json_404(server: Server):
    reply = server.call("/api/no-existe")
    assert reply.status == 404 and reply.content_type.startswith("application/json")
    assert "detail" in reply.json()


# --------------------------------------------------------------------------------------
# Live model: every input in /api/model/examples
# --------------------------------------------------------------------------------------


def test_model_examples_run_on_every_model_route(server: Server):
    examples = server.ok("/api/model/examples")
    assert len(examples["patients"]) == 5 and len(examples["egfr_trends"]) == 2

    for patient in examples["patients"]:
        albuminuria = server.ok("/api/model/albuminuria", patient["albuminuria"])
        assert albuminuria["as_of"] == examples["as_of"], patient["id"]
        assert len(albuminuria["belief"]["mass"]) == len(albuminuria["belief"]["uacr"]) > 0
        assert len(albuminuria["trajectory"]) == len(albuminuria["samples"]) == len(patient["albuminuria"].get("samples", []))

        assess = server.ok("/api/model/assess", patient["assess"])
        # The full assessment and the standalone filter see the same samples: same status.
        assert assess["albuminuria"]["status"] == albuminuria["status"], patient["id"]
        assert len(assess["kdigo_joint"]) == 6 and all(len(row["cells"]) == 3 for row in assess["kdigo_joint"])
        total = sum(cell["p"] for row in assess["kdigo_joint"] for cell in row["cells"])
        assert abs(total - 1.0) < 1e-6, patient["id"]

    for trend in examples["egfr_trends"]:
        result = server.ok("/api/model/egfr-trend", trend["egfr_trend"])
        assert result["n"] == len(trend["egfr_trend"]["measurements"]), trend["id"]
        assert [point["years"] for point in result["projection"]] == [1, 2, 3, 5]
    statuses = {t["id"]: server.ok("/api/model/egfr-trend", t["egfr_trend"])["status"] for t in examples["egfr_trends"]}
    assert statuses == {"descenso_rapido": "descenso_rapido", "estable": "estable"}


def test_model_routes_are_deterministic_over_http(server: Server):
    patient = server.ok("/api/model/examples")["patients"][0]
    for path, body in (("/api/model/albuminuria", patient["albuminuria"]), ("/api/model/assess", patient["assess"])):
        first, second = server.call(path, body), server.call(path, body)
        assert first.status == second.status == 200
        assert first.raw == second.raw, path


def test_model_domain_error_is_a_400_with_a_message(server: Server):
    body = dict(server.ok("/api/model/examples")["patients"][0]["albuminuria"])
    body["samples"] = [{"kind": "laboratorio", "date": "2026-11-10", "uacr": 45, "sample_type": "first_morning"}]
    body["as_of"] = "2026-11-01"  # before the sample
    reply = server.call("/api/model/albuminuria", body)
    assert reply.status == 400, reply.raw[:300]
    detail = reply.json()["detail"]
    assert isinstance(detail, str) and detail.strip()

    malformed = server.call("/api/model/albuminuria", {"as_of": "2026-11-14"})  # the patient is missing
    assert malformed.status == 422
    assert isinstance(malformed.json()["detail"], list)


# --------------------------------------------------------------------------------------
# At home: everything /api/home/config publishes
# --------------------------------------------------------------------------------------


def _patient_body(preset: dict[str, Any]) -> dict[str, Any]:
    return {key: preset[key] for key in ("age", "female", "diabetes", "egfr")}


def _play(server: Server, config: dict[str, Any], script: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replays a guided walkthrough against /step as the web app does (see the /config route).

    Returns the responses and the last body sent.
    """
    preset = next(p for p in config["patients"] if p["id"] == script["patient_id"])
    body: dict[str, Any] = {
        "patient": _patient_body(preset),
        "channel": preset["channel"],
        "today": config["today"],
        "samples": [],
    }
    seen = [server.ok("/api/home/step", body)]
    for item in script["steps"]:
        if item["kind"] == "respuestas":
            seen.append(server.ok("/api/home/step", {**body, "answers": item["answers"]}))
            if seen[-1]["action"] == "esperar":
                body["today"] = seen[-1]["on"]
                seen.append(server.ok("/api/home/step", body))
            continue
        body["today"] = seen[-1]["on"]
        sample: dict[str, Any] = {"kind": item["kind"], "date": body["today"], "answers": item["answers"]}
        if item["kind"] == "tira":
            sample |= {"albumin_mg_l": item["albumin_mg_l"], "creatinine_mg_dl": item["creatinine_mg_dl"]}
        else:
            sample["uacr"] = item["uacr"]
        body["samples"] = [*body["samples"], sample]
        seen.append(server.ok("/api/home/step", body))
    return seen, body


def test_home_config_has_what_the_app_needs(server: Server):
    config = server.ok("/api/home/config")
    dt.date.fromisoformat(config["today"])
    assert config["channels"] and config["questions"] and config["patients"] and config["scripts"]
    assert config["strip"]["albumin_levels_mg_l"] and config["strip"]["creatinine_levels_mg_dl"]
    patient_ids = {p["id"] for p in config["patients"]}
    assert {s["patient_id"] for s in config["scripts"]} <= patient_ids


def test_home_step_works_for_every_patient_and_channel(server: Server):
    config = server.ok("/api/home/config")
    for preset in config["patients"]:
        for channel in config["channels"]:
            for name in (channel["value"], channel["key"]):  # the channel works by its name or its key
                body = {"patient": _patient_body(preset), "channel": name, "today": config["today"], "samples": []}
                step = server.ok("/api/home/step", body)
                assert step["kit"]["channel"] == channel["value"], (preset["id"], name)
                assert step["kit"]["strips_total"] == channel["strips"] and step["kit"]["tubes_total"] == channel["tubes"]
                assert step["assessment"]["status"] == "sin_medir" and step["samples"] == []


def test_home_scripts_play_to_the_end(server: Server):
    config = server.ok("/api/home/config")
    for script in config["scripts"]:
        seen, _ = _play(server, config, script)
        last = seen[-1]
        assert last["finished"] is True, f"{script['id']}: ends at \"{last['action']}\""
        assert last["patient_message"] and last["clinician_note"]
        samples = [item for item in script["steps"] if item["kind"] != "respuestas"]
        assert len(last["samples"]) == len(last["assessment"]["trajectory"]) == len(samples), script["id"]
        dates = [dt.date.fromisoformat(step["on"]) for step in seen]
        assert dates == sorted(dates), f"{script['id']}: dates go backwards"


def test_home_measurements_at_home(server: Server):
    config = server.ok("/api/home/config")
    start = dt.date.fromisoformat(config["today"])
    days = [(start + dt.timedelta(days=offset)).isoformat() for offset in range(7)]

    readings = [{"date": day, "sbp": 142 + i, "dbp": 88, "evening": evening} for i, day in enumerate(days) for evening in (False, True)]
    bp = server.ok("/api/home/bp", {"readings": readings})
    assert bp["days"] == 6 and bp["n"] == 12 and bp["valid"] is True  # the first day is discarded
    assert 0.0 <= bp["p_high"] <= 1.0 and bp["message"]

    for preset in config["patients"]:
        who = {"age": preset["age"], "female": preset["female"]}
        # Two irregular pulses raise the probability; a week of regular pulses lowers it.
        irregular = server.ok("/api/home/rhythm", {**who, "checks": [{"date": day, "irregular": True} for day in days[:2]]})
        regular = server.ok("/api/home/rhythm", {**who, "checks": [{"date": day, "irregular": False} for day in days]})
        nothing = server.ok("/api/home/rhythm", who)
        assert 0.0 <= regular["probability"] < nothing["probability"] < irregular["probability"] <= 1.0, preset["id"]
        assert nothing["probability"] == nothing["prior"] == irregular["prior"], preset["id"]
        for rhythm in (irregular, regular, nothing):
            assert (rhythm["message"] is not None) == rhythm["alert"], preset["id"]

    glucose = server.ok("/api/home/glucose", {"readings": [{"date": day, "mg_dl": 131, "fasting_hours": 9} for day in days[:3]]})
    assert glucose["fasting_readings"] == 3 and glucose["days_above_126"] == 3
    assert glucose["alert"] is True and glucose["message"]
    empty = server.ok("/api/home/glucose", {})
    assert empty["fasting_mean_mg_dl"] is None and empty["alert"] is False and empty["message"] is None


def test_home_chat_answers_in_guided_mode(server: Server):
    config = server.ok("/api/home/config")
    script = config["scripts"][0]
    _, body = _play(server, config, script)
    body["messages"] = [{"role": "user", "content": "When is my next test due?"}]
    chat = server.ok("/api/home/chat", body)
    # This test's server has no credentials and no API access: it answers with fixed sentences.
    assert chat["mode"] == "guiado" and chat["model"] is None
    assert chat["reply"].strip()


def test_home_domain_error_is_a_400_with_a_message(server: Server):
    config = server.ok("/api/home/config")
    patient = _patient_body(config["patients"][0])
    late = {"kind": "tubo", "date": "2026-12-01", "uacr": 40}  # after "today"
    reply = server.call("/api/home/step", {"patient": patient, "today": config["today"], "samples": [late]})
    assert reply.status == 400, reply.raw[:300]
    assert isinstance(reply.json()["detail"], str)

    malformed = server.call("/api/home/step", {"today": config["today"]})  # the patient is missing
    assert malformed.status == 422
    assert isinstance(malformed.json()["detail"], list)
