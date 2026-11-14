"""Entrena y valida el detector de fibrilación auricular por intervalos entre latidos.

Datos: PhysioNet/CinC Challenge 2017 (8.528 registros de un electrocardiógrafo de bolsillo).
Se detectan los latidos de cada registro, se calculan medidas de irregularidad de los
intervalos y un clasificador separa la fibrilación auricular de todo lo demás.

Se evalúa con validación cruzada de cinco partes, con los latidos tal cual y degradados como
los marcaría la cámara de un móvil (imprecisión de 20 ms y un 3 % de latidos perdidos).

Guarda models/ritmo/fa_intervalos.joblib y escribe reports/ritmo.md.

Uso:
    uv run python scripts/fit_rhythm.py
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.io import loadmat
from sklearn.ensemble import HistGradientBoostingClassifier

from latenthealth.outcomes.evaluation import auc
from latenthealth.rhythm import FEATURES, MIN_INTERVALS, MODEL_PATH, degrade, detect_beats, interval_features, intervals_from_beats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "physionet2017"
REPORT = ROOT / "reports" / "ritmo.md"
FS, FOLDS = 300.0, 5
LABELS = {"N": "Ritmo normal", "A": "Fibrilación auricular", "O": "Otro ritmo", "~": "Ruido"}
SPECIFICITY = 0.95


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def features_table(beats: list[np.ndarray], rng=None) -> pd.DataFrame:
    rows = []
    for b in beats:
        b = degrade(b, rng) if rng is not None else b
        rows.append(interval_features(intervals_from_beats(b)))
    return pd.DataFrame(rows)[FEATURES]


def model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=400, max_leaf_nodes=15, min_samples_leaf=20, l2_regularization=1.0,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=25, random_state=0,
    )  # fmt: skip


def cross_validate(X: pd.DataFrame, y: np.ndarray, fold: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Probabilidad de cada registro por un modelo que no lo vio, y el umbral elegido en cada parte."""
    p = np.full(len(X), np.nan)
    flagged = np.zeros(len(X), bool)
    for k in range(FOLDS):
        clf = model().fit(X[fold != k], y[fold != k])
        inner = clf.predict_proba(X[fold != k])[:, 1]
        threshold = np.quantile(inner[~y[fold != k]], SPECIFICITY)  # especificidad buscada, fijada sin mirar la parte evaluada
        p[fold == k] = clf.predict_proba(X[fold == k])[:, 1]
        flagged[fold == k] = p[fold == k] >= threshold
    return p, flagged


def summarize(label: str, y, p, flagged, classes) -> list[str]:
    normal = classes == "N"
    return [
        label,
        num(auc(y, p)),
        num(auc(y[y | normal], p[y | normal])),
        pct(flagged[y].mean()),
        pct((~flagged[~y]).mean()),
        pct(flagged[normal].mean()),
        pct(flagged[classes == "O"].mean()),
    ]


