"""Demo of the full pathway with made-up patients (not real patients).

1. The patient at home: what the system tells them each day, through three different channels.
2. The family doctor: the practice-list worklist ranked by what would change, and one patient's record.
3. Each patient's kit (only what is missing) and the pulse with the watch or the camera.
4. The heart in 30 seconds: two real recordings (if downloaded) scored with each device level.

Usage:
    uv run python scripts/demo_casa.py
"""

from datetime import date, timedelta

import numpy as np

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
from latenthealth import ejection, rhythm
from latenthealth.assessment import ClinicalRecord, assess, describe
from latenthealth.diabetes import GlucoseReading
from latenthealth.home import BPReading, HomeLab, RhythmCheck, af_probability, low_ef_probability
from latenthealth.kidney_trend import EgfrMeasurement, TreatmentStart
from latenthealth.kit import Devices, checks_from_pulse, describe_kit, kit_for
from latenthealth.worklist import describe as describe_worklist
from latenthealth.worklist import rank_cupo

D0 = date(2026, 11, 16)
ACTION_LABELS = {
    "tira": "URINE STRIP",
    "tubo": "TUBE TO THE LAB",
    "esperar": "TEST POSTPONED",
    "fin_normal": "ALL DONE (normal)",
    "centro": "ALL DONE (health center)",
    "repetir_cronicidad": "REPEAT IN 3 MONTHS",
}
CHANNEL_LABELS = {
    Channel.APP: "app",
    Channel.PAPER: "letter",
    Channel.PHARMACY: "pharmacy",
    Channel.NURSE: "nurse",
    Channel.MAIL: "mail",
}


def title(text: str) -> None:
    print("=" * 100)
    print(text)
    print("=" * 100)


def journey(name: str, patient: Patient, kit, strips=(), tubes=(), answers=()) -> None:
    """Follows the protocol day by day.

    ``strips`` and ``tubes`` are the results that come out when the system asks for a strip or
    a tube; ``answers``, the patient's answers to the pre-test questions of each test (if
    missing, they answer no to everything).
    """
    filt = load_default_filter("espana")
    strips, tubes, answers = list(strips), list(tubes), list(answers)
    print(f"\n{name}  ·  channel: {CHANNEL_LABELS[kit.channel]}")
    day = D0
    step = next_step(filt, patient, kit, day)
    while True:
        print(f"  {day:%m/%d/%y}  [{ACTION_LABELS[step.action]}]  To the patient: {step.patient_message}")
        print(f"            In the record: {step.clinician_note}")
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
            print(f"            The patient answers the questions: {describe_answers(context)}")
        if any(getattr(context, key) for key in ("exercise_24h", "fever", "menstruation", "uti_symptoms")):
            step = next_step(filt, patient, kit, day, context=context)
            continue
        day = max(step.on, day + timedelta(days=1))
        value = queue.pop(0)
        if wants_tube:
            sample = UrineSample(day, value, FIRST_MORNING, creatinine_mg_dl=100, context=context)
            what = f"lab: {value:.0f} mg/g"
        else:
            sample = StripSample(day, kit.strip, value[0], value[1], context=context)
            what = f"strip: albumin {value[0]:.0f} mg/l, creatinine {value[1]:.0f} mg/dl"
        patient.samples.append(sample)
        print(f"  {day:%m/%d/%y}  Result ({what})")
        step = next_step(filt, patient, kit, day)


def describe_answers(ctx: SampleContext) -> str:
    names = {"exercise_24h": "intense exercise", "fever": "fever", "menstruation": "period", "uti_symptoms": "burning when urinating"}
    yes = [label for key, label in names.items() if getattr(ctx, key)]
    return "yes to " + ", ".join(yes) if yes else "no to everything"


CLEAN = SampleContext(exercise_24h=False, fever=False, menstruation=False, uti_symptoms=False)


