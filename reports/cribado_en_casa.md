# Cribado de la albuminuria en casa: simulación del protocolo

Generado por `scripts/simulate_home.py`. 1500 personas simuladas con las covariables reales de NHANES 2009-2010 (60 años o más, o con diabetes). Albuminuria verdadera (UACR ≥ 30 mg/g) en el 10,1 %. Cada política se prueba con las mismas mañanas de cada persona.

- **VPP**: de las personas señaladas como positivas, cuántas tienen albuminuria de verdad.
- **Positivos reales detectados**: de las que tienen albuminuria, cuántas quedan señaladas (a falta de la repetición a los tres meses que exige la cronicidad).
- **Sin resolver**: terminan el kit con duda y pasan al centro de salud.

## Reglas habituales con tiras

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Una tira positiva (móvil) | 59 % | 91 % | 9,3 % | 0,0 % | 1,00 | 0,00 |
| Dos de tres tiras positivas (móvil) | 67 % | 94 % | 6,0 % | 0,0 % | 3,00 | 0,00 |
| Una tira positiva (a ojo) | 52 % | 95 % | 5,3 % | 0,0 % | 1,00 | 0,00 |
| Dos de tres tiras positivas (a ojo) | 66 % | 97 % | 3,3 % | 0,0 % | 3,00 | 0,00 |

## Filtro con el protocolo en dos etapas

El kit trae 3 tiras y permite hasta 2 tubos para el laboratorio. Se pasa al tubo cuando se acaban las tiras o cuando una tira más resolvería la duda con probabilidad menor del 30 %.

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Tiras con el móvil y tubo si hay duda | 98 % | 81 % | 4,0 % | 3,1 % | 1,17 | 0,13 |
| Solo tiras con el móvil (hasta 6, sin tubo) | 98 % | 78 % | 6,0 % | 3,5 % | 1,39 | 0,00 |
| Tira de 3 categorías y tubo si hay duda | 98 % | 85 % | 8,6 % | 1,8 % | 1,08 | 0,13 |
| Tiras leídas a ojo y tubo si hay duda | 97 % | 82 % | 4,0 % | 3,1 % | 1,19 | 0,15 |
| Solo tubo por correo (hasta 2) | 99 % | 73 % | 2,6 % | 5,6 % | 0,00 | 1,11 |

## Umbral de descarte

Las tiras dejan escapar albuminurias cercanas a 30 mg/g: con una tira negativa la probabilidad baja del 5 % y el protocolo termina. El umbral es una decisión de utilidad (`decision.Utilities`): si no dejar escapar una albuminuria vale 50 pruebas en vez de 20, se descarta solo por debajo del 2 %.

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Descartar por debajo del 5 % (por defecto) | 98 % | 81 % | 4,0 % | 3,1 % | 1,17 | 0,13 |
| Descartar por debajo del 2 % | 98 % | 81 % | 4,0 % | 4,1 % | 1,27 | 0,17 |

## Leer el color en continuo con un modelo de visión

El color de cada almohadilla cambia de forma gradual con la concentración; los 4 o 5 niveles son para el ojo. Un modelo de visión podría leer el tono en continuo. Aquí se simula como una tira con muchos niveles dentro del mismo rango químico (la almohadilla sigue saturando fuera de 10-150 mg/l), primero con el mismo error de lectura que la foto de hoy y después con la mitad.

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Niveles de la tira leídos con el móvil (hoy) | 98 % | 81 % | 4,0 % | 3,1 % | 1,17 | 0,13 |
| Color leído en continuo, mismo error de lectura | 98 % | 83 % | 4,6 % | 3,1 % | 1,18 | 0,12 |
| Color leído en continuo, mitad de error | 99 % | 85 % | 4,0 % | 2,7 % | 1,16 | 0,10 |
| Referencia: tubo al laboratorio | 99 % | 73 % | 2,6 % | 5,6 % | 0,00 | 1,11 |

## Preguntas de contexto antes de la prueba

En el mundo simulado, el ejercicio intenso, la fiebre, la regla y los síntomas de infección multiplican la probabilidad de una elevación transitoria (efectos supuestos; ver `albuminuria/context.py`). Sin preguntas, el filtro no sabe qué mañanas tienen una causa. Con preguntas, la prueba se aplaza esas mañanas y el filtro sabe que las que se hacen no la tienen.

| Política | VPP | Positivos reales detectados | Positivos reales descartados | Sin resolver | Tiras por persona | Tubos por persona |
|---|---|---|---|---|---|---|
| Sin preguntas | 98 % | 81 % | 4,0 % | 3,1 % | 1,17 | 0,13 |
| Con preguntas | 98 % | 81 % | 5,3 % | 3,0 % | 1,16 | 0,14 |

Días hasta terminar (media): 1,30 sin preguntas y 1,94 con ellas (aplazar cuesta días).

## Rendimiento por canal, por cada 1.000 personas invitadas

Combina la participación de cada canal con lo que detecta el protocolo entre quienes participan.

| Canal | Participación | Albuminurias detectadas | Falsos positivos | Tiras usadas | Tubos al laboratorio |
|---|---|---|---|---|---|
| Aplicación: tiras con el móvil y tubo | 44 % (medida en THOMAS) | 36 | 0,89 | 518 | 58 |
| Carta o farmacia: tiras a ojo y tubo | 45 % (supuesta) | 37 | 1,20 | 536 | 69 |
| Correo: solo tubo | 59 % (medida en THOMAS) | 44 | 0,40 | 0 | 658 |

## Límites

- Es una simulación dentro del modelo: supone que el modelo de medida ajustado en NHANES es correcto y que las mañanas de una persona son independientes entre sí dado su nivel verdadero.
- El error de lectura de las tiras (móvil, a ojo, cociente) es un supuesto. Hay que medirlo con muestras leídas a la vez con la tira y en el laboratorio (`fit_strip_spec`).
- El efecto de las preguntas de contexto es un supuesto; la tabla dice cuánto se ganaría si fuera ese.
- No simula la repetición a los tres meses ni el abandono a mitad del kit.
