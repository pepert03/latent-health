# LatentHealth: early detection of cardio-renal-metabolic disease, measured at home

Challenge 1 of the Boehringer hackathon: help the primary care doctor catch patients with
cardiovascular risk (diabetes, hypertension, chronic kidney disease, heart failure) in time,
without adding to their workload.

Our bet: **the patient measures at home, easily and as many times as needed; the doctor receives a
ranked worklist.** In between sits a model that knows how much to trust each measurement.

## 1. The problem, with data

Diabetes, hypertension, chronic kidney disease (CKD) and heart failure (HF) feed each other. The
highest-risk patients are not missed because they never get lab tests, but because of four
breaks in the chain:

1. **The urine test is not ordered.** Over two years, the albumin-to-creatinine ratio (UACR) is
   measured in 35% of people with diabetes and 4% of people with hypertension, even though
   albuminuria is almost as common in one group (32%) as in the other (22%) (meta-analysis by
   Shin et al., *Hypertension* 2021, 3.7 million adults).
2. **A single UACR is misleading and is not confirmed.** In NHANES 2009-2010, half of the positives
   from a random sample do not repeat in the first morning urine, and only 40% of A2 results stay
   A2.
3. **What shows up in the lab results does not become a diagnosis.** Over 80% of patients with
   stage 3 CKD by their lab results do not have the diagnosis recorded (REVEAL-CKD).
4. **Therapeutic inertia.** Only 10% to 33% of patients who should be on an SGLT2 inhibitor are
   taking one.

The Spanish context points the same way:

- **ONDAAS** (Burgos, 2024; 9,526 adults with lab tests in primary care): 14% had albuminuria and
  903 people had it with a normal glomerular filtration rate. A low-eGFR alert does not see them.
- **Spanish National Health System consensus on CKD** (April 2026): annual blood and urine
  screening in people over 60 and in risk groups, with automatic low-eGFR alerts in the health
  record. Those alerts will become standard; repeated, confirmed albuminuria is what remains
  unsolved.
- **Home screening.** It already exists (strip read with a phone, tube by mail). In the THOMAS trial
  (*Lancet* 2023) the mailed tube had higher participation (59% vs. 44%) and much higher
  specificity (97% vs. 68%) than the app. A home strip is a noisy measurement: you need something
  that knows how to combine several.

That is why the product is not "yet another risk model". It is a system that **closes the
albuminuria loop from home**, **estimates, with its uncertainty, what is missing for a diagnosis**
and tells the doctor whom to look at and what to order.

### Which part of cardiovascular disease it covers

In Spain the leading specific cause of death is ischemic heart disease (26,851 deaths in 2024,
provisional INE data), and the top fifteen also include stroke, heart failure, hypertensive
disease, diabetes and kidney failure, which grew the most (+10.3%). There are two mechanisms:
small-vessel damage, which links kidney and heart, and atherosclerosis of the large arteries,
which causes heart attack and stroke. The project focuses on the first, which today goes
unnoticed, and does not try to detect every heart disease:

| Disease | What the project does |
|---|---|
| Chronic kidney disease | The core: repeated albuminuria at home, eGFR and its trend |
| Diabetes | Glucometer at home: finds 86% of undiagnosed diabetes where the FINDRISC questionnaire finds 52% (section 3.12) |
| Hypertension | Blood pressure measured at home with the one-week protocol |
| Heart attack and stroke (atherosclerosis) | SCORE2 and our own cardiovascular death model trained on real outcomes and checked in Spanish people (section 3.10) |
| Heart failure | Low ejection fraction from 30 s of single-lead ECG (AUC 0.88 against echocardiography; 0.91 with heart sound), estimated NT-proBNP and severity in Spanish patients (section 3.11) |
| Arrhythmias | Our own atrial fibrillation detector based on pulse irregularity, validated on 8,528 real recordings (section 3.12) |
| Valve disease and cardiomyopathies | Nothing: they are seen with ultrasound or auscultation |

## 2. How it works

1. **The system scans the practice list.** Using the health record it computes, for each patient,
   the probability that the tests they are missing would produce a new finding.
2. **The patient receives their kit**, with only what they are missing (section 3.5), through the
   channel that works for them: app, mail, pharmacy, nurse or tube by mail.
3. **Before each test they answer four questions** (intense exercise, fever, period, burning when
   urinating). If any answer is yes, the test is postponed.
4. **They do the strip and the system replies**: "you're done", "repeat tomorrow" or "send the
   tube". Only those with a borderline result repeat.
5. **The doctor opens the worklist.** At the top, clear findings that are not in the record.
   Below, patients ranked by probability of a new finding, with the most informative test.

`scripts/demo_casa.py` shows it with made-up patients. A walkthrough:

```
Marta, 47, diabetic  ·  channel: app
  16/11  [STRIP]    Tomorrow, with your first urine of the day, do a strip and photograph it with the app.
                    Answers to the questions: yes to period
  16/11  [WAIT]     The test would not be reliable today. Wait three days after your period ends.
  22/11  Result (strip: albumin 30 mg/l, creatinine 100 mg/dl)           P(albuminuria) = 14%
  22/11  [TUBE]     To settle it we need a lab measurement. Tomorrow, fill the tube...
  23/11  Result (lab: 58 mg/g)                                           P(albuminuria) = 75%
  24/11  Result (lab: 64 mg/g)
  24/11  [REPEAT IN 3 MONTHS]  We found albumin in your urine. To confirm it we need to repeat...
  22/02  Result (lab: 71 mg/g)
  22/02  [DONE]     We found albumin in your urine more than once. Your health center will call you.
```

And the doctor's worklist:

```
ACT: clear findings not recorded in the health record
  Pedro (70), diabetic with repeated albuminuria · very high risk · 1.5 times the risk for his age
      - Persistent albuminuria with no chronic kidney disease recorded.
  Ramón (56), obese and a smoker · high risk
      - Fasting glucose of 126 mg/dl or more on two different days, measured at home: confirm with HbA1c.
  Rosa (68), eGFR falling year after year · high risk · 1.4 times the risk for her age
      - Rapid eGFR decline: -8.2 ml/min/1.73 m² per year.
  Manuel (77), irregular pulse on two days · high risk
      - Repeated irregular pulse at home (P(atrial fibrillation) = 73%).
  Carmen P. (59), high blood pressure at home, no diagnosis · low or moderate risk
      - High blood pressure at home: mean 149/91 mmHg (threshold 135/85). No hypertension recorded.

MEASURE: probability of a new finding if the tests are completed
  Elena (74), finger-prick eGFR 51 · new finding 59% · order first: creatinine
  Marta (47), diabetic with borderline strips · new finding 39% · order first: urine (home kit)
  Antonio (81), no lab tests in years · new finding 24% · order first: creatinine

Nothing pending: 3 of 11 patients.
```

## 3. What we built

### 3.1 Albuminuria Bayesian filter (`src/latenthealth/albuminuria/`)

Estimates the patient's **true** UACR from all their urine samples, even when they are of
different types, diluted or below the detection limit.

