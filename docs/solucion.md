# LatentHealth: detección precoz cardio-renal-metabólica, medida en casa

Reto 1 del hackathon de Boehringer: que el médico de atención primaria detecte a tiempo a los
pacientes con riesgo cardiovascular (diabetes, hipertensión, enfermedad renal crónica,
insuficiencia cardíaca) sin añadirle trabajo.

La apuesta: **el paciente se mide en casa, fácil y las veces que haga falta; la médica recibe una
lista ya ordenada.** Entre los dos hay un modelo que sabe cuánto fiarse de cada medida.

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

El contexto español empuja en la misma dirección:

- **ONDAAS** (Burgos, 2024; 9.526 adultos con analítica en primaria): el 14 % tenía albuminuria y
  903 personas la tenían con el filtrado glomerular normal. Una alerta de filtrado bajo no las ve.
- **Consenso del SNS sobre ERC** (abril de 2026): cribado anual de sangre y orina en mayores de 60
  años y grupos de riesgo, con alertas automáticas de filtrado bajo en la historia clínica. Esas
  alertas van a ser estándar; la albuminuria repetida y confirmada es lo que sigue sin resolver.
- **Cribado en casa.** Ya existe (tira leída con el móvil, tubo por correo). En el ensayo THOMAS
  (*Lancet* 2023) el tubo por correo tuvo más participación (59 % frente a 44 %) y mucha más
  especificidad (97 % frente a 68 %) que la aplicación. Una tira en casa es una medida ruidosa:
  hace falta algo que sepa combinar varias.

Por eso el producto no es "un modelo de riesgo más". Es un sistema que **cierra el circuito de la
albuminuria desde casa**, **estima con su incertidumbre lo que falta para el diagnóstico** y le
dice a la médica a quién mirar y qué pedirle.

### Qué parte de la enfermedad cardiovascular cubre

En España la primera causa concreta de muerte es la cardiopatía isquémica (26.851 muertes en
2024, datos provisionales del INE), y entre las quince primeras están también el ictus, la
insuficiencia cardíaca, la enfermedad hipertensiva, la diabetes y la insuficiencia renal, que fue
la que más creció (+10,3 %). Hay dos mecanismos: el daño de los vasos pequeños, que une riñón y
corazón, y la aterosclerosis de las arterias grandes, que causa el infarto y el ictus. El proyecto
se centra en el primero, que es el que hoy pasa desapercibido, y no pretende detectar todas las
enfermedades del corazón:

| Enfermedad | Qué hace el proyecto |
|---|---|
| Enfermedad renal crónica | El núcleo: albuminuria repetida en casa, filtrado y su tendencia |
| Diabetes | Glucómetro en casa: encuentra el 86 % de la diabetes oculta donde el cuestionario FINDRISC encuentra el 52 % (apartado 3.12) |
| Hipertensión | Tensión medida en casa con el protocolo de una semana |
| Infarto e ictus (aterosclerosis) | SCORE2 y un modelo propio de muerte cardiovascular entrenado con desenlaces reales y comprobado en españoles (apartado 3.10) |
| Insuficiencia cardíaca | Probabilidad de NT-proBNP alto, afinada con síntomas y pulso (apartado 3.11). Es la parte más débil |
| Arritmias | Detector propio de fibrilación auricular por la irregularidad del pulso, validado con 8.528 registros reales (apartado 3.12) |
| Valvulopatías y cardiomiopatías | Nada: se ven con ecografía o auscultación |

## 2. Cómo funciona

1. **El sistema recorre el cupo.** Con la historia clínica calcula, para cada paciente, la
   probabilidad de que las pruebas que le faltan den un hallazgo nuevo.
2. **Al paciente le llega un kit** por el canal que le sirve: aplicación, carta, farmacia,
   enfermería o tubo por correo.
3. **Antes de cada prueba contesta cuatro preguntas** (ejercicio intenso, fiebre, regla, escozor
   al orinar). Si alguna es que sí, la prueba se aplaza.
4. **Hace la tira y el sistema le contesta**: "ya está", "repite mañana" o "manda el tubo". Solo
   repite quien tiene un resultado dudoso.
5. **La médica abre la lista.** Arriba, los hallazgos claros que no constan en la historia. Debajo,
   los pacientes ordenados por la probabilidad de hallazgo nuevo, con la prueba que más aporta.

`scripts/demo_casa.py` lo enseña con pacientes inventados. Un recorrido:

```
Marta, 47 años, diabética  ·  canal: aplicación
  16/11  [TIRA]     Mañana, con la primera orina del día, haz una tira y hazle la foto con la aplicación.
                    Contesta a las preguntas: sí a regla
  16/11  [ESPERAR]  Hoy la prueba no sería fiable. Espera tres días después de que termine la regla.
  22/11  Resultado (tira: albúmina 30 mg/l, creatinina 100 mg/dl)        P(albuminuria) = 14 %
  22/11  [TUBO]     Para salir de dudas hace falta medirlo en el laboratorio. Mañana, llena el tubo...
  23/11  Resultado (laboratorio: 58 mg/g)                                P(albuminuria) = 75 %
  24/11  Resultado (laboratorio: 64 mg/g)
  24/11  [REPETIR A LOS 3 MESES]  Hemos visto albúmina en la orina. Para confirmarlo hay que repetir...
  22/02  Resultado (laboratorio: 71 mg/g)
  22/02  [FIN]      Hemos encontrado albúmina en la orina de forma repetida. Tu centro te llamará.
```

Y la lista de la médica:

