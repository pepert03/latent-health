# Validación externa en españoles: muestra del ensayo PREDIMED

Generado por `scripts/validate_predimed.py`. 6324 participantes del ensayo PREDIMED (el 85 % del ensayo, elegido al azar; atención primaria española, 2003-2010), todos de alto riesgo cardiovascular y sin enfermedad cardiovascular al entrar. Edad media 67 años, 58 % mujeres, 47 % con diabetes. En 4,4 años de seguimiento medio hubo 252 infartos, ictus o muertes cardiovasculares.

El modelo se entrena con muertes cardiovasculares en EE. UU. (NHANES 1999-2014, 17848 personas de 45 años o más sin enfermedad cardiovascular previa) usando solo lo que PREDIMED también tiene: edad, sexo, tabaco, peso, cintura y diagnósticos de diabetes, hipertensión y colesterol. PREDIMED no interviene en el entrenamiento.

Índice de concordancia (probabilidad de dar más riesgo a quien tiene el evento antes), con su intervalo del 95 %:

| Modelo | Índice de concordancia en PREDIMED |
|---|---|
| Edad y sexo (entrenado en EE. UU.) | 0,631 (0,59-0,67) |
| Historia (entrenado en EE. UU.) | 0,662 (0,63-0,69) |
| Edad y sexo (entrenado en PREDIMED) | 0,627 (0,59-0,66) |
| Historia (entrenado en PREDIMED) | 0,649 (0,62-0,68) |

- Lo que añade la historia a la edad y el sexo, con el modelo de EE. UU.: +0,030 (0,011 a 0,051).
- Lo que se gana entrenando dentro de PREDIMED en vez de traer el modelo de EE. UU.: -0,013 (-0,043 a 0,015).

Eventos según el riesgo que da el modelo entrenado en EE. UU.:

| Quinta parte según el riesgo predicho | Personas | Eventos | Eventos por 1.000 personas y año |
|---|---|---|---|
| 1 | 1265 | 29 | 5,3 |
| 2 | 1265 | 19 | 3,4 |
| 3 | 1265 | 40 | 7,2 |
| 4 | 1265 | 62 | 11,1 |
| 5 | 1264 | 102 | 19,0 |

## Cómo leerlo

- **Todos los índices son bajos, y es lo esperable.** PREDIMED solo admitió a personas de alto riesgo (diabetes o tres factores de riesgo) de 55 a 80 años: al parecerse tanto entre sí, a cualquier modelo le cuesta ordenarlas.
- **Faltan los datos que más pesaban**: no hay orina, ni tensión, ni fármacos, ni enfermedad cardíaca previa (excluida por diseño). Esta validación solo dice si lo poco que comparten se traslada a españoles.
- El desenlace incluye infartos e ictus no mortales, que el modelo nunca vio al entrenarse.
- Es un ensayo con una intervención (dieta mediterránea) que redujo los eventos en dos de las tres ramas.
