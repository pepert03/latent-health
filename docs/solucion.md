# LatentHealth: detección precoz cardio-renal-metabólica a partir de la orina

Reto 1 del hackathon de Boehringer: que el médico de atención primaria detecte a tiempo a los
pacientes con riesgo cardiovascular (diabetes, hipertensión, enfermedad renal crónica,
insuficiencia cardíaca) sin añadirle trabajo.

## 1. El problema, con datos

La diabetes, la hipertensión, la enfermedad renal crónica (ERC) y la insuficiencia cardíaca (IC)
se alimentan entre sí. Los pacientes de más riesgo no se escapan porque no se hagan analíticas,
sino por cuatro fallos en la cadena:

1. **No se pide la orina.** El cociente albúmina/creatinina (UACR) se hace a ~50 % de los
   diabéticos y a ~4 % de los hipertensos (metaanálisis de Shin et al., *Hypertension* 2021).
2. **Un UACR aislado engaña y no se confirma.** En NHANES 2009-2010, la mitad de los positivos de
   una muestra aleatoria no se repiten en la primera orina de la mañana, y solo el 40 % de los
   A2 siguen siendo A2.
3. **Lo que sale en la analítica no se convierte en diagnóstico.** Más del 80 % de los pacientes con
   ERC estadio 3 según su analítica no tienen el diagnóstico registrado (REVEAL-CKD).
4. **Inercia terapéutica.** Solo entre el 10 % y el 33 % de los pacientes que deberían tomar un
   iSGLT2 lo toman.

Por eso el producto no es "un modelo de riesgo más". Es un sistema que **cierra el circuito de la
albuminuria** y **estima con su incertidumbre todo lo que hace falta para el diagnóstico**,
diciendo qué prueba pedir y cuándo.

## 2. Qué hemos construido

### 2.1 Filtro bayesiano de la albuminuria (`src/latenthealth/albuminuria/`)

Estima el UACR **verdadero** del paciente a partir de todas sus muestras de orina, aunque sean de
distinto tipo, estén diluidas o salgan por debajo del límite de detección.

- **Estado oculto:** log-UACR verdadero, en la escala de la primera orina de la mañana.
- **Prior:** mezcla de tres normales (normal, elevada, muy elevada) cuyos pesos y medias dependen
  de la edad, el sexo, la diabetes y el FG.
- **Medida:** cada muestra = nivel verdadero + exceso según el tipo de muestra + variación.
  - El **exceso de la muestra aleatoria** crece con la albuminuria: ×1,23 a 3 mg/g, ×1,49 a 30 y
    ×1,81 a 300.
  - La **variación habitual** es una t de Student, con más ruido en orina diluida (creatinina en
    orina baja).
  - Las **elevaciones transitorias** son de cola pesada (ejercicio, postura, fiebre, infección,
    sangre). Aparecen en el 15 % de las muestras aleatorias y en el 7 % de las de la mañana, y son
    mucho más frecuentes en mujeres.
  - La **albúmina bajo el límite de detección** se trata como dato censurado.
- **Dinámica:** paseo aleatorio entre fechas (supuesto de la literatura: ±42 % al año) y
  suavizado hacia atrás para dibujar la trayectoria.
- **Decisión:**
  - *Descartada* si P(UACR ≥ 30) ≤ 5 %.
  - *Dudosa* si está entre 5 % y 95 %. Indica la probabilidad de que una muestra más resuelva la
    duda, según sea primera de la mañana o aleatoria.
  - *Muy probable* si P ≥ 95 %. Pasa a *confirmada* cuando hay dos momentos con P ≥ 90 %
    separados más de 3 meses (criterio de cronicidad KDIGO).

**Ajuste:** máxima verosimilitud con gradiente analítico (verificado contra diferencias finitas)
sobre las 4.437 personas de entrenamiento de NHANES 2009-2010. Cada una tiene dos muestras de
orina: una aleatoria y una primera de la mañana.

**Validación** (976 personas de test; informe completo en `reports/validacion_albuminuria.md`):

| Variante (cada una quita una pieza a la anterior) | Log-verosimilitud por persona en test |
|---|---|
| Modelo completo | **-1,785** |
| Elevaciones de cola ligera | -1,789 |
| Sin dilución ni sexo/edad en la muestra | -1,798 |
| Sin exceso creciente de la muestra aleatoria | -1,802 |
| Sin elevaciones transitorias | -1,825 |
| Ruido normal (el modelo "de libro") | -1,931 |

