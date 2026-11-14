"""Tira reactiva semicuantitativa de albúmina y creatinina, leída en casa.

La tira no da un UACR: da el nivel de color de la almohadilla de albúmina (mg/l) y el de la
de creatinina (mg/dl). Aquí se calcula la probabilidad de cada lectura dado el UACR verdadero,
para que el filtro la use igual que una muestra de laboratorio:

    P(lectura | x) = Σ_u p(u) · P(creatinina leída | u) · P(albúmina leída | x, u)

- ``u`` es la dilución de la orina (creatinina real), que no se conoce: se integra con su
  distribución en ese tipo de muestra. La almohadilla de creatinina informa de ella.
- La albúmina real de la muestra es UACR de la muestra × creatinina, y el UACR de la muestra
  sigue el modelo de medida del filtro (variación habitual y elevaciones transitorias).
- Cada almohadilla se lee con un error en escala logarítmica (sesgo y desviación típica).

Leer las dos almohadillas por separado da mucha más resolución que la categoría del cociente
(< 30, 30-300, > 300), que también se admite para tiras o aplicaciones que solo dan eso.

Los errores por defecto son **supuestos**. Antes de usar una tira concreta hay que estimarlos
con ``fit_strip_spec`` y muestras leídas a la vez con la tira y en el laboratorio: un filtro
que cree que la tira es mejor de lo que es deja de estar calibrado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import ndtr

from .context import SampleContext
from .model import FIRST_MORNING, AlbuminuriaParams, new_sample_survival

_LOG_100 = np.log(100.0)


@dataclass(frozen=True)
class StripSpec:
    """Niveles de color de la tira y error de lectura de cada almohadilla (escala log)."""

    name: str
    albumin_levels: tuple[float, ...] = (10.0, 30.0, 80.0, 150.0)  # mg/l
    creatinine_levels: tuple[float, ...] = (10.0, 50.0, 100.0, 200.0, 300.0)  # mg/dl
    albumin_log_sd: float = 0.35
    albumin_log_bias: float = 0.0
    creatinine_log_sd: float = 0.30
    creatinine_log_bias: float = 0.0
    # Tira (o aplicación) que solo devuelve la categoría del cociente.
    ratio_only: bool = False
    ratio_edges: tuple[float, ...] = (30.0, 300.0)  # mg/g
    ratio_log_sd: float = 0.35
    ratio_log_bias: float = 0.0

    @staticmethod
    def _edges(levels) -> np.ndarray:
        """Fronteras entre niveles contiguos: su media geométrica (en log)."""
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


# Lectura con la cámara del móvil y una tarjeta de color: menos error que a ojo.
PHONE_STRIP = StripSpec("tira leída con el móvil", albumin_log_sd=0.30, creatinine_log_sd=0.25)
# Lectura a ojo comparando con la escala de color del bote (paciente, farmacia o enfermería).
EYE_STRIP = StripSpec("tira leída a ojo", albumin_log_sd=0.45, creatinine_log_sd=0.40)
# Solo la categoría del cociente (< 30, 30-300, > 300 mg/g).
RATIO_STRIP = StripSpec("tira de 3 categorías", ratio_only=True)


def _fine_levels(low: float, high: float, n: int) -> tuple[float, ...]:
    return tuple(float(v) for v in np.geomspace(low, high, n))


# Lectura continua del color con un modelo de visión. El color de la almohadilla cambia de forma
# gradual con la concentración; los 4 o 5 niveles son para el ojo. Se representa como una tira
# con muchos niveles dentro del mismo rango químico (10-150 mg/l y 10-300 mg/dl): desaparece el
# error de cuantizar y queda solo el de lectura. Con el mismo error que la foto de hoy...
VISION_STRIP = StripSpec(
    "tira leída en continuo",
    albumin_levels=_fine_levels(10.0, 150.0, 13),
    creatinine_levels=_fine_levels(10.0, 300.0, 11),
    albumin_log_sd=0.30,
    creatinine_log_sd=0.25,
)
# ... y con la mitad, lo que daría un buen modelo con tarjeta de color y tiempo controlado.
SHARP_VISION_STRIP = replace(VISION_STRIP, name="tira leída en continuo, mitad de error", albumin_log_sd=0.15, creatinine_log_sd=0.125)


@dataclass
class StripSample:
    """Una tira hecha en casa. Se da la lectura de las dos almohadillas o la categoría del cociente."""

    date: date
    spec: StripSpec = PHONE_STRIP
    albumin_mg_l: float | None = None  # nivel de color leído en la almohadilla de albúmina
    creatinine_mg_dl: float | None = None  # nivel de color leído en la de creatinina
    ratio_category: int | None = None  # 0: < 30, 1: 30-300, 2: > 300 (tiras de solo cociente)
    sample_type: str = FIRST_MORNING
    context: SampleContext | None = None

    def __post_init__(self) -> None:
        if self.spec.ratio_only:
            if self.ratio_category is None:
                raise ValueError("Esta tira solo da la categoría del cociente: falta ratio_category.")
        elif self.albumin_mg_l is None or self.creatinine_mg_dl is None:
            raise ValueError("Faltan las lecturas de las almohadillas de albúmina y creatinina.")

    @property
    def outcome(self) -> tuple[int, int]:
        """Índices de la lectura en la tabla de ``outcome_table``."""
        if self.spec.ratio_only:
            return int(self.ratio_category), 0
        return self.spec.albumin_index(self.albumin_mg_l), self.spec.creatinine_index(self.creatinine_mg_dl)

    @property
    def nominal_uacr(self) -> float:
        """UACR aproximado que sugiere la lectura (mg/g); solo para mostrarlo."""
        if self.spec.ratio_only:
            edges = [3.0, *self.spec.ratio_edges, 10.0 * self.spec.ratio_edges[-1]]
            k = min(int(self.ratio_category), len(edges) - 2)
            return float(np.sqrt(edges[k] * edges[k + 1]))  # centro geométrico de la categoría
        return 100.0 * self.albumin_mg_l / self.creatinine_mg_dl


def dilution_grid(p: AlbuminuriaParams, sample_type: str, n: int = 20) -> np.ndarray:
    """Valores equiprobables de la dilución u = log(creatinina / 100 mg/dl) de ese tipo de muestra."""
    q = np.asarray(p.dilution_quantiles[sample_type], dtype=float)
    if q.size < 2:
        return q
    probs = (np.arange(q.size) + 0.5) / q.size
    wanted = (np.arange(n) + 0.5) / n
    # Fuera del rango guardado se extrapola con la pendiente de los extremos.
    lo = q[0] + (wanted - probs[0]) * (q[1] - q[0]) / (probs[1] - probs[0])
    hi = q[-1] + (wanted - probs[-1]) * (q[-1] - q[-2]) / (probs[-1] - probs[-2])
    return np.where(wanted < probs[0], lo, np.where(wanted > probs[-1], hi, np.interp(wanted, probs, q)))


def _category_probs(survival: np.ndarray) -> np.ndarray:
    """De P(valor ≥ frontera_k) (K-1, ...) a la probabilidad de cada una de las K categorías."""
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
    """P(lectura | x) para todas las lecturas posibles de la tira de un paciente.

    Devuelve (niveles de albúmina, niveles de creatinina, G), o (categorías, 1, G) si la tira
    solo da el cociente. ``z`` son las covariables del paciente, (1, 4).
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
    # Albúmina leída = log UACR de la muestra + u + sesgo + error. Umbral sobre el UACR de la muestra:
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
    # Creatinina leída = log(creatinina) + sesgo + error, con log(creatinina) = u + log 100.
    c_surv = ndtr((u[None, :] + _LOG_100 + spec.creatinine_log_bias - c_edges[:, None]) / spec.creatinine_log_sd)
    p_creat = _category_probs(c_surv)  # (J, U)
    table = np.einsum("kug,ju->kjg", p_alb, p_creat) / u.size
    return np.clip(table, 1e-12, None)


