"""Demostración del circuito completo con pacientes inventados (no son pacientes reales).

1. El paciente en casa: qué le dice el sistema cada día, por tres canales distintos.
2. La médica: la lista del cupo ordenada por lo que cambiaría, y la ficha de un paciente.

Uso:
    uv run python scripts/demo_casa.py
"""

from datetime import date, timedelta

from latenthealth.albuminuria import (
    FIRST_MORNING,
    KITS,
    RANDOM,
    Channel,
    Patient,
    SampleContext,
    StripSample,
    UrineSample,
    load_default_filter,
    next_step,
)
from latenthealth.assessment import ClinicalRecord, assess, describe
from latenthealth.diabetes import GlucoseReading
from latenthealth.home import BPReading, HomeLab, RhythmCheck
from latenthealth.kidney_trend import EgfrMeasurement, TreatmentStart
from latenthealth.worklist import describe as describe_worklist
from latenthealth.worklist import rank_cupo

D0 = date(2026, 11, 16)
ACTION_LABELS = {
    "tira": "TIRA",
    "tubo": "TUBO",
    "esperar": "ESPERAR",
    "fin_normal": "FIN (normal)",
    "centro": "FIN (centro de salud)",
    "repetir_cronicidad": "REPETIR A LOS 3 MESES",
}


def title(text: str) -> None:
    print("=" * 100)
    print(text)
    print("=" * 100)


def journey(name: str, patient: Patient, kit, strips=(), tubes=(), answers=()) -> None:
    """Sigue el protocolo día a día.

    ``strips`` y ``tubes`` son los resultados que irán saliendo cuando el sistema pida una tira
    o un tubo; ``answers``, las respuestas del paciente a las preguntas previas de cada prueba
    (si faltan, contesta que no a todo).
    """
    filt = load_default_filter("espana")
    strips, tubes, answers = list(strips), list(tubes), list(answers)
    print(f"\n{name}  ·  canal: {kit.channel.value}")
    day = D0
    step = next_step(filt, patient, kit, day)
    while True:
        print(f"  {day:%d/%m/%y}  [{ACTION_LABELS[step.action]}]  Al paciente: {step.patient_message}")
        print(f"            En la historia: {step.clinician_note}")
        if step.finished:
            break
        if step.action == "esperar":
            day = step.on
            step = next_step(filt, patient, kit, day)
            continue
        wants_tube = step.action == "tubo" or (step.action == "repetir_cronicidad" and kit.tube)
        queue = tubes if wants_tube else strips
        if not queue:
            break
        context = answers.pop(0) if answers else CLEAN
        if step.questions:
            print(f"            El paciente contesta a las preguntas: {describe_answers(context)}")
        if any(getattr(context, key) for key in ("exercise_24h", "fever", "menstruation", "uti_symptoms")):
            step = next_step(filt, patient, kit, day, context=context)
            continue
        day = max(step.on, day + timedelta(days=1))
        value = queue.pop(0)
        if wants_tube:
            sample = UrineSample(day, value, FIRST_MORNING, creatinine_mg_dl=100, context=context)
            what = f"laboratorio: {value:.0f} mg/g"
        else:
            sample = StripSample(day, kit.strip, value[0], value[1], context=context)
            what = f"tira: albúmina {value[0]:.0f} mg/l, creatinina {value[1]:.0f} mg/dl"
        patient.samples.append(sample)
        print(f"  {day:%d/%m/%y}  Resultado ({what})")
        step = next_step(filt, patient, kit, day)


def describe_answers(ctx: SampleContext) -> str:
    names = {"exercise_24h": "ejercicio intenso", "fever": "fiebre", "menstruation": "regla", "uti_symptoms": "escozor al orinar"}
    yes = [label for key, label in names.items() if getattr(ctx, key)]
    return "sí a " + ", ".join(yes) if yes else "no a todo"


CLEAN = SampleContext(exercise_24h=False, fever=False, menstruation=False, uti_symptoms=False)