- **Hidden state:** true log-UACR, on the first-morning-urine scale.
- **Prior:** a mixture of three normals (normal, raised, very raised) whose weights and means depend
  on age, sex, diabetes and eGFR.
- **Measurement:** each sample = true level + excess depending on sample type + variation.
  - The **excess of the random sample** grows with albuminuria: ×1.23 at 3 mg/g, ×1.49 at 30 and
    ×1.81 at 300.
  - The **usual variation** is a Student's t, with more noise in dilute urine (low urine
    creatinine).
  - **Transient elevations** are heavy-tailed (exercise, posture, fever, infection, blood). They
    appear in 15% of random samples and 7% of morning samples, and are much more frequent in
    women.
  - **Albumin below the detection limit** is treated as censored data.
- **Dynamics:** random walk between dates (assumption from the literature: ±42% per year) and
  backward smoothing to draw the trajectory.
- **Decision:**
  - *Ruled out* if P(UACR ≥ 30) ≤ 5%.
  - *Borderline* if it is between 5% and 95%. Reports the probability that one more sample would
    settle the question, depending on whether it is first-morning or random.
  - *Very likely* if P ≥ 95%. Becomes *confirmed* when there are two time points with P ≥ 90%
    more than 3 months apart (KDIGO chronicity criterion).

**Fitting:** maximum likelihood with an analytic gradient (checked against finite differences)
on the 4,437 training participants from NHANES 2009-2010. Each has two urine samples: one random
and one first-morning.

**Validation** (976 test participants; full report in `reports/validacion_albuminuria.md`):

| Variant (each removes one piece from the previous one) | Test log-likelihood per person |
|---|---|
| Full model | **-1.785** |
| Light-tailed elevations | -1.789 |
| No dilution or sex/age in the sample | -1.798 |
| No growing excess in the random sample | -1.802 |
| No transient elevations | -1.825 |
| Normal noise (the "textbook" model) | -1.931 |

- **Calibration.** With a single random sample, the filter leaves 7% of people as *borderline*.
  Of these, the model expects 39.8% to be confirmed, and 38.4% are.
- **Random sample with UACR between 30 and 300.** Only 18% to 74% are confirmed in the morning,
  depending on the value, and the model reproduces this band by band.
- **Compared with other methods.** It predicts whether the next sample will be ≥ 30 better than a
  logistic regression trained only for that (log-loss 0.102 vs. 0.107; AUC 0.918 vs. 0.911). It
  also does much better than the usual "one positive is a positive" rule: Brier 0.027 vs. 0.067,
  and under that rule 60% of positives do not repeat.

### 3.2 Urine at home: strip, questions, protocol and channels

**Strip (`albuminuria/strip.py`).** A strip does not give a UACR: it gives the color level of the
albumin pad (10, 30, 80 or 150 mg/l) and of the creatinine pad (10 to 300 mg/dl). The filter
computes the probability of each reading given the true UACR, integrating over urine dilution and
each pad's reading error, and uses it just like a lab sample. It also accepts strips that only
give the ratio category. `fit_strip_spec` calibrates a specific strip with samples read both with
the strip and in the lab.

**Context questions (`albuminuria/context.py`).** Intense exercise, fever, period and infection
symptoms raise the probability of a transient elevation. If the patient answers yes, the test is
postponed; if they answer no to everything, the filter trusts a high result more.

**Two-stage protocol (`albuminuria/protocol.py`).** Strips for everyone. It switches to the lab
tube when the kit runs out of strips or when one more strip would settle the question with
probability below 30%. A clear positive is repeated after three months, as chronicity requires.

**Channels.** App (strip read with the phone), mail (strip read by eye, the patient reports two
numbers), pharmacy, nurse and mail-in (tube only). They change the reading error and the wording
of the instructions; the logic is the same.

**Simulation results** (`reports/cribado_en_casa.md`; 1,500 simulated people aged 60 or over or
with diabetes, using the real protocol and the measurement model fitted on NHANES; 10.1% have
albuminuria). PPV is the share of flagged people who truly have albuminuria.

| Policy | PPV | True positives detected | True positives ruled out | Unresolved | Strips per person | Tubes per person |
|---|---|---|---|---|---|---|
| One positive strip | 59% | 91% | 9.3% | - | 1.00 | - |
| Two of three strips positive | 67% | 94% | 6.0% | - | 3.00 | - |
| **Filter: phone-read strips and tube if borderline** | **98%** | 81% | 4.0% | 3.1% | **1.17** | 0.13 |
| Filter: 3-category strip and tube | 98% | 85% | 8.6% | 1.8% | 1.08 | 0.13 |
| Filter: strips read by eye and tube | 97% | 82% | 4.0% | 3.1% | 1.19 | 0.15 |
| Filter: mailed tube only | 99% | 73% | 2.6% | 5.6% | - | 1.11 |
| Filter: color read on a continuous scale, same reading error | 98% | 83% | 4.6% | 3.1% | 1.18 | 0.12 |
| Filter: color read on a continuous scale, half the error | 99% | 85% | 4.0% | 2.7% | 1.16 | 0.10 |

**Margin of error.** There are only about 150 people with albuminuria in the simulation: each one
is worth 0.7 points in the positive columns, and a small percentage has a margin of about ±3
points. The simulation was run twice with different populations; below, only what came out the
same both times is accepted.

What holds in both simulations:

- **The filter turns a mediocre strip into a reliable decision.** PPV goes from 55-67% to 98-99%
  with 1.2 strips per person on average and a tube for 13-15%. Those left unresolved (3%) go to
  the health center; they are not lost.
- **The strip misses more albuminuria than the tube**: between 4% and 7% vs. between 0.6% and
  2.6%. These are the cases close to 30 mg/g.
- **The strip that only gives the ratio category is the worst** (over 8% ruled out both times).
  Reading the two pads separately is worth it.
- **Per 1,000 invited, mail detects more** (44 cases of albuminuria vs. 36 with the app) because
  more people take part, but it sends ten times more tubes to the lab.

Reading the color with a vision model (`VISION_STRIP`):

- The pad color changes gradually; the 4 or 5 levels are for the human eye. A vision model could
  read it on a continuous scale.
- **With the same reading error as today's photo, almost nothing changes** (83% detected vs. 81%,
  within the margin). With half the error, 85% are detected and fewer tubes are needed.
- The gain is modest because the limit is not the number of levels: it is that urine changes from
  one day to the next and that the pad cannot distinguish below 10 mg/l.

What does **not** hold, and is therefore not claimed:

- **Lowering the rule-out threshold to 2%.** In the first simulation it halved the missed cases;
  in the second it changed nothing.
- **The context questions.** In the first they lowered missed cases by one point; in the second
  they raised them by one point. Their effect is also an assumption.

### 3.3 Virtual blood panel (`src/latenthealth/panel/`)

Estimates the full distribution of each lab variable: median, 80% interval and probability of
crossing each clinical threshold. It uses the health record (age, sex, BMI, waist, blood
pressure, diagnoses, medications, smoking) and the urine.

- **Method:** binned distributional regression. A gradient boosting classifier predicts the
  probability of each bin of the variable, and the clinical thresholds are bin edges.
