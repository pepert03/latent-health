"""eGFR trend: level and slope from previous lab tests.

A Kalman filter over the state (level, slope) runs through the patient's creatinine results.
It is meant to catch "kidney function slowly worsening without any pain":

- it separates real decline from creatinine noise (biological and analytical variation), which
  can move eGFR several points between two lab tests without anything happening;
- it uses **treatments as a known input**: when an SGLT2 inhibitor or an ACEi/ARB is started,
  eGFR drops a few points in the first weeks and then declines more slowly. Without that
  input, the expected dip is mistaken for a rapid decline;
- it assumes most people lose eGFR slowly and a few quickly (more so with diabetes or
  albuminuria): two filters, one per group, mixed according to what the data say;
- it gives probabilities: of decline (slope < -3 ml/min/1.73 m² per year), of rapid decline
  (< -5, KDIGO criterion), of being below 60 and of reaching below 30 within five years.

**The parameters are assumptions taken from the literature, not fitted**: NHANES is
cross-sectional and has no repeated lab tests. The model has only been checked in simulation
(``scripts/validate_trend.py``); it must be fitted on longitudinal primary care data before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.special import ndtr
from scipy.stats import norm

from .i18n import Labels, t

G_EDGES = (90.0, 60.0, 45.0, 30.0, 15.0)
G_LABELS = ("G1", "G2", "G3a", "G3b", "G4", "G5")
LAB, CAPILLARY = "laboratorio", "capilar"  # machine values (API field ``source``)


@dataclass
class EgfrMeasurement:
    date: date
    egfr: float  # ml/min/1.73 m² (CKD-EPI 2021)
    source: str = LAB  # "laboratorio" or "capilar" (finger-prick, noisier)
    above: bool = False  # the report only says "> value" (many labs cap at 90)


@dataclass
class TreatmentStart:
    date: date
    kind: str  # "isglt2" (SGLT2 inhibitor) or "ieca_ara2" (ACEi/ARB)


def _default_treatments() -> dict:
    # (mean initial dip, its SD, slope change, its SD)
    return {"isglt2": (-3.0, 2.0, 1.0, 0.7), "ieca_ara2": (-2.5, 2.5, 0.5, 0.7)}


@dataclass(frozen=True)
class TrendParams:
    # Slope before seeing data, in ml/min/1.73 m² per year. A mixture of two groups: most lose
    # eGFR slowly and a few quickly. With a single normal, rapid declines would look almost
    # impossible and the filter would take years to believe them.
    stable_slope: tuple[float, float] = (-0.8, 1.2)  # mean and SD of the stable group
    fast_slope: tuple[float, float] = (-4.5, 2.5)  # fast-progressing group
    fast_base: float = 0.05  # share of the fast group without diabetes or albuminuria
    fast_logit_diabetes: float = 0.9
    fast_logit_a2: float = 1.3  # albuminuria 30-300 mg/g
    fast_logit_a3: float = 2.6  # albuminuria > 300 mg/g
    # Dynamics: how far level and slope drift from a straight line, per square root of a year.
    level_noise: float = 1.5
    slope_noise: float = 0.4
    # Measurement: creatinine coefficient of variation (biological + analytical).
    creatinine_cv_lab: float = 0.055
    creatinine_cv_capillary: float = 0.11
    min_sd: float = 1.5
    treatments: dict = field(default_factory=_default_treatments)

    def p_fast(self, diabetes: bool, p_a2: float, p_a3: float) -> float:
        """Expected share of fast progressors among patients like this one."""
        logit = (
            np.log(self.fast_base / (1.0 - self.fast_base))
            + self.fast_logit_diabetes * bool(diabetes)
            + self.fast_logit_a2 * p_a2
            + self.fast_logit_a3 * p_a3
        )
        return float(1.0 / (1.0 + np.exp(-logit)))

    def slope_components(self, diabetes: bool, p_a2: float, p_a3: float) -> list[tuple[float, float, float]]:
        """Slope prior groups: (weight, mean, SD)."""
        fast = self.p_fast(diabetes, p_a2, p_a3)
        return [(1.0 - fast, *self.stable_slope), (fast, *self.fast_slope)]

    def prior_slope(self, diabetes: bool, p_a2: float, p_a3: float) -> tuple[float, float]:
        """Slope mean and SD before seeing data (of the whole mixture)."""
        comps = self.slope_components(diabetes, p_a2, p_a3)
        mean = sum(w * m for w, m, _ in comps)
        var = sum(w * (sd**2 + m**2) for w, m, sd in comps) - mean**2
        return float(mean), float(np.sqrt(var))

    def measurement_sd(self, egfr: float, age: float, female: bool, source: str = LAB) -> float:
        """SD of estimated eGFR due to creatinine noise (delta method on CKD-EPI)."""
        knee = 142.0 * 0.9938**age * (1.012 if female else 1.0)  # eGFR with creatinine at the κ knot
        exponent = 1.2 if egfr < knee else (0.241 if female else 0.302)
        cv = self.creatinine_cv_capillary if source == CAPILLARY else self.creatinine_cv_lab
        return float(np.hypot(self.min_sd, egfr * exponent * cv))


@dataclass
class TrendPoint:
    date: date
    level: float
    low: float
    high: float


@dataclass
class EgfrTrend:
    as_of: date
    n: int  # lab tests used
    span_years: float
    level: float
    level_sd: float
    slope: float  # ml/min/1.73 m² per year
    slope_sd: float
    p_decline: float  # P(slope < -3)
    p_rapid: float  # P(slope < -5)
    p_below_60: float
    p_below_30_in_5y: float
    p_fast: float  # probability of belonging to the fast-progressing group
    chronic_below_60: bool  # two lab tests more than 3 months apart with eGFR < 60 very likely
    # Machine values (see STATUS_TEXT for display): "sin_datos", "insuficiente", "estable",
    # "descenso", "descenso_rapido", "incierto".
    status: str
    trajectory: list[TrendPoint]
    measured_drop_explained: float = 0.0  # expected dip from treatments started (ml/min)
    # Normal mixture of the current state: (weight, mean [level, slope], 2x2 covariance).
    components: list = field(default_factory=list, repr=False)

    def _cdf(self, index: int, value):
        """P(level or slope ≤ value) under the mixture; ``value`` may be an array."""
        value = np.asarray(value, dtype=float)
        return sum(w * ndtr((value - m[index]) / np.sqrt(P[index, index])) for w, m, P in self.components)

    def interval(self, what: str = "level", q: float = 0.8) -> tuple[float, float]:
        """Central interval with probability ``q`` for the level or the slope."""
        index = 0 if what == "level" else 1
        mean, sd = (self.level, self.level_sd) if index == 0 else (self.slope, self.slope_sd)
        grid = np.linspace(mean - 8 * sd, mean + 8 * sd, 201)
        cdf = self._cdf(index, grid)
        lo, hi = np.interp([(1 - q) / 2, (1 + q) / 2], cdf, grid)
        return float(lo), float(hi)

    def p_below(self, threshold: float) -> float:
        return float(self._cdf(0, threshold))

    def category_probs(self) -> dict[str, float]:
        """Probability of each KDIGO G category given the uncertainty of the current level."""
        below = [self.p_below(e) for e in G_EDGES]
        probs = np.clip(np.r_[1.0 - below[0], -np.diff(below), below[-1]], 0.0, 1.0)
        return dict(zip(G_LABELS, (probs / probs.sum()).tolist()))


STATUS_TEXT = Labels(
    {
        "sin_datos": ("sin analíticas", "no lab tests"),
        "insuficiente": ("pocas analíticas para ver la tendencia", "too few lab tests to see a trend"),
        "estable": ("estable", "stable"),
        "descenso": ("descenso sostenido", "sustained decline"),
        "descenso_rapido": ("descenso rápido", "rapid decline"),
        "incierto": ("tendencia dudosa", "uncertain trend"),
    }
)


def default_level_prior(age: float) -> tuple[float, float]:
    """eGFR expected for age when there is nothing better (weak prior)."""
    return float(np.clip(100.0 - 0.85 * (age - 40.0), 45.0, 110.0)), 20.0


def _years(d: date, origin: date) -> float:
    return (d - origin).days / 365.25


def _advance(m, P, t_from, t_to, jumps, params: TrendParams):
    """Moves the state from t_from to t_to, applying any treatment starts in between.

    Returns the predicted mean and covariance and the total F matrix (for smoothing).
    """
    F_total = np.eye(2)
    t = t_from
    for t_jump, kind in [j for j in jumps if t_from < j[0] <= t_to] + [(t_to, None)]:
        dt = max(t_jump - t, 0.0)
        F = np.array([[1.0, dt], [0.0, 1.0]])
        ql, qs = params.level_noise**2, params.slope_noise**2
        Q = np.array([[ql * dt + qs * dt**3 / 3.0, qs * dt**2 / 2.0], [qs * dt**2 / 2.0, qs * dt]])
        m, P, F_total = F @ m, F @ P @ F.T + Q, F @ F_total
        if kind is not None:
            dip, dip_sd, dslope, dslope_sd = params.treatments[kind]
            m = m + np.array([dip, dslope])
            P = P + np.diag([dip_sd**2, dslope_sd**2])
        t = t_jump
    return m, P, F_total


def _kalman(m, P, ms, jumps, origin, as_of, age, female, params: TrendParams) -> dict:
    """Kalman filter and smoother for one prior group. Also returns the cumulative likelihood."""
    H = np.array([1.0, 0.0])
    t, loglik = 0.0, 0.0
    predicted, filtered, transitions, below, logliks = [], [], [], [], []
    for obs in ms:
        t_obs = _years(obs.date, origin)
        m, P, F = _advance(m, P, t, t_obs, jumps, params)
        predicted.append((m.copy(), P.copy()))
        transitions.append(F)
        r = params.measurement_sd(obs.egfr, age, female, obs.source) ** 2
        mu, s = float(H @ m), float(H @ P @ H + r)
        gain = P @ H / s
        if obs.above:  # only known to be higher: truncated-normal update
            alpha = (obs.egfr - mu) / np.sqrt(s)
            tail = max(norm.sf(alpha), 1e-12)
            lam = norm.pdf(alpha) / tail
            mean_z, var_z = mu + np.sqrt(s) * lam, s * max(1.0 - lam * (lam - alpha), 1e-6)
            m = m + gain * (mean_z - mu)
            P = P - np.outer(gain, gain) * (s - var_z)
            loglik += float(np.log(tail))
        else:
            m = m + gain * (obs.egfr - mu)
            P = P - np.outer(gain, gain) * s
            loglik += float(norm.logpdf(obs.egfr, mu, np.sqrt(s)))
        filtered.append((m.copy(), P.copy()))
        below.append(float(ndtr((60.0 - m[0]) / np.sqrt(P[0, 0]))))
        logliks.append(loglik)
        t = t_obs

    # Backward smoothing (Rauch-Tung-Striebel) to draw the trajectory.
    smooth = []
    if ms:
        sm, sP = filtered[-1]
        smooth = [(sm, sP)]
        for k in range(len(ms) - 2, -1, -1):
            mf, Pf = filtered[k]
            mp, Pp = predicted[k + 1]
            C = Pf @ transitions[k + 1].T @ np.linalg.inv(Pp)
            sm = mf + C @ (sm - mp)
            sP = Pf + C @ (sP - Pp) @ C.T
            smooth.append((sm, sP))
        smooth.reverse()
    m, P, _ = _advance(m, P, t, max(_years(as_of, origin), t), jumps, params)
    return {"m": m, "P": P, "below": below, "logliks": logliks, "smooth": smooth}


def fit_trend(
    measurements: list[EgfrMeasurement],
    age: float,
    female: bool,
    diabetes: bool = False,
    p_a2: float = 0.0,
    p_a3: float = 0.0,
    treatments: list[TreatmentStart] | None = None,
    as_of: date | None = None,
    prior_level: tuple[float, float] | None = None,
    params: TrendParams | None = None,
) -> EgfrTrend:
    """Current eGFR level and slope of a patient.

    ``prior_level`` is (mean, SD) of eGFR before seeing their lab tests; by default, the value
    expected for age. ``p_a2`` and ``p_a3`` are the albuminuria probabilities from the filter:
    with albuminuria a fast eGFR decline is more likely.
    """
    params = params or TrendParams()
    ms = sorted(measurements, key=lambda m: m.date)
    as_of = as_of or (ms[-1].date if ms else date.today())
    origin = ms[0].date if ms else as_of
    level0, level0_sd = prior_level or default_level_prior(age)

    jumps, explained, pre_slope, pre_var = [], 0.0, 0.0, 0.0
    for tr in sorted(treatments or [], key=lambda t: t.date):
        if tr.kind not in params.treatments:
            raise ValueError(t(f"Tratamiento desconocido: {tr.kind}", f"Unknown treatment: {tr.kind}"))
        dip, _, dslope, dslope_sd = params.treatments[tr.kind]
        if tr.date <= origin:  # already taken before the first lab test: only the slope changes
            pre_slope += dslope
            pre_var += dslope_sd**2
        elif tr.date <= as_of:
            jumps.append((_years(tr.date, origin), tr.kind))
            explained += dip

    comps = params.slope_components(diabetes, p_a2, p_a3)
    runs = [
        _kalman(
            np.array([level0, mean + pre_slope]),
            np.diag([level0_sd**2, sd**2 + pre_var]),
            ms,
            jumps,
            origin,
            as_of,
            age,
            female,
            params,
        )
        for _, mean, sd in comps
    ]
    prior_w = np.array([w for w, _, _ in comps])

    def weights_at(k: int | None) -> np.ndarray:
        """Weight of each group given the lab tests up to the k-th (None: all)."""
        if not ms:
            return prior_w
        index = len(ms) - 1 if k is None else k
        lw = np.log(prior_w) + np.array([r["logliks"][index] for r in runs])
        w = np.exp(lw - lw.max())
        return w / w.sum()

    w = weights_at(None)
    components = [(float(wi), r["m"], r["P"]) for wi, r in zip(w, runs)]

    def moments(index: int) -> tuple[float, float]:
        mean = sum(wi * m[index] for wi, m, _ in components)
        var = sum(wi * (P[index, index] + m[index] ** 2) for wi, m, P in components) - mean**2
        return float(mean), float(np.sqrt(max(var, 1e-9)))

    level, level_sd = moments(0)
    slope, slope_sd = moments(1)
    ahead = np.array([1.0, 5.0])
    noise_5y = params.level_noise**2 * 5.0 + params.slope_noise**2 * 5.0**3 / 3.0
    p_30 = float(
        sum(wi * ndtr((30.0 - ahead @ m) / np.sqrt(ahead @ P @ ahead + noise_5y)) for wi, m, P in components)
    )

    trajectory: list[TrendPoint] = []
    below: list[tuple[date, float]] = []
    for k, obs in enumerate(ms):
        mean = sum(wi * r["smooth"][k][0][0] for wi, r in zip(w, runs))
        var = sum(wi * (r["smooth"][k][1][0, 0] + r["smooth"][k][0][0] ** 2) for wi, r in zip(w, runs)) - mean**2
        sd = float(np.sqrt(max(var, 0.0)))
        trajectory.append(TrendPoint(obs.date, float(mean), float(mean - 1.2816 * sd), float(mean + 1.2816 * sd)))
        below.append((obs.date, float(weights_at(k) @ np.array([r["below"][k] for r in runs]))))

    trend = EgfrTrend(
        as_of=as_of,
        n=len(ms),
        span_years=_years(ms[-1].date, ms[0].date) if ms else 0.0,
        level=level,
        level_sd=level_sd,
        slope=slope,
        slope_sd=slope_sd,
        p_decline=0.0,
        p_rapid=0.0,
        p_below_60=0.0,
        p_below_30_in_5y=p_30,
        p_fast=float(w[-1]),
        chronic_below_60=False,
        status="sin_datos",
        trajectory=trajectory,
        measured_drop_explained=explained,
        components=components,
    )
    trend.p_decline, trend.p_rapid = float(trend._cdf(1, -3.0)), float(trend._cdf(1, -5.0))
    trend.p_below_60 = trend.p_below(60.0)
    sure = [d for d, p in below if p >= 0.9]
    trend.chronic_below_60 = bool(sure) and (sure[-1] - sure[0]).days >= 90
    if not ms:
        trend.status = "sin_datos"
    elif len(ms) < 2 or trend.span_years < 0.5:
        trend.status = "insuficiente"
    elif trend.p_rapid >= 0.8:
        trend.status = "descenso_rapido"
    elif trend.p_decline >= 0.8:
        trend.status = "descenso"
    elif trend.p_decline <= 0.2:
        trend.status = "estable"
    else:
        trend.status = "incierto"
    return trend


def simulate_trajectory(
    dates: list[date],
    level0: float,
    slope: float,
    age: float,
    female: bool,
    rng,
    treatments: list[TreatmentStart] | None = None,
    params: TrendParams | None = None,
    source: str = LAB,
) -> list[EgfrMeasurement]:
    """Lab tests simulated from the model itself (for tests and simulation validation)."""
    params = params or TrendParams()
    origin = dates[0]
    events = sorted(
        [(d, "") for d in dates] + [(t.date, t.kind) for t in (treatments or []) if t.date > origin],
        key=lambda e: e[0],
    )
    level, s, last, out = level0, slope, origin, []
    for d, kind in events:
        dt = max(_years(d, last), 0.0)
        level += s * dt + params.level_noise * np.sqrt(dt) * rng.standard_normal()
        s += params.slope_noise * np.sqrt(dt) * rng.standard_normal()
        last = d
        if kind:
            dip, dip_sd, dslope, dslope_sd = params.treatments[kind]
            level += dip + dip_sd * rng.standard_normal()
            s += dslope + dslope_sd * rng.standard_normal()
        else:
            sd = params.measurement_sd(max(level, 5.0), age, female, source)
            out.append(EgfrMeasurement(d, float(max(level + sd * rng.standard_normal(), 3.0)), source))
    return out


def _es(v: float, signed: bool = False) -> str:
    """Number with one decimal (decimal comma in Spanish)."""
    text = f"{v:+.1f}" if signed else f"{v:.1f}"
    return t(text.replace(".", ","), text)


def describe(trend: EgfrTrend) -> str:
    lo, hi = trend.interval("level")
    slo, shi = trend.interval("slope")
    lines = [
        t(
            f"FG actual: {trend.level:.0f} ml/min/1,73 m² (80 %: {lo:.0f}-{hi:.0f}) con {trend.n} analíticas en "
            f"{_es(trend.span_years)} años",
            f"Current eGFR: {trend.level:.0f} ml/min/1.73 m² (80%: {lo:.0f}-{hi:.0f}) from {trend.n} lab tests over "
            f"{_es(trend.span_years)} years",
        ),
        t(
            f"Tendencia: {STATUS_TEXT[trend.status]}; pendiente {_es(trend.slope, True)} al año "
            f"(80 %: {_es(slo, True)} a {_es(shi, True)})",
            f"Trend: {STATUS_TEXT[trend.status]}; slope {_es(trend.slope, True)} per year "
            f"(80%: {_es(slo, True)} to {_es(shi, True)})",
        ),
        t(
            f"P(descenso de más de 3 al año) = {trend.p_decline:.0%} · P(más de 5 al año) = {trend.p_rapid:.0%} · "
            f"P(FG < 30 en 5 años) = {trend.p_below_30_in_5y:.0%}",
            f"P(decline of more than 3 per year) = {trend.p_decline:.0%} · P(more than 5 per year) = {trend.p_rapid:.0%} · "
            f"P(eGFR < 30 within 5 years) = {trend.p_below_30_in_5y:.0%}",
        ),
    ]
    if trend.measured_drop_explained:
        drop = trend.measured_drop_explained
        lines.append(
            t(
                f"Se ha descontado la caída esperada al iniciar el tratamiento ({drop:+.0f} ml/min).",
                f"The expected dip on starting treatment has been discounted ({drop:+.0f} ml/min).",
            )
        )
    return "\n".join(lines)
