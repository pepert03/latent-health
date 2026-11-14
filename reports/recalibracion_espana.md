# Recalibración de los priors a atención primaria española

Generado por `scripts/fit_recalibration.py`. Referencia: ONDAAS, Clin Kidney J 2025;18(5):sfaf123 (Burgos, febrero-mayo de 2024), 9526 adultos (≥ 18 años) a los que su médico de familia pidió una analítica. Población de comparación: los 25319 adultos de NHANES 2009-2018 repesados al reparto por edad y sexo de ONDAAS.

Solo se mueven interceptos. El modelo de medida de la orina y la forma en que cada dato del paciente cambia la estimación quedan como estaban.

## Albuminuria

Proporción de personas cuya muestra de orina sale ≥ 30 mg/g, antes de medirles nada.

| | ONDAAS | Modelo de NHANES | Modelo recalibrado |
|---|---|---|---|
| Total | 14,0 % | 15,1 % | 14,0 % |
| 18-44 años | 3,0 % | 5,1 % | 4,6 % |
| 45-64 años | 8,2 % | 11,5 % | 10,6 % |
| 65+ años | 20,6 % | 20,6 % | 19,3 % |

Constante sumada al logit de las componentes elevadas del prior: **-0.187** (multiplica la odds de albuminuria por 0.83). El prior de NHANES ya estaba cerca. Se ajusta solo el total; las filas por edad son una comprobación, no un objetivo.

Se ha supuesto que la orina de ONDAAS es una muestra aleatoria (se recogió en el centro). Si fuera la primera de la mañana, el modelo de NHANES daría 9,6 % y la constante sería +1.235.

## Filtrado glomerular

ONDAAS usó la ecuación CKD-EPI 2009 y este proyecto usa la de 2021, que da valores algo más altos con la misma creatinina. Para comparar lo mismo, cada categoría se calcula con el corte de 2009 traducido a la escala de 2021 persona a persona (FG 60 de 2009 equivale a entre 61 y 65 de 2021).

| Categoría (ecuación de 2009) | ONDAAS | Panel de NHANES | Panel recalibrado |
|---|---|---|---|
| FG < 60 | 12,8 % | 18,3 % | 12,8 % |
| G1 | 36,4 % | 40,2 % | 41,8 % |
| G2 | 50,8 % | 41,5 % | 45,4 % |
| G3a | 8,3 % | 11,4 % | 8,6 % |
| G3b | 3,6 % | 4,7 % | 2,9 % |
| G4 | 0,9 % | 1,6 % | 1,0 % |
| G5 | 0,0 % | 0,5 % | 0,3 % |

Constante sumada al logit de FG < 60 en la distribución del panel: **-0.779** (multiplica su odds por 0.46). Se ajusta solo FG < 60; el resto de categorías es una comprobación. El reparto entre G1 y G2 no se corrige: no cambia ninguna decisión.

## Cautelas

- ONDAAS son pacientes a los que se pidió analítica, no todo el cupo.
- El artículo no dice si la orina era la primera de la mañana; se asume muestra aleatoria.
- ONDAAS usó CKD-EPI 2009 y creatinina por Jaffé; el objetivo se traduce a la escala de CKD-EPI 2021.
- La población de comparación es NHANES repesada por edad y sexo; la edad de NHANES está acotada en 80 años.
- Es una corrección de población, no una validación: no hay datos individuales españoles con los que comprobar la calibración paciente a paciente.
