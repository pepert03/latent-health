"""Tests de contrato del servidor local.

    uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests -q

Se ejecutan desde la raíz del repositorio. Usan los modelos reales: no hay dobles.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WEB_DIR = Path(__file__).resolve().parents[2]
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as test_client:
        yield test_client
