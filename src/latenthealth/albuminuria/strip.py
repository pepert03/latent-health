"""Semi-quantitative albumin and creatinine dipstick, read at home.

The strip does not give a UACR: it gives the color level of the albumin pad (mg/l) and of
the creatinine pad (mg/dl). Here we compute the probability of each reading given the true
UACR, so the filter can use it just like a lab sample:

    P(reading | x) = Σ_u p(u) · P(creatinine read | u) · P(albumin read | x, u)

- ``u`` is the urine dilution (actual creatinine), which is unknown: it is integrated over
  its distribution for that sample type. The creatinine pad informs about it.
- The sample's actual albumin is the sample UACR × creatinine, and the sample UACR follows
  the filter's measurement model (usual variation and transient elevations).
- Each pad is read with an error on the log scale (bias and standard deviation).

Reading the two pads separately gives much more resolution than the ratio category
(< 30, 30-300, > 300), which is also supported for strips or apps that only give that.

The default errors are **assumptions**. Before using a given strip they must be estimated
with ``fit_strip_spec`` and samples read both with the strip and in the lab: a filter that
believes the strip is better than it is is no longer calibrated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import ndtr

from ..i18n import t
from .context import SampleContext
from .model import FIRST_MORNING, AlbuminuriaParams, new_sample_survival

_LOG_100 = np.log(100.0)


@dataclass(frozen=True)
class StripSpec:
    """Strip color levels and reading error of each pad (log scale)."""

    names: str | tuple[str, str]  # display name: plain text or (es, en)
    albumin_levels: tuple[float, ...] = (10.0, 30.0, 80.0, 150.0)  # mg/l
    creatinine_levels: tuple[float, ...] = (10.0, 50.0, 100.0, 200.0, 300.0)  # mg/dl
    albumin_log_sd: float = 0.35
    albumin_log_bias: float = 0.0
    creatinine_log_sd: float = 0.30
    creatinine_log_bias: float = 0.0
    # Strip (or app) that only returns the ratio category.
    ratio_only: bool = False
    ratio_edges: tuple[float, ...] = (30.0, 300.0)  # mg/g
    ratio_log_sd: float = 0.35
    ratio_log_bias: float = 0.0

    @property
    def name(self) -> str:
        """Display name in the current language."""
        return self.names if isinstance(self.names, str) else t(*self.names)

    @staticmethod
    def _edges(levels) -> np.ndarray:
        """Boundaries between adjacent levels: their geometric mean (in log)."""
        logs = np.log(np.asarray(levels, dtype=float))
        return (logs[:-1] + logs[1:]) / 2.0

    @property
    def albumin_edges(self) -> np.ndarray:
        return self._edges(self.albumin_levels)

    @property
    def creatinine_edges(self) -> np.ndarray:
        return self._edges(self.creatinine_levels)

    @staticmethod
    def _index(levels, value) -> int:
        return int(np.argmin(np.abs(np.log(np.asarray(levels, dtype=float)) - np.log(value))))

    def albumin_index(self, value_mg_l: float) -> int:
        return self._index(self.albumin_levels, value_mg_l)

    def creatinine_index(self, value_mg_dl: float) -> int:
        return self._index(self.creatinine_levels, value_mg_dl)


# Read with the phone camera and a color card: less error than by eye.
PHONE_STRIP = StripSpec(("tira leída con el móvil", "strip read with the phone"), albumin_log_sd=0.30, creatinine_log_sd=0.25)
# Read by eye against the color scale on the bottle (patient, pharmacy or nurse).
EYE_STRIP = StripSpec(("tira leída a ojo", "strip read by eye"), albumin_log_sd=0.45, creatinine_log_sd=0.40)
# Only the ratio category (< 30, 30-300, > 300 mg/g).
RATIO_STRIP = StripSpec(("tira de 3 categorías", "3-category strip"), ratio_only=True)


def _fine_levels(low: float, high: float, n: int) -> tuple[float, ...]:
    return tuple(float(v) for v in np.geomspace(low, high, n))


# Continuous color reading with a vision model. The pad color changes gradually with
# concentration; the 4 or 5 levels are for the eye. It is represented as a strip with many
# levels within the same chemical range (10-150 mg/l and 10-300 mg/dl): the quantization error
# disappears and only the reading error remains. With the same error as today's photo...
VISION_STRIP = StripSpec(
    ("tira leída en continuo", "strip read continuously"),
    albumin_levels=_fine_levels(10.0, 150.0, 13),
    creatinine_levels=_fine_levels(10.0, 300.0, 11),
    albumin_log_sd=0.30,
    creatinine_log_sd=0.25,
)
# ... and with half of it, what a good model with a color card and controlled timing would give.
SHARP_VISION_STRIP = replace(
    VISION_STRIP,
    names=("tira leída en continuo, mitad de error", "strip read continuously, half the error"),
    albumin_log_sd=0.15,
    creatinine_log_sd=0.125,
)


@dataclass
class StripSample:
    """A strip done at home. Gives either the reading of both pads or the ratio category."""

    date: date
    spec: StripSpec = PHONE_STRIP
    albumin_mg_l: float | None = None  # color level read on the albumin pad
    creatinine_mg_dl: float | None = None  # color level read on the creatinine pad
    ratio_category: int | None = None  # 0: < 30, 1: 30-300, 2: > 300 (ratio-only strips)
    sample_type: str = FIRST_MORNING
    context: SampleContext | None = None

    def __post_init__(self) -> None:
        if self.spec.ratio_only:
            if self.ratio_category is None:
                raise ValueError(
                    t(
                        "Esta tira solo da la categoría del cociente: falta ratio_category.",
                        "This strip only gives the ratio category: ratio_category is missing.",
                    )
                )
        elif self.albumin_mg_l is None or self.creatinine_mg_dl is None:
            raise ValueError(
                t(
                    "Faltan las lecturas de las almohadillas de albúmina y creatinina.",
                    "The albumin and creatinine pad readings are missing.",
                )
            )

    @property
    def outcome(self) -> tuple[int, int]:
        """Indices of the reading in the ``outcome_table`` table."""
        if self.spec.ratio_only:
            return int(self.ratio_category), 0
        return self.spec.albumin_index(self.albumin_mg_l), self.spec.creatinine_index(self.creatinine_mg_dl)

    @property
    def nominal_uacr(self) -> float:
        """Approximate UACR suggested by the reading (mg/g); for display only."""
        if self.spec.ratio_only:
            edges = [3.0, *self.spec.ratio_edges, 10.0 * self.spec.ratio_edges[-1]]
            k = min(int(self.ratio_category), len(edges) - 2)
            return float(np.sqrt(edges[k] * edges[k + 1]))  # geometric center of the category
        return 100.0 * self.albumin_mg_l / self.creatinine_mg_dl


def dilution_grid(p: AlbuminuriaParams, sample_type: str, n: int = 20) -> np.ndarray:
    """Equiprobable values of the dilution u = log(creatinine / 100 mg/dl) for that sample type."""
    q = np.asarray(p.dilution_quantiles[sample_type], dtype=float)
    if q.size < 2:
        return q
    probs = (np.arange(q.size) + 0.5) / q.size
    wanted = (np.arange(n) + 0.5) / n
    # Outside the stored range, extrapolate with the slope at the ends.
    lo = q[0] + (wanted - probs[0]) * (q[1] - q[0]) / (probs[1] - probs[0])
    hi = q[-1] + (wanted - probs[-1]) * (q[-1] - q[-2]) / (probs[-1] - probs[-2])
    return np.where(wanted < probs[0], lo, np.where(wanted > probs[-1], hi, np.interp(wanted, probs, q)))


def _category_probs(survival: np.ndarray) -> np.ndarray:
    """From P(value ≥ boundary_k) (K-1, ...) to the probability of each of the K categories."""
    ones, zeros = np.ones_like(survival[:1]), np.zeros_like(survival[:1])
    upper = np.concatenate([ones, survival, zeros], axis=0)
    return upper[:-1] - upper[1:]


def outcome_table(
    p: AlbuminuriaParams,
    z: np.ndarray,
    sample_type: str,
    spec: StripSpec,
    x: np.ndarray,
    spike_offset: float = 0.0,
    n_u: int = 20,
    n_gh: int = 7,
) -> np.ndarray:
    """P(reading | x) for every possible strip reading of a patient.

    Returns (albumin levels, creatinine levels, G), or (categories, 1, G) if the strip only
    gives the ratio. ``z`` are the patient's covariates, (1, 4).
    """
    nodes, weights = np.polynomial.hermite.hermgauss(n_gh)
    weights = weights / np.sqrt(np.pi)
    if spec.ratio_only:
        edges = np.log(np.asarray(spec.ratio_edges, dtype=float))
        thresholds = (edges[:, None] - spec.ratio_log_bias - np.sqrt(2.0) * spec.ratio_log_sd * nodes[None, :]).ravel()
        Z = np.repeat(z, thresholds.size, axis=0)
        surv = new_sample_survival(p, Z, sample_type, thresholds, x, spike_offset=spike_offset)
        surv = (surv.reshape(edges.size, n_gh, x.size) * weights[None, :, None]).sum(axis=1)
        return np.clip(_category_probs(surv)[:, None, :], 1e-12, None)

    u = dilution_grid(p, sample_type, n_u)
    a_edges, c_edges = spec.albumin_edges, spec.creatinine_edges
    # Albumin read = sample log UACR + u + bias + error. Threshold on the sample UACR:
    thresholds = (
        a_edges[None, :, None]
        - u[:, None, None]
        - spec.albumin_log_bias
        - np.sqrt(2.0) * spec.albumin_log_sd * nodes[None, None, :]
    )  # (U, K-1, H)
    shape = thresholds.shape
    Z = np.repeat(z, thresholds.size, axis=0)
    u_rows = np.broadcast_to(u[:, None, None], shape).ravel()
    surv = new_sample_survival(p, Z, sample_type, thresholds.ravel(), x, u=u_rows, spike_offset=spike_offset)
    surv = (surv.reshape(*shape, x.size) * weights[None, None, :, None]).sum(axis=2)  # (U, K-1, G)
    p_alb = _category_probs(np.moveaxis(surv, 1, 0))  # (K, U, G)
    # Creatinine read = log(creatinine) + bias + error, with log(creatinine) = u + log 100.
    c_surv = ndtr((u[None, :] + _LOG_100 + spec.creatinine_log_bias - c_edges[:, None]) / spec.creatinine_log_sd)
    p_creat = _category_probs(c_surv)  # (J, U)
    table = np.einsum("kug,ju->kjg", p_alb, p_creat) / u.size
    return np.clip(table, 1e-12, None)


def simulate_reading(spec: StripSpec, log_uacr_sample, u, rng) -> tuple[np.ndarray, np.ndarray]:
    """Strip reading for samples with that log-UACR and that dilution.

    Returns the (albumin, creatinine) indices or (ratio category, 0).
    """
    y = np.atleast_1d(np.asarray(log_uacr_sample, dtype=float))
    u = np.broadcast_to(np.asarray(u, dtype=float), y.shape)
    if spec.ratio_only:
        read = y + spec.ratio_log_bias + spec.ratio_log_sd * rng.standard_normal(y.shape)
        return np.searchsorted(np.log(spec.ratio_edges), read, side="right"), np.zeros(y.shape, int)
    albumin = y + u + spec.albumin_log_bias + spec.albumin_log_sd * rng.standard_normal(y.shape)
    creatinine = u + _LOG_100 + spec.creatinine_log_bias + spec.creatinine_log_sd * rng.standard_normal(y.shape)
    return (
        np.searchsorted(spec.albumin_edges, albumin, side="right"),
        np.searchsorted(spec.creatinine_edges, creatinine, side="right"),
    )


def fit_pad(true_log, category, edges) -> tuple[float, float]:
    """Bias and standard deviation (in log) of one pad, by maximum likelihood.

    ``true_log`` is the log of each sample's lab value and ``category`` the level read on
    the strip (index). It is an ordered probit with known boundaries.
    """
    true_log = np.asarray(true_log, dtype=float)
    category = np.asarray(category, dtype=int)
    bounds = np.concatenate([[-np.inf], np.asarray(edges, dtype=float), [np.inf]])
    lower, upper = bounds[category], bounds[category + 1]

    def nll(theta):
        bias, sd = theta[0], np.exp(theta[1])
        mean = true_log + bias
        prob = ndtr((upper - mean) / sd) - ndtr((lower - mean) / sd)
        return -np.log(np.clip(prob, 1e-300, None)).sum()

    best = minimize(nll, np.array([0.0, np.log(0.4)]), method="Nelder-Mead", options={"xatol": 1e-5, "fatol": 1e-7})
    return float(best.x[0]), float(np.exp(best.x[1]))


def fit_strip_spec(spec: StripSpec, albumin_mg_l, creatinine_mg_dl, albumin_read, creatinine_read) -> StripSpec:
    """Calibrates a strip with samples measured both in the lab and with the strip.

    ``albumin_read`` and ``creatinine_read`` are the color levels read (in mg/l and mg/dl).
    """
    a_idx = [spec.albumin_index(v) for v in albumin_read]
    c_idx = [spec.creatinine_index(v) for v in creatinine_read]
    a_bias, a_sd = fit_pad(np.log(albumin_mg_l), a_idx, spec.albumin_edges)
    c_bias, c_sd = fit_pad(np.log(creatinine_mg_dl), c_idx, spec.creatinine_edges)
    return replace(
        spec, albumin_log_bias=a_bias, albumin_log_sd=a_sd, creatinine_log_bias=c_bias, creatinine_log_sd=c_sd
    )
