# Fracción de eyección baja con ECG de una derivación y sonido cardíaco

Generado por `scripts/fit_ejection.py`. Datos: [Zenodo 16934966](https://zenodo.org/records/16934966) (CC-BY 4.0), del artículo de Ma y colaboradores en *Patterns* (2026). 500 personas del hospital Tongji de Wuhan, 60 con fracción de eyección del 40 % o menos medida por ecocardiograma (y 107 por debajo del 50 %), y 120 de un segundo hospital (5 con fracción de eyección baja). Cada persona tiene cuatro grabaciones de 30 segundos, una por foco de auscultación, con un Eko DUO: un aparato de mano que recoge a la vez un ECG de una derivación y el sonido del corazón.

Es el primer conjunto del proyecto con **ecocardiograma como verdad y personas sin la enfermedad** de la misma consulta. Los que no tienen la fracción de eyección baja no están sanos: pueden tener valvulopatías, arritmias o miocardiopatías.

## Qué se mide

- **Pulso** (22 medidas): los intervalos entre latidos. Es lo que da la cámara del móvil, un reloj o un pulsioxímetro.
- **ECG** (13 medidas y el latido promedio en 32 puntos): anchura, voltaje y pendiente del QRS, onda T, segmento ST.
- **Sonido** (19 medidas y el sonido promedio en 16 tramos de tres bandas): el fonocardiograma promediado latido a latido usando el QRS como reloj. Da cuánto tarda el primer ruido, cuánto dura la sístole, la fuerza relativa de los dos ruidos y la energía entre ellos y después.

Añadir el latido y el sonido promedios completos a las medidas resumidas sube el AUC unas dos centésimas: las medidas con nombre recogen casi toda la señal, pero no toda.

Un modelo por nivel (árboles con refuerzo de gradiente, poco profundos). La validación cruzada usa las cinco partes por persona que publican los autores. La puntuación de una persona es la media de sus cuatro grabaciones.

## Resultados en validación cruzada (500 personas)

| Lo que se usa | AUC (cuatro grabaciones) | Intervalo 95 % | AUC con una sola grabación | Sensibilidad con especificidad 90 % | Sensibilidad con especificidad 80 % | AUC con un modelo lineal |
|---|---|---|---|---|---|---|
| Solo la frecuencia cardíaca | 0,682 | 0,60-0,76 |  | 32 % | 58 % |  |
| Pulso: intervalos entre latidos | 0,682 | 0,60-0,76 | 0,660 | 35 % | 48 % | 0,675 |
| ECG de una derivación | 0,883 | 0,83-0,93 | 0,826 | 68 % | 80 % | 0,851 |
| ECG y sonido cardíaco | 0,911 | 0,87-0,94 | 0,867 | 70 % | 83 % | 0,866 |

- El ECG añade 0,202 de AUC al pulso (intervalo del 95 %: 0,142 a 0,266).
- El sonido añade 0,027 al ECG (-0,008 a 0,063).
- Con ECG y sonido, la puntuación sigue a la fracción de eyección medida (correlación de rangos -0,46).
- Grabaciones descartadas por no tener 8 latidos válidos: 0 de 2480.

### Cuántos se señalan según la fracción de eyección

Con ECG y sonido y el umbral de especificidad 90 %:

| Fracción de eyección | Personas | Señaladas |
|---|---|---|
| 0 % a 30 % | 33 | 88 % |
| 30 % a 40 % | 27 | 48 % |
| 40 % a 50 % | 53 | 36 % |
| 50 % a 60 % | 118 | 8 % |
| 60 % a 100 % | 269 | 6 % |

### Por foco, con una sola grabación (ECG y sonido)

| Foco | AUC |
|---|---|
| APEX | 0,873 |
| LLSB | 0,877 |
| LUSB | 0,873 |
| RUSB | 0,843 |

### Las medidas que más separan por sí solas

Media de los cuatro focos. "Más alta" quiere decir más alta en quien tiene la fracción de eyección baja.

| Medida | Grupo | AUC | En fracción de eyección baja | Mediana con FE baja | Mediana sin ella |
|---|---|---|---|---|---|
| Pendiente del QRS | ECG | 0,81 | más baja | 44,260 | 50,419 |
| Energía grave antes del primer ruido | Sonido | 0,77 | más alta | -1,441 | -2,010 |
| Fuerza del primer ruido | Sonido | 0,77 | más baja | 1,418 | 2,146 |
| Retraso del primer ruido como parte del latido | Sonido | 0,76 | más alta | 0,054 | 0,033 |
| Parte aguda del primer ruido | Sonido | 0,76 | más alta | 0,196 | 0,138 |
| Retraso del primer ruido frente a la sístole | Sonido | 0,75 | más alta | 0,144 | 0,091 |
| Retraso del primer ruido tras el QRS | Sonido | 0,74 | más alta | 0,045 | 0,028 |
| Primer ruido frente al segundo | Sonido | 0,71 | más baja | -0,477 | 0,101 |
| Fuerza de los ruidos frente al fondo | Sonido | 0,70 | más baja | 1,865 | 2,148 |
| Duración de la sístole (primer a segundo ruido) | Sonido | 0,69 | más baja | 0,289 | 0,320 |
| Voltaje del QRS | ECG | 0,69 | más alta | 8,958 | 8,631 |
| Intervalo medio entre latidos | Pulso | 0,69 | más baja | 0,725 | 0,861 |

## Prueba en el segundo hospital (120 personas)

Modelos entrenados con las 500 personas del primer hospital y umbral fijado antes de mirar estas.

| Lo que se usa | AUC | Intervalo 95 % | Casos detectados | Sin la enfermedad bien descartados |
|---|---|---|---|---|
| Pulso: intervalos entre latidos | 0,715 | 0,51-0,91 | 0 de 5 | 107 de 115 (93 %) |
| ECG de una derivación | 0,981 | 0,95-1,00 | 5 de 5 | 107 de 115 (93 %) |
| ECG y sonido cardíaco | 0,977 | 0,94-1,00 | 5 de 5 | 101 de 115 (88 %) |

Son solo 5 casos: el intervalo es muy ancho y la sensibilidad no se puede afirmar.

## Qué significa un resultado positivo

Con la sensibilidad (70 %) y la especificidad (90 %) de la validación cruzada, según a quién se le haga:

| A quién | Señalados | De los señalados, con FE baja | De los no señalados, con FE baja |
|---|---|---|---|
| Mayores de 65 años sin síntomas (2 %) | 11 % | 13 % | 0,7 % |
| Diabetes o hipertensión de años (5 %) | 13 % | 27 % | 1,7 % |
| Consulta por ahogo o hinchazón (12 %) | 17 % | 49 % | 4,3 % |

Las prevalencias son órdenes de magnitud, no datos del proyecto. Sirve sobre todo para descartar y para ordenar la lista de ecocardiogramas, no para diagnosticar.

## Límites

- **Pacientes de un hospital chino**, no de atención primaria española. Los autores no publican edad ni sexo por persona, así que no se puede ajustar ni comprobar por grupos.
- **Pocos casos**: 60 en el conjunto principal y 5 en el segundo hospital.
- **Solo fracción de eyección reducida.** La mitad de la insuficiencia cardíaca tiene la fracción de eyección conservada y aquí cuenta como "sin la enfermedad".
- **El aparato lo usó personal sanitario** sobre el pecho. No se sabe cómo queda la grabación si se la hace el paciente, ni con el micrófono de un móvil. El nivel de pulso sí se puede tomar con la cámara, pero aquí sale del ECG.
- **No se compara con el modelo de los autores** (una red profunda sobre la señal entera): no se ha podido leer el artículo. Estas medidas son deliberadamente simples y explicables.
