"""Tendencia del filtrado glomerular (FG): nivel y pendiente con las analíticas previas.

Un filtro de Kalman sobre el estado (nivel, pendiente) recorre las creatininas del paciente.
Sirve para ver "la función renal que va deteriorándose poco a poco sin que duela":

- separa el descenso real del ruido de la creatinina (variación biológica y analítica), que
  entre dos analíticas puede mover el FG varios puntos sin que pase nada;
- usa los **tratamientos como entrada conocida**: al empezar un iSGLT2 o un IECA/ARA-II el FG
  cae unos puntos en las primeras semanas y luego baja más despacio. Sin esa entrada, esa
  caída esperada se confunde con un descenso rápido;
- parte de que la mayoría pierde FG despacio y unos pocos deprisa (más con diabetes o
  albuminuria): son dos filtros, uno por grupo, que se mezclan según lo que digan los datos;
- da probabilidades: de descenso (pendiente < -3 ml/min/1,73 m² al año), de descenso rápido
  (< -5, criterio KDIGO), de estar por debajo de 60 y de llegar a menos de 30 en cinco años.

**Los parámetros son supuestos tomados de la literatura, no están ajustados**: NHANES es
transversal y no tiene analíticas repetidas. El modelo está comprobado solo en simulación
(``scripts/validate_trend.py``); antes de usarlo hay que ajustarlo con datos longitudinales
de atención primaria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
from scipy.special import ndtr
from scipy.stats import norm

G_EDGES = (90.0, 60.0, 45.0, 30.0, 15.0)
G_LABELS = ("G1", "G2", "G3a", "G3b", "G4", "G5")
LAB, CAPILLARY = "laboratorio", "capilar"


@dataclass
class EgfrMeasurement:
    date: date
    egfr: float  # ml/min/1,73 m² (CKD-EPI 2021)
    source: str = LAB  # "laboratorio" o "capilar" (punción en el dedo, más ruido)
    above: bool = False  # el informe solo dice "> valor" (muchos laboratorios cortan en 90)


@dataclass
class TreatmentStart:
    date: date
    kind: str  # "isglt2" o "ieca_ara2"


def _default_treatments() -> dict:
    # (caída inicial media, su desviación, cambio de la pendiente, su desviación)
    return {"isglt2": (-3.0, 2.0, 1.0, 0.7), "ieca_ara2": (-2.5, 2.5, 0.5, 0.7)}


@dataclass(frozen=True)
class TrendParams:
    # Pendiente antes de ver datos, en ml/min/1,73 m² por año. Es una mezcla de dos grupos:
    # la mayoría pierde FG despacio y unos pocos lo pierden deprisa. Con una sola normal los
    # descensos rápidos quedarían como casi imposibles y el filtro tardaría años en creérselos.
    stable_slope: tuple[float, float] = (-0.8, 1.2)  # media y desviación del grupo estable
    fast_slope: tuple[float, float] = (-4.5, 2.5)  # grupo que progresa deprisa
    fast_base: float = 0.05  # proporción del grupo rápido sin diabetes ni albuminuria
    fast_logit_diabetes: float = 0.9
    fast_logit_a2: float = 1.3  # albuminuria 30-300 mg/g
    fast_logit_a3: float = 2.6  # albuminuria > 300 mg/g
    # Dinámica: cuánto se apartan el nivel y la pendiente de la recta, por raíz de año.
    level_noise: float = 1.5
    slope_noise: float = 0.4
    # Medida: coeficiente de variación de la creatinina (biológica + analítica).
    creatinine_cv_lab: float = 0.055
    creatinine_cv_capillary: float = 0.11
    min_sd: float = 1.5
    treatments: dict = field(default_factory=_default_treatments)

    def p_fast(self, diabetes: bool, p_a2: float, p_a3: float) -> float:
        """Proporción esperada de progresadores rápidos entre pacientes como este."""
        logit = (
            np.log(self.fast_base / (1.0 - self.fast_base))
            + self.fast_logit_diabetes * bool(diabetes)
            + self.fast_logit_a2 * p_a2
            + self.fast_logit_a3 * p_a3
        )
        return float(1.0 / (1.0 + np.exp(-logit)))

    def slope_components(self, diabetes: bool, p_a2: float, p_a3: float) -> list[tuple[float, float, float]]:
        """Grupos del prior de la pendiente: (peso, media, desviación)."""
        fast = self.p_fast(diabetes, p_a2, p_a3)
        return [(1.0 - fast, *self.stable_slope), (fast, *self.fast_slope)]

    def prior_slope(self, diabetes: bool, p_a2: float, p_a3: float) -> tuple[float, float]:
        """Media y desviación de la pendiente antes de ver datos (de la mezcla entera)."""
        comps = self.slope_components(diabetes, p_a2, p_a3)
        mean = sum(w * m for w, m, _ in comps)
        var = sum(w * (sd**2 + m**2) for w, m, sd in comps) - mean**2
        return float(mean), float(np.sqrt(var))

    def measurement_sd(self, egfr: float, age: float, female: bool, source: str = LAB) -> float:
        """Desviación típica del FG estimado por el ruido de la creatinina (método delta sobre CKD-EPI)."""
        knee = 142.0 * 0.9938**age * (1.012 if female else 1.0)  # FG con la creatinina en el punto κ
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
    n: int  # analíticas usadas
    span_years: float
    level: float
    level_sd: float
    slope: float  # ml/min/1,73 m² por año
    slope_sd: float
    p_decline: float  # P(pendiente < -3)
    p_rapid: float  # P(pendiente < -5)
    p_below_60: float
    p_below_30_in_5y: float
    p_fast: float  # probabilidad de pertenecer al grupo que progresa deprisa
    chronic_below_60: bool  # dos analíticas separadas más de 3 meses con FG < 60 muy probable
    status: str  # "sin_datos", "insuficiente", "estable", "descenso", "descenso_rapido", "incierto"
    trajectory: list[TrendPoint]
    measured_drop_explained: float = 0.0  # caída esperada por los tratamientos iniciados (ml/min)
    # Mezcla de normales del estado actual: (peso, media [nivel, pendiente], covarianza 2x2).
    components: list = field(default_factory=list, repr=False)

    def _cdf(self, index: int, value):
        """P(nivel o pendiente ≤ valor) con la mezcla; ``value`` puede ser un array."""
        value = np.asarray(value, dtype=float)
        return sum(w * ndtr((value - m[index]) / np.sqrt(P[index, index])) for w, m, P in self.components)

    def interval(self, what: str = "level", q: float = 0.8) -> tuple[float, float]:
        """Intervalo central de probabilidad ``q`` del nivel o de la pendiente."""
        index = 0 if what == "level" else 1
        mean, sd = (self.level, self.level_sd) if index == 0 else (self.slope, self.slope_sd)
        grid = np.linspace(mean - 8 * sd, mean + 8 * sd, 201)
        cdf = self._cdf(index, grid)
        lo, hi = np.interp([(1 - q) / 2, (1 + q) / 2], cdf, grid)
        return float(lo), float(hi)

    def p_below(self, threshold: float) -> float:
        return float(self._cdf(0, threshold))

    def category_probs(self) -> dict[str, float]:
        """Probabilidad de cada categoría G de KDIGO con la incertidumbre del nivel actual."""
        below = [self.p_below(e) for e in G_EDGES]
        probs = np.clip(np.r_[1.0 - below[0], -np.diff(below), below[-1]], 0.0, 1.0)
        return dict(zip(G_LABELS, (probs / probs.sum()).tolist()))


STATUS_TEXT = {
    "sin_datos": "sin analíticas",
    "insuficiente": "pocas analíticas para ver la tendencia",
    "estable": "estable",
    "descenso": "descenso sostenido",
    "descenso_rapido": "descenso rápido",
    "incierto": "tendencia dudosa",
}


def default_level_prior(age: float) -> tuple[float, float]:
    """FG esperado por la edad cuando no hay nada mejor (prior débil)."""
    return float(np.clip(100.0 - 0.85 * (age - 40.0), 45.0, 110.0)), 20.0


def _years(d: date, origin: date) -> float:
    return (d - origin).days / 365.25


def _advance(m, P, t_from, t_to, jumps, params: TrendParams):
    """Lleva el estado de t_from a t_to aplicando los inicios de tratamiento que caen en medio.

    Devuelve la media y la covarianza predichas y la matriz F total (para el suavizado).
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
    """Filtro y suavizado de Kalman para un grupo del prior. Devuelve también la verosimilitud acumulada."""
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
        if obs.above:  # solo se sabe que la medida es mayor: actualización con normal truncada
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

    # Suavizado hacia atrás (Rauch-Tung-Striebel) para dibujar la trayectoria.
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
    """Nivel y pendiente actuales del FG de un paciente.

    ``prior_level`` es (media, desviación) del FG antes de ver sus analíticas; por defecto, el
    esperado por la edad. ``p_a2`` y ``p_a3`` son las probabilidades de albuminuria del filtro:
    con albuminuria es más probable que el FG baje deprisa.
    """
    params = params or TrendParams()
    ms = sorted(measurements, key=lambda m: m.date)
    as_of = as_of or (ms[-1].date if ms else date.today())
    origin = ms[0].date if ms else as_of
    level0, level0_sd = prior_level or default_level_prior(age)

    jumps, explained, pre_slope, pre_var = [], 0.0, 0.0, 0.0
    for tr in sorted(treatments or [], key=lambda t: t.date):
        if tr.kind not in params.treatments:
            raise ValueError(f"Tratamiento desconocido: {tr.kind}")
        dip, _, dslope, dslope_sd = params.treatments[tr.kind]
        if tr.date <= origin:  # ya lo tomaba antes de la primera analítica: solo cambia la pendiente
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
        """Peso de cada grupo con las analíticas hasta la k-ésima (None: todas)."""
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
    """Analíticas simuladas con el propio modelo (para pruebas y para la validación en simulación)."""
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
    """Número con un decimal y coma decimal."""
    return (f"{v:+.1f}" if signed else f"{v:.1f}").replace(".", ",")


def describe(trend: EgfrTrend) -> str:
    lo, hi = trend.interval("level")
    slo, shi = trend.interval("slope")
    lines = [
        f"FG actual: {trend.level:.0f} ml/min/1,73 m² (80 %: {lo:.0f}-{hi:.0f}) con {trend.n} analíticas en "
        f"{_es(trend.span_years)} años",
        f"Tendencia: {STATUS_TEXT[trend.status]}; pendiente {_es(trend.slope, True)} al año "
        f"(80 %: {_es(slo, True)} a {_es(shi, True)})",
        f"P(descenso de más de 3 al año) = {trend.p_decline:.0%} · P(más de 5 al año) = {trend.p_rapid:.0%} · "
        f"P(FG < 30 en 5 años) = {trend.p_below_30_in_5y:.0%}",
    ]
    if trend.measured_drop_explained:
        lines.append(
            f"Se ha descontado la caída esperada al iniciar el tratamiento ({trend.measured_drop_explained:+.0f} ml/min)."
        )
    return "\n".join(lines)
