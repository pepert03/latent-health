"""Rutas del modelo en vivo: filtro de albuminuria, tendencia del filtrado y evaluación de un paciente."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/model", tags=["Modelo en vivo"])


def warm_up() -> None:
    """Carga lo que haga falta para que la primera petición sea rápida."""
