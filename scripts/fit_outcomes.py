"""Riesgo de muerte cardiovascular con lo que el paciente mide en casa, frente a SCORE2.

Datos: NHANES 1999-2014 enlazado con el registro de defunciones de EE. UU. (hasta 2019).
Desenlace: muerte por enfermedad del corazón o ictus en los 10 años siguientes.

Para cada nivel de recursos (solo cuestionario, más manguito, más orina, más sangre) se
entrena un modelo y se compara con SCORE2 publicado y con las variables de SCORE2 y de PREVENT
reajustadas con los mismos datos. Todo se evalúa con validación cruzada de cinco partes: cada
persona la predice un modelo que no la vio.

Guarda los modelos de casa en models/outcomes/ y escribe reports/riesgo_en_casa.md.

Uso:
    uv run python scripts/fit_outcomes.py
"""

import json
from pathlib import Path

import joblib
import numpy as np

from latenthealth import cvrisk
from latenthealth.albuminuria import PHONE_STRIP
from latenthealth.outcomes import (
    BLOCKS,
    CAUSES,
    CV_CYCLES,
    FULL_10Y_CYCLES,
    HOME_TIER,
    TIERS,
    add_strip,
    complete_home,
    event_within,
    load_cohort,
    mask_blocks,
)
from latenthealth.outcomes.data import (
    BLOOD,
    CUFF,
    DEMOGRAPHICS,
    PREVENT_FULL_VARIABLES,
    PREVENT_VARIABLES,
    QUESTIONNAIRE,
    SCORE2_VARIABLES,
    URINE_LAB,
)
from latenthealth.outcomes.evaluation import auc, bootstrap_auc, brier, c_index, calibration_table, capture, difference_interval
from latenthealth.outcomes.model import HazardModel

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models" / "outcomes"
REPORT = ROOT / "reports" / "riesgo_en_casa.md"
FOLDS = 5
SCORE2 = "SCORE2 publicado (analítica y consulta)"
SCORE2_REFIT = "Variables de SCORE2, ecuación reajustada"
CAPILLARY = [f"{v}_capilar" for v in BLOOD]
CAPILLARY_TIER = "Historia, cuestionario, manguito, orina y punción capilar"
MINIMAL_TIER = "Kit mínimo"
QUESTION_TEXT = {
    "age": "Edad",
    "female": "Sexo",
    "bmi": "Peso y talla (IMC)",
    "waist": "Cintura",
    "dx_diabetes": "Diabetes diagnosticada",
    "insulin": "Usa insulina",
    "diabetes_pills": "Toma pastillas para la diabetes",
    "dx_hypertension": "Hipertensión diagnosticada",
    "bp_meds": "Toma pastillas para la tensión",
    "dx_high_cholesterol": "Colesterol alto diagnosticado",
    "cholesterol_meds": "Toma pastillas para el colesterol",
    "dx_heart_failure": "Insuficiencia cardíaca diagnosticada",
    "dx_coronary": "Infarto, angina o enfermedad coronaria",
    "dx_stroke": "Ictus previo",
    "smoker_now": "Fuma",
    "smoker_ever": "Ha fumado",
    "health": "Salud percibida (de excelente a mala)",
    "dyspnea": "Le falta el aire al subir cuestas o escaleras",
    "walk_difficulty": "Dificultad para caminar 400 metros",
    "stairs_difficulty": "Dificultad para subir 10 escalones",
    "hospitalized": "Ingresado en el último año",
    "sbp": "Tensión sistólica",
    "dbp": "Tensión diastólica",
    "pulse": "Pulso en reposo",
    "pulse_irregular": "Pulso irregular",
    "log_uacr": "Albúmina en orina (UACR)",
    "log_urine_creatinine": "Creatinina en orina",
}


def pct(v: float, d: int = 1) -> str:
    return f"{100 * v:.{d}f} %".replace(".", ",")


def num(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}".replace(".", ",")


def table(header, rows) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(str(c) for c in r) + " |" for r in rows), ""]