```
ACTUAR: hallazgos claros que no constan en la historia
  Pedro (70), diabético con albuminuria repetida · riesgo muy alto · 1,5 veces el riesgo de su edad
      - Albuminuria persistente sin enfermedad renal crónica registrada.
  Ramón (56), obeso y fumador · riesgo alto
      - Glucosa en ayunas de 126 mg/dl o más en dos días distintos, medida en casa: confirmar con HbA1c.
  Rosa (68), FG que baja año tras año · riesgo alto · 1,4 veces el riesgo de su edad
      - Descenso rápido del FG: -8,2 ml/min/1,73 m² al año.
  Manuel (77), pulso irregular dos días · riesgo alto
      - Pulso irregular repetido en casa (P(fibrilación auricular) = 73%).
  Carmen P. (59), tensión alta en casa sin diagnóstico · riesgo bajo o moderado
      - Tensión alta en casa: media 149/91 mmHg (límite 135/85). Sin hipertensión registrada.

MEDIR: probabilidad de un hallazgo nuevo si se completan las pruebas
  Elena (74), punción capilar con FG 51 · hallazgo nuevo 59% · pedir primero: creatinina
  Marta (47), diabética con tiras dudosas · hallazgo nuevo 39% · pedir primero: orina (kit en casa)
  Antonio (81), sin analítica en años · hallazgo nuevo 24% · pedir primero: creatinina

Sin pendientes: 3 de 11 pacientes.
```

## 3. Qué hemos construido

### 3.1 Filtro bayesiano de la albuminuria (`src/latenthealth/albuminuria/`)

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

### 3.2 La orina en casa: tira, preguntas, protocolo y canales

**Tira (`albuminuria/strip.py`).** Una tira no da un UACR: da el nivel de color de la almohadilla
de albúmina (10, 30, 80 o 150 mg/l) y el de la de creatinina (10 a 300 mg/dl). El filtro calcula
la probabilidad de cada lectura dado el UACR verdadero, integrando la dilución de la orina y el
error de lectura de cada almohadilla, y la usa igual que una muestra de laboratorio. También admite
tiras que solo dan la categoría del cociente. `fit_strip_spec` calibra una tira concreta con
muestras leídas a la vez con la tira y en el laboratorio.

**Preguntas de contexto (`albuminuria/context.py`).** Ejercicio intenso, fiebre, regla y síntomas
de infección suben la probabilidad de una elevación pasajera. Si el paciente contesta que sí, la
prueba se aplaza; si contesta que no a todo, el filtro se fía más de un resultado alto.

**Protocolo en dos etapas (`albuminuria/protocol.py`).** Tira para todos. Se pasa al tubo de
laboratorio cuando se acaban las tiras del kit o cuando una tira más resolvería la duda con
probabilidad menor del 30 %. Un positivo claro se repite a los tres meses, como exige la
cronicidad.

**Canales.** Aplicación (tira leída con el móvil), carta (tira leída a ojo, el paciente comunica
dos números), farmacia, enfermería y correo (solo tubo). Cambian el error de lectura y el texto de
las instrucciones; la lógica es la misma.

**Resultados en simulación** (`reports/cribado_en_casa.md`; 1.500 personas simuladas de 60 años o
más o con diabetes, con el protocolo real y el modelo de medida ajustado en NHANES; el 10,1 % tiene
albuminuria). El VPP es la parte de los señalados que tiene albuminuria de verdad.

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Una tira positiva | 59 % | 91 % | 9,3 % | - | 1,00 | - |
| Dos de tres tiras positivas | 67 % | 94 % | 6,0 % | - | 3,00 | - |
| **Filtro: tiras con el móvil y tubo si hay duda** | **98 %** | 81 % | 4,0 % | 3,1 % | **1,17** | 0,13 |
| Filtro: tira de 3 categorías y tubo | 98 % | 85 % | 8,6 % | 1,8 % | 1,08 | 0,13 |
| Filtro: tiras leídas a ojo y tubo | 97 % | 82 % | 4,0 % | 3,1 % | 1,19 | 0,15 |
| Filtro: solo tubo por correo | 99 % | 73 % | 2,6 % | 5,6 % | - | 1,11 |
| Filtro: color leído en continuo, mismo error de lectura | 98 % | 83 % | 4,6 % | 3,1 % | 1,18 | 0,12 |
| Filtro: color leído en continuo, mitad de error | 99 % | 85 % | 4,0 % | 2,7 % | 1,16 | 0,10 |

**Margen de error.** Solo hay unas 150 personas con albuminuria en la simulación: cada una pesa
0,7 puntos en las columnas de positivos, y un porcentaje pequeño tiene un margen de unos ±3
puntos. La simulación se ha hecho dos veces con poblaciones distintas; abajo solo se da por bueno
lo que salió igual las dos veces.

Lo que se repite en las dos simulaciones:

- **El filtro convierte una tira mediocre en una decisión fiable.** El VPP pasa del 55-67 % al
  98-99 % con 1,2 tiras por persona de media y un tubo para el 13-15 %. Los que quedan sin
  resolver (3 %) pasan al centro de salud; no se pierden.
- **La tira deja escapar más albuminurias que el tubo**: entre el 4 % y el 7 % frente a entre el
  0,6 % y el 2,6 %. Son las cercanas a 30 mg/g.
- **La tira que solo da la categoría del cociente es la peor** (más del 8 % de descartes las dos
  veces). Leer las dos almohadillas por separado sí merece la pena.
- **Por cada 1.000 invitados, el correo detecta más** (44 albuminurias frente a 36 con la
  aplicación) porque participa más gente, pero manda diez veces más tubos al laboratorio.

Leer el color con un modelo de visión (`VISION_STRIP`):

- El color de la almohadilla cambia de forma gradual; los 4 o 5 niveles son para el ojo. Un modelo
  de visión podría leerlo en continuo.
- **Con el mismo error de lectura que la foto de hoy, casi no cambia nada** (83 % detectados frente
  a 81 %, dentro del margen). Con la mitad de error se detecta el 85 % y hacen falta menos tubos.
- La mejora es modesta porque lo que limita no es el número de niveles: es que la orina cambia de
  un día a otro y que la almohadilla no distingue por debajo de 10 mg/l.

Lo que **no** se repite, y por tanto no se afirma:

