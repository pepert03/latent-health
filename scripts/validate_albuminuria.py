"""Valida el filtro de albuminuria en la partición de test de NHANES 2009-2010.

Pregunta principal: dada la muestra aleatoria de una persona, ¿con qué probabilidad su
primera orina de la mañana saldrá ≥ 30 mg/g? Se compara el modelo con la regla habitual
(un positivo es positivo), una tabla empírica por tramos y una regresión logística
entrenada directamente para esta tarea.

Uso:
    uv run python scripts/validate_albuminuria.py
Escribe reports/validacion_albuminuria.md.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from scipy.special import expit
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from latenthealth.albuminuria import DEFAULT_PARAMS_PATH, AlbuminuriaFilter, AlbuminuriaParams
from latenthealth.albuminuria.fit import mean_loglik
from latenthealth.albuminuria.model import (
    FIRST_MORNING,
    RANDOM,
    covariates,
    Observations,
    dilution,
    make_grid,
    posterior,
    prob_new_sample_above,
    simulate,
)
from latenthealth.nhanes import is_test, load_pairs

REPORT = Path(__file__).resolve().parents[1] / "reports" / "validacion_albuminuria.md"
BINS = [0, 10, 20, 30, 50, 100, 300, 1000, np.inf]
BIN_LABELS = ["<10", "10-20", "20-30", "30-50", "50-100", "100-300", "300-1000", "≥1000"]
TYPES = {"random": RANDOM, "morning": FIRST_MORNING}


def predict_other(params, df, given, x):
    """P(la otra muestra ≥ 30 | la muestra ``given`` y las covariables)."""
    other = "morning" if given == "random" else "random"
    Z = covariates(df.age, df.female, df.diabetes, df.egfr)
    obs = [Observations(np.log(df[f"uacr_{given}"].to_numpy(float)), df[f"censored_{given}"].to_numpy(bool), TYPES[given], dilution(df[f"ucr_{given}"].to_numpy(float)))]
    post = posterior(params, Z, obs, x)
    return prob_new_sample_above(params, Z, post, TYPES[other], 30.0, x), post


def features(df, given):
    Z = covariates(df.age, df.female, df.diabetes, df.egfr)
    return np.column_stack([np.log(df[f"uacr_{given}"].to_numpy(float)), Z])


def metrics(y, p):
    return {
        "AUC": roc_auc_score(y, p),
        "Brier": brier_score_loss(y, p),
        "log-loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
    }


def table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def direction_block(variants, train, test, given, x):
    other = "morning" if given == "random" else "random"
    names = {"random": "muestra aleatoria", "morning": "primera orina de la mañana"}
    y = (test[f"uacr_{other}"] >= 30).to_numpy(int)
    preds = {label: predict_other(p, test, given, x)[0] for label, p in variants.items()}
    rule = (test[f"uacr_{given}"] >= 30).to_numpy(float)
    # Tabla empírica por tramos (entrenamiento)
    bins_tr = pd.cut(train[f"uacr_{given}"], BINS, right=False)
    rate = (train[f"uacr_{other}"] >= 30).groupby(bins_tr, observed=False).mean()
    p_tab = pd.cut(test[f"uacr_{given}"], BINS, right=False).map(rate).astype(float).to_numpy()
    # Regresión logística entrenada para esta tarea
    lr = LogisticRegression(max_iter=1000).fit(features(train, given), (train[f"uacr_{other}"] >= 30).astype(int))
    p_lr = lr.predict_proba(features(test, given))[:, 1]

    models = {
        **preds,
        "Regresión logística (entrenada para esto)": p_lr,
        "Tabla empírica por tramos": p_tab,
    }
    rows = [[k] + [f"{v:.3f}" for v in metrics(y, p).values()] for k, p in models.items()]
    tp, fp = int(((rule == 1) & (y == 1)).sum()), int(((rule == 1) & (y == 0)).sum())
    fn, tn = int(((rule == 0) & (y == 1)).sum()), int(((rule == 0) & (y == 0)).sum())
    lines = [
        f"### Dada la {names[given]}, ¿saldrá la {names[other]} ≥ 30?",
        f"Personas de test con las dos muestras: {len(test)}; la {names[other]} sale ≥ 30 en el {y.mean():.1%}.",
        "",
        table(rows, ["Predicción", "AUC", "Brier", "log-loss"]),
        "",
        f"Regla habitual (un positivo es positivo): Brier {brier_score_loss(y, rule):.3f}; "
        f"de {tp + fp} positivos, {fp} ({fp / max(tp + fp, 1):.0%}) no se repiten; "
        f"de {fn + tn} negativos, {fn} ({fn / max(fn + tn, 1):.1%}) salen positivos en la otra muestra.",
        "",
        f"Calibración por tramos de la {names[given]} (probabilidad media predicha frente a lo observado):",
        "",
    ]
    g = pd.cut(test[f"uacr_{given}"], BINS, right=False, labels=BIN_LABELS)
    cal = []
    for label in BIN_LABELS:
        m = (g == label).to_numpy()
        if m.sum() == 0:
            continue
        cal.append(
            [label, int(m.sum()), f"{y[m].mean():.0%}"]
            + [f"{p[m].mean():.0%}" for p in preds.values()]
            + [f"{p_lr[m].mean():.0%}"]
        )
    lines.append(table(cal, ["Tramo (mg/g)", "n", "Observado", *preds.keys(), "Logística"]))
    return "\n".join(lines)


def ppc_block(params, test, title, reps=200, seed=0):
    """Comprobación predictiva: simula muestras con las covariables dadas y compara con lo observado."""
    rng = np.random.default_rng(seed)
    Z = covariates(test.age, test.female, test.diabetes, test.egfr)

    def stats(r, m):
        a2r = (r >= 30) & (r < 300)
        conf = {}
        for lo, hi, lab in [(30, 50, "30-50"), (50, 100, "50-100"), (100, 300, "100-300"), (300, np.inf, "≥300")]:
            sel = (r >= lo) & (r < hi)
            conf[lab] = np.mean(m[sel] >= 30) if sel.any() else np.nan
        return {
            "Aleatoria ≥ 30": np.mean(r >= 30),
            "Primera de la mañana ≥ 30": np.mean(m >= 30),
            "Ambas ≥ 30": np.mean((r >= 30) & (m >= 30)),
            "A2 en aleatoria que siguen A2": np.mean((m[a2r] >= 30) & (m[a2r] < 300)) if a2r.any() else np.nan,
            **{f"Confirma con aleatoria {k}": v for k, v in conf.items()},
        }

    obs = stats(test.uacr_random.to_numpy(float), test.uacr_morning.to_numpy(float))
    sims = []
    for _ in range(reps):
        _, ys = simulate(params, Z, rng, u={RANDOM: dilution(test.ucr_random.to_numpy(float)), FIRST_MORNING: dilution(test.ucr_morning.to_numpy(float))})
        sims.append(stats(np.exp(ys[RANDOM]), np.exp(ys[FIRST_MORNING])))
    sims = pd.DataFrame(sims)
    rows = [
        [k, f"{v:.1%}", f"{sims[k].mean():.1%}", f"{sims[k].quantile(0.05):.1%}-{sims[k].quantile(0.95):.1%}"]
        for k, v in obs.items()
    ]
    return "\n".join(
        [
            f"### Comprobación predictiva ({title})",
            f"Simulación de {reps} réplicas de estas {len(test)} personas con sus covariables.",
            "",
            table(rows, ["Estadístico", "Observado", "Simulado (media)", "Simulado (90 %)"]),
        ]
    )


def decision_block(params, test, x):
    """Qué decidiría el filtro con una muestra aleatoria y si la segunda muestra le da la razón."""
    flt = AlbuminuriaFilter(params)
    _, post = predict_other(params, test, "random", x)
    p_a2 = post[:, x >= np.log(30.0)].sum(axis=1)
    p_next, _ = predict_other(params, test, "random", x)
    m = (test.uacr_morning >= 30).to_numpy()
    groups = {
        f"Descartada (P ≤ {flt.discard:.0%})": p_a2 <= flt.discard,
        "Dudosa": (p_a2 > flt.discard) & (p_a2 < flt.confirm),
        f"Muy probable (P ≥ {flt.confirm:.0%})": p_a2 >= flt.confirm,
    }
    rows = []
    for k, sel in groups.items():
        if sel.sum() == 0:
            rows.append([k, 0, "-", "-"])
            continue
        rows.append([k, f"{sel.sum()} ({sel.mean():.0%})", f"{m[sel].mean():.1%}", f"{p_next[sel].mean():.1%}"])
    return "\n".join(
        [
            "### Decisión tras una sola muestra aleatoria",
            "P = probabilidad de que el UACR verdadero (primera orina de la mañana) sea ≥ 30.",
            "",
            table(rows, ["Estado del filtro", "Personas", "Mañana ≥ 30 observado", "Mañana ≥ 30 esperado por el modelo"]),
        ]
    )


def main() -> None:
    params = AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)
    def load(variant):
        return AlbuminuriaParams.load(DEFAULT_PARAMS_PATH.with_name(f"albuminuria_params_{variant}.json"))

    # Escalera de variantes: cada una quita una pieza a la anterior.
    variants = {
        "Completo": params,
        "Elevaciones de cola ligera": load("picos_normales"),
        "Sin covariables de muestra": load("sin_covariables_muestra"),
        "Sin exceso creciente": load("sin_pendiente"),
        "Sin elevaciones": load("sin_picos"),
        "Ruido normal": load("normal"),
    }
    df = load_pairs()
    test_mask = is_test(df.seqn)
    both = df.uacr_random.notna() & df.uacr_morning.notna()
    train, test = df[~test_mask & both], df[test_mask & both]
    x, _ = make_grid(400)

    parts = [
        "# Validación del filtro de albuminuria (NHANES 2009-2010)",
        "",
        "Generado por `scripts/validate_albuminuria.py`. Modelo ajustado solo con la partición de "
        f"entrenamiento ({params.meta.get('n_personas')} personas); aquí se evalúa en las {len(test)} "
        "personas de test con las dos muestras (aleatoria en el centro y primera orina de la mañana en casa).",
        "",
        "## Parámetros ajustados",
        "",
        "- Exceso de la muestra aleatoria sobre la primera de la mañana (sin elevación): "
        + ", ".join(f"x{np.exp(params.bias_at(RANDOM, np.log(v))):.2f} a {v} mg/g" for v in (3, 10, 30, 100, 300))
        + ".",
        f"- Variación habitual por muestra (escala log, t de Student con ν = {params.nu:.1f}): primera de la "
        f"mañana {params.sigma(FIRST_MORNING):.3f}, aleatoria {params.sigma(RANDOM):.3f}.",
        f"- Elevaciones transitorias (hombre de 50 años sin diabetes, FG 90, orina de dilución típica): "
        f"{expit(params.logit_spike_random):.0%} de las muestras aleatorias y "
        f"{expit(params.logit_spike_morning):.0%} de las primeras de la mañana, de x{np.exp(params.spike_size):.1f} "
        f"de media (ω = {params.spike_sd:.2f} en log). Efectos en el logit: edad/15 años {params.kappa[0]:+.2f}, "
        f"mujer {params.kappa[1]:+.2f}, diabetes {params.kappa[2]:+.2f}, FG/20 {params.kappa[3]:+.2f}, "
        f"dilución (log creatinina en orina) {params.kappa_dilution:+.2f}.",
        f"- Efectos en la escala de la variación (log, por unidad): edad/15 años {params.eta[0]:+.2f}, mujer "
        f"{params.eta[1]:+.2f}, diabetes {params.eta[2]:+.2f}, FG/20 {params.eta[3]:+.2f}, "
        f"dilución {params.eta_dilution:+.2f}.",
        "- Log-verosimilitud por persona en test (más alto es mejor): "
        + ", ".join(f"{k.lower()} {mean_loglik(v, df[test_mask]):.3f}" for k, v in variants.items())
        + ".",
        "- Dinámica (no se ajusta con estos datos): cambio verdadero de "
        f"{params.drift_sd_per_year:.2f} en log por año (≈ ±{np.exp(params.drift_sd_per_year) - 1:.0%}).",
        "",
        "## Resultados",
        "",
    ]
    parts += [direction_block(variants, train, test, "random", x), ""]
    parts += [direction_block(variants, train, test, "morning", x), ""]
    parts += [decision_block(params, test, x), ""]
    parts += [ppc_block(params, test, title="modelo completo"), ""]
    parts += [ppc_block(variants["Sin elevaciones"], test, title="sin elevaciones transitorias"), ""]
    parts += [ppc_block(params, train, title="modelo completo, sobre los datos de entrenamiento"), ""]
    text = "\n".join(parts)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
