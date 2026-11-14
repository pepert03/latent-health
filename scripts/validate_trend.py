"""Comprueba en simulación el modelo de tendencia del filtrado glomerular.

No hay analíticas repetidas en NHANES, así que esto **no valida el modelo con pacientes**: mide
qué hace el filtro si el mundo se comporta como sus supuestos, y lo compara con las reglas
simples que se usan a ojo.

1. ¿Están calibrados los intervalos de la pendiente?
2. ¿Cuántas analíticas anuales hacen falta para ver un descenso rápido, y con cuántas falsas alarmas?
3. ¿Qué pasa al empezar un iSGLT2 si no se le dice al filtro?

Uso:
    uv run python scripts/validate_trend.py
Escribe reports/tendencia_fg.md.
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np

from latenthealth.kidney_trend import TreatmentStart, TrendParams, fit_trend, simulate_trajectory

REPORT = Path(__file__).resolve().parents[1] / "reports" / "tendencia_fg.md"
D0 = date(2020, 1, 15)
N = 3000


def pct(v: float, d: int = 0) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def draw_patient(rng, params):
    diabetes = bool(rng.random() < 0.35)
    p_a2 = float(rng.random() < 0.2)
    comps = params.slope_components(diabetes, p_a2, 0.0)
    fast = rng.random() < comps[1][0]
    _, mean, sd = comps[int(fast)]
    return diabetes, p_a2, mean + sd * rng.standard_normal(), 72.0 + 14.0 * rng.standard_normal()


def main() -> None:
    rng = np.random.default_rng(5)
    params = TrendParams()
    prior_level = (72.0, 14.0)
    lines = [
        "# Tendencia del filtrado glomerular: comprobación en simulación",
        "",
        "Generado por `scripts/validate_trend.py`. **No es una validación con pacientes**: NHANES no tiene analíticas "
        f"repetidas. Son {N} pacientes simulados con los supuestos del propio modelo (pendiente, ruido de la creatinina "
        "y efecto de los tratamientos tomados de la literatura), con una analítica al año.",
        "",
    ]

    # 1 y 2: calibración y detección según el número de analíticas.
    rows = []
    for n_tests in (2, 3, 4, 5, 6):
        dates = [D0 + timedelta(days=365 * i) for i in range(n_tests)]
        cover = flagged_true = flagged_false = n_fast = n_stable = naive_false = naive_true = watch_true = watch_false = 0
        for _ in range(N):
            diabetes, p_a2, slope, level = draw_patient(rng, params)
            ms = simulate_trajectory(dates, level, slope, 66, False, rng, params=params)
            t = fit_trend(ms, 66, False, diabetes, p_a2, 0.0, prior_level=prior_level, params=params)
            lo, hi = t.interval("slope")
            cover += lo <= slope <= hi
            observed = (ms[-1].egfr - ms[0].egfr) / (n_tests - 1)  # regla a ojo: caída media entre la primera y la última
            fast, stable = slope < -5.0, slope > -2.0
            alarm = t.status in ("descenso", "descenso_rapido")
            watch = t.p_decline >= 0.5  # aviso más sensible: descenso más probable que no
            watch_true += watch and fast
            watch_false += watch and stable
            n_fast += fast
            n_stable += stable
            flagged_true += alarm and fast
            flagged_false += alarm and stable
            naive_true += observed < -5.0 and fast
            naive_false += observed < -5.0 and stable
        rows.append(
            f"| {n_tests} | {pct(cover / N)} | {pct(flagged_true / max(n_fast, 1))} | {pct(flagged_false / max(n_stable, 1), 1)} | "
            f"{pct(watch_true / max(n_fast, 1))} | {pct(watch_false / max(n_stable, 1), 1)} | "
            f"{pct(naive_true / max(n_fast, 1))} | {pct(naive_false / max(n_stable, 1), 1)} |"
        )
        print(rows[-1], flush=True)
    lines += [
        "## Detección del descenso según el número de analíticas",
        "",
        "- **Intervalo**: cuántas veces la pendiente verdadera (la inicial) cae en el intervalo del 80 % del filtro. "
        "La pendiente cambia un poco con los años, así que algo por debajo del 80 % es lo esperable.",
        "- **Visto**: de los que pierden más de 5 al año, a cuántos marca.",
        "- **Falsa alarma**: de los que pierden menos de 2 al año, a cuántos marca.",
        "- **Filtro, alerta**: marca cuando P(pendiente < -3) ≥ 80 % (lo que sale como hallazgo en la lista del cupo).",
        "- **Filtro, aviso**: marca cuando P(pendiente < -3) ≥ 50 % (tendencia dudosa o peor: conviene adelantar la analítica).",
        "- **Regla a ojo**: marcar si la caída media entre la primera y la última analítica pasa de 5 al año.",
        "",
        "| Analíticas anuales | Intervalo del 80 % | Alerta: visto | Alerta: falsa alarma | Aviso: visto | Aviso: falsa alarma | Regla a ojo: visto | Regla a ojo: falsa alarma |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
    ]

    # 3: inicio de un iSGLT2 entre la segunda y la tercera analítica.
    dates = [D0 + timedelta(days=365 * i) for i in range(4)]
    start = [TreatmentStart(D0 + timedelta(days=365 + 180), "isglt2")]
    aware = blind = n_ok = 0
    for _ in range(N):
        diabetes, p_a2, slope, level = draw_patient(rng, params)
        if slope < -2.0:  # solo pacientes que no estaban perdiendo FG deprisa
            continue
        n_ok += 1
        ms = simulate_trajectory(dates, level, slope, 66, False, rng, treatments=start, params=params)
        with_input = fit_trend(ms, 66, False, diabetes, p_a2, 0.0, treatments=start, prior_level=prior_level, params=params)
        without = fit_trend(ms, 66, False, diabetes, p_a2, 0.0, prior_level=prior_level, params=params)
        aware += with_input.status in ("descenso", "descenso_rapido")
        blind += without.status in ("descenso", "descenso_rapido")
    lines += [
        "## Inicio de un iSGLT2",
        "",
        f"{n_ok} pacientes estables (pierden menos de 2 al año) que empiezan un iSGLT2 entre la segunda y la tercera de "
        "cuatro analíticas anuales. El fármaco baja el FG unos 3 puntos al principio.",
        "",
        "| | Marcados como descenso |",
        "|---|---|",
        f"| Sin decirle al filtro que empezó el tratamiento | {pct(blind / n_ok, 1)} |",
        f"| Con el tratamiento como entrada conocida | {pct(aware / n_ok, 1)} |",
        "",
        "## Límites",
        "",
        "- Todos los parámetros son supuestos. Hay que ajustarlos con analíticas repetidas de atención primaria.",
        "- El modelo no contempla el fracaso renal agudo: una caída brusca y reversible la tomaría por descenso.",
        "- La creatinina depende de la masa muscular; un cambio grande de peso mueve el FG estimado sin que cambie el riñón.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
