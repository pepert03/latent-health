# Vidas que salvaría el método en España: estimación con supuestos

Generado por `scripts/vidas_salvadas.py`. **No es un resultado medido**: es una cadena de supuestos para dar el orden de magnitud. Cada eslabón dice de dónde sale.

## La vía que se cuenta: albuminuria oculta tratada con iSGLT2

- **Mortalidad de partida (dato):** de las 1854 personas de 40 años o más con diabetes o hipertensión y albuminuria de NHANES 1999-2008, murió del corazón o de un ictus el 19,4 % en 10 años (2,14 % al año). Con la misma diabetes o hipertensión y sin albuminuria, el 9,4 %.
- **Efecto del tratamiento (publicado):** los iSGLT2 reducen la muerte cardiovascular un 14 % (RR 0,86; intervalo 0,81 a 0,92; metaanálisis de 13 ensayos y 90.409 personas, Lancet 2022;400:1788).

| Eslabón | Prudente | Central | Optimista | De dónde sale |
|---|---|---|---|---|
| Adultos de 40+ con diabetes o hipertensión | 12.000.000 | 12.000.000 | 12.000.000 | **Supuesto** (orden de magnitud con la prevalencia de di@bet.es) |
| Con albuminuria | 15 % | 20 % | 25 % | Por debajo de lo medido: 22 % en hipertensos y 32 % en diabéticos (Shin 2021); 14 % en todos los adultos (ONDAAS) |
| Sin medir ni diagnosticar | 70 % | 75 % | 80 % | UACR en dos años al 35 % de los diabéticos y al 4 % de los hipertensos (Shin 2021) |
| Albuminurias ocultas | 1.260.000 | 1.800.000 | 2.400.000 | |
| Participan en el cribado en casa | 30 % | 50 % | 60 % | THOMAS: 44 % con aplicación, 59 % con tubo |
| El circuito la confirma | 85 % | 90 % | 95 % | Filtro de albuminuria (validacion_albuminuria.md) |
| Empiezan iSGLT2 | 30 % | 50 % | 70 % | **Supuesto**; hoy lo toma el 10-33 % de los candidatos |
| Personas tratadas | 96.390 | 405.000 | 957.600 | |
| Reducción de la muerte cardiovascular | 5 % | 14 % | 19 % | Lancet 2022 (central y extremo del intervalo; el prudente, por debajo) |
| **Muertes evitadas al año** | **103** | **1.211** | **3.886** | |

## Lo que no se cuenta

- **Diabetes oculta.** Encontrarla antes no ha demostrado reducir la mortalidad a 5-10 años (ensayo ADDITION); su beneficio llega por la vía del riñón y del corazón, que ya se cuenta arriba.
- **Fibrilación auricular.** El cribado no ha demostrado reducir ictus ni muertes de forma clara (LOOP, STROKESTOP).
- **Fracción de eyección baja.** El tratamiento salva vidas en quien tiene síntomas (DAPA-HF: muerte 11,6 % frente a 13,9 % en 18 meses), pero el ECG solo llega a quien tiene reloj o un infarto previo: decenas de vidas al año, no centenares, con supuestos aún más débiles.
- **Muertes por riñón** (diálisis evitada) e ingresos por insuficiencia cardíaca, que los iSGLT2 también reducen.

Para comparar: en España mueren 113.620 personas al año por enfermedades del sistema circulatorio (INE, 2024).
