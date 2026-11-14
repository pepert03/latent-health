# Validación del filtro de albuminuria (NHANES 2009-2010)

Generado por `scripts/validate_albuminuria.py`. Modelo ajustado solo con la partición de entrenamiento (4437 personas); aquí se evalúa en las 976 personas de test con las dos muestras (aleatoria en el centro y primera orina de la mañana en casa).

## Parámetros ajustados

- Exceso de la muestra aleatoria sobre la primera de la mañana (sin elevación): x1.23 a 3 mg/g, x1.36 a 10 mg/g, x1.49 a 30 mg/g, x1.65 a 100 mg/g, x1.81 a 300 mg/g.
- Variación habitual por muestra (escala log, t de Student con ν = 8.7): primera de la mañana 0.274, aleatoria 0.302.
- Elevaciones transitorias (hombre de 50 años sin diabetes, FG 90, orina de dilución típica): 15% de las muestras aleatorias y 7% de las primeras de la mañana, de x2.1 de media (ω = 0.61 en log). Efectos en el logit: edad/15 años +0.11, mujer +0.81, diabetes +0.01, FG/20 -0.04, dilución (log creatinina en orina) -0.14.
- Efectos en la escala de la variación (log, por unidad): edad/15 años -0.04, mujer -0.11, diabetes +0.09, FG/20 -0.09, dilución -0.19.
- Log-verosimilitud por persona en test (más alto es mejor): completo -1.785, elevaciones de cola ligera -1.789, sin covariables de muestra -1.798, sin exceso creciente -1.802, sin elevaciones -1.825, ruido normal -1.931.
- Dinámica (no se ajusta con estos datos): cambio verdadero de 0.35 en log por año (≈ ±42%).

## Resultados

### Dada la muestra aleatoria, ¿saldrá la primera orina de la mañana ≥ 30?
Personas de test con las dos muestras: 976; la primera orina de la mañana sale ≥ 30 en el 4.7%.

| Predicción | AUC | Brier | log-loss |
|---|---|---|---|
| Completo | 0.918 | 0.027 | 0.102 |
| Elevaciones de cola ligera | 0.919 | 0.028 | 0.104 |
| Sin covariables de muestra | 0.916 | 0.027 | 0.104 |
| Sin exceso creciente | 0.916 | 0.028 | 0.105 |
| Sin elevaciones | 0.914 | 0.028 | 0.106 |
| Ruido normal | 0.917 | 0.029 | 0.131 |
| Regresión logística (entrenada para esto) | 0.911 | 0.027 | 0.107 |
| Tabla empírica por tramos | 0.910 | 0.028 | 0.117 |

Regla habitual (un positivo es positivo): Brier 0.067; de 97 positivos, 58 (60%) no se repiten; de 879 negativos, 7 (0.8%) salen positivos en la otra muestra.

Calibración por tramos de la muestra aleatoria (probabilidad media predicha frente a lo observado):

| Tramo (mg/g) | n | Observado | Completo | Elevaciones de cola ligera | Sin covariables de muestra | Sin exceso creciente | Sin elevaciones | Ruido normal | Logística |
|---|---|---|---|---|---|---|---|---|---|
| <10 | 674 | 1% | 1% | 1% | 1% | 1% | 0% | 0% | 1% |
| 10-20 | 157 | 1% | 3% | 3% | 3% | 3% | 2% | 2% | 4% |
| 20-30 | 48 | 2% | 7% | 7% | 7% | 8% | 8% | 10% | 9% |
| 30-50 | 40 | 20% | 18% | 17% | 17% | 21% | 24% | 24% | 18% |
| 50-100 | 24 | 42% | 41% | 39% | 39% | 42% | 52% | 51% | 35% |
| 100-300 | 20 | 45% | 57% | 54% | 54% | 55% | 66% | 81% | 61% |
| 300-1000 | 9 | 100% | 92% | 94% | 94% | 95% | 93% | 99% | 92% |
| ≥1000 | 4 | 75% | 92% | 98% | 99% | 98% | 90% | 100% | 99% |

### Dada la primera orina de la mañana, ¿saldrá la muestra aleatoria ≥ 30?
Personas de test con las dos muestras: 976; la muestra aleatoria sale ≥ 30 en el 9.9%.

| Predicción | AUC | Brier | log-loss |
|---|---|---|---|
| Completo | 0.909 | 0.051 | 0.183 |
| Elevaciones de cola ligera | 0.908 | 0.051 | 0.184 |
| Sin covariables de muestra | 0.905 | 0.051 | 0.185 |
| Sin exceso creciente | 0.905 | 0.051 | 0.186 |
| Sin elevaciones | 0.907 | 0.050 | 0.185 |
| Ruido normal | 0.909 | 0.050 | 0.185 |
| Regresión logística (entrenada para esto) | 0.897 | 0.050 | 0.185 |
| Tabla empírica por tramos | 0.857 | 0.053 | 0.197 |

