"""Filtro de la albuminuria de un paciente.

Recorre sus muestras de orina en orden (filtro bayesiano en rejilla, con paseo aleatorio
entre fechas), devuelve el estado actual con su incertidumbre, la decisión clínica y
cuánto ayudaría pedir otra muestra.

Admite muestras de laboratorio (``UrineSample``) y tiras hechas en casa (``StripSample``),
con las respuestas de contexto de cada una. Si el filtrado glomerular no está medido se le
puede pasar su distribución (``egfr_mixture``): el filtro se resuelve para cada valor y se
mezcla, de modo que la albuminuria y el filtrado dejan de tratarse como independientes.
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
from .strip import StripSample, StripSpec, outcome_table

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
    """Muestra medida en el laboratorio (cuantitativa)."""

    date: date
    uacr: float  # mg/g; si censored=True es el límite superior ("< valor")
    sample_type: str = FIRST_MORNING
    censored: bool = False
    creatinine_mg_dl: float | None = None  # creatinina en orina de esa muestra (dilución)
    context: SampleContext | None = None  # respuestas del paciente sobre la muestra


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
    low: float  # percentil 10
    high: float  # percentil 90
    p_a2_plus: float  # suavizada: usa todas las muestras


@dataclass
class EgfrComponent:
    """Albuminuria condicionada a un valor del filtrado glomerular."""

    egfr: float
    weight: float  # probabilidad de ese valor una vez vistas las muestras de orina
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
    repeat_from: date | None = None  # fecha desde la que una muestra alta cumple la cronicidad
    log_evidence: float = 0.0  # log-verosimilitud de las muestras (para comparar hipótesis)
    egfr_components: list[EgfrComponent] = field(default_factory=list)
    belief: np.ndarray | None = field(default=None, repr=False)  # distribución actual en la rejilla

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
        self._tables: dict = {}

    # --- piezas ---
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
        """K[i, j] = p(x_i tras ``days`` días | x_j). None si el cambio es despreciable."""
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
        """P(lectura | x) de todas las lecturas posibles de una tira para este paciente (con caché)."""
        key = (spec, sample_type, round(offset, 4), z.tobytes())
        if key not in self._tables:
            if len(self._tables) > 512:
                self._tables.clear()
            self._tables[key] = outcome_table(self.p, z, sample_type, spec, self.x, spike_offset=offset)
        return self._tables[key]

    def log_likelihood(self, sample: Sample, z: np.ndarray) -> np.ndarray:
        """log p(muestra | x) en la rejilla."""
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
        """P(que una muestra más deje P(≥ 30) por encima de ``confirm`` o por debajo de ``discard``).

        Con ``strip`` la muestra es una tira de ese tipo; sin ella, una muestra de laboratorio.
        """
        K = self.transition(days_ahead)
        b = belief if K is None else K @ belief
        if strip is not None:
            table = self.strip_table(strip, z, sample_type)
            dens = table.reshape(-1, self.x.size)  # una fila por lectura posible
        else:
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
    def _run(self, z: np.ndarray, samples: list[Sample], as_of: date | None):
        """Filtro y suavizado para unas covariables. Devuelve lo necesario para mezclar hipótesis."""
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
        """Estado de la albuminuria del paciente.

        ``egfr_mixture`` es la distribución del filtrado glomerular cuando no está medido:
        pares (valor, probabilidad). Con ``update_weights`` esas probabilidades se actualizan
        con lo que dicen las muestras de orina (regla de Bayes); sin él se toman como están.
        ``detail=False`` se salta el cálculo de cuánto ayudaría otra muestra, que es lo más lento
        (para evaluar a mucha gente de una vez).
        """
        samples = sorted(patient.samples, key=lambda s: s.date)
        mixture = egfr_mixture or [(patient.egfr, 1.0)]
        zs = [covariates(patient.age, patient.female, patient.diabetes, e) for e, _ in mixture]
        prior_w = np.asarray([w for _, w in mixture], dtype=float)
        prior_w = prior_w / prior_w.sum()
        runs = [self._run(z, samples, as_of) for z in zs]

        n = len(samples)
        if n and update_weights:
            log_ev = np.stack([r["log_ev"] for r in runs], axis=1)  # (muestras, hipótesis)
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
            resolves = {t: self.resolve_probability(w, z, t) for t in (FIRST_MORNING, RANDOM)}

        if status == "sin_medir":
            action = (
                f"Pedir UACR en primera orina de la mañana. Probabilidad de albuminuria antes de medir: "
                f"{point.p_a2_plus:.0%}."
            )
        elif status == "descartada":
            action = "Sin albuminuria. Repetir el cribado según la guía (anual en diabetes)."
        elif status == "dudosa":
            action = "Repetir en primera orina de la mañana, evitando ejercicio intenso, fiebre o infección de orina."
            if resolves:
                action += (
                    f" Probabilidad de que resuelva la duda: {resolves[FIRST_MORNING]:.0%} "
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
            repeat_from=repeat_from,
            log_evidence=evidence,
            egfr_components=components or [],
            belief=w,
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