def patients_at_home() -> None:
    title("1. THE PATIENT AT HOME")
    journey(
        "Julián, 62, hypertensive; albumin never checked",
        Patient(62, False, False, 85),
        KITS[Channel.APP],
        strips=[(10, 100)],
    )
    journey(
        "Marta, 47, diabetic",
        Patient(47, True, True, 92),
        KITS[Channel.APP],
        strips=[(30, 100), (80, 100), (30, 50)],
        tubes=[58, 64, 71],
        answers=[SampleContext(exercise_24h=False, fever=False, menstruation=True, uti_symptoms=False)],
    )
    journey(
        "Antonio, 81, no smartphone",
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
    "Julián (62), hypertensive, no urine test": ClinicalRecord(
        age=62, female=False, bmi=29.5, waist=104, sbp=146, dbp=88, hypertension=True, bp_meds=True,
        high_cholesterol=True, cholesterol_meds=True, smoker_ever=True, has_smartphone=True,
        measured={"total_cholesterol": 205, "hdl": 46, "egfr": 84},
        home_glucose=[GlucoseReading(D0 - timedelta(days=3), 91.0, 11.0)],
    ),
    "Marta (47), diabetic with doubtful strips": ClinicalRecord(
        age=47, female=True, bmi=31.0, waist=99, sbp=128, dbp=80, diabetes=True, diabetes_pills=True, has_smartphone=True,
        urine_samples=[
            StripSample(D0 - timedelta(days=3), KITS[Channel.APP].strip, 30, 100, context=CLEAN),
            StripSample(D0 - timedelta(days=2), KITS[Channel.APP].strip, 30, 50, context=CLEAN),
        ],
        measured={"hba1c": 7.4, "total_cholesterol": 190, "hdl": 52},
    ),
    "Pedro (70), diabetic with repeated albuminuria": ClinicalRecord(
        age=70, female=False, bmi=28.0, sbp=138, dbp=76, diabetes=True, diabetes_pills=True, hypertension=True,
        bp_meds=True, smoker_ever=True,
        urine_samples=[
            UrineSample(date(2026, 6, 10), 140.0, RANDOM, creatinine_mg_dl=110),
            UrineSample(date(2026, 7, 12), 95.0, FIRST_MORNING, creatinine_mg_dl=150),
            UrineSample(date(2026, 10, 15), 110.0, FIRST_MORNING, creatinine_mg_dl=140),
        ],
        measured={"egfr": 52.0, "hba1c": 7.9, "total_cholesterol": 180, "hdl": 41},
    ),
    "Rosa (68), eGFR falling year after year": ClinicalRecord(
        age=68, female=True, bmi=30.0, sbp=134, dbp=78, diabetes=True, diabetes_pills=True, hypertension=True, bp_meds=True,
        egfr_history=yearly_egfr([88, 79, 68, 60, 49]),
        measured={"hba1c": 7.1, "total_cholesterol": 198, "hdl": 55},
        self_rated_health=4, dyspnea_on_stairs=True, walk_difficulty=1, stairs_difficulty=1, hospitalized_last_year=False, pulse=82,
    ),
    "Luis (66), started an SGLT2 inhibitor a year ago": ClinicalRecord(
        age=66, female=False, bmi=29.0, sbp=130, dbp=76, diabetes=True, diabetes_pills=True,
        egfr_history=yearly_egfr([74, 73, 67, 66]),
        treatments=[TreatmentStart(D0 - timedelta(days=20 + 365 + 150), "isglt2")],
        urine_samples=[UrineSample(D0 - timedelta(days=30), 9.0, FIRST_MORNING, creatinine_mg_dl=120)],
        measured={"hba1c": 6.9, "total_cholesterol": 170, "hdl": 48},
    ),
    "Carmen P. (59), high home blood pressure, undiagnosed": ClinicalRecord(
        age=59, female=True, bmi=27.0, waist=92, sbp=138, dbp=86, has_smartphone=True,
        home_bp=week_of_bp(149, 91),
        measured={"total_cholesterol": 228, "hdl": 58, "egfr": 88},
        urine_samples=[UrineSample(D0 - timedelta(days=40), 7.0, FIRST_MORNING, creatinine_mg_dl=90)],
    ),
    "Antonio (81), no blood test in years": ClinicalRecord(
        age=81, female=False, bmi=27.5, sbp=150, dbp=72, hypertension=True, bp_meds=True, has_smartphone=False,
        self_rated_health=4, dyspnea_on_stairs=True, walk_difficulty=2, stairs_difficulty=2, hospitalized_last_year=True, pulse=88,
    ),
    "Elena (74), finger prick with eGFR 51": ClinicalRecord(
        age=74, female=True, bmi=32.0, waist=106, sbp=142, dbp=80, hypertension=True, bp_meds=True,
        home_labs={"egfr": HomeLab(51.0)},
        measured={"total_cholesterol": 215, "hdl": 60},
    ),
    "Manuel (77), irregular pulse two days": ClinicalRecord(
        age=77, female=False, bmi=28.0, sbp=136, dbp=78, hypertension=True, bp_meds=True,
        rhythm_checks=[RhythmCheck(D0 - timedelta(days=4), True), RhythmCheck(D0 - timedelta(days=3), True)],
        measured={"egfr": 71, "total_cholesterol": 185, "hdl": 50},
        urine_samples=[UrineSample(D0 - timedelta(days=60), 12.0, FIRST_MORNING, creatinine_mg_dl=100)],
    ),
    "Lucía (45), healthy and well studied": ClinicalRecord(
        age=45, female=True, bmi=23.0, sbp=116, dbp=72,
        measured={"egfr": 101, "hba1c": 5.2, "total_cholesterol": 180, "hdl": 65},
        urine_samples=[UrineSample(D0 - timedelta(days=90), 4.0, FIRST_MORNING, creatinine_mg_dl=110)],
        self_rated_health=1, dyspnea_on_stairs=False, walk_difficulty=0, stairs_difficulty=0, hospitalized_last_year=False, pulse=62,
    ),
    "Ramón (56), obese smoker, no urine or creatinine": ClinicalRecord(
        age=56, female=False, bmi=34.0, waist=116, sbp=142, dbp=90, hypertension=True, smoker_now=True, prediabetes=True,
        has_smartphone=True, measured={"total_cholesterol": 240, "hdl": 38},
        self_rated_health=3, dyspnea_on_stairs=True, walk_difficulty=0, stairs_difficulty=0, hospitalized_last_year=False, pulse=78,
        family_diabetes=True,
        home_glucose=[GlucoseReading(D0 - timedelta(days=d), value, 10.0) for d, value in ((6, 134.0), (4, 141.0), (2, 129.0))],
    ),
}


