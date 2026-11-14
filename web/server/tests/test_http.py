"""Comprobación de extremo a extremo por HTTP real.

Arranca el servidor como lo arranca ``web/start.ps1`` (``uv run ... uvicorn server.main:app``) en
un puerto libre, espera a que termine la precarga de los modelos y llama a todas las rutas con las
entradas que el propio servidor publica: ``/api/model/examples`` y ``/api/home/config``.

    uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests/test_http.py -q -s

Con ``-s`` se ve lo que ha tardado la precarga. No puede quedarse colgado: cada petición tiene
límite de tiempo, la espera del arranque también, y un temporizador apaga el servidor si el módulo
entero pasa de ``TOTAL_LIMIT`` segundos. El servidor se apaga siempre, pase lo que pase.
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

STARTUP_LIMIT = 300.0  # s: arranque más precarga de modelos (lo normal son unos 30 s)
REQUEST_LIMIT = 60.0  # s por petición (la más lenta medida, /assess, tarda 1,5 s)
TOTAL_LIMIT = 600.0  # s para el módulo entero; pasado ese tiempo se apaga el servidor

# Si está pytest-timeout, que corte él también; sin el complemento la marca solo daría un aviso.
if importlib.util.find_spec("pytest_timeout") is not None:
    pytestmark = pytest.mark.timeout(TOTAL_LIMIT + 60)


# --------------------------------------------------------------------------------------
# Cliente HTTP mínimo (biblioteca estándar): lo que llega por el cable, sin intermediarios
# --------------------------------------------------------------------------------------

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nunca por un proxy


def _reject_constant(name: str) -> Any:
    raise ValueError(f"El JSON trae {name}, que no es JSON estricto.")


def strict_json(raw: bytes) -> Any:
    """Lee JSON como lo lee un navegador: NaN, Infinity y -Infinity son un error."""
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
    seconds_to_listen: float  # del arranque del proceso al primer /api/health
    seconds_to_ready: float  # del arranque del proceso a models_ready

    def call(self, path: str, body: Any = None) -> Reply:
        """GET si no hay cuerpo; POST con JSON si lo hay. Un 4xx o 5xx se devuelve, no se lanza."""
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
        """Llama y exige 200 con JSON estricto; devuelve el JSON."""
        reply = self.call(path, body)
        assert reply.status == 200, f"{path} -> {reply.status}: {reply.raw[:400]!r}"
        assert reply.content_type.startswith("application/json"), f"{path}: {reply.content_type}"
        return reply.json()


# --------------------------------------------------------------------------------------
# Arranque y apagado del servidor
# --------------------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Apaga el servidor y sus hijos (``uv run`` lanza uvicorn en un proceso hijo). Se puede repetir."""
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
        return "(sin registro)"


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv no está en el PATH: no se puede arrancar el servidor como en la demo.")

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("servidor") / "uvicorn.log"

    env = dict(os.environ)
    # El entorno del servidor lo decide uv desde la raíz, no el que ejecuta estos tests.
    env.pop("VIRTUAL_ENV", None)
    # Los tests no llaman a ningún modelo de lenguaje: sin credenciales y con la API apuntando a
    # un puerto cerrado de esta máquina, el asistente contesta siempre en modo guiado.
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
        atexit.register(_stop, process)  # por si pytest muere sin pasar por el finally
        watchdog = threading.Timer(TOTAL_LIMIT, _stop, args=(process,))
        watchdog.daemon = True
        watchdog.start()
        try:
            probe = Server(base, 0.0, 0.0)
            listening: float | None = None
            while True:
                elapsed = time.monotonic() - started
                if process.poll() is not None:
                    pytest.fail(f"El servidor terminó solo (código {process.returncode}):\n{_tail(log_path)}")
                if elapsed > STARTUP_LIMIT:
                    pytest.fail(f"El servidor no estuvo listo en {STARTUP_LIMIT:.0f} s:\n{_tail(log_path)}")
                try:
                    reply = probe.call("/api/health")
                except (urllib.error.URLError, OSError):
                    time.sleep(0.25)  # todavía no escucha
                    continue
                assert reply.status == 200, f"/api/health -> {reply.status}"
                if listening is None:
                    listening = time.monotonic() - started
                if reply.json()["models_ready"] is True:
                    break
                time.sleep(0.25)
            ready = time.monotonic() - started
            print(
                f"\n[test_http] servidor en {base}: escucha a los {listening:.1f} s, "
                f"modelos precargados a los {ready:.1f} s"
            )
            yield Server(base, listening, ready)
        finally:
            watchdog.cancel()
            _stop(process)
            atexit.unregister(_stop)


