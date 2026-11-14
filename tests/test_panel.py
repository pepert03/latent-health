import numpy as np
import pytest

from latenthealth.panel import BinnedDistributionRegressor


@pytest.fixture(scope="module")
def fitted_model():
    rng = np.random.default_rng(0)
    X = rng.standard_normal((4000, 2))
    y = 50 + 10 * X[:, 0] + 5 * rng.standard_normal(4000)
    model = BinnedDistributionRegressor(thresholds=(45.0, 60.0)).fit(X[:3000], y[:3000])
    return model, X[3000:], y[3000:]


def test_thresholds_are_bin_edges(fitted_model):
    model, _, _ = fitted_model
    assert 45.0 in model.edges_ and 60.0 in model.edges_


def test_pmf_and_cdf_are_valid_distributions(fitted_model):
    model, X, _ = fitted_model
    pmf = model.predict_pmf(X)
    assert pmf.sum(axis=1) == pytest.approx(np.ones(len(X)))
    c = np.stack([model.cdf(X, t, pmf=pmf) for t in (30, 45, 50, 60, 70)], axis=1)
    assert np.all(np.diff(c, axis=1) >= -1e-12)
    assert np.all((c >= 0) & (c <= 1))


def test_quantiles_are_ordered_and_intervals_are_calibrated(fitted_model):
    model, X, y = fitted_model
    q = model.quantiles(X, [0.1, 0.5, 0.9])
    assert np.all(np.diff(q, axis=1) >= 0)
    coverage = np.mean((y >= q[:, 0]) & (y <= q[:, 2]))
    assert 0.74 <= coverage <= 0.86


def test_model_uses_the_predictor(fitted_model):
    model, X, y = fitted_model
    med = model.quantiles(X, [0.5])[:, 0]
    assert np.corrcoef(med, y)[0, 1] > 0.8
