"""Cohort with follow-up: NHANES 1999-2018 linked to the US death registry.

One row per adult with what was known on the exam day and what happened afterwards (whether
they died, of what and when, up to 31 December 2019). This is what allows training and
checking a risk model against real outcomes, which the rest of the project lacked.

Predictors are grouped by how hard they are to obtain from home (``TIERS``):
questionnaire, cuff, urine and blood.

Caveats when pooling ten cycles:
- Age is top-coded at 85 until 2006 and at 80 afterwards: it is capped at 80 throughout.
- Several questions change name or wording; only those that can be harmonized are used.
- Creatinine for 1999-2000 and 2005-2006 is corrected as NHANES recommends.
- In 2015-2018 the public file only distinguishes death from heart disease and from cancer;
  stroke falls under "other causes". Cardiovascular death uses 1999-2014.
- In the public files, follow-up time or cause for some records is replaced by synthetic
  values to protect identity. Vital status is left untouched.

``TIERS``/``HOME_TIER`` keys and ``BLOCKS`` keys are kept in Spanish: scripts look them up by name.
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
# Cycles in which stroke is distinguished as a cause of death.
CV_CYCLES = tuple(c for c in SUFFIX if int(c[:4]) <= 2013)
# Cycles in which everyone has at least 10 years of possible follow-up.
FULL_10Y_CYCLES = tuple(c for c in SUFFIX if int(c[:4]) <= 2007)

# Underlying cause of death (public-file codes).
HEART, CANCER, STROKE, DIABETES_DEATH, KIDNEY_DEATH = 1, 2, 5, 7, 9
CAUSES = {
    "cardiovascular": (HEART, STROKE),  # heart disease and stroke
    "corazon": (HEART,),
    "cardio_renal_metabolica": (HEART, STROKE, DIABETES_DEATH, KIDNEY_DEATH),
}

_OLD_LABS = {
    "1999-2000": dict(urine="LAB16", bio="LAB18", a1c="LAB10", lipids="LAB13", scr="LBXSCR", hdl="LBDHDL"),
    "2001-2002": dict(urine="L16_B", bio="L40_B", a1c="L10_B", lipids="L13_B", scr="LBDSCR", hdl="LBDHDL"),
    "2003-2004": dict(urine="L16_C", bio="L40_C", a1c="L10_C", lipids="L13_C", scr="LBXSCR", hdl="LBXHDD"),
}
# Creatinine correction to the standardized method (NHANES documentation).
_SCR_FIX = {"1999-2000": lambda s: 1.013 * s + 0.147, "2005-2006": lambda s: -0.016 + 0.978 * s}

# Predictors grouped by how hard they are to obtain from home.
DEMOGRAPHICS = ["age", "female"]
# What is already in the clinical record, without asking the patient anything.
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
# Five questions the patient answers from home.
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
# Variables of the equations in use today, to refit them on this same data.
SCORE2_VARIABLES = ["age", "female", "smoker_now", "sbp", "total_cholesterol", "hdl", "dx_diabetes"]
PREVENT_VARIABLES = SCORE2_VARIABLES + ["bmi", "egfr", "bp_meds", "cholesterol_meds"]
PREVENT_FULL_VARIABLES = PREVENT_VARIABLES + ["log_uacr", "hba1c"]


def _yes_no(series) -> np.ndarray:
    """1 = yes, 2 = no; anything else (don't know, refused, not asked) is left empty."""
    s = np.asarray(series, dtype=float)
    return np.where(s == 1, 1.0, np.where(s == 2, 0.0, np.nan))


def _col(df: pd.DataFrame, *names: str) -> np.ndarray:
    """First column that exists (questions change name between cycles)."""
    for name in names:
        if name in df:
            return df[name].to_numpy(float)
    return np.full(len(df), np.nan)


def _taking(asked: np.ndarray, answer: np.ndarray) -> np.ndarray:
    """Takes the drug: yes only if answered yes; no for anyone who answered the gate question."""
    return np.where(answer == 1, 1.0, np.where(np.isfinite(asked), 0.0, np.nan))


def _difficulty(code: np.ndarray, age: np.ndarray) -> np.ndarray:
    """Difficulty from 0 (none) to 3 (unable or does not do it). Under-60s without limitations are not asked."""
    out = np.select([code == 1, code == 2, code == 3, (code == 4) | (code == 5)], [0.0, 1.0, 2.0, 3.0], default=np.nan)
    return np.where(np.isnan(code) & (age < 60), 0.0, out)


def read_mortality(cycle: str, base_dir: Path = BASE_DIR) -> pd.DataFrame:
    """Public linked-mortality file for one cycle (CDC fixed-width format)."""
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
        warnings.simplefilter("ignore", RuntimeWarning)  # rows without any reading
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
    # Until 2010 only people who had ever had cholesterol checked were asked about it;
    # afterwards, everyone. Never checked counts as "no" in all cycles.
    out["dx_high_cholesterol"] = np.where(told_chol == 1, 1.0, np.where(np.isfinite(told_bp), 0.0, np.nan))
    out["cholesterol_meds"] = _taking(out["dx_high_cholesterol"].to_numpy(), _col(df, "BPQ100D"))
    out["dx_heart_failure"] = _yes_no(df.MCQ160B)
    out["dx_coronary"] = np.fmax(np.fmax(_yes_no(df.MCQ160C), _yes_no(df.MCQ160D)), _yes_no(df.MCQ160E))
    out["dx_stroke"] = _yes_no(df.MCQ160F)
    ever = _yes_no(df.SMQ020)
    now = df.SMQ040.to_numpy(float)
    out["smoker_ever"] = ever
    out["smoker_now"] = np.where(np.isin(now, (1, 2)), 1.0, np.where((now == 3) | (ever == 0), 0.0, np.nan))

    # Questionnaire: self-rated health (1 excellent ... 5 poor), shortness of breath on hills or
    # stairs (only asked from age 40), difficulty walking 400 m and climbing 10 steps,
    # and hospital admission in the last year.
    health = _col(df, "HUQ010")
    out["health"] = np.where((health >= 1) & (health <= 5), health, np.nan)
    out["dyspnea"] = _yes_no(_col(df, "CDQ010"))
    out["walk_difficulty"] = _difficulty(_col(df, "PFQ061B", "PFQ060B"), age)
    out["stairs_difficulty"] = _difficulty(_col(df, "PFQ061C", "PFQ060C"), age)
    out["hospitalized"] = _yes_no(_col(df, "HUQ071", "HUD070", "HUQ070"))

    albumin = df.URXUMA.to_numpy(float)
    ucr = df.URXUCR.to_numpy(float)
    albumin_eff = np.where(albumin <= 0.22, 0.3, albumin)  # below the detection limit
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
    """Adults (age >= 20, not pregnant) with mortality follow-up.

    Columns: identifiers (``seqn``, ``cycle``), predictors (see ``TIERS``) and outcome:
    ``dead`` (0/1), ``cause`` (underlying-cause code; empty if alive) and ``months`` from the
    exam to death or end of follow-up.
    """
    out = pd.concat([_load_cycle(c, base_dir) for c in cycles], ignore_index=True)
    out = out[out.eligible & np.isfinite(out.months) & np.isfinite(out.dead)].drop(columns="eligible")
    return out.reset_index(drop=True)


# Blocks of home data a patient may not have provided yet.
BLOCKS = {
    "cuestionario": ["health", "dyspnea", "walk_difficulty", "stairs_difficulty", "hospitalized"],
    "peso y cintura": ["bmi", "waist"],
    "manguito": CUFF,
    "orina": URINE_LAB,
}


def complete_home(df: pd.DataFrame) -> np.ndarray:
    """People with all the home data.

    In NHANES a missing value is not neutral: it usually belongs to someone who could not be
    examined, i.e. frailer. In the product, missing means "not provided yet". So the model does
    not learn the former, it is trained and evaluated only on people with everything (dyspnea
    is only asked from age 40).
    """
    needed = [c for cols in BLOCKS.values() for c in cols if c != "dyspnea"]
    ok = np.isfinite(df[needed]).all(axis=1).to_numpy()
    return ok & (np.isfinite(df.dyspnea.to_numpy()) | (df.age.to_numpy() < 40))


def mask_blocks(df: pd.DataFrame, rng, copies: int = 2, p: float = 0.5, blocks: dict | None = None) -> pd.DataFrame:
    """The original rows plus ``copies`` copies with whole data blocks randomly blanked.

    This way the model learns what to estimate when the questionnaire, cuff or urine is missing,
    and a gap means "not provided" and nothing else.
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
    """Add what a dipstick would have read on the same urine (albumin and creatinine levels, log).

    NHANES urine was measured in the lab. To assess what a strip is worth, its reading is
    simulated with the error of ``spec`` (see ``albuminuria.strip``).
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
    """Death from those causes within ``years`` years (only meaningful with complete follow-up)."""
    return ((df.dead == 1) & df.cause.isin(causes) & (df.months <= 12.0 * years)).to_numpy()