# --------------------------------------------------------------------------------------
# Estado, documentación y sitio
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
    # Si aparece una ruta nueva, este test avisa de que falta llamarla aquí (y tiparla en la web).
    assert paths == EXPECTED_PATHS
    docs = server.call("/api/docs")
    assert docs.status == 200 and docs.content_type.startswith("text/html")


def test_site_is_served_from_the_same_port(server: Server):
    if not server.ok("/api/health")["site_built"]:
        pytest.skip("No hay sitio que servir (falta web/site/index.html).")
    page = server.call("/")
    assert page.status == 200 and page.content_type.startswith("text/html")
    assert b"<html" in page.raw.lower()


def test_unknown_api_route_is_a_json_404(server: Server):
    reply = server.call("/api/no-existe")
    assert reply.status == 404 and reply.content_type.startswith("application/json")
    assert "detail" in reply.json()


# --------------------------------------------------------------------------------------
# Modelo en vivo: todas las entradas de /api/model/examples
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
        # La evaluación completa y el filtro suelto ven las mismas muestras: mismo estado.
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


def test_model_domain_error_is_a_400_in_spanish(server: Server):
    body = dict(server.ok("/api/model/examples")["patients"][0]["albuminuria"])
    body["samples"] = [{"kind": "laboratorio", "date": "2026-11-10", "uacr": 45, "sample_type": "first_morning"}]
    body["as_of"] = "2026-11-01"  # anterior a la muestra
    reply = server.call("/api/model/albuminuria", body)
    assert reply.status == 400, reply.raw[:300]
    detail = reply.json()["detail"]
    assert isinstance(detail, str) and detail.strip()

    malformed = server.call("/api/model/albuminuria", {"as_of": "2026-11-14"})  # falta el paciente
    assert malformed.status == 422
    assert isinstance(malformed.json()["detail"], list)


# --------------------------------------------------------------------------------------
# En casa: todo lo que publica /api/home/config
# --------------------------------------------------------------------------------------


def _patient_body(preset: dict[str, Any]) -> dict[str, Any]:
    return {key: preset[key] for key in ("age", "female", "diabetes", "egfr")}


def _play(server: Server, config: dict[str, Any], script: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reproduce un recorrido guiado contra /step como lo hace la web (ver la ruta /config).

    Devuelve las respuestas y el último cuerpo enviado.
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
            for name in (channel["value"], channel["key"]):  # el canal vale por su nombre o por su clave
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
        assert last["finished"] is True, f"{script['id']}: termina en «{last['action']}»"
        assert last["patient_message"] and last["clinician_note"]
        samples = [item for item in script["steps"] if item["kind"] != "respuestas"]
        assert len(last["samples"]) == len(last["assessment"]["trajectory"]) == len(samples), script["id"]
        dates = [dt.date.fromisoformat(step["on"]) for step in seen]
        assert dates == sorted(dates), f"{script['id']}: las fechas retroceden"


def test_home_measurements_at_home(server: Server):
    config = server.ok("/api/home/config")
    start = dt.date.fromisoformat(config["today"])
    days = [(start + dt.timedelta(days=offset)).isoformat() for offset in range(7)]

    readings = [{"date": day, "sbp": 142 + i, "dbp": 88, "evening": evening} for i, day in enumerate(days) for evening in (False, True)]
    bp = server.ok("/api/home/bp", {"readings": readings})
    assert bp["days"] == 6 and bp["n"] == 12 and bp["valid"] is True  # se descarta el primer día
    assert 0.0 <= bp["p_high"] <= 1.0 and bp["message"]

    for preset in config["patients"]:
        who = {"age": preset["age"], "female": preset["female"]}
        # Dos pulsos irregulares suben la probabilidad; una semana de pulsos regulares la baja.
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
    body["messages"] = [{"role": "user", "content": "¿Cuándo me toca la próxima prueba?"}]
    chat = server.ok("/api/home/chat", body)
    # El servidor de este test no tiene credenciales ni salida a la API: contesta con frases fijas.
    assert chat["mode"] == "guiado" and chat["model"] is None
    assert chat["reply"].strip()


def test_home_domain_error_is_a_400_in_spanish(server: Server):
    config = server.ok("/api/home/config")
    patient = _patient_body(config["patients"][0])
    late = {"kind": "tubo", "date": "2026-12-01", "uacr": 40}  # posterior a «hoy»
    reply = server.call("/api/home/step", {"patient": patient, "today": config["today"], "samples": [late]})
    assert reply.status == 400, reply.raw[:300]
    assert isinstance(reply.json()["detail"], str)

    malformed = server.call("/api/home/step", {"today": config["today"]})  # falta el paciente
    assert malformed.status == 422
    assert isinstance(malformed.json()["detail"], list)
