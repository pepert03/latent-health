from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from latenthealth.albuminuria import (
    DEFAULT_PARAMS_PATH,
    FIRST_MORNING,
    RANDOM,
    AlbuminuriaFilter,
    AlbuminuriaParams,
    Patient,
    UrineSample,
)
from latenthealth.albuminuria.fit import loglik_and_grad, nhanes_arrays, person_loglik
from latenthealth.albuminuria.model import (
    NO_SPIKES,
    Observations,
    covariates,
    log_prior,
    make_grid,
    posterior,
    prob_new_sample_above,
    simulate,
)
from latenthealth.egfr import ckd_epi_2021


def gaussian_params(mu=2.0, tau=0.8, sigma=0.4) -> AlbuminuriaParams:
    """Prior de una sola normal y medida normal sin sesgo ni elevaciones: caso con solución cerrada."""
    p = AlbuminuriaParams.initial()
    return replace(
        p,
        mu_low=mu,
        log_taus=[np.log(tau), 0.0, 0.0],
        beta=[0.0] * 4,
        alphas=[-50.0, -50.0],
        gammas=[0.0] * 8,
        log_sigma_morning=np.log(sigma),
        eta=[0.0] * 4,
        eta_dilution=0.0,
        log_nu=np.log(1e7),
        kappa=[0.0] * 4,
        kappa_dilution=0.0,
        **NO_SPIKES,
    )


@pytest.fixture(scope="module")
def fitted():
    if not DEFAULT_PARAMS_PATH.exists():
        pytest.skip("faltan los parámetros ajustados (scripts/fit_albuminuria.py)")
    return AlbuminuriaParams.load(DEFAULT_PARAMS_PATH)


def test_ckd_epi_2021_matches_the_published_equation():
    # 142 · min(Scr/κ, 1)^α · max(Scr/κ, 1)^-1,2 · 0,9938^edad · 1,012 (mujer)
    assert ckd_epi_2021(0.7, 50, True) == pytest.approx(142 * 0.9938**50 * 1.012)
    assert ckd_epi_2021(1.2, 60, False) == pytest.approx(142 * (1.2 / 0.9) ** -1.2 * 0.9938**60)
    assert ckd_epi_2021(0.5, 40, True) == pytest.approx(142 * (0.5 / 0.7) ** -0.241 * 0.9938**40 * 1.012)
    assert ckd_epi_2021(2.0, 70, False) < ckd_epi_2021(1.0, 70, False) < ckd_epi_2021(1.0, 40, False)


def test_prior_integrates_to_one(fitted):
    x, dx = make_grid(600)
    Z = covariates([30, 70], [0, 1], [0, 1], [110, 40])
    mass = np.exp(log_prior(fitted, Z, x)).sum(axis=1) * dx
    assert mass == pytest.approx([1.0, 1.0], abs=1e-3)


def test_posterior_matches_conjugate_normal_update():
    p = gaussian_params()
    x, _ = make_grid(4000)
    y = np.log(40.0)
    post = posterior(p, covariates([50], [0], [0], [90]), [Observations.from_uacr([40.0], FIRST_MORNING)], x)[0]
    tau2, s2 = 0.8**2, 0.4**2
    expected = (y / s2 + 2.0 / tau2) / (1 / s2 + 1 / tau2)
    assert (post * x).sum() == pytest.approx(expected, abs=1e-3)


def test_censored_sample_moves_mass_below_the_limit(fitted):
    x, _ = make_grid(400)
    Z = covariates([60], [0], [1], [80])
    prior = posterior(fitted, Z, [], x)[0]
    post = posterior(fitted, Z, [Observations.from_uacr([5.0], FIRST_MORNING, censored=[True])], x)[0]
    above = x >= np.log(5.0)
    assert post[above].sum() < prior[above].sum()


def test_probability_of_albuminuria_grows_with_the_measured_value(fitted):
    x, _ = make_grid(400)
    Z = covariates([60], [1], [1], [80])
    probs = []
    for value in (10, 20, 30, 50, 100, 300):
        post = posterior(fitted, Z, [Observations.from_uacr([value], RANDOM)], x)[0]
        probs.append(post[x >= np.log(30.0)].sum())
    assert np.all(np.diff(probs) > 0)


