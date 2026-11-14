# Panel virtual: qué se puede estimar sin analítica de sangre

Generado por `scripts/fit_panel.py`. Datos: NHANES 2009-2018 (analítica, orina e historia clínica, 26762 adultos) y NHANES 1999-2004 (NT-proBNP, 11370 adultos). Modelos entrenados con el 80 % y evaluados en el 20 % restante. Para cada variable el modelo da su distribución completa: mediana, intervalo del 80 % y probabilidad de pasar cada umbral clínico.

- **CRPS**: error de la distribución predicha, en las unidades de la variable (más bajo es mejor). **Mejora frente a la población** = 1 - CRPS / CRPS de predecir la distribución de toda la población.
- **Cobertura 80 %**: proporción de pacientes cuyo valor real cae en el intervalo del 80 % (debe rondar 0,80).
- La orina de NHANES es solo albúmina, creatinina, volumen y flujo: no hay tira reactiva (glucosa, proteínas, sangre, densidad), que en la práctica añadiría información.

## Resumen

AUC de la primera decisión clínica de cada variable según lo que se sabe del paciente.

| Variable | Decisión | Edad y sexo | Historia clínica | Historia clínica y orina | Mejora frente a la población | Cobertura 80 % |
|---|---|---|---|---|---|---|
| FG (ml/min/1,73 m²) | FG < 60 | 0.883 | 0.913 | 0.919 | 37% | 0.841 |
| HbA1c (%) | HbA1c ≥ 6,5 % | 0.708 | 0.923 | 0.927 | 30% | 0.815 |
| Glucosa (mg/dl, sin ayuno) | Glucosa ≥ 126 | 0.678 | 0.850 | 0.860 | 20% | 0.813 |
| Potasio (mmol/l) | Potasio ≥ 5,0 | 0.711 | 0.730 | 0.751 | 5% | 0.791 |
| Colesterol no-HDL (mg/dl) | No-HDL ≥ 190 | 0.659 | 0.757 | 0.758 | 12% | 0.823 |
| Hemoglobina (g/dl) | Anemia (Hb < 13 hombre, < 12 mujer) | 0.701 | 0.755 | 0.759 | 24% | 0.836 |
| log UACR primera orina (mg/g) | UACR ≥ 30 | 0.643 | 0.669 | 0.918 | 32% | 0.831 |
| log NT-proBNP (pg/ml) | NT-proBNP ≥ 125 | 0.876 | 0.895 | 0.896 | 31% | 0.826 |

## FG (ml/min/1,73 m²)

Test: 5067 personas · CRPS sin mirar al paciente: 12.4

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | 0.075 | 0.461 | 0.527 | 0.520 | 0.565 |
| Error absoluto medio | 17.0 | 12.5 | 11.6 | 11.9 | 11.2 |
| CRPS | 11.9 | 8.612 | 8.086 | 8.238 | 7.825 |
| Mejora frente a la población | 0.038 | 0.304 | 0.346 | 0.334 | 0.368 |
| Cobertura 80 % | 0.799 | 0.832 | 0.833 | 0.832 | 0.841 |
| Anchura 80 % | 56.5 | 40.7 | 39.3 | 39.8 | 38.8 |
| FG < 60: AUC | 0.711 | 0.883 | 0.904 | 0.913 | 0.919 |
| FG < 60: Brier | 0.061 | 0.053 | 0.050 | 0.047 | 0.046 |
| FG < 60: prevalencia / media predicha | 7.0% / 7.9% | 7.0% / 7.8% | 7.0% / 7.7% | 7.0% / 7.6% | 7.0% / 7.5% |
| FG < 45: AUC | 0.789 | 0.868 | 0.917 | 0.937 | 0.945 |
| FG < 45: Brier | 0.023 | 0.023 | 0.022 | 0.020 | 0.019 |
| FG < 45: prevalencia / media predicha | 2.6% / 2.9% | 2.6% / 3.0% | 2.6% / 2.8% | 2.6% / 2.7% | 2.6% / 2.6% |
| FG < 60 en diabéticos o hipertensos: AUC | 0.660 | 0.814 | 0.846 | 0.853 | 0.863 |
| FG < 60 en diabéticos o hipertensos: prevalencia / media predicha | 15.2% / 9.9% | 15.2% / 12.7% | 15.2% / 13.4% | 15.2% / 14.6% | 15.2% / 14.6% |

