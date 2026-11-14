"""Insuficiencia cardíaca: ¿qué se puede saber desde casa?

El NT-proBNP es la analítica que se usa en primaria para descartar insuficiencia cardíaca
(por debajo de 125 pg/ml es muy improbable). No se puede medir en casa. Aquí se comprueba:

1. Si las respuestas del paciente (falta de aire, dificultad para caminar, salud percibida) y
   el pulso mejoran la estimación de quién lo tendrá alto, frente a la historia clínica sola.
2. Cuánto añade medir el NT-proBNP a lo que ya se sabe en casa para predecir quién muere del corazón.

Datos: NHANES 1999-2004 (los únicos con NT-proBNP), con mortalidad enlazada hasta 2019.
Guarda models/panel/log_nt_probnp__casa*.joblib y escribe reports/insuficiencia_cardiaca.md.

Uso:
    uv run python scripts/fit_heart_home.py
"""

from pathlib import Path

import joblib
import numpy as np

from latenthealth.outcomes import CAUSES, HOME_TIER, TIERS, complete_home, event_within, load_cohort, mask_blocks
from latenthealth.outcomes.data import DEMOGRAPHICS
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, brier, difference_interval
from latenthealth.outcomes.model import HazardModel
from latenthealth.panel import BinnedDistributionRegressor

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "panel"
REPORT = ROOT / "reports" / "insuficiencia_cardiaca.md"
FOLDS = 5
THRESHOLDS = [np.log(125.0), np.log(300.0), np.log(450.0), np.log(900.0)]

HISTORY = DEMOGRAPHICS + [
    "bmi", "waist", "sbp", "dbp", "dx_diabetes", "dx_prediabetes", "insulin", "diabetes_pills", "dx_hypertension",
    "bp_meds", "dx_high_cholesterol", "cholesterol_meds", "dx_heart_failure", "dx_coronary", "dx_stroke",
    "smoker_now", "smoker_ever",
]  # fmt: skip
SYMPTOMS = ["health", "dyspnea", "walk_difficulty", "stairs_difficulty", "hospitalized", "pulse", "pulse_irregular"]
URINE = ["log_uacr", "log_urine_albumin", "log_urine_creatinine"]
SETS = {
    "Historia clínica (como hasta ahora)": HISTORY,
    "Historia y lo que cuenta el paciente (síntomas y pulso)": HISTORY + SYMPTOMS,
    "Historia, síntomas, pulso y orina": HISTORY + SYMPTOMS + URINE,
    "Todo lo anterior y filtrado glomerular": HISTORY + SYMPTOMS + URINE + ["egfr"],
}
BASE, HOME, HOME_URINE = list(SETS)[:3]
SAVE = {"casa": HISTORY + SYMPTOMS, "casa_y_orina": HISTORY + SYMPTOMS + URINE}


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def out_of_fold_bnp(d, features, cut: float) -> np.ndarray:
    """P(NT-proBNP ≥ cut) de cada persona, por un modelo entrenado sin su parte."""
    fold = d.seqn.to_numpy() % FOLDS
    p = np.full(len(d), np.nan)
    for k in range(FOLDS):
        train = d[fold != k]
        model = BinnedDistributionRegressor(THRESHOLDS).fit(train[features], train.log_nt_probnp)
        p[fold == k] = 1.0 - model.cdf(d.loc[fold == k, features].to_numpy(float), np.log(cut))
    return p


def out_of_fold_risk(d, features, causes) -> np.ndarray:
    fold = d.seqn.to_numpy() % FOLDS
    risk = np.full(len(d), np.nan)
    for k in range(FOLDS):
        risk[fold == k] = HazardModel(features).fit(d[fold != k], causes).risk(d[fold == k])
    return risk


