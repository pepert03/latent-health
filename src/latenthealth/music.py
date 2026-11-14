"""Cohorte MUSIC: 992 pacientes con insuficiencia cardíaca de ocho hospitales españoles.

Estudio prospectivo (2003-2004, seguimiento hasta 2008) de pacientes ambulatorios con
insuficiencia cardíaca sintomática (clases II y III de la NYHA), publicado en abierto en
PhysioNet (licencia ODbL). Aquí solo se usa la tabla clínica: datos de la visita, analítica,
ecocardiograma, ECG, resumen del Holter, medicación y mortalidad.

Todos tienen la enfermedad, así que no sirve para detectarla. Sirve para dos cosas: saber
cuánto de la gravedad se ve con lo que el paciente puede medir en casa, y comprobar en
pacientes españoles tratados lo que se aprende de otros datos.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "raw" / "music"

# Nombre en la tabla (sin espacios repetidos) -> nombre corto. Se busca por el comienzo.
COLUMNS = {
    "Patient ID": "patient", "Follow-up period from enrollment": "days", "Exit of the study": "exit", "Cause of death": "cause",
    "Age": "age", "Gender (male=1)": "male", "Weight (kg)": "weight", "Height (cm)": "height", "Body Mass Index": "bmi",
    "NYHA class": "nyha", "Diastolic blood pressure": "dbp", "Systolic blood pressure": "sbp", "HF etiology": "etiology",
    "Diabetes (yes=1)": "diabetes", "History of dyslipemia": "dyslipidemia", "Peripheral vascular disease": "vascular",
    "History of hypertension": "hypertension", "Prior Myocardial Infarction": "prior_mi", "Prior implantable device": "device",
    "Prior Revascularization": "revascularization", "Syncope": "syncope", "Albumin": "albumin", "Normalized Troponin": "troponin",
    "Total Cholesterol": "cholesterol", "Creatinine": "creatinine", "Glucose": "glucose", "Hemoglobin": "hemoglobin",
    "Potassium": "potassium", "Sodium": "sodium", "Pro-BNP": "nt_probnp", "Urea": "urea",
    "Signs of pulmonary venous hypertension": "lung_congestion", "Cardiothoracic ratio": "cardiothoracic",
    "Left atrial size": "left_atrium", "LVEF": "lvef", "Mitral valve insufficiency": "mitral",
    "Left ventricle end-diastolic diameter": "lv_diameter", "ECG rhythm": "ecg_rhythm", "Q-waves": "q_waves",
    "PR interval": "pr", "QRS duration": "qrs", "QT corrected": "qtc", "Average RR (ms)": "rr_ecg",
    "Left ventricular hypertrophy": "lvh", "Holter rhythm": "holter_rhythm", "Average RR (ms).1": "rr_holter",
    "Number of ventricular premature beats in 24h": "ventricular_beats", "Non-sustained ventricular tachycardia": "nsvt",
    "SDNN": "sdnn", "SDANN": "sdann", "RMSSD": "rmssd", "pNN50": "pnn50", "Calcium channel blocker": "rx_calcium",
    "Diabetes medication": "rx_diabetes", "Amiodarone": "rx_amiodarone", "Angiotensin-II receptor blocker": "rx_arb",
    "Anticoagulants": "rx_anticoagulant", "Betablockers": "rx_betablocker", "Digoxin": "rx_digoxin", "Loop diuretics": "rx_loop",
    "Spironolactone": "rx_spironolactone", "Statins": "rx_statin", "ACE inhibitor": "rx_ace", "Nitrovasodilator": "rx_nitrate",
}  # fmt: skip

# Lo que hace falta para conocer cada dato, de menos a más.
RECORD = ["age", "male", "diabetes", "hypertension", "prior_mi", "vascular", "dyslipidemia", "device", "ischemic",
          "rx_betablocker", "rx_loop", "rx_digoxin", "rx_spironolactone", "rx_ace", "rx_arb", "rx_anticoagulant", "rx_amiodarone"]  # fmt: skip
HOME = ["nyha", "bmi", "sbp", "dbp", "heart_rate", "irregular"]  # preguntas, báscula, manguito y pulso
ECG = ["qrs", "qtc", "pr", "q_waves"]
LAB = ["nt_probnp", "creatinine", "sodium", "hemoglobin", "urea", "albumin", "troponin", "cholesterol", "potassium", "glucose"]
ECHO = ["lvef", "left_atrium", "lv_diameter", "mitral", "cardiothoracic", "lung_congestion"]
HOLTER = ["ventricular_beats", "nsvt", "sdnn", "rmssd"]
TIERS = {
    "Edad y sexo": ["age", "male"],
    "Historia clínica": RECORD,
    "Historia y medidas de casa": RECORD + HOME,
    "Lo anterior y ECG": RECORD + HOME + ECG,
    "Lo anterior y analítica": RECORD + HOME + ECG + LAB,
    "Todo, con ecocardiograma y Holter": RECORD + HOME + ECG + LAB + ECHO + HOLTER,
}
HOME_TIER = "Historia y medidas de casa"


def load_music(root: Path = DATA) -> pd.DataFrame:
    """Tabla clínica con nombres cortos, números con punto decimal y los desenlaces a cuatro años."""
    raw = pd.read_csv(root / "subject-info.csv", sep=";", encoding="utf-8", encoding_errors="replace")
    names, seen = [], {}
    for column in raw.columns:
        name = " ".join(str(column).split())
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name}.{seen[name] - 1}")  # el RR medio sale dos veces: ECG y Holter
    raw.columns = names
    out = pd.DataFrame(index=raw.index)
    for prefix, name in COLUMNS.items():
        match = [c for c in raw.columns if c == prefix] or [c for c in raw.columns if c.startswith(prefix) and not c.endswith(".1")]
        if not match:
            raise KeyError(f"Falta la columna {prefix!r} en la tabla de MUSIC")
        column = raw[match[0]]
        out[name] = column if name == "patient" else pd.to_numeric(column.astype(str).str.replace(",", ".", regex=False), errors="coerce")
    for name in ("pr", "qrs", "qtc"):
        out.loc[out[name] == 999, name] = np.nan  # 999 es "no medible" (sin onda P en la fibrilación auricular)
    out["heart_rate"] = 60000.0 / out.rr_ecg
    out["irregular"] = (out.ecg_rhythm.isin([1, 2])).astype(float)  # fibrilación o aleteo auricular
    out["ischemic"] = out.etiology.isin([2, 6]).astype(float)
    out["device"] = (out.device > 0).astype(float)
    out["years"] = out.days / 365.25
    out["death"] = out.exit == 3
    out["cardiac_death"] = out.death & out.cause.isin([3, 6, 7])
    out["pump_death"] = out.death & out.cause.isin([6, 7])
    out["sudden_death"] = out.death & (out.cause == 3)
    return out


def known_at(data: pd.DataFrame, years: float, event: str = "death") -> pd.Series:
    """Si se sabe qué pasó a los ``years`` años: murió antes o se le siguió al menos ese tiempo."""
    return (data[event] & (data.years <= years)) | (data.years >= years)


def event_by(data: pd.DataFrame, years: float, event: str = "death") -> pd.Series:
    return data[event] & (data.years <= years)
