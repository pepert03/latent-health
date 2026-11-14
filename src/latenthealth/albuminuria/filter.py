"""Filtro de la albuminuria de un paciente.

Recorre sus muestras de orina en orden (filtro bayesiano en rejilla, con paseo aleatorio
entre fechas), devuelve el estado actual con su incertidumbre, la decisión clínica y
cuánto ayudaría pedir otra muestra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

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

STATUS_LABELS = {
    "sin_medir": "Sin medir",
    "descartada": "Descartada",
    "dudosa": "Dudosa",
    "pendiente_cronicidad": "Muy probable, falta cronicidad",
    "confirmada": "Confirmada",
}
SAMPLE_LABELS = {FIRST_MORNING: "primera orina de la mañana", RANDOM: "muestra aleatoria"}


@dataclass
class UrineSample:
    date: date
    uacr: float  # mg/g; si censored=True es el límite superior ("< valor")
    sample_type: str = FIRST_MORNING
    censored: bool = False
    creatinine_mg_dl: float | None = None  # creatinina en orina de esa muestra (dilución)


@dataclass
class Patient:
    age: float
    female: bool
    diabetes: bool
    egfr: float | None = None
    samples: list[UrineSample] = field(default_factory=list)


@dataclass
class TrajectoryPoint:
    date: date
    median: float  # mg/g
    low: float  # percentil 10
    high: float  # percentil 90
    p_a2_plus: float  # suavizada: usa todas las muestras


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

    @property
    def p_a2_plus(self) -> float:
        return self.p_a2 + self.p_a3


class AlbuminuriaFilter:
    """Umbrales de decisión: ``confirm`` y ``discard`` sobre P(UACR verdadero ≥ 30).

    La cronicidad (criterio KDIGO de más de 3 meses) exige dos momentos separados al
    menos ``chronicity_days`` en los que, con las muestras disponibles hasta entonces,
    P(≥ 30) sea al menos ``chronicity_level``.
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

    # --- piezas ---
    @staticmethod
    def covariates(patient: Patient) -> np.ndarray:
        return covariates(patient.age, patient.female, patient.diabetes, patient.egfr)

    def prior(self, patient: Patient) -> np.ndarray:
        lp = log_prior(self.p, self.covariates(patient), self.x)[0]
        w = np.exp(lp - lp.max())
        return w / w.sum()

    def transition(self, days: float) -> np.ndarray | None:
        """K[i, j] = p(x_i tras ``days`` días | x_j). None si el cambio es despreciable."""
        sd = self.p.drift_sd_per_year * np.sqrt(max(days, 0.0) / 365.25)
        if sd < self.dx / 4:
            return None
        K = np.exp(-0.5 * ((self.x[:, None] - self.x[None, :]) / sd) ** 2)
        return K / K.sum(axis=0, keepdims=True)

    def likelihood(self, sample: UrineSample, z: np.ndarray) -> np.ndarray:
        u = dilution([np.nan if sample.creatinine_mg_dl is None else sample.creatinine_mg_dl])
        obs = Observations(np.array([np.log(sample.uacr)]), np.array([sample.censored]), sample.sample_type, u)
        lo = log_obs(self.p, obs, z, self.x)[0]
        return np.exp(lo - lo.max())

    def _point(self, day: date, w: np.ndarray) -> TrajectoryPoint:
        cdf = np.cumsum(w)
        q = np.exp(np.interp([0.1, 0.5, 0.9], cdf, self.x))
        return TrajectoryPoint(day, median=q[1], low=q[0], high=q[2], p_a2_plus=float(w[self._a2].sum()))

    def p_a2_plus(self, w: np.ndarray) -> float:
        return float(w[self._a2].sum())

    def resolve_probability(self, belief: np.ndarray, z: np.ndarray, sample_type: str, days_ahead: float = 0) -> float:
        """P(que una muestra más de este tipo deje P(≥ 30) por encima de ``confirm`` o por debajo de ``discard``)."""
        K = self.transition(days_ahead)
        b = belief if K is None else K @ belief
        y = self.x  # resultados posibles, en la misma rejilla
        zr = np.repeat(z, y.size, axis=0)
        quantiles = self.p.dilution_quantiles[sample_type]  # la dilución de la muestra futura no se conoce
        dens = sum(
            np.exp(log_obs(self.p, Observations(y, np.zeros(y.size, bool), sample_type, np.full(y.size, q)), zr, self.x))
            for q in quantiles
        ) / len(quantiles)
        py = dens @ b
        pa2 = (dens[:, self._a2] @ b[self._a2]) / np.maximum(py, 1e-300)
        resolved = (pa2 >= self.confirm) | (pa2 <= self.discard)
        return float((py * resolved).sum() / py.sum())

    # --- evaluación completa ---
    def assess(self, patient: Patient, as_of: date | None = None) -> AlbuminuriaAssessment:
        z = self.covariates(patient)
        samples = sorted(patient.samples, key=lambda s: s.date)
        belief = self.prior(patient)
        if not samples:
            return self._summarize(belief, z, as_of, "sin_medir", False, None, [])

        # Paso hacia delante (filtro) guardando lo necesario para suavizar.
        filtered, kernels, liks = [], [], []
        previous = samples[0].date
        for s in samples:
            K = self.transition((s.date - previous).days)
            lik = self.likelihood(s, z)
            belief = (belief if K is None else K @ belief) * lik
            belief /= belief.sum()
            filtered.append(belief)
            kernels.append(K)
            liks.append(lik)
            previous = s.date

        # Paso hacia atrás (suavizado) para la trayectoria.
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
        trajectory = [self._point(s.date, w) for s, w in zip(samples, smoothed)]

        as_of = as_of or samples[-1].date
        K = self.transition((as_of - samples[-1].date).days)
        current = belief if K is None else K @ belief

        # Cronicidad: dos momentos con P(≥30) alta usando solo lo medido hasta cada uno.
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
        return self._summarize(current, z, as_of, status, chronic, repeat_from, trajectory)

    def _summarize(self, w, z, as_of, status, chronic, repeat_from, trajectory) -> AlbuminuriaAssessment:
        point = self._point(as_of, w)
        p_a3 = float(w[self._a3].sum())
        p_a2 = point.p_a2_plus - p_a3
        p_a1 = 1.0 - point.p_a2_plus
        category = ("A1", "A2", "A3")[int(np.argmax([p_a1, p_a2, p_a3]))]
        a2_or_a3 = "A3" if p_a3 > p_a2 else "A2"
        resolves = {}
        if status in ("sin_medir", "dudosa"):
            resolves = {t: self.resolve_probability(w, z, t) for t in (FIRST_MORNING, RANDOM)}

        if status == "sin_medir":
            action = (
                f"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: "
                f"{point.p_a2_plus:.0%}."
            )
        elif status == "descartada":
            action = "Sin albuminuria. Repetir el cribado según la guía (anual en diabetes)."
        elif status == "dudosa":
            action = (
                "Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina. "
                f"Probabilidad de que resuelva la duda: {resolves[FIRST_MORNING]:.0%} "
                f"(con una muestra aleatoria, {resolves[RANDOM]:.0%})."
            )
        elif status == "pendiente_cronicidad":
            when = f" a partir del {repeat_from:%d/%m/%Y}" if repeat_from else ""
            action = (
                f"Albuminuria {a2_or_a3} muy probable. Repetir{when} para cumplir el criterio de "
                "cronicidad (más de 3 meses)."
            )
        else:
            action = (
                f"Albuminuria persistente {a2_or_a3}: registrar ERC (categoría {a2_or_a3}) y revisar el "
                "tratamiento nefroprotector según la guía."
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
        )


def describe(assessment: AlbuminuriaAssessment) -> str:
    """Resumen en texto para el médico."""
    a = assessment
    lines = [
        f"Estado: {STATUS_LABELS[a.status]}",
        f"UACR verdadero estimado: {a.median:.0f} mg/g (80 %: {a.low:.0f}-{a.high:.0f})",
        f"Probabilidades: A1 {a.p_a1:.0%} · A2 {a.p_a2:.0%} · A3 {a.p_a3:.0%}",
        f"Acción: {a.action}",
    ]
    if a.trajectory:
        lines.append("Trayectoria (con todas las muestras):")
        for t in a.trajectory:
            lines.append(f"  {t.date:%d/%m/%Y}: {t.median:.0f} mg/g ({t.low:.0f}-{t.high:.0f}), P(≥30) = {t.p_a2_plus:.0%}")
    return "\n".join(lines)