def patients_at_home() -> None:
    title("1. EL PACIENTE EN CASA")
    journey(
        "Julián, 62 años, hipertenso; nunca se le ha mirado la albúmina",
        Patient(62, False, False, 85),
        KITS[Channel.APP],
        strips=[(10, 100)],
    )
    journey(
        "Marta, 47 años, diabética",
        Patient(47, True, True, 92),
        KITS[Channel.APP],
        strips=[(30, 100), (80, 100), (30, 50)],
        tubes=[58, 64, 71],
        answers=[SampleContext(exercise_24h=False, fever=False, menstruation=True, uti_symptoms=False)],
    )
    journey(
        "Antonio, 81 años, sin móvil",
        Patient(81, False, False, 61),
        KITS[Channel.MAIL],
        tubes=[11],
    )


def week_of_bp(sbp, dbp, start=D0 - timedelta(days=10)) -> list[BPReading]:
    return [
        BPReading(start + timedelta(days=d), sbp + (3 if d == 0 else 0) + (2 if evening else -2), dbp + (1 if evening else -1), evening)
        for d in range(7)
        for evening in (False, False, True, True)
    ]


def yearly_egfr(values, last=D0 - timedelta(days=20)) -> list[EgfrMeasurement]:
    n = len(values)
    return [EgfrMeasurement(last - timedelta(days=365 * (n - 1 - i)), v) for i, v in enumerate(values)]