Regla habitual (un positivo es positivo): Brier 0.067; de 46 positivos, 7 (15%) no se repiten; de 930 negativos, 58 (6.2%) salen positivos en la otra muestra.

Calibración por tramos de la primera orina de la mañana (probabilidad media predicha frente a lo observado):

| Tramo (mg/g) | n | Observado | Completo | Elevaciones de cola ligera | Sin covariables de muestra | Sin exceso creciente | Sin elevaciones | Ruido normal | Logística |
|---|---|---|---|---|---|---|---|---|---|
| <10 | 789 | 3% | 3% | 3% | 3% | 3% | 2% | 1% | 3% |
| 10-20 | 99 | 19% | 18% | 18% | 18% | 16% | 15% | 20% | 19% |
| 20-30 | 42 | 43% | 47% | 47% | 47% | 42% | 46% | 48% | 40% |
| 30-50 | 17 | 71% | 62% | 60% | 62% | 59% | 66% | 65% | 58% |
| 50-100 | 13 | 85% | 68% | 63% | 64% | 64% | 79% | 88% | 75% |
| 100-300 | 9 | 100% | 82% | 83% | 84% | 84% | 88% | 99% | 92% |
| 300-1000 | 5 | 100% | 98% | 99% | 99% | 99% | 98% | 100% | 99% |
| ≥1000 | 2 | 100% | 100% | 100% | 100% | 100% | 99% | 100% | 100% |

### Decisión tras una sola muestra aleatoria
P = probabilidad de que el UACR verdadero (primera orina de la mañana) sea ≥ 30.

| Estado del filtro | Personas | Mañana ≥ 30 observado | Mañana ≥ 30 esperado por el modelo |
|---|---|---|---|
| Descartada (P ≤ 5%) | 893 (91%) | 1.0% | 1.6% |
| Dudosa | 73 (7%) | 38.4% | 39.8% |
| Muy probable (P ≥ 95%) | 10 (1%) | 90.0% | 97.1% |

### Comprobación predictiva (modelo completo)
Simulación de 200 réplicas de estas 976 personas con sus covariables.

| Estadístico | Observado | Simulado (media) | Simulado (90 %) |
|---|---|---|---|
| Aleatoria ≥ 30 | 9.9% | 10.4% | 8.8%-12.0% |
| Primera de la mañana ≥ 30 | 4.7% | 6.3% | 5.0%-7.6% |
| Ambas ≥ 30 | 4.0% | 5.0% | 4.0%-5.9% |
| A2 en aleatoria que siguen A2 | 32.1% | 36.4% | 28.4%-44.3% |
| Confirma con aleatoria 30-50 | 20.0% | 17.9% | 8.0%-28.2% |
| Confirma con aleatoria 50-100 | 41.7% | 40.6% | 23.8%-57.9% |
| Confirma con aleatoria 100-300 | 45.0% | 72.9% | 53.8%-88.2% |
| Confirma con aleatoria ≥300 | 92.3% | 93.6% | 83.3%-100.0% |

### Comprobación predictiva (sin elevaciones transitorias)
Simulación de 200 réplicas de estas 976 personas con sus covariables.

| Estadístico | Observado | Simulado (media) | Simulado (90 %) |
|---|---|---|---|
| Aleatoria ≥ 30 | 9.9% | 9.4% | 8.1%-10.9% |
| Primera de la mañana ≥ 30 | 4.7% | 6.2% | 4.9%-7.4% |
| Ambas ≥ 30 | 4.0% | 5.2% | 4.1%-6.5% |
| A2 en aleatoria que siguen A2 | 32.1% | 44.8% | 34.7%-52.3% |
| Confirma con aleatoria 30-50 | 20.0% | 23.9% | 12.0%-33.4% |
| Confirma con aleatoria 50-100 | 41.7% | 54.7% | 39.1%-71.5% |
| Confirma con aleatoria 100-300 | 45.0% | 82.4% | 66.7%-94.7% |
| Confirma con aleatoria ≥300 | 92.3% | 91.7% | 80.0%-100.0% |

### Comprobación predictiva (modelo completo, sobre los datos de entrenamiento)
Simulación de 200 réplicas de estas 3962 personas con sus covariables.

| Estadístico | Observado | Simulado (media) | Simulado (90 %) |
|---|---|---|---|
| Aleatoria ≥ 30 | 10.7% | 11.1% | 10.2%-11.8% |
| Primera de la mañana ≥ 30 | 6.9% | 6.8% | 6.2%-7.4% |
| Ambas ≥ 30 | 5.4% | 5.5% | 4.9%-6.1% |
| A2 en aleatoria que siguen A2 | 41.5% | 37.8% | 34.6%-41.7% |
| Confirma con aleatoria 30-50 | 17.6% | 18.6% | 13.7%-23.6% |
| Confirma con aleatoria 50-100 | 43.0% | 42.5% | 36.0%-50.0% |
| Confirma con aleatoria 100-300 | 74.5% | 73.4% | 65.9%-80.2% |
| Confirma con aleatoria ≥300 | 87.7% | 93.4% | 88.6%-97.4% |