def main() -> None:
    ref = pd.read_csv(DATA / "REFERENCE-v3.csv", header=None, names=["record", "label"])
    beats = []
    for i, record in enumerate(ref.record):
        signal = loadmat(DATA / "training2017" / f"{record}.mat")["val"][0]
        beats.append(detect_beats(signal, FS))
        if i % 2000 == 0:
            print(f"{i} registros leídos", flush=True)
    classes = ref.label.to_numpy()
    y = classes == "A"
    fold = np.arange(len(ref)) % FOLDS
    n_beats = np.array([b.size for b in beats])
    duration = np.array([b[-1] - b[0] if b.size > 1 else 0.0 for b in beats])
    rate = 60.0 * (n_beats - 1) / np.maximum(duration, 1e-9)
    print(f"{len(ref)} registros; {int(y.sum())} con fibrilación auricular; latidos por registro (mediana) {np.median(n_beats):.0f}", flush=True)

    rng = np.random.default_rng(0)
    clean = features_table(beats)
    camera = features_table(beats, rng)
    usable = (clean.n >= MIN_INTERVALS).to_numpy()
    rows = []
    p_clean, f_clean = cross_validate(clean, y, fold)
    rows.append(summarize("Latidos del electrocardiograma", y, p_clean, f_clean, classes))
    p_cam, f_cam = cross_validate(camera, y, fold)
    rows.append(summarize("Latidos degradados como los de una cámara (simulado)", y, p_cam, f_cam, classes))
    # Entrenado con electrocardiograma y usado con cámara: lo que pasaría sin adaptar el modelo.
    p_shift = np.full(len(ref), np.nan)
    f_shift = np.zeros(len(ref), bool)
    for k in range(FOLDS):
        clf = model().fit(clean[fold != k], y[fold != k])
        threshold = np.quantile(clf.predict_proba(clean[fold != k])[:, 1][~y[fold != k]], SPECIFICITY)
        p_shift[fold == k] = clf.predict_proba(camera[fold == k])[:, 1]
        f_shift[fold == k] = p_shift[fold == k] >= threshold
    rows.append(summarize("Entrenado con electrocardiograma, usado con cámara (simulado)", y, p_shift, f_shift, classes))
    for r in rows:
        print(r, flush=True)

    # Regla simple de referencia: coeficiente de variación de los intervalos.
    cv = clean.cv.fillna(0).to_numpy()
    cut = np.quantile(cv[~y], SPECIFICITY)
    simple = summarize("Regla simple: variación de los intervalos", y, cv, cv >= cut, classes)

    # Calibración y razón de verosimilitud por tramos de la probabilidad.
    bins = [(0, 0.02), (0.02, 0.1), (0.1, 0.3), (0.3, 0.7), (0.7, 1.01)]
    prevalence = float(y.mean())
    calibration = []
    for lo, hi in bins:
        m = (p_clean >= lo) & (p_clean < hi)
        if m.any():
            observed = y[m].mean()
            ratio = (observed / max(1 - observed, 1e-9)) / (prevalence / (1 - prevalence))
            calibration.append([f"{pct(lo, 0)} a {pct(min(hi, 1.0), 0)}", int(m.sum()), pct(p_clean[m].mean()), pct(observed), num(ratio, 1)])

    # Modelo final: con todos los registros, mitad tal cual y mitad degradados, para que sirva con las dos fuentes.
    both = pd.concat([clean, camera], ignore_index=True)
    final = model().fit(both, np.r_[y, y])
    inner = final.predict_proba(both)[:, 1]
    threshold = float(np.quantile(inner[~np.r_[y, y]], SPECIFICITY))
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": final,
            "features": FEATURES,
            "threshold": threshold,
            "prevalence": prevalence,
            "max_ratio": 30.0,
            "sensitivity": float(f_clean[y].mean()),
            "specificity": float((~f_clean[~y]).mean()),
            "sensitivity_camera": float(f_cam[y].mean()),
            "specificity_camera": float((~f_cam[~y]).mean()),
        },
        MODEL_PATH,
        compress=3,
    )

    counts = ref.label.value_counts()
    header = ["Entrada", "AUC frente a todo lo demás", "AUC frente a ritmo normal", "Sensibilidad", "Especificidad", "Normales señalados", "\"Otro ritmo\" señalados"]
    lines = [
        "# Detector de fibrilación auricular por intervalos entre latidos",
        "",
        f"Generado por `scripts/fit_rhythm.py`. Datos: PhysioNet/CinC Challenge 2017, {len(ref)} registros de 9 a 60 segundos "
        "de un electrocardiógrafo de bolsillo de una derivación, etiquetados por expertos: "
        + ", ".join(f"{LABELS[k].lower()} {int(counts[k])}" for k in ("N", "A", "O", "~"))
        + ". Validación cruzada de cinco partes.",
        "",
        "El detector no mira la forma de la onda: detecta cada latido y mide lo irregulares que son los intervalos entre "
        "ellos (17 medidas). Así sirve con cualquier cosa que marque el latido, incluida la cámara del móvil. El umbral "
        f"se fija para una especificidad del {pct(SPECIFICITY, 0)} en los datos de entrenamiento de cada parte.",
        "",
        "## Resultados",
        "",
        *table(header, rows + [simple]),
        f"Registros con menos de {MIN_INTERVALS} intervalos válidos, en los que el detector no opina: {int((~usable).sum())} "
        f"({pct((~usable).mean())}).",
        "",
        "- **\"Otro ritmo\" señalados** es el coste real: extrasístoles y otras arritmias también dan un pulso irregular, y "
        "con los intervalos solos no siempre se distinguen. No son sanos: también conviene que los vea un médico.",
        "- **Las filas de cámara son simuladas**: los mismos latidos con 20 ms de imprecisión y un 3 % perdidos. No hay "
        "registros de cámara etiquetados en abierto para comprobarlo de verdad.",
        "",
        "## Qué significa cada resultado del detector",
        "",
        "Fibrilación auricular observada según la probabilidad que da el detector, y cuánto multiplica la odds de partida "
        "(razón de verosimilitud). Es lo que usa la ficha del paciente para actualizar su probabilidad.",
        "",
        *table(["Probabilidad del detector", "Registros", "Media predicha", "Fibrilación observada", "Razón de verosimilitud"], calibration),
        "## Límites",
        "",
        "- **No es la población del cribado.** Son registros de gente que usaba el aparato, con un 9 % de fibrilación; en "
        "el cribado de mayores de 65 años es del 1-2 % sin diagnosticar. Por eso la ficha no usa la probabilidad tal cual: "
        "la convierte en razón de verosimilitud y la aplica a la prevalencia española por edad y sexo.",
        "- **Registros cortos y de un solo momento.** La fibrilación paroxística puede no estar presente ese rato.",
        "- **Los mejores métodos del reto usan la forma de la onda** y redes profundas; este usa solo intervalos para "
        "poder funcionar con la cámara. No pretende superarlos.",
        "- No se sabe si hay varios registros de una misma persona; si los hay, la validación cruzada es algo optimista.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