- **Data:** NHANES 2009-2018 (26,762 adults) for lab tests, and NHANES 1999-2004 (11,370 adults
  with stored serum) for NT-proBNP.
- **Evaluation:** on the 20% test set (full report in `reports/panel_sangre.md`).

AUC for each clinical decision depending on what is known about the patient:

| Decision | Urine only | Age and sex | Health record | Health record and urine |
|---|---|---|---|---|
| eGFR < 60 | 0.71 | 0.88 | 0.91 | **0.92** |
| eGFR < 60 in people with diabetes or hypertension | - | 0.81 | 0.85 | **0.86** |
| HbA1c ≥ 6.5% | 0.70 | 0.71 | 0.92 | **0.93** |
| HbA1c ≥ 6.5% without a diabetes diagnosis | - | 0.67 | 0.79 | **0.81** |
| Glucose ≥ 126 | 0.69 | 0.68 | 0.85 | **0.86** |
| Non-HDL cholesterol ≥ 190 | 0.52 | 0.66 | 0.76 | **0.76** |
| Anemia | 0.49 | 0.70 | 0.76 | **0.76** |
| Potassium ≥ 5.0 (very rare) | 0.62 | 0.71 | 0.73 | 0.75 |
| NT-proBNP ≥ 125 (rules out HF in clinic) | - | 0.88 | 0.90 | **0.90** |
| NT-proBNP ≥ 125 without an HF diagnosis | - | 0.87 | 0.89 | **0.89** |
| UACR ≥ 30 in hypertension without diabetes | 0.90 | 0.65 | **0.53** | 0.91 |

The 80% intervals cover between 79% and 84% of the real values for every variable.

**What the data say, no embellishment:**

- **Urine alone does not replace a blood test.** With urine albumin, creatinine, volume and flow,
  eGFR < 60 is predicted with AUC 0.71 and everything else stays close to chance. That is why
  the panel combines urine with the health record, and why other home measurements are needed
  (section 3.5).
- **Almost all the predictive power comes from age and sex** (eGFR < 60: 0.88 → 0.92). The panel
  is for deciding whom to measure, not for skipping the measurement.
- **Potassium is unpredictable without measuring it.** Before touching ACE inhibitors/ARBs or
  finerenone it must always be measured.
- **Albuminuria cannot be guessed from the health record.** In hypertension without diabetes the
  AUC is 0.53, pure chance: the only way to find it is to order the urine test.

### 3.4 eGFR trend (`src/latenthealth/kidney_trend.py`)

The challenge brief talks about "kidney function that slowly deteriorates without any pain". A
Kalman filter on (level, slope) runs through the patient's previous creatinine values:

- **Creatinine noise.** Between two lab tests eGFR moves several points with nothing going on.
  The error of each measurement comes from creatinine variability and the CKD-EPI equation.
- **Two groups of patients.** Most lose eGFR slowly and a few quickly (more so with diabetes or
  albuminuria, which the urine filter provides). There are two filters, one per group, mixed
  according to the data.
- **Treatments as a known input.** When starting an SGLT2 inhibitor or an ACE inhibitor/ARB,
  eGFR drops a few points and then declines more slowly. If the filter is told, it does not
  mistake this for a decline.
- **Outputs.** Current level with its interval, slope, P(decline of more than 3 per year), P(more
  than 5 per year, KDIGO criterion), P(eGFR < 30 within five years) and whether there are two
  lab results below 60 more than three months apart.

**Check in simulation** (`reports/tendencia_fg.md`). This is not a validation with patients:
NHANES has no repeated lab tests and all the parameters are assumptions from the literature. Of
the patients losing more than 5 per year, how many are flagged; and of those losing less than 2,
how many are flagged by mistake:

| Annual lab tests | Filter, alert (P ≥ 80%) | False alarm | Filter, warning (P ≥ 50%) | False alarm | Eyeball rule (mean drop > 5 per year) | False alarm |
|---|---|---|---|---|---|---|
| 2 | 1% | 0.0% | 6% | 0.3% | 60% | 24.3% |
| 3 | 17% | 0.2% | 38% | 1.1% | 62% | 11.2% |
| 4 | 45% | 0.2% | 72% | 1.2% | 79% | 3.5% |
| 5 | 71% | 0.2% | 90% | 1.5% | 78% | 1.5% |
| 6 | 88% | 0.3% | 96% | 1.9% | 85% | 0.7% |

- **What it adds is removing false alarms.** With two lab tests, eyeballing the drop wrongly
  flags one in four stable patients; the filter, almost none.
- **It is cautious.** With three or four lab tests it catches fewer real declines than the eyeball
  rule. From five on, it catches more.
- **SGLT2 inhibitors.** In stable patients who start one, false decline alerts drop from 1.1% to
  0.2% when the treatment is entered as data.

### 3.5 Other home measurements and each patient's kit (`home.py`, `kit.py`)

Since urine does not replace blood, the patient needs other measurements to complete the
assessment without traveling:

- **Blood pressure with a validated cuff.** The usual one-week protocol: the first day is
  discarded and the rest averaged. It gives the probability that the true mean exceeds 135/85
  and feeds SCORE2 (adding 5 mmHg to match office readings).
- **Finger prick** (drop of blood on paper, by mail) for creatinine and HbA1c. This is not the
  glucometer: both prick the finger, but the glucometer gives glucose on the spot while this drop
  travels to the lab. It has more error than venous blood, so **it does not replace the estimate:
  it updates it** with Bayes' rule. A capillary eGFR of 51 leaves the estimate at 59 (between 51
  and 68) and recommends confirming it in the lab.
- **Heart rhythm** with the watch, if the patient connects it to the app, or with the phone camera
  (finger over the lens). Two irregular checks in a 77-year-old leave the probability of atrial
  fibrillation at 73%, and an ECG is ordered.
