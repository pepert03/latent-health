"""Practice-list worklist: whom to look at first and which test to order.

This is what the family doctor sees. It does not rank by "who is worst" (the doctor already
knows that) but by **what would change**:

1. **Act.** Patients with a finding that is already clear but not in the record (persistent
   albuminuria without recorded CKD, falling eGFR, high home blood pressure...). No further
   test is needed to see it.
2. **Measure.** Patients likely to have a new finding if the tests are completed (higher
   cardiovascular risk category, unrecorded kidney disease or undiagnosed diabetes), ranked by
   that probability, with the most informative test and how to do it from home.
3. **Nothing pending.** Everyone else.

So a known, well-studied high-risk patient takes up no space, while an apparently healthy one
with a high chance of hidden albuminuria moves up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import cvrisk
from .assessment import ClinicalRecord, PatientAssessment, assess, warm_up
from .decision import Thresholds
from .i18n import Labels, t

# Group values are machine keys (compared by the front end and tests); GROUP_LABELS is the display text.
ACT, MEASURE, NOTHING = "actuar", "medir", "sin pendientes"
GROUP_LABELS = Labels({ACT: ("Actuar", "Act"), MEASURE: ("Medir", "Measure"), NOTHING: ("Sin pendientes", "Nothing pending")})
# Keyed by the machine test keys of ``finding_by_test``.
HOW_AT_HOME = Labels(
    {
        "orina": ("kit de orina en casa", "home urine kit"),
        "creatinina": ("punción capilar en casa o analítica", "finger-prick at home or lab test"),
        "glucosa": ("una medida en la farmacia, o con su glucómetro", "one reading at the pharmacy, or with their own glucose meter"),
        "HbA1c": ("analítica", "lab test"),
        "lípidos": ("analítica", "lab test"),
        "ecocardiograma": ("cardiología o ecógrafo de bolsillo en el centro", "cardiology, or pocket ultrasound at the health center"),
    }
)
# Display text for the home-test channel values (``albuminuria.Channel``, machine keys).
CHANNEL_LABELS = Labels(
    {
        "aplicación": ("aplicación", "app"),
        "carta": ("carta", "paper"),
        "farmacia": ("farmacia", "pharmacy"),
        "enfermería": ("enfermería", "nurse"),
        "correo": ("correo", "mail"),
    }
)


@dataclass
class WorklistRow:
    patient_id: str
    group: str  # ACT, MEASURE or NOTHING (machine keys)
    recorded: str  # cardiovascular risk category on record today
    probable: str  # the most likely one given everything unknown
    p_up: float  # probability that the true one is higher than the recorded one
    p_finding: float  # probability of a new finding once the tests are done
    relative_risk: float | None  # cardiovascular death relative to age and sex (home model)
    test: str | None  # the most informative test (machine key of ``finding_by_test``)
    how: str  # how to do it
    reasons: list[str] = field(default_factory=list)
    assessment: PatientAssessment | None = field(default=None, repr=False)

    @property
    def sort_key(self) -> tuple:
        order = {ACT: 0, MEASURE: 1, NOTHING: 2}[self.group]
        category = self.assessment.cv.category if self.assessment else 0
        return (order, -category if self.group == ACT else 0, -self.p_finding)


def row_for(patient_id: str, a: PatientAssessment, min_p: float = 0.05) -> WorklistRow:
    cv = a.cv
    # The most informative test; on a tie (to the percentage point), the one done at home without a needle.
    order = {"orina": 0, "glucosa": 1, "creatinina": 2, "HbA1c": 3, "lípidos": 4, "ecocardiograma": 5}
    tests = sorted(a.finding_by_test, key=lambda k: (-round(a.finding_by_test[k], 2), order.get(k, 9)))
    test = tests[0] if tests and a.finding_by_test[tests[0]] > 0 else None
    how = ""
    if test == "orina":
        how = f"{HOW_AT_HOME[test]} ({CHANNEL_LABELS.get(a.channel, a.channel)})"
    elif test:
        how = HOW_AT_HOME[test]
    if a.alerts:
        group, reasons = ACT, list(a.alerts)
    elif a.p_new_finding >= min_p:
        group = MEASURE
        by_test = sorted(a.finding_by_test.items(), key=lambda kv: -kv[1])
        detail = ", ".join(f"{cvrisk.TEST_LABELS.get(k, k)} {p:.0%}" for k, p in by_test if p >= 0.005)
        if detail:
            reasons = [t(f"Hallazgo nuevo por prueba: {detail}.", f"New finding by test: {detail}.")]
        else:
            reasons = [t("Puede haber un hallazgo nuevo.", "There may be a new finding.")]
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
    """Assesses every patient on the practice list and ranks them.

    ``min_p``: minimum probability of a new finding to enter the measure group.
    """
    warm_up(records.values(), population)
    rows = [
        row_for(pid, assess(record, as_of=as_of, population=population, thresholds=thresholds, detail=False), min_p)
        for pid, record in records.items()
    ]
    return sorted(rows, key=lambda r: r.sort_key)


def describe(rows: list[WorklistRow], limit: int | None = None) -> str:
    """The list as text, by group."""
    lines = []
    for group, title in (
        (ACT, t("ACTUAR: hallazgos claros que no constan en la historia", "ACT: clear findings not in the record")),
        (MEASURE, t("MEDIR: probabilidad de un hallazgo nuevo si se completan las pruebas", "MEASURE: probability of a new finding if the tests are completed")),
    ):
        chosen = [r for r in rows if r.group == group][:limit]
        if not chosen:
            continue
        lines.append(title)
        for r in chosen:
            if r.relative_risk is None:
                times = ""
            else:
                times = t(
                    f" · {r.relative_risk:.1f} veces el riesgo de su edad".replace(".", ","),
                    f" · {r.relative_risk:.1f} times the risk for their age",
                )
            if group == ACT:
                lines.append(t(f"  {r.patient_id} · riesgo {r.probable}{times}", f"  {r.patient_id} · {r.probable} risk{times}"))
                lines += [f"      - {reason}" for reason in r.reasons]
            else:
                test = cvrisk.TEST_LABELS.get(r.test, r.test) if r.test else "-"
                how = f" ({r.how})" if r.how else ""
                lines.append(
                    t(
                        f"  {r.patient_id} · riesgo que consta: {r.recorded}{times} · hallazgo nuevo {r.p_finding:.0%} "
                        f"(sube de categoría {r.p_up:.0%}) · pedir primero: {test}{how}",
                        f"  {r.patient_id} · recorded risk: {r.recorded}{times} · new finding {r.p_finding:.0%} "
                        f"(moves up a category {r.p_up:.0%}) · order first: {test}{how}",
                    )
                )
                lines += [f"      - {reason}" for reason in r.reasons]
        lines.append("")
    rest = sum(r.group == NOTHING for r in rows)
    lines.append(t(f"Sin pendientes: {rest} de {len(rows)} pacientes.", f"Nothing pending: {rest} of {len(rows)} patients."))
    return "\n".join(lines)
