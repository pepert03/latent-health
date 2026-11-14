"""Medidas hechas en casa que sustituyen o acotan lo que hoy exige ir al centro.

La orina sola no sustituye a la analítica de sangre (ver ``reports/panel_sangre.md``), así que
el paciente necesita otras medidas para completar la evaluación sin desplazarse:

- **Tensión en casa** con un manguito validado (automedida, AMPA). Es la medida de más valor
  para el riesgo cardiovascular y muchos pacientes ya tienen el aparato.
- **Punción capilar** (gota de sangre en papel, enviada por correo) para creatinina y HbA1c.
  Mide de verdad, pero con más error que la sangre venosa: no sustituye a la estimación,
  la **actualiza** (regla de Bayes sobre la distribución del panel).
- **Ritmo cardíaco** con la cámara o el reloj, para sospechar fibrilación auricular.

Los errores de medida por defecto son **supuestos** (se indica en cada uno). La prevalencia de
fibrilación auricular sí es española y medida (estudio OFRECE). La evidencia de la punción
capilar para el FG es todavía de estudios pequeños.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.special import ndtr

# --- Tensión en casa ---

HOME_SBP_LIMIT, HOME_DBP_LIMIT = 135.0, 85.0  # en casa; equivalen a 140/90 en consulta
OFFICE_OFFSET = 5.0  # mmHg que se suman para usar la tensión de casa donde se espera la de consulta


@dataclass
class BPReading:
    date: date
    sbp: float
    dbp: float
    evening: bool = False


@dataclass
class HomeBP:
    n: int  # lecturas usadas
    days: int
    sbp: float
    dbp: float
    sbp_se: float  # error típico de la media
    dbp_se: float
    p_sbp_high: float  # P(media verdadera ≥ 135)
    p_dbp_high: float  # P(media verdadera ≥ 85)
    valid: bool
    message: str

    @property
    def p_high(self) -> float:
        return max(self.p_sbp_high, self.p_dbp_high)

    @property
    def office_sbp(self) -> float:
        return self.sbp + OFFICE_OFFSET

    @property
    def office_dbp(self) -> float:
        return self.dbp + OFFICE_OFFSET


def summarize_home_bp(readings: list[BPReading], min_readings: int = 12, min_days: int = 3) -> HomeBP | None:
    """Media de la automedida con el protocolo habitual: se descarta el primer día.

    Es válida con al menos ``min_readings`` lecturas en ``min_days`` días (lo ideal son 7 días,
    dos por la mañana y dos por la noche). La incertidumbre sale de la variación entre días,
    porque las lecturas de un mismo día se parecen entre sí.
    """
    if not readings:
        return None
    by_day: dict[date, list[BPReading]] = {}
    for r in readings:
        by_day.setdefault(r.date, []).append(r)
    days = sorted(by_day)
    if len(days) > 1:
        days = days[1:]  # el primer día suele salir más alto
    used = [r for d in days for r in by_day[d]]
    sbp_days = np.array([np.mean([r.sbp for r in by_day[d]]) for d in days])
    dbp_days = np.array([np.mean([r.dbp for r in by_day[d]]) for d in days])
    sbp, dbp = float(np.mean([r.sbp for r in used])), float(np.mean([r.dbp for r in used]))

    def se(day_means: np.ndarray, typical_sd: float) -> float:
        # Con pocos días la desviación observada es poco fiable: se combina con la habitual.
        k = len(day_means)
        observed = float(np.var(day_means, ddof=1)) if k > 1 else typical_sd**2
        pooled = ((k - 1) * observed + 2.0 * typical_sd**2) / (k + 1)
        return float(np.sqrt(pooled / k))

    sbp_se, dbp_se = se(sbp_days, 7.0), se(dbp_days, 5.0)
    valid = len(used) >= min_readings and len(days) >= min_days
    p_s = float(ndtr((sbp - HOME_SBP_LIMIT) / sbp_se))
    p_d = float(ndtr((dbp - HOME_DBP_LIMIT) / dbp_se))
    if not valid:
        message = (
            f"Faltan lecturas: hay {len(used)} en {len(days)} días (sin contar el primero). "
            f"Hacen falta al menos {min_readings} en {min_days} días."
        )
    elif max(p_s, p_d) >= 0.9:
        message = f"Tensión alta en casa: media {sbp:.0f}/{dbp:.0f} mmHg (límite 135/85)."
    elif max(p_s, p_d) <= 0.1:
        message = f"Tensión controlada en casa: media {sbp:.0f}/{dbp:.0f} mmHg."
    else:
        message = f"Tensión en el límite: media {sbp:.0f}/{dbp:.0f} mmHg. Conviene repetir la semana de medidas."
    return HomeBP(len(used), len(days), sbp, dbp, sbp_se, dbp_se, p_s, p_d, valid, message)


# --- Punción capilar ---

# Error de la medida capilar frente a la venosa. SUPUESTOS: el FG a partir de creatinina en gota
# seca concuerda peor que la creatinina misma (R² 0,86 frente a 0,97 en un estudio de 2025).
HOME_LAB_ERROR = {
    "egfr": {"log_sd": 0.13},
    "hba1c": {"sd": 0.35},
    "glucose": {"log_sd": 0.08},
    "non_hdl": {"log_sd": 0.10},
}


@dataclass
class HomeLab:
    """Resultado de una punción capilar hecha en casa."""

    value: float
    date: date | None = None
    sd: float | None = None  # error aditivo; si no se da, el de ``HOME_LAB_ERROR``
    log_sd: float | None = None  # error multiplicativo (escala log)

    def error(self, variable: str) -> dict:
        if self.sd is not None or self.log_sd is not None:
            return {"sd": self.sd, "log_sd": self.log_sd}
        if variable not in HOME_LAB_ERROR:
            raise ValueError(f"No hay error de medida por defecto para {variable}.")
        return HOME_LAB_ERROR[variable]


def update_pmf(bounds, pmf, value: float, sd: float | None = None, log_sd: float | None = None, points: int = 8):
    """Actualiza una distribución por tramos con una medida con error (regla de Bayes).

    ``bounds`` son los límites de los tramos y ``pmf`` la probabilidad de cada uno. Dentro de
    cada tramo se asume reparto uniforme, igual que en el panel.
    """
    bounds = np.asarray(bounds, dtype=float)
    pmf = np.asarray(pmf, dtype=float)
    frac = (np.arange(points) + 0.5) / points
    t = bounds[:-1, None] + frac[None, :] * np.diff(bounds)[:, None]  # puntos dentro de cada tramo
    if log_sd is not None:
        z = (np.log(value) - np.log(np.clip(t, 1e-9, None))) / log_sd
    elif sd is not None:
        z = (value - t) / sd
    else:
        raise ValueError("Hace falta sd o log_sd.")
    lik = np.exp(-0.5 * z**2).mean(axis=1)
    post = pmf * lik
    total = post.sum()
    return post / total if total > 0 else pmf


# --- Ritmo cardíaco ---


@dataclass
class RhythmCheck:
    """Una comprobación del ritmo con el móvil o el reloj (pulso irregular sí o no)."""

    date: date
    irregular: bool
    # Por defecto, lo que mide el detector propio con registros reales de un electrocardiógrafo
    # de bolsillo (reports/ritmo.md). Una aplicación validada puede traer los suyos.
    sensitivity: float = 0.875
    specificity: float = 0.938
    # Si la comprobación viene del detector propio (``rhythm.check_from_intervals``), cuánto
    # multiplica la odds de fibrilación auricular; tiene más matiz que un sí o un no.
    likelihood_ratio: float | None = None


# Prevalencia de fibrilación auricular en España por edad y sexo: estudio OFRECE (Rev Esp Cardiol
# 2014;67:259-269; 8.343 personas de 40 años o más, todas con ECG). (edad mínima, hombres, mujeres).
OFRECE_PREVALENCE = ((80, 0.170, 0.181), (70, 0.119, 0.072), (60, 0.053, 0.040), (50, 0.009, 0.011), (0, 0.005, 0.002))
OFRECE_UNDIAGNOSED = 0.10  # parte de los casos que no estaban diagnosticados


def af_prior(age: float, female: bool | None = None) -> float:
    """P(fibrilación auricular sin diagnosticar) en alguien que no la tiene diagnosticada.

    Sale de la prevalencia por edad y sexo de OFRECE y de que el 10 % de los casos no se
    conocía. Por debajo de 40 años, que OFRECE no estudió, se usa la cifra de 40 a 49.
    """
    for min_age, men, women in OFRECE_PREVALENCE:
        if age >= min_age:
            p = (men + women) / 2.0 if female is None else (women if female else men)
            break
    return OFRECE_UNDIAGNOSED * p / (1.0 - (1.0 - OFRECE_UNDIAGNOSED) * p)


def af_probability(checks: list[RhythmCheck], age: float, prior: float | None = None, female: bool | None = None) -> float:
    """P(fibrilación auricular) tras las comprobaciones, suponiéndolas independientes entre sí.

    La fibrilación paroxística no siempre está presente, así que varias comprobaciones normales
    la hacen menos probable pero no la descartan.
    """
    p = af_prior(age, female) if prior is None else prior
    log_odds = np.log(p / (1.0 - p))
    for c in checks:
        if c.likelihood_ratio is not None:
            log_odds += np.log(c.likelihood_ratio)
        elif c.irregular:
            log_odds += np.log(c.sensitivity / (1.0 - c.specificity))
        else:
            log_odds += np.log((1.0 - c.sensitivity) / c.specificity)
    return float(1.0 / (1.0 + np.exp(-log_odds)))
