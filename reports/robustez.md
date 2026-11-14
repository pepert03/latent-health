# Robustez

Generado por `scripts/validate_robustness.py` con la partición de test de NHANES (personas que los modelos no vieron al ajustarse). Modelos sin recalibrar a España, porque la referencia es NHANES.

## 1. Filtrado glomerular y albuminuria juntos

979 personas de test de NHANES 2009-2010. El sistema recibe la historia clínica y la muestra de orina aleatoria, sin la analítica de sangre. Hay 63 personas con FG < 60, 47 con albuminuria, 6 con las dos cosas y 27 de riesgo KDIGO alto o muy alto: con tan pocos casos conjuntos, diferencias pequeñas entre filas no significan nada. Se compara lo que predice con el FG real y con la primera orina de la mañana de esa persona (una sola muestra, así que como referencia de la albuminuria tiene ruido; afecta por igual a las tres formas de combinar).

Pérdida logarítmica de cada suceso (más baja es mejor):

| Cómo se combinan | FG < 60 y albuminuria | Riesgo KDIGO alto o muy alto | FG < 60 o albuminuria | FG < 60 | AUC del riesgo alto |
|---|---|---|---|---|---|
| Independientes (como antes) | 0,014 | 0,067 | 0,226 | 0,160 | 0,942 |
| Panel con orina × filtro por categoría de FG | 0,015 | 0,070 | 0,226 | 0,159 | 0,942 |
| Panel sin orina, actualizado por la orina (Bayes) | 0,018 | 0,071 | 0,227 | 0,161 | 0,938 |

Proporción observada frente a la media predicha:

| Cómo se combinan | Ambos: observado | predicho | Riesgo alto: observado | predicho | FG < 60: observado | predicho |
|---|---|---|---|---|---|---|
| Independientes (como antes) | 0,6 % | 1,1 % | 2,8 % | 3,1 % | 6,4 % | 7,2 % |
| Panel con orina × filtro por categoría de FG | 0,6 % | 1,2 % | 2,8 % | 3,0 % | 6,4 % | 7,1 % |
| Panel sin orina, actualizado por la orina (Bayes) | 0,6 % | 1,4 % | 2,8 % | 3,2 % | 6,4 % | 6,7 % |

## 2. Calibración por sexo y edad

Para cada grupo, la proporción real del suceso frente a la probabilidad media que da el modelo. Se marca "desviado" si la diferencia pasa de dos errores típicos y de dos puntos porcentuales.

| Suceso | Sexo | Edad | n | Observado | Predicho | Calibración |
|---|---|---|---|---|---|---|
| Primera orina ≥ 30 dada la aleatoria | Hombres | < 50 | 224 | 3,1 % | 2,2 % | bien |
| Primera orina ≥ 30 dada la aleatoria | Hombres | 50-64 | 129 | 4,7 % | 7,8 % | bien |
| Primera orina ≥ 30 dada la aleatoria | Hombres | ≥ 65 | 109 | 8,3 % | 12,1 % | desviado |
| Primera orina ≥ 30 dada la aleatoria | Mujeres | < 50 | 268 | 2,6 % | 2,9 % | bien |
| Primera orina ≥ 30 dada la aleatoria | Mujeres | 50-64 | 137 | 4,4 % | 4,5 % | bien |
| Primera orina ≥ 30 dada la aleatoria | Mujeres | ≥ 65 | 109 | 10,1 % | 9,8 % | bien |
| FG < 60 (historia y orina) | Hombres | < 50 | 1227 | 0,3 % | 0,9 % | bien |
| FG < 60 (historia y orina) | Hombres | 50-64 | 671 | 5,1 % | 5,6 % | bien |
| FG < 60 (historia y orina) | Hombres | ≥ 65 | 573 | 20,1 % | 24,3 % | desviado |
| FG < 60 (historia y orina) | Mujeres | < 50 | 1318 | 0,2 % | 0,7 % | bien |
| FG < 60 (historia y orina) | Mujeres | 50-64 | 677 | 5,8 % | 5,4 % | bien |
| FG < 60 (historia y orina) | Mujeres | ≥ 65 | 601 | 27,0 % | 24,8 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Hombres | < 50 | 1177 | 1,9 % | 1,9 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Hombres | 50-64 | 549 | 6,0 % | 5,7 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Hombres | ≥ 65 | 429 | 7,7 % | 6,2 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Mujeres | < 50 | 1277 | 2,2 % | 1,9 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Mujeres | 50-64 | 556 | 4,7 % | 5,6 % | bien |
| HbA1c ≥ 6,5 % sin diagnóstico de diabetes | Mujeres | ≥ 65 | 486 | 6,0 % | 6,9 % | bien |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Hombres | < 50 | 551 | 0,7 % | 4,0 % | desviado |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Hombres | 50-64 | 240 | 13,8 % | 16,2 % | bien |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Hombres | ≥ 65 | 274 | 50,0 % | 53,2 % | bien |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Mujeres | < 50 | 541 | 7,8 % | 9,1 % | bien |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Mujeres | 50-64 | 236 | 24,6 % | 26,8 % | bien |
| NT-proBNP ≥ 125 sin insuficiencia cardíaca | Mujeres | ≥ 65 | 311 | 61,1 % | 56,4 % | bien |

