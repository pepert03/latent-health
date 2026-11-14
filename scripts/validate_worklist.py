"""Valida la lista del cupo con personas reales de NHANES 2009-2010 (partición de test).

Se construye un cupo ficticio: a cada persona se le da al sistema solo su historia clínica
(sin orina ni creatinina) y se le pregunta a quién habría que medir primero. Después se mira
qué habría salido de verdad: su FG, su primera orina de la mañana y su SCORE2 reales.

El suceso es un **hallazgo nuevo**: su categoría de riesgo cardiovascular real (guía europea
de 2021) es más alta que la que consta, o tiene una enfermedad renal que no consta (FG < 60 o
albuminuria), o una HbA1c de diabetes sin diagnóstico. Se compara el orden del modelo con
ordenar por edad, por el SCORE2 y al azar.

Dos situaciones:
A. Los lípidos y la tensión ya constan (se conoce el SCORE2) y faltan la orina y la creatinina.
   Es la que aísla la enfermedad renal oculta.
B. No consta ninguna analítica.

Uso:
    uv run python scripts/validate_worklist.py
Escribe reports/lista_cupo.md.
"""

from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from latenthealth import cvrisk
from latenthealth.assessment import assess, warm_up
from latenthealth.cohort import record_from_row
from latenthealth.nhanes import is_test
from latenthealth.panel import load_panel

REPORT = Path(__file__).resolve().parents[1] / "reports" / "lista_cupo.md"
LIPIDS = ("total_cholesterol", "hdl")


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def true_category(r) -> tuple[int, float]:
    """Categoría real (guía europea de 2021) y SCORE2 real de una persona, con todo lo que midió NHANES."""
    g = int(np.searchsorted([-90.0, -60.0, -45.0, -30.0, -15.0], -r.egfr, side="left"))  # 0 = G1 ... 5 = G5
    a = int(r.log_uacr_morning >= np.log(30.0)) + int(r.log_uacr_morning >= np.log(300.0))
    organ = cvrisk.category_matrix(r.dx_diabetes == 1, (r.dx_coronary == 1) or (r.dx_stroke == 1))[g, a]
    score = cvrisk.score2(r.age, r.female == 1, r.smoker_now == 1, r.sbp, r.total_cholesterol, r.hdl, r.dx_diabetes == 1)
    return int(max(organ, cvrisk.score_category(r.age, score))), float(score)


def capture(event: np.ndarray, order: np.ndarray, share: float) -> tuple[float, float]:
    """Entre el ``share`` primero de la lista: proporción con el suceso y parte de todos los sucesos que recoge."""
    k = max(int(round(share * len(order))), 1)
    top = order[:k]
    return float(event[top].mean()), float(event[top].sum() / max(event.sum(), 1))


