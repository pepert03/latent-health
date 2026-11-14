"""NHANES 2009-2010: albúmina y creatinina en dos muestras de orina por persona.

La muestra 1 es aleatoria (se recoge en el centro de examen) y la muestra 2 es la
primera orina de la mañana (se recoge en casa unos días después).
"""

from pathlib import Path

import numpy as np
import pandas as pd

from .egfr import ckd_epi_2021

FILES = ("ALB_CR_F", "DEMO_F", "BIOPRO_F", "GHB_F")
BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2009/DataFiles/{name}.xpt"
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "nhanes" / "2009-2010"

# Límite de detección de la albúmina en orina. NHANES rellena los valores por debajo
# con LOD/√2 = 0,21 mg/l.
ALBUMIN_LOD_MG_L = 0.3
_FILL_MAX = 0.22


def read_xpt(name: str, directory: Path = DEFAULT_DIR) -> pd.DataFrame:
    return pd.read_sas(Path(directory) / f"{name}.xpt", format="xport", encoding="latin-1")


def _uacr(albumin_mg_l, ucr_mg_dl):
    """UACR (mg/g) y si está censurado: con la albúmina bajo el límite solo se sabe que es menor."""
    censored = albumin_mg_l <= _FILL_MAX
    albumin = np.where(censored, ALBUMIN_LOD_MG_L, albumin_mg_l)
    return 100.0 * albumin / ucr_mg_dl, censored


def load_pairs(directory: Path = DEFAULT_DIR) -> pd.DataFrame:
    """Una fila por adulto (≥20 años, sin embarazo) con covariables y sus muestras de orina.

    Columnas: seqn, age, female, diabetes, egfr, hba1c y, para cada muestra
    (``random`` y ``morning``): ``uacr_*`` (mg/g; si está censurado es el límite
    superior), ``censored_*`` y ``ucr_*`` (creatinina en orina, mg/dl).
    La diabetes se define por laboratorio (HbA1c ≥ 6,5 %), sin cuestionario.
    """
    demo = read_xpt("DEMO_F", directory)[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"]]
    alb = read_xpt("ALB_CR_F", directory)
    bio = read_xpt("BIOPRO_F", directory)[["SEQN", "LBXSCR"]]
    ghb = read_xpt("GHB_F", directory)[["SEQN", "LBXGH"]]
    df = demo.merge(alb, on="SEQN").merge(bio, on="SEQN", how="left").merge(ghb, on="SEQN", how="left")
    df = df[(df.RIDAGEYR >= 20) & (df.RIDEXPRG != 1)]

    out = pd.DataFrame(
        {
            "seqn": df.SEQN.astype(int).to_numpy(),
            "age": df.RIDAGEYR.to_numpy(float),
            "female": (df.RIAGENDR == 2).to_numpy(),
            "hba1c": df.LBXGH.to_numpy(float),
        }
    )
    out["diabetes"] = out.hba1c >= 6.5
    out["egfr"] = ckd_epi_2021(df.LBXSCR.to_numpy(float), out.age, out.female)
    for tag, alb_col, ucr_col in (("random", "URXUMA", "URXUCR"), ("morning", "URXUMA2", "URXUCR2")):
        albumin = df[alb_col].to_numpy(float)
        ucr = df[ucr_col].to_numpy(float)
        uacr, censored = _uacr(albumin, ucr)
        out[f"uacr_{tag}"] = uacr
        out[f"censored_{tag}"] = censored & ~np.isnan(albumin)
        out[f"ucr_{tag}"] = ucr
    has_sample = out.uacr_random.notna() | out.uacr_morning.notna()
    complete = out.egfr.notna() & out.hba1c.notna()
    return out[has_sample & complete].reset_index(drop=True)


def is_test(seqn) -> np.ndarray:
    """Partición fija y reproducible: el 20 % de las personas (seqn múltiplo de 5) es de test."""
    return np.asarray(seqn) % 5 == 0