- **Heart recording** of 30 seconds with a single-lead ECG (the watch's or a pocket ECG device),
  with or without sound. A suspicious recording raises the probability of low ejection fraction
  from 0.9% to 8% in a 70-year-old, and NT-proBNP and an echocardiogram are ordered (section 3.11).

The measurement errors are assumptions. The baseline prevalence of atrial fibrillation is Spanish
and measured (section 3.11). The evidence for finger-prick eGFR still comes from small studies.

**The kit is not the same for everyone** (`kit.kit_for`): it contains what the patient's record
says is missing. Nobody buys anything: strips are mailed, devices are loaned and glucose is
measured at the pharmacy.

| Piece | For whom | How |
|---|---|---|
| Urine | Anyone without measured albuminuria or with a borderline result | Strips read with the phone, or tube by mail |
| Five questions | Everyone | App, phone or paper |
| Glucose | No diagnosed diabetes and a probability of undiagnosed diabetes of 2% or more | One measurement at the nearest pharmacy, or with their own glucometer |
| Blood pressure | High or unrecorded office blood pressure, with or without diagnosed hypertension | Cuff on loan for a week |
| Pulse | No diagnosed atrial fibrillation | The connected watch; otherwise the phone camera |
| 30-second ECG | Watch with ECG, or after a heart attack | The watch; after a heart attack, a loaned pocket ECG device |
| Drop of blood by mail | Nobody at first | Ordered if the worklist says creatinine is the most informative test |

- **Capillary glucose is for discovering diabetes**, so it is measured in people without a
  diagnosis. In someone already diagnosed it discovers nothing; their glucose control is a
  different use, not covered here. One measurement is enough (section 3.12), so it is done at
  the pharmacy.
- **The cuff goes to people with high office blood pressure**: in treated hypertension, to see if
  it is controlled; in people with no diagnosis, to see if it is hypertension.
- **One week** is the self-measurement protocol: two readings in the morning and two in the
  evening for seven days. A single reading is not enough, because blood pressure varies a lot
  from one moment to the next. Afterwards the cuff is returned.

A diabetic patient with hypertension and office blood pressure in range, the typical patient in
the challenge, only receives the strips.

What is lost when ranking risk (`reports/kit_en_casa.md`; 12,710 people, 701 cardiovascular
deaths over 10 years, same people as section 3.10):

| What is used | AUC | Difference from the full kit |
|---|---|---|
| Full kit: record, five questions, cuff and strip | 0.844 | |
| Kit for everyone: record, five questions and strip | 0.844 | +0.000 (-0.003 to 0.003) |
| Record and strip, without the questions | 0.841 | -0.004 (-0.008 to 0.000) |
| Record and five questions, without the strip | 0.838 | -0.006 (-0.010 to -0.002) |

- **Removing the cuff from the kit for everyone does not change the risk ranking.**
- **The questions stay**: they cost nothing, and without them 0.004 is lost, with an interval
  that touches zero.
- **The strip cannot be removed.**

**Watch or camera.** The app accepts both pulse sources. `kit.checks_from_pulse` takes the
beat-to-beat intervals, from the watch or the camera, and `kit.checks_from_ecg` the watch ECG;
they return the checks stored in the record. Three limitations:

- **The watch connection is not built** (Apple Health, Health Connect or the manufacturer's app).
  The input for its data is.
- **With the camera**, the atrial fibrillation detector has only been tested on beats degraded by
  simulation (section 3.12).
- **The watch ECG is a different lead**, wrist to finger. The ejection fraction model was trained
  with the device on the chest, so with a watch it is unvalidated.

### 3.6 Cardiovascular risk and the practice worklist (`cvrisk.py`, `worklist.py`)

**Cardiovascular risk.** SCORE2 (40-69 years) and SCORE2-OP (70 or older) for the low-risk region,
with the published coefficients, and the categories of the 2021 European guideline (low or
moderate, high, very high), in which kidney disease, diabetes and cardiovascular disease set a
floor. When data are missing their uncertainty is propagated: you get the probability of each
category and the probability that the true category is higher than the recorded one.

**An isolated albuminuria almost never changes the guideline category.** With normal eGFR,
30-300 mg/g does not move it, and most people over 55 are already high risk by SCORE2. Ranking
the list only by "moves up a category" left out exactly the patients in the challenge. That is why
the worklist ranks by a **new finding**: moving up a category, finding kidney disease that is not
recorded (eGFR < 60 or albuminuria) or undiagnosed diabetes.

**The worklist** has three groups: *act* (clear findings not recorded in the health record),
*measure* (ranked by probability of a new finding, with the most informative test and how to do
it at home) and *nothing pending*. Predictions for the whole practice list are computed in one
batch, so the worklist for 1,500 patients takes seconds.

**Validation with real people** (`reports/lista_cupo.md`; 660 people aged 40 or over from the
NHANES 2009-2010 test split; the system receives only the health record and is compared with what
NHANES actually measured):

| Scenario | Real new finding | Worklist AUC | AUC by age | AUC by SCORE2 | Hits in the top 20% |
|---|---|---|---|---|---|
| A. Lipids and blood pressure known; urine and creatinine missing | 15.9% | 0.75 | 0.73 | 0.75 | 37% (36-37% by age or SCORE2) |
| B. No lab tests at all | 20.8% | 0.73 | 0.62 | 0.69 | 42% (37-39%) |

- **When lipids are already available, the worklist does not rank better than age or SCORE2.**
  This is consistent with the panel: almost all the signal is in age.
- **Without lab tests it does rank better** (AUC 0.73 vs. 0.62 by age).
- **Its probabilities are calibrated**, and that is what age does not provide: of the 144 people
  it gives less than 5%, 3.5% have a finding; of the 44 it gives between 40% and 60%, 52%. This
  is useful for deciding how many kits to send and whom not to send one to.
- The worklist's value also lies in the first group, which is not a prediction: these are findings
  already measured that nobody has turned into a diagnosis.

### 3.7 Per-patient assessment (`src/latenthealth/assessment.py`)

Brings all the pieces together. A recent lab value replaces the estimate; a capillary home
measurement updates it. It returns:

- **Findings that call for action:** persistent albuminuria or sustained eGFR < 60 with no CKD
  recorded, eGFR decline, high blood pressure at home, high HbA1c or NT-proBNP without a
  diagnosis, irregular pulse.
- **Albuminuria:** status, true UACR with its interval and trajectory.
- **Lab tests:** each variable, measured, capillary or estimated, with its interval.
- **eGFR trend**, if there are previous lab tests.
- **CKD:** probability of each eGFR category and each KDIGO risk level, crossing eGFR and
  albuminuria without treating them as independent (section 3.9).
- **Diabetes and heart failure:** P(HbA1c ≥ 6.5%) and P(NT-proBNP ≥ 125) if there is no
  diagnosis.
- **Cardiovascular risk:** SCORE2, recorded category, likely true category and probability of a
  new finding with each pending test.
- **Risk from home measurements:** how many times the cardiovascular death risk of someone of the
  same age and sex (section 3.10), and which home data are missing.
- **Recommended tests**, with thresholds derived from an explicit utility (section 3.9).

### 3.8 Recalibration to Spain (`recalibration.py`, `reports/recalibracion_espana.md`)

The models were fitted on US data. The urine measurement model should hold here as well; what
changes is how much disease there is before measuring. This is corrected by shifting only
intercepts, using ONDAAS prevalences and NHANES reweighted to its age and sex distribution:

| | ONDAAS | NHANES model | Recalibrated |
|---|---|---|---|
| Urine sample ≥ 30 mg/g | 14.0% | 15.1% | 14.0% |
| eGFR < 60 (2009 equation) | 12.8% | 18.3% | 12.8% |

- **The NHANES albuminuria prior was already close** (15.1% vs. 14.0%): the correction is small.
  It depends on an assumption: the paper does not say whether the urine was first-morning. If it
  were, the model would give 9.6% and the correction would be large and in the opposite
  direction.
- **Low eGFR is indeed less common** than in the US at the same age and sex, and it is corrected.
  ONDAAS used the 2009 CKD-EPI equation and we use the 2021 one; the target is converted from one
  to the other person by person.
- The assessment uses the recalibrated priors by default (`population="espana"`). The validations
  with NHANES use the models without recalibration.
- It is a population correction, not a validation: ONDAAS patients are those who had lab tests
  ordered, not the whole practice list, and there are no individual-level Spanish data.

### 3.9 Robustness (`reports/robustez.md`)

**eGFR and albuminuria together.** Previously their probabilities were multiplied as if they were
independent. Now, when eGFR is not measured, the albuminuria filter is solved for each eGFR
category and the results are combined. **In NHANES the difference does not show**: the log loss
for high KDIGO risk is 0.067 assuming independence and 0.070 with the new method, and among the
979 test participants there are only 27 at high risk and 6 with both eGFR < 60 and albuminuria.
The new method is kept because it is coherent and does no harm, but it is not a demonstrated
improvement.

**Calibration by sex and age.** Of 24 groups (four outcomes by sex and three age bands), 3 are off:

- **eGFR < 60 in people over 65:** the panel predicts the same for men and women (24%) and the
  reality is 20% in men and 27% in women. This needs fixing.
- **Filter in men aged 65 or over:** 8.3% observed vs. 12.1% predicted, with 109 people. May be
  noise; to be monitored.
- **NT-proBNP in men under 50:** 0.7% vs. 4.0%. Far from the 30% threshold, it does not change
  any recommendation.

**Thresholds based on clinical utility (`decision.py`).** A probability threshold is equivalent to
a number of acceptable tests per case found (5% = 20 tests). Thresholds are written this way and
checked with decision curves on the test split:

| Decision | Threshold | Ordered for | Cases found | Tests saved per 100 people vs. ordering for everyone |
|---|---|---|---|---|
| Creatinine by P(eGFR < 60) | 5% | 31% | 92% | 58 |
| HbA1c by P(≥ 6.5%) without diagnosis | 5% | 21% | 61% | 26 |
| NT-proBNP by P(≥ 125) | 30% | 29% | 77% | 26 |
| Urine by P(albuminuria) from the record | 5% | 41% | 62% | 19 |

The last row confirms what the panel showed: the health record is no use for deciding whom to
order the urine test for (38% of albuminuria cases are left out). The urine test has to be
offered to the whole risk group; the worklist only decides the order.

### 3.10 Risk with real outcomes (`src/latenthealth/outcomes/`, `reports/riesgo_en_casa.md`)

Up to this point the project had no outcomes at all: only single-day lab tests. To know whether
what is used today can be improved, you need data on who later fell ill or died.

**Data.** NHANES 1999-2014 linked to the US death registry (through December 2019). Outcome:
**death from heart disease or stroke within the next 10 years**. Evaluated in 12,710 people aged
40 or over with ten years of complete follow-up (701 cardiovascular deaths), with
cross-validation: each person is predicted by a model that did not see them.

**Model.** Discrete-time survival: each person is one row per year of follow-up, and two gradient
boosting classifiers estimate, each year, the probability of dying from cardiovascular causes and
from any other cause (competing risks). The 10-year risk is accumulated year by year. It makes
use of people with shorter follow-up and accepts data not provided.

**Comparators.** The published SCORE2 and SCORE2-OP, which is what Spain uses, and the variables
of SCORE2 and PREVENT (the 2023 US model) refitted on these same data. The published PREVENT
equation could not be included: we could not obtain its coefficients.

AUC (probability of assigning higher risk to someone who dies than to someone who does not):

| What is used | Everyone | No prior cardiovascular disease | With diabetes or hypertension |
|---|---|---|---|
| Published SCORE2 (needs lab tests and a clinic visit) | 0.813 | 0.826 | 0.755 |
| Age and sex | 0.801 | 0.806 | 0.756 |
| Health record: diagnoses, medications, smoking, weight and waist | 0.837 | 0.832 | 0.795 |
| + five questions to the patient | 0.838 | 0.833 | 0.798 |
| + cuff (blood pressure and pulse) | 0.840 | 0.836 | 0.799 |
| + urine strip | 0.844 | 0.840 | 0.805 |
| + lab urine test, instead of the strip | 0.844 | 0.840 | 0.808 |
| + blood tests | 0.845 | 0.841 | 0.809 |

Differences in the same people, with their 95% interval:

| Comparison | Everyone | No prior disease | With diabetes or hypertension |
|---|---|---|---|
| Record, questions, cuff and urine vs. SCORE2 | +0.031 (0.022 to 0.042) | +0.014 (0.002 to 0.025) | +0.054 (0.039 to 0.070) |
| Health record alone vs. SCORE2 | +0.023 (0.014 to 0.034) | +0.007 (-0.005 to 0.018) | +0.041 (0.024 to 0.059) |
| What the five questions add | +0.002 (-0.002 to 0.006) | +0.001 (-0.004 to 0.006) | +0.004 (-0.003 to 0.009) |
| What the cuff adds | +0.002 (-0.001 to 0.005) | +0.003 (-0.002 to 0.007) | +0.000 (-0.005 to 0.006) |
| What the urine strip adds | +0.004 (0.001 to 0.007) | +0.004 (-0.000 to 0.009) | +0.006 (0.002 to 0.011) |
| What blood tests add | +0.001 (-0.002 to 0.003) | +0.001 (-0.002 to 0.004) | +0.001 (-0.003 to 0.005) |

What the data say, no embellishment:

- **SCORE2 is beaten at ranking who dies of heart disease or stroke.** The advantage is clear
  overall (+0.031) and in people with diabetes or hypertension (+0.054), who are the patients in
  the challenge and in whom SCORE2 does no better than age and sex. In people without prior
  disease, the population SCORE2 is designed for, the advantage is small (+0.014).
- **The improvement does not come from measuring more: it comes from using what is already in the
  record** (prior heart disease, medications), which SCORE2 ignores. It costs the patient nothing.
- **Of what is done at home, only urine adds measurable signal.** One strip is enough. Urine
  albumin is the strongest predictor after age.
- **The five questions and the cuff do not measurably change the risk ranking**, and **neither do
  blood tests**. Ranking risk does not require drawing blood. Diagnosing and treating do.
- **It is not the method.** With the same variables as SCORE2 the new model reaches 0.817; with
  those of PREVENT, including urine and HbA1c, 0.834. The home model reaches 0.844 without blood.
- **It is calibrated**: it predicts 5.5% deaths and 5.5% are observed; in the highest-risk tenth
  it predicts 26.5% and 25.9% are observed. The top 20% by risk captures 70% of deaths; with
  SCORE2, 62%.

**At the same age and sex.** Almost all of the 0.8 AUC is age, which the doctor already knows.
Between two people of the same age and sex, SCORE2 correctly picks who should get the higher
risk 58.7% of the time (chance is 50%); the health record, 64.7%; and the home model, 66.9%. What
is known above chance almost doubles, and in people with diabetes or hypertension it goes from
56.1% to 66.7%.

**There is a ceiling.** Adding all blood tests reaches 67.4%. With the data NHANES has, it is not
possible to rank better who will die within ten years; going further would require other signals
(imaging, electrocardiogram, biomarkers). That is why the next effort went into diagnosing what is
present now (section 3.12) rather than fine-tuning this model further.

**Check in Spanish people** (`reports/validacion_espana.md`). The only downloadable Spanish
cohort with events is a sample from the PREDIMED trial: 6,324 high-risk people from primary care,
with 252 heart attacks, strokes or cardiovascular deaths. It has few variables (no blood pressure,
urine or medications). A model trained only on NHANES with those variables gives a concordance
index of 0.662, vs. 0.631 with age and sex (+0.030, interval 0.011 to 0.051), and does not lose
against one trained within PREDIMED (0.649). The indices are low because all participants are
high risk and similar to each other. What it shows is that what was learned from deaths in the US
carries over to Spanish people and to non-fatal events.

**A trap that had to be removed.** The first version showed a larger advantage (+0.043). It was
partly spurious: in NHANES a missing value usually belongs to someone who could not be examined,
who is frailer, and the model had learned that "no data" means "higher risk". In the product,
missing means "not provided yet". Now training and evaluation use only people with complete
data, and the final model is trained by randomly deleting blocks (questions, weight, cuff, urine)
so that it estimates well with whatever is available. On the held-out set it gives an AUC between
0.825 and 0.829 whatever is missing, vs. 0.804 for SCORE2.

**In the product** (`outcomes/risk.py`). The patient record and the practice worklist show how many
times the risk of someone of the same age and sex the patient has. Relative rather than absolute
risk is shown because the model was trained on a US population.

Limitations: deaths only (the public file has no non-fatal heart attacks or strokes, which is what
SCORE2 aims to predict); US population; questionnaire administered by an interviewer; and in the
public mortality files some times and causes are replaced with synthetic values.

### 3.11 Heart failure and atrial fibrillation

Reports: `reports/fraccion_eyeccion.md`, `reports/pulso_insuficiencia_cardiaca.md`,
`reports/insuficiencia_cardiaca_espana.md` and `reports/insuficiencia_cardiaca.md`.

This was the weakest part because there were no open data with echocardiograms. We found three
datasets that can be downloaded without an account or application, and each answers a different
question.

**a) Can a weakly pumping heart be seen from home?** (`src/latenthealth/ejection.py`). Data:
Zenodo 16934966 (CC-BY 4.0): 620 people from two hospitals in Wuhan with ejection fraction
measured by echocardiogram and four 30-second recordings with a handheld device that captures a
single-lead ECG and the heart sound. It is the only dataset in the project with echocardiography
as ground truth and with disease-free people from the same clinic. Three device levels are
compared for detecting an ejection fraction of 40% or less:

| What is used | AUC (500 people, cross-validation) | With a single recording | Sensitivity at 90% specificity | AUC at the second hospital (120 people, 5 cases) |
|---|---|---|---|---|
| Pulse: beat-to-beat intervals | 0.682 (0.60-0.76) | 0.660 | 35% | 0.715 |
| Single-lead ECG | 0.883 (0.83-0.93) | 0.826 | 68% | 0.981 |
| ECG and heart sound | 0.911 (0.87-0.94) | 0.867 | 70% | 0.977 |

- **The jump is in the single-lead ECG**, the one a watch or a pocket ECG device provides: +0.20
  AUC over pulse (interval 0.14 to 0.27). Pulse alone is not enough.
- **Sound adds little**: +0.027, with an interval that includes zero (-0.008 to 0.063).
- **The features are explainable** and point in the direction physiology describes: slower QRS
  upstroke, a weaker and later first heart sound, shorter systole and a faster pulse. Adding the
  full averaged beat and sound raises the AUC by two hundredths.
- **It mainly detects severe cases**: it flags 88% of those with ejection fraction below 30% and
  48% of those between 30% and 40%.
- **At the second hospital** the model, untouched, detects all 5 cases with specificity of 88% to
  93%. Only 5 cases: it confirms the direction, not the figure.

In the record it enters as an already-scored recording (`HeartCheck`): it multiplies the baseline
odds (1.8% of people over 45 have an ejection fraction below 40%, half of them unaware, according
to the ECHOES study; 22% after a heart attack) and, if the probability exceeds 5%, NT-proBNP and
an echocardiogram are recommended and the patient moves up the practice worklist. Several
recordings are averaged rather than accumulated: it is the same heart every day.

**b) And with pulse alone?** (`src/latenthealth/pulse.py`). Data: two PhysioNet databases with
24-hour beat data from 29 people with heart failure and 54 healthy people. A two-minute
measurement separates them with AUC 0.83 and the average of seven with 0.89; with beats degraded
like a camera's, the same. It looks very good, and **it is not**: applying the equivalent rule to
the Holter summary of the 587 Spanish MUSIC patients in sinus rhythm flags only **22%** (19% of
those on beta-blockers, 30% of those not). The patients in those databases are from the 1990s,
without current treatment, and the controls are healthy. With echocardiography as ground truth
(part a) pulse alone gives 0.68. That is why pulse never decides: its likelihood ratio is capped
at what was seen in the Spanish patients (between 0.86 and 2.2).

