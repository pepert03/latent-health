"""Probabilistic model of albuminuria.

Hidden variable ``x``: log of the true UACR (mg/g) on the first-morning-urine scale, the
sample recommended by guidelines.

Prior (what is known about the patient before measuring): mixture of K ordered normals
(normal, elevated, very elevated) whose weights and means depend on the covariates ``z``
(age, sex, diabetes, eGFR)::

    x | z ~ Σ_k π_k(z) N(μ_k + β·z, τ_k²),   π(z) = softmax(α_k + γ_k·z)

Measurement (each urine sample, in log). The residual ``r = y - x - b_type(x)`` is a mixture::

    r ~ (1 - ρ) · Student t(ν, 0, s)    usual variation
        + ρ     · Student t(ν_e, δ, ω)  transient elevation (heavy tail)
    log s     = log σ_type + η·z + η_u·u
    logit ρ   = c_type + κ·z + λ_u·u

where ``u = log(urine creatinine / 100 mg/dl)`` measures how diluted the sample is (in very
dilute urine the ratio is less reliable). ``b = 0`` for first morning urine and, for a
random sample, ``b(x) = b0 + b1 · (x - log 30)`` with x clipped between 2 and 300 mg/g: the
random sample's excess grows with albuminuria. The transient elevation captures high
samples from passing causes (exercise, posture, fever, infection, blood). If albumin is
below the detection limit, all we know is ``y < log(limit)`` (censoring).

Dynamics (assumption from the literature, cannot be fitted with NHANES): the true level
follows a random walk, ``x(t + Δt) = x(t) + N(0, q² Δt)`` with Δt in years.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.special import expit, gammaln, logsumexp, stdtr

FIRST_MORNING = "first_morning"
RANDOM = "random"
SAMPLE_TYPES = (FIRST_MORNING, RANDOM)

A2_THRESHOLD = 30.0  # mg/g
A3_THRESHOLD = 300.0  # mg/g
N_COVARIATES = 4  # age, female, diabetes, eGFR
N_COMPONENTS = 3  # prior components

_LOG_2PI = np.log(2.0 * np.pi)
_LOG_2, _LOG_30, _LOG_300 = np.log(2.0), np.log(30.0), np.log(300.0)


def bias_slope_term(x):
    """Level centered at 30 mg/g and clipped between 2 and 300 (outside that range the excess does not change)."""
    return np.clip(x, _LOG_2, _LOG_300) - _LOG_30


def dilution(ucr_mg_dl) -> np.ndarray:
    """u = log(urine creatinine / 100 mg/dl), clipped; 0 (typical) if unknown."""
    ucr = np.asarray(ucr_mg_dl, dtype=float)
    u = np.log(np.clip(ucr, 8.0, 600.0) / 100.0)
    return np.where(np.isnan(u), 0.0, u)


def covariates(age, female, diabetes, egfr=None) -> np.ndarray:
    """(N, 4) matrix of standardized covariates. Without eGFR, 90 (normal) is assumed."""
    age = np.atleast_1d(np.asarray(age, dtype=float))
    female = np.broadcast_to(np.asarray(female, dtype=float), age.shape)
    diabetes = np.broadcast_to(np.asarray(diabetes, dtype=float), age.shape)
    if egfr is None:
        egfr = np.full(age.shape, 90.0)
    egfr = np.broadcast_to(np.asarray(egfr, dtype=float), age.shape)
    egfr = np.where(np.isnan(egfr), 90.0, egfr)
    return np.column_stack(
        [(age - 50.0) / 15.0, female, diabetes, (np.clip(egfr, 15.0, 120.0) - 90.0) / 20.0]
    )


def make_grid(n: int = 400, lo: float = 0.05, hi: float = 30000.0):
    """Uniform grid in log-UACR and its step."""
    x = np.linspace(np.log(lo), np.log(hi), n)
    return x, x[1] - x[0]


@dataclass
class Observations:
    """One sample per patient (arrays of length N), all of the same type."""

    y: np.ndarray  # log-UACR; NaN if no sample; if censored, log of the limit
    censored: np.ndarray
    sample_type: str
    u: np.ndarray  # sample dilution (see ``dilution``)
    # Shift of the transient-elevation logit from the sample context
    # (exercise, fever, menstruation...; see ``context``). 0 if nothing is known.
    spike_offset: np.ndarray | float = 0.0

    @classmethod
    def from_uacr(cls, uacr, sample_type, censored=None, ucr=None) -> "Observations":
        uacr = np.atleast_1d(np.asarray(uacr, dtype=float))
        censored = np.zeros(uacr.shape, bool) if censored is None else np.asarray(censored, bool)
        u = np.zeros(uacr.shape) if ucr is None else dilution(ucr)
        return cls(np.log(uacr), censored, sample_type, u)


_FIELDS = (
    ("mu_low", 1),
    ("log_gaps", N_COMPONENTS - 1),
    ("log_taus", N_COMPONENTS),
    ("beta", N_COVARIATES),
    ("alphas", N_COMPONENTS - 1),
    ("gammas", (N_COMPONENTS - 1) * N_COVARIATES),
    ("bias_random", 1),
    ("bias_random_slope", 1),
    ("log_sigma_morning", 1),
    ("log_sigma_random", 1),
    ("eta", N_COVARIATES),
    ("eta_dilution", 1),
    ("log_nu", 1),
    ("logit_spike_random", 1),
    ("logit_spike_morning", 1),
    ("kappa", N_COVARIATES),
    ("kappa_dilution", 1),
    ("log_spike_size", 1),
    ("log_spike_sd", 1),
    ("log_nu_spike", 1),
)

NO_SPIKES = {
    "logit_spike_random": -30.0,
    "logit_spike_morning": -30.0,
    "log_spike_size": 0.0,
    "log_spike_sd": float(np.log(0.5)),
}


@dataclass
class AlbuminuriaParams:
    # Population prior
    mu_low: float  # mean of the lowest component
    log_gaps: list[float]  # μ_k = μ_{k-1} + exp(log_gap): ordered means
    log_taus: list[float]
    beta: list[float]  # common shift of the means by covariates
    alphas: list[float]  # logit of each component vs the first
    gammas: list[float]  # covariate effects on those logits, (K-1) x 4 row-major
    # Measurement: usual variation
    bias_random: float  # random-sample excess (log) at a true level of 30 mg/g
    log_sigma_morning: float
    log_sigma_random: float
    eta: list[float]
    log_nu: float
    bias_random_slope: float = 0.0  # how much that excess grows per unit of log-level
    eta_dilution: float = 0.0
    # Measurement: transient elevations (none by default)
    logit_spike_random: float = NO_SPIKES["logit_spike_random"]
    logit_spike_morning: float = NO_SPIKES["logit_spike_morning"]
    kappa: list[float] = field(default_factory=lambda: [0.0] * N_COVARIATES)
    kappa_dilution: float = 0.0
    log_spike_size: float = NO_SPIKES["log_spike_size"]  # δ: mean size in log
    log_spike_sd: float = NO_SPIKES["log_spike_sd"]  # ω
    log_nu_spike: float = float(np.log(1000.0))  # tail of the elevations (Student t; 1000 ≈ normal)
    # Typical dilution of each sample type (quantiles of u), to predict future samples
    dilution_quantiles: dict = field(default_factory=lambda: {FIRST_MORNING: [0.0], RANDOM: [0.0]})
    # Dynamics: assumed, not fitted (standard deviation of the true change over one year)
    drift_sd_per_year: float = 0.35
    # Recalibration to another population (see ``recalibration``): added to the logit of the
    # elevated prior components. 0 = fitting population (NHANES).
    prior_logit_offset: float = 0.0
    meta: dict = field(default_factory=dict)

    # --- parameter vector (for fitting) ---
    def to_vector(self) -> np.ndarray:
        parts: list[float] = []
        for name, size in _FIELDS:
            value = getattr(self, name)
            parts.extend(value if size > 1 else [value])
        return np.asarray(parts, dtype=float)

    @classmethod
    def from_vector(cls, vector, **extra) -> "AlbuminuriaParams":
        kwargs, i = {}, 0
        for name, size in _FIELDS:
            chunk = vector[i : i + size]
            kwargs[name] = [float(v) for v in chunk] if size > 1 else float(chunk[0])
            i += size
        return cls(**kwargs, **extra)

    @classmethod
    def initial(cls) -> "AlbuminuriaParams":
        """Reasonable starting point for the fit."""
        zeros = [0.0] * N_COVARIATES
        return cls(
            mu_low=np.log(5.0),
            log_gaps=[np.log(1.5), np.log(2.0)][: N_COMPONENTS - 1],
            log_taus=[np.log(0.5), np.log(0.8), np.log(1.2)][:N_COMPONENTS],
            beta=list(zeros),
            alphas=[-2.0, -3.5][: N_COMPONENTS - 1],
            gammas=[0.0] * ((N_COMPONENTS - 1) * N_COVARIATES),
            bias_random=0.3,
            bias_random_slope=0.1,
            log_sigma_morning=np.log(0.35),
            log_sigma_random=np.log(0.45),
            eta=list(zeros),
            eta_dilution=0.0,
            log_nu=np.log(5.0),
            logit_spike_random=-1.7,
            logit_spike_morning=-2.9,
            kappa=list(zeros),
            kappa_dilution=0.0,
            log_spike_size=0.0,
            log_spike_sd=np.log(0.6),
            log_nu_spike=np.log(4.0),
        )

    # --- derived quantities ---
    @property
    def nu(self) -> float:
        return float(np.exp(self.log_nu))

    @property
    def spike_size(self) -> float:
        return float(np.exp(self.log_spike_size))

    @property
    def spike_sd(self) -> float:
        return float(np.exp(self.log_spike_sd))

    @property
    def nu_spike(self) -> float:
        return float(np.exp(self.log_nu_spike))

    def bias_at(self, sample_type: str, x) -> np.ndarray:
        """Shift of the sample relative to the true level x (0 for first morning urine)."""
        x = np.asarray(x, dtype=float)
        if sample_type != RANDOM:
            return np.zeros_like(x)
        return self.bias_random + self.bias_random_slope * bias_slope_term(x)

    def sigma(self, sample_type: str) -> float:
        return float(np.exp(self.log_sigma_random if sample_type == RANDOM else self.log_sigma_morning))

    def spike_logit_base(self, sample_type: str) -> float:
        return self.logit_spike_random if sample_type == RANDOM else self.logit_spike_morning

    # --- save / load ---
    def save(self, path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "AlbuminuriaParams":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


# --- model pieces, vectorized over N patients and G grid points ---


def _norm_logpdf(x, mean, sd):
    return -0.5 * ((x - mean) / sd) ** 2 - np.log(sd) - 0.5 * _LOG_2PI


def _t_logpdf(z, nu):
    return (
        gammaln((nu + 1.0) / 2.0)
        - gammaln(nu / 2.0)
        - 0.5 * np.log(nu * np.pi)
        - (nu + 1.0) / 2.0 * np.log1p(z * z / nu)
    )


def _t_logcdf(z, nu):
    return np.log(np.clip(stdtr(nu, z), 1e-300, None))


def prior_components(p: AlbuminuriaParams, Z: np.ndarray):
    """Means (N, K), standard deviations (K,) and log-weights (N, K) of the prior components."""
    offsets = np.concatenate([[0.0], np.cumsum(np.exp(p.log_gaps))])
    means = p.mu_low + (Z @ np.asarray(p.beta))[:, None] + offsets[None, :]
    gammas = np.asarray(p.gammas).reshape(len(p.alphas), Z.shape[1])
    logits = np.column_stack([np.zeros(Z.shape[0]), np.asarray(p.alphas)[None, :] + Z @ gammas.T + p.prior_logit_offset])
    log_w = logits - logsumexp(logits, axis=1, keepdims=True)
    return means, np.exp(np.asarray(p.log_taus)), log_w


def log_prior(p: AlbuminuriaParams, Z: np.ndarray, x: np.ndarray) -> np.ndarray:
    """log p(x | z) on the grid, (N, G)."""
    means, taus, log_w = prior_components(p, Z)
    comp = log_w[:, :, None] + _norm_logpdf(x[None, None, :], means[:, :, None], taus[None, :, None])
    return logsumexp(comp, axis=1)


def noise_scale(p: AlbuminuriaParams, Z: np.ndarray, sample_type: str, u) -> np.ndarray:
    """Scale of the usual variation of each sample, (N,)."""
    return p.sigma(sample_type) * np.exp(Z @ np.asarray(p.eta) + p.eta_dilution * np.asarray(u))


def spike_prob(p: AlbuminuriaParams, Z: np.ndarray, sample_type: str, u, offset=0.0) -> np.ndarray:
    """Probability of a transient elevation for each sample, (N,).

    ``offset`` shifts the logit according to the sample context (0 if unknown).
    """
    logit = p.spike_logit_base(sample_type) + Z @ np.asarray(p.kappa) + p.kappa_dilution * np.asarray(u)
    return expit(logit + np.asarray(offset, dtype=float))


def log_obs(p, obs: Observations, Z, x) -> np.ndarray:
    """log p(y | x) on the grid, (N, G). Missing samples (NaN) contribute 0."""
    y = np.asarray(obs.y, dtype=float)
    s = noise_scale(p, Z, obs.sample_type, obs.u)[:, None]
    rho = spike_prob(p, Z, obs.sample_type, obs.u, obs.spike_offset)[:, None]
    r = y[:, None] - x[None, :] - p.bias_at(obs.sample_type, x)[None, :]
    z = r / s
    base = np.log1p(-rho) + _t_logpdf(z, p.nu) - np.log(s)
    spike = np.log(rho) + _t_logpdf((r - p.spike_size) / p.spike_sd, p.nu_spike) - np.log(p.spike_sd)
    with np.errstate(invalid="ignore"):  # rows without a sample (NaN): set to 0 at the end
        out = np.logaddexp(base, spike)
    rows = np.flatnonzero(np.asarray(obs.censored, bool) & ~np.isnan(y))
    if rows.size:
        out[rows] = np.logaddexp(
            np.log1p(-rho[rows]) + _t_logcdf(z[rows], p.nu),
            np.log(rho[rows]) + _t_logcdf((r[rows] - p.spike_size) / p.spike_sd, p.nu_spike),
        )
    out[np.isnan(y)] = 0.0
    return out


def posterior(p, Z, observations: list[Observations], x) -> np.ndarray:
    """Normalized posterior on the grid (N, G) given samples taken at the same time."""
    lp = log_prior(p, Z, x)
    for obs in observations:
        lp = lp + log_obs(p, obs, Z, x)
    lp = lp - lp.max(axis=1, keepdims=True)
    w = np.exp(lp)
    return w / w.sum(axis=1, keepdims=True)


def new_sample_survival(p, Z, sample_type, log_threshold, x, u=None, spike_offset=0.0) -> np.ndarray:
    """P(new sample ≥ threshold | x), (N, G). Without ``u`` it averages over the typical dilution.

    ``log_threshold`` can be a scalar or an (N,) array, with one threshold per row.
    """
    us = [np.asarray(u, float)] if u is not None else [np.full(Z.shape[0], q) for q in p.dilution_quantiles[sample_type]]
    threshold = np.reshape(np.asarray(log_threshold, dtype=float), (-1, 1))
    out = 0.0
    for ui in us:
        s = noise_scale(p, Z, sample_type, ui)[:, None]
        rho = spike_prob(p, Z, sample_type, ui, spike_offset)[:, None]
        r = threshold - x[None, :] - p.bias_at(sample_type, x)[None, :]
        out = out + (1.0 - rho) * (1.0 - stdtr(p.nu, r / s)) + rho * (1.0 - stdtr(p.nu_spike, (r - p.spike_size) / p.spike_sd))
    return out / len(us)


def prob_new_sample_above(p, Z, post, sample_type, threshold, x, u=None) -> np.ndarray:
    """P(a new sample of this type gives UACR ≥ threshold | what is known), (N,)."""
    return (post * new_sample_survival(p, Z, sample_type, np.log(threshold), x, u)).sum(axis=1)


def simulate(p, Z, rng, u: dict | None = None) -> tuple[np.ndarray, dict]:
    """Simulates the true level and one sample of each type per patient (log-UACR).

    ``u`` gives each sample's dilution by type; without it, it is drawn from the typical quantiles.
    """
    n = Z.shape[0]
    means, taus, log_w = prior_components(p, Z)
    k = (rng.random(n)[:, None] > np.cumsum(np.exp(log_w), axis=1)).sum(axis=1).clip(max=len(taus) - 1)
    x = means[np.arange(n), k] + taus[k] * rng.standard_normal(n)
    samples = {}
    for t in SAMPLE_TYPES:
        ut = u[t] if u is not None else rng.choice(p.dilution_quantiles[t], n)
        usual = noise_scale(p, Z, t, ut) * rng.standard_t(p.nu, n)
        transient = p.spike_size + p.spike_sd * rng.standard_t(p.nu_spike, n)
        samples[t] = x + p.bias_at(t, x) + np.where(rng.random(n) < spike_prob(p, Z, t, ut), transient, usual)
    return x, samples