- **Bajar el umbral de descarte al 2 %.** En la primera simulación redujo los descartes a la mitad;
  en la segunda no cambió nada.
- **Las preguntas de contexto.** En la primera bajaron los descartes un punto; en la segunda los
  subieron un punto. Su efecto es además un supuesto.

### 3.3 Panel virtual de sangre (`src/latenthealth/panel/`)

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
  de la orina, el FG < 60 se predice con AUC 0,71 y el resto se queda cerca del azar. Por eso el
  panel combina la orina con la historia clínica, y por eso hacen falta otras medidas en casa
  (apartado 3.5).
- **Casi toda la capacidad viene de la edad y el sexo** (FG < 60: 0,88 → 0,92). El panel sirve para
  decidir a quién medir, no para ahorrarse la medida.
- **El potasio es impredecible sin medirlo.** Antes de tocar IECA/ARA-II o finerenona hay que
  medirlo siempre.
- **La albuminuria no se puede adivinar con la historia clínica.** En hipertensos sin diabetes el
  AUC es 0,53, puro azar: la única forma de encontrarla es pedir la orina.

### 3.4 Tendencia del filtrado glomerular (`src/latenthealth/kidney_trend.py`)

El enunciado habla de "una función renal que va deteriorándose poco a poco sin que duela". Un
filtro de Kalman sobre (nivel, pendiente) recorre las creatininas previas del paciente:

- **Ruido de la creatinina.** Entre dos analíticas el FG se mueve varios puntos sin que pase nada.
  El error de cada medida sale de la variación de la creatinina y de la ecuación CKD-EPI.
- **Dos grupos de pacientes.** La mayoría pierde FG despacio y unos pocos deprisa (más con
  diabetes o albuminuria, que el filtro de la orina aporta). Son dos filtros, uno por grupo, que
  se mezclan según los datos.
- **Tratamientos como entrada conocida.** Al empezar un iSGLT2 o un IECA/ARA-II el FG cae unos
  puntos y luego baja más despacio. Si se le dice al filtro, no lo toma por un descenso.
- **Salidas.** Nivel actual con su intervalo, pendiente, P(descenso de más de 3 al año), P(más de
  5 al año, criterio KDIGO), P(FG < 30 en cinco años) y si hay dos analíticas por debajo de 60
  separadas más de tres meses.

**Comprobación en simulación** (`reports/tendencia_fg.md`). No es una validación con pacientes:
NHANES no tiene analíticas repetidas y todos los parámetros son supuestos de la literatura. De
los pacientes que pierden más de 5 al año, cuántos se marcan; y de los que pierden menos de 2,
cuántos se marcan por error:

| Analíticas anuales | Filtro, alerta (P ≥ 80 %) | Falsa alarma | Filtro, aviso (P ≥ 50 %) | Falsa alarma | Regla a ojo (caída media > 5 al año) | Falsa alarma |
|---|---|---|---|---|---|---|
| 2 | 1 % | 0,0 % | 6 % | 0,3 % | 60 % | 24,3 % |
| 3 | 17 % | 0,2 % | 38 % | 1,1 % | 62 % | 11,2 % |
| 4 | 45 % | 0,2 % | 72 % | 1,2 % | 79 % | 3,5 % |
| 5 | 71 % | 0,2 % | 90 % | 1,5 % | 78 % | 1,5 % |
| 6 | 88 % | 0,3 % | 96 % | 1,9 % | 85 % | 0,7 % |

- **Lo que aporta es quitar falsas alarmas.** Con dos analíticas, mirar la caída a ojo marca por
  error a uno de cada cuatro pacientes estables; el filtro, a casi ninguno.
- **Es prudente.** Con tres o cuatro analíticas ve menos descensos reales que la regla a ojo. A
  partir de cinco ve más.
- **iSGLT2.** En pacientes estables que lo empiezan, las alertas falsas de descenso bajan del
  1,1 % al 0,2 % cuando el tratamiento entra como dato.

### 3.5 Otras medidas en casa (`src/latenthealth/home.py`)

Como la orina no sustituye a la sangre, el paciente necesita otras medidas para completar la
evaluación sin desplazarse:

- **Tensión con manguito validado.** Protocolo habitual de una semana: se descarta el primer día
  y se promedia el resto. Da la probabilidad de que la media verdadera pase de 135/85 y alimenta
  el SCORE2 (sumando 5 mmHg para equipararla a la de consulta).
- **Punción capilar** (gota de sangre en papel, por correo) para creatinina y HbA1c. Tiene más
  error que la sangre venosa, así que **no sustituye a la estimación: la actualiza** con la regla
  de Bayes. Un FG capilar de 51 deja la estimación en 59 (entre 51 y 68) y recomienda confirmarlo
  en el laboratorio.
- **Ritmo cardíaco** con el móvil o el reloj. Dos comprobaciones irregulares en un paciente de 77
  años dejan la probabilidad de fibrilación auricular en el 73 % y se pide un ECG.

Los errores de medida son supuestos. La prevalencia de fibrilación auricular de partida es
española y medida (apartado 3.11). La evidencia de la punción capilar para el FG es todavía de
estudios pequeños.

### 3.6 Riesgo cardiovascular y lista del cupo (`cvrisk.py`, `worklist.py`)

**Riesgo cardiovascular.** SCORE2 (40-69 años) y SCORE2-OP (70 o más) para región de riesgo bajo,
con los coeficientes publicados, y las categorías de la guía europea de 2021 (bajo o moderado,
alto, muy alto), en las que la enfermedad renal, la diabetes y la enfermedad cardiovascular fijan
un mínimo. Cuando faltan datos se propaga su incertidumbre: se obtiene la probabilidad de cada
categoría y la de que la categoría real sea más alta que la que consta.