CUPO = {
    "Julián (62), hipertenso sin orina": ClinicalRecord(
        age=62, female=False, bmi=29.5, waist=104, sbp=146, dbp=88, hypertension=True, bp_meds=True,
        high_cholesterol=True, cholesterol_meds=True, smoker_ever=True, has_smartphone=True,
        measured={"total_cholesterol": 205, "hdl": 46, "egfr": 84},
        home_glucose=[GlucoseReading(D0 - timedelta(days=3), 91.0, 11.0)],
    ),
    "Marta (47), diabética con tiras dudosas": ClinicalRecord(
        age=47, female=True, bmi=31.0, waist=99, sbp=128, dbp=80, diabetes=True, diabetes_pills=True, has_smartphone=True,
        urine_samples=[
            StripSample(D0 - timedelta(days=3), KITS[Channel.APP].strip, 30, 100, context=CLEAN),
            StripSample(D0 - timedelta(days=2), KITS[Channel.APP].strip, 30, 50, context=CLEAN),
        ],
        measured={"hba1c": 7.4, "total_cholesterol": 190, "hdl": 52},
    ),
    "Pedro (70), diabético con albuminuria repetida": ClinicalRecord(
        age=70, female=False, bmi=28.0, sbp=138, dbp=76, diabetes=True, diabetes_pills=True, hypertension=True,
        bp_meds=True, smoker_ever=True,
        urine_samples=[
            UrineSample(date(2026, 6, 10), 140.0, RANDOM, creatinine_mg_dl=110),
            UrineSample(date(2026, 7, 12), 95.0, FIRST_MORNING, creatinine_mg_dl=150),
            UrineSample(date(2026, 10, 15), 110.0, FIRST_MORNING, creatinine_mg_dl=140),
        ],
        measured={"egfr": 52.0, "hba1c": 7.9, "total_cholesterol": 180, "hdl": 41},
    ),
    "Rosa (68), FG que baja año tras año": ClinicalRecord(
        age=68, female=True, bmi=30.0, sbp=134, dbp=78, diabetes=True, diabetes_pills=True, hypertension=True, bp_meds=True,
        egfr_history=yearly_egfr([88, 79, 68, 60, 49]),
        measured={"hba1c": 7.1, "total_cholesterol": 198, "hdl": 55},
        self_rated_health=4, dyspnea_on_stairs=True, walk_difficulty=1, stairs_difficulty=1, hospitalized_last_year=False, pulse=82,
    ),
    "Luis (66), empezó un iSGLT2 hace un año": ClinicalRecord(
        age=66, female=False, bmi=29.0, sbp=130, dbp=76, diabetes=True, diabetes_pills=True,
        egfr_history=yearly_egfr([74, 73, 67, 66]),
        treatments=[TreatmentStart(D0 - timedelta(days=20 + 365 + 150), "isglt2")],
        urine_samples=[UrineSample(D0 - timedelta(days=30), 9.0, FIRST_MORNING, creatinine_mg_dl=120)],
        measured={"hba1c": 6.9, "total_cholesterol": 170, "hdl": 48},
    ),
    "Carmen P. (59), tensión alta en casa sin diagnóstico": ClinicalRecord(
        age=59, female=True, bmi=27.0, waist=92, sbp=138, dbp=86, has_smartphone=True,
        home_bp=week_of_bp(149, 91),
        measured={"total_cholesterol": 228, "hdl": 58, "egfr": 88},
        urine_samples=[UrineSample(D0 - timedelta(days=40), 7.0, FIRST_MORNING, creatinine_mg_dl=90)],
    ),
    "Antonio (81), sin analítica en años": ClinicalRecord(
        age=81, female=False, bmi=27.5, sbp=150, dbp=72, hypertension=True, bp_meds=True, has_smartphone=False,
        self_rated_health=4, dyspnea_on_stairs=True, walk_difficulty=2, stairs_difficulty=2, hospitalized_last_year=True, pulse=88,
    ),
    "Elena (74), punción capilar con FG 51": ClinicalRecord(
        age=74, female=True, bmi=32.0, waist=106, sbp=142, dbp=80, hypertension=True, bp_meds=True,
        home_labs={"egfr": HomeLab(51.0)},
        measured={"total_cholesterol": 215, "hdl": 60},
    ),
    "Manuel (77), pulso irregular dos días": ClinicalRecord(
        age=77, female=False, bmi=28.0, sbp=136, dbp=78, hypertension=True, bp_meds=True,
        rhythm_checks=[RhythmCheck(D0 - timedelta(days=4), True), RhythmCheck(D0 - timedelta(days=3), True)],
        measured={"egfr": 71, "total_cholesterol": 185, "hdl": 50},
        urine_samples=[UrineSample(D0 - timedelta(days=60), 12.0, FIRST_MORNING, creatinine_mg_dl=100)],
    ),
    "Lucía (45), sana y bien estudiada": ClinicalRecord(
        age=45, female=True, bmi=23.0, sbp=116, dbp=72,
        measured={"egfr": 101, "hba1c": 5.2, "total_cholesterol": 180, "hdl": 65},
        urine_samples=[UrineSample(D0 - timedelta(days=90), 4.0, FIRST_MORNING, creatinine_mg_dl=110)],
        self_rated_health=1, dyspnea_on_stairs=False, walk_difficulty=0, stairs_difficulty=0, hospitalized_last_year=False, pulse=62,
    ),
    "Ramón (56), obeso y fumador, sin orina ni creatinina": ClinicalRecord(
        age=56, female=False, bmi=34.0, waist=116, sbp=142, dbp=90, hypertension=True, smoker_now=True, prediabetes=True,
        has_smartphone=True, measured={"total_cholesterol": 240, "hdl": 38},
        self_rated_health=3, dyspnea_on_stairs=True, walk_difficulty=0, stairs_difficulty=0, hospitalized_last_year=False, pulse=78,
        family_diabetes=True,
        home_glucose=[GlucoseReading(D0 - timedelta(days=d), value, 10.0) for d, value in ((6, 134.0), (4, 141.0), (2, 129.0))],
    ),
}


def carmen() -> None:
    title("2. LA MÉDICA: LISTA DEL CUPO")
    rows = rank_cupo(CUPO, as_of=D0)
    print(describe_worklist(rows))
    for name in ("Rosa (68), FG que baja año tras año", "Antonio (81), sin analítica en años"):
        print()
        title(f"Ficha: {name}")
        print(describe(assess(CUPO[name], as_of=D0)))


def main() -> None:
    patients_at_home()
    print()
    carmen()


if __name__ == "__main__":
    main()