def main() -> None:
    d = load_cohort(cycles=("1999-2000", "2001-2002", "2003-2004"))
    # Solo personas con todos los datos de casa (un dato vacío en NHANES delata a alguien más frágil).
    d = d[np.isfinite(d.log_nt_probnp) & complete_home(d)].reset_index(drop=True)
    no_hf = (d.dx_heart_failure != 1).to_numpy()
    older = (d.age >= 60).to_numpy() & no_hf
    lines = [
        "# Insuficiencia cardíaca: qué se puede saber desde casa",
        "",
        f"Generado por `scripts/fit_heart_home.py`. Datos: NHANES 1999-2004, {len(d)} adultos con NT-proBNP medido y "
        "todos los datos de casa, con mortalidad enlazada hasta 2019. Validación cruzada de cinco partes; entre paréntesis, el intervalo del 95 %.",
        "",
        "El NT-proBNP es la analítica con la que en primaria se descarta la insuficiencia cardíaca: por debajo de "
        "125 pg/ml es muy improbable. No se puede medir en casa.",
        "",
    ]

    # 1. ¿Quién tendrá el NT-proBNP alto?
    blocks = []
    for cut in (125.0, 300.0):
        y = (d.log_nt_probnp >= np.log(cut)).to_numpy()
        probs = {name: out_of_fold_bnp(d, feats, cut) for name, feats in SETS.items()}
        boot = {g: bootstrap_auc(y[m], {k: v[m] for k, v in probs.items()}, n=400) for g, m in (("sin", no_hf), ("mayores", older))}
        rows = []
        for name, p in probs.items():
            cells = [name]
            for g, m in (("sin", no_hf), ("mayores", older)):
                lo, hi = np.percentile(boot[g][name], [2.5, 97.5])
                cells.append(f"{num(auc(y[m], p[m]))} ({num(lo, 2)}-{num(hi, 2)})")
            cells.append(num(brier(y[no_hf], p[no_hf]), 4))
            rows.append(cells)
        gains = []
        for g, label in (("sin", "sin insuficiencia cardíaca diagnosticada"), ("mayores", "de 60 años o más")):
            mean, lo, hi = difference_interval(boot[g][HOME], boot[g][BASE])
            gains.append(f"{label}, {'+' if mean >= 0 else ''}{num(mean)} ({num(lo)} a {num(hi)})")
        blocks.append((cut, y, rows, gains, probs))
        print(f"NT-proBNP ≥ {cut:.0f}:", [(r[0][:30], r[1]) for r in rows], flush=True)
    for cut, y, rows, gains, _ in blocks:
        lines += [
            f"## ¿Quién tendrá el NT-proBNP por encima de {cut:.0f} pg/ml?",
            "",
            f"Lo tiene el {pct(y[no_hf].mean())} de las {int(no_hf.sum())} personas sin insuficiencia cardíaca diagnosticada "
            f"y el {pct(y[older].mean())} de las {int(older.sum())} de 60 años o más.",
            "",
            *table(["Lo que se usa", "AUC sin diagnóstico previo", "AUC en 60 años o más", "Error cuadrático"], rows),
            "Ganancia de AUC al añadir los síntomas y el pulso a la historia: " + "; ".join(gains) + ".",
            "",
        ]

    # 2. ¿Cuánto añade medirlo para saber quién muere del corazón?
    ev_rows = (d.age >= 40).to_numpy()
    home = [f for f in TIERS[HOME_TIER]]
    result_rows = []
    for outcome, label in (("corazon", "Muerte por enfermedad del corazón"), ("cardiovascular", "Muerte por corazón o ictus")):
        causes = CAUSES[outcome]
        y = event_within(d, causes)[ev_rows]
        risks = {
            "Edad, sexo y NT-proBNP medido": out_of_fold_risk(d, DEMOGRAPHICS + ["log_nt_probnp"], causes)[ev_rows],
            "Lo de casa (historia, cuestionario, manguito y orina)": out_of_fold_risk(d, home, causes)[ev_rows],
            "Lo de casa y NT-proBNP medido": out_of_fold_risk(d, home + ["log_nt_probnp"], causes)[ev_rows],
        }
        boot = bootstrap_auc(y, risks, n=400)
        names = list(risks)
        mean, lo, hi = difference_interval(boot[names[2]], boot[names[1]])
        for name in names:
            blo, bhi = np.percentile(boot[name], [2.5, 97.5])
            result_rows.append([label, name, f"{num(auc(y, risks[name]))} ({num(blo, 2)}-{num(bhi, 2)})"])
        result_rows.append([label, "Lo que añade el NT-proBNP a lo de casa", f"{'+' if mean >= 0 else ''}{num(mean)} ({num(lo)} a {num(hi)})"])
        print(label, int(y.sum()), "sucesos", [(n[:25], round(auc(y, r), 3)) for n, r in risks.items()], flush=True)
        n_events = int(y.sum())
    lines += [
        "## ¿Cuánto añade medir el NT-proBNP a lo que ya se sabe en casa?",
        "",
        f"Muerte en los 10 años siguientes entre las {int(ev_rows.sum())} personas de 40 años o más (todas con más de 15 "
        "años de seguimiento).",
        "",
        *table(["Desenlace", "Lo que se usa", "AUC"], result_rows),
    ]

    # Modelos para la evaluación del paciente: entrenados sin la quinta parte reservada.
    # Con bloques borrados al azar, para que sirvan aunque el paciente no haya contestado todo.
    blocks = {"cuestionario": SYMPTOMS[:5], "pulso": SYMPTOMS[5:], "peso y cintura": ["bmi", "waist"], "manguito": ["sbp", "dbp"]}
    train = mask_blocks(d[d.seqn % FOLDS != 0], np.random.default_rng(0), blocks=blocks)
    for name, feats in SAVE.items():
        model = BinnedDistributionRegressor(THRESHOLDS).fit(train[feats], train.log_nt_probnp)
        joblib.dump({"model": model, "features": feats, "target": "log_nt_probnp"}, MODELS / f"log_nt_probnp__{name}.joblib", compress=3)

    lines += [
        "## Límites",
        "",
        "- NHANES no tiene ecocardiograma ni diagnóstico confirmado de insuficiencia cardíaca: se predice una analítica "
        "y la muerte por enfermedad del corazón (que incluye el infarto), no la insuficiencia cardíaca en sí.",
        "- Sueros de 1999-2004 y cuestionario hecho por un entrevistador.",
        "- Faltan los síntomas más específicos (hinchazón de tobillos, dormir incorporado, subida rápida de peso), que "
        "NHANES no pregunta y que el paciente sí puede contar.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
