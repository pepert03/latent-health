# LatentHealth

Detección precoz del riesgo cardio-renal-metabólico en atención primaria a partir de la orina y
la historia clínica (Reto 1 del hackathon de Boehringer: *automatizar lo repetitivo*).

- **Filtro bayesiano de la albuminuria.** Estima el UACR verdadero de cada paciente con todas sus
  muestras de orina: tipo de muestra, dilución, elevaciones transitorias y censura. A partir de ahí
  descarta, confirma (con el criterio de cronicidad KDIGO) o dice si merece la pena repetir.
  Validado en NHANES 2009-2010 y bien calibrado.
- **Panel virtual de sangre.** Estima con su incertidumbre el FG, la HbA1c, la glucosa, el potasio,
  el colesterol no-HDL, la hemoglobina y el NT-proBNP a partir de la historia clínica y la orina.
  Entrenado en NHANES 1999-2018.
- **Evaluación por paciente.** Da la probabilidad de cada categoría y nivel de riesgo KDIGO, de
  diabetes oculta y de insuficiencia cardíaca, y dice qué pruebas pedir.

Toda la explicación, con resultados y límites: [docs/solucion.md](docs/solucion.md). Informes de
validación: [reports/validacion_albuminuria.md](reports/validacion_albuminuria.md) y
[reports/panel_sangre.md](reports/panel_sangre.md).

## Uso rápido

```bash
uv sync
```

```bash
uv run python scripts/demo.py
```

```bash
uv run pytest
```

Para rehacer los modelos desde los datos públicos de NHANES, sigue la sección 3 de
[docs/solucion.md](docs/solucion.md).

## Estructura

| Ruta | Contenido |
|---|---|
| `src/latenthealth/albuminuria/` | Modelo, ajuste y filtro de la albuminuria |
| `src/latenthealth/panel/` | Datos, modelo distribucional y evaluación del panel de sangre |
| `src/latenthealth/assessment.py` | Evaluación cardio-renal-metabólica de un paciente |
| `scripts/` | Descarga de datos, ajuste, validación y demo |
| `models/` | Parámetros y modelos ya entrenados |
| `reports/` | Informes de validación generados por los scripts |
| `tests/` | Tests |

---

## Entrega del hackathon (instrucciones de la organización)

Welcome! This is your team's repository for developing and delivering your hackathon project.

### Where to work

Find your team's repository on the [organisation's repositories page](https://github.com/orgs/HackathonBoehringerIT/repositories).

Use only the private repository assigned to your team. Your teammates can access it after accepting their organisation invitations. Do not work in `base_template`; it is a shared, read-only starting point.

Your team can work in this repository throughout the hackathon. It is the one place to deliver your project—do not create or submit a separate repository.

### Submission deadline

The organisers will announce the final deadline and its time zone. **Any work uploaded after that deadline will not be taken into account.**

Before the deadline, make sure the final version is committed and pushed to the repository's `main` branch. If you use a pull request, merge it before the deadline; work left only on another branch or in an unmerged pull request may not be included in the final review.

You only need to deliver your project through this repository. You do **not** need to wait until the end to upload it: it is recommended that you make commits throughout the project, recording the different stages of your planning, development, and final result. This gives your team a useful history of how the project evolved.

### Before the deadline

- Confirm the final version is present on the `main` branch.
- Make sure any pull requests containing final work have been merged.
- Open the important files on GitHub and check that they render or download correctly.
- Confirm the work was committed and pushed before the announced deadline and time zone.

If you cannot access your team's repository, cannot push, or are unsure whether your work was submitted in time, contact an organiser as soon as possible.
