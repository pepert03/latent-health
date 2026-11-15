"""CORS for the GitHub Pages build: the site lives on another origin and calls this API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from server.main import cors_origins

WEB_DIR = Path(__file__).resolve().parents[2]

PROBE = """
import json
from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)  # no context manager: the models are not warmed up
pre = client.options("/api/health", headers={
    "Origin": "https://pepert03.github.io",
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type,x-lang",
})
ok = client.get("/api/health", headers={"Origin": "https://pepert03.github.io"})
bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
print(json.dumps({
    "pre_status": pre.status_code,
    "pre_origin": pre.headers.get("access-control-allow-origin"),
    "pre_headers": pre.headers.get("access-control-allow-headers", "").lower(),
    "pre_methods": pre.headers.get("access-control-allow-methods", ""),
    "ok_origin": ok.headers.get("access-control-allow-origin"),
    "bad_origin": bad.headers.get("access-control-allow-origin"),
}))
"""


def _probe(origins: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "CORS_ORIGINS"}
    if origins is not None:
        env["CORS_ORIGINS"] = origins
    out = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=WEB_DIR, env=env, capture_output=True, text=True, timeout=300, check=True
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_cors_origins_parsing():
    assert cors_origins("") == []
    assert cors_origins(" https://a.io/ , https://b.io,,") == ["https://a.io", "https://b.io"]


def test_cors_allows_configured_origin_only():
    r = _probe("https://pepert03.github.io, http://127.0.0.1:8765")
    assert r["pre_status"] == 200
    assert r["pre_origin"] == "https://pepert03.github.io"
    assert "x-lang" in r["pre_headers"] and "content-type" in r["pre_headers"]
    assert "POST" in r["pre_methods"] and "GET" in r["pre_methods"]
    assert r["ok_origin"] == "https://pepert03.github.io"
    assert r["bad_origin"] is None


def test_no_cors_by_default():
    r = _probe(None)
    assert r["ok_origin"] is None
    assert r["pre_origin"] is None