**Una albuminuria aislada casi nunca cambia la categoría de la guía.** Con el filtrado normal,
30-300 mg/g no la mueven, y la mayoría de los mayores de 55 años ya son de riesgo alto por el
SCORE2. Ordenar la lista solo por "sube de categoría" dejaba fuera justo a los pacientes del
reto. Por eso la lista ordena por un **hallazgo nuevo**: subir de categoría, encontrar una
enfermedad renal que no consta (FG < 60 o albuminuria) o una diabetes sin diagnosticar.

**La lista** tiene tres grupos: *actuar* (hallazgos ya claros que no constan en la historia),
*medir* (ordenados por la probabilidad de hallazgo nuevo, con la prueba que más aporta y cómo
hacerla en casa) y *sin pendientes*. Las predicciones de todo el cupo se calculan de una vez, así
que la lista de 1.500 pacientes tarda segundos.

**Validación con personas reales** (`reports/lista_cupo.md`; 660 personas de 40 años o más de la
partición de test de NHANES 2009-2010; el sistema recibe solo la historia y se compara con lo que
de verdad midió NHANES):

| Situación | Hallazgo nuevo real | AUC de la lista | AUC por edad | AUC por SCORE2 | Aciertos en el primer 20 % |
|---|---|---|---|---|---|
| A. Lípidos y tensión conocidos; faltan orina y creatinina | 15,9 % | 0,75 | 0,73 | 0,75 | 37 % (36-37 % por edad o SCORE2) |
| B. Sin ninguna analítica | 20,8 % | 0,73 | 0,62 | 0,69 | 42 % (37-39 %) |

- **Cuando ya hay lípidos, la lista no ordena mejor que la edad o el SCORE2.** Es coherente con el
  panel: casi toda la señal está en la edad.
- **Sin analítica sí ordena mejor** (AUC 0,73 frente a 0,62 por edad).
- **Sus probabilidades están calibradas**, y eso es lo que la edad no da: de las 144 personas a
  las que da menos del 5 %, tiene un hallazgo el 3,5 %; de las 44 a las que da entre el 40 % y el
  60 %, el 52 %. Sirve para decidir cuántos kits mandar y a quién no mandárselo.
- El valor de la lista está también en el primer grupo, que no es una predicción: son hallazgos
  ya medidos que nadie ha convertido en diagnóstico.

### 3.7 Evaluación por paciente (`src/latenthealth/assessment.py`)

Une todas las piezas. Un valor de laboratorio reciente sustituye a la estimación; una medida
capilar de casa la actualiza. Devuelve:

- **Hallazgos que piden actuar:** albuminuria persistente o FG < 60 mantenido sin ERC registrada,
  descenso del FG, tensión alta en casa, HbA1c o NT-proBNP altos sin diagnóstico, pulso irregular.
- **Albuminuria:** estado, UACR verdadero con su intervalo y trayectoria.
- **Analítica:** cada variable, medida, capilar o estimada, con su intervalo.
- **Tendencia del FG**, si hay analíticas previas.
- **ERC:** probabilidad de cada categoría de FG y de cada nivel de riesgo KDIGO, cruzando FG y
  albuminuria sin tratarlos como independientes (apartado 3.9).
- **Diabetes e insuficiencia cardíaca:** P(HbA1c ≥ 6,5 %) y P(NT-proBNP ≥ 125) si no hay
  diagnóstico.
- **Riesgo cardiovascular:** SCORE2, categoría que consta, categoría real probable y probabilidad
  de hallazgo nuevo con cada prueba pendiente.
- **Riesgo con lo medido en casa:** cuántas veces el riesgo de muerte cardiovascular de alguien de
  su edad y sexo (apartado 3.10), y qué datos de casa faltan.
- **Pruebas recomendadas**, con umbrales que salen de una utilidad explícita (apartado 3.9).

### 3.8 Recalibración a España (`recalibration.py`, `reports/recalibracion_espana.md`)

Los modelos se ajustaron con datos de EE. UU. El modelo de medida de la orina debería valer
igual aquí; lo que cambia es cuánta enfermedad hay antes de medir. Se corrige moviendo solo
interceptos, con las prevalencias de ONDAAS y NHANES repesado a su reparto por edad y sexo:

| | ONDAAS | Modelo de NHANES | Recalibrado |
|---|---|---|---|
| Muestra de orina ≥ 30 mg/g | 14,0 % | 15,1 % | 14,0 % |
| FG < 60 (ecuación de 2009) | 12,8 % | 18,3 % | 12,8 % |

- **El prior de albuminuria de NHANES ya estaba cerca** (15,1 % frente a 14,0 %): la corrección es
  pequeña. Depende de un supuesto: el artículo no dice si la orina era la primera de la mañana.
  Si lo fuera, el modelo daría 9,6 % y la corrección sería grande y de signo contrario.
- **El filtrado bajo sí es menos frecuente** que en EE. UU. a igual edad y sexo, y se corrige.
  ONDAAS usó la ecuación CKD-EPI de 2009 y aquí se usa la de 2021; el objetivo se traduce de una
  a otra persona a persona.
- La evaluación usa los priors recalibrados por defecto (`population="espana"`). Las
  validaciones con NHANES usan los modelos sin recalibrar.
- Es una corrección de población, no una validación: ONDAAS son pacientes a los que se pidió
  analítica, no todo el cupo, y no hay datos individuales españoles.

### 3.9 Robustez (`reports/robustez.md`)

**FG y albuminuria juntos.** Antes se multiplicaban sus probabilidades como si fueran
independientes. Ahora, cuando el FG no está medido, el filtro de albuminuria se resuelve para
cada categoría de FG y se combinan. **En NHANES no se nota la diferencia**: la pérdida
logarítmica del riesgo KDIGO alto es 0,067 con independencia y 0,070 con el método nuevo, y entre
las 979 personas de test solo hay 27 de riesgo alto y 6 con FG < 60 y albuminuria a la vez. Se
deja el método nuevo porque es coherente y no empeora, pero no es una mejora demostrada.

