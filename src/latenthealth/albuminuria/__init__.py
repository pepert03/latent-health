"""Filtro bayesiano de la albuminuria (UACR)."""

from pathlib import Path

from .context import SampleContext
from .filter import AlbuminuriaAssessment, AlbuminuriaFilter, Patient, UrineSample, describe
from .model import FIRST_MORNING, RANDOM, AlbuminuriaParams
from .protocol import KITS, Channel, HomeKit, Step, choose_channel, next_step
from .strip import (
    EYE_STRIP,
    PHONE_STRIP,
    RATIO_STRIP,
    SHARP_VISION_STRIP,
    VISION_STRIP,
    StripSample,
    StripSpec,
    fit_strip_spec,
)

DEFAULT_PARAMS_PATH = Path(__file__).resolve().parents[3] / "models" / "albuminuria_params.json"
# Mismos parámetros con el prior recalibrado a atención primaria española (scripts/fit_recalibration.py).
SPAIN_PARAMS_PATH = DEFAULT_PARAMS_PATH.with_name("albuminuria_params_espana.json")


def params_path(population: str = "nhanes") -> Path:
    """Fichero de parámetros de una población: ``"nhanes"`` (ajuste original) o ``"espana"``."""
    if population == "espana" and SPAIN_PARAMS_PATH.exists():
        return SPAIN_PARAMS_PATH
    return DEFAULT_PARAMS_PATH


def load_default_filter(population: str = "nhanes", **kwargs) -> AlbuminuriaFilter:
    """Filtro con los parámetros ajustados en NHANES (``models/albuminuria_params.json``).

    Con ``population="espana"`` usa el prior recalibrado, si existe.
    """
    return AlbuminuriaFilter(AlbuminuriaParams.load(params_path(population)), **kwargs)


__all__ = [
    "AlbuminuriaAssessment",
    "AlbuminuriaFilter",
    "AlbuminuriaParams",
    "Channel",
    "EYE_STRIP",
    "FIRST_MORNING",
    "HomeKit",
    "KITS",
    "PHONE_STRIP",
    "Patient",
    "RANDOM",
    "RATIO_STRIP",
    "SHARP_VISION_STRIP",
    "SampleContext",
    "Step",
    "StripSample",
    "StripSpec",
    "UrineSample",
    "VISION_STRIP",
    "choose_channel",
    "describe",
    "fit_strip_spec",
    "load_default_filter",
    "next_step",
    "params_path",
]
