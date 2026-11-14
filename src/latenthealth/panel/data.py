"""Datos de NHANES 2009-2010 para el panel virtual: historia clínica, orina y analítica de sangre.

Predictores (lo que se tiene sin sacar sangre):
- Historia clínica: edad, sexo, IMC, cintura, tensión, diagnósticos (diabetes, hipertensión,
  colesterol, insuficiencia cardíaca, cardiopatía isquémica, ictus, riñón), fármacos
  (insulina, antidiabéticos orales, antihipertensivos, hipolipemiantes) y tabaco.
- Una muestra de orina (la aleatoria del centro): UACR, albúmina, creatinina en orina,
  volumen, flujo y horas desde la micción anterior.

Objetivos (lo que mide la analítica de sangre): FG (CKD-EPI 2021), HbA1c, glucosa, potasio,
colesterol no-HDL y hemoglobina. Además, el UACR de la primera orina de la mañana, que con
la historia clínica sola sirve para decidir a quién pedirle la prueba.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..egfr import ckd_epi_2021
from ..nhanes import DEFAULT_DIR, read_xpt

DEMOGRAPHICS = ["age", "female"]
CLINICAL = [
    "bmi",
    "waist",
    "sbp",
    "dbp",
    "dx_diabetes",
    "dx_prediabetes",
    "insulin",
    "diabetes_pills",
    "dx_hypertension",
    "bp_meds",
    "dx_high_cholesterol",
    "cholesterol_meds",
    "dx_heart_failure",
    "dx_coronary",
    "dx_stroke",
    "dx_kidney",
    "smoker_now",
    "smoker_ever",
]
URINE = ["log_uacr", "log_urine_albumin", "log_urine_creatinine", "urine_volume", "urine_flow", "hours_since_void"]

FEATURE_SETS = {
    "solo orina": URINE,
    "edad y sexo": DEMOGRAPHICS,
    "edad, sexo y orina": DEMOGRAPHICS + URINE,
    "historia clínica": DEMOGRAPHICS + CLINICAL,
    "historia clínica y orina": DEMOGRAPHICS + CLINICAL + URINE,
}

TARGETS = {
    "egfr": "FG (ml/min/1,73 m²)",
    "hba1c": "HbA1c (%)",
    "glucose": "Glucosa (mg/dl, sin ayuno)",
    "potassium": "Potasio (mmol/l)",
    "non_hdl": "Colesterol no-HDL (mg/dl)",
    "hemoglobin": "Hemoglobina (g/dl)",
    "log_uacr_morning": "log UACR primera orina (mg/g)",
}


def _yes_no(series) -> np.ndarray:
    """1 = sí, 2 = no; el resto (no sabe, no contesta, no preguntado) queda vacío."""
    s = series.to_numpy(float)
    return np.where(s == 1, 1.0, np.where(s == 2, 0.0, np.nan))


PANEL_CYCLES = {"2009-2010": "_F", "2011-2012": "_G", "2013-2014": "_H", "2015-2016": "_I", "2017-2018": "_J"}
_PANEL_FILES = ("BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ", "KIQ_U", "ALB_CR", "UCFLOW", "BIOPRO", "GHB", "TCHOL", "HDL", "CBC")


def load_panel(base_dir: Path = DEFAULT_DIR.parent, cycles=tuple(PANEL_CYCLES)) -> pd.DataFrame:
    """Una fila por adulto (≥ 20 años, sin embarazo) con predictores y objetivos.

    Junta las oleadas de NHANES indicadas (por defecto 2009-2018). Solo 2009-2010 tiene la
    segunda muestra de orina, así que ``log_uacr_morning`` solo existe para esa oleada.
    """
    frames = []
    for cycle in cycles:
        suffix, directory = PANEL_CYCLES[cycle], Path(base_dir) / cycle
        demo = read_xpt(f"DEMO{suffix}", directory)[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"]]
        df = demo[(demo.RIDAGEYR >= 20) & (demo.RIDEXPRG != 1)]
        for name in _PANEL_FILES:
            df = df.merge(read_xpt(f"{name}{suffix}", directory), on="SEQN", how="left", suffixes=("", "_dup"))
        out = _panel_columns(df)
        out.insert(1, "cycle", cycle)
        frames.append(out)
    out = pd.concat(frames, ignore_index=True)
    # Solo personas con muestra de orina (el escenario del panel).
    return out[np.isfinite(out.log_uacr)].reset_index(drop=True)


def _col(df: pd.DataFrame, name: str) -> np.ndarray:
    return df[name].to_numpy(float) if name in df else np.full(len(df), np.nan)


def _panel_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"seqn": df.SEQN.astype(int).to_numpy(), "age": df.RIDAGEYR.to_numpy(float)})
    out["female"] = (df.RIAGENDR == 2).to_numpy(float)
    out["bmi"] = df.BMXBMI.to_numpy(float)
    out["waist"] = df.BMXWAIST.to_numpy(float)
    sbp = df[["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"]].to_numpy(float, copy=True)
    dbp = df[["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"]].to_numpy(float, copy=True)
    dbp[dbp <= 0] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # filas sin ninguna lectura
        out["sbp"] = np.nanmean(sbp, axis=1)
        out["dbp"] = np.nanmean(dbp, axis=1)
    diq010 = df.DIQ010.to_numpy(float)
    out["dx_diabetes"] = np.where(diq010 == 1, 1.0, np.where(np.isin(diq010, (2, 3)), 0.0, np.nan))
    out["dx_prediabetes"] = np.where(diq010 == 3, 1.0, np.where(np.isin(diq010, (1, 2)), 0.0, np.nan))
    out["insulin"] = _yes_no(df.DIQ050)
    out["diabetes_pills"] = _yes_no(df.DIQ070)
    out["dx_hypertension"] = _yes_no(df.BPQ020)
    out["bp_meds"] = _yes_no(df.BPQ050A)
    out["dx_high_cholesterol"] = _yes_no(df.BPQ080)
    out["cholesterol_meds"] = _yes_no(df.BPQ100D)
    out["dx_heart_failure"] = _yes_no(df.MCQ160B)
    out["dx_coronary"] = np.fmax(np.fmax(_yes_no(df.MCQ160C), _yes_no(df.MCQ160D)), _yes_no(df.MCQ160E))
    out["dx_stroke"] = _yes_no(df.MCQ160F)
    out["dx_kidney"] = _yes_no(df.KIQ022)
    ever = _yes_no(df.SMQ020)
    now = df.SMQ040.to_numpy(float)
    out["smoker_ever"] = ever
    out["smoker_now"] = np.where(np.isin(now, (1, 2)), 1.0, np.where((now == 3) | (ever == 0), 0.0, np.nan))
    # Orina: muestra aleatoria del centro de examen (la única con volumen y flujo).
    albumin = df.URXUMA.to_numpy(float)
    ucr = df.URXUCR.to_numpy(float)
    albumin_eff = np.where(albumin <= 0.22, 0.3, albumin)  # bajo el límite de detección
    out["log_uacr"] = np.log(100.0 * albumin_eff / ucr)
    out["log_urine_albumin"] = np.log(albumin_eff)
    out["log_urine_creatinine"] = np.log(ucr)
    out["urine_volume"] = df.URXVOL1.to_numpy(float)
    out["urine_flow"] = df.URDFLOW1.to_numpy(float)
    out["hours_since_void"] = df.URDTIME1.to_numpy(float) / 60.0
    # Objetivos de la analítica de sangre.
    out["egfr"] = ckd_epi_2021(df.LBXSCR.to_numpy(float), out.age, out.female == 1)
    out["hba1c"] = df.LBXGH.to_numpy(float)
    out["glucose"] = df.LBXSGL.to_numpy(float)
    out["potassium"] = df.LBXSKSI.to_numpy(float)
    out["non_hdl"] = df.LBXTC.to_numpy(float) - df.LBDHDD.to_numpy(float)
    out["hemoglobin"] = df.LBXHGB.to_numpy(float)
    morning_alb = _col(df, "URXUMA2")
    with np.errstate(invalid="ignore"):
        out["log_uacr_morning"] = np.log(100.0 * np.where(morning_alb <= 0.22, 0.3, morning_alb) / _col(df, "URXUCR2"))
    return out


# --- NT-proBNP (insuficiencia cardíaca): NHANES 1999-2004, sueros guardados ---

HEART_CLINICAL = [c for c in CLINICAL if c != "dx_kidney"]
HEART_URINE = ["log_uacr", "log_urine_albumin", "log_urine_creatinine"]
HEART_FEATURE_SETS = {
    "edad y sexo": DEMOGRAPHICS,
    "edad, sexo y orina": DEMOGRAPHICS + HEART_URINE,
    "historia clínica": DEMOGRAPHICS + HEART_CLINICAL,
    "historia clínica y orina": DEMOGRAPHICS + HEART_CLINICAL + HEART_URINE,
    "historia, orina y FG": DEMOGRAPHICS + HEART_CLINICAL + HEART_URINE + ["egfr"],
}
_HEART_CYCLES = {
    "1999-2000": dict(suffix="", urine="LAB16", bio="LAB18", a1c="LAB10", scr="LBXSCR", scr_fix=lambda s: 1.013 * s + 0.147),
    "2001-2002": dict(suffix="_B", urine="L16_B", bio="L40_B", a1c="L10_B", scr="LBDSCR", scr_fix=lambda s: s),
    "2003-2004": dict(suffix="_C", urine="L16_C", bio="L40_C", a1c="L10_C", scr="LBXSCR", scr_fix=lambda s: s),
}


def load_heart(base_dir: Path = DEFAULT_DIR.parent) -> pd.DataFrame:
    """Adultos de NHANES 1999-2004 con NT-proBNP (muestras nunca descongeladas), historia y orina.

    La creatinina de 1999-2000 se recalibra al método estandarizado como indica NHANES.
    """
    bnp = read_xpt("SSBNP_A", base_dir / "1999-2000")
    bnp = bnp[bnp.SSPRIS == 1][["SEQN", "SSBNP"]]
    frames = []
    for cycle, c in _HEART_CYCLES.items():
        directory = base_dir / cycle
        s = c["suffix"]
        demo = read_xpt(f"DEMO{s}", directory)[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"]]
        df = demo[(demo.RIDAGEYR >= 20) & (demo.RIDEXPRG != 1)].merge(bnp, on="SEQN")
        for name in (f"BMX{s}", f"BPX{s}", f"BPQ{s}", f"DIQ{s}", f"MCQ{s}", f"SMQ{s}", c["urine"], c["a1c"]):
            df = df.merge(read_xpt(name, directory), on="SEQN", how="left", suffixes=("", "_dup"))
        bio = read_xpt(c["bio"], directory)[["SEQN", c["scr"]]].rename(columns={c["scr"]: "SCR"})
        df = df.merge(bio, on="SEQN", how="left")
        df["SCR"] = c["scr_fix"](df["SCR"])
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    out = pd.DataFrame({"seqn": df.SEQN.astype(int).to_numpy(), "age": df.RIDAGEYR.to_numpy(float)})
    out["female"] = (df.RIAGENDR == 2).to_numpy(float)
    out["bmi"] = df.BMXBMI.to_numpy(float)
    out["waist"] = df.BMXWAIST.to_numpy(float)
    sbp = df[["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"]].to_numpy(float, copy=True)
    dbp = df[["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"]].to_numpy(float, copy=True)
    dbp[dbp <= 0] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        out["sbp"] = np.nanmean(sbp, axis=1)
        out["dbp"] = np.nanmean(dbp, axis=1)
    diq010 = df.DIQ010.to_numpy(float)
    out["dx_diabetes"] = np.where(diq010 == 1, 1.0, np.where(np.isin(diq010, (2, 3)), 0.0, np.nan))
    out["dx_prediabetes"] = np.where(diq010 == 3, 1.0, np.where(np.isin(diq010, (1, 2)), 0.0, np.nan))
    out["insulin"] = _yes_no(df.DIQ050)
    out["diabetes_pills"] = _yes_no(df.DIQ070)
    out["dx_hypertension"] = _yes_no(df.BPQ020)
    out["bp_meds"] = _yes_no(df.BPQ050A)
    out["dx_high_cholesterol"] = _yes_no(df.BPQ080)
    out["cholesterol_meds"] = _yes_no(df.BPQ100D)
    out["dx_heart_failure"] = _yes_no(df.MCQ160B)
    out["dx_coronary"] = np.fmax(np.fmax(_yes_no(df.MCQ160C), _yes_no(df.MCQ160D)), _yes_no(df.MCQ160E))
    out["dx_stroke"] = _yes_no(df.MCQ160F)
    ever = _yes_no(df.SMQ020)
    now = df.SMQ040.to_numpy(float)
    out["smoker_ever"] = ever
    out["smoker_now"] = np.where(np.isin(now, (1, 2)), 1.0, np.where((now == 3) | (ever == 0), 0.0, np.nan))
    albumin = df.URXUMA.to_numpy(float)
    ucr = df.URXUCR.to_numpy(float)
    albumin_eff = np.where(albumin <= 0.22, 0.3, albumin)
    out["log_uacr"] = np.log(100.0 * albumin_eff / ucr)
    out["log_urine_albumin"] = np.log(albumin_eff)
    out["log_urine_creatinine"] = np.log(ucr)
    out["egfr"] = ckd_epi_2021(df.SCR.to_numpy(float), out.age, out.female == 1)
    out["hba1c"] = df.LBXGH.to_numpy(float)
    out["log_nt_probnp"] = np.log(df.SSBNP.to_numpy(float))
    return out[np.isfinite(out.log_uacr) & np.isfinite(out.log_nt_probnp)].reset_index(drop=True)