**Calibración por sexo y edad.** De 24 grupos (cuatro sucesos por sexo y tres tramos de edad), 3
se desvían:

- **FG < 60 en mayores de 65 años:** el panel predice lo mismo para hombres y mujeres (24 %) y
  la realidad es 20 % en hombres y 27 % en mujeres. Hay que corregirlo.
- **Filtro en hombres de 65 años o más:** 8,3 % observado frente a 12,1 % predicho, con 109
  personas. Puede ser ruido; a vigilar.
- **NT-proBNP en hombres menores de 50 años:** 0,7 % frente a 4,0 %. Lejos del umbral del 30 %,
  no cambia ninguna recomendación.

**Umbrales por utilidad clínica (`decision.py`).** Un umbral de probabilidad equivale a un número
de pruebas aceptables por caso encontrado (5 % = 20 pruebas). Los umbrales se escriben así y se
comprueban con curvas de decisión en la partición de test:

| Decisión | Umbral | Se pide a | Casos encontrados | Pruebas ahorradas por 100 personas frente a pedirla a todos |
|---|---|---|---|---|
| Creatinina por P(FG < 60) | 5 % | 31 % | 92 % | 58 |
| HbA1c por P(≥ 6,5 %) sin diagnóstico | 5 % | 21 % | 61 % | 26 |
| NT-proBNP por P(≥ 125) | 30 % | 29 % | 77 % | 26 |
| Orina por P(albuminuria) con la historia | 5 % | 41 % | 62 % | 19 |

La última fila confirma lo del panel: la historia no sirve para decidir a quién pedir la orina
(se deja fuera al 38 % de las albuminurias). La orina hay que ofrecerla a todo el grupo de
riesgo; la lista solo decide el orden.

### 3.10 Riesgo con desenlaces reales (`src/latenthealth/outcomes/`, `reports/riesgo_en_casa.md`)

Hasta aquí el proyecto no tenía ningún desenlace: solo analíticas de un día. Para saber si se
puede mejorar lo que se usa hoy hacen falta datos de quién enfermó o murió después.

**Datos.** NHANES 1999-2014 enlazado con el registro de defunciones de EE. UU. (hasta diciembre
de 2019). Desenlace: **muerte por enfermedad del corazón o ictus en los 10 años siguientes**. Se
evalúa en 12.710 personas de 40 años o más con diez años de seguimiento completo (701 muertes
cardiovasculares), con validación cruzada: a cada persona la predice un modelo que no la vio.

**Modelo.** Supervivencia en tiempo discreto: cada persona es una fila por año de seguimiento, y
dos clasificadores de gradient boosting estiman cada año la probabilidad de morir por causa
cardiovascular y por cualquier otra (riesgos competitivos). El riesgo a 10 años se acumula año a
año. Aprovecha a quien tiene menos seguimiento y admite datos sin aportar.

**Comparadores.** SCORE2 y SCORE2-OP publicados, que es lo que se usa en España, y las variables
de SCORE2 y de PREVENT (el modelo americano de 2023) reajustadas con estos mismos datos. La
ecuación publicada de PREVENT no se pudo incluir: no se consiguieron sus coeficientes.

AUC (probabilidad de dar más riesgo a quien muere que a quien no):

| Lo que se usa | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión |
|---|---|---|---|
| SCORE2 publicado (necesita analítica y consulta) | 0,813 | 0,826 | 0,755 |
| Edad y sexo | 0,801 | 0,806 | 0,756 |
| Historia clínica: diagnósticos, fármacos, tabaco, peso y cintura | 0,837 | 0,832 | 0,795 |
| + cinco preguntas al paciente | 0,838 | 0,833 | 0,798 |
| + manguito (tensión y pulso) | 0,840 | 0,836 | 0,799 |
| + tira de orina | 0,844 | 0,840 | 0,805 |
| + orina de laboratorio, en lugar de la tira | 0,844 | 0,840 | 0,808 |
| + analítica de sangre | 0,845 | 0,841 | 0,809 |

Diferencias en las mismas personas, con su intervalo del 95 %:

| Comparación | Todos | Sin enfermedad previa | Con diabetes o hipertensión |
|---|---|---|---|
| Historia, preguntas, manguito y orina frente a SCORE2 | +0,031 (0,022 a 0,042) | +0,014 (0,002 a 0,025) | +0,054 (0,039 a 0,070) |
| Solo la historia clínica frente a SCORE2 | +0,023 (0,014 a 0,034) | +0,007 (-0,005 a 0,018) | +0,041 (0,024 a 0,059) |
| Lo que añaden las cinco preguntas | +0,002 (-0,002 a 0,006) | +0,001 (-0,004 a 0,006) | +0,004 (-0,003 a 0,009) |
| Lo que añade el manguito | +0,002 (-0,001 a 0,005) | +0,003 (-0,002 a 0,007) | +0,000 (-0,005 a 0,006) |
| Lo que añade la tira de orina | +0,004 (0,001 a 0,007) | +0,004 (-0,000 a 0,009) | +0,006 (0,002 a 0,011) |
| Lo que añade la analítica de sangre | +0,001 (-0,002 a 0,003) | +0,001 (-0,002 a 0,004) | +0,001 (-0,003 a 0,005) |

Lo que dicen los datos, sin adornos:

- **Se mejora a SCORE2 al ordenar quién muere del corazón o de un ictus.** La ventaja es clara en
  el conjunto (+0,031) y en diabéticos e hipertensos (+0,054), que son los pacientes del reto y en
  los que SCORE2 no distingue mejor que la edad y el sexo. En personas sin enfermedad previa, que
  es para quien está pensado SCORE2, la ventaja es pequeña (+0,014).
- **La mejora no viene de medir más: viene de usar lo que ya está en la historia** (enfermedad
  cardíaca previa, fármacos), que SCORE2 no mira. No le cuesta nada al paciente.
- **De lo que se hace en casa, solo la orina añade señal medible.** Una tira basta. La albúmina en
  orina es el dato que más pesa después de la edad.