**c) In people who already have the disease, how much of the severity can be seen from home?**
(`src/latenthealth/music.py`). Data: MUSIC clinical table (PhysioNet, ODbL): 992 patients with
heart failure from eight Spanish hospitals, with four-year mortality.

| Who dies within three years (221 of 962) | AUC |
|---|---|
| Age and sex | 0.629 |
| Health record (diagnoses and medication) | 0.733 |
| + home measurements: how easily they tire, weight, blood pressure and pulse | 0.757 |
| + ECG | 0.754 |
| + lab tests with NT-proBNP | 0.764 |
| Everything from the hospital, with echocardiogram and Holter | 0.778 |

- **The four home measurements add +0.024** to the health record (interval 0.001 to 0.047).
  Everything the hospital measures adds another +0.021, with an interval that includes zero
  (-0.005 to 0.046).
- Ranking with the health record and home measurements, the highest-risk third contains 64% of
  deaths (44% die, vs. 9% in the lowest-risk third).
- The same measurements predict who has NT-proBNP above 1,000 ng/l with AUC 0.745 (0.700 with the
  health record alone).
- Only 8% of these patients had NT-proBNP below 125 ng/l.

**d) NT-proBNP estimated from the record and symptoms** (what we already had). NT-proBNP cannot be
measured at home. Using the 10,174 adults in NHANES 1999-2004 who have it measured, we checked
how much what the patient reports helps:

