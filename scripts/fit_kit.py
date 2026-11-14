"""Kit de casa: qué se pierde al ordenar el riesgo cardiovascular si se quita cada pieza.

Mismos datos, mismas personas y mismo desenlace que ``scripts/fit_outcomes.py`` (NHANES
1999-2014 con mortalidad enlazada; muerte por enfermedad del corazón o ictus en 10 años). Aquí
solo se comparan las combinaciones que deciden el kit: con y sin manguito, con y sin las cinco
preguntas, con y sin la tira de orina.

Escribe reports/kit_en_casa.md.

Uso:
    uv run python scripts/fit_kit.py
"""

from pathlib import Path

import numpy as np

from latenthealth.albuminuria import PHONE_STRIP
from latenthealth.outcomes import CAUSES, CV_CYCLES, FULL_10Y_CYCLES, TIERS, add_strip, complete_home, event_within, load_cohort
from latenthealth.outcomes.data import DEMOGRAPHICS, QUESTIONNAIRE, RECORD, STRIP
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, capture, difference_interval
from latenthealth.outcomes.model import HazardModel

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "kit_en_casa.md"
FOLDS = 5
FULL = "Kit completo: historia, cinco preguntas, manguito y tira"
EVERYONE = "Kit de todos: historia, cinco preguntas y tira (sin manguito)"
SETS = {
    FULL: TIERS["Historia, cuestionario, manguito y tira de orina"],
    EVERYONE: DEMOGRAPHICS + QUESTIONNAIRE + STRIP,
    "Historia y tira (sin preguntas ni manguito)": DEMOGRAPHICS + RECORD + STRIP,
    "Historia y cinco preguntas (sin tira ni manguito)": TIERS["Historia y cuestionario"],
    "Solo la historia clínica": TIERS["Historia clínica"],
}


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def out_of_fold(df, features, causes) -> np.ndarray:
    """Riesgo a 10 años de cada persona, predicho por un modelo entrenado sin su parte."""
    fold = df.seqn.to_numpy() % FOLDS
    risk = np.full(len(df), np.nan)
    for k in range(FOLDS):
        risk[fold == k] = HazardModel(features).fit(df[fold != k], causes).risk(df[fold == k])
    return risk


def main() -> None:
    causes = CAUSES["cardiovascular"]
    cohort = load_cohort(cycles=CV_CYCLES)
    d = add_strip(cohort[complete_home(cohort)], PHONE_STRIP).reset_index(drop=True)
    rows = (d.cycle.isin(FULL_10Y_CYCLES) & (d.age >= 40) & np.isfinite(d[["sbp", "total_cholesterol", "hdl"]]).all(axis=1)).to_numpy()
    ev = d[rows]
    y = event_within(d, causes)[rows]
    groups = {
        "Todos": np.ones(len(ev), bool),
        "Sin enfermedad cardiovascular previa": ((ev.dx_coronary != 1) & (ev.dx_stroke != 1) & (ev.dx_heart_failure != 1)).to_numpy(),
        "Con diabetes o hipertensión": ((ev.dx_diabetes == 1) | (ev.dx_hypertension == 1)).to_numpy(),
    }
    print(f"{len(ev)} personas, {int(y.sum())} muertes cardiovasculares en 10 años", flush=True)

    scores = {}
    for name, features in SETS.items():
        scores[name] = out_of_fold(d, features, causes)[rows]
        print(f"{name:62s} AUC {auc(y, scores[name]):.3f}", flush=True)
    boot = {g: bootstrap_auc(y[m], {k: v[m] for k, v in scores.items()}, n=500) for g, m in groups.items()}

    def row(name: str) -> list[str]:
        return [name, *[num(auc(y[m], scores[name][m])) for m in groups.values()], pct(capture(y, scores[name], 0.2)[1])]

    def versus(name: str) -> list[str]:
        cells = [name]
        for g in groups:
            mean, lo, hi = difference_interval(boot[g][name], boot[g][FULL])
            cells.append(f"{'+' if mean >= 0 else ''}{num(mean)} ({num(lo)} a {num(hi)})")
        return cells

    lines = [
        "# Kit de casa: qué se pierde al quitar cada pieza",
        "",
        "Generado por `scripts/fit_kit.py`. Mismos datos, personas y desenlace que `reports/riesgo_en_casa.md`: "
        f"{len(ev)} personas de 40 años o más de NHANES 1999-2008, {int(y.sum())} muertes por enfermedad del corazón o ictus "
        "en 10 años. Validación cruzada de cinco partes: a cada persona la predice un modelo que no la vio.",
        "",
        "La pregunta es si el kit puede llevar menos cosas **sin ordenar peor el riesgo**. La tira es la del proyecto "
        "(albúmina y creatinina, leída con el móvil, con su error simulado).",
        "",
        "## AUC con cada combinación",
        "",
        *table(["Lo que se usa", *groups, "Muertes en el 20 % de más riesgo"], [row(n) for n in SETS]),
        "## Diferencia con el kit completo",
        "",
        "En las mismas personas, con su intervalo del 95 % por remuestreo. Si el intervalo incluye el cero, quitar esas "
        "piezas no cambia el orden del riesgo de forma medible.",
        "",
        *table(["Lo que se usa, menos el kit completo", *groups], [versus(n) for n in SETS if n != FULL]),
        "## Cómo leerlo",
        "",
        "- Esto mide **el orden del riesgo**, no el diagnóstico. El manguito sigue siendo la forma de diagnosticar la "
        "hipertensión en casa y el glucómetro la de encontrar la diabetes oculta (`reports/diabetes_en_casa.md`): se "
        "prestan a quien su ficha se lo pide, no a todos.",
        "- Las cinco preguntas no cuestan nada, así que se mantienen aunque su aportación sea pequeña.",
        "- Población de EE. UU., tensión tomada por personal entrenado y orina de laboratorio con el error de la tira "
        "simulado: los mismos límites que `reports/riesgo_en_casa.md`.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