- **Las cinco preguntas y el manguito no cambian el orden del riesgo** de forma medible, y **la
  analítica de sangre tampoco**. Para ordenar el riesgo no hace falta sacar sangre. Sí hace falta
  para diagnosticar y para tratar.
- **No es el método.** Con las mismas variables de SCORE2 el modelo nuevo saca 0,817; con las de
  PREVENT, incluidas la orina y la HbA1c, 0,834. El modelo de casa llega a 0,844 sin sangre.
- **Está calibrado**: predice un 5,5 % de muertes y se observa un 5,5 %; en la décima parte de más
  riesgo predice un 26,5 % y se observa un 25,9 %. El 20 % de más riesgo recoge el 70 % de las
  muertes; con SCORE2, el 62 %.

**A igual edad y sexo.** Casi todo el AUC de 0,8 es la edad, que la médica ya conoce. Entre dos
personas de la misma edad y sexo, SCORE2 acierta a cuál dar más riesgo el 58,7 % de las veces
(el azar es el 50 %); la historia clínica, el 64,7 %; y el modelo de casa, el 66,9 %. Lo que se
sabe por encima del azar casi se duplica, y en diabéticos e hipertensos pasa de 56,1 % a 66,7 %.

**Hay techo.** Añadiendo toda la analítica de sangre se llega al 67,4 %. Con los datos que tiene
NHANES no se ordena mejor quién morirá en diez años; para ir más allá harían falta otras señales
(imagen, electrocardiograma, biomarcadores). Por eso el esfuerzo siguiente se puso en
diagnosticar lo presente (apartado 3.12) y no en afinar más este modelo.

**Comprobación en españoles** (`reports/validacion_espana.md`). La única cohorte española con
eventos que se puede descargar es una muestra del ensayo PREDIMED: 6.324 personas de alto riesgo
de atención primaria, con 252 infartos, ictus o muertes cardiovasculares. Tiene pocas variables
(sin tensión, orina ni fármacos). Un modelo entrenado solo con NHANES y esas variables da un
índice de concordancia de 0,662, frente a 0,631 con la edad y el sexo (+0,030, intervalo 0,011 a
0,051), y no pierde frente a uno entrenado dentro de PREDIMED (0,649). Los índices son bajos
porque todos los participantes son de alto riesgo y se parecen entre sí. Lo que dice es que lo
aprendido con muertes en EE. UU. se traslada a españoles y a eventos no mortales.

**Una trampa que hubo que quitar.** La primera versión daba más ventaja (+0,043). Era en parte
falsa: en NHANES un dato vacío suele ser de alguien a quien no se pudo explorar, más frágil, y el
modelo había aprendido que "sin dato" significa "más riesgo". En el producto, vacío significa "aún
no lo ha aportado". Ahora se entrena y se evalúa solo con personas que tienen todos los datos, y
el modelo final se entrena borrando bloques al azar (preguntas, peso, manguito, orina) para que
estime bien con lo que haya. En la parte reservada da un AUC de entre 0,825 y 0,829 falte lo que
falte, frente a 0,804 de SCORE2.

**En el producto** (`outcomes/risk.py`). La ficha del paciente y la lista del cupo enseñan cuántas
veces el riesgo de alguien de su edad y sexo tiene el paciente. Se enseña el riesgo relativo y no
el absoluto porque el modelo se entrenó con población de EE. UU.

Límites: solo muertes (el fichero público no tiene infartos ni ictus no mortales, que es lo que
SCORE2 pretende predecir); población de EE. UU.; cuestionario hecho por un entrevistador; y en los
ficheros públicos de mortalidad algunos tiempos y causas están sustituidos por valores sintéticos.

### 3.11 Insuficiencia cardíaca y fibrilación auricular (`reports/insuficiencia_cardiaca.md`)

**Insuficiencia cardíaca.** El NT-proBNP no se puede medir en casa. Se comprobó, con los 10.174
adultos de NHANES 1999-2004 que lo tienen medido, cuánto ayuda lo que el paciente cuenta:

| Quién tendrá el NT-proBNP alto, en personas de 60 años o más | Por encima de 125 pg/ml | Por encima de 300 pg/ml |
|---|---|---|
| Historia clínica (como hasta ahora) | 0,754 | 0,764 |
| + síntomas y pulso (falta de aire, dificultad para caminar, salud percibida) | 0,769 | 0,782 |
| + orina | 0,770 | 0,795 |

- **Los síntomas y el pulso ayudan algo**: +0,014 de AUC para 125 pg/ml (intervalo 0,009 a 0,020)
  y +0,019 para 300. Por eso la evaluación los usa si están, y los pide a los mayores de 60 años
  con sospecha.
- **Medir el NT-proBNP sigue aportando.** Para predecir la muerte por enfermedad del corazón, lo de
  casa da 0,824, lo mismo que la edad, el sexo y el NT-proBNP medido (0,822); las dos cosas
  juntas, 0,838 (+0,014, intervalo 0,004 a 0,025).
- **Sigue siendo la parte más débil.** NHANES no tiene ecocardiograma ni diagnóstico confirmado, ni
  pregunta por los síntomas más específicos (tobillos hinchados, dormir incorporado, subida rápida
  de peso). Con una cohorte que los tenga es donde más se puede ganar.

**Fibrilación auricular.** La probabilidad de partida ya no es un supuesto: sale del estudio OFRECE
(8.343 españoles de 40 años o más con ECG), por edad y sexo, y de que el 10 % de los casos no
estaba diagnosticado. El detector que la actualiza está en el apartado 3.12.

### 3.12 Diagnóstico en casa: diabetes con glucómetro y ritmo con el pulso

Predecir quién morirá en diez años tiene techo (apartado 3.10). Donde cabe mucha mejora es en
**diagnosticar lo que el paciente tiene hoy**, y eso se gana midiendo en casa.

