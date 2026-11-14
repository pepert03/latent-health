from server.serialize import clean


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "models_ready", "site_built"}


def test_unknown_api_route_is_json_404(client):
    response = client.get("/api/no-existe")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_openapi_lists_the_routers(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/health" in paths


def test_clean_handles_model_types():
    from dataclasses import dataclass
    from datetime import date

    import numpy as np

    @dataclass
    class Point:
        day: date
        value: np.float64
        belief: np.ndarray

    out = clean(
        {"p": Point(date(2026, 11, 16), np.float64(1.23456), np.ones(3)), "nan": float("nan"), "ok": np.bool_(True)},
        exclude=frozenset({"belief"}),
        digits=2,
    )
    assert out == {"p": {"day": "2026-11-16", "value": 1.23}, "nan": None, "ok": True}
