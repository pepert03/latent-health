"""Diabetes sin diagnosticar: glucómetro en casa frente al cuestionario FINDRISC.

Datos: NHANES 2005-2018. Referencia: HbA1c ≥ 6,5 % en personas sin diabetes diagnosticada ni
tratamiento. Se compara, en las mismas personas y con validación cruzada:

- FINDRISC, el cuestionario que se usa en España para decidir a quién hacer el análisis,
- la historia clínica, la historia con la orina, y
- lo mismo con una glucosa capilar (la de laboratorio de NHANES con el error de un glucómetro)
  y las horas que llevaba sin comer.

Guarda models/panel/hba1c__casa.joblib (la HbA1c estimada que usa la ficha del paciente cuando
hay una glucosa de casa) y escribe reports/diabetes_en_casa.md.

Uso:
    uv run python scripts/fit_diabetes_home.py
"""

from pathlib import Path

import joblib
import numpy as np

from latenthealth.decision import Thresholds
from latenthealth.diabetes import BLOCKS, DIABETES_HBA1C, GLUCOSE, HISTORY, URINE, findrisc, load_diabetes, undiagnosed
from latenthealth.outcomes import mask_blocks
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, difference_interval
from latenthealth.panel import BinnedDistributionRegressor

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "panel"
REPORT = ROOT / "reports" / "diabetes_en_casa.md"
FOLDS = 5
THRESHOLDS = [5.7, 6.5, 7.0, 8.0]
FINDRISC = "FINDRISC (cuestionario que se usa hoy)"
SETS = {
    "Historia clínica": HISTORY,
    "Historia y orina": HISTORY + URINE,
    "Solo el glucómetro": GLUCOSE,
    "Historia y glucómetro": HISTORY + GLUCOSE,
    "Historia, orina y glucómetro": HISTORY + URINE + GLUCOSE,
}
BEST = "Historia, orina y glucómetro"
# Predictores del modelo del producto: los de la ficha del paciente más los de casa.
PRODUCT = HISTORY + ["dx_diabetes", "insulin", "diabetes_pills"] + URINE + GLUCOSE


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def out_of_fold(e, features) -> np.ndarray:
    fold = e.seqn.to_numpy() % FOLDS
    p = np.full(len(e), np.nan)
    for k in range(FOLDS):
        model = BinnedDistributionRegressor(THRESHOLDS).fit(e.loc[fold != k, features], e.hba1c[fold != k])
        p[fold == k] = 1.0 - model.cdf(e.loc[fold == k, features].to_numpy(float), DIABETES_HBA1C)
    return p


def at_flag_rate(y, score, rate: float) -> tuple[float, float]:
    """Señalando a la proporción ``rate`` de más puntuación: sensibilidad y valor predictivo."""
    k = max(int(round(rate * len(y))), 1)
    top = np.argsort(-score, kind="stable")[:k]
    return float(y[top].sum() / y.sum()), float(y[top].mean())


def flagged_for_sensitivity(y, score, sensitivity: float) -> float:
    """Proporción de personas que hay que señalar para encontrar esa parte de los casos."""
    order = np.argsort(-score, kind="stable")
    found = np.cumsum(y[order]) / y.sum()
    return float((np.argmax(found >= sensitivity) + 1) / len(y))