## HbA1c (%)

Test: 5167 personas · CRPS sin mirar al paciente: 0.468

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | 0.046 | 0.046 | 0.102 | 0.413 | 0.434 |
| Error absoluto medio | 0.578 | 0.546 | 0.537 | 0.444 | 0.440 |
| CRPS | 0.445 | 0.429 | 0.413 | 0.333 | 0.328 |
| Mejora frente a la población | 0.049 | 0.082 | 0.118 | 0.288 | 0.298 |
| Cobertura 80 % | 0.786 | 0.794 | 0.796 | 0.810 | 0.815 |
| Anchura 80 % | 1.844 | 1.634 | 1.742 | 1.548 | 1.527 |
| HbA1c ≥ 6,5 %: AUC | 0.699 | 0.708 | 0.768 | 0.923 | 0.927 |
| HbA1c ≥ 6,5 %: Brier | 0.098 | 0.101 | 0.095 | 0.056 | 0.056 |
| HbA1c ≥ 6,5 %: prevalencia / media predicha | 12.1% / 12.4% | 12.1% / 12.5% | 12.1% / 12.4% | 12.1% / 12.1% | 12.1% / 11.9% |
| HbA1c ≥ 5,7 %: AUC | 0.621 | 0.740 | 0.755 | 0.830 | 0.830 |
| HbA1c ≥ 5,7 %: Brier | 0.231 | 0.201 | 0.196 | 0.163 | 0.163 |
| HbA1c ≥ 5,7 %: prevalencia / media predicha | 41.7% / 41.6% | 41.7% / 41.5% | 41.7% / 41.4% | 41.7% / 41.4% | 41.7% / 41.3% |
| HbA1c ≥ 6,5 % en sin diagnóstico de diabetes: AUC | 0.648 | 0.668 | 0.717 | 0.794 | 0.813 |
| HbA1c ≥ 6,5 % en sin diagnóstico de diabetes: prevalencia / media predicha | 3.8% / 11.4% | 3.8% / 11.6% | 3.8% / 10.7% | 3.8% / 3.8% | 3.8% / 3.8% |

## Glucosa (mg/dl, sin ayuno)

Test: 5068 personas · CRPS sin mirar al paciente: 15.5

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | -0.007 | -0.018 | 0.020 | 0.217 | 0.247 |
| Error absoluto medio | 19.0 | 18.5 | 18.3 | 16.6 | 16.5 |
| CRPS | 14.9 | 14.8 | 14.3 | 12.6 | 12.5 |
| Mejora frente a la población | 0.042 | 0.046 | 0.077 | 0.187 | 0.198 |
| Cobertura 80 % | 0.797 | 0.801 | 0.802 | 0.811 | 0.813 |
| Anchura 80 % | 58.3 | 54.0 | 58.2 | 58.1 | 57.6 |
| Glucosa ≥ 126: AUC | 0.690 | 0.678 | 0.742 | 0.850 | 0.860 |
| Glucosa ≥ 126: Brier | 0.097 | 0.100 | 0.095 | 0.074 | 0.073 |
| Glucosa ≥ 126: prevalencia / media predicha | 11.8% / 11.8% | 11.8% / 11.8% | 11.8% / 11.7% | 11.8% / 11.4% | 11.8% / 11.4% |
| Glucosa ≥ 126 en sin diagnóstico de diabetes: AUC | 0.648 | 0.635 | 0.690 | 0.704 | 0.729 |
| Glucosa ≥ 126 en sin diagnóstico de diabetes: prevalencia / media predicha | 5.3% / 10.9% | 5.3% / 11.1% | 5.3% / 10.4% | 5.3% / 5.2% | 5.3% / 5.2% |