def simulate_reading(spec: StripSpec, log_uacr_sample, u, rng) -> tuple[np.ndarray, np.ndarray]:
    """Lectura de la tira para muestras con ese log-UACR y esa dilución.

    Devuelve los índices (albúmina, creatinina) o (categoría del cociente, 0).
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
    """Sesgo y desviación típica (en log) de una almohadilla, por máxima verosimilitud.

    ``true_log`` es el log del valor de laboratorio de cada muestra y ``category`` el nivel
    que se leyó en la tira (índice). Es un probit ordenado con las fronteras conocidas.
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
    """Calibra una tira con muestras medidas a la vez en el laboratorio y con la tira.

    ``albumin_read`` y ``creatinine_read`` son los niveles de color leídos (en mg/l y mg/dl).
    """
    a_idx = [spec.albumin_index(v) for v in albumin_read]
    c_idx = [spec.creatinine_index(v) for v in creatinine_read]
    a_bias, a_sd = fit_pad(np.log(albumin_mg_l), a_idx, spec.albumin_edges)
    c_bias, c_sd = fit_pad(np.log(creatinine_mg_dl), c_idx, spec.creatinine_edges)
    return replace(
        spec, albumin_log_bias=a_bias, albumin_log_sd=a_sd, creatinine_log_bias=c_bias, creatinine_log_sd=c_sd
    )
