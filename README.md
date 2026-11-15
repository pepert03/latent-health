# LatentHealth

Detección precoz del riesgo cardio-renal-metabólico en atención primaria (Reto 1 del hackathon de
Boehringer: *automatizar lo repetitivo*). El paciente se mide en casa, las veces que haga falta, y
el médico recibe una lista ya ordenada de a quién mirar y qué pedirle.

**En casa (el paciente)**

- **Tira de orina y protocolo de repetición.** El filtro lee las almohadillas de albúmina y
  creatinina de una tira y dice "ya está", "repite mañana" o "manda el tubo". Tira para todos y
  tubo al laboratorio solo para los dudosos.
- **Preguntas antes de la prueba.** Ejercicio intenso, fiebre, regla o síntomas de infección
  aplazan la prueba y explican las elevaciones pasajeras.
- **Canales sin móvil.** La misma lógica con la tira leída a ojo, en la farmacia, en enfermería o
  solo con el tubo por correo.
- **Glucosa capilar.** Una sola medida, en la farmacia o con glucómetro, encuentra el 75 % de la
  diabetes sin diagnosticar con los mismos análisis con los que el cuestionario FINDRISC
  encuentra el 52 %.
- **Ritmo cardíaco.** Detector propio de fibrilación auricular por la irregularidad del pulso,
  validado con 8.528 registros reales.
- **Otras medidas.** Tensión con manguito y punción capilar (creatinina y HbA1c).
- **Un kit distinto para cada paciente**, con lo que su ficha dice que falta. Las tiras se mandan
  y el manguito se presta una semana solo a quien lo necesita. El pulso se toma del reloj,
  si el paciente lo conecta, o con la cámara del móvil.
- **Preguntas sobre síntomas.** Falta de aire, dificultad para caminar y salud percibida: afinan
  la sospecha de insuficiencia cardíaca en mayores de 60 años.
- **El corazón en 30 segundos.** Un ECG de una derivación (reloj o electrocardiógrafo de bolsillo)
  detecta la fracción de eyección baja con AUC 0,88 frente al ecocardiograma; con el sonido del
  corazón, 0,91. El pulso solo no basta (0,68).

**En la consulta (el médico)**

- **Lista del cupo.** Primero los hallazgos claros que no constan en la historia; después, los
  pacientes ordenados por la probabilidad de que completar las pruebas dé un hallazgo nuevo, con
  la prueba que más aporta.
- **Riesgo cardiovascular.** SCORE2, SCORE2-OP y categorías de la guía europea, con la
  incertidumbre de lo que falta por medir.
- **Tendencia del filtrado glomerular.** Nivel y pendiente con las analíticas previas, con los
  tratamientos como entrada conocida.

**Los modelos**

- **Riesgo de muerte cardiovascular sin analítica de sangre.** Entrenado con desenlaces reales
  (NHANES enlazado con el registro de defunciones). Ordena el riesgo mejor que SCORE2 con la
  historia clínica y una tira de orina, sobre todo en diabéticos e hipertensos.

- **Filtro bayesiano de la albuminuria.** Estima el UACR verdadero con todas las muestras: tipo de
  muestra, dilución, elevaciones transitorias y censura. Validado en NHANES 2009-2010.
- **Panel virtual de sangre.** Estima con su incertidumbre el FG, la HbA1c, la glucosa, el potasio,
  el colesterol no-HDL, la hemoglobina y el NT-proBNP con la historia clínica y la orina.
- **Recalibración a España** con las prevalencias del estudio ONDAAS, y **comprobaciones de
  robustez** (FG y albuminuria juntos, calibración por sexo y edad, umbrales por utilidad).

Toda la explicación, con resultados y límites: [docs/solucion.md](docs/solucion.md). Ahí se dice
también **qué está ajustado con datos y qué es un supuesto** todavía.

Informes generados por los scripts:

| Informe | Qué comprueba | Con qué |
|---|---|---|
| [validacion_albuminuria.md](reports/validacion_albuminuria.md) | El filtro de albuminuria | Personas reales (NHANES) |
| [panel_sangre.md](reports/panel_sangre.md) | El panel virtual | Personas reales (NHANES) |
| [robustez.md](reports/robustez.md) | FG y albuminuria juntos, calibración por grupos, umbrales | Personas reales (NHANES) |
| [lista_cupo.md](reports/lista_cupo.md) | El orden de la lista del cupo | Personas reales (NHANES) |
| [riesgo_en_casa.md](reports/riesgo_en_casa.md) | El riesgo con lo medido en casa frente a SCORE2 | Personas reales con seguimiento (NHANES y mortalidad) |
| [kit_en_casa.md](reports/kit_en_casa.md) | Qué se pierde al quitar cada pieza del kit | Personas reales con seguimiento (NHANES y mortalidad) |
| [insuficiencia_cardiaca.md](reports/insuficiencia_cardiaca.md) | Qué se sabe de la insuficiencia cardíaca desde casa | Personas reales con seguimiento |
| [fraccion_eyeccion.md](reports/fraccion_eyeccion.md) | La fracción de eyección baja con pulso, ECG de una derivación y sonido | 620 personas con ecocardiograma (Zenodo) |
| [pulso_insuficiencia_cardiaca.md](reports/pulso_insuficiencia_cardiaca.md) | La insuficiencia cardíaca con el pulso solo, y por qué no basta | 83 personas (PhysioNet) y 587 pacientes españoles |
| [insuficiencia_cardiaca_espana.md](reports/insuficiencia_cardiaca_espana.md) | Cuánto de la gravedad se ve desde casa | 992 pacientes españoles con seguimiento (MUSIC) |
| [diabetes_en_casa.md](reports/diabetes_en_casa.md) | La diabetes oculta con glucómetro frente a FINDRISC | Personas reales (NHANES) |
| [ritmo.md](reports/ritmo.md) | El detector de fibrilación auricular | 8.528 registros reales de electrocardiógrafo de bolsillo |
| [validacion_espana.md](reports/validacion_espana.md) | El riesgo cardiovascular en españoles | Muestra del ensayo PREDIMED |
| [recalibracion_espana.md](reports/recalibracion_espana.md) | El ajuste a atención primaria española | Prevalencias publicadas (ONDAAS) |
| [cribado_en_casa.md](reports/cribado_en_casa.md) | El protocolo en casa | Simulación |
| [tendencia_fg.md](reports/tendencia_fg.md) | La tendencia del filtrado | Simulación |