| Who will have high NT-proBNP, in people aged 60 or over | Above 125 pg/ml | Above 300 pg/ml |
|---|---|---|
| Health record (as before) | 0.754 | 0.764 |
| + symptoms and pulse (shortness of breath, difficulty walking, self-rated health) | 0.769 | 0.782 |
| + urine | 0.770 | 0.795 |

- **Symptoms and pulse help somewhat**: +0.014 AUC for 125 pg/ml (interval 0.009 to 0.020) and
  +0.019 for 300. That is why the assessment uses them when available, and asks for them in
  people over 60 with suspected HF.
- **Measuring NT-proBNP still adds value.** For predicting death from heart disease, the home data
  give 0.824, the same as age, sex and measured NT-proBNP (0.822); both together, 0.838 (+0.014,
  interval 0.004 to 0.025).

**What is still missing.** The echocardiogram data are from hospitals and from China, with 65
cases; half of heart failure has preserved ejection fraction and is not detected here; and the
recordings were made by healthcare staff, not by the patient.

**Atrial fibrillation.** The baseline probability is no longer an assumption: it comes from the
OFRECE study (8,343 Spanish people aged 40 or over with ECG), by age and sex, and from the fact
that 10% of cases were undiagnosed. The detector that updates it is in section 3.12.

### 3.12 Diagnosis at home: diabetes with a glucometer and rhythm from pulse