def carmen() -> None:
    title("2. THE FAMILY DOCTOR: PRACTICE-LIST WORKLIST")
    rows = rank_cupo(CUPO, as_of=D0)
    print(describe_worklist(rows))
    for name in ("Rosa (68), eGFR falling year after year", "Antonio (81), no blood test in years"):
        print()
        title(f"Record: {name}")
        print(describe(assess(CUPO[name], as_of=D0)))


def kits() -> None:
    """What each patient is asked to do and with what, and a pulse measurement with the watch or the camera."""
    title("3. EACH PATIENT'S KIT: WHAT THEIR RECORD SAYS IS MISSING (strips are sent, devices are lent)")
    infarction = ClinicalRecord(
        age=64, female=False, bmi=29.0, sbp=132, dbp=78, coronary=True, hypertension=True, bp_meds=True,
        diabetes=True, diabetes_pills=True, has_smartphone=True,
    )
    cases = (
        ("Julián (62), hypertensive, 146 in the office and no urine test; has a watch that measures the pulse", CUPO["Julián (62), hypertensive, no urine test"], Devices(watch_pulse=True)),
        ("Marta (47), diabetic with doubtful strips", CUPO["Marta (47), diabetic with doubtful strips"], Devices()),
        ("Elena (74), hypertensive, 142 in the office, no known diabetes: gets almost everything", CUPO["Elena (74), finger prick with eGFR 51"], Devices()),
        ("Antonio (81), hypertensive, 150 in the office, no smartphone and his own cuff", CUPO["Antonio (81), no blood test in years"], Devices(cuff=True)),
        ("Lucía (45), healthy and well studied: nothing to send her", CUPO["Lucía (45), healthy and well studied"], Devices()),
        ("Paco (64), diabetic and hypertensive after a heart attack, with an ECG watch", infarction, Devices(watch_pulse=True, watch_ecg=True)),
        ("Paco, if he had no watch", infarction, Devices()),
    )
    for name, record, devices in cases:
        print()
        print(name)
        print(describe_kit(kit_for(record, devices, as_of=D0)))
    if not rhythm.available():
        return
    print()
    print("A one-minute pulse measurement in a 77-year-old man (simulated beats):")
    rng = np.random.default_rng(0)
    regular = np.cumsum(0.85 + 0.02 * rng.standard_normal(70))
    irregular = np.cumsum(rng.uniform(0.45, 1.15, 80))
    measures = (
        ("Watch, regular pulse", rhythm.intervals_from_beats(regular), "reloj"),
        ("Camera, regular pulse", rhythm.intervals_from_beats(rhythm.degrade(regular, rng)), "cámara"),
        ("Camera, irregular pulse", rhythm.intervals_from_beats(rhythm.degrade(irregular, rng)), "cámara"),
    )
    for label, rr, source in measures:
        check, _ = checks_from_pulse(D0, rr, source)
        p = af_probability([check], 77, female=False)
        print(f"  {label:24s} multiplies the suspicion by {check.likelihood_ratio:6.2f}  ->  P(atrial fibrillation) = {p:5.1%}")


def heart() -> None:
    """Two real people from the second hospital (unseen by the model during training), one with a weak heart."""
    if not (ejection.available() and ejection.COMMUNITY_ZIP.exists()):
        return
    title("4. THE HEART IN 30 SECONDS (real recordings, Zenodo 16934966)")
    labels = ejection.read_labels(ejection.COMMUNITY_ZIP).sort_values(["lvef", "subject"])
    weak, healthy = labels.iloc[0], labels.iloc[len(labels) // 2]
    table = ejection.features_from_zip(ejection.COMMUNITY_ZIP, subjects=[weak.subject, healthy.subject], profiles=True)
    table["site_code"] = table.site.map({site: i for i, site in enumerate(ejection.SITES)})
    for person in (weak, healthy):
        recordings = table[table.subject == person.subject].to_dict("records")
        print()
        print(f"Person with an ejection fraction of {person.lvef:.0%} on echocardiography ({len(recordings)} recordings of 30 s)")
        for tier, label in (("pulso", "Pulse only"), ("ecg", "Single-lead ECG"), ("sonido", "ECG and heart sound")):
            check = ejection.check_from_recordings(D0, recordings, tier)
            p = low_ef_probability([check], 70)
            action = "order NT-proBNP and echocardiography" if p >= 0.05 else "nothing to do"
            print(f"  {label:24s} multiplies the suspicion by {check.likelihood_ratio:5.2f}  ->  P(low ejection fraction) at age 70: {p:5.1%}  ({action})")


def main() -> None:
    patients_at_home()
    print()
    carmen()
    print()
    kits()
    print()
    heart()


if __name__ == "__main__":
    main()