**Diabetes sin diagnosticar** (`diabetes.py`, `reports/diabetes_en_casa.md`). Hoy, para decidir a
quién hacer el análisis sin pinchar, en España se usa el cuestionario FINDRISC. Un glucómetro
cuesta poco. Se comparan en 27.300 adultos de NHANES 2005-2018 sin diabetes diagnosticada, de los
que 865 (3,2 %) tienen una HbA1c de diabetes. La glucosa es la de laboratorio con el error de un
glucómetro doméstico (7,5 %).

| Lo que se usa (AUC) | Todos | En ayunas | Sin ayunas |
|---|---|---|---|
| FINDRISC, el cuestionario que se usa hoy | 0,754 | 0,759 | 0,749 |
| Historia clínica | 0,785 | 0,783 | 0,787 |
| Historia y orina | 0,811 | 0,813 | 0,809 |
| Solo el glucómetro | 0,896 | 0,932 | 0,849 |
| Historia, orina y glucómetro | 0,920 | 0,944 | 0,893 |

| Con el mismo esfuerzo que FINDRISC ≥ 15 (se señala al 22 %) | Diabetes oculta encontrada | VPP |
|---|---|---|
| FINDRISC ≥ 15 | 52 % | 7,6 % |
| Historia y orina | 64 % | 9,4 % |
| Historia, orina y glucómetro | 86 % | 12,6 % |
| Historia, orina y glucómetro en ayunas | 92 % | 12,8 % |

- **Con un glucómetro se encuentra el 86 % de la diabetes oculta donde FINDRISC encuentra el
  52 %**, analizando a la misma cantidad de gente. La diferencia de AUC es +0,166 (intervalo
  0,151 a 0,180).
- **Para encontrar el 80 %** hay que hacer el análisis al 44 % de las personas con FINDRISC y al
  16 % con el glucómetro.
- **Sirve aunque no esté en ayunas** (0,893), porque el modelo sabe cuántas horas lleva sin comer.
- **Regla sin modelo:** glucosa en ayunas de 110 mg/dl o más señala al 13 % y encuentra el 84 %.
- **Está calibrado:** a quien da entre el 30 % y el 60 % de probabilidad, la tiene el 47 %.
- En la ficha, la glucosa de casa actualiza la HbA1c estimada y la probabilidad de diabetes. Dos
  días en ayunas con 126 mg/dl o más salen como hallazgo. El paciente puede repetirla.

No es un hallazgo médico nuevo: la glucosa en ayunas es un criterio diagnóstico. Lo que se mide
es cuánto se gana frente a lo que hoy se usa para cribar sin análisis. Los límites: glucosa de
laboratorio con error simulado, una sola medida por persona y población de EE. UU.

**Fibrilación auricular** (`rhythm.py`, `reports/ritmo.md`). Un detector propio que no mira la
forma de la onda: detecta cada latido y mide lo irregulares que son los intervalos entre ellos,
así que sirve con un electrocardiógrafo de bolsillo, un reloj o la cámara del móvil. Entrenado y
validado con los 8.528 registros reales del PhysioNet/CinC Challenge 2017 (758 con fibrilación).

| Entrada | AUC frente a todo lo demás | AUC frente a ritmo normal | Sensibilidad | Especificidad |
|---|---|---|---|---|
| Latidos del electrocardiograma | 0,971 | 0,988 | 87,5 % | 93,8 % |
| Latidos degradados como los de una cámara (simulado) | 0,957 | 0,979 | 83,1 % | 93,5 % |
| Regla simple: variación de los intervalos | 0,751 | 0,823 | 5,4 % | 95,0 % |

- **Los falsos avisos son casi todos otras arritmias**: señala al 1,8 % de los ritmos normales y
  al 13 % de los "otros ritmos", que también conviene que vea un médico.
- **La ficha usa la razón de verosimilitud del detector**, no un sí o un no, y la aplica a la
  prevalencia española por edad y sexo: una probabilidad del detector por encima del 70 %
  multiplica la odds por 75; por debajo del 2 %, la divide por más de 20.
- **Las filas de cámara son simuladas** (20 ms de imprecisión y un 3 % de latidos perdidos). No
  hay registros de cámara etiquetados en abierto.
- No pretende superar a los mejores métodos del reto, que usan la forma de la onda y redes
  profundas, ni a las aplicaciones ya validadas. Aporta un componente propio con su error medido.

## 4. Cómo ejecutarlo

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

Los modelos ya entrenados están en `models/`. Para rehacerlo todo desde los datos públicos
(unos 360 MB de NHANES y su mortalidad enlazada), en este orden:

| Paso | Comando | Qué produce |
|---|---|---|
| 1 | `uv run python scripts/download_nhanes.py` | Datos en `data/raw/nhanes/` |
| 2 | `uv run python scripts/fit_albuminuria.py` | `models/albuminuria_params.json` |
| 3 | `uv run python scripts/validate_albuminuria.py` | `reports/validacion_albuminuria.md` |
| 4 | `uv run python scripts/fit_panel.py` | `models/panel/` y `reports/panel_sangre.md` |
| 5 | `uv run python scripts/fit_recalibration.py` | Priors para España y `reports/recalibracion_espana.md` |
| 6 | `uv run python scripts/validate_robustness.py` | `reports/robustez.md` |
| 7 | `uv run python scripts/validate_worklist.py` | `reports/lista_cupo.md` |
| 8 | `uv run python scripts/simulate_home.py` | `reports/cribado_en_casa.md` (unos 15 minutos) |
| 9 | `uv run python scripts/validate_trend.py` | `reports/tendencia_fg.md` |
| 10 | `uv run python scripts/fit_outcomes.py` | `models/outcomes/` y `reports/riesgo_en_casa.md` (unos 15 minutos) |
| 11 | `uv run python scripts/fit_heart_home.py` | `models/panel/log_nt_probnp__casa*.joblib` y `reports/insuficiencia_cardiaca.md` |
| 12 | `uv run python scripts/fit_diabetes_home.py` | `models/panel/hba1c__casa.joblib` y `reports/diabetes_en_casa.md` |
| 13 | `uv run python scripts/download_open_data.py` | Electrocardiogramas de PhysioNet y muestra PREDIMED en `data/raw/` (unos 100 MB) |
| 14 | `uv run python scripts/fit_rhythm.py` | `models/ritmo/fa_intervalos.joblib` y `reports/ritmo.md` |
| 15 | `uv run python scripts/validate_predimed.py` | `reports/validacion_espana.md` |

