from datetime import date, timedelta

import numpy as np
import pytest

from latenthealth.kidney_trend import (
    CAPILLARY,
    EgfrMeasurement,
    TreatmentStart,
    TrendParams,
    fit_trend,
    simulate_trajectory,
)

D0 = date(2021, 1, 10)


def yearly(values, start=D0, step_days=365):
    return [EgfrMeasurement(start + timedelta(days=step_days * i), v) for i, v in enumerate(values)]


def test_without_measurements_returns_the_prior():
    t = fit_trend([], age=70, female=False, as_of=D0)
    assert t.status == "sin_datos" and t.n == 0
    assert t.slope == pytest.approx(TrendParams().prior_slope(False, 0.0, 0.0)[0])
    assert 0 < t.p_below_60 < 1


def test_one_measurement_is_not_enough_to_talk_about_a_trend():
    t = fit_trend(yearly([58]), age=70, female=False)
    assert t.status == "insuficiente"
    assert not t.chronic_below_60


def test_steady_fall_is_detected_and_flat_series_is_stable():
    # About 7 points a year for 4 years: a clear decline, but with creatinine noise it cannot yet
    # be said to exceed 5 a year.
    falling = fit_trend(yearly([82, 75, 69, 62, 55]), age=66, female=False, diabetes=True)
    assert falling.status == "descenso"
    assert falling.slope < -4 and falling.p_decline > 0.8 and falling.p_fast > 0.5
    steep = fit_trend(yearly([88, 76, 65, 53, 42]), age=66, female=False, diabetes=True)
    assert steep.status == "descenso_rapido"
    assert steep.p_rapid > 0.8
    flat = fit_trend(yearly([74, 77, 73, 76, 75]), age=66, female=False)
    assert flat.status == "estable"
    assert abs(flat.slope) < 1.5


def test_noise_between_two_tests_is_not_called_a_decline():
    # From 68 to 61 in one year: within creatinine noise plus the normal age-related decline.
    t = fit_trend(yearly([68, 61]), age=72, female=True)
    assert t.status != "descenso_rapido"
    assert t.p_rapid < 0.5


def test_two_low_values_three_months_apart_meet_chronicity():
    close = fit_trend(yearly([48, 47], step_days=30), age=75, female=False)
    apart = fit_trend(yearly([48, 47], step_days=120), age=75, female=False)
    assert not close.chronic_below_60
    assert apart.chronic_below_60
    assert apart.category_probs()["G3a"] > 0.5


def test_treatment_start_explains_the_initial_drop():
    values = yearly([70, 69, 63, 62])
    start = [TreatmentStart(D0 + timedelta(days=365 + 200), "isglt2")]
    blind = fit_trend(values, age=64, female=False, diabetes=True)
    aware = fit_trend(values, age=64, female=False, diabetes=True, treatments=start)
    assert aware.p_decline < blind.p_decline
    assert aware.slope > blind.slope
    assert aware.measured_drop_explained < 0
    with pytest.raises(ValueError):
        fit_trend(values, age=64, female=False, treatments=[TreatmentStart(D0, "aspirin")])


def test_albuminuria_and_diabetes_speed_up_the_expected_decline():
    base = fit_trend([], age=60, female=True, as_of=D0)
    risky = fit_trend([], age=60, female=True, diabetes=True, p_a3=1.0, as_of=D0)
    assert risky.slope < base.slope
    assert risky.p_below_30_in_5y > base.p_below_30_in_5y


def test_capillary_measurement_is_noisier_and_above_only_pushes_up():
    lab = fit_trend(yearly([55]), age=70, female=False)
    capillary = fit_trend([EgfrMeasurement(D0, 55, CAPILLARY)], age=70, female=False)
    assert capillary.level_sd > lab.level_sd
    censored = fit_trend([EgfrMeasurement(D0, 90, above=True)], age=70, female=False)
    prior = fit_trend([], age=70, female=False, as_of=D0)
    assert censored.level > prior.level
    assert censored.level_sd < prior.level_sd


def test_intervals_are_calibrated_on_simulated_patients():
    rng = np.random.default_rng(3)
    params = TrendParams()
    dates = [D0 + timedelta(days=365 * i) for i in range(5)]
    inside, n = 0, 400
    for _ in range(n):
        diabetes = bool(rng.random() < 0.4)
        comps = params.slope_components(diabetes, 0.0, 0.0)
        _, mean, sd = comps[int(rng.random() < comps[1][0])]
        slope = mean + sd * rng.standard_normal()
        level0 = 75 + 15 * rng.standard_normal()
        ms = simulate_trajectory(dates, level0, slope, 65, False, rng, params=params)
        t = fit_trend(ms, 65, False, diabetes=diabetes, prior_level=(75, 15), params=params)
        lo, hi = t.interval("slope")
        # The true slope at the end has drifted a little from the initial one; compare with the initial one,
        # widening for that drift (0.4 per root year over 4 years ≈ 0.8).
        inside += lo - 0.8 <= slope <= hi + 0.8
    assert 0.75 <= inside / n <= 0.99
