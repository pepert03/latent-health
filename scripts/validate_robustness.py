"""Comprobaciones de robustez con personas reales de NHANES (partición de test).

1. FG y albuminuria juntos: ¿mejora dejar de tratarlos como independientes?
2. Calibración por sexo y edad del filtro y del panel.
3. Curvas de decisión: ¿con los umbrales elegidos el modelo ayuda más que pedir la prueba a
   todos o a nadie?

Uso:
    uv run python scripts/validate_robustness.py
Escribe reports/robustez.md.
"""

from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import log_loss, roc_auc_score

from latenthealth.albuminuria import DEFAULT_PARAMS_PATH, AlbuminuriaParams
from latenthealth.albuminuria.model import FIRST_MORNING, RANDOM, Observations, covariates, dilution, make_grid, posterior, prob_new_sample_above
from latenthealth.assessment import assess, warm_up
from latenthealth.cohort import record_from_row
from latenthealth.decision import Thresholds, avoided_tests_per_100, decision_curve
from latenthealth.nhanes import is_test, load_pairs
from latenthealth.panel import load_panel
from latenthealth.panel.data import load_heart

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "robustez.md"
PANEL = ROOT / "models" / "panel"
AGE_BANDS = (("< 50", 0, 50), ("50-64", 50, 65), ("≥ 65", 65, 200))


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


# --- 1. FG y albuminuria juntos ---


def joint_block(lines: list[str]) -> None:
    panel = load_panel(cycles=("2009-2010",))
    pairs = load_pairs().set_index("seqn")
    d = panel[is_test(panel.seqn) & np.isfinite(panel.log_uacr_morning) & np.isfinite(panel.egfr)].reset_index(drop=True)
    low = d.egfr.to_numpy() < 60
    alb = d.log_uacr_morning.to_numpy() >= np.log(30.0)
    both, either = low & alb, low | alb
    # Riesgo KDIGO alto o muy alto: G3a con A2 o más, G3b o peor, o A3.
    a3 = d.log_uacr_morning.to_numpy() >= np.log(300.0)
    high = (low & alb) | (d.egfr.to_numpy() < 45) | a3

    modes = {"independent": "Independientes (como antes)", "panel": "Panel con orina × filtro por categoría de FG", "bayes": "Panel sin orina, actualizado por la orina (Bayes)"}
    rows, cal = [], []
    records = [record_from_row(r, urine=True, censored=bool(pairs.censored_random.get(r.seqn, False))) for r in d.itertuples()]
    warm_up(records, "nhanes")
    for mode, label in modes.items():
        p_both, p_either, p_high, p_low = [], [], [], []
        for record in records:
            a = assess(record, population="nhanes", joint=mode, detail=False)
            j = a.kdigo_joint
            p_both.append(j[2:, 1:].sum())
            p_either.append(1.0 - j[:2, 0].sum())
            p_high.append(j[2, 1:].sum() + j[3:, :].sum() + j[:2, 2].sum())
            p_low.append(j[2:, :].sum())
        clip = lambda p: np.clip(np.asarray(p), 1e-4, 1 - 1e-4)  # noqa: E731
        rows.append(
            [
                label,
                num(log_loss(both, clip(p_both))),
                num(log_loss(high, clip(p_high))),
                num(log_loss(either, clip(p_either))),
                num(log_loss(low, clip(p_low))),
                num(roc_auc_score(high, p_high)),
            ]
        )
        cal.append([label, pct(both.mean()), pct(np.mean(p_both)), pct(high.mean()), pct(np.mean(p_high)), pct(low.mean()), pct(np.mean(p_low))])
        print(mode, rows[-1][1:], cal[-1][1:], flush=True)

    lines += [
        "## 1. Filtrado glomerular y albuminuria juntos",
        "",
        f"{len(d)} personas de test de NHANES 2009-2010. El sistema recibe la historia clínica y la muestra de orina "
        f"aleatoria, sin la analítica de sangre. Hay {int(low.sum())} personas con FG < 60, {int(alb.sum())} con "
        f"albuminuria, {int(both.sum())} con las dos cosas y {int(high.sum())} de riesgo KDIGO alto o muy alto: con tan "
        "pocos casos conjuntos, diferencias pequeñas entre filas no significan nada. "
        "Se compara lo que predice con el FG real y con la primera orina de la "
        "mañana de esa persona (una sola muestra, así que como referencia de la albuminuria tiene ruido; afecta por igual "
        "a las tres formas de combinar).",
        "",
        "Pérdida logarítmica de cada suceso (más baja es mejor):",
        "",
        *table(
            ["Cómo se combinan", "FG < 60 y albuminuria", "Riesgo KDIGO alto o muy alto", "FG < 60 o albuminuria", "FG < 60", "AUC del riesgo alto"],
            rows,
        ),
        "Proporción observada frente a la media predicha:",
        "",
        *table(
            ["Cómo se combinan", "Ambos: observado", "predicho", "Riesgo alto: observado", "predicho", "FG < 60: observado", "predicho"],
            cal,
        ),
    ]


