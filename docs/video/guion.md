# LatentHealth video: script

**One sentence (the video's job):** viewers should understand why kidney, heart and diabetes
patients slip through today before it is too late, and believe that measuring at home with a system
that knows how far to trust each measurement fixes it.

**Audience:** hackathon jury (doctors, Boehringer people, engineers). They know health; no need to
explain what an artery is, but we do need to explain what we built.

**Protagonist:** Julián, 62, with hypertension (a made-up character, stated on screen). The heroes
are him and his doctor; LatentHealth is the guide.

**Length:** about 7 and a half minutes (≈1,080 words at 145 per minute). If the hackathon asks for
less, there is a 3-minute version at the end.

**Arc:** hook (Julián knows nothing) → why it matters → what is measured → where it fails today → the idea
→ the app with Julián → the doctor → how it was built and what comes out → what it would save → back to Julián.

**Pace:** something changes on screen every 3-5 seconds. Every 60-90 seconds, a "re-hook": a
question or a number that opens the next block.

Tags: **[VO]** voice-over · **[TXT]** on-screen text · **[GRAF]** animated graphic ·
**[APP]** app screen · **[SFX]** sound.

---

## 0. Hook (0:00-0:30)

| Audio | Visual |
|---|---|
| [VO] This is Julián. He's sixty-two and he feels fine. | [GRAF] Julián's silhouette drawing itself in a thin line. [TXT] "Julián, 62 · made-up character" (small, bottom). |
| [VO] He's had high blood pressure for years. He takes his pill. He sees his doctor once a year. | [GRAF] Three icons appear: pill, calendar, office visit. All green. |
| [VO] What nobody has ever checked is his urine. | [GRAF] The silhouette's kidney lights up. A drop falls. |
| [VO] And there's albumin in his urine: the first sign that the kidney, and with it the heart, is starting to get damaged. | [GRAF] The drop turns amber. A pulse line slowly flattening. |
| [VO] Ninety-six out of a hundred people with hypertension are never asked for that test. | [GRAF] Grid of 100 people; 96 stay gray, 4 light up. [TXT] "96 out of 100" · small source: Shin et al., *Hypertension* 2021. |
| [VO] This is about how to find Julián in time. Without him having to go anywhere. | [TXT] LatentHealth logo. [SFX] soft hit. |

## 1. Why it matters (0:30-1:20)

| Audio | Visual |
|---|---|
| [VO] Diabetes, hypertension, kidney and heart are not four problems. They're one. | [GRAF] Four circles moving closer and overlapping into a knot. |
| [VO] High blood pressure and sugar damage small vessels. The kidney leaks albumin. And that same damage reaches the heart. | [GRAF] Arrows run through the knot: vessel → kidney → heart. |
| [VO] In Spain, heart and vascular disease kill more than a hundred and thirteen thousand people a year. It's the leading cause of death. | [GRAF] Big number counting up to 113,620. [TXT] "deaths per year · INE 2024". |
| [VO] One in seven adults has chronic kidney disease. | [GRAF] 7 people, one fills in. [TXT] "15% · ENRICA study". |
| [VO] One in two people with diabetes doesn't know it. And one in three with hypertension doesn't either. | [GRAF] Two split bars: diabetes 6 of 13.8% unaware; hypertension 37% undiagnosed. [TXT] "di@bet.es". |
| [VO] The problem isn't that we lack treatments. We have them, and they work. The problem is they arrive late. | [GRAF] A timeline: "damage starts" ... "diagnosis" with a huge gap in between marked in amber. |

## 2. What is measured (1:20-2:15)

| Audio | Visual |
|---|---|
| [VO] To see this damage in time, you only need a few measurements. | [GRAF] Julián's silhouette, with six dots lighting up one by one. |
| [VO] In urine, albumin: the albumin-to-creatinine ratio. It's the earliest sign. | [GRAF] Kidney dot → card "Urine · albumin/creatinine · earliest". |
| [VO] In blood, kidney filtration and glucose. | [GRAF] Cards "Blood · eGFR" and "Glucose". |
| [VO] Blood pressure, but measured properly: a week at home, not one reading at the office. | [GRAF] Card "Blood pressure · 7 days, morning and night". Mini calendar with 28 dots. |
| [VO] And the heart: whether it beats in rhythm, and whether it pumps strongly. Today, only an echocardiogram tells you the latter. | [GRAF] Cards "Rhythm · ECG" and "Pumping · echocardiogram (hospital)". |
| [VO] Almost all of this can be measured without leaving home. But that's not how it's done today. | [GRAF] The cards split into two groups: "at home" (5) and "hospital" (1). |

## 3. Where it fails today (2:15-3:05)

| Audio | Visual |
|---|---|
| [VO] Today the pathway depends on someone remembering to order the test. And it breaks in four places. | [GRAF] A chain of four links. |
| [VO] One: it isn't ordered. Over two years, urine is checked in one in three people with diabetes and four in a hundred with hypertension. | [GRAF] Link 1 breaks. Two bars: 35% and 4%. |
| [VO] Two: when it is ordered, a single sample misleads. Half of the positives don't repeat on the next one. | [GRAF] Link 2. Two lab tubes: one red, the next green. [TXT] "1 in 2". |
| [VO] Three: what shows up in the lab test doesn't become a diagnosis. More than eighty percent of people with a damaged kidney don't have it recorded in their chart. | [GRAF] Link 3. A blank clinical record. [TXT] "> 80% · REVEAL-CKD". |
| [VO] And four: even when it's diagnosed, only one to three in ten get the treatment that protects the kidney and the heart. | [GRAF] Link 4. [TXT] "10-33% on SGLT2 inhibitors". |
| [VO] For diabetes, screening uses a questionnaire. It finds half. | [GRAF] FINDRISC: a question sheet. [TXT] "52%". |
| [VO] And all of this lands on a doctor with fifteen hundred patients and ten minutes for each one. | [GRAF] A 10-minute clock on top of a stack of records. |

## 4. The idea (3:05-3:30)

| Audio | Visual |
|---|---|
| [VO] So we turned it around. | [SFX] cut. Clean background. |
| [VO] The patient measures at home, easily, as many times as needed. | [GRAF] House → phone → strip. |
| [VO] The doctor gets a list that's already ranked: who to look at first and what to order. | [GRAF] List with three groups. |
| [VO] And in between, a model that knows how far to trust each measurement. | [GRAF] Between the two, a probability curve that narrows with each measurement. [TXT] "LatentHealth". |

## 5. The app, with Julián (3:30-5:00)

| Audio | Visual |
|---|---|
| [VO] The system goes through the practice list and sees that Julián is missing a urine test, and that his office blood pressure was a hundred forty-six. | [APP] Phone: notification "Your health center is sending you a kit". |
| [VO] He gets a kit with only what he's missing: three strips. And they lend him a BP cuff for a week. Nobody buys anything. | [GRAF] Kit render: box with three strips and a BP cuff. Glucometer and watch in gray ("only if needed"). |
| [VO] Before the strip, four questions. Have you exercised hard? Do you have a fever? Does it burn when you pee? | [APP] Questions screen, taps on "No". |
| [VO] If any answer is yes, the result wouldn't be reliable, and the app tells him to wait. | [APP] Insert: Marta, "Not today. Wait 3 days after your period". |
| [VO] With the first urine of the morning, he dips the strip and takes a photo. | [APP] Camera framing the strip; guide frame; flash. |
| [VO] The app doesn't give him a bare number. It tells him what to do. "All done", "repeat tomorrow", or "send the lab tube". | [APP] Result: "Repeat tomorrow" with probability bar 14%. |
| [VO] Every measurement moves the probability. Only those with an uncertain result repeat. | [GRAF] Probability curve shifting with each strip: 14% → 75% with the lab tube. |
| [VO] Blood pressure, for a week, morning and night. Pulse, with his watch; or with the phone camera, finger on top. | [APP] Blood pressure calendar filling up. Pulse screen with finger on camera. |
| [VO] If the watch records an electrocardiogram, thirty seconds are enough to suspect the heart is pumping weakly. | [APP] "ECG 30 s" screen with a trace drawing itself. |
| [VO] And if the system suspects diabetes, a single fasting glucose, at the corner pharmacy. | [APP] Card "Stop by the pharmacy before breakfast". |
| [VO] At the end, Julián gets a message: we've seen albumin in your urine repeatedly. Your health center will call you. | [APP] Final screen with a check mark. |

## 6. The doctor (5:00-5:40)

| Audio | Visual |
|---|---|
| [VO] On the other side is his doctor. She doesn't get a hundred alerts. She gets a list. | [APP] Desktop screen: "My practice list · 1,500 patients". |
| [VO] At the top, what's already clear and not on record: Julián, repeated albuminuria with no diagnosis. | [APP] "Act" group with Julián highlighted. |
| [VO] Next, who's missing a test, ranked by the probability of finding something new, and which one to order first. | [APP] "Measure" group with probability bars and an "order" button. |
| [VO] And at the bottom, those who are well worked up. They take up one line. | [APP] "Nothing pending: 3 of 11". |
| [VO] In the patient record, every value with its uncertainty: measured, estimated, or measured at home. | [APP] Julián's record with intervals. |

## 7. How it was built and what comes out (5:40-6:50)

| Audio | Visual |
|---|---|
| [VO] None of this is a made-up rule. Every piece is trained and checked on real people. | [GRAF] Data logos: NHANES, PhysioNet, Zenodo, MUSIC, PREDIMED. |
| [VO] The heart of the system is a Bayesian filter: the same kind of model that tracks a plane with a noisy radar. It tracks Julián's true albumin with measurements that, on their own, mislead. | [GRAF] Noisy dots (strips) and a smooth line with a band that narrows. |
| [VO] For cardiovascular risk, Spain uses SCORE2. Our model, trained on who actually died within ten years, ranks risk better, especially in people with diabetes or hypertension. Without drawing blood. | [GRAF] AUC bars: SCORE2 0.755 · LatentHealth 0.808 (diabetes or hypertension). [TXT] "+0.054". |
| [VO] For hidden diabetes, against today's questionnaire: with the same number of lab tests, it finds three in four cases instead of one in two. | [GRAF] Two grids of 100 hidden diabetes cases: 52 found vs 75. |
| [VO] The arrhythmia detector reaches ninety-seven percent area under the curve on eighty-five hundred real recordings. | [GRAF] Gauge 0.97. |
| [VO] And with thirty seconds of single-lead electrocardiogram, we detect a weak heart with 0.88 against the echocardiogram. Today that requires a hospital visit. | [GRAF] Three bars: pulse 0.68 · ECG 0.88 · ECG and sound 0.91. |
| [VO] We also know what doesn't work, and we say so: pulse alone isn't enough for a weak heart. And these data come from the United States and China: before use, it has to be validated in Spain. | [TXT] "What we don't know yet" with three bullet points. |

## 8. What it would save (6:50-7:30)

| Audio | Visual |
|---|---|
| [VO] So how much does all this matter? | Dark background. |
| [VO] In Spain there are more than a million people with albuminuria that nobody has seen. | [GRAF] Dot map of Spain filling up. [TXT] "≈ 1.8 million · estimate". |
| [VO] If half of them measure at home and half of those start treatment, that's about twelve hundred fewer deaths every year. | [GRAF] Counter up to 1,200. [TXT] "deaths averted per year · central scenario (100-3,900)". |
| [VO] Twelve thousand in ten years. | [GRAF] Counter up to 12,000. |
| [VO] Julián won't notice. There won't be a day when we save his life. He'll simply still be here ten years from now. | [GRAF] Julián's silhouette, now with a grandchild beside him. All green. |
| [VO] LatentHealth. What your body already knows, in time. | [TXT] Logo. "Challenge 1 · Boehringer Hackathon". |

---

## Sources shown on screen

- UACR within two years in 4.1% of people with hypertension (96 in 100 without it) and in 35.1% of
  people with diabetes: Shin et al., *Hypertension* 2021 (3.7 million adults from 24 cohorts).
- 113,620 deaths from diseases of the circulatory system: INE, 2024.
- 15.1% CKD: ENRICA study (Gorostidi et al., *Nefrología* 2018).
- Diabetes 13.8%, 6.0% unaware: di@bet.es (Soriguer et al., *Diabetologia* 2012).
- 37% of people with hypertension undiagnosed: di@bet.es (Menéndez et al., *Rev Esp Cardiol* 2016).
- > 80% of CKD stage 3 undiagnosed: REVEAL-CKD. 10-33% on SGLT2 inhibitors: see `docs/solucion.md`.
- Our own results: `reports/riesgo_en_casa.md`, `reports/diabetes_en_casa.md`, `reports/ritmo.md`,
  `reports/fraccion_eyeccion.md`.
- Lives: `reports/vidas_salvadas.md` (estimate built on assumptions; SGLT2 inhibitors RR 0.86, *Lancet* 2022).

## 3-minute version

0 (hook, 25 s) → 1 condensed (death toll and "they arrive late", 20 s) → 3 (the four failures,
35 s) → 4 (the idea, 15 s) → 5 condensed (kit, strip, result, 40 s) → 6 (the list, 20 s) → 7 only
SCORE2 and diabetes (20 s) → 8 (25 s).