def main() -> None:
    d = load_diabetes()
    needed = ["hba1c", "glucose", "fasting_hours", "bmi", "waist", "sbp", "dbp", "log_uacr", "family_diabetes"]
    complete = np.isfinite(d[needed]).all(axis=1).to_numpy()
    e = d[complete & undiagnosed(d)].reset_index(drop=True)
    y = (e.hba1c >= DIABETES_HBA1C).to_numpy()
    fasting = (e.fasting_hours >= 8).to_numpy()
    groups = {"Todos": np.ones(len(e), bool), "En ayunas (8 horas o más)": fasting, "Sin ayunas": ~fasting}
    print(f"{len(e)} personas sin diagnóstico; {int(y.sum())} con HbA1c ≥ 6,5 ({y.mean():.1%})", flush=True)

    scores = {FINDRISC: findrisc(e)}
    for name, feats in SETS.items():
        scores[name] = out_of_fold(e, feats)
        print(f"{name:32s} AUC {auc(y, scores[name]):.3f}", flush=True)
    boot = {g: bootstrap_auc(y[m], {k: v[m] for k, v in scores.items()}, n=400) for g, m in groups.items()}

    def row(name: str) -> list[str]:
        cells = [name]
        for g, m in groups.items():
            lo, hi = np.percentile(boot[g][name], [2.5, 97.5])
            cells.append(f"{num(auc(y[m], scores[name][m]))} ({num(lo, 2)}-{num(hi, 2)})")
        return cells

    def versus(a: str, b: str) -> list[str]:
        cells = [f"{a} − {b}"]
        for g in groups:
            mean, lo, hi = difference_interval(boot[g][a], boot[g][b])
            cells.append(f"{'+' if mean >= 0 else ''}{num(mean)} ({num(lo)} a {num(hi)})")
        return cells

    # Mismo esfuerzo que FINDRISC ≥ 15 y ≥ 12: a cuánta gente señalan y qué encuentran.
    fr = scores[FINDRISC]
    effort = []
    for cut in (15, 12):
        rate = float((fr >= cut).mean())
        effort.append([f"FINDRISC ≥ {cut}", pct(rate), pct((fr >= cut)[y].mean()), pct(y[fr >= cut].mean(), 1)])
        for name in ("Historia y orina", BEST):
            sens, ppv = at_flag_rate(y, scores[name], rate)
            effort.append([f"{name}, señalando a los mismos", pct(rate), pct(sens), pct(ppv, 1)])
        sens, ppv = at_flag_rate(y[fasting], scores[BEST][fasting], rate)
        effort.append([f"{BEST}, en ayunas", pct(rate), pct(sens), pct(ppv, 1)])
    need = [[name, pct(flagged_for_sensitivity(y, s, 0.8)), pct(flagged_for_sensitivity(y, s, 0.9))] for name, s in scores.items()]

    # El circuito en dos pasos, con los umbrales del producto: la glucosa capilar se le mide a
    # quien la historia deja con probabilidad suficiente (es lo que hay al decidir el kit) y el
    # análisis se pide a quien la sigue teniendo después de medirse.
    cuts = Thresholds()
    after = scores[BEST]

    def circuit(label: str, first: np.ndarray, measure: float, lab: float = cuts.hba1c) -> list[str]:
        measured = first >= measure
        analysed = measured & (after >= lab)
        found = int((analysed & y).sum())
        return [
            label, pct(measured.mean()), pct(measured[y].mean()), pct(analysed.mean()), pct(found / y.sum()),
            pct(y[analysed].mean(), 1), num(measured.sum() / found, 0),
        ]  # fmt: skip

    history = scores["Historia clínica"]
    lent = history >= cuts.home_glucose
    circuits = [
        ["FINDRISC ≥ 15 y análisis directo, sin medir la glucosa", "-", "-", pct((fr >= 15).mean()), pct((fr >= 15)[y].mean()), pct(y[fr >= 15].mean(), 1), "-"],
        circuit("Glucosa a todos", history, 0.0),
        circuit(f"Glucosa si la historia da {pct(cuts.home_glucose)} o más (el producto)", history, cuts.home_glucose),
        circuit(f"Glucosa si la historia y la orina dan {pct(cuts.home_glucose)} o más", scores["Historia y orina"], cuts.home_glucose),
        circuit("Glucosa si la historia da 5 % o más", history, 0.05),
    ]
    done_after_one = float((after[lent] < cuts.hba1c).mean())
    # Con la glucosa medida como en el producto, lo que cambia al mover el umbral del análisis.
    lab_rows = []
    for cut in (0.05, 0.03, 0.02, 0.01):
        analysed = lent & (after >= cut)
        mark = " (el producto)" if abs(cut - cuts.hba1c) < 1e-9 else ""
        lab_rows.append([pct(cut) + mark, pct(analysed.mean()), pct((analysed & y).sum() / y.sum()), pct(y[analysed].mean(), 1)])

    # ¿Una medida o varias? Todo lo anterior es con una sola. Repetir promedia el error del aparato:
    # el techo de eso es un glucómetro sin error, es decir, la glucosa de laboratorio.
    perfect = out_of_fold(e, HISTORY + URINE + ["glucose", "fasting_hours"])
    repeat_boot = bootstrap_auc(y, {"sin error": perfect, "una medida": after}, n=400)
    repeat_gain = difference_interval(repeat_boot["sin error"], repeat_boot["una medida"])

    # Regla simple con el glucómetro en ayunas.
    g = e.glucose_home.to_numpy()
    rules = []
    for cut in (100, 110, 126):
        pos = g[fasting] >= cut
        yf = y[fasting]
        rules.append([f"Glucosa en ayunas ≥ {cut} mg/dl", pct(pos.mean()), pct(pos[yf].mean()), pct((~pos[~yf]).mean()), pct(yf[pos].mean(), 1)])

    # Calibración del modelo completo.
    p = scores[BEST]
    bins = [(0, 0.01), (0.01, 0.03), (0.03, 0.10), (0.10, 0.30), (0.30, 0.60), (0.60, 1.01)]
    calibration = [
        [f"{pct(lo)} a {pct(min(hi, 1.0))}", int(m.sum()), pct(p[m].mean(), 1), pct(y[m].mean(), 1)]
        for lo, hi in bins
        if (m := (p >= lo) & (p < hi)).any()
    ]

    # Modelo del producto: HbA1c de cualquier adulto, con bloques borrados al azar para que sirva
    # tenga o no glucosa de casa y orina. Se entrena sin la quinta parte reservada.
    everyone = d[np.isfinite(d[needed + ["dx_diabetes"]]).all(axis=1)].reset_index(drop=True)
    train = mask_blocks(everyone[everyone.seqn % FOLDS != 0], np.random.default_rng(0), blocks=BLOCKS)
    product = BinnedDistributionRegressor(THRESHOLDS).fit(train[PRODUCT], train.hba1c)
    joblib.dump({"model": product, "features": PRODUCT, "target": "hba1c"}, MODELS / "hba1c__casa.joblib", compress=3)
    held = e[e.seqn % FOLDS == 0].reset_index(drop=True)
    y0 = (held.hba1c >= DIABETES_HBA1C).to_numpy()
    f0 = (held.fasting_hours >= 8).to_numpy()

    def product_auc(drop: list[str], mask=None) -> str:
        part = held.copy()
        for b in drop:
            part[BLOCKS[b]] = np.nan
        score = 1.0 - product.cdf(part[PRODUCT].to_numpy(float), DIABETES_HBA1C)
        m = np.ones(len(part), bool) if mask is None else mask
        return num(auc(y0[m], score[m]))

    product_rows = [
        ["Con glucosa en ayunas y orina", product_auc([], f0)],
        ["Con glucosa sin ayunas y orina", product_auc([], ~f0)],
        ["Con glucosa, sin orina", product_auc(["orina"])],
        ["Sin glucosa, con orina", product_auc(["glucosa"])],
        ["Sin glucosa ni orina", product_auc(["glucosa", "orina"])],
    ]

    lines = [
        "# Diabetes sin diagnosticar: glucómetro en casa frente a FINDRISC",
        "",
        f"Generado por `scripts/fit_diabetes_home.py`. Datos: NHANES 2005-2018, {len(e)} adultos sin diabetes "
        f"diagnosticada ni tratamiento y con todos los datos. Referencia: HbA1c ≥ 6,5 %, que tienen {int(y.sum())} "
        f"({pct(y.mean(), 1)}). Validación cruzada de cinco partes; entre paréntesis, el intervalo del 95 %.",
        "",
        "La glucosa es la de laboratorio con el error de un glucómetro doméstico (norma ISO 15197: desviación del 7,5 %). "
        f"La mitad de las personas ({pct(fasting.mean())}) estaba en ayunas de 8 horas o más; el modelo recibe también cuántas "
        "horas llevaba sin comer.",
        "",
        "## Capacidad de encontrar la diabetes oculta (AUC)",
        "",
        *table(["Lo que se usa", *groups], [row(n) for n in scores]),
        *table(
            ["Diferencia de AUC en las mismas personas", *groups],
            [versus(BEST, FINDRISC), versus("Historia clínica", FINDRISC), versus("Historia y orina", "Historia clínica"), versus(BEST, "Historia y orina"), versus(BEST, "Solo el glucómetro")],
        ),
        "## Con el mismo esfuerzo que FINDRISC",
        "",
        "FINDRISC señala a quien pasa de un corte para hacerle el análisis. Señalando a la misma cantidad de gente, "
        "cuánta diabetes oculta se encuentra (sensibilidad) y qué parte de los señalados la tiene (VPP).",
        "",
        *table(["Criterio", "Personas señaladas", "Diabetes oculta encontrada", "VPP"], effort),
        "Personas a las que hay que hacer el análisis para encontrar el 80 % y el 90 % de la diabetes oculta:",
        "",
        *table(["Lo que se usa", "Para encontrar el 80 %", "Para encontrar el 90 %"], need),
        "## El circuito en dos pasos: a quién se le mide la glucosa",
        "",
        "En el producto la glucosa capilar no se le mide a todos. Se le mide a quien la historia clínica deja con una "
        f"probabilidad de diabetes oculta del {pct(cuts.home_glucose)} o más, y después se pide el análisis a quien, ya con "
        f"su glucosa, sigue en el {pct(cuts.hba1c)} o más. Como basta una medida, se hace en la farmacia más cercana o con "
        "el glucómetro del paciente, si lo tiene. Los porcentajes son sobre todas las personas sin diagnóstico.",
        "",
        *table(
            [
                "Criterio", "Se miden la glucosa", "Diabetes oculta entre ellos", "Se les pide el análisis",
                "Diabetes oculta encontrada", "VPP del análisis", "Medidas de glucosa por caso encontrado",
            ],  # fmt: skip
            circuits,
        ),
        "Cuánto se encuentra depende sobre todo del umbral del análisis. Con la glucosa medida como en el producto:",
        "",
        *table(["Se pide el análisis si la probabilidad, ya con la glucosa, es al menos", "Se les pide el análisis", "Diabetes oculta encontrada", "VPP del análisis"], lab_rows),
        "## ¿Una medida o varias?",
        "",
        "- **Todas las cifras de este informe son con una sola medida por persona.**",
        f"- Con esa medida, al {pct(done_after_one)} de quienes se la hacen el sistema les contesta que ya está; "
        "al resto se le pide el análisis.",
        f"- **Repetir para promediar el error del aparato apenas añade.** Con un glucómetro sin error, que es el techo de "
        f"repetir muchas veces, la AUC pasa de {num(auc(y, after))} a {num(auc(y, perfect))} "
        f"({'+' if repeat_gain[0] >= 0 else ''}{num(repeat_gain[0])}; intervalo {num(repeat_gain[1])} a {num(repeat_gain[2])}).",
        "- **Lo que no se puede medir aquí** es si repetirla en días distintos añade algo más, porque la glucosa de una "
        "persona cambia de un día a otro y NHANES tiene una sola por persona.",
        "- En el producto, una glucosa en ayunas de 126 mg/dl o más se repite otro día: con dos días sale como hallazgo, "
        "que es lo que exige el criterio diagnóstico.",
        "",
        "## Regla simple con el glucómetro",
        "",
        f"Entre las {int(fasting.sum())} personas en ayunas, sin modelo: solo el número del glucómetro.",
        "",
        *table(["Regla", "Personas señaladas", "Diabetes oculta encontrada", "Especificidad", "VPP"], rules),
        "## Calibración",
        "",
        "Probabilidad de HbA1c ≥ 6,5 % que da el modelo con historia, orina y glucómetro, frente a lo observado.",
        "",
        *table(["Probabilidad del modelo", "Personas", "Media predicha", "Observado"], calibration),
        "## El modelo que se usa en la ficha del paciente",
        "",
        "Un solo modelo estima la HbA1c de cualquier adulto y sirve con o sin glucosa de casa y con o sin orina (se "
        f"entrena borrando esos bloques al azar). En la quinta parte reservada ({len(held)} personas sin diagnóstico, "
        f"{int(y0.sum())} con diabetes oculta):",
        "",
        *table(["Datos disponibles", "AUC"], product_rows),
        "## Límites",
        "",
        "- **No es un hallazgo nuevo que la glucosa detecte la diabetes**: la glucosa en ayunas es uno de sus criterios "
        "diagnósticos. Lo que se mide aquí es cuánto se gana frente a lo que hoy se usa para cribar sin análisis.",
        "- **Glucosa de laboratorio con error simulado**, no lecturas reales de glucómetros en casa. La sangre capilar y "
        "la venosa difieren algo después de comer.",
        "- **Una sola medida por persona.** No se puede comprobar con estos datos cuánto mejora repetirla varios días.",
        "- **La referencia es una sola HbA1c.** El diagnóstico exige confirmarla.",
        "- FINDRISC sin la pregunta de fruta y verdura, que NHANES no tiene (vale 1 punto de 26).",
        "- Población de EE. UU.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
