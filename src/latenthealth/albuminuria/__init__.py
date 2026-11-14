"""Filtro bayesiano de la albuminuria (UACR)."""

from pathlib import Path

from .filter import AlbuminuriaAssessment, AlbuminuriaFilter, Patient, UrineSample, describe
from .model import FIRST_MORNING, RANDOM, AlbuminuriaParams

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[3] / "models" / "albuminuria_params.json"


def load_default_filter(**kwargs) -> AlbuminuriaFilter:
    """Filtro con los parámetros ajustados en NHANES (``models/albuminuria_params.json``)."""
    return AlbuminuriaFilter(AlbuminuriaParams.load(DEFAULT_PARAMS_PATH), **kwargs)


__all__ = [
    "AlbuminuriaAssessment",
    "AlbuminuriaFilter",
    "AlbuminuriaParams",
    "FIRST_MORNING",
    "Patient",
    "RANDOM",
    "UrineSample",
    "describe",
    "load_default_filter",
]