def add_capillary(df, seed: int = 1):
    """Analítica por punción capilar: la misma con el error de medida supuesto en ``home.HOME_LAB_ERROR``."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    out["egfr_capilar"] = df.egfr * np.exp(0.13 * rng.standard_normal(len(df)))
    out["hba1c_capilar"] = df.hba1c + 0.35 * rng.standard_normal(len(df))
    out["total_cholesterol_capilar"] = df.total_cholesterol * np.exp(0.10 * rng.standard_normal(len(df)))
    out["hdl_capilar"] = df.hdl * np.exp(0.10 * rng.standard_normal(len(df)))
    return out


def out_of_fold(df, features, causes, kind="boosting") -> np.ndarray:
    """Riesgo a 10 años de cada persona, predicho por un modelo entrenado sin su parte."""
    fold = df.seqn.to_numpy() % FOLDS
    risk = np.full(len(df), np.nan)
    for k in range(FOLDS):
        model = HazardModel(features, kind=kind).fit(df[fold != k], causes)
        risk[fold == k] = model.risk(df[fold == k])
    return risk


def stratified_auc(event, score, groups) -> float:
    """AUC dentro de cada oleada, promediada por el número de sucesos (descarta que el modelo acierte por la época)."""
    total = weight = 0.0
    for g in np.unique(groups):
        m = groups == g
        if event[m].sum() >= 5:
            total += auc(event[m], score[m]) * event[m].sum()
            weight += event[m].sum()
    return total / weight


def permutation_importance(df, features, causes, rows, event, seed: int = 0) -> dict[str, float]:
    """Caída de AUC al barajar cada predictor en personas que el modelo no vio."""
    rng = np.random.default_rng(seed)
    fold = df.seqn.to_numpy() % FOLDS
    drops = {f: 0.0 for f in features}
    parts = [k for k in range(FOLDS) if ((fold == k) & rows).any()]  # puede faltar la parte reservada
    for k in parts:
        model = HazardModel(features).fit(df[fold != k], causes)
        part = df[(fold == k) & rows].reset_index(drop=True)
        ev = event[(fold == k) & rows]
        base = auc(ev, model.risk(part))
        for f in features:
            shuffled = part.copy()
            shuffled[f] = rng.permutation(shuffled[f].to_numpy())
            drops[f] += (base - auc(ev, model.risk(shuffled))) / len(parts)
    return drops


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    causes = CAUSES["cardiovascular"]
    cohort = load_cohort(cycles=CV_CYCLES)
    n_cohort = len(cohort)
    # Solo personas con todos los datos de casa: en NHANES un dato vacío delata a alguien más
    # frágil, y el modelo no debe aprender eso (ver ``outcomes.data.complete_home``).
    d = add_capillary(add_strip(cohort[complete_home(cohort)], PHONE_STRIP)).reset_index(drop=True)
    fold = d.seqn.to_numpy() % FOLDS

    # Personas en las que se evalúa: 40 años o más, con 10 años de seguimiento completo y con
    # los datos que necesita SCORE2 (para comparar todos los modelos en las mismas personas).
    rows = (d.cycle.isin(FULL_10Y_CYCLES) & (d.age >= 40) & np.isfinite(d[["sbp", "total_cholesterol", "hdl"]]).all(axis=1)).to_numpy()
    event = event_within(d, causes)
    ev = d[rows]
    primary = ((ev.dx_coronary != 1) & (ev.dx_stroke != 1) & (ev.dx_heart_failure != 1)).to_numpy()
    risk_group = ((ev.dx_diabetes == 1) | (ev.dx_hypertension == 1)).to_numpy()
    groups = {"Todos": np.ones(len(ev), bool), "Sin enfermedad cardiovascular previa": primary, "Con diabetes o hipertensión": risk_group}
    y = event[rows]
    print(f"{len(d)} adultos; evaluación en {len(ev)} ({int(y.sum())} muertes cardiovasculares en 10 años)", flush=True)

    # Cuestionario mínimo: los predictores de casa que más pesan, elegidos sin mirar la parte 0.
    inner = d[fold != 0].reset_index(drop=True)
    inner_rows = rows[fold != 0]
    inner_event = event[fold != 0]
    home = TIERS["Historia, cuestionario y manguito"]
    weights = permutation_importance(inner, home, causes, inner_rows, inner_event)
    ranked = sorted((f for f in home if f not in DEMOGRAPHICS), key=lambda f: -weights[f])
    minimal = DEMOGRAPHICS + ranked[:6]
    print("Kit mínimo:", minimal, flush=True)

    sets = {name: (feats, "boosting") for name, feats in TIERS.items()}
    sets[CAPILLARY_TIER] = (DEMOGRAPHICS + QUESTIONNAIRE + CUFF + URINE_LAB + CAPILLARY, "boosting")
    sets[MINIMAL_TIER] = (minimal, "boosting")
    sets[SCORE2_REFIT] = (SCORE2_VARIABLES, "linear")
    sets["Variables de SCORE2, con el método nuevo"] = (SCORE2_VARIABLES, "boosting")
    sets["Variables de PREVENT, con el método nuevo"] = (PREVENT_VARIABLES, "boosting")
    sets["Variables de PREVENT con orina y HbA1c, con el método nuevo"] = (PREVENT_FULL_VARIABLES, "boosting")

    scores = {}
    scores[SCORE2] = np.array(
        [
            float(cvrisk.score2(r.age, r.female == 1, r.smoker_now == 1, r.sbp, r.total_cholesterol, r.hdl, r.dx_diabetes == 1))
            for r in ev.itertuples()
        ]
    )
    full_risk = {}
    for name, (feats, kind) in sets.items():
        full_risk[name] = out_of_fold(d, feats, causes, kind)
        scores[name] = full_risk[name][rows]
        print(f"{name:62s} AUC {auc(y, scores[name]):.3f}", flush=True)

    boot = {g: bootstrap_auc(y[m], {k: v[m] for k, v in scores.items()}, n=500) for g, m in groups.items()}
    cycles = ev.cycle.to_numpy()

    def row(name: str) -> list[str]:
        cells = [name]
        for g, m in groups.items():
            lo, hi = np.percentile(boot[g][name], [2.5, 97.5])
            cells.append(f"{num(auc(y[m], scores[name][m]))} ({num(lo, 2)}-{num(hi, 2)})")
        cells.append(num(stratified_auc(y, scores[name], cycles)))
        cells.append(pct(capture(y, scores[name], 0.2)[1], 0))
        return cells

    def versus(name: str, reference: str) -> list[str]:
        cells = [f"{name} − {reference}"]
        for g in groups:
            mean, lo, hi = difference_interval(boot[g][name], boot[g][reference])
            cells.append(f"{'+' if mean >= 0 else ''}{num(mean)} ({num(lo)} a {num(hi)})")
        return cells

    tier_names = list(TIERS)
    lines = [
        "# Riesgo cardiovascular con lo que se mide en casa",
        "",
        "Generado por `scripts/fit_outcomes.py`. Datos: NHANES 1999-2014 enlazado con el registro de defunciones de "
        f"EE. UU. (seguimiento hasta diciembre de 2019). De {n_cohort} adultos se usan los {len(d)} que tienen todos los "
        "datos de casa: en NHANES un dato vacío suele ser de alguien a quien no se pudo explorar, más frágil, y el modelo "
        "no debe aprovecharse de eso. Desenlace: **muerte por enfermedad del corazón o ictus en los 10 años siguientes**.",
        "",
        f"Evaluación: {len(ev)} personas de 40 años o más de las oleadas 1999-2008 (todas con 10 años de seguimiento), "
        f"{int(y.sum())} muertes cardiovasculares ({pct(y.mean())}). Validación cruzada de cinco partes: a cada persona la "
        "predice un modelo que no la vio. Entre paréntesis, el intervalo del 95 % por remuestreo.",
        "",
        "- **AUC**: probabilidad de que el modelo dé más riesgo a quien muere que a quien no (0,5 es azar; 1, perfecto).",
        "- **AUC dentro de cada oleada**: la misma, calculada oleada a oleada. Descarta que el modelo acierte por "
        "reconocer la época y no al paciente.",
        "- **Muertes en el 20 % de más riesgo**: de todas las muertes, cuántas caen en la quinta parte que el modelo señala.",
        "",
        "## Qué se gana con cada cosa que hace el paciente",
        "",
        "\"Historia clínica\" es lo que ya consta sin pedir nada: diagnósticos, fármacos, tabaco, peso y cintura. El "
        "\"cuestionario\" son cinco preguntas: salud percibida, falta de aire al subir cuestas, dificultad para caminar "
        "400 metros y para subir 10 escalones, e ingresos en el último año.",
        "",
        *table(
            ["Lo que se usa", *groups, "AUC dentro de cada oleada", "Muertes en el 20 % de más riesgo"],
            [row(SCORE2), row(SCORE2_REFIT), *[row(n) for n in tier_names], row(CAPILLARY_TIER)],
        ),
        "Diferencias de AUC en las mismas personas (positivo: gana el primero). Si el intervalo no incluye el cero, la "
        "diferencia es clara.",
        "",
        *table(
            ["Comparación", *groups],
            [
                versus("Historia clínica", SCORE2),
                versus("Historia y cuestionario", "Historia clínica"),
                versus("Historia y cuestionario", SCORE2),
                versus("Historia y cuestionario", SCORE2_REFIT),
                versus(HOME_TIER, SCORE2),
                versus(HOME_TIER, SCORE2_REFIT),
                versus("Historia, cuestionario y manguito", "Historia y cuestionario"),
                versus(HOME_TIER, "Historia, cuestionario y manguito"),
                versus("Historia, cuestionario, manguito y tira de orina", "Historia, cuestionario y manguito"),
                versus("Todo lo anterior y analítica de sangre", HOME_TIER),
                versus(SCORE2, "Edad y sexo"),
            ],
        ),
        "## ¿Es el método o son los datos?",
        "",
        "Las mismas variables que usan las ecuaciones de hoy, reajustadas con estos datos. Si el modelo de casa ganara "
        "solo por el método, estas filas lo igualarían.",
        "",
        *table(
            ["Lo que se usa", *groups, "AUC dentro de cada oleada", "Muertes en el 20 % de más riesgo"],
            [row(n) for n in sets if n.startswith("Variables de")] + [row("Historia y cuestionario"), row(HOME_TIER)],
        ),
    ]

    # Cuestionario mínimo.
    part0 = fold[rows] == 0
    lines += [
        "## Kit mínimo",
        "",
        "Los seis datos que más pesan (de la historia, el cuestionario y el manguito), elegidos sin usar la quinta parte reservada: "
        + "; ".join(QUESTION_TEXT[f].lower() for f in minimal[2:])
        + " (además de la edad y el sexo).",
        "",
        *table(
            ["Lo que se usa", *groups, "AUC dentro de cada oleada", "Muertes en el 20 % de más riesgo"],
            [row(MINIMAL_TIER), row("Historia y cuestionario"), row(SCORE2)],
        ),
        f"En la quinta parte reservada, que no intervino en la elección ({int(part0.sum())} personas, {int(y[part0].sum())} "
        f"muertes): kit mínimo {num(auc(y[part0], scores[MINIMAL_TIER][part0]))}, historia y cuestionario completos "
        f"{num(auc(y[part0], scores['Historia y cuestionario'][part0]))}, SCORE2 {num(auc(y[part0], scores[SCORE2][part0]))}.",
        "",
    ]

    # Qué pesa.
    importance = permutation_importance(d, TIERS[HOME_TIER], causes, rows, event)
    top = sorted(importance.items(), key=lambda kv: -kv[1])[:12]
    lines += [
        "## Qué pesa en el modelo de casa",
        "",
        "Caída de AUC al barajar cada dato (cuanto más cae, más aporta ese dato que no aporten los demás).",
        "",
        *table(["Dato", "Caída de AUC"], [[QUESTION_TEXT.get(f, f), num(v, 4)] for f, v in top]),
    ]

    # Calibración del modelo de casa.
    home_risk = scores[HOME_TIER]
    lines += [
        "## Calibración del modelo de casa",
        "",
        f"Riesgo medio predicho {pct(home_risk.mean())}, observado {pct(y.mean())}. Error cuadrático (Brier) "
        f"{num(brier(y, home_risk), 4)}; el de SCORE2 es {num(brier(y, scores[SCORE2]), 4)}, pero SCORE2 predice otra cosa "
        "(infarto e ictus, mortales o no, en Europa), así que su valor absoluto no es comparable.",
        "",
        *table(
            ["Décima parte según el riesgo predicho", "Personas", "Riesgo predicho", "Muertes observadas"],
            [[i + 1, n, pct(p), pct(o)] for i, (n, p, o) in enumerate(calibration_table(y, home_risk))],
        ),
    ]

    # Concordancia con censura en todas las oleadas con ictus como causa (1999-2014).
    all_rows = ((d.age >= 40) & np.isfinite(d[["sbp", "total_cholesterol", "hdl"]]).all(axis=1)).to_numpy()
    died_cv = ((d.dead == 1) & d.cause.isin(causes)).to_numpy()[all_rows]
    months = d.months.to_numpy()[all_rows]
    score2_all = np.array(
        [
            float(cvrisk.score2(r.age, r.female == 1, r.smoker_now == 1, r.sbp, r.total_cholesterol, r.hdl, r.dx_diabetes == 1))
            for r in d[all_rows].itertuples()
        ]
    )
    lines += [
        "## Con todo el seguimiento (1999-2014)",
        "",
        f"Índice de concordancia con censura en las {int(all_rows.sum())} personas de 40 años o más de todas las oleadas "
        f"({int(died_cv.sum())} muertes cardiovasculares, con hasta 20 años de seguimiento).",
        "",
        *table(
            ["Lo que se usa", "Índice de concordancia"],
            [[SCORE2, num(c_index(months, died_cv, score2_all))]]
            + [[n, num(c_index(months, died_cv, full_risk[n][all_rows]))] for n in (SCORE2_REFIT, "Edad y sexo", "Historia clínica", "Historia y cuestionario", HOME_TIER)],
        ),
    ]

    # Modelos finales: entrenados sin la quinta parte reservada, como el resto del proyecto. El
    # de casa se entrena además con bloques de datos borrados al azar, para que sirva con lo que
    # el paciente haya aportado hasta el momento.
    train = d[fold != 0]
    final = HazardModel(TIERS[HOME_TIER]).fit(mask_blocks(train, np.random.default_rng(0)), causes)
    reference = HazardModel(DEMOGRAPHICS).fit(train, causes)
    joblib.dump({"model": final, "features": TIERS[HOME_TIER], "causes": causes}, MODELS / "muerte_cardiovascular__casa.joblib", compress=3)
    joblib.dump({"model": reference, "features": DEMOGRAPHICS, "causes": causes}, MODELS / "muerte_cardiovascular__edad_y_sexo.joblib", compress=3)

    # Cómo responde ese modelo cuando faltan datos, en la quinta parte reservada.
    held = d[(fold == 0) & rows].reset_index(drop=True)
    y0 = event[(fold == 0) & rows]
    dedicated = {
        "Con todo": HOME_TIER,
        "Sin orina": "Historia, cuestionario y manguito",
        "Sin orina ni manguito": "Historia y cuestionario",
        "Sin cuestionario, manguito ni orina": "Historia clínica",
    }
    drops = {
        "Con todo": [],
        "Sin orina": ["orina"],
        "Sin orina ni manguito": ["orina", "manguito"],
        "Sin cuestionario": ["cuestionario"],
        "Sin cuestionario, manguito ni orina": ["cuestionario", "manguito", "orina"],
    }
    missing_rows = []
    for label, blocks in drops.items():
        part = held.copy()
        for b in blocks:
            part[BLOCKS[b]] = np.nan
        own = num(auc(y0, scores[dedicated[label]][part0])) if label in dedicated else "-"
        missing_rows.append([label, num(auc(y0, final.risk(part))), own])
    lines += [
        "## El modelo que se usa: sirve con lo que haya",
        "",
        "En el producto hay un solo modelo, entrenado con bloques de datos borrados al azar (cuestionario, peso y "
        "cintura, manguito, orina). Si el paciente aún no ha aportado algo, estima con el resto. En la quinta parte "
        f"reservada ({len(held)} personas, {int(y0.sum())} muertes), frente al modelo entrenado solo para ese caso:",
        "",
        *table(["Datos disponibles", "AUC del modelo único", "AUC del modelo específico"], missing_rows),
        f"Con solo la edad y el sexo, {num(auc(y0, reference.risk(held)))}; SCORE2, {num(auc(y0, scores[SCORE2][part0]))}.",
        "",
    ]
    meta = {
        "desenlace": "muerte por enfermedad del corazón o ictus en 10 años",
        "datos": "NHANES 1999-2014 con mortalidad enlazada hasta 2019 (EE. UU.)",
        "auc_validacion_cruzada": {name: auc(y, s) for name, s in scores.items()},
        "cuestionario_minimo": minimal,
    }
    (MODELS / "resumen.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    lines += [
        "## Límites",
        "",
        "- **Población de EE. UU.** El orden de los pacientes debería trasladarse; el riesgo absoluto no (en España se "
        "muere menos del corazón). Antes de dar porcentajes a un paciente español hay que recalibrar.",
        "- **Solo muertes.** El fichero público no tiene infartos ni ictus no mortales, que es lo que SCORE2 pretende "
        "predecir. La comparación es sobre quién muere, no sobre quién enferma.",
        "- **SCORE2 no está pensado para quien ya tiene enfermedad cardiovascular.** Por eso se da también la columna "
        "sin enfermedad previa, que es la comparación justa.",
        "- **Cuestionario hecho por un entrevistador**, no por el paciente en su móvil; y tensión y pulso tomados por "
        "personal entrenado, no en casa.",
        "- **La orina es una muestra aleatoria única medida en el laboratorio.** La fila de la tira simula su lectura "
        "con un error supuesto.",
        "- En los ficheros públicos de mortalidad, el tiempo o la causa de algunos registros están sustituidos por "
        "valores sintéticos para proteger la identidad.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe en {REPORT}")


if __name__ == "__main__":
    main()
