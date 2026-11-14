"""Cuánto de la gravedad de la insuficiencia cardíaca se ve desde casa, en pacientes españoles.

Datos: tabla clínica de MUSIC (PhysioNet, ODbL): 992 pacientes ambulatorios con insuficiencia
cardíaca de ocho hospitales españoles, seguidos una mediana de casi cinco años.

Tres preguntas, todas con validación cruzada de cinco partes:

1. ¿Quién muere en tres años? Se compara lo que ya está en la historia, lo que el paciente
   puede medir en casa (cómo se cansa, peso, tensión, pulso), y lo que exige ir al hospital
   (ECG, analítica, ecocardiograma, Holter).
2. ¿Quién tiene el NT-proBNP por encima de 1.000 ng/l sin sacarle sangre?
3. ¿Quién tiene la fracción de eyección reducida, con los números de un ECG?

Escribe reports/insuficiencia_cardiaca_espana.md.

Uso:
    uv run python scripts/validate_music.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from latenthealth.music import ECG, HOME, HOME_TIER, RECORD, TIERS, event_by, known_at, load_music
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, c_index, difference_interval

REPORT = Path(__file__).resolve().parents[1] / "reports" / "insuficiencia_cardiaca_espana.md"
FOLDS, YEARS = 5, 3.0
SKEWED = ["nt_probnp", "creatinine", "urea", "troponin", "ventricular_beats", "glucose"]


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def linear():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.3, max_iter=3000))


def boosting():
    return HistGradientBoostingClassifier(learning_rate=0.05, max_iter=150, max_depth=2, min_samples_leaf=20, l2_regularization=1.0, random_state=0)


def prepare(data: pd.DataFrame) -> pd.DataFrame:
    """Logaritmo de las variables muy asimétricas, para el modelo lineal."""
    out = data.copy()
    for name in SKEWED:
        out[name] = np.log1p(out[name].clip(lower=0))
    return out


def out_of_fold(data: pd.DataFrame, features: list[str], y: np.ndarray, train: np.ndarray, make) -> np.ndarray:
    """Puntuación de cada paciente por un modelo que no lo vio. Solo se entrena con ``train``."""
    fold = np.arange(len(data)) % FOLDS
    score = np.full(len(data), np.nan)
    for k in range(FOLDS):
        fit = (fold != k) & train
        model = make().fit(data.loc[fit, features], y[fit])
        score[fold == k] = model.predict_proba(data.loc[fold == k, features])[:, 1]
    return score


def interval(samples: np.ndarray) -> str:
    lo, hi = np.nanpercentile(samples, [2.5, 97.5])
    return f"{num(lo, 2)}-{num(hi, 2)}"


def tier_table(data: pd.DataFrame, y: np.ndarray, known: np.ndarray, tiers: dict[str, list[str]], survival: tuple | None = None):
    """Una fila por nivel: AUC con modelo lineal y con árboles, y el índice de concordancia si hay seguimiento."""
    scores, rows = {}, []
    for name, features in tiers.items():
        s_lin = out_of_fold(data, features, y, known, linear)
        s_tree = out_of_fold(data, features, y, known, boosting)
        scores[name] = s_lin
        row = [name, len(features), num(auc(y[known], s_lin[known])), num(auc(y[known], s_tree[known]))]
        if survival is not None:
            months, event = survival
            row.append(num(c_index(months, event, s_lin)))
        rows.append(row)
        print(row, flush=True)
    samples = bootstrap_auc(y[known], {k: v[known] for k, v in scores.items()}, n=1000)
    for row, name in zip(rows, tiers):
        row.insert(3, interval(samples[name]))
    return rows, scores, samples


def main() -> None:
    raw = load_music()
    raw = raw.sample(frac=1.0, random_state=0).reset_index(drop=True)  # las partes no deben depender del orden de inclusión
    data = prepare(raw)

    # 1. Muerte a tres años.
    known = known_at(raw, YEARS).to_numpy()
    death = event_by(raw, YEARS).to_numpy()
    months = (raw.years * 12).to_numpy()
    rows_death, scores, samples = tier_table(data, death, known, TIERS, survival=(months, raw.death.to_numpy()))
    home_vs_record = difference_interval(samples[HOME_TIER], samples["Historia clínica"])
    all_vs_home = difference_interval(samples["Todo, con ecocardiograma y Holter"], samples[HOME_TIER])
    lab_vs_home = difference_interval(samples["Lo anterior y analítica"], samples[HOME_TIER])

    cardiac = event_by(raw, YEARS, "cardiac_death").to_numpy()
    rows_cardiac, _, _ = tier_table(data, cardiac, known, TIERS)

    # Quién se lleva las muertes si se ordena por el modelo de casa.
    s = scores[HOME_TIER][known]
    order = np.argsort(-s)
    d = death[known][order]
    thirds = np.array_split(d, 3)
    capture = [["Tercio de más riesgo", len(thirds[0]), pct(thirds[0].mean()), pct(thirds[0].sum() / d.sum())],
               ["Tercio intermedio", len(thirds[1]), pct(thirds[1].mean()), pct(thirds[1].sum() / d.sum())],
               ["Tercio de menos riesgo", len(thirds[2]), pct(thirds[2].mean()), pct(thirds[2].sum() / d.sum())]]  # fmt: skip

    # Qué pesa de lo que se mide en casa (cada dato por separado).
    single = []
    labels = {"nyha": "Clase funcional III (se cansa con poco)", "sbp": "Tensión sistólica", "dbp": "Tensión diastólica", "bmi": "Índice de masa corporal",
              "heart_rate": "Frecuencia cardíaca en reposo", "irregular": "Pulso irregular (fibrilación auricular)", "age": "Edad"}  # fmt: skip
    for name in ["age", *HOME]:
        v = raw[name].to_numpy(dtype=float)
        ok = known & np.isfinite(v)
        a = auc(death[ok], v[ok])
        single.append([labels[name], num(max(a, 1 - a), 2), "más alta" if a > 0.5 else "más baja",
                       num(float(np.nanmedian(v[ok & death])), 1), num(float(np.nanmedian(v[ok & ~death])), 1)])  # fmt: skip

    # 2. NT-proBNP alto sin sacar sangre.
    has_bnp = raw.nt_probnp.notna().to_numpy()
    high = (raw.nt_probnp > 1000).to_numpy()
    bnp_tiers = {k: TIERS[k] for k in ("Edad y sexo", "Historia clínica", HOME_TIER, "Lo anterior y ECG")}
    rows_bnp, _, samples_bnp = tier_table(data, high, has_bnp, bnp_tiers)
    bnp_gain = difference_interval(samples_bnp[HOME_TIER], samples_bnp["Historia clínica"])

    # 3. Fracción de eyección reducida con los números de un ECG.
    has_ef = raw.lvef.notna().to_numpy()
    reduced = (raw.lvef <= 40).to_numpy()
    ef_tiers = {
        "Edad y sexo": ["age", "male"],
        "Pulso (frecuencia e irregularidad)": ["age", "male", "heart_rate", "irregular"],
        "Números del ECG (QRS, QT, PR, ondas Q)": ["age", "male", "heart_rate", "irregular", *ECG],
        "ECG, historia y medidas de casa": RECORD + HOME + ECG,
    }
    rows_ef, _, _ = tier_table(data, reduced, has_ef, ef_tiers)
    qrs = raw.qrs.to_numpy(dtype=float)
    ok = has_ef & np.isfinite(qrs)
    qrs_auc = auc(reduced[ok], qrs[ok])

    n = len(raw)
    lines = [
        "# Insuficiencia cardíaca en pacientes españoles: qué se ve desde casa",
        "",
        "Generado por `scripts/validate_music.py`. Datos: tabla clínica de "
        "[MUSIC](https://physionet.org/content/music-sudden-cardiac-death/1.0.1/) (PhysioNet, licencia ODbL): "
        f"{n} pacientes ambulatorios con insuficiencia cardíaca sintomática de ocho hospitales universitarios españoles "
        "(Murcia, Las Palmas, Madrid, Tarragona, Santiago, Barcelona, Mallorca y Sevilla), incluidos en 2003-2004 y seguidos "
        f"una mediana de {num(float(raw.years.median()), 1)} años. Murieron {int(raw.death.sum())}: {int(raw.pump_death.sum())} "
        f"por fallo de bomba, {int(raw.sudden_death.sum())} de muerte súbita y {int((raw.death & ~raw.cardiac_death).sum())} "
        "por causas no cardíacas.",
        "",
        f"Edad mediana {int(raw.age.median())} años, {pct(raw.male.mean())} hombres, {pct((raw.nyha == 3).mean())} en clase "
        f"funcional III, {pct((raw.lvef <= 40).mean())} con fracción de eyección del 40 % o menos, {pct(raw.rx_betablocker.mean())} "
        f"con betabloqueante. Solo el {pct((raw.nt_probnp < 125).mean())} tenía el NT-proBNP por debajo de 125 ng/l, el umbral "
        "con el que hoy se descarta la enfermedad.",
        "",
        "**Todos tienen la enfermedad**, así que esta cohorte no sirve para detectarla. Sirve para saber cuánto de su gravedad "
        "se ve con lo que el paciente puede medir en casa, y para comprobar en pacientes españoles lo aprendido con otros datos.",
        "",
        f"## 1. ¿Quién muere en {int(YEARS)} años?",
        "",
        f"De {int(known.sum())} pacientes con seguimiento suficiente murieron {int(death[known].sum())} ({pct(death[known].mean())}). "
        "Validación cruzada de cinco partes. Las medidas de casa son cuatro: cómo de pronto se cansa (clase funcional), el "
        "peso, la tensión y el pulso (frecuencia y si es irregular).",
        "",
        *table(["Lo que se usa", "Datos", "AUC (modelo lineal)", "Intervalo 95 %", "AUC (árboles)", "Concordancia con todo el seguimiento"], rows_death),
        f"- Las medidas de casa añaden {num(home_vs_record[0])} de AUC a la historia clínica (intervalo del 95 %: "
        f"{num(home_vs_record[1])} a {num(home_vs_record[2])}).",
        f"- La analítica, con el NT-proBNP, añade {num(lab_vs_home[0])} a lo de casa ({num(lab_vs_home[1])} a {num(lab_vs_home[2])}).",
        f"- Todo lo del hospital junto añade {num(all_vs_home[0])} a lo de casa ({num(all_vs_home[1])} a {num(all_vs_home[2])}).",
        "",
        "Solo muerte cardíaca (súbita o por fallo de bomba):",
        "",
        *table(["Lo que se usa", "Datos", "AUC (modelo lineal)", "Intervalo 95 %", "AUC (árboles)"], rows_cardiac),
        "### Ordenando a los pacientes con la historia y las medidas de casa",
        "",
        *table(["Grupo", "Pacientes", f"Mueren en {int(YEARS)} años", "Parte de todas las muertes"], capture),
        "### Cada medida de casa por separado",
        "",
        *table(["Medida", "AUC", "En quien muere", "Mediana en quien muere", "Mediana en quien vive"], single),
        "## 2. ¿Quién tiene el NT-proBNP por encima de 1.000 ng/l?",
        "",
        f"Lo tenía el {pct(high[has_bnp].mean())} de los {int(has_bnp.sum())} pacientes con el dato. Es un valor claramente "
        "alto: en consulta la enfermedad se descarta por debajo de 125.",
        "",
        *table(["Lo que se usa", "Datos", "AUC (modelo lineal)", "Intervalo 95 %", "AUC (árboles)"], rows_bnp),
        f"Las medidas de casa añaden {num(bnp_gain[0])} a la historia ({num(bnp_gain[1])} a {num(bnp_gain[2])}).",
        "",
        "## 3. ¿Quién tiene la fracción de eyección reducida?",
        "",
        f"Entre pacientes que ya tienen insuficiencia cardíaca, {pct(reduced[has_ef].mean())} tienen la fracción de eyección "
        "del 40 % o menos. Aquí no hay señal del ECG, solo los números que da el aparato.",
        "",
        *table(["Lo que se usa", "Datos", "AUC (modelo lineal)", "Intervalo 95 %", "AUC (árboles)"], rows_ef),
        f"La anchura del QRS sola separa con AUC {num(max(qrs_auc, 1 - qrs_auc), 2)}: más ancho con fracción de eyección reducida, "
        "la misma dirección que en los datos de Wuhan (`reports/fraccion_eyeccion.md`).",
        "",
        "## Límites",
        "",
        "- **Pacientes de consultas de insuficiencia cardíaca de hospital, de 2003-2004.** Hoy se tratan con fármacos que "
        "entonces no había (sacubitrilo-valsartán, inhibidores de SGLT2), y los de primaria son mayores y con más fracción "
        "de eyección conservada.",
        "- **Las \"medidas de casa\" las tomó personal sanitario** en la visita. La clase funcional la puso un cardiólogo; "
        "en casa saldría de preguntas y sería menos fina.",
        "- **Es pronóstico, no diagnóstico.** Dice a quién vigilar más entre los ya diagnosticados.",
        "- No se compara con la escala de riesgo publicada del estudio (necesita ecocardiograma, Holter y analítica); la "
        "última fila de la primera tabla hace de referencia de \"todo lo que midió el hospital\".",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
