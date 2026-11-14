"""Entrena y valida la señal de insuficiencia cardíaca en el pulso en reposo.

Datos: dos bases de PhysioNet con los latidos de 24 horas de 29 personas con insuficiencia
cardíaca (chf2db) y 54 en ritmo sinusal normal (nsr2db). De cada persona se toman 48 tramos
repartidos por el registro, como si fueran medidas sueltas del pulso de uno, dos o cinco
minutos, y un clasificador separa a los enfermos con las medidas de los intervalos.

Se evalúa por persona (validación cruzada de cinco partes, sin repartir a nadie entre partes):
una medida suelta, la media de siete (una semana) y los latidos degradados como los de una
cámara. Después se comprueba en los pacientes españoles de MUSIC, con el resumen de su Holter,
cuántos tienen el pulso "de enfermo" hoy que la mayoría toma betabloqueantes.

Guarda models/ritmo/ic_pulso.joblib y escribe reports/pulso_insuficiencia_cardiaca.md.

Uso:
    uv run python scripts/fit_pulse_hf.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from latenthealth.music import load_music
from latenthealth.outcomes.evaluation import auc
from latenthealth.pulse import FEATURES, MODEL_PATH, Subject, load_subjects, pulse_features, window_intervals, window_starts
from latenthealth.rhythm import MIN_INTERVALS, degrade

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "pulso_insuficiencia_cardiaca.md"
FOLDS, WINDOWS, SPECIFICITY = 5, 48, 0.90
MAIN_SECONDS = 120


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def measurements(subjects: list[Subject], seconds: float, rng=None) -> pd.DataFrame:
    """Una fila por medida del pulso: 48 tramos por persona. Con ``rng``, los latidos se degradan como los de una cámara."""
    rows = []
    for i, s in enumerate(subjects):
        beats = degrade(s.beats, rng) if rng is not None else s.beats
        for start in window_starts(s.beats, seconds, WINDOWS):
            row = pulse_features(window_intervals(beats, start, seconds))
            row["subject"] = i
            rows.append(row)
    return pd.DataFrame(rows)


def boosting() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(learning_rate=0.05, max_iter=200, max_leaf_nodes=8, min_samples_leaf=40, l2_regularization=1.0, random_state=0)


def simple():
    return make_pipeline(StandardScaler(), LogisticRegression())


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def out_of_fold(data: pd.DataFrame, features: list[str], sick: np.ndarray, fold: np.ndarray, make, test: pd.DataFrame | None = None) -> np.ndarray:
    """Puntuación de cada medida por un modelo que no vio a esa persona. ``test`` permite evaluar con otras medidas."""
    test = data if test is None else test
    y = sick[data.subject.to_numpy()]
    usable = (data.n >= MIN_INTERVALS).to_numpy()
    usable_test = (test.n >= MIN_INTERVALS).to_numpy()
    part = fold[data.subject.to_numpy()]
    score = np.full(len(test), np.nan)
    for k in range(FOLDS):
        model = make().fit(data.loc[(part != k) & usable, features], y[(part != k) & usable])
        rows = (fold[test.subject.to_numpy()] == k) & usable_test
        score[rows] = logit(model.predict_proba(test.loc[rows, features])[:, 1])
    return score


def per_person(data: pd.DataFrame, score: np.ndarray, sick: np.ndarray, k: int, rng, repeats: int = 200) -> tuple[float, float]:
    """AUC y sensibilidad (con la especificidad fijada) al promediar ``k`` medidas al azar de cada persona."""
    subject = data.subject.to_numpy()
    groups = [np.flatnonzero((subject == i) & np.isfinite(score)) for i in range(sick.size)]
    aucs, sens = [], []
    for _ in range(repeats):
        s = np.array([score[rng.choice(g, size=min(k, g.size), replace=False)].mean() for g in groups])
        aucs.append(auc(sick, s))
        sens.append(float((s[sick] > np.quantile(s[~sick], SPECIFICITY)).mean()))
    return float(np.mean(aucs)), float(np.mean(sens))


def day_summary(s: Subject) -> dict[str, float]:
    """Resumen de 24 horas como el de un Holter: solo intervalos entre latidos normales."""
    rr = np.diff(s.beats)
    valid = s.normal[1:] & s.normal[:-1] & (rr > 0.3) & (rr < 2.0)
    nn = rr[valid] * 1000.0
    pairs = valid[1:] & valid[:-1]
    change = np.diff(rr)[pairs] * 1000.0
    block = ((s.beats[1:][valid] - s.beats[0]) // 300).astype(int)
    means = pd.Series(nn).groupby(block).mean()
    return {"rr": float(nn.mean()), "sdnn": float(nn.std()), "sdann": float(means.std()), "rmssd": float(np.sqrt(np.mean(change**2))),
            "pnn50": float(100.0 * np.mean(np.abs(change) > 50.0))}  # fmt: skip


def main() -> None:
    subjects = load_subjects()
    sick = np.array([s.heart_failure for s in subjects])
    age = np.array([s.age for s in subjects])
    nyha = np.array([s.nyha or 0 for s in subjects])
    fold = np.empty(len(subjects), int)
    rng = np.random.default_rng(0)
    for group in (True, False):
        idx = rng.permutation(np.flatnonzero(sick == group))
        fold[idx] = np.arange(idx.size) % FOLDS
    print(f"{len(subjects)} personas, {int(sick.sum())} con insuficiencia cardíaca", flush=True)

    rows, scores = [], {}
    tables = {}
    for seconds in (60, MAIN_SECONDS, 300):
        tables[seconds] = measurements(subjects, seconds)
        scores[seconds] = out_of_fold(tables[seconds], FEATURES, sick, fold, boosting)
        one = per_person(tables[seconds], scores[seconds], sick, 1, rng)
        week = per_person(tables[seconds], scores[seconds], sick, 7, rng)
        label = f"Una medida de {seconds // 60} min"
        rows.append([label, num(one[0]), pct(one[1]), num(week[0]), pct(week[1])])
        print(rows[-1], flush=True)
    main_table, main_score = tables[MAIN_SECONDS], scores[MAIN_SECONDS]

    camera = measurements(subjects, MAIN_SECONDS, rng)
    camera_score = out_of_fold(camera, FEATURES, sick, fold, boosting)
    one, week = per_person(camera, camera_score, sick, 1, rng), per_person(camera, camera_score, sick, 7, rng)
    rows.append([f"{MAIN_SECONDS // 60} min, latidos degradados como los de una cámara (simulado)", num(one[0]), pct(one[1]), num(week[0]), pct(week[1])])
    shifted = out_of_fold(main_table, FEATURES, sick, fold, boosting, test=camera)
    one, week = per_person(camera, shifted, sick, 1, rng), per_person(camera, shifted, sick, 7, rng)
    rows.append([f"{MAIN_SECONDS // 60} min, entrenado con ECG y usado con cámara (simulado)", num(one[0]), pct(one[1]), num(week[0]), pct(week[1])])
    for name, features in (("Solo la frecuencia cardíaca", ["rate"]), ("Frecuencia y variación (SDNN)", ["rate", "sdnn"])):
        s = out_of_fold(main_table, features, sick, fold, simple)
        one, week = per_person(main_table, s, sick, 1, rng), per_person(main_table, s, sick, 7, rng)
        rows.append([f"{MAIN_SECONDS // 60} min, {name[0].lower()}{name[1:]}", num(one[0]), pct(one[1]), num(week[0]), pct(week[1])])
    for r in rows[3:]:
        print(r, flush=True)

    # Por gravedad y con edades parecidas (media de siete medidas).
    detail = []
    for label, mask in (
        ("Clase I de la NYHA", (nyha == 1) | ~sick), ("Clase II", (nyha == 2) | ~sick), ("Clase III", (nyha == 3) | ~sick),
        ("Solo personas de 50 a 75 años", (age >= 50) & (age <= 75)),
    ):  # fmt: skip
        keep = np.flatnonzero(mask)
        sub = main_table[main_table.subject.isin(keep)]
        relabel = {old: new for new, old in enumerate(keep)}
        sub = sub.assign(subject=sub.subject.map(relabel))
        a, _ = per_person(sub, main_score[main_table.subject.isin(keep).to_numpy()], sick[keep], 7, rng)
        detail.append([label, int(sick[keep].sum()), int((~sick[keep]).sum()), num(a)])

    medians = main_table.assign(sick=sick[main_table.subject.to_numpy()]).groupby("sick")[["rate", "sdnn", "rmssd", "dc", "pnn50"]].median()

    # Comprobación con los pacientes españoles de MUSIC: resumen del Holter de 24 horas.
    day = pd.DataFrame([day_summary(s) for s in subjects])
    holter = ["rr", "sdnn", "rmssd", "pnn50"]
    x = day[holter].assign(rmssd=np.log(day.rmssd), pnn50=np.log1p(day.pnn50))
    cv_score = np.full(len(day), np.nan)
    for k in range(FOLDS):
        cv_score[fold == k] = simple().fit(x[fold != k], sick[fold != k]).decision_function(x[fold == k])
    day_auc = auc(sick, cv_score)
    cut = float(np.quantile(cv_score[~sick], SPECIFICITY))
    day_sens = float((cv_score[sick] > cut).mean())
    final_day = simple().fit(x, sick)
    music = load_music()
    music = music[music.sdnn.notna() & music.rmssd.notna() & music.pnn50.notna() & music.rr_holter.notna()].reset_index(drop=True)
    xm = pd.DataFrame({"rr": music.rr_holter, "sdnn": music.sdnn, "rmssd": np.log(music.rmssd.clip(lower=1)), "pnn50": np.log1p(music.pnn50)})
    flagged = final_day.decision_function(xm[holter]) > cut
    spanish = [["Todos (ritmo sinusal, con Holter analizado)", len(music), pct(flagged.mean())]]
    for label, mask in (
        ("Con betabloqueante", music.rx_betablocker == 1), ("Sin betabloqueante", music.rx_betablocker == 0),
        ("Clase funcional II", music.nyha == 2), ("Clase funcional III", music.nyha == 3),
        ("Fracción de eyección ≤ 40 %", music.lvef <= 40), ("Fracción de eyección > 40 %", music.lvef > 40),
        ("Murieron en el seguimiento", music.death), ("Siguieron vivos", ~music.death),
    ):  # fmt: skip
        mask = mask.to_numpy()
        spanish.append([label, int(mask.sum()), pct(flagged[mask].mean())])
    groups = [["Sanos (nsr2db)", int((~sick).sum()), num(float(day.rr[~sick].median()), 0), num(float(day.sdnn[~sick].median()), 0), num(float(day.rmssd[~sick].median()), 0)],
              ["Insuficiencia cardíaca, años 90 (chf2db)", int(sick.sum()), num(float(day.rr[sick].median()), 0), num(float(day.sdnn[sick].median()), 0), num(float(day.rmssd[sick].median()), 0)],
              ["Insuficiencia cardíaca, España 2003-2004 (MUSIC)", len(music), num(float(music.rr_holter.median()), 0), num(float(music.sdnn.median()), 0), num(float(music.rmssd.median()), 0)]]  # fmt: skip
    print(f"Holter 24 h: AUC {day_auc:.3f}, sensibilidad {day_sens:.2f}; MUSIC señalados {flagged.mean():.2f}", flush=True)

    # Modelo final: todas las personas, medidas tal cual y degradadas.
    both = pd.concat([main_table, camera], ignore_index=True)
    usable = (both.n >= MIN_INTERVALS).to_numpy()
    y = sick[both.subject.to_numpy()]
    final = boosting().fit(both.loc[usable, FEATURES], y[usable])
    week_scores = np.array([np.nanmean(main_score[(main_table.subject == i).to_numpy()]) for i in range(len(subjects))])
    one_auc, one_sens = per_person(main_table, main_score, sick, 1, rng)
    week_auc, week_sens = per_person(main_table, main_score, sick, 7, rng)
    threshold = float(np.quantile(main_score[np.isfinite(main_score) & ~sick[main_table.subject.to_numpy()]], SPECIFICITY))
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": final, "features": FEATURES, "threshold": 1.0 / (1.0 + np.exp(-threshold)), "prevalence": float(y[usable].mean()),
         "max_ratio": float(flagged.mean() / (1 - SPECIFICITY)), "min_ratio": float((1 - flagged.mean()) / SPECIFICITY),
         "min_intervals": MIN_INTERVALS, "seconds": MAIN_SECONDS, "auc_one": one_auc, "auc_week": week_auc, "sensitivity_week": week_sens},
        MODEL_PATH, compress=3,
    )  # fmt: skip

    header = ["Entrada", "AUC con una medida", f"Sensibilidad (especificidad {pct(SPECIFICITY)})", "AUC con siete medidas", "Sensibilidad con siete"]
    lines = [
        "# Señal de insuficiencia cardíaca en el pulso en reposo",
        "",
        "Generado por `scripts/fit_pulse_hf.py`. Datos: dos bases abiertas de PhysioNet con los latidos de 24 horas de "
        f"{int(sick.sum())} personas con insuficiencia cardíaca ([chf2db](https://physionet.org/content/chf2db/1.0.0/), clases I a III "
        f"de la NYHA, {int(np.nanmedian(age[sick]))} años de mediana) y {int((~sick).sum())} en ritmo sinusal normal "
        f"([nsr2db](https://physionet.org/content/nsr2db/1.0.0/), {int(np.nanmedian(age[~sick]))} años de mediana). "
        "Solo traen el instante de cada latido, que es justo lo que da un sensor de pulso.",
        "",
        f"De cada persona se toman {WINDOWS} tramos repartidos por el registro, como medidas sueltas del pulso. El modelo usa las "
        "17 medidas de irregularidad del detector de fibrilación auricular y cinco más (frecuencia, variación absoluta y capacidad "
        "de aceleración y deceleración). Validación cruzada de cinco partes por persona. No usa la edad: aquí los sanos son "
        "mayores que los enfermos, así que la edad no puede explicar la diferencia.",
        "",
        "## Resultados",
        "",
        *table(header, rows),
        "- **Repetir la medida ayuda**: un rato de pulso rápido y plano no dice mucho; que lo sea todos los días, sí.",
        "- **Las filas de cámara son simuladas** (20 ms de imprecisión y un 3 % de latidos perdidos).",
        "- La variación clásica (SDNN) no separa en tramos cortos: las extrasístoles de los enfermos la inflan. Lo que separa "
        "es la frecuencia, la falta de deceleraciones y el patrón de los cambios de un latido al siguiente.",
        "",
        "### Por gravedad y con edades parecidas (media de siete medidas)",
        "",
        *table(["Grupo", "Con insuficiencia cardíaca", "Sanos", "AUC"], detail),
        "### Medianas de una medida de dos minutos",
        "",
        *table(["Grupo", "Frecuencia (lpm)", "SDNN (ms)", "RMSSD (ms)", "Capacidad de deceleración (ms)", "pNN50"],
               [[("Insuficiencia cardíaca" if flag else "Sanos"), num(r.rate, 0), num(1000 * r.sdnn, 0), num(1000 * r.rmssd, 0), num(1000 * r.dc, 1), pct(r.pnn50)]
                for flag, r in medians.iterrows()]),  # fmt: skip
        "## Comprobación en pacientes españoles (MUSIC)",
        "",
        "MUSIC no trae los latidos, pero sí el resumen del Holter de 24 horas de sus pacientes en ritmo sinusal. Se calcula el "
        "mismo resumen en las dos bases de PhysioNet, se entrena una regla con cuatro números (intervalo medio, SDNN, RMSSD y "
        f"pNN50) y se aplica a los pacientes españoles. En las bases de PhysioNet esa regla tiene AUC {num(day_auc)} y señala al "
        f"{pct(day_sens)} de los enfermos con especificidad del {pct(SPECIFICITY)}.",
        "",
        *table(["Grupo", "Personas", "Intervalo medio (ms)", "SDNN de 24 h (ms)", "RMSSD (ms)"], groups),
        *table(["Pacientes españoles con insuficiencia cardíaca", "Pacientes", "Señalados por la regla"], spanish),
        "Los pacientes españoles, tratados en su mayoría con betabloqueantes, tienen el pulso más lento y con más variación que "
        "los de los años noventa: la regla del pulso los señala menos. Es la advertencia principal de este detector.",
        "",
        "## Límites",
        "",
        "- **83 personas.** Los intervalos de confianza son anchos y cualquier cifra puede moverse varios puntos.",
        "- **Los controles están sanos.** En atención primaria la comparación real es con personas mayores con hipertensión, "
        "diabetes o EPOC, que también tienen el pulso menos variable. La especificidad real será menor.",
        "- **Los enfermos son de los años noventa**, antes de que los betabloqueantes fueran tratamiento habitual. La "
        "comprobación con MUSIC lo cuantifica.",
        "- **Los tramos salen de un registro de 24 horas**, con sueño y actividad mezclados; no son medidas en reposo sentado.",
        "- Por todo esto el resultado entra en la ficha con la razón de verosimilitud limitada a lo que se vio en los "
        f"pacientes españoles: como mucho multiplica la odds por {num(flagged.mean() / (1 - SPECIFICITY), 1)} o la deja en "
        f"{num((1 - flagged.mean()) / SPECIFICITY, 2)} veces. Nunca decide solo.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}; una medida {one_auc:.3f}, siete {week_auc:.3f} ({week_scores.size} personas)")


if __name__ == "__main__":
    main()
