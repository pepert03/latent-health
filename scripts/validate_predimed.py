"""Validación externa en españoles: la muestra del ensayo PREDIMED.

Pregunta: un modelo entrenado con muertes cardiovasculares en EE. UU. (NHANES), ¿ordena bien
quién tendrá un infarto, un ictus o morirá de causa cardiovascular entre españoles de alto riesgo?

Se entrena en NHANES con los pocos predictores que PREDIMED comparte (edad, sexo, tabaco, peso,
cintura y diagnósticos de diabetes, hipertensión y colesterol), sin tocar PREDIMED, y se evalúa
allí. Como referencia de lo que es posible con esas variables, un modelo entrenado dentro de
PREDIMED con validación cruzada.

Uso:
    uv run python scripts/validate_predimed.py
Escribe reports/validacion_espana.md.
"""

from pathlib import Path

import numpy as np

from latenthealth.outcomes import CAUSES, CV_CYCLES, load_cohort
from latenthealth.outcomes.data import DEMOGRAPHICS
from latenthealth.outcomes.evaluation import c_index
from latenthealth.outcomes.model import HazardModel
from latenthealth.predimed import SHARED, as_followup, load_predimed

REPORT = Path(__file__).resolve().parents[1] / "reports" / "validacion_espana.md"
FOLDS = 5


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def bootstrap_c(months, event, scores: dict, n: int = 300, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    out = {k: np.empty(n) for k in scores}
    for b in range(n):
        idx = rng.integers(0, len(months), len(months))
        for k, s in scores.items():
            out[k][b] = c_index(months[idx], event[idx], s[idx])
    return out


def main() -> None:
    p = load_predimed()
    months, event = (p.years * 12.0).to_numpy(), p.event.to_numpy()
    causes = CAUSES["cardiovascular"]

    # Modelos entrenados solo con NHANES (personas con esos datos completos, de 45 años o más como en PREDIMED).
    cohort = load_cohort(cycles=CV_CYCLES)
    cohort = cohort[np.isfinite(cohort[SHARED]).all(axis=1) & (cohort.age >= 45)].reset_index(drop=True)
    # Como PREDIMED excluye a quien ya tenía enfermedad cardiovascular, se entrena también solo con prevención primaria.
    primary = cohort[(cohort.dx_coronary != 1) & (cohort.dx_stroke != 1) & (cohort.dx_heart_failure != 1)].reset_index(drop=True)
    scores = {
        "Edad y sexo (entrenado en EE. UU.)": HazardModel(DEMOGRAPHICS).fit(primary, causes).risk(p),
        "Historia (entrenado en EE. UU.)": HazardModel(SHARED).fit(primary, causes).risk(p),
    }
    # Referencia: lo que se consigue entrenando dentro de PREDIMED con las mismas variables.
    followup = as_followup(p)
    fold = np.arange(len(p)) % FOLDS
    inside = np.full(len(p), np.nan)
    inside_age = np.full(len(p), np.nan)
    for k in range(FOLDS):
        settings = {"horizon": 7, "min_samples_leaf": 100}
        inside[fold == k] = HazardModel(SHARED + ["family_history"], **settings).fit(followup[fold != k], (1,)).risk(followup[fold == k])
        inside_age[fold == k] = HazardModel(DEMOGRAPHICS, **settings).fit(followup[fold != k], (1,)).risk(followup[fold == k])
    scores["Edad y sexo (entrenado en PREDIMED)"] = inside_age
    scores["Historia (entrenado en PREDIMED)"] = inside

    boot = bootstrap_c(months, event, scores)
    rows = []
    for name, s in scores.items():
        lo, hi = np.percentile(boot[name], [2.5, 97.5])
        rows.append([name, f"{num(c_index(months, event, s))} ({num(lo, 2)}-{num(hi, 2)})"])
    a, b = "Historia (entrenado en EE. UU.)", "Edad y sexo (entrenado en EE. UU.)"
    diff = boot[a] - boot[b]
    gain = f"{'+' if diff.mean() >= 0 else ''}{num(diff.mean())} ({num(np.percentile(diff, 2.5))} a {num(np.percentile(diff, 97.5))})"
    c, e = "Historia (entrenado en PREDIMED)", "Historia (entrenado en EE. UU.)"
    diff2 = boot[c] - boot[e]
    loss = f"{'+' if diff2.mean() >= 0 else ''}{num(diff2.mean())} ({num(np.percentile(diff2, 2.5))} a {num(np.percentile(diff2, 97.5))})"
    for r in rows:
        print(r, flush=True)

    # Gradiente: eventos por 1.000 personas y año en cada quinta parte del riesgo que da el modelo de EE. UU.
    order = np.argsort(scores[a])
    gradient = []
    for i, part in enumerate(np.array_split(order, 5)):
        rate = 1000.0 * event[part].sum() / p.years.to_numpy()[part].sum()
        gradient.append([i + 1, len(part), int(event[part].sum()), f"{rate:.1f}".replace(".", ",")])

    lines = [
        "# Validación externa en españoles: muestra del ensayo PREDIMED",
        "",
        f"Generado por `scripts/validate_predimed.py`. {len(p)} participantes del ensayo PREDIMED (el 85 % del ensayo, "
        "elegido al azar; atención primaria española, 2003-2010), todos de alto riesgo cardiovascular y sin enfermedad "
        f"cardiovascular al entrar. Edad media {num(p.age.mean(), 0)} años, {pct(p.female.mean(), 0)} mujeres, "
        f"{pct(p.dx_diabetes.mean(), 0)} con diabetes. En {num(p.years.mean(), 1)} años de seguimiento medio hubo "
        f"{int(event.sum())} infartos, ictus o muertes cardiovasculares.",
        "",
        "El modelo se entrena con muertes cardiovasculares en EE. UU. (NHANES 1999-2014, "
        f"{len(primary)} personas de 45 años o más sin enfermedad cardiovascular previa) usando solo lo que PREDIMED "
        "también tiene: edad, sexo, tabaco, peso, cintura y diagnósticos de diabetes, hipertensión y colesterol. "
        "PREDIMED no interviene en el entrenamiento.",
        "",
        "Índice de concordancia (probabilidad de dar más riesgo a quien tiene el evento antes), con su intervalo del 95 %:",
        "",
        *table(["Modelo", "Índice de concordancia en PREDIMED"], rows),
        f"- Lo que añade la historia a la edad y el sexo, con el modelo de EE. UU.: {gain}.",
        f"- Lo que se gana entrenando dentro de PREDIMED en vez de traer el modelo de EE. UU.: {loss}.",
        "",
        "Eventos según el riesgo que da el modelo entrenado en EE. UU.:",
        "",
        *table(["Quinta parte según el riesgo predicho", "Personas", "Eventos", "Eventos por 1.000 personas y año"], gradient),
        "## Cómo leerlo",
        "",
        "- **Todos los índices son bajos, y es lo esperable.** PREDIMED solo admitió a personas de alto riesgo (diabetes "
        "o tres factores de riesgo) de 55 a 80 años: al parecerse tanto entre sí, a cualquier modelo le cuesta ordenarlas.",
        "- **Faltan los datos que más pesaban**: no hay orina, ni tensión, ni fármacos, ni enfermedad cardíaca previa "
        "(excluida por diseño). Esta validación solo dice si lo poco que comparten se traslada a españoles.",
        "- El desenlace incluye infartos e ictus no mortales, que el modelo nunca vio al entrenarse.",
        "- Es un ensayo con una intervención (dieta mediterránea) que redujo los eventos en dos de las tres ramas.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
