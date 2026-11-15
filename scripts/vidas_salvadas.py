"""Cuántas muertes al año evitaría el método en España: una estimación con supuestos explícitos.

No es un resultado medido: es una cadena de supuestos, cada uno con su fuente o marcado como
supuesto, para dar el orden de magnitud. Se calcula un escenario prudente, uno central y uno
optimista.

La vía que más pesa es la albuminuria oculta: encontrarla permite tratar con iSGLT2, que reduce la
muerte cardiovascular un 14 % (RR 0,86; metaanálisis de 13 ensayos, Lancet 2022;400:1788). La
mortalidad cardiovascular de partida sale de los datos: personas de 40 años o más de NHANES con
diabetes o hipertensión y albuminuria, con su seguimiento de mortalidad a 10 años.

Uso:
    uv run python scripts/vidas_salvadas.py
"""

from pathlib import Path

import numpy as np

from latenthealth.outcomes import CAUSES, CV_CYCLES, FULL_10Y_CYCLES, event_within, load_cohort

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "vidas_salvadas.md"


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def miles(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def main() -> None:
    d = load_cohort(cycles=CV_CYCLES)
    d = d[d.cycle.isin(FULL_10Y_CYCLES) & (d.age >= 40)]
    risk = (d.dx_diabetes == 1) | (d.dx_hypertension == 1)
    albuminuria = np.exp(d.log_uacr) >= 30
    group = d[risk & albuminuria]
    cv10 = float(event_within(group, CAUSES["cardiovascular"]).mean())
    cv_year = 1.0 - (1.0 - cv10) ** 0.1
    base = d[risk & ~albuminuria]
    cv10_base = float(event_within(base, CAUSES["cardiovascular"]).mean())
    print(f"{len(group)} personas con diabetes o hipertensión y albuminuria: muerte CV a 10 años {cv10:.1%} ({cv_year:.2%} al año)")

    # Escenarios: (prudente, central, optimista)
    target = 12_000_000  # SUPUESTO: adultos de 40+ con diabetes o hipertensión diagnosticadas en España
    prevalence = (0.15, 0.20, 0.25)  # Shin 2021: 22 % en hipertensos y 32 % en diabéticos (mediana de cohortes); ONDAAS: 14 % en todos
    unknown = (0.70, 0.75, 0.80)  # UACR en dos años al 35 % de los diabéticos y al 4 % de los hipertensos (Shin 2021)
    participation = (0.30, 0.50, 0.60)  # THOMAS: 44 % con aplicación, 59 % con tubo por correo
    found = (0.85, 0.90, 0.95)  # el filtro confirma casi todas las albuminurias reales (validacion_albuminuria.md)
    treated = (0.30, 0.50, 0.70)  # SUPUESTO: hoy solo 10-33 % de los candidatos toma iSGLT2
    rr = (0.95, 0.86, 0.81)  # muerte CV con iSGLT2: 0,86 (0,81-0,92), Lancet 2022
    scenarios = []
    for i in range(3):
        hidden = target * prevalence[i] * unknown[i]
        reached = hidden * participation[i] * found[i]
        on_drug = reached * treated[i]
        lives = on_drug * cv_year * (1.0 - rr[i])
        scenarios.append((hidden, reached, on_drug, lives))
        print(f"escenario {i}: ocultas {hidden:,.0f}; encontradas {reached:,.0f}; tratadas {on_drug:,.0f}; vidas/año {lives:,.0f}")

    names = ("Prudente", "Central", "Optimista")
    lines = [
        "# Vidas que salvaría el método en España: estimación con supuestos",
        "",
        "Generado por `scripts/vidas_salvadas.py`. **No es un resultado medido**: es una cadena de supuestos para dar "
        "el orden de magnitud. Cada eslabón dice de dónde sale.",
        "",
        "## La vía que se cuenta: albuminuria oculta tratada con iSGLT2",
        "",
        f"- **Mortalidad de partida (dato):** de las {len(group)} personas de 40 años o más con diabetes o hipertensión y "
        f"albuminuria de NHANES 1999-2008, murió del corazón o de un ictus el {pct(cv10)} en 10 años ({pct(cv_year, 2)} al "
        f"año). Con la misma diabetes o hipertensión y sin albuminuria, el {pct(cv10_base)}.",
        "- **Efecto del tratamiento (publicado):** los iSGLT2 reducen la muerte cardiovascular un 14 % (RR 0,86; "
        "intervalo 0,81 a 0,92; metaanálisis de 13 ensayos y 90.409 personas, Lancet 2022;400:1788).",
        "",
        "| Eslabón | Prudente | Central | Optimista | De dónde sale |",
        "|---|---|---|---|---|",
        f"| Adultos de 40+ con diabetes o hipertensión | {miles(target)} | {miles(target)} | {miles(target)} | **Supuesto** (orden de magnitud con la prevalencia de di@bet.es) |",
        f"| Con albuminuria | {pct(prevalence[0], 0)} | {pct(prevalence[1], 0)} | {pct(prevalence[2], 0)} | Por debajo de lo medido: 22 % en hipertensos y 32 % en diabéticos (Shin 2021); 14 % en todos los adultos (ONDAAS) |",
        f"| Sin medir ni diagnosticar | {pct(unknown[0], 0)} | {pct(unknown[1], 0)} | {pct(unknown[2], 0)} | UACR en dos años al 35 % de los diabéticos y al 4 % de los hipertensos (Shin 2021) |",
        f"| Albuminurias ocultas | {miles(scenarios[0][0])} | {miles(scenarios[1][0])} | {miles(scenarios[2][0])} | |",
        f"| Participan en el cribado en casa | {pct(participation[0], 0)} | {pct(participation[1], 0)} | {pct(participation[2], 0)} | THOMAS: 44 % con aplicación, 59 % con tubo |",
        f"| El circuito la confirma | {pct(found[0], 0)} | {pct(found[1], 0)} | {pct(found[2], 0)} | Filtro de albuminuria (validacion_albuminuria.md) |",
        f"| Empiezan iSGLT2 | {pct(treated[0], 0)} | {pct(treated[1], 0)} | {pct(treated[2], 0)} | **Supuesto**; hoy lo toma el 10-33 % de los candidatos |",
        f"| Personas tratadas | {miles(scenarios[0][2])} | {miles(scenarios[1][2])} | {miles(scenarios[2][2])} | |",
        f"| Reducción de la muerte cardiovascular | {pct(1 - rr[0], 0)} | {pct(1 - rr[1], 0)} | {pct(1 - rr[2], 0)} | Lancet 2022 (central y extremo del intervalo; el prudente, por debajo) |",
        f"| **Muertes evitadas al año** | **{miles(scenarios[0][3])}** | **{miles(scenarios[1][3])}** | **{miles(scenarios[2][3])}** | |",
        "",
        "## Lo que no se cuenta",
        "",
        "- **Diabetes oculta.** Encontrarla antes no ha demostrado reducir la mortalidad a 5-10 años (ensayo ADDITION); "
        "su beneficio llega por la vía del riñón y del corazón, que ya se cuenta arriba.",
        "- **Fibrilación auricular.** El cribado no ha demostrado reducir ictus ni muertes de forma clara (LOOP, "
        "STROKESTOP).",
        "- **Fracción de eyección baja.** El tratamiento salva vidas en quien tiene síntomas (DAPA-HF: muerte 11,6 % frente "
        "a 13,9 % en 18 meses), pero el ECG solo llega a quien tiene reloj o un infarto previo: decenas de vidas al año, "
        "no centenares, con supuestos aún más débiles.",
        "- **Muertes por riñón** (diálisis evitada) e ingresos por insuficiencia cardíaca, que los iSGLT2 también reducen.",
        "",
        "Para comparar: en España mueren 113.620 personas al año por enfermedades del sistema circulatorio (INE, 2024).",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