Grupos desviados: 3 de 24.

## 3. Umbrales por utilidad clínica

Un umbral de probabilidad equivale a aceptar un número de pruebas por caso encontrado (5 % = 20 pruebas). Para cada umbral: a qué proporción de personas se le pediría la prueba, qué proporción de los casos se encontraría, el beneficio neto del modelo frente a la mejor alternativa simple (pedirla a todos o a nadie) y cuántas pruebas ahorra el modelo por cada 100 personas sin perder beneficio. Modelos de historia clínica, sin orina, en la partición de test.

| Decisión | Umbral | Pruebas por caso | Se pide a | Casos encontrados | Beneficio neto | Mejor alternativa | Pruebas ahorradas por 100 |
|---|---|---|---|---|---|---|---|
| Pedir creatinina por P(FG < 60) | 2 % | 50 | 45 % | 99 % | 0,0617 | 0,0515 | 50 |
| Pedir creatinina por P(FG < 60) | 5 % (elegido) | 20 | 31 % | 92 % | 0,0523 | 0,0215 | 58 |
| Pedir creatinina por P(FG < 60) | 10 % | 10 | 22 % | 85 % | 0,0419 | 0,0000 | 38 |
| Pedir creatinina por P(FG < 60) | 20 % | 5 | 13 % | 71 % | 0,0285 | 0,0000 | 11 |
| Pedir HbA1c por P(≥ 6,5 %) sin diagnóstico | 2 % | 50 | 54 % | 89 % | 0,0238 | 0,0186 | 26 |
| Pedir HbA1c por P(≥ 6,5 %) sin diagnóstico | 5 % (elegido) | 20 | 21 % | 61 % | 0,0134 | 0,0000 | 26 |
| Pedir HbA1c por P(≥ 6,5 %) sin diagnóstico | 10 % | 10 | 7 % | 31 % | 0,0051 | 0,0000 | 5 |
| Pedir HbA1c por P(≥ 6,5 %) sin diagnóstico | 20 % | 5 | 2 % | 15 % | 0,0019 | 0,0000 | 1 |
| Pedir NT-proBNP por P(≥ 125) | 10 % | 10 | 54 % | 94 % | 0,1655 | 0,1283 | 33 |
| Pedir NT-proBNP por P(≥ 125) | 20 % | 5 | 39 % | 86 % | 0,1353 | 0,0194 | 46 |
| Pedir NT-proBNP por P(≥ 125) | 30 % (elegido) | 3 | 29 % | 77 % | 0,1121 | 0,0000 | 26 |
| Pedir NT-proBNP por P(≥ 125) | 40 % | 2 | 22 % | 67 % | 0,0935 | 0,0000 | 14 |
| Pedir la orina por P(albuminuria) con la historia | 2 % | 50 | 97 % | 100 % | 0,0296 | 0,0290 | 3 |
| Pedir la orina por P(albuminuria) con la historia | 5 % (elegido) | 20 | 41 % | 62 % | 0,0101 | 0,0000 | 19 |
| Pedir la orina por P(albuminuria) con la historia | 10 % | 10 | 15 % | 34 % | 0,0018 | 0,0000 | 2 |
| Pedir la orina por P(albuminuria) con la historia | 20 % | 5 | 5 % | 18 % | -0,0015 | 0,0000 | -1 |
