"""Recalibra los priors a atención primaria española con las prevalencias del estudio ONDAAS.

Solo mueve interceptos: una constante en el prior de la albuminuria y otra en el suceso
"FG < 60" de la distribución del filtrado glomerular del panel. Guarda:
- models/albuminuria_params_espana.json (los mismos parámetros con el prior recalibrado),
- models/recalibracion_espana.json (lo que se ha movido, con qué datos y con qué cautelas),
- reports/recalibracion_espana.md.

Uso:
    uv run python scripts/fit_recalibration.py
"""

import json
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np

from latenthealth.albuminuria import DEFAULT_PARAMS_PATH, SPAIN_PARAMS_PATH, AlbuminuriaParams
from latenthealth.albuminuria.model import FIRST_MORNING, RANDOM, covariates
from latenthealth.panel import load_panel
from latenthealth.recalibration import (
    AGE_GROUPS,
    ONDAAS,
    RECALIBRATION_PATH,
    age_group,
    cdf_from_pmf,
    egfr_2009_cut_in_2021_scale,
    fit_prior_offset,
    fit_shift,
    reference_weights,
    sample_prevalence,
    shift_below,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "recalibracion_espana.md"
PANEL = ROOT / "models" / "panel"
G_EDGES = [90, 60, 45, 30, 15]
G_LABELS = ["G1", "G2", "G3a", "G3b", "G4", "G5"]


def pct(v: float) -> str:
    return f"{100 * v:.1f} %".replace(".", ",")


def by_age(p, weights, group) -> list[float]:
    return [float(weights[group == g] @ p[group == g] / weights[group == g].sum()) for g in range(3)]


def main() -> None:
    panel = load_panel()
    panel = panel[np.isfinite(panel.egfr)].reset_index(drop=True)
    female = panel.female.to_numpy() == 1
    age = panel.age.to_numpy(float)
    weights = reference_weights(age, female)
    group = age_group(age)
    # Diabetes como en el ajuste del filtro: por laboratorio (HbA1c ≥ 6,5 %).
    diabetes = panel.hba1c.to_numpy(float) >= 6.5
    Z = covariates(age, female, diabetes, panel.egfr.to_numpy(float))
    params = AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)
    observed_age = [cases / n for n, cases in (ONDAAS["edad"][name] for name, _, _ in AGE_GROUPS)]

    # --- Albuminuria ---
    alb = {}
    for sample_type, label in ((RANDOM, "muestra aleatoria"), (FIRST_MORNING, "primera orina de la mañana")):
        before = sample_prevalence(params, Z, sample_type)
        offset = fit_prior_offset(params, Z, weights, ONDAAS["albuminuria"], sample_type)
        after = sample_prevalence(replace(params, prior_logit_offset=offset), Z, sample_type)
        alb[sample_type] = {
            "etiqueta": label,
            "constante": offset,
            "antes": float(weights @ before),
            "despues": float(weights @ after),
            "antes_por_edad": by_age(before, weights, group),
            "despues_por_edad": by_age(after, weights, group),
        }
        print(f"Albuminuria ({label}): modelo {pct(alb[sample_type]['antes'])} -> objetivo {pct(ONDAAS['albuminuria'])}; constante {offset:+.3f}")
    chosen = alb[RANDOM]
    spain = replace(params, prior_logit_offset=chosen["constante"])
    spain.meta = {
        **params.meta,
        "recalibracion": f"prior recalibrado a {ONDAAS['fuente']}; constante {chosen['constante']:+.3f} (muestra aleatoria)",
    }
    spain.save(SPAIN_PARAMS_PATH)

    # --- Filtrado glomerular ---
    bundle = joblib.load(PANEL / "egfr__historia_clínica.joblib")
    model = bundle["model"]
    pmf = model.predict_pmf(panel[bundle["features"]].to_numpy(float))
    bounds = model.bin_bounds
    cuts = egfr_2009_cut_in_2021_scale(age, female)
    before = float(weights @ cdf_from_pmf(pmf, bounds, cuts))
    observed_2021 = float(weights @ (panel.egfr.to_numpy(float) < cuts))
    theta = fit_shift(pmf, bounds, 60.0, cuts, weights, ONDAAS["fg_menor_60"])
    tilted = shift_below(pmf, bounds, 60.0, theta)
    after = float(weights @ cdf_from_pmf(tilted, bounds, cuts))

    def g_distribution(p) -> list[float]:
        # Categorías con la ecuación de 2009, como en ONDAAS: cada corte se traduce a la escala de 2021.
        below = [float(weights @ cdf_from_pmf(p, bounds, egfr_2009_cut_in_2021_scale(age, female, e))) for e in G_EDGES]
        return [1 - below[0], *(-np.diff(below)).tolist(), below[-1]]

    g_before, g_after = g_distribution(pmf), g_distribution(tilted)
    print(f"FG < 60 (ecuación de 2009): modelo {pct(before)} (NHANES repesado, real {pct(observed_2021)}) -> objetivo {pct(ONDAAS['fg_menor_60'])}; constante {theta:+.3f}")

    result = {
        "fuente": ONDAAS["fuente"],
        "poblacion": ONDAAS["poblacion"],
        "albuminuria": {
            "constante_prior": chosen["constante"],
            "tipo_de_muestra_supuesto": "aleatoria",
            "objetivo": ONDAAS["albuminuria"],
            "modelo_antes": chosen["antes"],
            "constante_si_fuera_primera_de_la_manana": alb[FIRST_MORNING]["constante"],
        },
        "egfr": {
            "constante_fg_menor_60": theta,
            "corte": 60.0,
            "objetivo_fg_menor_60_ckd_epi_2009": ONDAAS["fg_menor_60"],
            "modelo_antes": before,
        },
        "cautelas": [
            "ONDAAS son pacientes a los que se pidió analítica, no todo el cupo.",
            "El artículo no dice si la orina era la primera de la mañana; se asume muestra aleatoria.",
            "ONDAAS usó CKD-EPI 2009 y creatinina por Jaffé; el objetivo se traduce a la escala de CKD-EPI 2021.",
            "La población de comparación es NHANES repesada por edad y sexo; la edad de NHANES está acotada en 80 años.",
        ],
    }
    RECALIBRATION_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    names = [name for name, _, _ in AGE_GROUPS]
    lines = [
        "# Recalibración de los priors a atención primaria española",
        "",
        "Generado por `scripts/fit_recalibration.py`. Referencia: " + ONDAAS["fuente"] + f", {ONDAAS['n']} "
        + ONDAAS["poblacion"] + ". Población de comparación: los "
        f"{len(panel)} adultos de NHANES 2009-2018 repesados al reparto por edad y sexo de ONDAAS.",
        "",
        "Solo se mueven interceptos. El modelo de medida de la orina y la forma en que cada dato del paciente cambia la "
        "estimación quedan como estaban.",
        "",
        "## Albuminuria",
        "",
        "Proporción de personas cuya muestra de orina sale ≥ 30 mg/g, antes de medirles nada.",
        "",
        "| | ONDAAS | Modelo de NHANES | Modelo recalibrado |",
        "|---|---|---|---|",
        f"| Total | {pct(ONDAAS['albuminuria'])} | {pct(chosen['antes'])} | {pct(chosen['despues'])} |",
        *[
            f"| {name} años | {pct(obs)} | {pct(b)} | {pct(a)} |"
            for name, obs, b, a in zip(names, observed_age, chosen["antes_por_edad"], chosen["despues_por_edad"])
        ],
        "",
        f"Constante sumada al logit de las componentes elevadas del prior: **{chosen['constante']:+.3f}** "
        f"(multiplica la odds de albuminuria por {np.exp(chosen['constante']):.2f}). El prior de NHANES ya estaba cerca. "
        "Se ajusta solo el total; las filas por edad son una comprobación, no un objetivo.",
        "",
        f"Se ha supuesto que la orina de ONDAAS es una muestra aleatoria (se recogió en el centro). Si fuera la primera "
        f"de la mañana, el modelo de NHANES daría {pct(alb[FIRST_MORNING]['antes'])} y la constante sería "
        f"{alb[FIRST_MORNING]['constante']:+.3f}.",
        "",
        "## Filtrado glomerular",
        "",
        "ONDAAS usó la ecuación CKD-EPI 2009 y este proyecto usa la de 2021, que da valores algo más altos con la misma "
        "creatinina. Para comparar lo mismo, cada categoría se calcula con el corte de 2009 traducido a la escala de 2021 "
        f"persona a persona (FG 60 de 2009 equivale a entre {cuts.min():.0f} y {cuts.max():.0f} de 2021).",
        "",
        "| Categoría (ecuación de 2009) | ONDAAS | Panel de NHANES | Panel recalibrado |",
        "|---|---|---|---|",
        f"| FG < 60 | {pct(ONDAAS['fg_menor_60'])} | {pct(before)} | {pct(after)} |",
        *[f"| {g} | {pct(ONDAAS['g'][g])} | {pct(b)} | {pct(a)} |" for g, b, a in zip(G_LABELS, g_before, g_after)],
        "",
        f"Constante sumada al logit de FG < 60 en la distribución del panel: **{theta:+.3f}** (multiplica su odds por "
        f"{np.exp(theta):.2f}). Se ajusta solo FG < 60; el resto de categorías es una comprobación. El reparto entre G1 "
        "y G2 no se corrige: no cambia ninguna decisión.",
        "",
        "## Cautelas",
        "",
        *[f"- {c}" for c in result["cautelas"]],
        "- Es una corrección de población, no una validación: no hay datos individuales españoles con los que "
        "comprobar la calibración paciente a paciente.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Guardado en {SPAIN_PARAMS_PATH.name}, {RECALIBRATION_PATH.name} y {REPORT}")


if __name__ == "__main__":
    main()
