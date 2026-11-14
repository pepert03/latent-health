# Diabetes sin diagnosticar: glucómetro en casa frente a FINDRISC

Generado por `scripts/fit_diabetes_home.py`. Datos: NHANES 2005-2018, 27300 adultos sin diabetes diagnosticada ni tratamiento y con todos los datos. Referencia: HbA1c ≥ 6,5 %, que tienen 865 (3,2 %). Validación cruzada de cinco partes; entre paréntesis, el intervalo del 95 %.

La glucosa es la de laboratorio con el error de un glucómetro doméstico (norma ISO 15197: desviación del 7,5 %). La mitad de las personas (50 %) estaba en ayunas de 8 horas o más; el modelo recibe también cuántas horas llevaba sin comer.

## Capacidad de encontrar la diabetes oculta (AUC)

| Lo que se usa | Todos | En ayunas (8 horas o más) | Sin ayunas |
|---|---|---|---|
| FINDRISC (cuestionario que se usa hoy) | 0,754 (0,74-0,77) | 0,759 (0,74-0,78) | 0,749 (0,73-0,77) |
| Historia clínica | 0,785 (0,77-0,80) | 0,783 (0,76-0,80) | 0,787 (0,77-0,81) |
| Historia y orina | 0,811 (0,80-0,82) | 0,813 (0,79-0,83) | 0,809 (0,79-0,83) |
| Solo el glucómetro | 0,896 (0,88-0,91) | 0,932 (0,92-0,95) | 0,849 (0,83-0,87) |
| Historia y glucómetro | 0,920 (0,91-0,93) | 0,943 (0,93-0,95) | 0,894 (0,88-0,91) |
| Historia, orina y glucómetro | 0,920 (0,91-0,93) | 0,944 (0,93-0,95) | 0,893 (0,88-0,91) |

| Diferencia de AUC en las mismas personas | Todos | En ayunas (8 horas o más) | Sin ayunas |
|---|---|---|---|
| Historia, orina y glucómetro − FINDRISC (cuestionario que se usa hoy) | +0,166 (0,151 a 0,180) | +0,184 (0,165 a 0,204) | +0,145 (0,123 a 0,165) |
| Historia clínica − FINDRISC (cuestionario que se usa hoy) | +0,032 (0,020 a 0,044) | +0,024 (0,002 a 0,043) | +0,038 (0,021 a 0,056) |
| Historia y orina − Historia clínica | +0,025 (0,018 a 0,033) | +0,030 (0,020 a 0,042) | +0,022 (0,011 a 0,032) |
| Historia, orina y glucómetro − Historia y orina | +0,109 (0,097 a 0,121) | +0,130 (0,115 a 0,147) | +0,084 (0,068 a 0,103) |
| Historia, orina y glucómetro − Solo el glucómetro | +0,024 (0,018 a 0,031) | +0,011 (0,005 a 0,017) | +0,045 (0,032 a 0,057) |

## Con el mismo esfuerzo que FINDRISC

FINDRISC señala a quien pasa de un corte para hacerle el análisis. Señalando a la misma cantidad de gente, cuánta diabetes oculta se encuentra (sensibilidad) y qué parte de los señalados la tiene (VPP).

| Criterio | Personas señaladas | Diabetes oculta encontrada | VPP |
|---|---|---|---|
| FINDRISC ≥ 15 | 22 % | 52 % | 7,6 % |
| Historia y orina, señalando a los mismos | 22 % | 64 % | 9,4 % |
| Historia, orina y glucómetro, señalando a los mismos | 22 % | 86 % | 12,6 % |
| Historia, orina y glucómetro, en ayunas | 22 % | 92 % | 12,8 % |
| FINDRISC ≥ 12 | 39 % | 76 % | 6,1 % |
| Historia y orina, señalando a los mismos | 39 % | 84 % | 6,8 % |
| Historia, orina y glucómetro, señalando a los mismos | 39 % | 95 % | 7,7 % |
| Historia, orina y glucómetro, en ayunas | 39 % | 98 % | 7,5 % |

Personas a las que hay que hacer el análisis para encontrar el 80 % y el 90 % de la diabetes oculta:

| Lo que se usa | Para encontrar el 80 % | Para encontrar el 90 % |
|---|---|---|
| FINDRISC (cuestionario que se usa hoy) | 44 % | 57 % |
| Historia clínica | 40 % | 55 % |
| Historia y orina | 34 % | 48 % |
| Solo el glucómetro | 19 % | 36 % |
| Historia y glucómetro | 16 % | 26 % |
| Historia, orina y glucómetro | 16 % | 27 % |

## El circuito en dos pasos: a quién se le mide la glucosa

En el producto la glucosa capilar no se le mide a todos. Se le mide a quien la historia clínica deja con una probabilidad de diabetes oculta del 2 % o más, y después se pide el análisis a quien, ya con su glucosa, sigue en el 2 % o más. Como basta una medida, se hace en la farmacia más cercana o con el glucómetro del paciente, si lo tiene. Los porcentajes son sobre todas las personas sin diagnóstico.