- **Calibración.** Con una sola muestra aleatoria, el filtro deja como *dudosos* al 7 % de las
  personas. De ellas, el modelo espera que se confirme el 39,8 % y se confirma el 38,4 %.
- **Muestra aleatoria con UACR entre 30 y 300.** Solo se confirma en la mañana entre el 18 % y el
  74 % de los casos según el valor, y el modelo lo reproduce tramo a tramo.
- **Frente a otros métodos.** Predice si la siguiente muestra saldrá ≥ 30 mejor que una regresión
  logística entrenada solo para eso (log-loss 0,102 frente a 0,107; AUC 0,918 frente a 0,911).
  También mejora mucho la regla habitual de "un positivo es positivo": Brier 0,027 frente a 0,067,
  y con esa regla el 60 % de los positivos no se repiten.

### 2.2 Panel virtual de sangre (`src/latenthealth/panel/`)

Estima la distribución completa de cada variable de la analítica: mediana, intervalo del 80 % y
probabilidad de pasar cada umbral clínico. Usa la historia clínica (edad, sexo, IMC, cintura,
tensión, diagnósticos, fármacos, tabaco) y la orina.

- **Método:** regresión distribucional por tramos. Un clasificador de gradient boosting predice la
  probabilidad de cada tramo de la variable, y los umbrales clínicos son límites de tramo.
- **Datos:** NHANES 2009-2018 (26.762 adultos) para la analítica, y NHANES 1999-2004 (11.370 adultos
  con suero guardado) para el NT-proBNP.
- **Evaluación:** con el 20 % de test (informe completo en `reports/panel_sangre.md`).

AUC de cada decisión clínica según lo que se sabe del paciente:

| Decisión | Solo orina | Edad y sexo | Historia clínica | Historia clínica y orina |
|---|---|---|---|---|
| FG < 60 | 0,71 | 0,88 | 0,91 | **0,92** |
| FG < 60 en diabéticos o hipertensos | - | 0,81 | 0,85 | **0,86** |
| HbA1c ≥ 6,5 % | 0,70 | 0,71 | 0,92 | **0,93** |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | - | 0,67 | 0,79 | **0,81** |
| Glucosa ≥ 126 | 0,69 | 0,68 | 0,85 | **0,86** |
| Colesterol no-HDL ≥ 190 | 0,52 | 0,66 | 0,76 | **0,76** |
| Anemia | 0,49 | 0,70 | 0,76 | **0,76** |
| Potasio ≥ 5,0 (muy poco frecuente) | 0,62 | 0,71 | 0,73 | 0,75 |
| NT-proBNP ≥ 125 (descarta IC en consulta) | - | 0,88 | 0,90 | **0,90** |
| NT-proBNP ≥ 125 sin diagnóstico de IC | - | 0,87 | 0,89 | **0,89** |
| UACR ≥ 30 en hipertensos sin diabetes | 0,90 | 0,65 | **0,53** | 0,91 |

Los intervalos del 80 % cubren entre el 79 % y el 84 % de los valores reales en todas las variables.

**Lo que dicen los datos, sin adornos:**

- **La orina sola no sustituye a la analítica de sangre.** Con albúmina, creatinina, volumen y flujo
  de la orina, el FG < 60 se predice con AUC 0,71 y el resto se queda cerca del azar. Tampoco ayuda
  añadir tasas de excreción. Por eso el panel combina la orina con la historia clínica.
- **La orina sí añade información sobre el riñón.** Sobre la historia clínica, mejora la estimación
  del FG un 3,4 % y las del NT-proBNP y la glucosa un poco.
- **El potasio es impredecible sin medirlo.** La mejora frente a no mirar al paciente es del 5 %, así
  que antes de tocar IECA/ARA-II o finerenona hay que medirlo siempre.
- **La albuminuria no se puede adivinar con la historia clínica.** En hipertensos sin diabetes el
  AUC es 0,53, puro azar: la única forma de encontrarla es pedir la orina. Es justo el grupo en el
  que hoy se pide al 4 %.
- **El escenario de "solo un test de orina".** Junto con la historia clínica, permite ordenar con
  buena precisión a quién le falta analítica (FG, HbA1c, NT-proBNP) y decidir qué pedir. No permite
  evitar la analítica cuando el resultado cambia el tratamiento.

### 2.3 Evaluación por paciente (`src/latenthealth/assessment.py`)

Une las dos piezas. Un valor medido reciente siempre sustituye a la estimación. Devuelve:

