# Insuficiencia cardíaca en pacientes españoles: qué se ve desde casa

Generado por `scripts/validate_music.py`. Datos: tabla clínica de [MUSIC](https://physionet.org/content/music-sudden-cardiac-death/1.0.1/) (PhysioNet, licencia ODbL): 992 pacientes ambulatorios con insuficiencia cardíaca sintomática de ocho hospitales universitarios españoles (Murcia, Las Palmas, Madrid, Tarragona, Santiago, Barcelona, Mallorca y Sevilla), incluidos en 2003-2004 y seguidos una mediana de 4,9 años. Murieron 266: 111 por fallo de bomba, 94 de muerte súbita y 61 por causas no cardíacas.

Edad mediana 67 años, 72 % hombres, 22 % en clase funcional III, 72 % con fracción de eyección del 40 % o menos, 68 % con betabloqueante. Solo el 8 % tenía el NT-proBNP por debajo de 125 ng/l, el umbral con el que hoy se descarta la enfermedad.

**Todos tienen la enfermedad**, así que esta cohorte no sirve para detectarla. Sirve para saber cuánto de su gravedad se ve con lo que el paciente puede medir en casa, y para comprobar en pacientes españoles lo aprendido con otros datos.

## 1. ¿Quién muere en 3 años?

De 962 pacientes con seguimiento suficiente murieron 221 (23 %). Validación cruzada de cinco partes. Las medidas de casa son cuatro: cómo de pronto se cansa (clase funcional), el peso, la tensión y el pulso (frecuencia y si es irregular).

| Lo que se usa | Datos | AUC (modelo lineal) | Intervalo 95 % | AUC (árboles) | Concordancia con todo el seguimiento |
|---|---|---|---|---|---|
| Edad y sexo | 2 | 0,629 | 0,58-0,67 | 0,610 | 0,609 |
| Historia clínica | 17 | 0,733 | 0,70-0,77 | 0,721 | 0,697 |
| Historia y medidas de casa | 23 | 0,757 | 0,72-0,79 | 0,741 | 0,714 |
| Lo anterior y ECG | 27 | 0,754 | 0,72-0,79 | 0,744 | 0,714 |
| Lo anterior y analítica | 37 | 0,764 | 0,73-0,79 | 0,760 | 0,720 |
| Todo, con ecocardiograma y Holter | 47 | 0,778 | 0,74-0,81 | 0,778 | 0,735 |

- Las medidas de casa añaden 0,024 de AUC a la historia clínica (intervalo del 95 %: 0,001 a 0,047).
- La analítica, con el NT-proBNP, añade 0,007 a lo de casa (-0,012 a 0,026).
- Todo lo del hospital junto añade 0,021 a lo de casa (-0,005 a 0,046).

Solo muerte cardíaca (súbita o por fallo de bomba):

| Lo que se usa | Datos | AUC (modelo lineal) | Intervalo 95 % | AUC (árboles) |
|---|---|---|---|---|
| Edad y sexo | 2 | 0,606 | 0,56-0,65 | 0,576 |
| Historia clínica | 17 | 0,722 | 0,68-0,76 | 0,701 |
| Historia y medidas de casa | 23 | 0,736 | 0,70-0,77 | 0,710 |
| Lo anterior y ECG | 27 | 0,731 | 0,69-0,77 | 0,717 |
| Lo anterior y analítica | 37 | 0,742 | 0,70-0,78 | 0,751 |
| Todo, con ecocardiograma y Holter | 47 | 0,768 | 0,73-0,80 | 0,755 |

### Ordenando a los pacientes con la historia y las medidas de casa

| Grupo | Pacientes | Mueren en 3 años | Parte de todas las muertes |
|---|---|---|---|
| Tercio de más riesgo | 321 | 44 % | 64 % |
| Tercio intermedio | 321 | 16 % | 23 % |
| Tercio de menos riesgo | 320 | 9 % | 13 % |

### Cada medida de casa por separado

| Medida | AUC | En quien muere | Mediana en quien muere | Mediana en quien vive |
|---|---|---|---|---|
| Edad | 0,64 | más alta | 70,0 | 65,0 |
| Clase funcional III (se cansa con poco) | 0,61 | más alta | 2,0 | 2,0 |
| Índice de masa corporal | 0,61 | más baja | 26,8 | 28,7 |
| Tensión sistólica | 0,54 | más baja | 120,0 | 128,0 |
| Tensión diastólica | 0,52 | más baja | 70,0 | 75,0 |
| Frecuencia cardíaca en reposo | 0,58 | más alta | 72,0 | 69,0 |
| Pulso irregular (fibrilación auricular) | 0,57 | más alta | 0,0 | 0,0 |

## 2. ¿Quién tiene el NT-proBNP por encima de 1.000 ng/l?

Lo tenía el 44 % de los 870 pacientes con el dato. Es un valor claramente alto: en consulta la enfermedad se descarta por debajo de 125.

| Lo que se usa | Datos | AUC (modelo lineal) | Intervalo 95 % | AUC (árboles) |
|---|---|---|---|---|
| Edad y sexo | 2 | 0,640 | 0,60-0,68 | 0,621 |
| Historia clínica | 17 | 0,700 | 0,66-0,73 | 0,683 |
| Historia y medidas de casa | 23 | 0,745 | 0,71-0,78 | 0,743 |
| Lo anterior y ECG | 27 | 0,746 | 0,71-0,78 | 0,748 |

Las medidas de casa añaden 0,044 a la historia (0,022 a 0,067).

## 3. ¿Quién tiene la fracción de eyección reducida?

Entre pacientes que ya tienen insuficiencia cardíaca, 73 % tienen la fracción de eyección del 40 % o menos. Aquí no hay señal del ECG, solo los números que da el aparato.

| Lo que se usa | Datos | AUC (modelo lineal) | Intervalo 95 % | AUC (árboles) |
|---|---|---|---|---|
| Edad y sexo | 2 | 0,587 | 0,55-0,63 | 0,575 |
| Pulso (frecuencia e irregularidad) | 4 | 0,602 | 0,56-0,65 | 0,580 |
| Números del ECG (QRS, QT, PR, ondas Q) | 8 | 0,694 | 0,66-0,73 | 0,675 |
| ECG, historia y medidas de casa | 27 | 0,756 | 0,72-0,79 | 0,749 |

La anchura del QRS sola separa con AUC 0,64: más ancho con fracción de eyección reducida, la misma dirección que en los datos de Wuhan (`reports/fraccion_eyeccion.md`).

## Límites

- **Pacientes de consultas de insuficiencia cardíaca de hospital, de 2003-2004.** Hoy se tratan con fármacos que entonces no había (sacubitrilo-valsartán, inhibidores de SGLT2), y los de primaria son mayores y con más fracción de eyección conservada.
- **Las "medidas de casa" las tomó personal sanitario** en la visita. La clase funcional la puso un cardiólogo; en casa saldría de preguntas y sería menos fina.
- **Es pronóstico, no diagnóstico.** Dice a quién vigilar más entre los ya diagnosticados.
- No se compara con la escala de riesgo publicada del estudio (necesita ecocardiograma, Holter y analítica); la última fila de la primera tabla hace de referencia de "todo lo que midió el hospital".
