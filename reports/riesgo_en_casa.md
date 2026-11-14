# Riesgo cardiovascular con lo que se mide en casa

Generado por `scripts/fit_outcomes.py`. Datos: NHANES 1999-2014 enlazado con el registro de defunciones de EE. UU. (seguimiento hasta diciembre de 2019). De 42305 adultos se usan los 34443 que tienen todos los datos de casa: en NHANES un dato vacío suele ser de alguien a quien no se pudo explorar, más frágil, y el modelo no debe aprovecharse de eso. Desenlace: **muerte por enfermedad del corazón o ictus en los 10 años siguientes**.

Evaluación: 12710 personas de 40 años o más de las oleadas 1999-2008 (todas con 10 años de seguimiento), 701 muertes cardiovasculares (5,5 %). Validación cruzada de cinco partes: a cada persona la predice un modelo que no la vio. Entre paréntesis, el intervalo del 95 % por remuestreo.

- **AUC**: probabilidad de que el modelo dé más riesgo a quien muere que a quien no (0,5 es azar; 1, perfecto).
- **AUC dentro de cada oleada**: la misma, calculada oleada a oleada. Descarta que el modelo acierte por reconocer la época y no al paciente.
- **Muertes en el 20 % de más riesgo**: de todas las muertes, cuántas caen en la quinta parte que el modelo señala.

## Qué se gana con cada cosa que hace el paciente

"Historia clínica" es lo que ya consta sin pedir nada: diagnósticos, fármacos, tabaco, peso y cintura. El "cuestionario" son cinco preguntas: salud percibida, falta de aire al subir cuestas, dificultad para caminar 400 metros y para subir 10 escalones, e ingresos en el último año.

| Lo que se usa | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión | AUC dentro de cada oleada | Muertes en el 20 % de más riesgo |
|---|---|---|---|---|---|
| SCORE2 publicado (analítica y consulta) | 0,813 (0,80-0,83) | 0,826 (0,81-0,84) | 0,755 (0,73-0,78) | 0,812 | 62 % |
| Variables de SCORE2, ecuación reajustada | 0,815 (0,80-0,83) | 0,823 (0,80-0,84) | 0,763 (0,74-0,78) | 0,813 | 65 % |
| Edad y sexo | 0,801 (0,78-0,82) | 0,806 (0,78-0,83) | 0,756 (0,73-0,78) | 0,800 | 64 % |
| Historia clínica | 0,837 (0,82-0,85) | 0,832 (0,81-0,85) | 0,795 (0,78-0,81) | 0,836 | 70 % |
| Historia y cuestionario | 0,838 (0,82-0,85) | 0,833 (0,81-0,85) | 0,798 (0,78-0,82) | 0,837 | 70 % |
| Historia, cuestionario y manguito | 0,840 (0,83-0,85) | 0,836 (0,82-0,86) | 0,799 (0,78-0,82) | 0,839 | 69 % |
| Historia, cuestionario, manguito y tira de orina | 0,844 (0,83-0,86) | 0,840 (0,82-0,86) | 0,805 (0,79-0,82) | 0,843 | 70 % |
| Historia, cuestionario, manguito y orina de laboratorio | 0,844 (0,83-0,86) | 0,840 (0,82-0,86) | 0,808 (0,79-0,83) | 0,843 | 69 % |
| Todo lo anterior y analítica de sangre | 0,845 (0,83-0,86) | 0,841 (0,82-0,86) | 0,809 (0,79-0,83) | 0,844 | 70 % |
| Historia, cuestionario, manguito, orina y punción capilar | 0,845 (0,83-0,86) | 0,842 (0,82-0,86) | 0,808 (0,79-0,83) | 0,844 | 70 % |

Diferencias de AUC en las mismas personas (positivo: gana el primero). Si el intervalo no incluye el cero, la diferencia es clara.

