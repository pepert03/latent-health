# Señal de insuficiencia cardíaca en el pulso en reposo

Generado por `scripts/fit_pulse_hf.py`. Datos: dos bases abiertas de PhysioNet con los latidos de 24 horas de 29 personas con insuficiencia cardíaca ([chf2db](https://physionet.org/content/chf2db/1.0.0/), clases I a III de la NYHA, 58 años de mediana) y 54 en ritmo sinusal normal ([nsr2db](https://physionet.org/content/nsr2db/1.0.0/), 65 años de mediana). Solo traen el instante de cada latido, que es justo lo que da un sensor de pulso.

De cada persona se toman 48 tramos repartidos por el registro, como medidas sueltas del pulso. El modelo usa las 17 medidas de irregularidad del detector de fibrilación auricular y cinco más (frecuencia, variación absoluta y capacidad de aceleración y deceleración). Validación cruzada de cinco partes por persona. No usa la edad: aquí los sanos son mayores que los enfermos, así que la edad no puede explicar la diferencia.

## Resultados

| Entrada | AUC con una medida | Sensibilidad (especificidad 90 %) | AUC con siete medidas | Sensibilidad con siete |
|---|---|---|---|---|
| Una medida de 1 min | 0,823 | 61 % | 0,893 | 82 % |
| Una medida de 2 min | 0,829 | 65 % | 0,888 | 82 % |
| Una medida de 5 min | 0,835 | 68 % | 0,886 | 82 % |
| 2 min, latidos degradados como los de una cámara (simulado) | 0,813 | 59 % | 0,890 | 77 % |
| 2 min, entrenado con ECG y usado con cámara (simulado) | 0,684 | 24 % | 0,785 | 40 % |
| 2 min, solo la frecuencia cardíaca | 0,705 | 30 % | 0,752 | 48 % |
| 2 min, frecuencia y variación (SDNN) | 0,709 | 31 % | 0,785 | 50 % |

- **Repetir la medida ayuda**: un rato de pulso rápido y plano no dice mucho; que lo sea todos los días, sí.
- **Las filas de cámara son simuladas** (20 ms de imprecisión y un 3 % de latidos perdidos).
- La variación clásica (SDNN) no separa en tramos cortos: las extrasístoles de los enfermos la inflan. Lo que separa es la frecuencia, la falta de deceleraciones y el patrón de los cambios de un latido al siguiente.

### Por gravedad y con edades parecidas (media de siete medidas)

| Grupo | Con insuficiencia cardíaca | Sanos | AUC |
|---|---|---|---|
| Clase I de la NYHA | 4 | 54 | 0,853 |
| Clase II | 8 | 54 | 0,902 |
| Clase III | 17 | 54 | 0,889 |
| Solo personas de 50 a 75 años | 21 | 45 | 0,871 |

### Medianas de una medida de dos minutos

| Grupo | Frecuencia (lpm) | SDNN (ms) | RMSSD (ms) | Capacidad de deceleración (ms) | pNN50 |
|---|---|---|---|---|---|
| Sanos | 76 | 40 | 23 | 6,1 | 3 % |
| Insuficiencia cardíaca | 87 | 38 | 40 | 2,5 | 4 % |

## Comprobación en pacientes españoles (MUSIC)

MUSIC no trae los latidos, pero sí el resumen del Holter de 24 horas de sus pacientes en ritmo sinusal. Se calcula el mismo resumen en las dos bases de PhysioNet, se entrena una regla con cuatro números (intervalo medio, SDNN, RMSSD y pNN50) y se aplica a los pacientes españoles. En las bases de PhysioNet esa regla tiene AUC 0,890 y señala al 86 % de los enfermos con especificidad del 90 %.

| Grupo | Personas | Intervalo medio (ms) | SDNN de 24 h (ms) | RMSSD (ms) |
|---|---|---|---|---|
| Sanos (nsr2db) | 54 | 780 | 139 | 28 |
| Insuficiencia cardíaca, años 90 (chf2db) | 29 | 689 | 78 | 39 |
| Insuficiencia cardíaca, España 2003-2004 (MUSIC) | 587 | 857 | 106 | 26 |

| Pacientes españoles con insuficiencia cardíaca | Pacientes | Señalados por la regla |
|---|---|---|
| Todos (ritmo sinusal, con Holter analizado) | 587 | 22 % |
| Con betabloqueante | 415 | 19 % |
| Sin betabloqueante | 172 | 30 % |
| Clase funcional II | 487 | 20 % |
| Clase funcional III | 100 | 36 % |
| Fracción de eyección ≤ 40 % | 428 | 23 % |
| Fracción de eyección > 40 % | 157 | 20 % |
| Murieron en el seguimiento | 143 | 33 % |
| Siguieron vivos | 444 | 19 % |

Los pacientes españoles, tratados en su mayoría con betabloqueantes, tienen el pulso más lento y con más variación que los de los años noventa: la regla del pulso los señala menos. Es la advertencia principal de este detector.

## Límites

- **83 personas.** Los intervalos de confianza son anchos y cualquier cifra puede moverse varios puntos.
- **Los controles están sanos.** En atención primaria la comparación real es con personas mayores con hipertensión, diabetes o EPOC, que también tienen el pulso menos variable. La especificidad real será menor.
- **Los enfermos son de los años noventa**, antes de que los betabloqueantes fueran tratamiento habitual. La comprobación con MUSIC lo cuantifica.
- **Los tramos salen de un registro de 24 horas**, con sueño y actividad mezclados; no son medidas en reposo sentado.
- Por todo esto el resultado entra en la ficha con la razón de verosimilitud limitada a lo que se vio en los pacientes españoles: como mucho multiplica la odds por 2,2 o la deja en 0,86 veces. Nunca decide solo.