def test_random_sample_counts_as_lower_than_same_first_morning_value(fitted):
    x, _ = make_grid(400)
    Z = covariates([60], [0], [1], [80])
    p_random = posterior(fitted, Z, [Observations.from_uacr([45.0], RANDOM)], x)[0][x >= np.log(30)].sum()
    p_morning = posterior(fitted, Z, [Observations.from_uacr([45.0], FIRST_MORNING)], x)[0][x >= np.log(30)].sum()
    assert p_random < p_morning


def test_new_sample_probability_is_a_probability(fitted):
    x, _ = make_grid(400)
    Z = covariates([60, 40], [0, 1], [1, 0], [80, 100])
    post = posterior(fitted, Z, [Observations.from_uacr([45.0, 10.0], RANDOM)], x)
    p = prob_new_sample_above(fitted, Z, post, FIRST_MORNING, 30.0, x)
    assert np.all((p >= 0) & (p <= 1))
    assert p[0] > p[1]


def test_analytic_gradient_matches_finite_differences():
    rng = np.random.default_rng(0)
    n = 150
    df = pd.DataFrame(
        {
            "age": rng.uniform(25, 80, n),
            "female": rng.random(n) < 0.5,
            "diabetes": rng.random(n) < 0.2,
            "egfr": rng.uniform(40, 110, n),
            "ucr_random": rng.uniform(20, 250, n),
            "ucr_morning": rng.uniform(40, 250, n),
        }
    )
    p0 = AlbuminuriaParams.initial()
    Z = covariates(df.age, df.female, df.diabetes, df.egfr)
    _, ys = simulate(p0, Z, rng)
    df["uacr_random"], df["uacr_morning"] = np.exp(ys[RANDOM]), np.exp(ys[FIRST_MORNING])
    df["censored_random"] = df["censored_morning"] = False
    df.loc[:4, "censored_random"] = True  # algunas censuras para cubrir esa rama
    df.loc[5:9, "uacr_morning"] = np.nan  # y alguna muestra que falta
    data = nhanes_arrays(df)
    x, dx = make_grid(120)
    p = AlbuminuriaParams.from_vector(p0.to_vector() + 0.1 * rng.standard_normal(p0.to_vector().size))
    _, grad = loglik_and_grad(p, data, x, dx)
    v, h = p.to_vector(), 1e-5
    for i in range(v.size):
        e = np.zeros_like(v)
        e[i] = h
        num = (
            person_loglik(AlbuminuriaParams.from_vector(v + e), data, x, dx).sum()
            - person_loglik(AlbuminuriaParams.from_vector(v - e), data, x, dx).sum()
        ) / (2 * h)
        assert grad[i] == pytest.approx(num, rel=1e-4, abs=1e-4), i


# --- Filtro de un paciente ---

D0 = date(2026, 1, 15)


def patient(*samples, diabetes=True):
    return Patient(age=62, female=False, diabetes=diabetes, egfr=75, samples=list(samples))


def morning(days, value):
    return UrineSample(D0 + timedelta(days=days), value, FIRST_MORNING, creatinine_mg_dl=120)


def test_filter_without_samples_asks_for_one(fitted):
    a = AlbuminuriaFilter(fitted).assess(patient())
    assert a.status == "sin_medir"
    assert 0 < a.p_a2_plus < 1


def test_one_very_high_sample_is_probable_but_not_chronic(fitted):
    a = AlbuminuriaFilter(fitted).assess(patient(morning(0, 1500)))
    assert a.status == "pendiente_cronicidad"
    assert a.p_a3 > 0.5


def test_two_high_samples_three_months_apart_confirm(fitted):
    a = AlbuminuriaFilter(fitted).assess(patient(morning(0, 400), morning(100, 350)))
    assert a.status == "confirmada"
    assert a.chronicity_met


def test_two_high_samples_close_together_are_not_chronic(fitted):
    a = AlbuminuriaFilter(fitted).assess(patient(morning(0, 400), morning(20, 350)))
    assert a.status == "pendiente_cronicidad"


def test_low_samples_discard(fitted):
    a = AlbuminuriaFilter(fitted).assess(patient(morning(0, 4), morning(30, 6)))
    assert a.status == "descartada"


def test_borderline_sample_is_doubtful_and_more_samples_narrow_the_estimate(fitted):
    flt = AlbuminuriaFilter(fitted)
    one = flt.assess(patient(morning(0, 35)))
    three = flt.assess(patient(morning(0, 35), morning(10, 38), morning(20, 33)))
    assert one.status == "dudosa"
    assert (three.high / three.low) < (one.high / one.low)
    assert 0 <= one.next_sample_resolves[FIRST_MORNING] <= 1