| Comparación | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión |
|---|---|---|---|
| Historia clínica − SCORE2 publicado (analítica y consulta) | +0,023 (0,014 a 0,034) | +0,007 (-0,005 a 0,018) | +0,041 (0,024 a 0,059) |
| Historia y cuestionario − Historia clínica | +0,002 (-0,002 a 0,006) | +0,001 (-0,004 a 0,006) | +0,004 (-0,003 a 0,009) |
| Historia y cuestionario − SCORE2 publicado (analítica y consulta) | +0,026 (0,015 a 0,037) | +0,008 (-0,004 a 0,020) | +0,044 (0,027 a 0,062) |
| Historia y cuestionario − Variables de SCORE2, ecuación reajustada | +0,024 (0,014 a 0,033) | +0,010 (0,001 a 0,020) | +0,036 (0,022 a 0,050) |
| Historia, cuestionario, manguito y orina de laboratorio − SCORE2 publicado (analítica y consulta) | +0,031 (0,022 a 0,042) | +0,014 (0,002 a 0,025) | +0,054 (0,039 a 0,070) |
| Historia, cuestionario, manguito y orina de laboratorio − Variables de SCORE2, ecuación reajustada | +0,030 (0,020 a 0,039) | +0,016 (0,007 a 0,028) | +0,046 (0,031 a 0,059) |
| Historia, cuestionario y manguito − Historia y cuestionario | +0,002 (-0,001 a 0,005) | +0,003 (-0,002 a 0,007) | +0,000 (-0,005 a 0,006) |
| Historia, cuestionario, manguito y orina de laboratorio − Historia, cuestionario y manguito | +0,004 (0,000 a 0,008) | +0,003 (-0,002 a 0,009) | +0,009 (0,002 a 0,016) |
| Historia, cuestionario, manguito y tira de orina − Historia, cuestionario y manguito | +0,004 (0,001 a 0,007) | +0,004 (-0,000 a 0,009) | +0,006 (0,002 a 0,011) |
| Todo lo anterior y analítica de sangre − Historia, cuestionario, manguito y orina de laboratorio | +0,001 (-0,002 a 0,003) | +0,001 (-0,002 a 0,004) | +0,001 (-0,003 a 0,005) |
| SCORE2 publicado (analítica y consulta) − Edad y sexo | +0,012 (0,002 a 0,020) | +0,020 (0,008 a 0,033) | -0,002 (-0,016 a 0,012) |

## ¿Es el método o son los datos?

Las mismas variables que usan las ecuaciones de hoy, reajustadas con estos datos. Si el modelo de casa ganara solo por el método, estas filas lo igualarían.

| Lo que se usa | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión | AUC dentro de cada oleada | Muertes en el 20 % de más riesgo |
|---|---|---|---|---|---|
| Variables de SCORE2, ecuación reajustada | 0,815 (0,80-0,83) | 0,823 (0,80-0,84) | 0,763 (0,74-0,78) | 0,813 | 65 % |
| Variables de SCORE2, con el método nuevo | 0,817 (0,80-0,83) | 0,820 (0,80-0,84) | 0,767 (0,74-0,79) | 0,816 | 65 % |
| Variables de PREVENT, con el método nuevo | 0,827 (0,81-0,84) | 0,831 (0,81-0,85) | 0,777 (0,76-0,80) | 0,825 | 67 % |
| Variables de PREVENT con orina y HbA1c, con el método nuevo | 0,834 (0,82-0,85) | 0,836 (0,82-0,85) | 0,793 (0,77-0,81) | 0,833 | 68 % |
| Historia y cuestionario | 0,838 (0,82-0,85) | 0,833 (0,81-0,85) | 0,798 (0,78-0,82) | 0,837 | 70 % |
| Historia, cuestionario, manguito y orina de laboratorio | 0,844 (0,83-0,86) | 0,840 (0,82-0,86) | 0,808 (0,79-0,83) | 0,843 | 69 % |

## Kit mínimo

Los seis datos que más pesan (de la historia, el cuestionario y el manguito), elegidos sin usar la quinta parte reservada: salud percibida (de excelente a mala); insuficiencia cardíaca diagnosticada; toma pastillas para la tensión; fuma; infarto, angina o enfermedad coronaria; tensión sistólica (además de la edad y el sexo).

| Lo que se usa | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión | AUC dentro de cada oleada | Muertes en el 20 % de más riesgo |
|---|---|---|---|---|---|
| Kit mínimo | 0,836 (0,82-0,85) | 0,833 (0,81-0,85) | 0,792 (0,77-0,81) | 0,835 | 68 % |
| Historia y cuestionario | 0,838 (0,82-0,85) | 0,833 (0,81-0,85) | 0,798 (0,78-0,82) | 0,837 | 70 % |
| SCORE2 publicado (analítica y consulta) | 0,813 (0,80-0,83) | 0,826 (0,81-0,84) | 0,755 (0,73-0,78) | 0,812 | 62 % |