- **Albuminuria:** estado, UACR verdadero con su intervalo y trayectoria.
- **Analítica:** cada variable, medida o estimada con su intervalo.
- **ERC:** probabilidad de cada categoría de FG y de cada nivel de riesgo KDIGO (cruzando FG y
  albuminuria), además de P(FG < 60 o albuminuria ≥ 30).
- **Diabetes:** si no está diagnosticada, P(HbA1c ≥ 6,5 %).
- **Insuficiencia cardíaca:** si no está diagnosticada, P(NT-proBNP ≥ 125).
- **Pruebas recomendadas:**
  - UACR, si falta, es dudoso o falta la cronicidad.
  - Creatinina, si P(FG < 60) > 5 %.
  - HbA1c, si P(diabetes oculta) > 5 %.
  - NT-proBNP, si P(≥ 125) ≥ 30 %.
  - Potasio, antes de tratar el riñón.

Ejemplo (paciente inventado; `scripts/demo.py` tiene cinco):

```
5. Hombre de 78 años, obeso, hipertenso y con cardiopatía isquémica, sin analítica reciente
ALBUMINURIA
  Estado: Dudosa · UACR verdadero estimado: 44 mg/g (80 %: 11-72) · A2 72 %
DIAGNÓSTICOS
  Enfermedad renal crónica: P(FG < 60 o albuminuria ≥ 30) = 79 %
  Diabetes: posible (P = 13 %)
  Insuficiencia cardíaca: a descartar (P(NT-proBNP ≥ 125) = 79 %)
PRUEBAS RECOMENDADAS
  - UACR (primera orina de la mañana) · Creatinina (FG) · HbA1c · NT-proBNP
```

## 3. Cómo ejecutarlo

```bash
uv sync
```

```bash
uv run python scripts/demo.py
```

```bash
uv run pytest
```

Los modelos ya entrenados están en `models/`. Para rehacerlo todo desde los datos públicos
(unos 220 MB de NHANES):

```bash
uv run python scripts/download_nhanes.py
```

```bash
uv run python scripts/fit_albuminuria.py
```

```bash
uv run python scripts/validate_albuminuria.py
```

```bash
uv run python scripts/fit_panel.py
```

`fit_albuminuria.py --variant <nombre>` ajusta las variantes de la tabla de validación
(`picos_normales`, `sin_covariables_muestra`, `sin_pendiente`, `sin_picos`, `normal`).

## 4. Límites y supuestos

- **Datos de EE. UU. (NHANES), sin ponderar.** No es población de atención primaria española. El
  modelo de medida de la orina (sesgo, ruido, elevaciones) debería transferirse bien. Los priors y
  el panel hay que recalibrarlos con datos locales.
- **Sin tira reactiva.** NHANES no tiene glucosa, proteínas, sangre ni densidad en orina. Con la tira,
  la HbA1c y la glucosa (glucosuria) y las elevaciones transitorias (sangre, leucocitos, nitritos)
  mejorarían. Un estudio coreano obtuvo un AUC ≥ 0,90 para FG < 60 con edad, sexo y tira.
- **La dinámica de la albuminuria a meses o años es un supuesto.** NHANES solo tiene dos muestras
  separadas unos días. Faltan además el efecto de los tratamientos (IECA/ARA-II e iSGLT2 bajan la
  albuminuria un 30-40 %) y las señales de la tira como causa de una elevación.
- **NT-proBNP con sueros de 1999-2004** y con la historia clínica de entonces.
- **Riesgo KDIGO:** se asume que FG y albuminuria verdadera son independientes una vez conocidos la
  historia y la orina.
- **Sin analíticas anteriores del paciente.** NHANES es transversal. En la práctica, el FG o la HbA1c
  del año pasado estrecharían mucho los intervalos.
- **Umbrales de recomendación** (5 %, 30 %, 95 %): son razonables, pero no están validados
  clínicamente.
- **Es apoyo a la decisión, no diagnóstico.** Antes de usarse en pacientes necesitaría validación
  prospectiva y marcado como producto sanitario.

## 5. Próximos pasos

1. Recalibrar con datos españoles de atención primaria (SIDIAP, BIGPAC) con UACR repetidos y tira
   reactiva.
2. Modelo longitudinal del FG y la HbA1c usando las analíticas anteriores del paciente.
3. Efecto de los tratamientos y de las señales de la tira en el filtro.
4. Integración en la historia clínica (FHIR): lista de trabajo del cupo ordenada por probabilidad y
   petición de pruebas con un clic.
