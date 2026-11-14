"""Entrena y valida la estimación de fracción de eyección baja con ECG de una derivación y sonido.

Datos: Zenodo 16934966 (CC-BY 4.0). 500 personas del hospital Tongji (Wuhan) repartidas por
sus autores en cinco partes por persona, y 120 del hospital Liyuan como prueba "comunitaria".
A todas se les midió la fracción de eyección por ecocardiograma y se les grabaron 30 s de ECG
de una derivación y sonido cardíaco en cuatro focos con un Eko DUO.

Se comparan tres niveles de aparato: solo los intervalos entre latidos (pulso), el ECG de una
derivación, y ECG más sonido. Validación cruzada con las cinco partes de los autores; después
se entrena con las 500 y se prueba en las 120 del otro hospital.

Guarda models/ritmo/fe_baja.joblib y escribe reports/fraccion_eyeccion.md.

Uso:
    uv run python scripts/fit_ejection.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from latenthealth import ejection as ej
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, difference_interval
from latenthealth.rhythm import MIN_INTERVALS

ROOT = Path(__file__).resolve().parents[1]
CACHE = ej.DATA / "medidas.csv"
REPORT = ROOT / "reports" / "fraccion_eyeccion.md"
FOLDS = 5
SPECIFICITY = 0.90
TIERS = {
    "pulso": ("Pulso: intervalos entre latidos", ej.PULSE),
    "ecg": ("ECG de una derivación", ej.PULSE + ej.ECG + ej.ECG_PROFILE),
    "sonido": ("ECG y sonido cardíaco", ej.PULSE + ej.ECG + ej.ECG_PROFILE + ej.SOUND + ej.SOUND_PROFILE),
}
NAMES = {
    "rate": "Frecuencia cardíaca", "s1_s2": "Primer ruido frente al segundo", "sound_quality": "Fuerza de los ruidos frente al fondo",
    "systole": "Duración de la sístole (primer a segundo ruido)", "systole_rel": "Sístole como parte del latido",
    "s1_systole": "Retraso del primer ruido frente a la sístole", "s1_time": "Retraso del primer ruido tras el QRS",
    "qrs_width": "Anchura del QRS", "qrs_equivalent": "Anchura equivalente del QRS", "qrs_amplitude": "Voltaje del QRS",
    "t_amplitude": "Onda T (con signo, frente al QRS)", "st_level": "Nivel del segmento ST", "s3_low": "Energía grave tras el segundo ruido",
    "s4_low": "Energía grave antes del primer ruido", "murmur_mid": "Energía entre los dos ruidos", "murmur_high": "Energía aguda entre los dos ruidos",
    "s1_level": "Fuerza del primer ruido", "s2_level": "Fuerza del segundo ruido", "cv": "Variación de los intervalos",
    "sdnn": "Desviación de los intervalos", "rmssd": "Cambio de un latido al siguiente", "dc": "Capacidad de deceleración",
    "qrs_slope": "Pendiente del QRS", "p_amplitude": "Onda P", "s1_width": "Duración del primer ruido", "s2_width": "Duración del segundo ruido",
    "s1_rel": "Retraso del primer ruido como parte del latido", "t_time": "Tiempo hasta la onda T", "diastole_mid": "Energía al principio de la diástole",
    "low_share": "Parte grave del primer ruido", "high_share": "Parte aguda del primer ruido", "odd_beats": "Latidos de forma distinta", "mean": "Intervalo medio entre latidos",
}  # fmt: skip


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def extract(path: Path) -> pd.DataFrame:
    subjects = sorted({s for s, _ in ej.recording_names(path)})
    chunks = [subjects[i::16] for i in range(16)]
    parts = joblib.Parallel(n_jobs=-1)(joblib.delayed(ej.features_from_zip)(path, chunk, True) for chunk in chunks if chunk)
    return pd.concat(parts, ignore_index=True)


def load() -> pd.DataFrame:
    """Medidas de todas las grabaciones con la fracción de eyección de la persona (se guardan para no repetir)."""
    if CACHE.exists():
        return pd.read_csv(CACHE, dtype={"subject": str})
    parts = []
    for path in (ej.MAIN_ZIP, ej.COMMUNITY_ZIP):
        print(f"Midiendo {path.name}", flush=True)
        parts.append(extract(path).merge(ej.read_labels(path), on="subject"))
    data = pd.concat(parts, ignore_index=True)
    data.to_csv(CACHE, index=False)
    return data


def boosting() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(learning_rate=0.05, max_iter=200, max_depth=3, min_samples_leaf=20, l2_regularization=1.0, random_state=0)


def linear():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def out_of_fold(data: pd.DataFrame, features: list[str], y: np.ndarray, make) -> np.ndarray:
    """Puntuación (logit) de cada grabación por un modelo que no vio a esa persona."""
    score = np.full(len(data), np.nan)
    fold = data.fold.to_numpy()
    for k in range(FOLDS):
        clf = make().fit(data.loc[fold != k, features], y[fold != k])
        score[fold == k] = logit(clf.predict_proba(data.loc[fold == k, features])[:, 1])
    return score


def by_subject(data: pd.DataFrame, score: np.ndarray, sites=None) -> pd.Series:
    """Puntuación por persona: media de sus grabaciones (todas o solo las de unos focos)."""
    frame = pd.DataFrame({"subject": data.subject.to_numpy(), "site": data.site.to_numpy(), "score": score})
    if sites is not None:
        frame = frame[frame.site.isin(sites)]
    return frame.groupby("subject").score.mean()


def operating_point(y: np.ndarray, score: np.ndarray, specificity: float) -> tuple[float, float, float]:
    """Umbral para una especificidad dada, con la sensibilidad y la especificidad que resultan."""
    threshold = float(np.quantile(score[~y], specificity))
    flagged = score > threshold
    return threshold, float(flagged[y].mean()), float((~flagged[~y]).mean())


def interval(samples: np.ndarray) -> str:
    lo, hi = np.nanpercentile(samples, [2.5, 97.5])
    return f"{num(lo, 2)}-{num(hi, 2)}"


def main() -> None:
    data = load()
    data["site_code"] = data.site.map({s: i for i, s in enumerate(ej.SITES)})
    data = data[data.n >= MIN_INTERVALS].reset_index(drop=True)  # grabaciones sin latidos suficientes: no se opina
    main_set = data[data.fold >= 0].reset_index(drop=True)
    community = data[data.fold < 0].reset_index(drop=True)
    people = main_set.groupby("subject").agg(lvef=("lvef", "first"), fold=("fold", "first"))
    people_c = community.groupby("subject").lvef.first()
    y_people = (people.lvef <= ej.REDUCED).to_numpy()
    y_people_c = (people_c <= ej.REDUCED).to_numpy()
    print(f"{len(people)} personas ({int(y_people.sum())} con FE <= 40 %), {len(main_set)} grabaciones; "
          f"comunitario {len(people_c)} ({int(y_people_c.sum())}), {len(community)} grabaciones", flush=True)  # fmt: skip

    y = (main_set.lvef <= ej.REDUCED).to_numpy()
    scores, scores_site, scores_linear, mild = {}, {}, {}, {}
    for key, (label, features) in TIERS.items():
        features = features + ["site_code"]
        s = out_of_fold(main_set, features, y, boosting)
        scores[key] = by_subject(main_set, s).reindex(people.index).to_numpy()
        scores_site[key] = {site: by_subject(main_set, s, [site]).reindex(people.index) for site in ej.SITES}
        scores_linear[key] = by_subject(main_set, out_of_fold(main_set, features, y, linear)).reindex(people.index).to_numpy()
        s50 = out_of_fold(main_set, features, (main_set.lvef < 0.50).to_numpy(), boosting)
        mild[key] = by_subject(main_set, s50).reindex(people.index).to_numpy()
        print(f"{label}: AUC {auc(y_people, scores[key]):.3f} (lineal {auc(y_people, scores_linear[key]):.3f}); "
              f"un foco {np.mean([auc(y_people[v.notna()], v.dropna()) for v in scores_site[key].values()]):.3f}; "
              f"FE < 50 %: {auc(people.lvef.to_numpy() < 0.5, mild[key]):.3f}", flush=True)  # fmt: skip
    rate = main_set.groupby("subject").rate.mean().reindex(people.index).to_numpy()

    samples = bootstrap_auc(y_people, {**scores, "rate": rate}, n=1000)
    results = []
    for key, (label, _) in TIERS.items():
        _, sens, spec = operating_point(y_people, scores[key], SPECIFICITY)
        _, sens80, _ = operating_point(y_people, scores[key], 0.80)
        single = [auc(y_people[v.notna()], v.dropna()) for v in scores_site[key].values()]
        results.append([label, num(auc(y_people, scores[key])), interval(samples[key]), num(float(np.mean(single))), pct(sens), pct(sens80), num(auc(y_people, scores_linear[key]))])
    results.insert(0, ["Solo la frecuencia cardíaca", num(auc(y_people, rate)), interval(samples["rate"]), "", pct(operating_point(y_people, rate, SPECIFICITY)[1]), pct(operating_point(y_people, rate, 0.80)[1]), ""])
    gain_sound = difference_interval(samples["sonido"], samples["ecg"])
    gain_ecg = difference_interval(samples["ecg"], samples["pulso"])

    # Por foco, con ECG y sonido.
    per_site = [[site, num(auc(y_people[v.notna()], v.dropna()))] for site, v in scores_site["sonido"].items()]

    # Gravedad: cuánto sube la detección cuanto más baja es la fracción de eyección.
    lvef = people.lvef.to_numpy()
    threshold, _, _ = operating_point(y_people, scores["sonido"], SPECIFICITY)
    flagged = scores["sonido"] > threshold
    bands = [(0.0, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 1.0)]
    severity = []
    for lo, hi in bands:
        m = (lvef > lo) & (lvef <= hi)
        severity.append([f"{pct(lo)} a {pct(hi)}", int(m.sum()), pct(flagged[m].mean()) if m.any() else ""])
    spearman = float(pd.Series(scores["sonido"]).corr(pd.Series(lvef), method="spearman"))

    # Medidas sueltas que más separan (media de los cuatro focos por persona).
    means = main_set.groupby("subject")[ej.PULSE + ej.ECG + ej.SOUND].mean().reindex(people.index)
    single_rows = []
    for name in means.columns:
        v = means[name].to_numpy()
        ok = np.isfinite(v)
        if ok.sum() < 100:
            continue
        a = auc(y_people[ok], v[ok])
        group = "Pulso" if name in ej.PULSE else "ECG" if name in ej.ECG else "Sonido"
        single_rows.append((abs(a - 0.5), [NAMES.get(name, name), group, num(max(a, 1 - a), 2), "más alta" if a > 0.5 else "más baja",
                                           num(float(np.nanmedian(v[y_people])), 3), num(float(np.nanmedian(v[~y_people])), 3)]))  # fmt: skip
    single_rows = [row for _, row in sorted(single_rows, key=lambda r: -r[0])[:12]]

    # Prueba en el otro hospital: modelos entrenados con las 500 personas, umbral fijado en la validación cruzada.
    bundle = {"models": {}, "prevalence": float(y_people.mean()), "max_ratio": 10.0, "min_intervals": MIN_INTERVALS, "sites": ej.SITES}
    external = []
    for key, (label, features) in TIERS.items():
        features = features + ["site_code"]
        final = boosting().fit(main_set[features], y)
        cut, sens_cv, spec_cv = operating_point(y_people, scores[key], SPECIFICITY)
        bundle["models"][key] = {"model": final, "features": features, "threshold": cut, "sensitivity": sens_cv, "specificity": spec_cv, "auc": auc(y_people, scores[key])}
        s = by_subject(community, logit(final.predict_proba(community[features])[:, 1])).reindex(people_c.index).to_numpy()
        hit = s > cut
        boot = bootstrap_auc(y_people_c, {"s": s}, n=1000)["s"]
        external.append([label, num(auc(y_people_c, s)), interval(boot), f"{int(hit[y_people_c].sum())} de {int(y_people_c.sum())}",
                         f"{int((~hit[~y_people_c]).sum())} de {int((~y_people_c).sum())} ({pct((~hit[~y_people_c]).mean())})"])  # fmt: skip
        print(external[-1], flush=True)
    ej.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, ej.MODEL_PATH, compress=3)

    # Qué significa un resultado: de cada 100 personas señaladas, cuántas tienen la fracción de eyección baja.
    _, sens, spec = operating_point(y_people, scores["sonido"], SPECIFICITY)
    ppv_rows = []
    for prevalence, where in ((0.02, "Mayores de 65 años sin síntomas (2 %)"), (0.05, "Diabetes o hipertensión de años (5 %)"), (0.12, "Consulta por ahogo o hinchazón (12 %)")):
        positive = sens * prevalence + (1 - spec) * (1 - prevalence)
        ppv = sens * prevalence / positive
        npv = spec * (1 - prevalence) / (spec * (1 - prevalence) + (1 - sens) * prevalence)
        ppv_rows.append([where, pct(positive), pct(ppv), pct(1 - npv, 1)])

    lost = len(load()) - len(data)
    header = ["Lo que se usa", "AUC (cuatro grabaciones)", "Intervalo 95 %", "AUC con una sola grabación", f"Sensibilidad con especificidad {pct(SPECIFICITY)}",
              "Sensibilidad con especificidad 80 %", "AUC con un modelo lineal"]  # fmt: skip
    lines = [
        "# Fracción de eyección baja con ECG de una derivación y sonido cardíaco",
        "",
        "Generado por `scripts/fit_ejection.py`. Datos: [Zenodo 16934966](https://zenodo.org/records/16934966) (CC-BY 4.0), "
        "del artículo de Ma y colaboradores en *Patterns* (2026). "
        f"{len(people)} personas del hospital Tongji de Wuhan, {int(y_people.sum())} con fracción de eyección del 40 % o menos "
        f"medida por ecocardiograma (y {int((lvef < 0.5).sum())} por debajo del 50 %), y {len(people_c)} de un segundo hospital "
        f"({int(y_people_c.sum())} con fracción de eyección baja). Cada persona tiene cuatro grabaciones de 30 segundos, una por foco "
        "de auscultación, con un Eko DUO: un aparato de mano que recoge a la vez un ECG de una derivación y el sonido del corazón.",
        "",
        "Es el primer conjunto del proyecto con **ecocardiograma como verdad y personas sin la enfermedad** de la misma consulta. "
        "Los que no tienen la fracción de eyección baja no están sanos: pueden tener valvulopatías, arritmias o miocardiopatías.",
        "",
        "## Qué se mide",
        "",
        "- **Pulso** (22 medidas): los intervalos entre latidos. Es lo que da la cámara del móvil, un reloj o un pulsioxímetro.",
        "- **ECG** (13 medidas y el latido promedio en 32 puntos): anchura, voltaje y pendiente del QRS, onda T, segmento ST.",
        "- **Sonido** (19 medidas y el sonido promedio en 16 tramos de tres bandas): el fonocardiograma promediado latido a "
        "latido usando el QRS como reloj. Da cuánto tarda el primer ruido, cuánto dura la sístole, la fuerza relativa de los "
        "dos ruidos y la energía entre ellos y después.",
        "",
        "Añadir el latido y el sonido promedios completos a las medidas resumidas sube el AUC unas dos centésimas: las medidas "
        "con nombre recogen casi toda la señal, pero no toda.",
        "",
        "Un modelo por nivel (árboles con refuerzo de gradiente, poco profundos). La validación cruzada usa las cinco partes por "
        "persona que publican los autores. La puntuación de una persona es la media de sus cuatro grabaciones.",
        "",
        "## Resultados en validación cruzada (500 personas)",
        "",
        *table(header, results),
        f"- El ECG añade {num(gain_ecg[0])} de AUC al pulso (intervalo del 95 %: {num(gain_ecg[1])} a {num(gain_ecg[2])}).",
        f"- El sonido añade {num(gain_sound[0])} al ECG ({num(gain_sound[1])} a {num(gain_sound[2])}).",
        f"- Con ECG y sonido, la puntuación sigue a la fracción de eyección medida (correlación de rangos {num(spearman, 2)}).",
        f"- Grabaciones descartadas por no tener {MIN_INTERVALS} latidos válidos: {lost} de {len(load())}.",
        "",
        "### Cuántos se señalan según la fracción de eyección",
        "",
        f"Con ECG y sonido y el umbral de especificidad {pct(SPECIFICITY)}:",
        "",
        *table(["Fracción de eyección", "Personas", "Señaladas"], severity),
        "### Por foco, con una sola grabación (ECG y sonido)",
        "",
        *table(["Foco", "AUC"], per_site),
        "### Las medidas que más separan por sí solas",
        "",
        "Media de los cuatro focos. \"Más alta\" quiere decir más alta en quien tiene la fracción de eyección baja.",
        "",
        *table(["Medida", "Grupo", "AUC", "En fracción de eyección baja", "Mediana con FE baja", "Mediana sin ella"], single_rows),
        "## Prueba en el segundo hospital (120 personas)",
        "",
        "Modelos entrenados con las 500 personas del primer hospital y umbral fijado antes de mirar estas.",
        "",
        *table(["Lo que se usa", "AUC", "Intervalo 95 %", "Casos detectados", "Sin la enfermedad bien descartados"], external),
        f"Son solo {int(y_people_c.sum())} casos: el intervalo es muy ancho y la sensibilidad no se puede afirmar.",
        "",
        "## Qué significa un resultado positivo",
        "",
        f"Con la sensibilidad ({pct(sens)}) y la especificidad ({pct(spec)}) de la validación cruzada, según a quién se le haga:",
        "",
        *table(["A quién", "Señalados", "De los señalados, con FE baja", "De los no señalados, con FE baja"], ppv_rows),
        "Las prevalencias son órdenes de magnitud, no datos del proyecto. Sirve sobre todo para descartar y para ordenar la "
        "lista de ecocardiogramas, no para diagnosticar.",
        "",
        "## Límites",
        "",
        "- **Pacientes de un hospital chino**, no de atención primaria española. Los autores no publican edad ni sexo por "
        "persona, así que no se puede ajustar ni comprobar por grupos.",
        "- **Pocos casos**: 60 en el conjunto principal y 5 en el segundo hospital.",
        "- **Solo fracción de eyección reducida.** La mitad de la insuficiencia cardíaca tiene la fracción de eyección "
        "conservada y aquí cuenta como \"sin la enfermedad\".",
        "- **El aparato lo usó personal sanitario** sobre el pecho. No se sabe cómo queda la grabación si se la hace el "
        "paciente, ni con el micrófono de un móvil. El nivel de pulso sí se puede tomar con la cámara, pero aquí sale del ECG.",
        "- **No se compara con el modelo de los autores** (una red profunda sobre la señal entera): no se ha podido leer el "
        "artículo. Estas medidas son deliberadamente simples y explicables.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
