"""Modelo de riesgo con desenlaces reales: NHANES enlazado con mortalidad."""

from .data import (
    BLOCKS,
    CAUSES,
    CV_CYCLES,
    FULL_10Y_CYCLES,
    HOME_TIER,
    TIERS,
    add_strip,
    complete_home,
    event_within,
    load_cohort,
    mask_blocks,
)

__all__ = [
    "BLOCKS",
    "CAUSES",
    "CV_CYCLES",
    "FULL_10Y_CYCLES",
    "HOME_TIER",
    "TIERS",
    "add_strip",
    "complete_home",
    "event_within",
    "load_cohort",
    "mask_blocks",
]
