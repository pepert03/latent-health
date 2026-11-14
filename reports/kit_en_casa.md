# Kit de casa: qué se pierde al quitar cada pieza

Generado por `scripts/fit_kit.py`. Mismos datos, personas y desenlace que `reports/riesgo_en_casa.md`: 12710 personas de 40 años o más de NHANES 1999-2008, 701 muertes por enfermedad del corazón o ictus en 10 años. Validación cruzada de cinco partes: a cada persona la predice un modelo que no la vio.

La pregunta es si el kit puede llevar menos cosas **sin ordenar peor el riesgo**. La tira es la del proyecto (albúmina y creatinina, leída con el móvil, con su error simulado).

## AUC con cada combinación

| Lo que se usa | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión | Muertes en el 20 % de más riesgo |
|---|---|---|---|---|
| Kit completo: historia, cinco preguntas, manguito y tira | 0,844 | 0,840 | 0,805 | 70 % |
| Kit de todos: historia, cinco preguntas y tira (sin manguito) | 0,844 | 0,840 | 0,807 | 70 % |
| Historia y tira (sin preguntas ni manguito) | 0,841 | 0,837 | 0,801 | 69 % |
| Historia y cinco preguntas (sin tira ni manguito) | 0,838 | 0,833 | 0,798 | 70 % |
| Solo la historia clínica | 0,837 | 0,832 | 0,795 | 70 % |

## Diferencia con el kit completo

En las mismas personas, con su intervalo del 95 % por remuestreo. Si el intervalo incluye el cero, quitar esas piezas no cambia el orden del riesgo de forma medible.

| Lo que se usa, menos el kit completo | Todos | Sin enfermedad cardiovascular previa | Con diabetes o hipertensión |
|---|---|---|---|
| Kit de todos: historia, cinco preguntas y tira (sin manguito) | +0,000 (-0,003 a 0,003) | -0,000 (-0,004 a 0,004) | +0,002 (-0,003 a 0,006) |
| Historia y tira (sin preguntas ni manguito) | -0,004 (-0,008 a 0,000) | -0,003 (-0,010 a 0,003) | -0,004 (-0,010 a 0,002) |
| Historia y cinco preguntas (sin tira ni manguito) | -0,006 (-0,010 a -0,002) | -0,007 (-0,013 a -0,000) | -0,007 (-0,014 a -0,000) |
| Solo la historia clínica | -0,008 (-0,013 a -0,002) | -0,008 (-0,016 a 0,001) | -0,011 (-0,020 a -0,002) |

## Cómo leerlo

- Esto mide **el orden del riesgo**, no el diagnóstico. El manguito sigue siendo la forma de diagnosticar la hipertensión en casa y el glucómetro la de encontrar la diabetes oculta (`reports/diabetes_en_casa.md`): se prestan a quien su ficha se lo pide, no a todos.
- Las cinco preguntas no cuestan nada, así que se mantienen aunque su aportación sea pequeña.
- Población de EE. UU., tensión tomada por personal entrenado y orina de laboratorio con el error de la tira simulado: los mismos límites que `reports/riesgo_en_casa.md`.