| Criterio | Se miden la glucosa | Diabetes oculta entre ellos | Se les pide el análisis | Diabetes oculta encontrada | VPP del análisis | Medidas de glucosa por caso encontrado |
|---|---|---|---|---|---|---|
| FINDRISC ≥ 15 y análisis directo, sin medir la glucosa | - | - | 22 % | 52 % | 7,6 % | - |
| Glucosa a todos | 100 % | 100 % | 22 % | 87 % | 12,3 % | 36 |
| Glucosa si la historia da 2 % o más (el producto) | 46 % | 85 % | 20 % | 75 % | 12,2 % | 20 |
| Glucosa si la historia y la orina dan 2 % o más | 41 % | 85 % | 19 % | 76 % | 12,9 % | 17 |
| Glucosa si la historia da 5 % o más | 19 % | 56 % | 11 % | 52 % | 14,4 % | 11 |

Cuánto se encuentra depende sobre todo del umbral del análisis. Con la glucosa medida como en el producto:

| Se pide el análisis si la probabilidad, ya con la glucosa, es al menos | Se les pide el análisis | Diabetes oculta encontrada | VPP del análisis |
|---|---|---|---|
| 5 % | 10 % | 63 % | 20,0 % |
| 3 % | 15 % | 70 % | 15,2 % |
| 2 % (el producto) | 20 % | 75 % | 12,2 % |
| 1 % | 30 % | 82 % | 8,7 % |

## ¿Una medida o varias?

- **Todas las cifras de este informe son con una sola medida por persona.**
- Con esa medida, al 58 % de quienes se la hacen el sistema les contesta que ya está; al resto se le pide el análisis.
- **Repetir para promediar el error del aparato apenas añade.** Con un glucómetro sin error, que es el techo de repetir muchas veces, la AUC pasa de 0,920 a 0,931 (+0,011; intervalo 0,007 a 0,015).
- **Lo que no se puede medir aquí** es si repetirla en días distintos añade algo más, porque la glucosa de una persona cambia de un día a otro y NHANES tiene una sola por persona.
- En el producto, una glucosa en ayunas de 126 mg/dl o más se repite otro día: con dos días sale como hallazgo, que es lo que exige el criterio diagnóstico.

## Regla simple con el glucómetro

Entre las 13620 personas en ayunas, sin modelo: solo el número del glucómetro.

| Regla | Personas señaladas | Diabetes oculta encontrada | Especificidad | VPP |
|---|---|---|---|---|
| Glucosa en ayunas ≥ 100 mg/dl | 31 % | 93 % | 71 % | 9,2 % |
| Glucosa en ayunas ≥ 110 mg/dl | 13 % | 84 % | 89 % | 19,2 % |
| Glucosa en ayunas ≥ 126 mg/dl | 4 % | 62 % | 98 % | 46,0 % |

## Calibración

Probabilidad de HbA1c ≥ 6,5 % que da el modelo con historia, orina y glucómetro, frente a lo observado.

| Probabilidad del modelo | Personas | Media predicha | Observado |
|---|---|---|---|
| 0 % a 1 % | 17580 | 0,4 % | 0,3 % |
| 1 % a 3 % | 5247 | 1,7 % | 2,2 % |
| 3 % a 10 % | 2851 | 5,4 % | 6,3 % |
| 10 % a 30 % | 1068 | 16,7 % | 16,2 % |
| 30 % a 60 % | 345 | 41,8 % | 46,7 % |
| 60 % a 100 % | 209 | 81,6 % | 88,0 % |

## El modelo que se usa en la ficha del paciente

Un solo modelo estima la HbA1c de cualquier adulto y sirve con o sin glucosa de casa y con o sin orina (se entrena borrando esos bloques al azar). En la quinta parte reservada (5464 personas sin diagnóstico, 183 con diabetes oculta):

| Datos disponibles | AUC |
|---|---|
| Con glucosa en ayunas y orina | 0,931 |
| Con glucosa sin ayunas y orina | 0,909 |
| Con glucosa, sin orina | 0,918 |
| Sin glucosa, con orina | 0,810 |
| Sin glucosa ni orina | 0,787 |

## Límites

- **No es un hallazgo nuevo que la glucosa detecte la diabetes**: la glucosa en ayunas es uno de sus criterios diagnósticos. Lo que se mide aquí es cuánto se gana frente a lo que hoy se usa para cribar sin análisis.
- **Glucosa de laboratorio con error simulado**, no lecturas reales de glucómetros en casa. La sangre capilar y la venosa difieren algo después de comer.
- **Una sola medida por persona.** No se puede comprobar con estos datos cuánto mejora repetirla varios días.
- **La referencia es una sola HbA1c.** El diagnóstico exige confirmarla.
- FINDRISC sin la pregunta de fruta y verdura, que NHANES no tiene (vale 1 punto de 26).
- Población de EE. UU.