# --- 2. Calibración por sexo y edad ---


def subgroup_rows(name, event, p, female, age) -> list[list[str]]:
    rows = []
    for sex, sex_label in ((False, "Hombres"), (True, "Mujeres")):
        for band, lo, hi in AGE_BANDS:
            m = (female == sex) & (age >= lo) & (age < hi)
            n = int(m.sum())
            if n < 30:
                continue
            obs, pred = event[m].mean(), p[m].mean()
            se = np.sqrt(max(np.mean(p[m] * (1 - p[m])), 1e-9) / n)
            off = abs(obs - pred) > 2 * se and abs(obs - pred) > 0.02
            rows.append([name, sex_label, band, n, pct(obs), pct(pred), "desviado" if off else "bien"])
    return rows


def calibration_block(lines: list[str]) -> None:
    rows = []
    # Filtro: dada la muestra aleatoria, ¿sale la primera de la mañana ≥ 30?
    pairs = load_pairs()
    t = pairs[is_test(pairs.seqn) & pairs.uacr_random.notna() & pairs.uacr_morning.notna()].reset_index(drop=True)
    params = AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)
    x, _ = make_grid(400)
    Z = covariates(t.age, t.female, t.diabetes, t.egfr)
    obs = [Observations(np.log(t.uacr_random.to_numpy(float)), t.censored_random.to_numpy(bool), RANDOM, dilution(t.ucr_random.to_numpy(float)))]
    p = prob_new_sample_above(params, Z, posterior(params, Z, obs, x), FIRST_MORNING, 30.0, x)
    rows += subgroup_rows("Primera orina ≥ 30 dada la aleatoria", t.uacr_morning.to_numpy() >= 30, p, t.female.to_numpy(bool), t.age.to_numpy())

    panel = load_panel()
    test = panel[is_test(panel.seqn)]
    for target, label, threshold, below, subset in (
        ("egfr", "FG < 60 (historia y orina)", 60.0, True, None),
        ("hba1c", "HbA1c ≥ 6,5 % sin diagnóstico de diabetes", 6.5, False, lambda d: d.dx_diabetes == 0),
    ):
        d = test[np.isfinite(test[target])]
        if subset is not None:
            d = d[subset(d)]
        bundle = joblib.load(PANEL / f"{target}__historia_clínica_y_orina.joblib")
        cdf = bundle["model"].cdf(d[bundle["features"]].to_numpy(float), threshold)
        p = cdf if below else 1 - cdf
        event = (d[target].to_numpy() < threshold) if below else (d[target].to_numpy() >= threshold)
        rows += subgroup_rows(label, event, p, d.female.to_numpy() == 1, d.age.to_numpy())

    heart = load_heart()
    d = heart[is_test(heart.seqn) & (heart.dx_heart_failure == 0)]
    bundle = joblib.load(PANEL / "log_nt_probnp__historia_clínica_y_orina.joblib")
    p = 1 - bundle["model"].cdf(d[bundle["features"]].to_numpy(float), np.log(125.0))
    rows += subgroup_rows("NT-proBNP ≥ 125 sin insuficiencia cardíaca", d.log_nt_probnp.to_numpy() >= np.log(125.0), p, d.female.to_numpy() == 1, d.age.to_numpy())

    bad = sum(r[-1] == "desviado" for r in rows)
    lines += [
        "## 2. Calibración por sexo y edad",
        "",
        "Para cada grupo, la proporción real del suceso frente a la probabilidad media que da el modelo. Se marca "
        "\"desviado\" si la diferencia pasa de dos errores típicos y de dos puntos porcentuales.",
        "",
        *table(["Suceso", "Sexo", "Edad", "n", "Observado", "Predicho", "Calibración"], rows),
        f"Grupos desviados: {bad} de {len(rows)}.",
        "",
    ]