Predicting who will die within ten years has a ceiling (section 3.10). Where there is a lot of
room for improvement is in **diagnosing what the patient has today**, and that is gained by
measuring at home.

**Undiagnosed diabetes** (`diabetes.py`, `reports/diabetes_en_casa.md`). Today, to decide whom to
test without a needle, Spain uses the FINDRISC questionnaire. A glucometer is cheap. They are
compared in 27,300 adults from NHANES 2005-2018 without diagnosed diabetes, of whom 865 (3.2%)
have a diabetic-range HbA1c. Glucose is the lab value with the error of a home glucometer
(7.5%).

| What is used (AUC) | Everyone | Fasting | Not fasting |
|---|---|---|---|
| FINDRISC, the questionnaire used today | 0.754 | 0.759 | 0.749 |
| Health record | 0.785 | 0.783 | 0.787 |
| Record and urine | 0.811 | 0.813 | 0.809 |
| Glucometer alone | 0.896 | 0.932 | 0.849 |
| Record, urine and glucometer | 0.920 | 0.944 | 0.893 |

| With the same effort as FINDRISC ≥ 15 (22% flagged) | Undiagnosed diabetes found | PPV |
|---|---|---|
| FINDRISC ≥ 15 | 52% | 7.6% |
| Record and urine | 64% | 9.4% |
| Record, urine and glucometer | 86% | 12.6% |
| Record, urine and fasting glucometer | 92% | 12.8% |

- **With a glucometer, 86% of undiagnosed diabetes is found where FINDRISC finds 52%**, testing
  the same number of people. The AUC difference is +0.166 (interval 0.151 to 0.180).
- **To find 80%**, 44% of people need testing with FINDRISC and 16% with the glucometer.
- **It works even when not fasting** (0.893), because the model knows how many hours since the
  last meal.
- **Rule without a model:** fasting glucose of 110 mg/dl or more flags 13% and finds 84%.
- **It is calibrated:** of those given a probability between 30% and 60%, 47% have it.
- In the record, the home glucose updates the estimated HbA1c and the probability of diabetes.
  Two fasting days with 126 mg/dl or more come up as a finding. The patient can repeat it.

**In the product, glucose is not measured in everyone: there are two steps.** It is measured in
people whom the health record leaves with a probability of undiagnosed diabetes of 2% or more,
and the lab test is ordered for those who, with their glucose, are still at 2% or more (50 tests
per case across both steps). Percentages are of all people without a diagnosis:

| Criterion | Glucose measured | Lab test ordered | Undiagnosed diabetes found | PPV of the lab test |
|---|---|---|---|---|
| FINDRISC ≥ 15 and direct lab test | - | 22% | 52% | 7.6% |
| Glucose for everyone | 100% | 22% | 87% | 12.3% |
| Glucose if the record gives 2% or more (the product) | 46% | 20% | 75% | 12.2% |
| Glucose if the record gives 5% or more | 19% | 11% | 52% | 14.4% |

- **With the same number of lab tests as FINDRISC (20% vs. 22%), the product finds 75% of
  undiagnosed diabetes vs. 52%**, measuring glucose in fewer than half the people.
- **The lab-test threshold decides how much is found.** At 5%, it is ordered for 10% and 63% are
  found; at 1%, for 30% and 82%.
- **One measurement is enough, so it is done at the nearest pharmacy**, fasting and without an
  appointment, or with the patient's own glucometer if they have one. There is no device to loan.
  For 58% of those who get it, the system replies that they are done; the rest are asked for the
  lab test.
- **Repeating to average out device error adds almost nothing**: an error-free glucometer, the
  ceiling, raises the AUC from 0.920 to 0.931. Whether repeating it on different days adds more
  cannot be measured with these data, which have one glucose value per person.
- **At the pharmacy it is no longer a test done at home**, and fasting means going in the morning.
  Non-fasting also works, with somewhat less accuracy (AUC 0.893 vs. 0.944).

This is not a new medical finding: fasting glucose is a diagnostic criterion. What is measured is
how much is gained over what is used today to screen without lab tests. Limitations: lab glucose
with simulated error, a single measurement per person and a US population.

**Atrial fibrillation** (`rhythm.py`, `reports/ritmo.md`). Our own detector that does not look at
the waveform: it detects each beat and measures how irregular the intervals between them are, so
it works with a pocket ECG device, a watch or the phone camera. Trained and validated on the
8,528 real recordings from the PhysioNet/CinC Challenge 2017 (758 with atrial fibrillation).

| Input | AUC vs. everything else | AUC vs. normal rhythm | Sensitivity | Specificity |
|---|---|---|---|---|
| Beats from the electrocardiogram | 0.971 | 0.988 | 87.5% | 93.8% |
| Beats degraded like a camera's (simulated) | 0.957 | 0.979 | 83.1% | 93.5% |
| Simple rule: interval variability | 0.751 | 0.823 | 5.4% | 95.0% |

- **False alarms are almost all other arrhythmias**: it flags 1.8% of normal rhythms and 13% of
  "other rhythms", which a doctor should also see.
- **The record uses the detector's likelihood ratio**, not a yes or no, and applies it to the
  Spanish prevalence by age and sex: a detector probability above 70% multiplies the odds by 75;
  below 2%, it divides them by more than 20.
- **The camera rows are simulated** (20 ms of jitter and 3% of beats missed). There are no openly
  available labeled camera recordings.
- It does not aim to beat the best methods in the challenge, which use the waveform and deep
  networks, or apps that are already validated. It provides our own component with its error
  measured.

## 4. How to run it

```bash
uv sync
```

```bash
uv run python scripts/demo_casa.py
```

```bash
uv run python scripts/demo.py
```

```bash
uv run pytest
```

The trained models are in `models/`. To rebuild everything from the public data (about 360 MB of
NHANES and its linked mortality), in this order:

