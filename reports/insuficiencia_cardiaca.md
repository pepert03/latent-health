# Insuficiencia cardíaca: qué se puede saber desde casa

Generado por `scripts/fit_heart_home.py`. Datos: NHANES 1999-2004, 10174 adultos con NT-proBNP medido y todos los datos de casa, con mortalidad enlazada hasta 2019. Validación cruzada de cinco partes; entre paréntesis, el intervalo del 95 %.

El NT-proBNP es la analítica con la que en primaria se descarta la insuficiencia cardíaca: por debajo de 125 pg/ml es muy improbable. No se puede medir en casa.

## ¿Quién tendrá el NT-proBNP por encima de 125 pg/ml?

Lo tiene el 20,5 % de las 9930 personas sin insuficiencia cardíaca diagnosticada y el 47,9 % de las 3258 de 60 años o más.

| Lo que se usa | AUC sin diagnóstico previo | AUC en 60 años o más | Error cuadrático |
|---|---|---|---|
| Historia clínica (como hasta ahora) | 0,872 (0,86-0,88) | 0,754 (0,74-0,77) | 0,1071 |
| Historia y lo que cuenta el paciente (síntomas y pulso) | 0,876 (0,87-0,88) | 0,769 (0,75-0,79) | 0,1050 |
| Historia, síntomas, pulso y orina | 0,879 (0,87-0,89) | 0,770 (0,75-0,79) | 0,1045 |
| Todo lo anterior y filtrado glomerular | 0,881 (0,87-0,89) | 0,779 (0,76-0,79) | 0,1029 |

Ganancia de AUC al añadir los síntomas y el pulso a la historia: sin insuficiencia cardíaca diagnosticada, +0,004 (0,002 a 0,006); de 60 años o más, +0,014 (0,009 a 0,020).

## ¿Quién tendrá el NT-proBNP por encima de 300 pg/ml?

Lo tiene el 7,5 % de las 9930 personas sin insuficiencia cardíaca diagnosticada y el 20,2 % de las 3258 de 60 años o más.

| Lo que se usa | AUC sin diagnóstico previo | AUC en 60 años o más | Error cuadrático |
|---|---|---|---|
| Historia clínica (como hasta ahora) | 0,897 (0,89-0,91) | 0,764 (0,74-0,78) | 0,0534 |
| Historia y lo que cuenta el paciente (síntomas y pulso) | 0,904 (0,89-0,91) | 0,782 (0,76-0,80) | 0,0519 |
| Historia, síntomas, pulso y orina | 0,910 (0,90-0,92) | 0,795 (0,78-0,81) | 0,0505 |
| Todo lo anterior y filtrado glomerular | 0,915 (0,91-0,92) | 0,805 (0,79-0,82) | 0,0495 |

Ganancia de AUC al añadir los síntomas y el pulso a la historia: sin insuficiencia cardíaca diagnosticada, +0,007 (0,004 a 0,010); de 60 años o más, +0,019 (0,009 a 0,028).

## ¿Cuánto añade medir el NT-proBNP a lo que ya se sabe en casa?

Muerte en los 10 años siguientes entre las 6756 personas de 40 años o más (todas con más de 15 años de seguimiento).

| Desenlace | Lo que se usa | AUC |
|---|---|---|
| Muerte por enfermedad del corazón | Edad, sexo y NT-proBNP medido | 0,822 (0,80-0,84) |
| Muerte por enfermedad del corazón | Lo de casa (cuestionario, manguito y orina) | 0,824 (0,80-0,84) |
| Muerte por enfermedad del corazón | Lo de casa y NT-proBNP medido | 0,838 (0,82-0,86) |
| Muerte por enfermedad del corazón | Lo que añade el NT-proBNP a lo de casa | +0,014 (0,004 a 0,025) |
| Muerte por corazón o ictus | Edad, sexo y NT-proBNP medido | 0,830 (0,81-0,85) |
| Muerte por corazón o ictus | Lo de casa (cuestionario, manguito y orina) | 0,835 (0,82-0,85) |
| Muerte por corazón o ictus | Lo de casa y NT-proBNP medido | 0,845 (0,83-0,86) |
| Muerte por corazón o ictus | Lo que añade el NT-proBNP a lo de casa | +0,010 (0,004 a 0,018) |

## Límites

- NHANES no tiene ecocardiograma ni diagnóstico confirmado de insuficiencia cardíaca: se predice una analítica y la muerte por enfermedad del corazón (que incluye el infarto), no la insuficiencia cardíaca en sí.
- Sueros de 1999-2004 y cuestionario hecho por un entrevistador.
- Faltan los síntomas más específicos (hinchazón de tobillos, dormir incorporado, subida rápida de peso), que NHANES no pregunta y que el paciente sí puede contar.
