"""Rutas de la app del paciente: protocolo de orina en casa y otras medidas (tensión, pulso, glucosa)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/home", tags=["En casa (app del paciente)"])


def warm_up() -> None:
    """Carga lo que haga falta para que la primera petición sea rápida."""
