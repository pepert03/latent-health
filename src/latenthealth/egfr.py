"""Estimated glomerular filtration rate (eGFR)."""

import numpy as np


def ckd_epi_2021(scr_mg_dl, age, female):
    """eGFR in ml/min/1.73 m² with the CKD-EPI 2021 equation (race-free)."""
    scr = np.asarray(scr_mg_dl, dtype=float)
    age = np.asarray(age, dtype=float)
    female = np.asarray(female, dtype=bool)
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr / kappa
    return (
        142.0
        * np.minimum(ratio, 1.0) ** alpha
        * np.maximum(ratio, 1.0) ** -1.2
        * 0.9938**age
        * np.where(female, 1.012, 1.0)
    )
