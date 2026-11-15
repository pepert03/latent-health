"""Maximum-likelihood fit of the model on the NHANES 2009-2010 sample pairs.

Each person contributes a random sample and a first morning urine a few days apart. The
true level is assumed not to change in that interval, so their difference informs about
the sample-type bias, the noise and the transient elevations. Each person's likelihood
integrates the true level over the grid::

    p(y_random, y_morning | z) = ∫ p(x | z) p(y_random | x) p(y_morning | x) dx
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import digamma, logsumexp

from .model import (
    _FIELDS,
    _LOG_2PI,
    FIRST_MORNING,
    N_COVARIATES,
    NO_SPIKES,
    RANDOM,
    AlbuminuriaParams,
    Observations,
    _t_logcdf,
    _t_logpdf,
    bias_slope_term,
    covariates,
    dilution,
    log_obs,
    log_prior,
    make_grid,
    noise_scale,
    prior_components,
    spike_prob,
)

_BOUNDS = {
    "log_gaps": (np.log(0.1), np.log(10.0)),
    "bias_random_slope": (-1.0, 1.0),
    "log_taus": (np.log(0.05), np.log(5.0)),
    "log_sigma_morning": (np.log(0.02), np.log(3.0)),
    "log_sigma_random": (np.log(0.02), np.log(3.0)),
    "eta_dilution": (-3.0, 3.0),
    "log_nu": (np.log(0.5), np.log(1000.0)),
    "logit_spike_random": (-30.0, 0.0),  # baseline ρ ≤ 0.5: the elevation is the exception
    "logit_spike_morning": (-30.0, 0.0),
    "kappa_dilution": (-5.0, 5.0),
    "log_spike_size": (np.log(0.05), np.log(5.0)),
    "log_spike_sd": (np.log(0.05), np.log(3.0)),
    "log_nu_spike": (np.log(0.5), np.log(1000.0)),
}

_NO_SAMPLE_COVARIATES = {"eta_dilution": 0.0, "kappa": [0.0] * N_COVARIATES, "kappa_dilution": 0.0}
_LIGHT_SPIKES = {"log_nu_spike": float(np.log(1000.0))}
# Variant names are CLI choices and file-name suffixes (scripts/fit_albuminuria.py); keep them.
VARIANTS = {
    "completo": {},
    "picos_normales": dict(_LIGHT_SPIKES),
    "sin_covariables_muestra": {**_NO_SAMPLE_COVARIATES, **_LIGHT_SPIKES},
    "sin_pendiente": {**_NO_SAMPLE_COVARIATES, **_LIGHT_SPIKES, "bias_random_slope": 0.0},
    "sin_picos": {**_NO_SAMPLE_COVARIATES, **_LIGHT_SPIKES, **NO_SPIKES, "bias_random_slope": 0.0},
    "normal": {**_NO_SAMPLE_COVARIATES, **_LIGHT_SPIKES, **NO_SPIKES, "bias_random_slope": 0.0, "log_nu": float(np.log(1000.0))},
}


def nhanes_arrays(df: pd.DataFrame) -> dict:
    """Covariates and observations in the model format."""
    Z = covariates(df.age, df.female, df.diabetes, df.egfr)
    obs = [
        Observations(
            np.log(df[f"uacr_{tag}"].to_numpy(float)),
            df[f"censored_{tag}"].to_numpy(bool),
            sample_type,
            dilution(df[f"ucr_{tag}"].to_numpy(float)),
        )
        for tag, sample_type in (("random", RANDOM), ("morning", FIRST_MORNING))
    ]
    return {"Z": Z, "obs": obs}


def person_loglik(p: AlbuminuriaParams, data: dict, x: np.ndarray, dx: float) -> np.ndarray:
    """Marginal log-likelihood of each person, (N,)."""
    lp = log_prior(p, data["Z"], x)
    for obs in data["obs"]:
        lp = lp + log_obs(p, obs, data["Z"], x)
    return logsumexp(lp, axis=1) + np.log(dx)


def mean_loglik(p: AlbuminuriaParams, df: pd.DataFrame, grid_n: int = 400) -> float:
    x, dx = make_grid(grid_n)
    return float(person_loglik(p, nhanes_arrays(df), x, dx).mean())


def _t_dlognu(z, nu):
    """d log t_ν(z) / d log ν."""
    return nu * (
        0.5 * digamma((nu + 1.0) / 2.0)
        - 0.5 * digamma(nu / 2.0)
        - 0.5 / nu
        - 0.5 * np.log1p(z * z / nu)
        + (nu + 1.0) * z * z / (2.0 * nu * (nu + z * z))
    )


def _obs_terms(p, obs: Observations, Z, x):
    """log p(y|x) and its derivatives (N, G) with respect to r, log s, log ν, logit ρ, log δ, log ω and log ν_e."""
    nu, nu_e, delta, omega = p.nu, p.nu_spike, p.spike_size, p.spike_sd
    X = x[None, :]
    s = noise_scale(p, Z, obs.sample_type, obs.u)[:, None]
    rho = spike_prob(p, Z, obs.sample_type, obs.u)[:, None]
    missing = np.isnan(obs.y)
    r = obs.y[:, None] - X - p.bias_at(obs.sample_type, x)[None, :]
    z = r / s
    v = (r - delta) / omega
    log_base = np.log1p(-rho) + _t_logpdf(z, nu) - np.log(s)
    log_spike = np.log(rho) + _t_logpdf(v, nu_e) - np.log(omega)
    with np.errstate(invalid="ignore"):  # rows without a sample (NaN): set to 0 at the end
        lo = np.logaddexp(log_base, log_spike)
    q = np.exp(log_spike - lo)  # responsibility of the transient elevation
    q0 = 1.0 - q
    psi = -(nu + 1.0) * z / (nu + z * z)  # d log t / dz
    psi_e = -(nu_e + 1.0) * v / (nu_e + v * v)
    d = {
        "r": q0 * psi / s + q * psi_e / omega,
        "log_s": q0 * (-z * psi - 1.0),
        "log_nu": q0 * _t_dlognu(z, nu),
        "logit_rho": q - rho,
        "log_delta": -q * psi_e / omega * delta,
        "log_omega": q * (-v * psi_e - 1.0),
        "log_nu_e": q * _t_dlognu(v, nu_e),
    }
    rows = np.flatnonzero(np.asarray(obs.censored, bool) & ~missing)
    if rows.size:  # y < c: log[(1-ρ) T_ν(z) + ρ T_νe(v)] with z, v evaluated at the limit c
        zc, vc, sc, rc = z[rows], v[rows], s[rows], rho[rows]
        log_f0 = np.log1p(-rc) + _t_logcdf(zc, nu)
        log_f1 = np.log(rc) + _t_logcdf(vc, nu_e)
        lo_c = np.logaddexp(log_f0, log_f1)
        k0 = np.exp(np.log1p(-rc) + _t_logpdf(zc, nu) - lo_c)  # (1-ρ) t(z) / P
        k1 = np.exp(np.log(rc) + _t_logpdf(vc, nu_e) - lo_c)  # ρ t_e(v) / P
        w0, w1 = np.exp(log_f0 - lo_c), np.exp(log_f1 - lo_c)
        h = 1e-4
        dlogF0 = (_t_logcdf(zc, nu * np.exp(h)) - _t_logcdf(zc, nu * np.exp(-h))) / (2 * h)
        dlogF1 = (_t_logcdf(vc, nu_e * np.exp(h)) - _t_logcdf(vc, nu_e * np.exp(-h))) / (2 * h)
        lo[rows] = lo_c
        d["r"][rows] = k0 / sc + k1 / omega
        d["log_s"][rows] = -zc * k0
        d["log_nu"][rows] = w0 * dlogF0
        d["logit_rho"][rows] = w1 * (1.0 - rc) - w0 * rc
        d["log_delta"][rows] = -k1 * delta / omega
        d["log_omega"][rows] = -k1 * vc
        d["log_nu_e"][rows] = w1 * dlogF1
    lo[missing] = 0.0
    for arr in d.values():
        arr[missing] = 0.0
    return lo, d


def loglik_and_grad(p: AlbuminuriaParams, data: dict, x: np.ndarray, dx: float):
    """Total log-likelihood and its analytic gradient with respect to the parameter vector.

    For each person, d log ∫ exp(ℓ(x)) dx / dθ = E_post[dℓ/dθ], with the posterior on the
    grid. So a gradient costs the same as a few evaluations.
    """
    Z = data["Z"]
    X = x[None, :]
    # Prior: mixture of K normals.
    means, taus, log_w = prior_components(p, Z)
    dev = (X[:, None, :] - means[:, :, None]) / taus[None, :, None]  # (N, K, G)
    comp = log_w[:, :, None] - 0.5 * dev**2 - np.log(taus)[None, :, None] - 0.5 * _LOG_2PI
    lp = logsumexp(comp, axis=1)
    resp = np.exp(comp - lp[:, None, :])  # responsibility of each component
    total = lp
    terms = []
    for obs in data["obs"]:
        lo, d = _obs_terms(p, obs, Z, x)
        total = total + lo
        terms.append((obs, d))

    norm = logsumexp(total, axis=1)
    w = np.exp(total - norm[:, None])
    loglik = float((norm + np.log(dx)).sum())

    wr = w[:, None, :] * resp  # (N, K, G)
    a_mean = (wr * dev / taus[None, :, None]).sum(axis=2)  # E[resp_k (x - μ_k) / τ_k²], (N, K)
    r_k = wr.sum(axis=2) - np.exp(log_w)  # E[resp_k] - π_k, (N, K)
    np.zeros(Z.shape[1])
    grad = {name: (np.zeros(size) if size > 1 else 0.0) for name, size in _FIELDS}
    gap = np.exp(np.asarray(p.log_gaps))
    grad.update(
        {
            "mu_low": a_mean.sum(),
            "log_gaps": np.array([gap[j] * a_mean[:, j + 1 :].sum() for j in range(len(gap))]),
            "log_taus": (wr * (dev**2 - 1.0)).sum(axis=(0, 2)),
            "beta": Z.T @ a_mean.sum(axis=1),
            "alphas": r_k[:, 1:].sum(axis=0),
            "gammas": (r_k[:, 1:].T @ Z).ravel(),
        }
    )
    for obs, d in terms:
        tag = "random" if obs.sample_type == RANDOM else "morning"
        v_s = (w * d["log_s"]).sum(axis=1)  # per person
        grad[f"log_sigma_{tag}"] += v_s.sum()
        grad["eta"] = grad["eta"] + Z.T @ v_s
        grad["eta_dilution"] += (v_s * obs.u).sum()
        grad["log_nu"] += (w * d["log_nu"]).sum()
        v_rho = (w * d["logit_rho"]).sum(axis=1)
        grad[f"logit_spike_{tag}"] += v_rho.sum()
        grad["kappa"] = grad["kappa"] + Z.T @ v_rho
        grad["kappa_dilution"] += (v_rho * obs.u).sum()
        grad["log_spike_size"] += (w * d["log_delta"]).sum()
        grad["log_spike_sd"] += (w * d["log_omega"]).sum()
        grad["log_nu_spike"] += (w * d["log_nu_e"]).sum()
        if obs.sample_type == RANDOM:
            grad["bias_random"] -= (w * d["r"]).sum()
            grad["bias_random_slope"] -= (w * d["r"] * bias_slope_term(x)[None, :]).sum()
    vector = np.concatenate([np.atleast_1d(np.asarray(grad[name], dtype=float)) for name, _ in _FIELDS])
    return loglik, vector


def _field_slices() -> dict[str, slice]:
    out, i = {}, 0
    for name, size in _FIELDS:
        out[name] = slice(i, i + size)
        i += size
    return out


def dilution_quantiles(df: pd.DataFrame, n: int = 10) -> dict:
    """Dilution quantiles of each sample type, to predict future samples."""
    qs = (np.arange(n) + 0.5) / n
    out = {}
    for tag, sample_type in (("random", RANDOM), ("morning", FIRST_MORNING)):
        ucr = df[f"ucr_{tag}"].to_numpy(float)
        out[sample_type] = [float(v) for v in np.quantile(dilution(ucr[~np.isnan(ucr)]), qs)]
    return out


def fit(
    df: pd.DataFrame,
    grid_n: int = 150,
    fixed: dict | None = None,
    maxiter: int = 2000,
    verbose: bool = True,
) -> AlbuminuriaParams:
    """Fits all parameters except the dynamics and those in ``fixed`` (name -> value or list)."""
    fixed = fixed or {}
    x, dx = make_grid(grid_n)
    data = nhanes_arrays(df)
    n = len(df)
    full0 = AlbuminuriaParams.initial().to_vector()
    bounds_all = [_BOUNDS.get(name, (-15.0, 15.0)) for name, size in _FIELDS for _ in range(size)]
    slices = _field_slices()
    free = np.ones(full0.size, dtype=bool)
    for name, value in fixed.items():
        free[slices[name]] = False
        full0[slices[name]] = value

    def unpack(theta):
        full = full0.copy()
        full[free] = theta
        return AlbuminuriaParams.from_vector(full)

    calls, start = [0], time.time()

    def objective(theta):
        loglik, grad = loglik_and_grad(unpack(theta), data, x, dx)
        calls[0] += 1
        if verbose and calls[0] % 50 == 0:
            print(f"  {calls[0]} evaluations, -loglik per person = {-loglik / n:.4f} ({time.time() - start:.0f} s)", flush=True)
        return -loglik / n, -grad[free] / n

    result = minimize(
        objective,
        full0[free],
        jac=True,
        method="L-BFGS-B",
        bounds=[b for b, f in zip(bounds_all, free) if f],
        options={"maxiter": maxiter},
    )
    params = unpack(result.x)
    params.dilution_quantiles = dilution_quantiles(df)
    # Keys are stored in the saved JSON and read by scripts; keep them.
    params.meta = {
        "datos": "NHANES 2009-2010, non-pregnant adults, training split",
        "n_personas": n,
        "loglik_por_persona": float(-result.fun),
        "convergencia": bool(result.success),
        "mensaje": str(result.message),
        "iteraciones": int(result.nit),
        "rejilla": grid_n,
        "fijos": fixed,
        "segundos": round(time.time() - start, 1),
    }
    return params