# --- 3. Curvas de decisión ---


def decision_block(lines: list[str]) -> None:
    thresholds = Thresholds()
    panel = load_panel()
    test = panel[is_test(panel.seqn)]
    heart = load_heart()
    heart_test = heart[is_test(heart.seqn) & (heart.dx_heart_failure == 0)]
    cases = [
        ("Pedir creatinina por P(FG < 60)", test[np.isfinite(test.egfr)], "egfr", 60.0, True, thresholds.creatinine, (0.02, 0.05, 0.10, 0.20)),
        (
            "Pedir HbA1c por P(≥ 6,5 %) sin diagnóstico",
            test[np.isfinite(test.hba1c) & (test.dx_diabetes == 0)],
            "hba1c",
            6.5,
            False,
            thresholds.hba1c,
            (0.02, 0.05, 0.10, 0.20),
        ),
        ("Pedir NT-proBNP por P(≥ 125)", heart_test, "log_nt_probnp", np.log(125.0), False, thresholds.nt_probnp, (0.10, 0.20, 0.30, 0.40)),
        (
            "Pedir la orina por P(albuminuria) con la historia",
            test[np.isfinite(test.log_uacr_morning)],
            "log_uacr_morning",
            np.log(30.0),
            False,
            0.05,
            (0.02, 0.05, 0.10, 0.20),
        ),
    ]
    rows = []
    for label, d, target, cut, below, chosen, grid in cases:
        bundle = joblib.load(PANEL / f"{target}__historia_clínica.joblib")
        cdf = bundle["model"].cdf(d[bundle["features"]].to_numpy(float), cut)
        p = cdf if below else 1 - cdf
        event = (d[target].to_numpy() < cut) if below else (d[target].to_numpy() >= cut)
        curve = decision_curve(event, p, grid)
        for t, model, everyone in zip(curve["umbral"], curve["modelo"], curve["todos"]):
            asked = float(np.mean(p >= t))
            found = float(event[p >= t].sum() / max(event.sum(), 1))
            mark = " (elegido)" if abs(t - chosen) < 1e-9 else ""
            rows.append(
                [
                    label,
                    pct(t, 0) + mark,
                    f"{1 / t:.0f}".replace(".", ","),
                    pct(asked, 0),
                    pct(found, 0),
                    num(model, 4),
                    num(max(everyone, 0.0), 4),
                    f"{avoided_tests_per_100(event, p, t):.0f}",
                ]
            )
    lines += [
        "## 3. Umbrales por utilidad clínica",
        "",
        "Un umbral de probabilidad equivale a aceptar un número de pruebas por caso encontrado (5 % = 20 pruebas). "
        "Para cada umbral: a qué proporción de personas se le pediría la prueba, qué proporción de los casos se "
        "encontraría, el beneficio neto del modelo frente a la mejor alternativa simple (pedirla a todos o a nadie) y "
        "cuántas pruebas ahorra el modelo por cada 100 personas sin perder beneficio. Modelos de historia clínica, sin "
        "orina, en la partición de test.",
        "",
        *table(
            ["Decisión", "Umbral", "Pruebas por caso", "Se pide a", "Casos encontrados", "Beneficio neto", "Mejor alternativa", "Pruebas ahorradas por 100"],
            rows,
        ),
    ]


def main() -> None:
    lines = [
        "# Robustez",
        "",
        "Generado por `scripts/validate_robustness.py` con la partición de test de NHANES (personas que los modelos no "
        "vieron al ajustarse). Modelos sin recalibrar a España, porque la referencia es NHANES.",
        "",
    ]
    joint_block(lines)
    calibration_block(lines)
    decision_block(lines)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
