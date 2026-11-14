"""Cohorte con seguimiento: NHANES 1999-2018 enlazado con el registro de defunciones de EE. UU.

Una fila por adulto con lo que se sabía el día del examen y lo que le pasó después (si murió,
de qué y cuándo, hasta el 31 de diciembre de 2019). Es lo que permite entrenar y comprobar un
modelo de riesgo con desenlaces reales, cosa que el resto del proyecto no tenía.

Los predictores están agrupados por lo que cuesta conseguirlos desde casa (``TIERS``):
cuestionario, manguito, orina y sangre.

Cuidados al juntar diez oleadas:
- La edad está acotada en 85 años hasta 2006 y en 80 después: se acota en 80 en todas.
- Varias preguntas cambian de nombre o de redacción; solo se usan las que se pueden igualar.
- La creatinina de 1999-2000 y de 2005-2006 se corrige como indica NHANES.
- En 2015-2018 el fichero público solo distingue la muerte por enfermedad del corazón y por
  cáncer; el ictus queda en "otras causas". Para la muerte cardiovascular se usan 1999-2014.
- En los ficheros públicos, el tiempo de seguimiento o la causa de algunos registros están
  sustituidos por valores sintéticos para proteger la identidad. Vivo o muerto no se toca.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from ..egfr import ckd_epi_2021
from ..nhanes import DEFAULT_DIR, read_xpt

BASE_DIR = DEFAULT_DIR.parent
SUFFIX = {
    "1999-2000": "",
    "2001-2002": "_B",
    "2003-2004": "_C",
    "2005-2006": "_D",
    "2007-2008": "_E",
    "2009-2010": "_F",
    "2011-2012": "_G",
    "2013-2014": "_H",
    "2015-2016": "_I",
    "2017-2018": "_J",
}
# Oleadas en las que el ictus se distingue como causa de muerte.
CV_CYCLES = tuple(c for c in SUFFIX if int(c[:4]) <= 2013)
# Oleadas en las que todo el mundo tiene al menos 10 años de seguimiento posible.
FULL_10Y_CYCLES = tuple(c for c in SUFFIX if int(c[:4]) <= 2007)

# Causa básica de muerte (códigos del fichero público).
HEART, CANCER, STROKE, DIABETES_DEATH, KIDNEY_DEATH = 1, 2, 5, 7, 9
CAUSES = {
    "cardiovascular": (HEART, STROKE),  # enfermedades del corazón e ictus
    "corazon": (HEART,),
    "cardio_renal_metabolica": (HEART, STROKE, DIABETES_DEATH, KIDNEY_DEATH),
}

_OLD_LABS = {
    "1999-2000": dict(urine="LAB16", bio="LAB18", a1c="LAB10", lipids="LAB13", scr="LBXSCR", hdl="LBDHDL"),
    "2001-2002": dict(urine="L16_B", bio="L40_B", a1c="L10_B", lipids="L13_B", scr="LBDSCR", hdl="LBDHDL"),
    "2003-2004": dict(urine="L16_C", bio="L40_C", a1c="L10_C", lipids="L13_C", scr="LBXSCR", hdl="LBXHDD"),
}
# Corrección de la creatinina al método estandarizado (documentación de NHANES).
_SCR_FIX = {"1999-2000": lambda s: 1.013 * s + 0.147, "2005-2006": lambda s: -0.016 + 0.978 * s}

# Predictores por lo que cuesta conseguirlos desde casa.
DEMOGRAPHICS = ["age", "female"]
# Lo que ya consta en la historia clínica, sin pedirle nada al paciente.
RECORD = [
    "bmi",
    "waist",
    "dx_diabetes",
    "insulin",
    "diabetes_pills",
    "dx_hypertension",
    "bp_meds",
    "dx_high_cholesterol",
    "cholesterol_meds",
    "dx_heart_failure",
    "dx_coronary",
    "dx_stroke",
    "smoker_now",
    "smoker_ever",
]
# Cinco preguntas que el paciente contesta desde casa.
QUESTIONS = ["health", "dyspnea", "walk_difficulty", "stairs_difficulty", "hospitalized"]
QUESTIONNAIRE = RECORD + QUESTIONS
CUFF = ["sbp", "dbp", "pulse", "pulse_irregular"]
STRIP = ["strip_albumin", "strip_creatinine"]
URINE_LAB = ["log_uacr", "log_urine_creatinine"]
BLOOD = ["egfr", "hba1c", "total_cholesterol", "hdl"]
TIERS = {
    "Edad y sexo": DEMOGRAPHICS,
    "Historia clínica": DEMOGRAPHICS + RECORD,
    "Historia y cuestionario": DEMOGRAPHICS + QUESTIONNAIRE,
    "Historia, cuestionario y manguito": DEMOGRAPHICS + QUESTIONNAIRE + CUFF,
    "Historia, cuestionario, manguito y tira de orina": DEMOGRAPHICS + QUESTIONNAIRE + CUFF + STRIP,
    "Historia, cuestionario, manguito y orina de laboratorio": DEMOGRAPHICS + QUESTIONNAIRE + CUFF + URINE_LAB,
    "Todo lo anterior y analítica de sangre": DEMOGRAPHICS + QUESTIONNAIRE + CUFF + URINE_LAB + BLOOD,
}
HOME_TIER = "Historia, cuestionario, manguito y orina de laboratorio"
# Variables de las ecuaciones que se usan hoy, para reajustarlas con estos mismos datos.
SCORE2_VARIABLES = ["age", "female", "smoker_now", "sbp", "total_cholesterol", "hdl", "dx_diabetes"]
PREVENT_VARIABLES = SCORE2_VARIABLES + ["bmi", "egfr", "bp_meds", "cholesterol_meds"]
PREVENT_FULL_VARIABLES = PREVENT_VARIABLES + ["log_uacr", "hba1c"]


def _yes_no(series) -> np.ndarray:
    """1 = sí, 2 = no; el resto (no sabe, no contesta, no preguntado) queda vacío."""
    s = np.asarray(series, dtype=float)
    return np.where(s == 1, 1.0, np.where(s == 2, 0.0, np.nan))


def _col(df: pd.DataFrame, *names: str) -> np.ndarray:
    """Primera de las columnas que exista (las preguntas cambian de nombre entre oleadas)."""
    for name in names:
        if name in df:
            return df[name].to_numpy(float)
    return np.full(len(df), np.nan)


def _taking(asked: np.ndarray, answer: np.ndarray) -> np.ndarray:
    """Toma el fármaco: sí solo si contestó que sí; no para quien contestó a la pregunta de entrada."""
    return np.where(answer == 1, 1.0, np.where(np.isfinite(asked), 0.0, np.nan))


def _difficulty(code: np.ndarray, age: np.ndarray) -> np.ndarray:
    """Dificultad de 0 (ninguna) a 3 (no puede o no lo hace). A los menores de 60 sin limitaciones no se les pregunta."""
    out = np.select([code == 1, code == 2, code == 3, (code == 4) | (code == 5)], [0.0, 1.0, 2.0, 3.0], default=np.nan)
    return np.where(np.isnan(code) & (age < 60), 0.0, out)


def read_mortality(cycle: str, base_dir: Path = BASE_DIR) -> pd.DataFrame:
    """Fichero público de mortalidad enlazada de una oleada (formato de ancho fijo de los CDC)."""
    path = Path(base_dir) / "mortality" / f"NHANES_{cycle.replace('-', '_')}_MORT_2019_PUBLIC.dat"
    m = pd.read_fwf(
        path,
        colspecs=[(0, 6), (14, 15), (15, 16), (16, 19), (42, 45), (45, 48)],
        names=["SEQN", "eligible", "dead", "cause", "months_interview", "months_exam"],
        na_values=["."],
    )
    m["months"] = m.months_exam.fillna(m.months_interview)
    return m[["SEQN", "eligible", "dead", "cause", "months"]]


def _load_cycle(cycle: str, base_dir: Path) -> pd.DataFrame:
    s, d = SUFFIX[cycle], Path(base_dir) / cycle
    old = _OLD_LABS.get(cycle)
    demo = read_xpt(f"DEMO{s}", d)[["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG"]]
    df = demo[(demo.RIDAGEYR >= 20) & (demo.RIDEXPRG != 1)]
    files = [f"{n}{s}" for n in ("BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ", "CDQ", "HUQ", "PFQ")]
    files += [old["urine"], old["a1c"], old["lipids"]] if old else [f"ALB_CR{s}", f"GHB{s}", f"TCHOL{s}", f"HDL{s}"]
    for name in files:
        df = df.merge(read_xpt(name, d), on="SEQN", how="left", suffixes=("", "_dup"))
    scr_col = old["scr"] if old else "LBXSCR"
    bio = read_xpt(old["bio"] if old else f"BIOPRO{s}", d)[["SEQN", scr_col]].rename(columns={scr_col: "SCR"})
    df = df.merge(bio, on="SEQN", how="left")
    df["SCR"] = _SCR_FIX.get(cycle, lambda v: v)(df["SCR"])
    if int(cycle[:4]) <= 2003:
        bnp = read_xpt("SSBNP_A", Path(base_dir) / "1999-2000")
        df = df.merge(bnp[bnp.SSPRIS == 1][["SEQN", "SSBNP"]], on="SEQN", how="left")
    df = df.merge(read_mortality(cycle, base_dir), on="SEQN", how="left")

    age = np.minimum(df.RIDAGEYR.to_numpy(float), 80.0)
    out = pd.DataFrame({"seqn": df.SEQN.astype(int).to_numpy(), "cycle": cycle, "age": age})
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
    out["pulse"] = _col(df, "BPXPLS")
    rhythm = _col(df, "BPXPULS")
    out["pulse_irregular"] = np.where(rhythm == 2, 1.0, np.where(rhythm == 1, 0.0, np.nan))

    diq010 = df.DIQ010.to_numpy(float)
    out["dx_diabetes"] = np.where(diq010 == 1, 1.0, np.where(np.isin(diq010, (2, 3)), 0.0, np.nan))
    out["dx_prediabetes"] = np.where(diq010 == 3, 1.0, np.where(np.isin(diq010, (1, 2)), 0.0, np.nan))
    out["insulin"] = _taking(diq010, _col(df, "DIQ050"))
    out["diabetes_pills"] = _taking(diq010, _col(df, "DIQ070", "DID070"))
    told_bp, told_chol = _col(df, "BPQ020"), _col(df, "BPQ080")
    out["dx_hypertension"] = _yes_no(told_bp)
    out["bp_meds"] = _taking(_yes_no(told_bp), _col(df, "BPQ050A"))
    # Hasta 2010 solo se preguntaba por el colesterol a quien se lo había medido alguna vez;
    # después, a todos. Quien nunca se lo midió cuenta como "no" en todas las oleadas.
    out["dx_high_cholesterol"] = np.where(told_chol == 1, 1.0, np.where(np.isfinite(told_bp), 0.0, np.nan))
    out["cholesterol_meds"] = _taking(out["dx_high_cholesterol"].to_numpy(), _col(df, "BPQ100D"))
    out["dx_heart_failure"] = _yes_no(df.MCQ160B)
    out["dx_coronary"] = np.fmax(np.fmax(_yes_no(df.MCQ160C), _yes_no(df.MCQ160D)), _yes_no(df.MCQ160E))
    out["dx_stroke"] = _yes_no(df.MCQ160F)
    ever = _yes_no(df.SMQ020)
    now = df.SMQ040.to_numpy(float)
    out["smoker_ever"] = ever
    out["smoker_now"] = np.where(np.isin(now, (1, 2)), 1.0, np.where((now == 3) | (ever == 0), 0.0, np.nan))

    # Cuestionario: salud percibida (1 excelente ... 5 mala), disnea al subir cuestas o
    # escaleras (solo se pregunta a partir de 40 años), dificultad para caminar 400 m y para
    # subir 10 escalones, e ingreso en el último año.
    health = _col(df, "HUQ010")
    out["health"] = np.where((health >= 1) & (health <= 5), health, np.nan)
    out["dyspnea"] = _yes_no(_col(df, "CDQ010"))
    out["walk_difficulty"] = _difficulty(_col(df, "PFQ061B", "PFQ060B"), age)
    out["stairs_difficulty"] = _difficulty(_col(df, "PFQ061C", "PFQ060C"), age)
    out["hospitalized"] = _yes_no(_col(df, "HUQ071", "HUD070", "HUQ070"))

    albumin = df.URXUMA.to_numpy(float)
    ucr = df.URXUCR.to_numpy(float)
    albumin_eff = np.where(albumin <= 0.22, 0.3, albumin)  # bajo el límite de detección
    with np.errstate(invalid="ignore", divide="ignore"):
        out["log_uacr"] = np.log(100.0 * albumin_eff / ucr)
        out["log_urine_albumin"] = np.log(albumin_eff)
        out["log_urine_creatinine"] = np.log(ucr)
    out["egfr"] = ckd_epi_2021(df.SCR.to_numpy(float), age, out.female == 1)
    out["hba1c"] = df.LBXGH.to_numpy(float)
    out["total_cholesterol"] = df.LBXTC.to_numpy(float)
    out["hdl"] = _col(df, old["hdl"] if old else "LBDHDD")
    out["non_hdl"] = out.total_cholesterol - out.hdl
    with np.errstate(invalid="ignore"):
        out["log_nt_probnp"] = np.log(_col(df, "SSBNP"))

    out["eligible"] = (df.eligible == 1).to_numpy()
    out["dead"] = df.dead.to_numpy(float)
    out["cause"] = df.cause.to_numpy(float)
    out["months"] = df.months.to_numpy(float)
    return out


def load_cohort(base_dir: Path = BASE_DIR, cycles=tuple(SUFFIX)) -> pd.DataFrame:
    """Adultos (≥ 20 años, sin embarazo) con seguimiento de mortalidad.

    Columnas: identificación (``seqn``, ``cycle``), predictores (ver ``TIERS``) y desenlace:
    ``dead`` (0/1), ``cause`` (código de la causa básica; vacío si vive) y ``months`` desde el
    examen hasta la muerte o el fin del seguimiento.
    """
    out = pd.concat([_load_cycle(c, base_dir) for c in cycles], ignore_index=True)
    out = out[out.eligible & np.isfinite(out.months) & np.isfinite(out.dead)].drop(columns="eligible")
    return out.reset_index(drop=True)


# Bloques de datos de casa que un paciente puede no haber aportado todavía.
BLOCKS = {
    "cuestionario": ["health", "dyspnea", "walk_difficulty", "stairs_difficulty", "hospitalized"],
    "peso y cintura": ["bmi", "waist"],
    "manguito": CUFF,
    "orina": URINE_LAB,
}


def complete_home(df: pd.DataFrame) -> np.ndarray:
    """Personas con todos los datos de casa.

    En NHANES un dato vacío no es neutro: suele ser de alguien a quien no se pudo explorar, más
    frágil. En el producto, vacío significa "aún no lo ha aportado". Para que el modelo no
    aprenda lo primero se entrena y se evalúa solo con personas que lo tienen todo (la disnea
    solo se pregunta desde los 40 años).
    """
    needed = [c for cols in BLOCKS.values() for c in cols if c != "dyspnea"]
    ok = np.isfinite(df[needed]).all(axis=1).to_numpy()
    return ok & (np.isfinite(df.dyspnea.to_numpy()) | (df.age.to_numpy() < 40))


def mask_blocks(df: pd.DataFrame, rng, copies: int = 2, p: float = 0.5, blocks: dict | None = None) -> pd.DataFrame:
    """Las filas originales más ``copies`` copias con bloques enteros de datos borrados al azar.

    Así el modelo aprende qué estimar cuando falta el cuestionario, el manguito o la orina, y
    un hueco significa "no aportado" y nada más.
    """
    out = [df]
    for _ in range(copies):
        copy = df.copy()
        for cols in (blocks or BLOCKS).values():
            cols = [c for c in cols if c in copy]
            copy.loc[rng.random(len(copy)) < p, cols] = np.nan
        out.append(copy)
    return pd.concat(out, ignore_index=True)


def add_strip(df: pd.DataFrame, spec, seed: int = 0) -> pd.DataFrame:
    """Añade lo que habría leído una tira en la misma orina (niveles de albúmina y creatinina, en log).

    La orina de NHANES se midió en el laboratorio. Para saber cuánto vale una tira se simula su
    lectura con el error de ``spec`` (ver ``albuminuria.strip``).
    """
    from ..albuminuria.strip import simulate_reading

    rng = np.random.default_rng(seed)
    out = df.copy()
    ok = np.isfinite(df.log_uacr.to_numpy()) & np.isfinite(df.log_urine_creatinine.to_numpy())
    u = df.log_urine_creatinine.to_numpy()[ok] - np.log(100.0)
    a, c = simulate_reading(spec, df.log_uacr.to_numpy()[ok], u, rng)
    out["strip_albumin"] = np.nan
    out["strip_creatinine"] = np.nan
    out.loc[ok, "strip_albumin"] = np.log(np.asarray(spec.albumin_levels))[a]
    out.loc[ok, "strip_creatinine"] = np.log(np.asarray(spec.creatinine_levels))[c]
    return out


def event_within(df: pd.DataFrame, causes: tuple[int, ...], years: float = 10.0) -> np.ndarray:
    """Muerte por esas causas antes de ``years`` años (solo tiene sentido con seguimiento completo)."""
    return ((df.dead == 1) & df.cause.isin(causes) & (df.months <= 12.0 * years)).to_numpy()