## Potasio (mmol/l)

Test: 5067 personas · CRPS sin mirar al paciente: 0.199

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | 0.011 | 0.051 | 0.060 | 0.069 | 0.078 |
| Error absoluto medio | 0.275 | 0.269 | 0.268 | 0.266 | 0.265 |
| CRPS | 0.197 | 0.192 | 0.192 | 0.190 | 0.189 |
| Mejora frente a la población | 0.010 | 0.033 | 0.037 | 0.045 | 0.048 |
| Cobertura 80 % | 0.783 | 0.797 | 0.796 | 0.791 | 0.791 |
| Anchura 80 % | 0.869 | 0.859 | 0.855 | 0.852 | 0.848 |
| Potasio ≥ 5,0: AUC | 0.622 | 0.711 | 0.720 | 0.730 | 0.751 |
| Potasio ≥ 5,0: Brier | 0.012 | 0.012 | 0.012 | 0.012 | 0.012 |
| Potasio ≥ 5,0: prevalencia / media predicha | 1.2% / 1.1% | 1.2% / 1.1% | 1.2% / 1.0% | 1.2% / 1.0% | 1.2% / 1.0% |

## Colesterol no-HDL (mg/dl)

Test: 5087 personas · CRPS sin mirar al paciente: 23.3

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | -0.010 | 0.082 | 0.069 | 0.218 | 0.207 |
| Error absoluto medio | 32.8 | 31.1 | 31.3 | 28.4 | 28.6 |
| CRPS | 23.3 | 22.1 | 22.3 | 20.4 | 20.5 |
| Mejora frente a la población | -0.000 | 0.049 | 0.043 | 0.124 | 0.118 |
| Cobertura 80 % | 0.793 | 0.800 | 0.806 | 0.822 | 0.823 |
| Anchura 80 % | 103.6 | 100.0 | 101.7 | 98.6 | 99.8 |
| No-HDL ≥ 190: AUC | 0.515 | 0.659 | 0.659 | 0.757 | 0.758 |
| No-HDL ≥ 190: Brier | 0.099 | 0.096 | 0.096 | 0.090 | 0.090 |
| No-HDL ≥ 190: prevalencia / media predicha | 11.1% / 11.0% | 11.1% / 11.0% | 11.1% / 11.0% | 11.1% / 11.0% | 11.1% / 11.0% |

## Hemoglobina (g/dl)

Test: 5168 personas · CRPS sin mirar al paciente: 0.857

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | 0.072 | 0.346 | 0.354 | 0.389 | 0.387 |
| Error absoluto medio | 1.146 | 0.936 | 0.933 | 0.904 | 0.907 |
| CRPS | 0.819 | 0.674 | 0.670 | 0.650 | 0.652 |
| Mejora frente a la población | 0.044 | 0.214 | 0.217 | 0.241 | 0.239 |
| Cobertura 80 % | 0.801 | 0.817 | 0.825 | 0.831 | 0.836 |
| Anchura 80 % | 3.652 | 3.055 | 3.127 | 3.066 | 3.100 |
| Anemia (Hb < 13 hombre, < 12 mujer): AUC | 0.487 | 0.701 | 0.727 | 0.755 | 0.759 |
| Anemia (Hb < 13 hombre, < 12 mujer): Brier | 0.095 | 0.083 | 0.081 | 0.079 | 0.079 |
| Anemia (Hb < 13 hombre, < 12 mujer): prevalencia / media predicha | 9.6% / 14.6% | 9.6% / 10.7% | 9.6% / 10.8% | 9.6% / 10.6% | 9.6% / 10.6% |

## log UACR primera orina (mg/g)

