"""Bayesian filter for albuminuria (UACR)."""

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
# Same parameters with the prior recalibrated to Spanish primary care (scripts/fit_recalibration.py).
SPAIN_PARAMS_PATH = DEFAULT_PARAMS_PATH.with_name("albuminuria_params_espana.json")


def params_path(population: str = "nhanes") -> Path:
    """Parameter file for a population: ``"nhanes"`` (original fit) or ``"espana"`` (Spain)."""
    if population == "espana" and SPAIN_PARAMS_PATH.exists():
        return SPAIN_PARAMS_PATH
    return DEFAULT_PARAMS_PATH


def load_default_filter(population: str = "nhanes", **kwargs) -> AlbuminuriaFilter:
    """Filter with the parameters fitted on NHANES (``models/albuminuria_params.json``).

    With ``population="espana"`` it uses the recalibrated prior, if available.
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