En la quinta parte reservada, que no intervino en la elección (2521 personas, 146 muertes): kit mínimo 0,823, historia y cuestionario completos 0,822, SCORE2 0,804.

## Qué pesa en el modelo de casa

Caída de AUC al barajar cada dato (cuanto más cae, más aporta ese dato que no aporten los demás).

| Dato | Caída de AUC |
|---|---|
| Edad | 0,1855 |
| Albúmina en orina (UACR) | 0,0173 |
| Salud percibida (de excelente a mala) | 0,0069 |
| Insuficiencia cardíaca diagnosticada | 0,0044 |
| Fuma | 0,0032 |
| Sexo | 0,0027 |
| Toma pastillas para la tensión | 0,0021 |
| Infarto, angina o enfermedad coronaria | 0,0019 |
| Tensión sistólica | 0,0017 |
| Dificultad para subir 10 escalones | 0,0014 |
| Ictus previo | 0,0010 |
| Peso y talla (IMC) | 0,0008 |

## Calibración del modelo de casa

Riesgo medio predicho 5,5 %, observado 5,5 %. Error cuadrático (Brier) 0,0462; el de SCORE2 es 0,0482, pero SCORE2 predice otra cosa (infarto e ictus, mortales o no, en Europa), así que su valor absoluto no es comparable.

| Décima parte según el riesgo predicho | Personas | Riesgo predicho | Muertes observadas |
|---|---|---|---|
| 1 | 1271 | 0,4 % | 0,3 % |
| 2 | 1271 | 0,6 % | 0,2 % |
| 3 | 1271 | 0,7 % | 0,7 % |
| 4 | 1271 | 1,0 % | 0,9 % |
| 5 | 1271 | 1,5 % | 1,7 % |
| 6 | 1271 | 2,2 % | 2,4 % |
| 7 | 1271 | 3,5 % | 3,8 % |
| 8 | 1271 | 6,1 % | 6,9 % |
| 9 | 1271 | 12,2 % | 12,3 % |
| 10 | 1271 | 26,5 % | 25,9 % |

## Con todo el seguimiento (1999-2014)

Índice de concordancia con censura en las 21490 personas de 40 años o más de todas las oleadas (1526 muertes cardiovasculares, con hasta 20 años de seguimiento).

| Lo que se usa | Índice de concordancia |
|---|---|
| SCORE2 publicado (analítica y consulta) | 0,823 |
| Variables de SCORE2, ecuación reajustada | 0,825 |
| Edad y sexo | 0,808 |
| Historia clínica | 0,845 |
| Historia y cuestionario | 0,848 |
| Historia, cuestionario, manguito y orina de laboratorio | 0,853 |

## El modelo que se usa: sirve con lo que haya

En el producto hay un solo modelo, entrenado con bloques de datos borrados al azar (cuestionario, peso y cintura, manguito, orina). Si el paciente aún no ha aportado algo, estima con el resto. En la quinta parte reservada (2521 personas, 146 muertes), frente al modelo entrenado solo para ese caso:

| Datos disponibles | AUC del modelo único | AUC del modelo específico |
|---|---|---|
| Con todo | 0,827 | 0,831 |
| Sin orina | 0,827 | 0,828 |
| Sin orina ni manguito | 0,829 | 0,822 |
| Sin cuestionario | 0,825 | - |
| Sin cuestionario, manguito ni orina | 0,828 | 0,829 |

Con solo la edad y el sexo, 0,799; SCORE2, 0,804.

## Límites

- **Población de EE. UU.** El orden de los pacientes debería trasladarse; el riesgo absoluto no (en España se muere menos del corazón). Antes de dar porcentajes a un paciente español hay que recalibrar.
- **Solo muertes.** El fichero público no tiene infartos ni ictus no mortales, que es lo que SCORE2 pretende predecir. La comparación es sobre quién muere, no sobre quién enferma.
- **SCORE2 no está pensado para quien ya tiene enfermedad cardiovascular.** Por eso se da también la columna sin enfermedad previa, que es la comparación justa.
- **Cuestionario hecho por un entrevistador**, no por el paciente en su móvil; y tensión y pulso tomados por personal entrenado, no en casa.
- **La orina es una muestra aleatoria única medida en el laboratorio.** La fila de la tira simula su lectura con un error supuesto.
- En los ficheros públicos de mortalidad, el tiempo o la causa de algunos registros están sustituidos por valores sintéticos para proteger la identidad.