Test: 1033 personas · CRPS sin mirar al paciente: 0.462

| Métrica | solo orina | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina |
|---|---|---|---|---|---|
| R² (mediana) | 0.546 | -0.000 | 0.548 | 0.059 | 0.536 |
| Error absoluto medio | 0.424 | 0.598 | 0.424 | 0.588 | 0.426 |
| CRPS | 0.312 | 0.446 | 0.311 | 0.433 | 0.312 |
| Mejora frente a la población | 0.324 | 0.035 | 0.327 | 0.063 | 0.325 |
| Cobertura 80 % | 0.820 | 0.807 | 0.821 | 0.812 | 0.831 |
| Anchura 80 % | 1.474 | 2.032 | 1.471 | 1.960 | 1.500 |
| UACR ≥ 30: AUC | 0.898 | 0.643 | 0.903 | 0.669 | 0.918 |
| UACR ≥ 30: Brier | 0.029 | 0.046 | 0.029 | 0.046 | 0.029 |
| UACR ≥ 30: prevalencia / media predicha | 4.8% / 6.1% | 4.8% / 6.7% | 4.8% / 5.8% | 4.8% / 6.5% | 4.8% / 5.8% |
| UACR ≥ 30 en hipertensos sin diabetes: AUC | 0.900 | 0.649 | 0.911 | 0.528 | 0.906 |
| UACR ≥ 30 en hipertensos sin diabetes: prevalencia / media predicha | 4.2% / 6.0% | 4.2% / 8.5% | 4.2% / 6.1% | 4.2% / 8.2% | 4.2% / 5.9% |

## log NT-proBNP (pg/ml)

Test: 2241 personas · CRPS sin mirar al paciente: 0.740

| Métrica | edad y sexo | edad, sexo y orina | historia clínica | historia clínica y orina | historia, orina y FG |
|---|---|---|---|---|---|
| R² (mediana) | 0.463 | 0.475 | 0.518 | 0.527 | 0.542 |
| Error absoluto medio | 0.744 | 0.740 | 0.709 | 0.709 | 0.698 |
| CRPS | 0.538 | 0.533 | 0.513 | 0.511 | 0.503 |
| Mejora frente a la población | 0.273 | 0.280 | 0.307 | 0.310 | 0.320 |
| Cobertura 80 % | 0.816 | 0.818 | 0.826 | 0.826 | 0.825 |
| Anchura 80 % | 2.573 | 2.535 | 2.544 | 2.527 | 2.493 |
| NT-proBNP ≥ 125: AUC | 0.876 | 0.884 | 0.895 | 0.896 | 0.899 |
| NT-proBNP ≥ 125: Brier | 0.115 | 0.111 | 0.106 | 0.105 | 0.103 |
| NT-proBNP ≥ 125: prevalencia / media predicha | 23.7% / 25.2% | 23.7% / 24.9% | 23.7% / 24.7% | 23.7% / 24.7% | 23.7% / 24.7% |
| NT-proBNP ≥ 300: AUC | 0.881 | 0.891 | 0.908 | 0.911 | 0.914 |
| NT-proBNP ≥ 300: Brier | 0.073 | 0.070 | 0.067 | 0.065 | 0.063 |
| NT-proBNP ≥ 300: prevalencia / media predicha | 11.1% / 10.5% | 11.1% / 10.4% | 11.1% / 10.2% | 11.1% / 10.1% | 11.1% / 10.0% |
| NT-proBNP ≥ 125 en sin diagnóstico de insuficiencia cardíaca: AUC | 0.871 | 0.878 | 0.886 | 0.888 | 0.890 |
| NT-proBNP ≥ 125 en sin diagnóstico de insuficiencia cardíaca: prevalencia / media predicha | 21.6% / 24.0% | 21.6% / 23.6% | 21.6% / 23.1% | 21.6% / 23.0% | 21.6% / 23.0% |
