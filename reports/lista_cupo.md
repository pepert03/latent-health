# Lista del cupo: validación con personas reales

Generado por `scripts/validate_worklist.py`. Personas de 40 años o más de la partición de test de NHANES 2009-2010, con la primera orina de la mañana como referencia de la albuminuria (una sola muestra: tiene ruido). Modelos sin recalibrar a España, porque la referencia es NHANES.

El sistema recibe la historia clínica y dice qué probabilidad hay de que completar las pruebas dé un hallazgo nuevo. La lista ordena por esa probabilidad.

## A. Con lípidos y tensión conocidos; faltan la orina y la creatinina

660 personas. Tienen un hallazgo nuevo el 15,9 % (105 personas): enfermedad renal que no consta el 13,2 %, diabetes sin diagnosticar el 3,2 % y subida de categoría de riesgo el 1,2 %. Probabilidad media que da el modelo: 15,6 %.

| Orden de la lista | AUC | Aciertos en el primer 10 % | Casos que recoge | Aciertos en el primer 20 % | Casos que recoge |
|---|---|---|---|---|---|
| Lista del modelo (probabilidad de hallazgo nuevo) | 0,75 | 47 % | 30 % | 37 % | 47 % |
| Por edad, de mayor a menor | 0,73 | 48 % | 30 % | 36 % | 46 % |
| Por SCORE2, de mayor a menor | 0,75 | 48 % | 30 % | 37 % | 47 % |
| Al azar | 0,50 | 18 % | 11 % | 18 % | 23 % |

Calibración de la probabilidad de hallazgo nuevo:

| Probabilidad del modelo | Personas | Media predicha | Observado |
|---|---|---|---|
| 0 % a 5 % | 144 | 3,3 % | 3,5 % |
| 5 % a 10 % | 167 | 7,2 % | 9,0 % |
| 10 % a 20 % | 165 | 14,3 % | 13,3 % |
| 20 % a 40 % | 136 | 28,5 % | 27,2 % |
| 40 % a 60 % | 44 | 48,6 % | 52,3 % |
| 60 % a 100 % | 4 | 64,9 % | 75,0 % |

## B. Sin ninguna analítica

660 personas. Tienen un hallazgo nuevo el 20,8 % (137 personas): enfermedad renal que no consta el 13,2 %, diabetes sin diagnosticar el 3,2 % y subida de categoría de riesgo el 6,4 %. Probabilidad media que da el modelo: 19,1 %.

| Orden de la lista | AUC | Aciertos en el primer 10 % | Casos que recoge | Aciertos en el primer 20 % | Casos que recoge |
|---|---|---|---|---|---|
| Lista del modelo (probabilidad de hallazgo nuevo) | 0,73 | 53 % | 26 % | 42 % | 41 % |
| Por edad, de mayor a menor | 0,62 | 50 % | 24 % | 37 % | 36 % |
| Por SCORE2, de mayor a menor | 0,69 | 50 % | 24 % | 39 % | 37 % |
| Al azar | 0,50 | 26 % | 12 % | 27 % | 26 % |

Calibración de la probabilidad de hallazgo nuevo:

| Probabilidad del modelo | Personas | Media predicha | Observado |
|---|---|---|---|
| 0 % a 5 % | 116 | 3,2 % | 3,4 % |
| 5 % a 10 % | 124 | 7,3 % | 11,3 % |
| 10 % a 20 % | 173 | 14,3 % | 18,5 % |
| 20 % a 40 % | 167 | 28,5 % | 28,1 % |
| 40 % a 60 % | 70 | 49,4 % | 47,1 % |
| 60 % a 100 % | 10 | 63,6 % | 70,0 % |

Solo la subida de categoría de riesgo (42 personas): AUC de su probabilidad, 0,90; media predicha 5,5 %, observada 6,4 %.

## Límites

- Población general de EE. UU., no un cupo español; pocas personas, así que las cifras del primer 10 % tienen mucho margen de error.
- En la situación B el SCORE2 se aproxima con lípidos típicos; lo que consta es esa aproximación.
- La referencia de la albuminuria es una sola muestra de la mañana, sin confirmar a los tres meses.