`fit_albuminuria.py --variant <nombre>` ajusta las variantes de la tabla de validación
(`picos_normales`, `sin_covariables_muestra`, `sin_pendiente`, `sin_picos`, `normal`).

## 5. Qué está ajustado con datos y qué es un supuesto

| Pieza | Estado |
|---|---|
| Filtro: prior, tipo de muestra, ruido, elevaciones, dilución | Ajustado y validado con personas reales (NHANES 2009-2010) |
| Filtro: cambio de la albuminuria a meses o años | Supuesto de la literatura |
| Panel virtual de sangre | Ajustado y validado con personas reales (NHANES) |
| SCORE2 y SCORE2-OP | Coeficientes publicados, comprobados contra una implementación abierta |
| Categorías de la guía europea de 2021 | Implementadas según la guía; no se pudo cotejar la tabla original en esta sesión. Conviene que las revise un clínico |
| Lista del cupo | Validada con personas reales: probabilidades calibradas; el orden no mejora a la edad cuando ya hay lípidos |
| FG y albuminuria juntos | Comprobado con personas reales: sin diferencia medible |
| Umbrales | Explícitos como pruebas por caso; curvas de decisión con personas reales |
| Recalibración a España | Prevalencias publicadas de ONDAAS; sin datos individuales |
| Tira: error de lectura | **Supuesto.** Hay que medirlo con muestras pareadas |
| Preguntas de contexto: efecto | **Supuesto.** Se puede estimar con los datos de uso |
| Protocolo en casa | Evaluado solo en simulación |
| Participación por canal | Medida en THOMAS para aplicación y correo; supuesta para el resto |
| Tendencia del FG | **Supuesto** de la literatura; comprobado solo en simulación |
| Riesgo de muerte cardiovascular con datos de casa | Entrenado y validado con desenlaces reales (EE. UU.); el riesgo absoluto está sin recalibrar a España |
| NT-proBNP con síntomas y pulso | Ajustado y validado con personas reales (NHANES 1999-2004) |
| Fibrilación auricular: probabilidad de partida | Medida en España (estudio OFRECE) |
| Detector de fibrilación auricular | Entrenado y validado con 8.528 registros reales de electrocardiógrafo de bolsillo; con cámara, **solo simulado** |
| Diabetes oculta con glucómetro | Validado con personas reales (NHANES); la glucosa es de laboratorio con el error de un glucómetro **simulado** |
| Riesgo cardiovascular en españoles | Comprobado en la muestra PREDIMED (pocas variables, todos de alto riesgo) |
| Lectura continua del color de la tira | **Supuesto**; evaluada solo en simulación. No hay modelo de visión construido |
| Punción capilar y ritmo: errores de medida | **Supuesto** |

Otros límites:

- **Datos de EE. UU. (NHANES), sin ponderar.** No es población de atención primaria española.
- **Las simulaciones son dentro del modelo**: dicen qué pasa si el mundo se comporta como el
  modelo, no si el modelo es correcto.
- **Sin tira multiparamétrica.** NHANES no tiene glucosa, proteínas, sangre ni densidad en orina.
- **Faltan el efecto de los tratamientos sobre la albuminuria** (IECA/ARA-II e iSGLT2 la bajan un
  30-40 %) y el fracaso renal agudo en la tendencia del FG.
- **NT-proBNP con sueros de 1999-2004** y con la historia clínica de entonces.
- **En diabéticos** la guía actual usa SCORE2-Diabetes, que no está implementado.
- **Es apoyo a la decisión, no diagnóstico.** Antes de usarse en pacientes necesita validación
  prospectiva y marcado como producto sanitario; una prueba hecha por el propio paciente añade
  requisitos regulatorios.

## 6. Próximos pasos

1. **Calibrar la tira** con unas 200-300 muestras leídas a la vez con la tira y en el
   laboratorio. Es barato y es el supuesto que más pesa en el circuito de casa.
2. **Datos longitudinales de primaria** (SIDIAP, BIGPAC) para ajustar la tendencia del FG, el
   cambio de la albuminuria en el tiempo y el efecto de los tratamientos.
3. **Corregir la calibración del FG por sexo en mayores de 65 años.**
4. **Estimar el efecto de las preguntas de contexto** con los datos de uso.
5. **SCORE2-Diabetes y el complemento de ERC** para el riesgo cardiovascular, y **recalibrar a
   España el riesgo absoluto** del modelo de casa con las tasas de mortalidad del INE.
6. **Una cohorte con infartos e ictus no mortales y con ecocardiograma.** No se puede descargar
   ninguna: SIDIAP y similares exigen solicitud institucional con protocolo y comité de ética, y
   SHARE (que incluye España) exige registrarse como investigador. Es lo que falta para comparar
   con SCORE2 en lo que SCORE2 predice y para mejorar de verdad la insuficiencia cardíaca.
7. **Lecturas reales de casa**: glucómetros y pulso por cámara en pacientes, para sustituir los
   errores simulados por medidos.
8. **Integración en la historia clínica (FHIR)** e interfaz: aplicación del paciente y lista de la
   médica con petición de pruebas en un clic.
9. **Paso al tratamiento.** El cuarto fallo de la cadena, la inercia terapéutica, sigue sin
   abordar: señalar quién cumple criterios de guía para cada fármaco.
