"""Home measurements that replace or narrow down what today requires a visit to the health center.

Urine alone does not replace a blood test (see ``reports/panel_sangre.md``), so the patient
needs other measurements to complete the assessment without traveling:

- **Home blood pressure** with a validated cuff (self-measurement, HBPM). The most valuable
  measurement for cardiovascular risk, and many patients already own the device.
- **Finger prick** (dried blood spot on paper, sent by mail) for creatinine and HbA1c. Not
  the glucometer, which also pricks the finger but gives glucose on the spot. It truly
  measures, but with more error than venous blood: it does not replace the estimate, it
  **updates** it (Bayes' rule on the panel distribution).
- **Heart rhythm** with the watch or the phone camera, to suspect atrial fibrillation.
- **Heart recording** (pulse, single-lead ECG or ECG with sound), to suspect that the heart
  pumps poorly (low ejection fraction).

The default measurement errors are **assumptions** (noted for each). The atrial fibrillation
prevalence is Spanish and measured (OFRECE study). The evidence for finger-prick eGFR still
comes from small studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.special import ndtr

from .i18n import t

# --- Home blood pressure ---

HOME_SBP_LIMIT, HOME_DBP_LIMIT = 135.0, 85.0  # at home; equivalent to 140/90 in the office
OFFICE_OFFSET = 5.0  # mmHg added to use home BP where office BP is expected


@dataclass
class BPReading:
    date: date
    sbp: float
    dbp: float
    evening: bool = False


@dataclass
class HomeBP:
    n: int  # readings used
    days: int
    sbp: float
    dbp: float
    sbp_se: float  # standard error of the mean
    dbp_se: float
    p_sbp_high: float  # P(true mean ≥ 135)
    p_dbp_high: float  # P(true mean ≥ 85)
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
    """Mean of home self-measurement with the usual protocol: the first day is discarded.

    Valid with at least ``min_readings`` readings over ``min_days`` days (ideally 7 days, two
    in the morning and two in the evening). The uncertainty comes from day-to-day variation,
    because readings from the same day resemble each other.
    """
    if not readings:
        return None
    by_day: dict[date, list[BPReading]] = {}
    for r in readings:
        by_day.setdefault(r.date, []).append(r)
    days = sorted(by_day)
    if len(days) > 1:
        days = days[1:]  # the first day tends to read higher
    used = [r for d in days for r in by_day[d]]
    sbp_days = np.array([np.mean([r.sbp for r in by_day[d]]) for d in days])
    dbp_days = np.array([np.mean([r.dbp for r in by_day[d]]) for d in days])
    sbp, dbp = float(np.mean([r.sbp for r in used])), float(np.mean([r.dbp for r in used]))

    def se(day_means: np.ndarray, typical_sd: float) -> float:
        # With few days the observed deviation is unreliable: pool it with the typical one.
        k = len(day_means)
        observed = float(np.var(day_means, ddof=1)) if k > 1 else typical_sd**2
        pooled = ((k - 1) * observed + 2.0 * typical_sd**2) / (k + 1)
        return float(np.sqrt(pooled / k))

    sbp_se, dbp_se = se(sbp_days, 7.0), se(dbp_days, 5.0)
    valid = len(used) >= min_readings and len(days) >= min_days
    p_s = float(ndtr((sbp - HOME_SBP_LIMIT) / sbp_se))
    p_d = float(ndtr((dbp - HOME_DBP_LIMIT) / dbp_se))
    if not valid:
        message = t(
            f"Faltan lecturas: hay {len(used)} en {len(days)} días (sin contar el primero). "
            f"Hacen falta al menos {min_readings} en {min_days} días.",
            f"Not enough readings: {len(used)} over {len(days)} days (not counting the first). "
            f"At least {min_readings} over {min_days} days are needed.",
        )
    elif max(p_s, p_d) >= 0.9:
        message = t(
            f"Tensión alta en casa: media {sbp:.0f}/{dbp:.0f} mmHg (límite 135/85).",
            f"High blood pressure at home: average {sbp:.0f}/{dbp:.0f} mmHg (limit 135/85).",
        )
    elif max(p_s, p_d) <= 0.1:
        message = t(
            f"Tensión controlada en casa: media {sbp:.0f}/{dbp:.0f} mmHg.",
            f"Blood pressure controlled at home: average {sbp:.0f}/{dbp:.0f} mmHg.",
        )
    else:
        message = t(
            f"Tensión en el límite: media {sbp:.0f}/{dbp:.0f} mmHg. Conviene repetir la semana de medidas.",
            f"Borderline blood pressure: average {sbp:.0f}/{dbp:.0f} mmHg. Repeating the week of readings is advisable.",
        )
    return HomeBP(len(used), len(days), sbp, dbp, sbp_se, dbp_se, p_s, p_d, valid, message)


# --- Finger prick ---

# Error of the capillary measurement vs venous. ASSUMPTIONS: eGFR from dried-blood-spot creatinine
# agrees worse than creatinine itself (R² 0.86 vs 0.97 in a 2025 study).
HOME_LAB_ERROR = {
    "egfr": {"log_sd": 0.13},
    "hba1c": {"sd": 0.35},
    "glucose": {"log_sd": 0.08},
    "non_hdl": {"log_sd": 0.10},
}


@dataclass
class HomeLab:
    """Result of a finger prick done at home."""

    value: float
    date: date | None = None
    sd: float | None = None  # additive error; if not given, the one in ``HOME_LAB_ERROR``
    log_sd: float | None = None  # multiplicative error (log scale)

    def error(self, variable: str) -> dict:
        if self.sd is not None or self.log_sd is not None:
            return {"sd": self.sd, "log_sd": self.log_sd}
        if variable not in HOME_LAB_ERROR:
            raise ValueError(
                t(
                    f"No hay error de medida por defecto para {variable}.",
                    f"There is no default measurement error for {variable}.",
                )
            )
        return HOME_LAB_ERROR[variable]


def update_pmf(bounds, pmf, value: float, sd: float | None = None, log_sd: float | None = None, points: int = 8):
    """Updates a binned distribution with a noisy measurement (Bayes' rule).

    ``bounds`` are the bin edges and ``pmf`` the probability of each bin. Within each bin a
    uniform distribution is assumed, as in the panel.
    """
    bounds = np.asarray(bounds, dtype=float)
    pmf = np.asarray(pmf, dtype=float)
    frac = (np.arange(points) + 0.5) / points
    pts = bounds[:-1, None] + frac[None, :] * np.diff(bounds)[:, None]  # points within each bin
    if log_sd is not None:
        z = (np.log(value) - np.log(np.clip(pts, 1e-9, None))) / log_sd
    elif sd is not None:
        z = (value - pts) / sd
    else:
        raise ValueError(t("Hace falta sd o log_sd.", "sd or log_sd is required."))
    lik = np.exp(-0.5 * z**2).mean(axis=1)
    post = pmf * lik
    total = post.sum()
    return post / total if total > 0 else pmf


# --- Heart rhythm ---

# Where the beats come from: a single-lead ECG (watch or pocket ECG device), the pulse recorded
# by the watch ("reloj"), or the phone camera ("cámara") with a finger on the lens. The detector
# was validated with real ECGs; with the camera, only with beats degraded by simulation.
# These are machine values (kept in Spanish).
RHYTHM_SOURCES = ("ecg", "reloj", "cámara")


@dataclass
class RhythmCheck:
    """A rhythm check with the watch or the phone camera (irregular pulse yes or no)."""

    date: date
    irregular: bool
    # By default, what our own detector measures on real recordings from a pocket ECG device
    # (reports/ritmo.md). A validated app can bring its own.
    sensitivity: float = 0.875
    specificity: float = 0.938
    # If the check comes from our own detector (``rhythm.check_from_intervals``), how much it
    # multiplies the odds of atrial fibrillation; more nuanced than a yes or no.
    likelihood_ratio: float | None = None
    source: str = "reloj"  # "ecg", "reloj" (watch) or "cámara" (camera)


# Atrial fibrillation prevalence in Spain by age and sex: OFRECE study (Rev Esp Cardiol
# 2014;67:259-269; 8,343 people aged 40 or older, all with ECG). (minimum age, men, women).
OFRECE_PREVALENCE = ((80, 0.170, 0.181), (70, 0.119, 0.072), (60, 0.053, 0.040), (50, 0.009, 0.011), (0, 0.005, 0.002))
OFRECE_UNDIAGNOSED = 0.10  # share of cases that were undiagnosed


def af_prior(age: float, female: bool | None = None) -> float:
    """P(undiagnosed atrial fibrillation) in someone without a diagnosis.

    Comes from the OFRECE prevalence by age and sex and the fact that 10% of cases were
    unknown. Below age 40, which OFRECE did not study, the 40-49 figure is used.
    """
    for min_age, men, women in OFRECE_PREVALENCE:
        if age >= min_age:
            p = (men + women) / 2.0 if female is None else (women if female else men)
            break
    return OFRECE_UNDIAGNOSED * p / (1.0 - (1.0 - OFRECE_UNDIAGNOSED) * p)


def af_probability(checks: list[RhythmCheck], age: float, prior: float | None = None, female: bool | None = None) -> float:
    """P(atrial fibrillation) after the checks, assuming they are independent.

    Paroxysmal fibrillation is not always present, so several normal checks make it less
    likely but do not rule it out.
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


# --- Low ejection fraction ---

# Ejection fraction below 40% in people over 45: ECHOES study (Lancet 2001;358:439-444;
# 3,960 people in England with echocardiography), 1.8%, half without symptoms. After a heart
# attack, 22.1% (54 of 244; BMJ 2001). There is no equivalent Spanish study with
# echocardiography of the whole sample.
LOW_EF_PREVALENCE = 0.018
LOW_EF_AFTER_INFARCTION = 0.221
LOW_EF_UNDIAGNOSED = 0.5  # assumption: those without symptoms are the undiagnosed ones
LOW_EF_UNDER_45 = 0.003  # assumption: ECHOES did not study people under 45
# Machine values (kept in Spanish): "ecg y sonido" (ECG and sound), "ecg", "pulso" (pulse).
SOURCES = ("ecg y sonido", "ecg", "pulso")  # from most to least informative


@dataclass
class HeartCheck:
    """A home heart recording already scored (``ejection.classify`` or ``pulse.classify_pulse``)."""

    date: date
    likelihood_ratio: float  # how much it multiplies the odds of low ejection fraction
    source: str = "ecg y sonido"  # "pulso", "ecg" or "ecg y sonido"


def low_ef_prior(age: float, coronary: bool = False) -> float:
    """P(undiagnosed low ejection fraction) before recording anything."""
    prevalence = LOW_EF_AFTER_INFARCTION if coronary else LOW_EF_PREVALENCE if age >= 45 else LOW_EF_UNDER_45
    return LOW_EF_UNDIAGNOSED * prevalence / (1.0 - (1.0 - LOW_EF_UNDIAGNOSED) * prevalence)


def low_ef_probability(checks: list[HeartCheck], age: float, coronary: bool = False, prior: float | None = None) -> float:
    """P(low ejection fraction) after the recordings.

    Unlike atrial fibrillation, the heart is the same every day: repeating the recording
    removes noise but adds no independent evidence. So the recordings' results are averaged
    (not accumulated), and only the most informative source counts.
    """
    p = low_ef_prior(age, coronary) if prior is None else prior
    log_odds = np.log(p / (1.0 - p))
    for source in SOURCES:
        ratios = [c.likelihood_ratio for c in checks if c.source == source]
        if ratios:
            log_odds += float(np.mean(np.log(ratios)))
            break
    return float(1.0 / (1.0 + np.exp(-log_odds)))