## Uso rápido

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

`demo_casa.py` enseña el circuito completo (el paciente en casa y la lista del médico);
`demo.py`, la ficha de cinco pacientes. Para rehacer los modelos y los informes desde los datos
públicos de NHANES, sigue la sección 4 de [docs/solucion.md](docs/solucion.md).

## Sitio web de presentación (local)

```powershell
powershell -ExecutionPolicy Bypass -File web\start.ps1
```

Abre <http://127.0.0.1:8000>. Un solo proceso sirve la web (`web/site`: HTML, CSS y JavaScript,
sin compilar) y las rutas `/api` que llaman a los modelos de `src/latenthealth` en tiempo real
(documentadas en <http://127.0.0.1:8000/api/docs>). La página cuenta el porqué del proyecto, deja
probar el filtro de albuminuria en vivo y trae la app del paciente dentro de un teléfono:
recordatorio, tira, registro, asistente y mensaje al médico. Todo con datos sintéticos.

- El asistente de la app usa Claude si existe la variable `ANTHROPIC_API_KEY`; sin ella contesta en
  modo guiado con los mismos datos del modelo, y lo indica.
- Tests del servidor: `uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests -q`
- Prueba de humo de la app en el navegador: <http://127.0.0.1:8000/?auto=registro>

## Estructura

| Ruta | Contenido |
|---|---|
| `web/` | Sitio de presentación (`site/`) y servidor local que envuelve los modelos (`server/`) |
| `src/latenthealth/albuminuria/` | Modelo, ajuste y filtro de la albuminuria; tira (`strip.py`), preguntas de contexto (`context.py`) y protocolo en casa (`protocol.py`) |
| `src/latenthealth/panel/` | Datos, modelo distribucional y evaluación del panel de sangre |
| `src/latenthealth/outcomes/` | Cohorte con seguimiento de mortalidad, modelo de riesgo en tiempo discreto y sus métricas |
| `src/latenthealth/kidney_trend.py` | Tendencia del filtrado glomerular |
| `src/latenthealth/home.py` | Tensión en casa, punción capilar, ritmo cardíaco y grabación del corazón |
| `src/latenthealth/kit.py` | Qué lleva el kit de cada paciente y entrada de las medidas del reloj o de la cámara |
| `src/latenthealth/diabetes.py` | Glucómetro en casa y cuestionario FINDRISC |
| `src/latenthealth/rhythm.py` | Detector de fibrilación auricular por intervalos entre latidos |
| `src/latenthealth/ejection.py` | Fracción de eyección baja con ECG de una derivación y sonido cardíaco |
| `src/latenthealth/pulse.py`, `wfdb.py` | Señal de insuficiencia cardíaca en el pulso y lector de latidos de PhysioNet |
| `src/latenthealth/music.py` | Cohorte española MUSIC de insuficiencia cardíaca |
| `src/latenthealth/predimed.py`, `rdata.py` | Muestra española PREDIMED y lector de sus datos |
| `src/latenthealth/cvrisk.py` | SCORE2, SCORE2-OP y categorías de riesgo cardiovascular |
| `src/latenthealth/assessment.py` | Evaluación completa de un paciente |
| `src/latenthealth/worklist.py` | Lista del cupo |
| `src/latenthealth/recalibration.py` | Recalibración de los priors a España |
| `src/latenthealth/decision.py` | Umbrales por utilidad clínica y beneficio neto |
| `src/latenthealth/cohort.py` | Pacientes de prueba a partir de NHANES |
| `scripts/` | Descarga de datos, ajuste, validación, simulación y demos |
| `models/` | Parámetros y modelos ya entrenados |
| `reports/` | Informes generados por los scripts |
| `tests/` | Tests |

---

## Entrega del hackathon (instrucciones de la organización)

Welcome! This is your team's repository for developing and delivering your hackathon project.

### Where to work

Find your team's repository on the [organisation's repositories page](https://github.com/orgs/HackathonBoehringerIT/repositories).

Use only the private repository assigned to your team. Your teammates can access it after accepting their organisation invitations. Do not work in `base_template`; it is a shared, read-only starting point.

Your team can work in this repository throughout the hackathon. It is the one place to deliver your project—do not create or submit a separate repository.

### Submission deadline

The organisers will announce the final deadline and its time zone. **Any work uploaded after that deadline will not be taken into account.**

Before the deadline, make sure the final version is committed and pushed to the repository's `main` branch. If you use a pull request, merge it before the deadline; work left only on another branch or in an unmerged pull request may not be included in the final review.

You only need to deliver your project through this repository. You do **not** need to wait until the end to upload it: it is recommended that you make commits throughout the project, recording the different stages of your planning, development, and final result. This gives your team a useful history of how the project evolved.

### Before the deadline

- Confirm the final version is present on the `main` branch.
- Make sure any pull requests containing final work have been merged.
- Open the important files on GitHub and check that they render or download correctly.
- Confirm the work was committed and pushed before the announced deadline and time zone.

If you cannot access your team's repository, cannot push, or are unsure whether your work was submitted in time, contact an organiser as soon as possible.
