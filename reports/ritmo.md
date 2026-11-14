# Detector de fibrilación auricular por intervalos entre latidos

Generado por `scripts/fit_rhythm.py`. Datos: PhysioNet/CinC Challenge 2017, 8528 registros de 9 a 60 segundos de un electrocardiógrafo de bolsillo de una derivación, etiquetados por expertos: ritmo normal 5076, fibrilación auricular 758, otro ritmo 2415, ruido 279. Validación cruzada de cinco partes.

El detector no mira la forma de la onda: detecta cada latido y mide lo irregulares que son los intervalos entre ellos (17 medidas). Así sirve con cualquier cosa que marque el latido, incluida la cámara del móvil. El umbral se fija para una especificidad del 95 % en los datos de entrenamiento de cada parte.

## Resultados

| Entrada | AUC frente a todo lo demás | AUC frente a ritmo normal | Sensibilidad | Especificidad | Normales señalados | "Otro ritmo" señalados |
|---|---|---|---|---|---|---|
| Latidos del electrocardiograma | 0,971 | 0,988 | 87,5 % | 93,8 % | 1,8 % | 13,0 % |
| Latidos degradados como los de una cámara (simulado) | 0,957 | 0,979 | 83,1 % | 93,5 % | 2,1 % | 13,3 % |
| Entrenado con electrocardiograma, usado con cámara (simulado) | 0,941 | 0,962 | 90,5 % | 80,0 % | 12,9 % | 32,8 % |
| Regla simple: variación de los intervalos | 0,751 | 0,823 | 5,4 % | 95,0 % | 2,2 % | 6,1 % |

Registros con menos de 8 intervalos válidos, en los que el detector no opina: 0 (0,0 %).

- **"Otro ritmo" señalados** es el coste real: extrasístoles y otras arritmias también dan un pulso irregular, y con los intervalos solos no siempre se distinguen. No son sanos: también conviene que los vea un médico.
- **Las filas de cámara son simuladas**: los mismos latidos con 20 ms de imprecisión y un 3 % perdidos. No hay registros de cámara etiquetados en abierto para comprobarlo de verdad.

## Qué significa cada resultado del detector

Fibrilación auricular observada según la probabilidad que da el detector, y cuánto multiplica la odds de partida (razón de verosimilitud). Es lo que usa la ficha del paciente para actualizar su probabilidad.

| Probabilidad del detector | Registros | Media predicha | Fibrilación observada | Razón de verosimilitud |
|---|---|---|---|---|
| 0 % a 2 % | 6429 | 0,3 % | 0,4 % | 0,0 |
| 2 % a 10 % | 891 | 4,6 % | 7,3 % | 0,8 |
| 10 % a 30 % | 396 | 17,6 % | 19,9 % | 2,6 |
| 30 % a 70 % | 295 | 47,9 % | 44,7 % | 8,3 |
| 70 % a 100 % | 517 | 88,5 % | 88,0 % | 75,2 |

## Límites

- **No es la población del cribado.** Son registros de gente que usaba el aparato, con un 9 % de fibrilación; en el cribado de mayores de 65 años es del 1-2 % sin diagnosticar. Por eso la ficha no usa la probabilidad tal cual: la convierte en razón de verosimilitud y la aplica a la prevalencia española por edad y sexo.
- **Registros cortos y de un solo momento.** La fibrilación paroxística puede no estar presente ese rato.
- **Los mejores métodos del reto usan la forma de la onda** y redes profundas; este usa solo intervalos para poder funcionar con la cámara. No pretende superarlos.
- No se sabe si hay varios registros de una misma persona; si los hay, la validación cruzada es algo optimista.