| Step | Command | Output |
|---|---|---|
| 1 | `uv run python scripts/download_nhanes.py` | Data in `data/raw/nhanes/` |
| 2 | `uv run python scripts/fit_albuminuria.py` | `models/albuminuria_params.json` |
| 3 | `uv run python scripts/validate_albuminuria.py` | `reports/validacion_albuminuria.md` |
| 4 | `uv run python scripts/fit_panel.py` | `models/panel/` and `reports/panel_sangre.md` |
| 5 | `uv run python scripts/fit_recalibration.py` | Priors for Spain and `reports/recalibracion_espana.md` |
| 6 | `uv run python scripts/validate_robustness.py` | `reports/robustez.md` |
| 7 | `uv run python scripts/validate_worklist.py` | `reports/lista_cupo.md` |
| 8 | `uv run python scripts/simulate_home.py` | `reports/cribado_en_casa.md` (about 15 minutes) |
| 9 | `uv run python scripts/validate_trend.py` | `reports/tendencia_fg.md` |
| 10 | `uv run python scripts/fit_outcomes.py` | `models/outcomes/` and `reports/riesgo_en_casa.md` (about 15 minutes) |
| 11 | `uv run python scripts/fit_heart_home.py` | `models/panel/log_nt_probnp__casa*.joblib` and `reports/insuficiencia_cardiaca.md` |
| 12 | `uv run python scripts/fit_diabetes_home.py` | `models/panel/hba1c__casa.joblib` and `reports/diabetes_en_casa.md` |
| 13 | `uv run python scripts/download_open_data.py` | PhysioNet electrocardiograms, PREDIMED sample, Zenodo recordings with echocardiogram, MUSIC table and 24 h beat data, in `data/raw/` (about 480 MB) |
| 14 | `uv run python scripts/fit_rhythm.py` | `models/ritmo/fa_intervalos.joblib` and `reports/ritmo.md` |
| 15 | `uv run python scripts/validate_predimed.py` | `reports/validacion_espana.md` |
| 16 | `uv run python scripts/fit_ejection.py` | `models/ritmo/fe_baja.joblib` and `reports/fraccion_eyeccion.md` |
| 17 | `uv run python scripts/fit_pulse_hf.py` | `models/ritmo/ic_pulso.joblib` and `reports/pulso_insuficiencia_cardiaca.md` (about 5 minutes) |
| 18 | `uv run python scripts/validate_music.py` | `reports/insuficiencia_cardiaca_espana.md` |
| 19 | `uv run python scripts/fit_kit.py` | `reports/kit_en_casa.md` (about 5 minutes) |

`fit_albuminuria.py --variant <name>` fits the variants in the validation table
(`picos_normales`, `sin_covariables_muestra`, `sin_pendiente`, `sin_picos`, `normal`).

## 5. What is fitted to data and what is an assumption

| Piece | Status |
|---|---|
| Filter: prior, sample type, noise, elevations, dilution | Fitted and validated on real people (NHANES 2009-2010) |
| Filter: change in albuminuria over months or years | Assumption from the literature |
| Virtual blood panel | Fitted and validated on real people (NHANES) |
| SCORE2 and SCORE2-OP | Published coefficients, checked against an open implementation |
| 2021 European guideline categories | Implemented following the guideline; the original table could not be cross-checked in this session. Should be reviewed by a clinician |
| Practice worklist | Validated on real people: calibrated probabilities; the ranking does not beat age when lipids are available |
| eGFR and albuminuria together | Checked on real people: no measurable difference |
| Thresholds | Explicit as tests per case; decision curves on real people |
| Recalibration to Spain | Published ONDAAS prevalences; no individual-level data |
| Strip: reading error | **Assumption.** Needs to be measured with paired samples |
| Context questions: effect | **Assumption.** Can be estimated from usage data |
| Home protocol | Evaluated in simulation only |
| Participation by channel | Measured in THOMAS for app and mail; assumed for the rest |
| eGFR trend | **Assumption** from the literature; checked in simulation only |
| Cardiovascular death risk from home data | Trained and validated on real outcomes (US); absolute risk not recalibrated to Spain |
| NT-proBNP with symptoms and pulse | Fitted and validated on real people (NHANES 1999-2004) |
| Low ejection fraction from ECG and sound | Trained and validated on 500 people with echocardiogram (Wuhan hospital) and tested on 120 from another hospital; 65 cases in total. Recorded by healthcare staff |
| Low ejection fraction: baseline probability | Measured in England (ECHOES study); that half are undiagnosed is an **assumption** |
| Heart failure from pulse alone | Trained on 83 people (1990s databases); in treated Spanish patients it flags only 22%. Does not decide |
| Heart failure severity from home measurements | Validated on 992 Spanish patients (MUSIC, 2003-2004); measurements taken by healthcare staff |
| Atrial fibrillation: baseline probability | Measured in Spain (OFRECE study) |
| Atrial fibrillation detector | Trained and validated on 8,528 real pocket ECG recordings; with camera, **simulated only** |
| Undiagnosed diabetes with a glucometer | Validated on real people (NHANES); glucose is the lab value with **simulated** glucometer error |
| Cardiovascular risk in Spanish people | Checked on the PREDIMED sample (few variables, all high risk) |
| Continuous reading of the strip color | **Assumption**; evaluated in simulation only. No vision model built |
| Finger prick and rhythm: measurement errors | **Assumption** |
| Kit per patient | Measured on real outcomes (US): without the cuff the risk ranking does not change. The watch connection is not built, only the input for its data; the watch ECG is unvalidated |

Other limitations:

- **US data (NHANES), unweighted.** Not a Spanish primary care population.
- **The simulations are within the model**: they say what happens if the world behaves like the
  model, not whether the model is correct.
- **No multi-parameter strip.** NHANES has no urine glucose, protein, blood or specific gravity.
- **Missing: the effect of treatments on albuminuria** (ACE inhibitors/ARBs and SGLT2 inhibitors
  lower it by 30-40%) and acute kidney injury in the eGFR trend.
- **NT-proBNP from 1999-2004 sera** and with the health record of that time.
- **In diabetes** the current guideline uses SCORE2-Diabetes, which is not implemented.
- **It is decision support, not diagnosis.** Before being used on patients it needs prospective
  validation and certification as a medical device; a test performed by the patient adds
  regulatory requirements.

## 6. Next steps

1. **Calibrate the strip** with about 200-300 samples read both with the strip and in the lab.
   It is cheap and it is the assumption that weighs most in the home loop.
2. **Longitudinal primary care data** (SIDIAP, BIGPAC) to fit the eGFR trend, the change in
   albuminuria over time and the effect of treatments.
3. **Fix the eGFR calibration by sex in people over 65.**
4. **Estimate the effect of the context questions** from usage data.
5. **SCORE2-Diabetes and the CKD add-on** for cardiovascular risk, and **recalibrate to Spain the
   absolute risk** of the home model using INE mortality rates.
6. **A primary care cohort with non-fatal heart attacks and strokes and with echocardiograms.**
   None can be downloaded: SIDIAP and similar require an institutional application with a
   protocol and ethics committee approval, and SHARE (which includes Spain) requires registering
   as a researcher. This is what is needed to compare against SCORE2 on what SCORE2 predicts. For
   heart failure there are already data with echocardiograms (section 3.11), but from hospitals;
   the next one is EchoNext (100,000 ECGs with echocardiograms, on PhysioNet), which only
   requires signing a data use agreement with an account.
7. **Real home readings**: glucometers, camera pulse and heart recordings made by the patient
   themselves (with a watch or a pocket ECG device), to replace simulated errors with measured
   ones.
8. **Integration with the health record (FHIR)** and interface: the patient app, with the watch
   connection and camera pulse measurement, and the doctor's worklist with one-click test
   ordering.
9. **Moving to treatment.** The fourth break in the chain, therapeutic inertia, is still not
   addressed: flagging who meets guideline criteria for each drug.
