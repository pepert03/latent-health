"""Albuminuria filter for one patient.

Walks through the patient's urine samples in order (grid Bayesian filter with a random walk
between dates) and returns the current state with its uncertainty, the clinical decision and
how much another sample would help.

Accepts lab samples (``UrineSample``) and home strips (``StripSample``), each with its context
answers. If eGFR is not measured, its distribution can be passed (``egfr_mixture``): the filter
is solved for each value and mixed, so albuminuria and eGFR are no longer treated as
independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from .context import SampleContext, spike_offset
from .model import (
    A2_THRESHOLD,
    A3_THRESHOLD,
    FIRST_MORNING,
    RANDOM,
    AlbuminuriaParams,
    Observations,
    covariates,
    dilution,
    log_obs,
    log_prior,
    make_grid,
)
from ..i18n import Labels, fmt_date, fmt_short_date, t
from .strip import StripSample, StripSpec, outcome_table

# Keys are machine status values (kept in Spanish, shared with the web API); values are display labels.
STATUS_LABELS = Labels(
    {
        "sin_medir": ("Sin medir", "Not measured"),
        "descartada": ("Descartada", "Ruled out"),
        "dudosa": ("Dudosa", "Doubtful"),
        "pendiente_cronicidad": ("Muy probable, falta cronicidad", "Very likely, chronicity pending"),
        "confirmada": ("Confirmada", "Confirmed"),
    }
)
SAMPLE_LABELS = Labels(
    {
        FIRST_MORNING: ("primera orina de la mañana", "first morning urine"),
        RANDOM: ("muestra aleatoria", "random sample"),
    }
)


def format_date(day: date, weekday: bool = True) -> str:
    """Long date in the current language (thin wrapper over ``i18n.fmt_date``)."""
    return fmt_date(day, weekday=weekday)


@dataclass
class UrineSample:
    """Sample measured in the lab (quantitative)."""

    date: date
    uacr: float  # mg/g; if censored=True it is the upper limit ("< value")
    sample_type: str = FIRST_MORNING
    censored: bool = False
    creatinine_mg_dl: float | None = None  # urine creatinine of this sample (dilution)
    context: SampleContext | None = None  # patient answers about the sample


Sample = UrineSample | StripSample


@dataclass
class Patient:
    age: float
    female: bool
    diabetes: bool
    egfr: float | None = None
    samples: list[Sample] = field(default_factory=list)


@dataclass
class TrajectoryPoint:
    date: date
    median: float  # mg/g
    low: float  # 10th percentile
    high: float  # 90th percentile
    p_a2_plus: float  # smoothed: uses all samples


@dataclass
class EgfrComponent:
    """Albuminuria conditional on one eGFR value."""

    egfr: float
    weight: float  # probability of that value after seeing the urine samples
    p_a1: float
    p_a2: float
    p_a3: float


@dataclass
class AlbuminuriaAssessment:
    as_of: date | None
    p_a1: float
    p_a2: float
    p_a3: float
    median: float
    low: float
    high: float
    status: str
    category: str
    action: str
    chronicity_met: bool
    next_sample_resolves: dict[str, float]
    trajectory: list[TrajectoryPoint]
    repeat_from: date | None = None  # date from which a high sample meets chronicity
    log_evidence: float = 0.0  # log-likelihood of the samples (to compare hypotheses)
    egfr_components: list[EgfrComponent] = field(default_factory=list)
    belief: np.ndarray | None = field(default=None, repr=False)  # current distribution on the grid

    @property
    def p_a2_plus(self) -> float:
        return self.p_a2 + self.p_a3


class AlbuminuriaFilter:
    """Decision thresholds: ``confirm`` and ``discard`` on P(true UACR ≥ 30).

    Chronicity (KDIGO criterion of more than 3 months) requires two time points at least
    ``chronicity_days`` apart at which, with the samples available up to then, P(≥ 30) is at
    least ``chronicity_level``.
    """

    def __init__(
        self,
        params: AlbuminuriaParams,
        grid_n: int = 400,
        confirm: float = 0.95,
        discard: float = 0.05,
        chronicity_days: int = 90,
        chronicity_level: float = 0.9,
    ):
        self.p = params
        self.x, self.dx = make_grid(grid_n)
        self.confirm, self.discard = confirm, discard
        self.chronicity_days, self.chronicity_level = chronicity_days, chronicity_level
        self._a2 = self.x >= np.log(A2_THRESHOLD)
        self._a3 = self.x >= np.log(A3_THRESHOLD)
        self._tables: dict = {}

    # --- building blocks ---
    @staticmethod
    def covariates(patient: Patient) -> np.ndarray:
        return covariates(patient.age, patient.female, patient.diabetes, patient.egfr)

    def prior(self, patient: Patient) -> np.ndarray:
        return self._prior(self.covariates(patient))

    def _prior(self, z: np.ndarray) -> np.ndarray:
        lp = log_prior(self.p, z, self.x)[0]
        w = np.exp(lp - lp.max())
        return w / w.sum()

    def transition(self, days: float) -> np.ndarray | None:
        """K[i, j] = p(x_i after ``days`` days | x_j). None if the change is negligible."""
        sd = self.p.drift_sd_per_year * np.sqrt(max(days, 0.0) / 365.25)
        if sd < self.dx / 4:
            return None
        K = np.exp(-0.5 * ((self.x[:, None] - self.x[None, :]) / sd) ** 2)
        return K / K.sum(axis=0, keepdims=True)

    @staticmethod
    def _context_offset(context: SampleContext | None, z: np.ndarray) -> float:
        age, female = 50.0 + 15.0 * float(z[0, 0]), bool(z[0, 1] > 0.5)
        return spike_offset(context, female, age)

    def strip_table(self, spec: StripSpec, z: np.ndarray, sample_type: str, offset: float = 0.0) -> np.ndarray:
        """P(reading | x) for every possible strip reading for this patient (cached)."""
        key = (spec, sample_type, round(offset, 4), z.tobytes())
        if key not in self._tables:
            if len(self._tables) > 512:
                self._tables.clear()
            self._tables[key] = outcome_table(self.p, z, sample_type, spec, self.x, spike_offset=offset)
        return self._tables[key]

    def log_likelihood(self, sample: Sample, z: np.ndarray) -> np.ndarray:
        """log p(sample | x) on the grid."""
        offset = self._context_offset(sample.context, z)
        if isinstance(sample, StripSample):
            a, c = sample.outcome
            return np.log(self.strip_table(sample.spec, z, sample.sample_type, offset)[a, c])
        u = dilution([np.nan if sample.creatinine_mg_dl is None else sample.creatinine_mg_dl])
        obs = Observations(np.array([np.log(sample.uacr)]), np.array([sample.censored]), sample.sample_type, u, offset)
        return log_obs(self.p, obs, z, self.x)[0]

    def likelihood(self, sample: Sample, z: np.ndarray) -> np.ndarray:
        lo = self.log_likelihood(sample, z)
        return np.exp(lo - lo.max())

    def _point(self, day: date, w: np.ndarray) -> TrajectoryPoint:
        cdf = np.cumsum(w)
        q = np.exp(np.interp([0.1, 0.5, 0.9], cdf, self.x))
        return TrajectoryPoint(day, median=q[1], low=q[0], high=q[2], p_a2_plus=float(w[self._a2].sum()))

    def p_a2_plus(self, w: np.ndarray) -> float:
        return float(w[self._a2].sum())

    def resolve_probability(
        self,
        belief: np.ndarray,
        z: np.ndarray,
        sample_type: str,
        days_ahead: float = 0,
        strip: StripSpec | None = None,
    ) -> float:
        """P(one more sample leaves P(≥ 30) above ``confirm`` or below ``discard``).

        With ``strip`` the sample is a strip of that kind; without it, a lab sample.
        """
        K = self.transition(days_ahead)
        b = belief if K is None else K @ belief
        if strip is not None:
            table = self.strip_table(strip, z, sample_type)
            dens = table.reshape(-1, self.x.size)  # one row per possible reading
        else:
            y = self.x  # possible results, on the same grid
            zr = np.repeat(z, y.size, axis=0)
            quantiles = self.p.dilution_quantiles[sample_type]  # the future sample's dilution is unknown
            dens = sum(
                np.exp(log_obs(self.p, Observations(y, np.zeros(y.size, bool), sample_type, np.full(y.size, q)), zr, self.x))
                for q in quantiles
            ) / len(quantiles)
        py = dens @ b
        pa2 = (dens[:, self._a2] @ b[self._a2]) / np.maximum(py, 1e-300)
        resolved = (pa2 >= self.confirm) | (pa2 <= self.discard)
        return float((py * resolved).sum() / py.sum())

    # --- full assessment ---
    def _run(self, z: np.ndarray, samples: list[Sample], as_of: date | None):
        """Filtering and smoothing for one covariate set. Returns what is needed to mix hypotheses."""
        belief = self._prior(z)
        if not samples:
            return {"current": belief, "filtered": [], "smoothed": [], "log_ev": np.zeros(0)}
        filtered, kernels, liks, log_ev = [], [], [], []
        previous, total = samples[0].date, 0.0
        for s in samples:
            K = self.transition((s.date - previous).days)
            lo = self.log_likelihood(s, z)
            peak = lo.max()
            lik = np.exp(lo - peak)
            belief = (belief if K is None else K @ belief) * lik
            norm = belief.sum()
            belief = belief / norm
            total += peak + np.log(norm)
            filtered.append(belief)
            kernels.append(K)
            liks.append(lik)
            log_ev.append(total)
            previous = s.date

        # Backward pass (smoothing) for the trajectory.
        smoothed = [None] * len(samples)
        smoothed[-1] = filtered[-1]
        message = np.ones_like(belief)
        for k in range(len(samples) - 2, -1, -1):
            K = kernels[k + 1]
            m = liks[k + 1] * message
            message = m if K is None else K.T @ m
            message /= message.sum()
            g = filtered[k] * message
            smoothed[k] = g / g.sum()

        end = as_of or samples[-1].date
        K = self.transition((end - samples[-1].date).days)
        current = belief if K is None else K @ belief
        return {"current": current, "filtered": filtered, "smoothed": smoothed, "log_ev": np.asarray(log_ev)}

    def assess(
        self,
        patient: Patient,
        as_of: date | None = None,
        egfr_mixture: list[tuple[float, float]] | None = None,
        update_weights: bool = True,
        detail: bool = True,
    ) -> AlbuminuriaAssessment:
        """The patient's albuminuria state.

        ``egfr_mixture`` is the eGFR distribution when it is not measured: (value, probability)
        pairs. With ``update_weights`` those probabilities are updated with what the urine
        samples say (Bayes' rule); without it they are taken as given. ``detail=False`` skips
        computing how much another sample would help, the slowest part (for assessing many
        people at once).
        """
        samples = sorted(patient.samples, key=lambda s: s.date)
        mixture = egfr_mixture or [(patient.egfr, 1.0)]
        zs = [covariates(patient.age, patient.female, patient.diabetes, e) for e, _ in mixture]
        prior_w = np.asarray([w for _, w in mixture], dtype=float)
        prior_w = prior_w / prior_w.sum()
        runs = [self._run(z, samples, as_of) for z in zs]

        n = len(samples)
        if n and update_weights:
            log_ev = np.stack([r["log_ev"] for r in runs], axis=1)  # (samples, hypotheses)
            lw = np.log(prior_w)[None, :] + log_ev
            peak = lw.max(axis=1, keepdims=True)
            weights = np.exp(lw - peak)
            evidence = float(peak[-1, 0] + np.log(weights[-1].sum()))
            weights = weights / weights.sum(axis=1, keepdims=True)
        else:
            weights = np.tile(prior_w, (max(n, 1), 1))
            evidence = float(prior_w @ np.asarray([r["log_ev"][-1] for r in runs])) if n else 0.0
        final_w = weights[-1]
        current = sum(w * r["current"] for w, r in zip(final_w, runs))
        z_main = zs[int(np.argmax(final_w))]
        components = []
        if len(mixture) > 1:
            for (e, _), w, r in zip(mixture, final_w, runs):
                c = r["current"]
                p_a3 = float(c[self._a3].sum())
                p_a2p = float(c[self._a2].sum())
                components.append(EgfrComponent(float(e), float(w), 1.0 - p_a2p, p_a2p - p_a3, p_a3))

        if not samples:
            return self._summarize(current, z_main, as_of, "sin_medir", False, None, [], evidence, components, detail)

        filtered = [sum(weights[k, g] * runs[g]["filtered"][k] for g in range(len(runs))) for k in range(n)]
        smoothed = [sum(final_w[g] * runs[g]["smoothed"][k] for g in range(len(runs))) for k in range(n)]
        trajectory = [self._point(s.date, w) for s, w in zip(samples, smoothed)]
        as_of = as_of or samples[-1].date

        # Chronicity: two time points with high P(≥30), each using only what was measured up to then.
        high = [s.date for s, w in zip(samples, filtered) if self.p_a2_plus(w) >= self.chronicity_level]
        chronic = bool(high) and (high[-1] - high[0]).days >= self.chronicity_days
        repeat_from = high[0] + timedelta(days=self.chronicity_days) if high else None

        p = self.p_a2_plus(current)
        if p <= self.discard:
            status = "descartada"
        elif p >= self.confirm:
            status = "confirmada" if chronic else "pendiente_cronicidad"
        else:
            status = "dudosa"
        return self._summarize(
            current, z_main, as_of, status, chronic, repeat_from, trajectory, evidence, components, detail
        )

    def _summarize(
        self, w, z, as_of, status, chronic, repeat_from, trajectory, evidence=0.0, components=None, detail=True
    ) -> AlbuminuriaAssessment:
        point = self._point(as_of, w)
        p_a3 = float(w[self._a3].sum())
        p_a2 = point.p_a2_plus - p_a3
        p_a1 = 1.0 - point.p_a2_plus
        category = ("A1", "A2", "A3")[int(np.argmax([p_a1, p_a2, p_a3]))]
        a2_or_a3 = "A3" if p_a3 > p_a2 else "A2"
        resolves = {}
        if detail and status in ("sin_medir", "dudosa"):
            resolves = {kind: self.resolve_probability(w, z, kind) for kind in (FIRST_MORNING, RANDOM)}

        if status == "sin_medir":
            action = t(
                f"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: "
                f"{point.p_a2_plus:.0%}.",
                f"Order UACR on a first morning urine sample. Probability of albuminuria before measuring: "
                f"{point.p_a2_plus:.0%}.",
            )
        elif status == "descartada":
            action = t(
                "Sin albuminuria. Repetir el cribado según la guía (anual en diabetes).",
                "No albuminuria. Repeat screening as per guidelines (yearly in diabetes).",
            )
        elif status == "dudosa":
            action = t(
                "Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina.",
                "Repeat on a first morning urine sample, avoiding intense exercise, fever or urinary tract infection.",
            )
            if resolves:
                action += t(
                    f" Probabilidad de que resuelva la duda: {resolves[FIRST_MORNING]:.0%} "
                    f"(con una muestra aleatoria, {resolves[RANDOM]:.0%}).",
                    f" Probability that it settles the doubt: {resolves[FIRST_MORNING]:.0%} "
                    f"(with a random sample, {resolves[RANDOM]:.0%}).",
                )
        elif status == "pendiente_cronicidad":
            if not repeat_from:
                when = ""
            else:
                when = t(f" a partir del {repeat_from:%d/%m/%Y}", f" from {fmt_date(repeat_from, weekday=False)}")
            action = t(
                f"Albuminuria {a2_or_a3} muy probable. Repetir{when} para cumplir el criterio de "
                "cronicidad (más de 3 meses).",
                f"{a2_or_a3} albuminuria very likely. Repeat{when} to meet the chronicity "
                "criterion (more than 3 months).",
            )
        else:
            action = t(
                f"Albuminuria persistente {a2_or_a3}: registrar ERC (categoría {a2_or_a3}) y revisar el "
                "tratamiento nefroprotector según la guía.",
                f"Persistent {a2_or_a3} albuminuria: record CKD (category {a2_or_a3}) and review "
                "kidney-protective treatment as per guidelines.",
            )
        return AlbuminuriaAssessment(
            as_of=as_of,
            p_a1=p_a1,
            p_a2=p_a2,
            p_a3=p_a3,
            median=point.median,
            low=point.low,
            high=point.high,
            status=status,
            category=category,
            action=action,
            chronicity_met=chronic,
            next_sample_resolves=resolves,
            trajectory=trajectory,
            repeat_from=repeat_from,
            log_evidence=evidence,
            egfr_components=components or [],
            belief=w,
        )


def describe(assessment: AlbuminuriaAssessment) -> str:
    """Text summary for the clinician."""
    a = assessment
    lines = [
        t(f"Estado: {STATUS_LABELS[a.status]}", f"Status: {STATUS_LABELS[a.status]}"),
        t(
            f"UACR verdadero estimado: {a.median:.0f} mg/g (80 %: {a.low:.0f}-{a.high:.0f})",
            f"Estimated true UACR: {a.median:.0f} mg/g (80%: {a.low:.0f}-{a.high:.0f})",
        ),
        t("Probabilidades", "Probabilities") + f": A1 {a.p_a1:.0%} · A2 {a.p_a2:.0%} · A3 {a.p_a3:.0%}",
        t(f"Acción: {a.action}", f"Action: {a.action}"),
    ]
    if a.trajectory:
        lines.append(t("Trayectoria (con todas las muestras):", "Trajectory (using all samples):"))
        for point in a.trajectory:
            lines.append(
                f"  {fmt_short_date(point.date)}: {point.median:.0f} mg/g ({point.low:.0f}-{point.high:.0f}), "
                f"P(≥30) = {point.p_a2_plus:.0%}"
            )
    return "\n".join(lines)
