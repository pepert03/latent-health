"""Entrena y evalúa el panel virtual de sangre.

- Analítica (FG, HbA1c, glucosa, potasio, no-HDL, hemoglobina): NHANES 2009-2018; UACR de la primera orina: 2009-2010.
- NT-proBNP (insuficiencia cardíaca): NHANES 1999-2004.

Para cada variable compara qué se puede estimar con distintos conjuntos de predictores
(solo orina, edad y sexo, historia clínica, historia clínica y orina...) en la partición
de test (20 %). Guarda los modelos de "historia clínica" y "historia clínica y orina" en
models/panel/ y escribe reports/panel_sangre.md.

Uso:
    uv run python scripts/fit_panel.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from latenthealth.nhanes import is_test
from latenthealth.panel import FEATURE_SETS, TARGETS, BinnedDistributionRegressor, load_panel
from latenthealth.panel.data import HEART_FEATURE_SETS, load_heart
from latenthealth.panel.evaluation import evaluate, event_probability, fmt, marginal_crps

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "panel"
REPORT = ROOT / "reports" / "panel_sangre.md"
SAVE_SETS = ("historia clínica", "historia clínica y orina")

# Umbrales clínicos: se usan como límites de tramo y para evaluar decisiones.
BIN_THRESHOLDS = {
    "egfr": [15, 30, 45, 60, 90],
    "hba1c": [5.7, 6.5, 7.0, 8.0],
    "glucose": [100, 126, 200],
    "potassium": [3.5, 5.0, 5.5],
    "non_hdl": [130, 160, 190],
    "hemoglobin": [12.0, 13.0],
    "log_uacr_morning": [np.log(30.0), np.log(300.0)],
    "log_nt_probnp": [np.log(125.0), np.log(300.0), np.log(450.0), np.log(900.0)],
}
# (etiqueta, umbral por fila, True si el evento es estar por debajo del umbral)
DECISIONS = {
    "egfr": [("FG < 60", lambda d: 60.0, True), ("FG < 45", lambda d: 45.0, True)],
    "hba1c": [("HbA1c ≥ 6,5 %", lambda d: 6.5, False), ("HbA1c ≥ 5,7 %", lambda d: 5.7, False)],
    "glucose": [("Glucosa ≥ 126", lambda d: 126.0, False)],
    "potassium": [("Potasio ≥ 5,0", lambda d: 5.0, False)],
    "non_hdl": [("No-HDL ≥ 190", lambda d: 190.0, False)],
    "hemoglobin": [("Anemia (Hb < 13 hombre, < 12 mujer)", lambda d: np.where(d.female == 1, 12.0, 13.0), True)],
    "log_uacr_morning": [("UACR ≥ 30", lambda d: np.log(30.0), False)],
    "log_nt_probnp": [
        ("NT-proBNP ≥ 125", lambda d: np.log(125.0), False),
        ("NT-proBNP ≥ 300", lambda d: np.log(300.0), False),
    ],
}
# Subgrupos de atención primaria donde se mide además la primera decisión.
SUBGROUPS = {
    "egfr": ("diabéticos o hipertensos", lambda d: (d.dx_diabetes == 1) | (d.dx_hypertension == 1)),
    "hba1c": ("sin diagnóstico de diabetes", lambda d: d.dx_diabetes == 0),
    "glucose": ("sin diagnóstico de diabetes", lambda d: d.dx_diabetes == 0),
    "log_uacr_morning": ("hipertensos sin diabetes", lambda d: (d.dx_hypertension == 1) & (d.dx_diabetes == 0)),
    "log_nt_probnp": ("sin diagnóstico de insuficiencia cardíaca", lambda d: d.dx_heart_failure == 0),
}
LABELS = {**TARGETS, "log_nt_probnp": "log NT-proBNP (pg/ml)"}


def run_target(target, data, feature_sets, lines, summary):
    d = data[np.isfinite(data[target])]
    train, test = d[~is_test(d.seqn)], d[is_test(d.seqn)]
    base = marginal_crps(train[target].to_numpy(), test[target].to_numpy())
    rows = {}
    for set_name, features in feature_sets.items():
        model = BinnedDistributionRegressor(BIN_THRESHOLDS[target]).fit(train[features], train[target])
        X = test[features].to_numpy(float)
        y = test[target].to_numpy()
        res = evaluate(model, X, test, y, DECISIONS[target])
        res["Mejora frente a la población"] = 1 - res["CRPS"] / base
        if target in SUBGROUPS:
            name, rule = SUBGROUPS[target]
            sub = rule(test).to_numpy()
            decision = DECISIONS[target][0]
            p, t = event_probability(model, X[sub], test[sub], decision)
            event = (y[sub] < t) if decision[2] else (y[sub] >= t)
            auc = roc_auc_score(event, p) if 0 < event.sum() < len(event) else np.nan
            res[f"{decision[0]} en {name}: AUC"] = auc
            res[f"{decision[0]} en {name}: prevalencia / media predicha"] = f"{event.mean():.1%} / {p.mean():.1%}"
        rows[set_name] = res
        if set_name in SAVE_SETS:
            path = MODELS / f"{target}__{set_name.replace(' ', '_')}.joblib"
            joblib.dump({"model": model, "features": features, "target": target}, path, compress=3)
        print(
            f"{target:18s} {set_name:26s} R²={res['R² (mediana)']:.3f} mejora={res['Mejora frente a la población']:.1%} "
            f"cobertura={res['Cobertura 80 %']:.2f}",
            flush=True,
        )
    table = pd.DataFrame(rows)
    lines += [f"## {LABELS[target]}", "", f"Test: {len(test)} personas · CRPS sin mirar al paciente: {fmt(base)}", ""]
    lines.append("| Métrica | " + " | ".join(table.columns) + " |")
    lines.append("|---|" + "---|" * len(table.columns))
    order = ["R² (mediana)", "Error absoluto medio", "CRPS", "Mejora frente a la población", "Cobertura 80 %", "Anchura 80 %"]
    order += [i for i in table.index if i not in order]
    for metric in order:
        lines.append(f"| {metric} | " + " | ".join(fmt(table.loc[metric, c]) for c in table.columns) + " |")
    lines.append("")
    key = [i for i in table.index if i.endswith(": AUC")][0]
    best = "historia clínica y orina"
    summary.append(
        [LABELS[target], DECISIONS[target][0][0]]
        + [fmt(rows[s][key]) if s in rows else "-" for s in ("edad y sexo", "historia clínica", best)]
        + [f"{rows[best]['Mejora frente a la población']:.0%}", fmt(rows[best]["Cobertura 80 %"])]
    )


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    lines, summary = [], []
    panel = load_panel()
    for target in TARGETS:
        run_target(target, panel, FEATURE_SETS, lines, summary)
    heart = load_heart()
    run_target("log_nt_probnp", heart, HEART_FEATURE_SETS, lines, summary)

    header = [
        "# Panel virtual: qué se puede estimar sin analítica de sangre",
        "",
        "Generado por `scripts/fit_panel.py`. Datos: NHANES 2009-2018 (analítica, orina e historia "
        f"clínica, {len(panel)} adultos) y NHANES 1999-2004 (NT-proBNP, {len(heart)} adultos). Modelos "
        "entrenados con el 80 % y evaluados en el 20 % restante. Para cada variable el modelo da su "
        "distribución completa: mediana, intervalo del 80 % y probabilidad de pasar cada umbral clínico.",
        "",
        "- **CRPS**: error de la distribución predicha, en las unidades de la variable (más bajo es mejor). "
        "**Mejora frente a la población** = 1 - CRPS / CRPS de predecir la distribución de toda la población.",
        "- **Cobertura 80 %**: proporción de pacientes cuyo valor real cae en el intervalo del 80 % (debe rondar 0,80).",
        "- La orina de NHANES es solo albúmina, creatinina, volumen y flujo: no hay tira reactiva (glucosa, "
        "proteínas, sangre, densidad), que en la práctica añadiría información.",
        "",
        "## Resumen",
        "",
        "AUC de la primera decisión clínica de cada variable según lo que se sabe del paciente.",
        "",
        "| Variable | Decisión | Edad y sexo | Historia clínica | Historia clínica y orina | Mejora frente a la población | Cobertura 80 % |",
        "|---|---|---|---|---|---|---|",
        *["| " + " | ".join(r) + " |" for r in summary],
        "",
    ]
    REPORT.write_text("\n".join(header + lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
