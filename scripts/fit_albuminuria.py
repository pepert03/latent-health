"""Ajusta el filtro de albuminuria con NHANES 2009-2010 (partición de entrenamiento, 80 %).

Uso:
    uv run python scripts/fit_albuminuria.py                    # modelo completo
    uv run python scripts/fit_albuminuria.py --variant <nombre>  # variantes para la validación:
        picos_normales, sin_covariables_muestra, sin_pendiente, sin_picos, normal
"""

import argparse
from pathlib import Path

import numpy as np

from latenthealth.albuminuria import DEFAULT_PARAMS_PATH
from latenthealth.albuminuria.fit import VARIANTS, fit, mean_loglik
from latenthealth.albuminuria.model import FIRST_MORNING, RANDOM
from latenthealth.nhanes import is_test, load_pairs


def variant_path(variant: str) -> Path:
    return DEFAULT_PARAMS_PATH if variant == "completo" else DEFAULT_PARAMS_PATH.with_name(f"albuminuria_params_{variant}.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="completo")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or variant_path(args.variant)

    df = load_pairs()
    test = is_test(df.seqn)
    train, held_out = df[~test], df[test]
    print(f"Variante {args.variant} · entrenamiento: {len(train)} personas · test: {len(held_out)}")
    params = fit(train, fixed=VARIANTS[args.variant])
    params.meta["variante"] = args.variant
    params.meta["loglik_test_por_persona"] = mean_loglik(params, held_out)
    params.save(out)

    m = params.meta
    print(f"Convergencia: {m['convergencia']} ({m['mensaje']}), {m['iteraciones']} iteraciones, {m['segundos']} s")
    print(f"log-verosimilitud por persona: entrenamiento {m['loglik_por_persona']:.4f}, test {m['loglik_test_por_persona']:.4f}")
    print(f"Exceso de la muestra aleatoria a 30 mg/g: x{np.exp(params.bias_random):.2f} (pendiente {params.bias_random_slope:+.3f})")
    print(f"Dilución: ruido {params.eta_dilution:+.2f}, elevaciones {params.kappa_dilution:+.2f}; covariables de elevación κ = {[round(k, 2) for k in params.kappa]}")
    print(
        f"Variación habitual (log): primera de la mañana {params.sigma(FIRST_MORNING):.3f}, "
        f"aleatoria {params.sigma(RANDOM):.3f}, ν = {params.nu:.1f}"
    )
    if args.variant == "completo":
        from scipy.special import expit

        print(
            f"Elevaciones transitorias (base): {expit(params.logit_spike_random):.1%} de las aleatorias, "
            f"{expit(params.logit_spike_morning):.1%} de las de la mañana; "
            f"tamaño medio x{np.exp(params.spike_size):.2f} (ω = {params.spike_sd:.2f} en log)"
        )
    print(f"Guardado en {out}")


if __name__ == "__main__":
    main()
