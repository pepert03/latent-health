"""Demostración con pacientes inventados del cupo de Carmen (no son pacientes reales).

Uso:
    uv run python scripts/demo.py
"""

from datetime import date

from latenthealth.albuminuria import FIRST_MORNING, RANDOM, UrineSample
from latenthealth.assessment import ClinicalRecord, assess, describe

PATIENTS = {
    "1. Hipertenso de 62 años, nunca se le ha pedido UACR": ClinicalRecord(
        age=62, female=False, bmi=29.5, waist=104, sbp=146, dbp=88, hypertension=True, bp_meds=True,
        high_cholesterol=True, cholesterol_meds=True, smoker_ever=True,
    ),
    "2. Diabética de 58 años con una muestra aleatoria de 38 mg/g": ClinicalRecord(
        age=58, female=True, bmi=31.0, waist=99, sbp=132, dbp=80, diabetes=True, diabetes_pills=True,
        hypertension=True, bp_meds=True,
        urine_samples=[UrineSample(date(2026, 10, 2), 38.0, RANDOM, creatinine_mg_dl=85)],
        measured={"hba1c": 7.4},
    ),
    "3. Diabético de 70 años, FG 52, tres muestras en cuatro meses": ClinicalRecord(
        age=70, female=False, bmi=28.0, sbp=138, dbp=76, diabetes=True, diabetes_pills=True, hypertension=True,
        bp_meds=True, coronary=True, smoker_ever=True,
        urine_samples=[
            UrineSample(date(2026, 6, 10), 140.0, RANDOM, creatinine_mg_dl=110),
            UrineSample(date(2026, 7, 12), 95.0, FIRST_MORNING, creatinine_mg_dl=150),
            UrineSample(date(2026, 10, 15), 110.0, FIRST_MORNING, creatinine_mg_dl=140),
        ],
        measured={"egfr": 52.0, "hba1c": 7.9},
    ),
    "4. Mujer de 45 años, una muestra aleatoria de 260 mg/g en orina muy diluida": ClinicalRecord(
        age=45, female=True, bmi=24.0, sbp=118, dbp=74,
        urine_samples=[UrineSample(date(2026, 11, 3), 260.0, RANDOM, creatinine_mg_dl=22)],
    ),
    "5. Hombre de 78 años, obeso, hipertenso y con cardiopatía isquémica, sin analítica reciente": ClinicalRecord(
        age=78, female=False, bmi=33.0, waist=118, sbp=152, dbp=70, hypertension=True, bp_meds=True,
        coronary=True, high_cholesterol=True, cholesterol_meds=True, smoker_ever=True,
        urine_samples=[UrineSample(date(2026, 11, 5), 55.0, FIRST_MORNING, creatinine_mg_dl=95)],
    ),
}


def main() -> None:
    for title, record in PATIENTS.items():
        print("=" * 100)
        print(title)
        print("=" * 100)
        print(describe(assess(record)))
        print()


if __name__ == "__main__":
    main()
