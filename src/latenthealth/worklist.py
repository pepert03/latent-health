"""Lista de trabajo del cupo: a quién mirar primero y qué prueba pedirle.

Es lo que ve la médica. No ordena por "quién está peor" (eso ya lo sabe), sino por **lo que
cambiaría**:

1. **Actuar.** Pacientes con un hallazgo ya claro que no está recogido en la historia
   (albuminuria persistente sin ERC registrada, FG que cae, tensión alta en casa...). No
   necesitan otra prueba para verlos.
2. **Medir.** Pacientes con probabilidad de un hallazgo nuevo si se completan las pruebas
   (subir de categoría de riesgo cardiovascular, enfermedad renal que no consta o diabetes sin
   diagnosticar), ordenados por esa probabilidad, con la prueba que más aporta y cómo hacerla
   desde casa.
3. **Sin pendientes.** El resto.

Así un paciente de riesgo ya conocido y bien estudiado no ocupa sitio, y uno aparentemente
sano con mucha probabilidad de albuminuria oculta sube.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import cvrisk
from .assessment import ClinicalRecord, PatientAssessment, assess, warm_up
from .decision import Thresholds

ACT, MEASURE, NOTHING = "actuar", "medir", "sin pendientes"
HOW_AT_HOME = {
    "orina": "kit de orina en casa",
    "creatinina": "punción capilar en casa o analítica",
    "glucosa": "glucómetro en casa",
    "HbA1c": "analítica",
    "lípidos": "analítica",
}


@dataclass
class WorklistRow:
    patient_id: str
    group: str  # "actuar", "medir" o "sin pendientes"
    recorded: str  # categoría de riesgo cardiovascular que consta hoy
    probable: str  # la más probable con todo lo que no se sabe
    p_up: float  # probabilidad de que la real sea mayor que la que consta
    p_finding: float  # probabilidad de un hallazgo nuevo al completar las pruebas
    relative_risk: float | None  # muerte cardiovascular respecto a su edad y sexo (modelo de casa)
    test: str | None  # la prueba que más aporta
    how: str  # cómo hacerla
    reasons: list[str] = field(default_factory=list)
    assessment: PatientAssessment | None = field(default=None, repr=False)

    @property
    def sort_key(self) -> tuple:
        order = {ACT: 0, MEASURE: 1, NOTHING: 2}[self.group]
        category = self.assessment.cv.category if self.assessment else 0
        return (order, -category if self.group == ACT else 0, -self.p_finding)


def row_for(patient_id: str, a: PatientAssessment, min_p: float = 0.05) -> WorklistRow:
    cv = a.cv
    # La prueba que más aporta; a igualdad (al punto porcentual), la que se hace en casa sin pinchar.
    order = {"orina": 0, "glucosa": 1, "creatinina": 2, "HbA1c": 3, "lípidos": 4}
    tests = sorted(a.finding_by_test, key=lambda t: (-round(a.finding_by_test[t], 2), order.get(t, 9)))
    test = tests[0] if tests and a.finding_by_test[tests[0]] > 0 else None
    how = ""
    if test == "orina":
        how = f"{HOW_AT_HOME[test]} ({a.channel})"
    elif test:
        how = HOW_AT_HOME[test]
    if a.alerts:
        group, reasons = ACT, list(a.alerts)
    elif a.p_new_finding >= min_p:
        group = MEASURE
        by_test = sorted(a.finding_by_test.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{t} {p:.0%}" for t, p in by_test if p >= 0.005)
        reasons = [f"Hallazgo nuevo por prueba: {detail}." if detail else "Puede haber un hallazgo nuevo."]
    else:
        group, reasons = NOTHING, []
    return WorklistRow(
        patient_id,
        group,
        cvrisk.CATEGORY_LABELS[cv.recorded],
        cvrisk.CATEGORY_LABELS[cv.category],
        cv.p_up,
        a.p_new_finding,
        a.home_risk.ratio if a.home_risk is not None else None,
        test,
        how,
        reasons,
        a,
    )


def rank_cupo(
    records: dict[str, ClinicalRecord],
    as_of: date | None = None,
    population: str = "espana",
    thresholds: Thresholds | None = None,
    min_p: float = 0.05,
) -> list[WorklistRow]:
    """Evalúa a todos los pacientes del cupo y los ordena.

    ``min_p``: probabilidad mínima de hallazgo nuevo para entrar en el grupo de medir.
    """
    warm_up(records.values(), population)
    rows = [
        row_for(pid, assess(record, as_of=as_of, population=population, thresholds=thresholds, detail=False), min_p)
        for pid, record in records.items()
    ]
    return sorted(rows, key=lambda r: r.sort_key)


def describe(rows: list[WorklistRow], limit: int | None = None) -> str:
    """La lista en texto, por grupos."""
    lines = []
    for group, title in (
        (ACT, "ACTUAR: hallazgos claros que no constan en la historia"),
        (MEASURE, "MEDIR: probabilidad de un hallazgo nuevo si se completan las pruebas"),
    ):
        chosen = [r for r in rows if r.group == group][:limit]
        if not chosen:
            continue
        lines.append(title)
        for r in chosen:
            times = "" if r.relative_risk is None else f" · {r.relative_risk:.1f} veces el riesgo de su edad".replace(".", ",")
            if group == ACT:
                lines.append(f"  {r.patient_id} · riesgo {r.probable}{times}")
                lines += [f"      - {reason}" for reason in r.reasons]
            else:
                lines.append(
                    f"  {r.patient_id} · riesgo que consta: {r.recorded}{times} · hallazgo nuevo {r.p_finding:.0%} "
                    f"(sube de categoría {r.p_up:.0%}) · pedir primero: {r.test or '-'}" + (f" ({r.how})" if r.how else "")
                )
                lines += [f"      - {reason}" for reason in r.reasons]
        lines.append("")
    rest = sum(r.group == NOTHING for r in rows)
    lines.append(f"Sin pendientes: {rest} de {len(rows)} pacientes.")
    return "\n".join(lines)
