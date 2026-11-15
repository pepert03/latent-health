"""Copia estática del modelo para la interfaz del médico (web/site/js/medico.js).

Calcula con el modelo real (latenthealth) a los pacientes inventados del cupo de ejemplo, a fecha
16/11/2026, y escribe un JSON compacto para pegarlo en medico.js como respaldo si el servidor no
responde. Los pacientes que la API representa entera llevan también los cuerpos de las peticiones
en vivo; su copia se calcula con las mismas funciones que las rutas, así que coincide con ellas.

Uso (desde la raíz del repo):
    uv run --with-requirements web/server/requirements.txt python scripts/web_medico.py [salida.json]

El JSON que escribe es el que va pegado al final de web/site/js/medico.js.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "web"))
sys.path.insert(0, str(REPO / "src"))

from latenthealth import assessment as panel  # noqa: E402
from latenthealth import cvrisk  # noqa: E402
from latenthealth.albuminuria import PHONE_STRIP, UrineSample  # noqa: E402
from latenthealth.albuminuria.model import FIRST_MORNING  # noqa: E402
from latenthealth.diabetes import GlucoseReading  # noqa: E402
from latenthealth.home import BPReading, HeartCheck, HomeLab, RhythmCheck, af_probability, af_prior, summarize_home_bp  # noqa: E402
from latenthealth.kidney_trend import EgfrMeasurement  # noqa: E402
from latenthealth.worklist import row_for  # noqa: E402
from server.routes import model as route  # noqa: E402
from server.serialize import clean  # noqa: E402

D0 = date(2026, 11, 16)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("medico_modelo.json")


def r4(x):
    """Cuatro decimales; lo que no es cero no se redondea a cero (en pantalla sería «0 %»)."""
    if x is None:
        return None
    x = float(x)
    return round(x, 4) if x <= 0 or x >= 1e-4 else 1e-4


def r1(x):
    return None if x is None else round(float(x), 1)


def compact_assess(a, samples):
    alb = route.AlbuminuriaSummaryOut(**route._albuminuria_fields(a.albuminuria, samples)).model_dump(mode="json")
    joint = np.asarray(a.kdigo_joint, dtype=float)
    out = {
        "alb": {
            "status": alb["status"], "label": alb["status_label"], "cat": alb["category"],
            "p": [r4(alb["p_a1"]), r4(alb["p_a2"]), r4(alb["p_a3"])], "p2": r4(alb["p_a2_plus"]),
            "median": r1(alb["median"]), "low": r1(alb["low"]), "high": r1(alb["high"]),
            "action": alb["action"], "chronic": alb["chronicity_met"],
            "resolve": None if not alb["next_sample_resolves"] else r4(alb["next_sample_resolves"]["first_morning"]),
        },
        "blood": {k: [r1(v.median), r1(v.low), r1(v.high), bool(v.measured), v.source] for k, v in a.blood.items() if k in ("egfr", "hba1c", "potassium", "nt_probnp", "non_hdl")},
        "pG60": r4(a.p_egfr_below_60),
        "joint": [[r4(max(0.0, joint[i, j])) for j in range(3)] for i in range(6)],
        "pCkd": r4(a.p_ckd),
        "dm": a.diabetes, "pDm": r4(a.p_diabetes),
        "hf": a.heart_failure, "pBnp": r4(a.p_nt_probnp_high),
        "pAf": r4(a.p_af), "pEf": r4(a.p_low_ef),
        "pNew": r4(a.p_new_finding),
        "byTest": {t: r4(p) for t, p in a.finding_by_test.items()},
        "recs": [[x.test, x.reason] for x in a.recommendations],
        "alerts": list(a.alerts),
        "hr": None if a.home_risk is None else round(float(a.home_risk.ratio), 2),
        "cv": None,
    }
    if a.cv is not None:
        out["cv"] = {
            "score": r4(a.cv.score), "probs": [r4(p) for p in a.cv.probs], "rec": int(a.cv.recorded),
            "cat": int(a.cv.category), "pUp": r4(a.cv.p_up), "approx": bool(a.cv.approximate),
        }
    if a.home_bp is not None:
        b = a.home_bp
        out["bp"] = {"sbp": r1(b.sbp), "dbp": r1(b.dbp), "p": r4(max(b.p_sbp_high, b.p_dbp_high)), "valid": bool(b.valid), "msg": b.message, "n": b.n, "days": b.days}
    if a.egfr_trend is not None:
        t = a.egfr_trend
        lo, hi = t.interval("level")
        slo, shi = t.interval("slope")
        out["trend"] = {
            "level": r1(t.level), "low": r1(lo), "high": r1(hi), "slope": round(float(t.slope), 2),
            "slopeLow": round(float(slo), 2), "slopeHigh": round(float(shi), 2), "status": t.status,
            "traj": [[p["date"], r1(p["level"]), r1(p["low"]), r1(p["high"])] for p in (clean(x) for x in t.trajectory)],
            "meas": [[m.date.isoformat(), m.egfr] for m in t.measurements] if hasattr(t, "measurements") else None,
        }
    w = row_for("x", a)
    out["row"] = {"group": w.group, "p": r4(w.p_finding), "test": w.test, "how": w.how}
    return out


def belief(patient, samples_api):
    b = route._compute_albuminuria(route.AlbuminuriaIn.model_validate({"patient": patient, "samples": samples_api, "as_of": D0.isoformat()}))
    d = json.loads(b.model_dump_json())
    u, m = d["belief"]["uacr"], d["belief"]["mass"]
    pts = [[round(u[i], 2), round(m[i], 5)] for i in range(0, len(u), 3) if 1.0 <= u[i] <= 2500]
    return {"pts": pts, "median": r1(d["median"]), "low": r1(d["low"]), "high": r1(d["high"]), "p2": r4(d["p_a2_plus"])}


def trend(body):
    t = route._compute_egfr_trend(route.EgfrTrendIn.model_validate(body))
    d = json.loads(t.model_dump_json())
    return {
        "level": r1(d["level"]), "low": r1(d["level_low"]), "high": r1(d["level_high"]), "slope": round(d["slope"], 2),
        "slopeLow": round(d["slope_low"], 2), "slopeHigh": round(d["slope_high"], 2), "status": d["status"],
        "traj": [[p["date"], r1(p["level"]), r1(p["low"]), r1(p["high"])] for p in d["trajectory"]],
        "meas": [[m["date"], m["egfr"]] for m in d["measurements"]],
        "proj": [[p["date"], r1(p["level"]), r1(p["low"]), r1(p["high"])] for p in d["projection"]],
    }


def api_strip(day, a, c):
    return {"kind": "tira", "date": day, "albumin_mg_l": a, "creatinine_mg_dl": c}


def api_lab(day, uacr, creat):
    return {"kind": "laboratorio", "date": day, "uacr": uacr, "sample_type": "first_morning", "creatinine_mg_dl": creat}


def via_api(body):
    """Evaluación con la función de la ruta /api/model/assess (idéntica a la respuesta en vivo)."""
    model_in = route.AssessIn.model_validate(body)
    samples = route._model_samples(model_in.urine_samples)
    record = panel.ClinicalRecord(
        **{name: getattr(model_in, name) for name in route._RECORD_FIELDS},
        urine_samples=samples,
        measured=model_in.measured.model_dump(exclude_none=True),
    )
    a = panel.assess(record, as_of=model_in.as_of, population=model_in.population, detail=True)
    return compact_assess(a, samples)


def week_of_bp(sbp, dbp, start):
    rng = np.random.default_rng(int(sbp * 10 + dbp))
    out = []
    for d in range(7):
        for evening in (False, False, True, True):
            out.append(BPReading(start + timedelta(days=d), round(sbp + (3 if d == 0 else 0) + (2 if evening else -2) + rng.normal(0, 3.2)), round(dbp + (1 if evening else -1) + rng.normal(0, 2.4)), evening))
    return out


def bp_out(readings):
    b = summarize_home_bp(readings)
    by_day = {}
    for x in readings:
        by_day.setdefault(x.date.isoformat(), []).append((x.sbp, x.dbp))
    days = [[d, round(sum(s for s, _ in v) / len(v)), round(sum(t for _, t in v) / len(v))] for d, v in sorted(by_day.items())]
    return {"sbp": r1(b.sbp), "dbp": r1(b.dbp), "p": r4(max(b.p_sbp_high, b.p_dbp_high)), "valid": bool(b.valid), "msg": b.message, "n": b.n, "days": b.days, "byDay": days}


def yearly(values, last):
    n = len(values)
    return [EgfrMeasurement(last - timedelta(days=365 * (n - 1 - i)), v) for i, v in enumerate(values)]


def record_api(body):
    return {k: v for k, v in body.items()}


M = {}
LIVE = {}
AS_OF = D0.isoformat()

# ---------------------------------------------------------------- Julián
julian_samples = [api_strip("2026-07-14", 80, 100), api_strip("2026-07-15", 80, 100), api_strip("2026-07-16", 80, 100), api_strip("2026-11-02", 80, 100)]
julian_body = {
    "age": 62, "female": False, "bmi": 29.5, "waist": 104, "sbp": 146, "dbp": 88, "hypertension": True, "bp_meds": True,
    "high_cholesterol": True, "cholesterol_meds": True, "smoker_ever": True, "measured": {"total_cholesterol": 205, "hdl": 46},
    "urine_samples": julian_samples, "as_of": AS_OF,
}
M["julian"] = via_api(julian_body)
julian_alb_body = {"patient": {"age": 62, "female": False, "diabetes": False}, "samples": julian_samples, "as_of": AS_OF}
M["julian"]["belief"] = belief(julian_alb_body["patient"], julian_samples)
julian_trend_body = {
    "age": 62, "female": False, "diabetes": False, "p_a2": M["julian"]["alb"]["p"][1], "p_a3": M["julian"]["alb"]["p"][2],
    "measurements": [{"date": "2021-03-15", "egfr": 96}, {"date": "2022-04-20", "egfr": 94}, {"date": "2023-05-08", "egfr": 93}, {"date": "2024-05-06", "egfr": 90}],
    "as_of": AS_OF,
}
M["julian"]["trend"] = trend(julian_trend_body)
M["julian"]["bp"] = bp_out(week_of_bp(141, 87, date(2026, 11, 2)))
M["julian"]["pAf"] = r4(af_probability([RhythmCheck(date(2026, 11, 1) + timedelta(days=i), False) for i in range(14)], 62, female=False))
M["julian"]["pAfPrior"] = r4(af_prior(62, False))
LIVE["julian"] = {"assess": julian_body, "albuminuria": julian_alb_body, "trend": julian_trend_body}

# ---------------------------------------------------------------- Manuel
manuel = panel.ClinicalRecord(
    age=77, female=False, bmi=28.0, sbp=136, dbp=78, hypertension=True, bp_meds=True,
    rhythm_checks=[RhythmCheck(date(2026, 11, 12), True), RhythmCheck(date(2026, 11, 13), True)],
    measured={"egfr": 71, "total_cholesterol": 185, "hdl": 50},
    urine_samples=[UrineSample(date(2026, 9, 17), 12.0, FIRST_MORNING, creatinine_mg_dl=100)],
)
M["manuel"] = compact_assess(panel.assess(manuel, as_of=D0), manuel.urine_samples)
M["manuel"]["pAfPrior"] = r4(af_prior(77, False))
M["manuel"]["belief"] = belief({"age": 77, "female": False, "diabetes": False, "egfr": 71}, [api_lab("2026-09-17", 12.0, 100)])

# ---------------------------------------------------------------- Carmen
carmen_bp = week_of_bp(149, 91, date(2026, 11, 5))
carmen = panel.ClinicalRecord(
    age=59, female=True, bmi=27.0, waist=92, sbp=138, dbp=86, has_smartphone=True, home_bp=carmen_bp,
    measured={"total_cholesterol": 228, "hdl": 58, "egfr": 88},
    urine_samples=[UrineSample(date(2026, 10, 7), 7.0, FIRST_MORNING, creatinine_mg_dl=90)],
)
M["carmen"] = compact_assess(panel.assess(carmen, as_of=D0), carmen.urine_samples)
M["carmen"]["bp"] = bp_out(carmen_bp)
M["carmen"]["belief"] = belief({"age": 59, "female": True, "diabetes": False, "egfr": 88}, [api_lab("2026-10-07", 7.0, 90)])

# ---------------------------------------------------------------- Rosa
rosa = panel.ClinicalRecord(
    age=68, female=True, bmi=30.0, sbp=134, dbp=78, diabetes=True, diabetes_pills=True, hypertension=True, bp_meds=True,
    egfr_history=yearly([88, 79, 68, 60, 49], date(2026, 10, 27)), measured={"hba1c": 7.1, "total_cholesterol": 198, "hdl": 55},
    self_rated_health=4, dyspnea_on_stairs=True, walk_difficulty=1, stairs_difficulty=1, hospitalized_last_year=False, pulse=82,
)
M["rosa"] = compact_assess(panel.assess(rosa, as_of=D0), [])
M["rosa"]["trend"]["meas"] = [[m.date.isoformat(), m.egfr] for m in rosa.egfr_history]
M["rosa"]["belief"] = belief({"age": 68, "female": True, "diabetes": True, "egfr": 49}, [])

# ---------------------------------------------------------------- Ramón
ramon = panel.ClinicalRecord(
    age=56, female=False, bmi=34.0, waist=116, sbp=142, dbp=90, hypertension=True, smoker_now=True, prediabetes=True,
    has_smartphone=True, measured={"total_cholesterol": 240, "hdl": 38}, family_diabetes=True,
    self_rated_health=3, dyspnea_on_stairs=True, walk_difficulty=0, stairs_difficulty=0, hospitalized_last_year=False, pulse=78,
    home_glucose=[GlucoseReading(date(2026, 11, 10), 134.0, 10.0), GlucoseReading(date(2026, 11, 12), 141.0, 10.0)],
)
M["ramon"] = compact_assess(panel.assess(ramon, as_of=D0), [])
M["ramon"]["belief"] = belief({"age": 56, "female": False, "diabetes": False}, [])

# ---------------------------------------------------------------- Elena
elena = panel.ClinicalRecord(
    age=74, female=True, bmi=32.0, waist=106, sbp=142, dbp=80, hypertension=True, bp_meds=True,
    home_labs={"egfr": HomeLab(51.0, date(2026, 11, 11))}, measured={"total_cholesterol": 215, "hdl": 60},
)
M["elena"] = compact_assess(panel.assess(elena, as_of=D0), [])
M["elena"]["belief"] = belief({"age": 74, "female": True, "diabetes": False, "egfr": 59}, [])

# ---------------------------------------------------------------- Marta (en vivo)
marta_samples = [api_strip("2026-11-13", 30, 100), api_strip("2026-11-14", 30, 50)]
marta_body = {
    "age": 47, "female": True, "bmi": 31.0, "waist": 99, "sbp": 128, "dbp": 80, "diabetes": True, "diabetes_pills": True,
    "measured": {"hba1c": 7.4, "total_cholesterol": 190, "hdl": 52}, "urine_samples": marta_samples, "as_of": AS_OF,
}
M["marta"] = via_api(marta_body)
marta_alb = {"patient": {"age": 47, "female": True, "diabetes": True}, "samples": marta_samples, "as_of": AS_OF}
M["marta"]["belief"] = belief(marta_alb["patient"], marta_samples)
LIVE["marta"] = {"assess": marta_body, "albuminuria": marta_alb}

# ---------------------------------------------------------------- Pilar (en vivo)
pilar_samples = [api_strip("2026-11-12", 30, 100), api_strip("2026-11-13", 30, 100)]
pilar_body = {
    "age": 58, "female": True, "bmi": 26.0, "waist": 86, "sbp": 128, "dbp": 79,
    "measured": {"egfr": 88, "total_cholesterol": 212, "hdl": 61}, "urine_samples": pilar_samples, "as_of": AS_OF,
}
M["pilar"] = via_api(pilar_body)
pilar_alb = {"patient": {"age": 58, "female": True, "diabetes": False, "egfr": 88}, "samples": pilar_samples, "as_of": AS_OF}
M["pilar"]["belief"] = belief(pilar_alb["patient"], pilar_samples)
LIVE["pilar"] = {"assess": pilar_body, "albuminuria": pilar_alb}

# ---------------------------------------------------------------- Antonio (en vivo)
antonio_body = {"age": 81, "female": False, "bmi": 27.5, "sbp": 150, "dbp": 72, "hypertension": True, "bp_meds": True, "as_of": AS_OF}
M["antonio"] = via_api(antonio_body)
antonio_alb = {"patient": {"age": 81, "female": False, "diabetes": False}, "samples": [], "as_of": AS_OF}
M["antonio"]["belief"] = belief(antonio_alb["patient"], [])
LIVE["antonio"] = {"assess": antonio_body, "albuminuria": antonio_alb}

# ---------------------------------------------------------------- Francisco (en vivo)
francisco_samples = [api_lab("2026-09-22", 9.0, 110)]
francisco_body = {
    "age": 66, "female": False, "bmi": 31.0, "waist": 108, "sbp": 134, "dbp": 82, "hypertension": True, "bp_meds": True,
    "high_cholesterol": True, "cholesterol_meds": True, "smoker_ever": True,
    "measured": {"egfr": 78, "total_cholesterol": 196, "hdl": 41}, "urine_samples": francisco_samples, "as_of": AS_OF,
}
M["francisco"] = via_api(francisco_body)
francisco_alb = {"patient": {"age": 66, "female": False, "diabetes": False, "egfr": 78}, "samples": francisco_samples, "as_of": AS_OF}
M["francisco"]["belief"] = belief(francisco_alb["patient"], francisco_samples)
LIVE["francisco"] = {"assess": francisco_body, "albuminuria": francisco_alb}

# ---------------------------------------------------------------- Dolores (en vivo): diabética e hipertensa, orina nunca medida
dolores_body = {
    "age": 69, "female": True, "bmi": 30.0, "waist": 98, "sbp": 136, "dbp": 80, "diabetes": True, "diabetes_pills": True,
    "hypertension": True, "bp_meds": True, "measured": {"egfr": 66, "hba1c": 7.6, "total_cholesterol": 190, "hdl": 50}, "as_of": AS_OF,
}
M["dolores"] = via_api(dolores_body)
dolores_alb = {"patient": {"age": 69, "female": True, "diabetes": True, "egfr": 66}, "samples": [], "as_of": AS_OF}
M["dolores"]["belief"] = belief(dolores_alb["patient"], [])
LIVE["dolores"] = {"assess": dolores_body, "albuminuria": dolores_alb}

# ---------------------------------------------------------------- Andrés
andres = panel.ClinicalRecord(
    age=70, female=False, bmi=28.0, sbp=132, dbp=76, hypertension=True, bp_meds=True, cholesterol_meds=True, high_cholesterol=True,
    measured={"egfr": 74, "total_cholesterol": 168, "hdl": 44},
    urine_samples=[UrineSample(date(2026, 10, 1), 15.0, FIRST_MORNING, creatinine_mg_dl=105)],
    heart_checks=[HeartCheck(date(2026, 11, 9), 9.6, "ecg")],
)
M["andres"] = compact_assess(panel.assess(andres, as_of=D0), andres.urine_samples)
M["andres"]["belief"] = belief({"age": 70, "female": False, "diabetes": False, "egfr": 74}, [api_lab("2026-10-01", 15.0, 105)])

OUT.write_text(json.dumps({"model": M, "live": LIVE}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("bytes", OUT.stat().st_size)
for k, v in M.items():
    print(k, v["row"], "| alb", v["alb"]["status"], v["alb"]["p2"], v["alb"]["median"], "| cv", v["cv"], "| hr", v["hr"], "| trend", (v.get("trend") or {}).get("slope"))