def scenario(d, labs: tuple[str, ...], title: str, lines: list[str]) -> None:
    rows = []
    records = [record_from_row(r, urine=False, labs=labs) for r in d.itertuples()]
    warm_up(records, "nhanes")
    for r, record in zip(d.itertuples(), records):
        a = assess(record, population="nhanes", detail=False)
        truth, score = true_category(r)
        kidney = (r.dx_kidney != 1) and (r.egfr < 60 or r.log_uacr_morning >= np.log(30.0))
        diabetes = (r.dx_diabetes != 1) and np.isfinite(r.hba1c) and r.hba1c >= 6.5
        rows.append((a.p_new_finding, a.cv.p_up, a.cv.recorded, truth, score, r.age, kidney, diabetes))
    p_new, p_up, recorded, truth, score, age, kidney, diabetes = (np.array(c) for c in zip(*rows))
    up = truth > recorded
    event = up | kidney.astype(bool) | diabetes.astype(bool)
    rng = np.random.default_rng(0)
    model = "Lista del modelo (probabilidad de hallazgo nuevo)"
    orders = {
        model: np.argsort(-p_new, kind="stable"),
        "Por edad, de mayor a menor": np.argsort(-age, kind="stable"),
        "Por SCORE2, de mayor a menor": np.argsort(-score, kind="stable"),
        "Al azar": rng.permutation(len(event)),
    }
    aucs = {
        model: roc_auc_score(event, p_new),
        "Por edad, de mayor a menor": roc_auc_score(event, age),
        "Por SCORE2, de mayor a menor": roc_auc_score(event, score),
        "Al azar": 0.5,
    }
    lines += [
        f"## {title}",
        "",
        f"{len(event)} personas. Tienen un hallazgo nuevo el {pct(event.mean(), 1)} ({int(event.sum())} personas): "
        f"enfermedad renal que no consta el {pct(kidney.mean(), 1)}, diabetes sin diagnosticar el {pct(diabetes.mean(), 1)} y "
        f"subida de categoría de riesgo el {pct(up.mean(), 1)}. Probabilidad media que da el modelo: {pct(p_new.mean(), 1)}.",
        "",
        "| Orden de la lista | AUC | Aciertos en el primer 10 % | Casos que recoge | Aciertos en el primer 20 % | Casos que recoge |",
        "|---|---|---|---|---|---|",
    ]
    for name, order in orders.items():
        p10, c10 = capture(event, order, 0.10)
        p20, c20 = capture(event, order, 0.20)
        auc = f"{aucs[name]:.2f}".replace(".", ",")
        lines.append(f"| {name} | {auc} | {pct(p10)} | {pct(c10)} | {pct(p20)} | {pct(c20)} |")
    # Calibración de la probabilidad por tramos.
    lines += [
        "",
        "Calibración de la probabilidad de hallazgo nuevo:",
        "",
        "| Probabilidad del modelo | Personas | Media predicha | Observado |",
        "|---|---|---|---|",
    ]
    for lo, hi in ((0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 1.01)):
        m = (p_new >= lo) & (p_new < hi)
        if m.sum():
            label = f"{pct(lo)} a {pct(min(hi, 1.0))}"
            lines.append(f"| {label} | {int(m.sum())} | {pct(p_new[m].mean(), 1)} | {pct(event[m].mean(), 1)} |")
    if up.sum() >= 10:
        lines += ["", f"Solo la subida de categoría de riesgo ({int(up.sum())} personas): AUC de su probabilidad, "
                  + f"{roc_auc_score(up, p_up):.2f}".replace(".", ",") + f"; media predicha {pct(p_up.mean(), 1)}, observada {pct(up.mean(), 1)}."]
    lines.append("")
    print(title, {k: round(v, 3) for k, v in aucs.items()}, "prevalencia", round(event.mean(), 3), flush=True)


def main() -> None:
    panel = load_panel(cycles=("2009-2010",))
    keep = (
        is_test(panel.seqn)
        & np.isfinite(panel.log_uacr_morning)
        & np.isfinite(panel.egfr)
        & np.isfinite(panel.total_cholesterol)
        & np.isfinite(panel.hdl)
        & np.isfinite(panel.sbp)
        & (panel.age >= 40)
    )
    d = panel[keep].reset_index(drop=True)
    lines = [
        "# Lista del cupo: validación con personas reales",
        "",
        "Generado por `scripts/validate_worklist.py`. Personas de 40 años o más de la partición de test de NHANES "
        "2009-2010, con la primera orina de la mañana como referencia de la albuminuria (una sola muestra: tiene ruido). "
        "Modelos sin recalibrar a España, porque la referencia es NHANES.",
        "",
        "El sistema recibe la historia clínica y dice qué probabilidad hay de que completar las pruebas dé un hallazgo "
        "nuevo. La lista ordena por esa probabilidad.",
        "",
    ]
    scenario(d, LIPIDS, "A. Con lípidos y tensión conocidos; faltan la orina y la creatinina", lines)
    scenario(d, (), "B. Sin ninguna analítica", lines)
    lines += [
        "## Límites",
        "",
        "- Población general de EE. UU., no un cupo español; pocas personas, así que las cifras del primer 10 % tienen "
        "mucho margen de error.",
        "- En la situación B el SCORE2 se aproxima con lípidos típicos; lo que consta es esa aproximación.",
        "- La referencia de la albuminuria es una sola muestra de la mañana, sin confirmar a los tres meses.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
