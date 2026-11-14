"""Simulación del cribado de albuminuria en casa con el protocolo real.

Mundo simulado: el modelo ajustado en NHANES 2009-2010 (nivel verdadero, variación entre días y
elevaciones transitorias) con las covariables reales de personas de 60 años o más o con
diabetes. Cada persona tiene hasta 8 mañanas posibles; cada política decide cuántas usa. Todas
las políticas ven las mismas mañanas, así que las diferencias son de la política y no del azar.

Se comparan:
- las reglas habituales con tiras (un positivo, dos de tres),
- el filtro con el protocolo en dos etapas (tiras y, si la duda sigue, tubo al laboratorio),
  con la tira leída con el móvil, a ojo o dando solo la categoría del cociente,
- el tubo por correo sin tiras, y
- el efecto de preguntar por el contexto de la muestra antes de hacerla.

Lo que es **supuesto y no dato**: el error de lectura de las tiras y el efecto de las preguntas
de contexto. La participación por canal solo se conoce para el tubo y la aplicación (ensayo THOMAS).

Uso:
    uv run python scripts/simulate_home.py
Escribe reports/cribado_en_casa.md.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from latenthealth.albuminuria import (
    DEFAULT_PARAMS_PATH,
    EYE_STRIP,
    FIRST_MORNING,
    KITS,
    PHONE_STRIP,
    RATIO_STRIP,
    SHARP_VISION_STRIP,
    VISION_STRIP,
    AlbuminuriaFilter,
    AlbuminuriaParams,
    Channel,
    HomeKit,
    Patient,
    SampleContext,
    StripSample,
    UrineSample,
    next_step,
)
from latenthealth.albuminuria.context import FACTORS, QUESTIONS, applies, deferral, spike_offset
from latenthealth.albuminuria.model import covariates, noise_scale, prior_components, spike_prob
from latenthealth.albuminuria.strip import simulate_reading
from latenthealth.decision import Utilities
from latenthealth.nhanes import load_pairs

REPORT = Path(__file__).resolve().parents[1] / "reports" / "cribado_en_casa.md"
D0 = date(2026, 3, 2)
N, MORNINGS, SEED = 1500, 8, 11
SPECS = {
    "móvil": PHONE_STRIP,
    "ojo": EYE_STRIP,
    "cociente": RATIO_STRIP,
    "visión": VISION_STRIP,
    "visión fina": SHARP_VISION_STRIP,
}
L30 = np.log(30.0)


@dataclass
class Person:
    age: float
    female: bool
    diabetes: bool
    egfr: float
    truth: bool  # UACR verdadero ≥ 30
    uacr: np.ndarray  # mg/g de cada mañana
    creatinine: np.ndarray  # mg/dl de cada mañana
    contexts: list  # SampleContext de cada mañana
    strips: dict  # lectura de cada tipo de tira en cada mañana


def make_world(params, rng) -> list[Person]:
    df = load_pairs()
    pop = df[(df.age >= 60) | df.diabetes].sample(N, replace=True, random_state=SEED).reset_index(drop=True)
    people = []
    for r in pop.itertuples():
        z = covariates([r.age], [r.female], [r.diabetes], [r.egfr])
        means, taus, log_w = prior_components(params, z)
        k = min(int((rng.random() > np.cumsum(np.exp(log_w[0]))).sum()), len(taus) - 1)
        x = means[0, k] + taus[k] * rng.standard_normal()
        u = rng.choice(params.dilution_quantiles[FIRST_MORNING], MORNINGS)
        contexts, offsets = [], []
        for _ in range(MORNINGS):
            answers = {q: bool(applies(q, r.female, r.age) and rng.random() < FACTORS[q].prevalence) for q in QUESTIONS}
            ctx = SampleContext(**answers)
            contexts.append(ctx)
            offsets.append(spike_offset(ctx, r.female, r.age))
        zs = np.repeat(z, MORNINGS, axis=0)
        usual = noise_scale(params, zs, FIRST_MORNING, u) * rng.standard_t(params.nu, MORNINGS)
        transient = params.spike_size + params.spike_sd * rng.standard_t(params.nu_spike, MORNINGS)
        spike = rng.random(MORNINGS) < spike_prob(params, zs, FIRST_MORNING, u, np.asarray(offsets))
        y = x + np.where(spike, transient, usual)
        strips = {name: simulate_reading(spec, y, u, rng) for name, spec in SPECS.items()}
        people.append(Person(r.age, bool(r.female), bool(r.diabetes), r.egfr, x >= L30, np.exp(y), 100.0 * np.exp(u), contexts, strips))
    return people


def strip_sample(person: Person, spec_name: str, j: int, day: date, context) -> StripSample:
    spec = SPECS[spec_name]
    a, c = person.strips[spec_name]
    if spec.ratio_only:
        return StripSample(day, spec, ratio_category=int(a[j]), context=context)
    return StripSample(day, spec, spec.albumin_levels[a[j]], spec.creatinine_levels[c[j]], context=context)


def strip_positive(person: Person, spec_name: str, j: int) -> bool:
    return strip_sample(person, spec_name, j, D0, None).nominal_uacr >= 30.0


def run_protocol(filt, person: Person, kit: HomeKit, spec_name: str | None, ask_context: bool) -> dict:
    """Sigue el protocolo con las mañanas de la persona hasta que termina."""
    samples, j, day = [], 0, D0
    strips = tubes = 0
    while True:
        patient = Patient(person.age, person.female, person.diabetes, person.egfr, samples)
        step = next_step(filt, patient, kit, day, episode_start=D0)
        status = step.assessment.status
        if step.action == "fin_normal":
            outcome = "descartada"
        elif step.action == "repetir_cronicidad" or status in ("confirmada", "pendiente_cronicidad"):
            outcome = "probable"
        elif step.action == "centro":
            outcome = "dudosa"
        else:
            outcome = None
        if outcome is None and ask_context:
            # Las preguntas previas aplazan la prueba: se salta la mañana sin gastar tira.
            while j < MORNINGS and deferral(person.contexts[j], person.female, person.age)[0]:
                j += 1
                day += timedelta(days=3)
        if outcome is None and j >= MORNINGS:
            outcome = "dudosa"
        if outcome is not None:
            return {"outcome": outcome, "strips": strips, "tubes": tubes, "days": (day - D0).days}
        day += timedelta(days=1)
        context = person.contexts[j] if ask_context else None
        if step.action == "tira":
            samples.append(strip_sample(person, spec_name, j, day, context))
            strips += 1
        else:
            samples.append(UrineSample(day, float(person.uacr[j]), FIRST_MORNING, creatinine_mg_dl=float(person.creatinine[j]), context=context))
            tubes += 1
        j += 1


def summarize(label: str, results: list[dict], truth: np.ndarray) -> dict:
    outcome = np.array([r["outcome"] for r in results])
    probable, discarded = outcome == "probable", outcome == "descartada"
    return {
        "label": label,
        "resolved": float(np.mean(outcome != "dudosa")),
        "ppv": float(truth[probable].mean()) if probable.any() else float("nan"),
        "sens": float((probable & truth).sum() / truth.sum()),
        "missed": float((discarded & truth).sum() / truth.sum()),
        "false_pos": float((probable & ~truth).sum() / (~truth).sum()),
        "strips": float(np.mean([r["strips"] for r in results])),
        "tubes": float(np.mean([r["tubes"] for r in results])),
        "days": float(np.mean([r["days"] for r in results])),
    }


def rule(label: str, positive: np.ndarray, truth: np.ndarray, strips: float) -> dict:
    return {
        "label": label,
        "resolved": 1.0,
        "ppv": float(truth[positive].mean()),
        "sens": float((positive & truth).sum() / truth.sum()),
        "missed": float((~positive & truth).sum() / truth.sum()),
        "false_pos": float((positive & ~truth).sum() / (~truth).sum()),
        "strips": strips,
        "tubes": 0.0,
        "days": strips,
    }


def pct(v: float, d: int = 0) -> str:
    return "-" if np.isnan(v) else f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def row(r: dict) -> str:
    return (
        f"| {r['label']} | {pct(r['ppv'])} | {pct(r['sens'])} | {pct(r['missed'], 1)} | {pct(1 - r['resolved'], 1)} | "
        f"{num(r['strips'])} | {num(r['tubes'])} |"
    )


def main() -> None:
    rng = np.random.default_rng(SEED)
    params = AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)
    filt = AlbuminuriaFilter(params, grid_n=300)
    people = make_world(params, rng)
    truth = np.array([p.truth for p in people])
    print(f"{N} personas; albuminuria verdadera en el {truth.mean():.1%}", flush=True)

    rules = []
    for name, label in (("móvil", "móvil"), ("ojo", "a ojo")):
        one = np.array([strip_positive(p, name, 0) for p in people])
        two_of_three = np.array([sum(strip_positive(p, name, j) for j in range(3)) >= 2 for p in people])
        rules.append(rule(f"Una tira positiva ({label})", one, truth, 1.0))
        rules.append(rule(f"Dos de tres tiras positivas ({label})", two_of_three, truth, 3.0))

    def protocol(label, kit, spec_name, ask=False, flt=filt):
        res = summarize(label, [run_protocol(flt, p, kit, spec_name, ask) for p in people], truth)
        print(label, {k: round(v, 3) for k, v in res.items() if k != "label"}, flush=True)
        return res

    app, paper, mail = KITS[Channel.APP], KITS[Channel.PAPER], KITS[Channel.MAIL]
    ratio_kit = HomeKit(Channel.APP, RATIO_STRIP)
    strips_only = HomeKit(Channel.APP, PHONE_STRIP, strips=6, tube=False)
    protocols = [
        protocol("Tiras con el móvil y tubo si hay duda", app, "móvil"),
        protocol("Solo tiras con el móvil (hasta 6, sin tubo)", strips_only, "móvil"),
        protocol("Tira de 3 categorías y tubo si hay duda", ratio_kit, "cociente"),
        protocol("Tiras leídas a ojo y tubo si hay duda", paper, "ojo"),
        protocol("Solo tubo por correo (hasta 2)", mail, None),
    ]
    with_questions = protocol("Tiras con el móvil y tubo, con preguntas previas", app, "móvil", ask=True)
    vision = protocol("Color leído en continuo, mismo error de lectura", HomeKit(Channel.APP, VISION_STRIP), "visión")
    sharp = protocol("Color leído en continuo, mitad de error", HomeKit(Channel.APP, SHARP_VISION_STRIP), "visión fina")
    # Umbral de descarte más exigente: vale 50 pruebas no dejar escapar una albuminuria (2 %).
    strict = AlbuminuriaFilter(params, grid_n=300, discard=Utilities(missed_albuminuria=50).thresholds().albuminuria_discard)
    careful = protocol("Tiras con el móvil y tubo, descartando solo por debajo del 2 %", app, "móvil", flt=strict)

    prevalence = truth.mean()
    channels = [
        ("Aplicación: tiras con el móvil y tubo", protocols[0], app),
        ("Carta o farmacia: tiras a ojo y tubo", protocols[3], paper),
        ("Correo: solo tubo", protocols[4], mail),
    ]
    channel_rows = []
    for label, res, kit in channels:
        takers = 1000 * kit.participation
        found = takers * prevalence * res["sens"]
        false = takers * (1 - prevalence) * res["false_pos"]
        source = "medida en THOMAS" if kit.participation_measured else "supuesta"
        channel_rows.append(
            f"| {label} | {pct(kit.participation)} ({source}) | {found:.0f} | {num(false)} | "
            f"{takers * res['strips']:.0f} | {takers * res['tubes']:.0f} |"
        )

    header = "| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |"
    lines = [
        "# Cribado de la albuminuria en casa: simulación del protocolo",
        "",
        f"Generado por `scripts/simulate_home.py`. {N} personas simuladas con las covariables reales de NHANES 2009-2010 "
        f"(60 años o más, o con diabetes). Albuminuria verdadera (UACR ≥ 30 mg/g) en el {pct(prevalence, 1)}. "
        "Cada política se prueba con las mismas mañanas de cada persona.",
        "",
        "- **VPP**: de las personas señaladas como positivas, cuántas tienen albuminuria de verdad.",
        "- **Positivos reales detectados**: de las que tienen albuminuria, cuántas quedan señaladas (a falta de la "
        "repetición a los tres meses que exige la cronicidad).",
        "- **Sin resolver**: terminan el kit con duda y pasan al centro de salud.",
        "",
        "## Reglas habituales con tiras",
        "",
        header,
        "|---|---|---|---|---|---|---|",
        *[row(r) for r in rules],
        "",
        "## Filtro con el protocolo en dos etapas",
        "",
        "El kit trae 3 tiras y permite hasta 2 tubos para el laboratorio. Se pasa al tubo cuando se acaban las tiras o "
        "cuando una tira más resolvería la duda con probabilidad menor del 30 %.",
        "",
        header,
        "|---|---|---|---|---|---|---|",
        *[row(r) for r in protocols],
        "",
        "## Umbral de descarte",
        "",
        "Las tiras dejan escapar albuminurias cercanas a 30 mg/g: con una tira negativa la probabilidad baja del 5 % y "
        "el protocolo termina. El umbral es una decisión de utilidad (`decision.Utilities`): si no dejar escapar una "
        "albuminuria vale 50 pruebas en vez de 20, se descarta solo por debajo del 2 %.",
        "",
        header,
        "|---|---|---|---|---|---|---|",
        row({**protocols[0], "label": "Descartar por debajo del 5 % (por defecto)"}),
        row({**careful, "label": "Descartar por debajo del 2 %"}),
        "",
        "## Leer el color en continuo con un modelo de visión",
        "",
        "El color de cada almohadilla cambia de forma gradual con la concentración; los 4 o 5 niveles son para el ojo. "
        "Un modelo de visión podría leer el tono en continuo. Aquí se simula como una tira con muchos niveles dentro del "
        "mismo rango químico (la almohadilla sigue saturando fuera de 10-150 mg/l), primero con el mismo error de lectura "
        "que la foto de hoy y después con la mitad.",
        "",
        header,
        "|---|---|---|---|---|---|---|",
        row({**protocols[0], "label": "Niveles de la tira leídos con el móvil (hoy)"}),
        row(vision),
        row(sharp),
        row({**protocols[4], "label": "Referencia: tubo al laboratorio"}),
        "",
        "## Preguntas de contexto antes de la prueba",
        "",
        "En el mundo simulado, el ejercicio intenso, la fiebre, la regla y los síntomas de infección multiplican la "
        "probabilidad de una elevación transitoria (efectos supuestos; ver `albuminuria/context.py`). Sin preguntas, el "
        "filtro no sabe qué mañanas tienen una causa. Con preguntas, la prueba se aplaza esas mañanas y el filtro sabe "
        "que las que se hacen no la tienen.",
        "",
        header,
        "|---|---|---|---|---|---|---|",
        row({**protocols[0], "label": "Sin preguntas"}),
        row({**with_questions, "label": "Con preguntas"}),
        "",
        f"Días hasta terminar (media): {num(protocols[0]['days'])} sin preguntas y {num(with_questions['days'])} con ellas "
        "(aplazar cuesta días).",
        "",
        "## Rendimiento por canal, por cada 1.000 personas invitadas",
        "",
        "Combina la participación de cada canal con lo que detecta el protocolo entre quienes participan.",
        "",
        "| Canal | Participación | Albuminurias detectadas | Falsos positivos | Tiras usadas | Tubos al laboratorio |",
        "|---|---|---|---|---|---|",
        *channel_rows,
        "",
        "## Límites",
        "",
        "- Es una simulación dentro del modelo: supone que el modelo de medida ajustado en NHANES es correcto y que las "
        "mañanas de una persona son independientes entre sí dado su nivel verdadero.",
        "- El error de lectura de las tiras (móvil, a ojo, cociente) es un supuesto. Hay que medirlo con muestras leídas "
        "a la vez con la tira y en el laboratorio (`fit_strip_spec`).",
        "- El efecto de las preguntas de contexto es un supuesto; la tabla dice cuánto se ganaría si fuera ese.",
        "- No simula la repetición a los tres meses ni el abandono a mitad del kit.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
