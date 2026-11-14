# Tendencia del filtrado glomerular: comprobación en simulación

Generado por `scripts/validate_trend.py`. **No es una validación con pacientes**: NHANES no tiene analíticas repetidas. Son 3000 pacientes simulados con los supuestos del propio modelo (pendiente, ruido de la creatinina y efecto de los tratamientos tomados de la literatura), con una analítica al año.

## Detección del descenso según el número de analíticas

- **Intervalo**: cuántas veces la pendiente verdadera (la inicial) cae en el intervalo del 80 % del filtro. La pendiente cambia un poco con los años, así que algo por debajo del 80 % es lo esperable.
- **Visto**: de los que pierden más de 5 al año, a cuántos marca.
- **Falsa alarma**: de los que pierden menos de 2 al año, a cuántos marca.
- **Filtro, alerta**: marca cuando P(pendiente < -3) ≥ 80 % (lo que sale como hallazgo en la lista del cupo).
- **Filtro, aviso**: marca cuando P(pendiente < -3) ≥ 50 % (tendencia dudosa o peor: conviene adelantar la analítica).
- **Regla a ojo**: marcar si la caída media entre la primera y la última analítica pasa de 5 al año.

| Analíticas anuales | Intervalo del 80 % | Alerta: visto | Alerta: falsa alarma | Aviso: visto | Aviso: falsa alarma | Regla a ojo: visto | Regla a ojo: falsa alarma |
|---|---|---|---|---|---|---|---|
| 2 | 82 % | 1 % | 0,0 % | 6 % | 0,3 % | 60 % | 24,3 % |
| 3 | 84 % | 17 % | 0,2 % | 38 % | 1,1 % | 62 % | 11,2 % |
| 4 | 83 % | 45 % | 0,2 % | 72 % | 1,2 % | 79 % | 3,5 % |
| 5 | 84 % | 71 % | 0,2 % | 90 % | 1,5 % | 78 % | 1,5 % |
| 6 | 84 % | 88 % | 0,3 % | 96 % | 1,9 % | 85 % | 0,7 % |

## Inicio de un iSGLT2

2316 pacientes estables (pierden menos de 2 al año) que empiezan un iSGLT2 entre la segunda y la tercera de cuatro analíticas anuales. El fármaco baja el FG unos 3 puntos al principio.

| | Marcados como descenso |
|---|---|
| Sin decirle al filtro que empezó el tratamiento | 1,1 % |
| Con el tratamiento como entrada conocida | 0,2 % |

## Límites

- Todos los parámetros son supuestos. Hay que ajustarlos con analíticas repetidas de atención primaria.
- El modelo no contempla el fracaso renal agudo: una caída brusca y reversible la tomaría por descenso.
- La creatinina depende de la masa muscular; un cambio grande de peso mueve el FG estimado sin que cambie el riñón.
