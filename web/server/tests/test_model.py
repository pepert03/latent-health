"""Contract tests for the live model routes (``/api/model``), with the real models.

    uv run --with-requirements web/server/requirements-dev.txt pytest web/server/tests/test_model.py -q

Mounts its own app with only this routes module (it does not use conftest's ``client``, which also
loads the patient-app routes). Each route is compared with a direct call to the library: what the
web returns must be exactly what the model says.
"""

from __future__ import annotations

import importlib.util
import json
import math
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scipy.special import ndtr

from latenthealth import assessment as library
from latenthealth.albuminuria import (
    EYE_STRIP,
    FIRST_MORNING,
    PHONE_STRIP,
    Patient,
    StripSample,
    UrineSample,
    load_default_filter,
)
from latenthealth.albuminuria.filter import SAMPLE_LABELS, STATUS_LABELS
from latenthealth.assessment import G_LABELS, KDIGO_RISK, ClinicalRecord
from latenthealth.assessment import assess as library_assess
from latenthealth.cvrisk import CATEGORY_LABELS
from latenthealth.kidney_trend import STATUS_TEXT, EgfrMeasurement, TreatmentStart, TrendParams, fit_trend
from server.main import LanguageMiddleware
from server.routes import model

TOL = 1e-9
TODAY = date(2026, 11, 14)
REPO_DIR = Path(__file__).resolve().parents[3]
# The only fields that may be null; a null anywhere else would be a NaN from the model.
NULLABLE = {"repeat_from", "next_sample_resolves", "p_diabetes", "p_nt_probnp_high", "cv"}

app = FastAPI()
app.include_router(model.router)
app.add_middleware(LanguageMiddleware)  # X-Lang: es -> Spanish texts


@pytest.fixture(scope="module")
def api():
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def strict_json(text: str):
    """Real JSON: ``NaN`` and ``Infinity`` are not, and they break ``JSON.parse`` in the browser."""

    def not_json(name):
        raise AssertionError(f"The response contains {name}")

    return json.loads(text, parse_constant=not_json)


def null_fields(value, name: str = "") -> set[str]:
    """Names of the fields that are null, at any depth."""
    if value is None:
        return {name}
    if isinstance(value, dict):
        return set().union(*(null_fields(v, k) for k, v in value.items())) if value else set()
    if isinstance(value, list):
        return set().union(*(null_fields(v, name) for v in value)) if value else set()
    return set()


def probabilities(value, name: str = "") -> list[tuple[str, float]]:
    """All values in a response that are probabilities, with their field name."""
    if isinstance(value, dict):
        whole = name in ("kdigo_g", "kdigo_risk", "finding_by_test", "next_sample_resolves")
        found = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                found += probabilities(item, key)
            elif item is not None and not isinstance(item, (str, bool)):
                if whole or key.startswith("p_") or key in ("p", "score", "score_low", "score_high"):
                    found.append((f"{name}.{key}" if name else key, item))
        return found
    if isinstance(value, list):
        if name in ("mass", "probs"):
            return [(name, item) for item in value]
        return [pair for item in value for pair in probabilities(item, name)]
    return []


def post(api: TestClient, route: str, body: dict, status: int = 200):
    response = api.post(f"/api/model/{route}", json=body)
    assert response.status_code == status, response.text
    data = strict_json(response.text)
    if status == 200:
        assert null_fields(data) <= NULLABLE
        # Fractions between 0 and 1, without the model's rounding error (1.0000000000000002, -2e-16
        # or -0.0), which shows on screen as "-0%".
        for name, p in probabilities(data):
            assert 0.0 <= p <= 1.0 and math.copysign(1.0, p) > 0, f"{name} = {p!r} is not a probability between 0 and 1"
    return data


def same(got, expected) -> None:
    assert got == pytest.approx(float(expected), rel=TOL, abs=TOL)


def lab(day: str, uacr: float, sample_type: str = "first_morning", creatinine: float | None = None, **extra) -> dict:
    sample = {"kind": "laboratorio", "date": day, "uacr": uacr, "sample_type": sample_type, **extra}
    if creatinine is not None:
        sample["creatinine_mg_dl"] = creatinine
    return sample


def strip(day: str, albumin: float, creatinine: float, **extra) -> dict:
    return {"kind": "tira", "date": day, "albumin_mg_l": albumin, "creatinine_mg_dl": creatinine, **extra}


def library_sample(sample: dict) -> UrineSample | StripSample:
    """The same sample as the library wants it (a conversion independent of the route's)."""
    day = date.fromisoformat(sample["date"])
    if sample["kind"] == "tira":
        spec = {"movil": PHONE_STRIP, "ojo": EYE_STRIP}[sample.get("reader", "movil")]
        return StripSample(
            day,
            spec,
            sample["albumin_mg_l"],
            sample["creatinine_mg_dl"],
            sample_type=sample.get("sample_type", FIRST_MORNING),
        )
    return UrineSample(
        day, sample["uacr"], sample["sample_type"], sample.get("censored", False), sample.get("creatinine_mg_dl")
    )


def check_albuminuria(got: dict, expected, samples: list) -> None:
    """``got`` (the route's JSON) against the library's ``AlbuminuriaAssessment``."""
    assert got["as_of"] == expected.as_of.isoformat()
    assert got["status"] == expected.status
    assert got["status_label"] == STATUS_LABELS[expected.status]
    assert got["category"] == expected.category
    assert got["action"] == expected.action  # the model's literal text
    for name in ("p_a1", "p_a2", "p_a3", "p_a2_plus", "median", "low", "high"):
        same(got[name], getattr(expected, name))
    assert got["chronicity_met"] is bool(expected.chronicity_met)
    assert got["repeat_from"] == (expected.repeat_from.isoformat() if expected.repeat_from else None)
    if expected.next_sample_resolves:
        assert set(got["next_sample_resolves"]) == {"first_morning", "random"}
        for kind, p in expected.next_sample_resolves.items():
            same(got["next_sample_resolves"][kind], p)
    else:
        assert got["next_sample_resolves"] is None
    assert len(got["trajectory"]) == len(expected.trajectory)
    for point, reference in zip(got["trajectory"], expected.trajectory):
        assert set(point) == {"date", "median", "low", "high", "p_a2_plus"}
        assert point["date"] == reference.date.isoformat()
        for name in ("median", "low", "high", "p_a2_plus"):
            same(point[name], getattr(reference, name))
    ordered = sorted(samples, key=lambda s: s.date)
    assert len(got["samples"]) == len(ordered)
    for echo, sample in zip(got["samples"], ordered):
        assert set(echo) == {"kind", "date", "label", "value_mg_g", "sample_type", "censored"}
        assert echo["date"] == sample.date.isoformat()
        assert echo["sample_type"] == sample.sample_type
        if isinstance(sample, StripSample):
            assert (echo["kind"], echo["label"]) == ("tira", sample.spec.name)
            same(echo["value_mg_g"], sample.nominal_uacr)
            assert echo["censored"] is False
        else:
            assert (echo["kind"], echo["label"]) == ("laboratorio", SAMPLE_LABELS[sample.sample_type])
            same(echo["value_mg_g"], sample.uacr)
            assert echo["censored"] is bool(sample.censored)


# --------------------------------------------------------------------------------------
# 1. Albuminuria filter
# --------------------------------------------------------------------------------------

# Patient and recipes from the survey report (mapa_albuminuria.md, section 6).
BASE = {"age": 62, "female": False, "diabetes": True, "egfr": 75}
DESCARTADA = [lab("2026-10-20", 4.0, creatinine=120)]
DUDOSA = [lab("2026-11-02", 35.0, creatinine=120)]
PENDIENTE = [lab("2026-10-20", 400.0, creatinine=120)]
CONFIRMADA = [lab("2026-05-05", 400.0, creatinine=120), lab("2026-08-13", 350.0, creatinine=120)]
CONFIRMADA_A2 = [
    lab("2026-10-01", 120.0, creatinine=110),  # out of order on purpose
    lab("2026-03-01", 90.0, "random", 100),
    lab("2026-06-15", 80.0, creatinine=130),
]
CON_TIRAS = [
    strip("2026-10-28", 30, 100),
    strip("2026-11-01", 80, 50, reader="ojo"),
    lab("2026-11-06", 58.0, creatinine=100),
    lab("2026-11-09", 30.0, "random", censored=True),
]
PROJECTION_DATES = ["2026-11-14", "2027-02-14", "2027-05-14", "2027-11-14"]

ALBUMINURIA_CASES = {
    "sin_muestras": ({"patient": BASE, "samples": [], "as_of": "2026-11-14"}, PROJECTION_DATES),
    "dudosa": ({"patient": BASE, "samples": DUDOSA, "as_of": "2026-11-14"}, PROJECTION_DATES),
    "confirmada_desordenada": ({"patient": BASE, "samples": CONFIRMADA_A2, "as_of": "2026-11-14"}, PROJECTION_DATES),
    "tiras_y_laboratorio_sin_fg": (
        {"patient": {"age": 45, "female": True, "diabetes": False}, "samples": CON_TIRAS, "as_of": "2026-11-30"},
        ["2026-11-30", "2027-02-28", "2027-05-30", "2027-11-30"],  # February has no 30th
    ),
    "pendiente_nhanes": (
        {"patient": BASE, "samples": PENDIENTE, "as_of": "2026-11-14", "population": "nhanes"},
        PROJECTION_DATES,
    ),
    "descartada_meses_despues": (
        {"patient": {**BASE, "egfr": 38}, "samples": DESCARTADA, "as_of": "2027-08-31"},
        ["2027-08-31", "2027-11-30", "2028-02-29", "2028-08-31"],  # 2028 is a leap year
    ),
}


@pytest.mark.parametrize("name", ALBUMINURIA_CASES)
def test_albuminuria_matches_the_library(api, name):
    body, projection_dates = ALBUMINURIA_CASES[name]
    got = post(api, "albuminuria", body)

    filt = load_default_filter(body.get("population", "espana"))
    samples = [library_sample(s) for s in body["samples"]]
    patient = Patient(**{"egfr": None, **body["patient"]}, samples=samples)
    as_of = date.fromisoformat(body["as_of"])
    expected = filt.assess(patient, as_of=as_of)
    check_albuminuria(got, expected, samples)

    # Projection: the filter itself evaluated at future dates.
    assert [p["months"] for p in got["projection"]] == [0, 3, 6, 12]
    assert [p["date"] for p in got["projection"]] == projection_dates
    for point in got["projection"]:
        assert set(point) == {"months", "date", "median", "low", "high", "p_a2_plus"}
        future = filt.assess(patient, as_of=date.fromisoformat(point["date"]), detail=False)
        for field in ("median", "low", "high", "p_a2_plus"):
            same(point[field], getattr(future, field))

    # Current belief and prior: the filter's grid grouped two cells at a time.
    centers = np.exp(filt.x.reshape(-1, 2).mean(axis=1))
    for key, mass in (("belief", expected.belief), ("prior", filt.prior(patient))):
        assert set(got[key]) == {"uacr", "mass"}
        np.testing.assert_allclose(got[key]["uacr"], centers, rtol=TOL)
        np.testing.assert_allclose(got[key]["mass"], np.asarray(mass).reshape(-1, 2).sum(axis=1), atol=1e-12)


@pytest.mark.parametrize("name", ALBUMINURIA_CASES)
def test_belief_and_prior_are_distributions(api, name):
    got = post(api, "albuminuria", ALBUMINURIA_CASES[name][0])
    for key in ("belief", "prior"):
        uacr, mass = np.array(got[key]["uacr"]), np.array(got[key]["mass"])
        assert 150 <= uacr.size == mass.size <= 250  # "about 200 points"
        assert np.all(np.diff(uacr) > 0) and uacr[0] > 0
        assert np.all(mass >= 0)
        assert mass.sum() == pytest.approx(1.0, abs=1e-9)  # grouping loses no mass
    # The median read off the belief falls where the filter says (grouping loses half a cell).
    uacr, mass = np.array(got["belief"]["uacr"]), np.array(got["belief"]["mass"])
    median = float(np.exp(np.interp(0.5, np.cumsum(mass), np.log(uacr))))
    assert median == pytest.approx(got["median"], rel=0.05)
    assert mass[uacr >= 30].sum() == pytest.approx(got["p_a2_plus"], abs=0.05)


@pytest.mark.parametrize("name", ALBUMINURIA_CASES)
def test_projection_band_never_narrows(api, name):
    projection = post(api, "albuminuria", ALBUMINURIA_CASES[name][0])["projection"]
    widths = [p["high"] / p["low"] for p in projection]
    assert all(later >= earlier - 1e-9 for earlier, later in zip(widths, widths[1:]))
    if ALBUMINURIA_CASES[name][0]["samples"]:
        assert widths[-1] > widths[0]  # a year-old data point says less than today's


def test_without_samples_is_sin_medir_and_projection_repeats(api):
    got = post(api, "albuminuria", {"patient": BASE, "samples": [], "as_of": "2026-11-14"})
    assert (got["status"], got["status_label"]) == ("sin_medir", "Not measured")
    assert got["trajectory"] == [] and got["samples"] == []
    assert got["repeat_from"] is None and got["chronicity_met"] is False
    assert got["action"].startswith("Order UACR on a first morning urine sample.")
    assert got["next_sample_resolves"]["first_morning"] > got["next_sample_resolves"]["random"] > 0
    assert got["belief"] == got["prior"]
    first = got["projection"][0]
    for name in ("median", "low", "high", "p_a2_plus"):
        assert first[name] == got[name]
        assert all(point[name] == first[name] for point in got["projection"])
    # "samples" can be omitted: same as having no samples.
    assert post(api, "albuminuria", {"patient": BASE, "as_of": "2026-11-14"}) == got


@pytest.mark.parametrize(
    ("samples", "status", "label", "category", "chronic", "repeat_from", "in_action"),
    [
        (DESCARTADA, "descartada", "Ruled out", "A1", False, None, "No albuminuria."),
        (DUDOSA, "dudosa", "Doubtful", "A2", False, None, "Probability that it settles the doubt: 7%"),
        (
            PENDIENTE,
            "pendiente_cronicidad",
            "Very likely, chronicity pending",
            "A3",
            False,
            "2027-01-18",
            "A3 albuminuria very likely. Repeat from January 18, 2027",
        ),
        (CONFIRMADA, "confirmada", "Confirmed", "A3", True, "2026-08-03", "Persistent A3 albuminuria: record CKD"),
        (CONFIRMADA_A2, "confirmada", "Confirmed", "A2", True, "2026-09-13", "Persistent A2 albuminuria: record CKD"),
    ],
)
def test_status_recipes(api, samples, status, label, category, chronic, repeat_from, in_action):
    got = post(api, "albuminuria", {"patient": BASE, "samples": samples, "as_of": "2026-11-14"})
    assert (got["status"], got["status_label"], got["category"]) == (status, label, category)
    assert got["chronicity_met"] is chronic
    assert in_action in got["action"]
    assert got["repeat_from"] == repeat_from  # first clearly high sample + 90 days
    # How much another sample would help is only computed while in doubt.
    assert (got["next_sample_resolves"] is not None) == (status == "dudosa")
    if status == "descartada":
        assert got["p_a2_plus"] <= 0.05
    elif status == "dudosa":
        assert got["p_a2_plus"] == pytest.approx(0.567, abs=0.001)
    else:
        assert got["p_a2_plus"] >= 0.95


def test_strip_reader_and_sample_order(api):
    body = {"patient": BASE, "samples": CON_TIRAS, "as_of": "2026-11-14"}
    got = post(api, "albuminuria", body)
    assert [s["kind"] for s in got["samples"]] == ["tira", "tira", "laboratorio", "laboratorio"]
    assert [s["label"] for s in got["samples"]] == [
        "strip read with the phone",
        "strip read by eye",
        "first morning urine",
        "random sample",
    ]
    assert [s["value_mg_g"] for s in got["samples"]] == [30.0, 160.0, 58.0, 30.0]
    # The last one is a "less than 30": its value is the detection limit, not a measurement.
    assert [s["censored"] for s in got["samples"]] == [False, False, False, True]
    assert [p["date"] for p in got["trajectory"]] == [s["date"] for s in got["samples"]]
    # The order in which samples arrive does not matter.
    assert post(api, "albuminuria", {**body, "samples": CON_TIRAS[::-1]}) == got
    # The same reading weighs less read by eye than with the phone.
    by_reader = {
        reader: post(
            api,
            "albuminuria",
            {"patient": BASE, "samples": [strip("2026-11-10", 80, 100, reader=reader)], "as_of": "2026-11-14"},
        )["p_a2_plus"]
        for reader in ("movil", "ojo")
    }
    assert by_reader["movil"] > by_reader["ojo"] > 0.268  # 0.268 is the probability before measuring


# --------------------------------------------------------------------------------------
# 2. eGFR trend
# --------------------------------------------------------------------------------------


def yearly(values: list[float], last: str = "2026-10-27") -> list[dict]:
    """Yearly lab tests (every 365 days) ending on ``last``: the report's series."""
    end, n = date.fromisoformat(last), len(values)
    return [{"date": (end - timedelta(days=365 * (n - 1 - i))).isoformat(), "egfr": v} for i, v in enumerate(values)]


FALLING = {"age": 68, "female": True, "diabetes": True, "measurements": yearly([88, 79, 68, 60, 49]), "as_of": "2026-11-14"}
STABLE = {"age": 68, "female": True, "diabetes": True, "measurements": yearly([75, 77, 74, 76, 75]), "as_of": "2026-11-14"}
TREND_CASES = {
    "descenso_rapido": FALLING,
    "estable": STABLE,
    "tratamiento_y_albuminuria": {
        "age": 66,
        "female": False,
        "diabetes": True,
        "p_a2": 0.3,
        "p_a3": 0.1,
        "measurements": yearly([74, 73, 67, 66])[::-1],  # out of order on purpose
        "treatments": [{"date": "2025-05-30", "kind": "isglt2"}, {"date": "2020-01-15", "kind": "ieca_ara2"}],
        "as_of": "2026-11-16",
    },
    "capilar_y_mayor_que_sin_as_of": {
        "age": 74,
        "female": True,
        "measurements": [
            {"date": "2024-03-01", "egfr": 90, "above": True},
            {"date": "2025-04-10", "egfr": 71},
            {"date": "2026-09-20", "egfr": 58, "source": "capilar"},
        ],
    },
}


def library_trend(body: dict):
    measurements = [
        EgfrMeasurement(date.fromisoformat(m["date"]), m["egfr"], m.get("source", "laboratorio"), m.get("above", False))
        for m in body["measurements"]
    ]
    treatments = [TreatmentStart(date.fromisoformat(t["date"]), t["kind"]) for t in body.get("treatments", [])]
    as_of = date.fromisoformat(body["as_of"]) if body.get("as_of") else None
    trend = fit_trend(
        measurements,
        body["age"],
        body["female"],
        body.get("diabetes", False),
        body.get("p_a2", 0.0),
        body.get("p_a3", 0.0),
        treatments,
        as_of,
    )
    return trend, sorted(measurements, key=lambda m: m.date)


def level_mixture(trend, years: float) -> list[tuple[float, float, float]]:
    """(weight, mean, sd) of the level in ``years`` years, written here independently.

    It is the ``kidney_trend.fit_trend`` formula for ``p_below_30_in_5y``.
    """
    params = TrendParams()
    noise = params.level_noise**2 * years + params.slope_noise**2 * years**3 / 3.0
    return [
        (w, m[0] + m[1] * years, float(np.sqrt(P[0, 0] + 2 * years * P[0, 1] + years**2 * P[1, 1] + noise)))
        for w, m, P in trend.components
    ]


def mixture_cdf(mixture, value: float) -> float:
    return float(sum(w * ndtr((value - mean) / sd) for w, mean, sd in mixture))


@pytest.mark.parametrize("name", TREND_CASES)
def test_egfr_trend_matches_the_library(api, name):
    body = TREND_CASES[name]
    got = post(api, "egfr-trend", body)
    trend, measurements = library_trend(body)

    assert got["as_of"] == trend.as_of.isoformat()
    assert got["n"] == trend.n == len(measurements)
    assert got["status"] == trend.status
    assert got["status_label"] == STATUS_TEXT[trend.status]
    assert got["chronic_below_60"] is bool(trend.chronic_below_60)
    for field in (
        "span_years",
        "level",
        "slope",
        "p_decline",
        "p_rapid",
        "p_below_60",
        "p_below_30_in_5y",
        "measured_drop_explained",
    ):
        same(got[field], getattr(trend, field))
    for what in ("level", "slope"):  # 80% intervals with interval()
        low, high = trend.interval(what)
        same(got[f"{what}_low"], low)
        same(got[f"{what}_high"], high)
        assert got[f"{what}_low"] < got[what] < got[f"{what}_high"]

    assert len(got["trajectory"]) == len(trend.trajectory)
    for point, reference in zip(got["trajectory"], trend.trajectory):
        assert set(point) == {"date", "level", "low", "high"}
        assert point["date"] == reference.date.isoformat()
        for field in ("level", "low", "high"):
            same(point[field], getattr(reference, field))

    assert got["measurements"] == [
        {"date": m.date.isoformat(), "egfr": float(m.egfr), "source": m.source, "above": m.above} for m in measurements
    ]

    # Projection at 1, 2, 3 and 5 years with the module's own formula, clipped at 0.
    assert [p["years"] for p in got["projection"]] == [1, 2, 3, 5]
    for point in got["projection"]:
        assert set(point) == {"years", "date", "level", "low", "high"}
        assert point["date"] == trend.as_of.replace(year=trend.as_of.year + point["years"]).isoformat()
        mixture = level_mixture(trend, point["years"])
        same(point["level"], max(sum(w * mean for w, mean, _ in mixture), 0.0))
        assert 0.0 <= point["low"] <= point["level"] <= point["high"]
        for edge, q in (("low", 0.1), ("high", 0.9)):
            if point[edge] > 0:
                assert mixture_cdf(mixture, point[edge]) == pytest.approx(q, abs=1e-7)
            else:  # clipped: the quantile was negative
                assert mixture_cdf(mixture, 0.0) >= q
    widths = [p["high"] - p["low"] for p in got["projection"] if p["low"] > 0]
    assert widths == sorted(widths)


@pytest.mark.parametrize("name", TREND_CASES)
def test_projection_reproduces_p_below_30_in_5y(api, name):
    body = TREND_CASES[name]
    trend, _ = library_trend(body)
    # The mixture the route uses to draw the five-year point gives the model's probability...
    route_mixture = model._level_ahead(trend, 5)
    assert mixture_cdf(route_mixture, 30.0) == pytest.approx(trend.p_below_30_in_5y, abs=1e-12)
    np.testing.assert_allclose(route_mixture, level_mixture(trend, 5), rtol=1e-12)
    # ... and the band returned is consistent with it.
    got = post(api, "egfr-trend", body)
    five = got["projection"][-1]
    assert (five["high"] < 30) == (got["p_below_30_in_5y"] > 0.9)
    assert (five["low"] > 30) == (got["p_below_30_in_5y"] < 0.1)


def test_the_two_series_of_the_report(api):
    falling = post(api, "egfr-trend", FALLING)
    assert (falling["status"], falling["status_label"]) == ("descenso_rapido", "rapid decline")
    assert falling["slope"] == pytest.approx(-8.11, abs=0.005)
    assert (falling["slope_low"], falling["slope_high"]) == pytest.approx((-10.02, -6.19), abs=0.005)
    assert falling["level"] == pytest.approx(50.8, abs=0.05)
    assert (falling["p_decline"], falling["p_rapid"]) == pytest.approx((0.999, 0.978), abs=0.0005)
    assert falling["p_below_30_in_5y"] == pytest.approx(0.969, abs=0.0005)
    assert [round(p["level"], 1) for p in falling["trajectory"]] == [84.6, 76.5, 68.1, 59.7, 51.2]
    assert falling["projection"][-1]["low"] == 0.0  # unclipped it would be negative

    stable = post(api, "egfr-trend", STABLE)
    assert (stable["status"], stable["status_label"]) == ("estable", "stable")
    assert stable["slope"] == pytest.approx(-0.58, abs=0.005)
    assert (stable["slope_low"], stable["slope_high"]) == pytest.approx((-2.15, 0.98), abs=0.005)
    assert stable["level"] == pytest.approx(74.3, abs=0.05)
    assert stable["p_decline"] == pytest.approx(0.026, abs=0.0005)
    assert stable["p_below_30_in_5y"] < 0.001


def test_fewer_than_two_measurements(api):
    empty = post(api, "egfr-trend", {"age": 68, "female": True, "measurements": [], "as_of": "2026-11-14"})
    assert (empty["status"], empty["status_label"], empty["n"]) == ("sin_datos", "no lab tests", 0)
    assert empty["trajectory"] == [] and empty["projection"] == [] and empty["measurements"] == []
    assert empty["as_of"] == "2026-11-14" and empty["span_years"] == 0.0
    # "measurements" can be omitted.
    assert post(api, "egfr-trend", {"age": 68, "female": True, "as_of": "2026-11-14"}) == empty

    one = post(api, "egfr-trend", {"age": 68, "female": True, "measurements": yearly([55])})
    assert (one["status"], one["n"], one["as_of"]) == ("insuficiente", 1, "2026-10-27")
    assert one["status_label"] == "too few lab tests to see a trend"
    assert len(one["trajectory"]) == 1 and len(one["projection"]) == 4

    # Two lab tests less than half a year apart are not enough to see the trend either.
    close = [{"date": "2026-08-01", "egfr": 62}, {"date": "2026-10-27", "egfr": 55}]
    assert post(api, "egfr-trend", {"age": 68, "female": True, "measurements": close})["status"] == "insuficiente"


def test_more_measurements_change_the_reading(api):
    """The same series read with 2, 3, 4 and 5 lab tests (report, section 3)."""
    statuses = [
        post(api, "egfr-trend", {**FALLING, "measurements": FALLING["measurements"][:k], "as_of": None})["status"]
        for k in range(2, 6)
    ]
    assert statuses == ["estable", "incierto", "descenso", "descenso_rapido"]


# --------------------------------------------------------------------------------------
# 3. Full assessment and 4. examples
# --------------------------------------------------------------------------------------


def demo_patients() -> dict[str, ClinicalRecord]:
    """``PATIENTS`` from scripts/demo.py, loaded here without going through the route."""
    spec = importlib.util.spec_from_file_location("demo_for_tests", REPO_DIR / "scripts" / "demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PATIENTS


@pytest.fixture(scope="module")
def examples(api):
    response = api.get("/api/model/examples")
    assert response.status_code == 200, response.text
    return strict_json(response.text)


def check_assess(got: dict, expected, samples: list) -> None:
    """``got`` (the route's JSON) against the library's ``PatientAssessment``."""
    check_albuminuria(got["albuminuria"], expected.albuminuria, samples)
    assert set(got["albuminuria"]) == set(model.AlbuminuriaSummaryOut.model_fields)  # no belief, prior or projection

    assert [b["key"] for b in got["blood"]] == list(expected.blood)
    for row, estimate in zip(got["blood"], expected.blood.values()):
        assert set(row) == {"key", "name", "unit", "median", "low", "high", "measured", "decimals", "source"}
        assert (row["name"], row["unit"], row["source"]) == (estimate.name, estimate.unit, estimate.source)
        assert (row["measured"], row["decimals"]) == (estimate.measured, estimate.decimals)
        for field in ("median", "low", "high"):
            same(row[field], getattr(estimate, field))

    for field in ("p_egfr_below_60", "p_ckd", "p_new_finding"):
        same(got[field], getattr(expected, field))
    for field in ("kdigo_g", "kdigo_risk", "finding_by_test"):
        reference = getattr(expected, field)
        assert list(got[field]) == list(reference)
        for key, p in reference.items():
            same(got[field][key], p)
    assert list(got["kdigo_risk"]) == ["bajo", "moderado", "alto", "muy alto"]

    assert [row["g"] for row in got["kdigo_joint"]] == list(G_LABELS)
    for i, row in enumerate(got["kdigo_joint"]):
        assert [cell["a"] for cell in row["cells"]] == ["A1", "A2", "A3"]
        assert [cell["risk"] for cell in row["cells"]] == KDIGO_RISK[row["g"]]  # the model's own table
        for j, cell in enumerate(row["cells"]):
            same(cell["p"], expected.kdigo_joint[i, j])

    assert (got["diabetes"], got["heart_failure"]) == (expected.diabetes, expected.heart_failure)
    for field in ("p_diabetes", "p_nt_probnp_high"):
        if getattr(expected, field) is None:
            assert got[field] is None
        else:
            same(got[field], getattr(expected, field))

    cv = got["cv"]
    assert set(cv) == {
        "score",
        "score_low",
        "score_high",
        "probs",
        "recorded",
        "recorded_label",
        "category",
        "category_label",
        "approximate",
    }
    for field in ("score", "score_low", "score_high"):
        same(cv[field], getattr(expected.cv, field))
    np.testing.assert_allclose(cv["probs"], expected.cv.probs, atol=TOL)
    assert (cv["recorded"], cv["category"]) == (expected.cv.recorded, expected.cv.category)
    assert (cv["recorded_label"], cv["category_label"]) == (
        CATEGORY_LABELS[expected.cv.recorded],
        CATEGORY_LABELS[expected.cv.category],
    )
    assert cv["approximate"] is bool(expected.cv.approximate)

    assert got["recommendations"] == [{"test": r.test, "reason": r.reason} for r in expected.recommendations]
    assert got["alerts"] == expected.alerts


def check_kdigo_map(got: dict) -> None:
    cells = [(row["g"], cell) for row in got["kdigo_joint"] for cell in row["cells"]]
    assert len(got["kdigo_joint"]) == 6 and len(cells) == 18
    assert sum(cell["p"] for _, cell in cells) == pytest.approx(1.0, abs=TOL)
    for level, p in got["kdigo_risk"].items():  # aggregated by risk level
        assert sum(cell["p"] for _, cell in cells if cell["risk"] == level) == pytest.approx(p, abs=TOL)
    for g, p in got["kdigo_g"].items():  # eGFR marginal
        assert sum(cell["p"] for row, cell in cells if row == g) == pytest.approx(p, abs=TOL)
    for a in ("A1", "A2", "A3"):  # albuminuria marginal
        total = sum(cell["p"] for _, cell in cells if cell["a"] == a)
        assert total == pytest.approx(got["albuminuria"][f"p_{a.lower()}"], abs=TOL)
    normal = sum(cell["p"] for g, cell in cells if g in ("G1", "G2") and cell["a"] == "A1")
    assert got["p_ckd"] == pytest.approx(1.0 - normal, abs=TOL)
    assert got["p_egfr_below_60"] == pytest.approx(sum(got["kdigo_g"][g] for g in ("G3a", "G3b", "G4", "G5")), abs=TOL)


@pytest.mark.parametrize("index", range(5))
def test_assess_matches_the_library_for_the_demo_patients(api, examples, index):
    title, record = list(demo_patients().items())[index]
    example = examples["patients"][index]
    assert example["id"] == f"p{index + 1}"
    assert title == f"{index + 1}. {example['title']}"

    got = post(api, "assess", example["assess"])
    expected = library_assess(record, as_of=TODAY, population="espana", detail=True)
    check_assess(got, expected, list(record.urine_samples))
    check_kdigo_map(got)


EXTRA_ASSESS = {
    "minimo": {"age": 42, "female": True, "as_of": "2026-11-14"},
    "tiras_analitica_y_lipidos": {
        "age": 71,
        "female": False,
        "bmi": 30.5,
        "waist": 108,
        "sbp": 151,
        "dbp": 84,
        "diabetes": True,
        "insulin": True,
        "hypertension": True,
        "bp_meds": True,
        "stroke": True,
        "smoker_now": True,
        "measured": {"egfr": 41, "potassium": 4.9, "total_cholesterol": 212, "hdl": 44, "nt_probnp": 480},
        "urine_samples": CON_TIRAS,
        "as_of": "2026-11-20",
    },
    "nhanes_con_hba1c_alta": {
        "age": 55,
        "female": True,
        "bmi": 36,
        "prediabetes": True,
        "high_cholesterol": True,
        "kidney_disease": True,
        "heart_failure": True,
        "measured": {"hba1c": 7.1, "glucose": 148, "hemoglobin": 12.9, "non_hdl": 171},
        "urine_samples": CONFIRMADA,
        "as_of": "2026-11-14",
        "population": "nhanes",
    },
}


def forget_panel_predictions() -> None:
    """Empties the panel predictions the library caches.

    Without this the direct call would reuse the ones the route just computed (it evaluates with a
    single thread) and the cache would be compared with itself.
    """
    cache = getattr(library, "_PMF_CACHE", None)
    if cache is not None:
        cache.clear()


@pytest.mark.parametrize("name", EXTRA_ASSESS)
def test_assess_matches_the_library_for_other_patients(api, name):
    body = EXTRA_ASSESS[name]
    model._assess_cached.cache_clear()
    forget_panel_predictions()
    got = post(api, "assess", body)
    forget_panel_predictions()
    history = {k: v for k, v in body.items() if k not in ("measured", "urine_samples", "as_of", "population")}
    samples = [library_sample(s) for s in body.get("urine_samples", [])]
    record = ClinicalRecord(**history, urine_samples=samples, measured=dict(body.get("measured", {})))
    expected = library_assess(
        record, as_of=date.fromisoformat(body["as_of"]), population=body.get("population", "espana"), detail=True
    )
    check_assess(got, expected, samples)
    check_kdigo_map(got)


def test_assess_reads_what_is_measured(api):
    got = post(api, "assess", EXTRA_ASSESS["tiras_analitica_y_lipidos"])
    egfr = got["blood"][0]
    assert (egfr["key"], egfr["measured"], egfr["source"]) == ("egfr", True, "measured")
    assert egfr["median"] == egfr["low"] == egfr["high"] == 41.0
    assert got["kdigo_g"] == {"G1": 0.0, "G2": 0.0, "G3a": 0.0, "G3b": 1.0, "G4": 0.0, "G5": 0.0}
    assert not re.search(r"-0\.0(?![0-9])", json.dumps(got))  # the model leaves negative zeros with a measured eGFR
    assert any("NT-proBNP of 480 pg/ml" in alert for alert in got["alerts"])
    assert (got["cv"]["category"], got["cv"]["category_label"]) == (2, "very high")  # previous stroke

    without = post(api, "assess", EXTRA_ASSESS["minimo"])
    assert without["albuminuria"]["status"] == "sin_medir"
    assert without["albuminuria"]["as_of"] == "2026-11-14"
    assert all(not row["measured"] for row in without["blood"])
    assert without["recommendations"][0]["reason"] == without["albuminuria"]["action"]


def test_examples(api, examples):
    assert examples["as_of"] == "2026-11-14"
    assert [p["id"] for p in examples["patients"]] == ["p1", "p2", "p3", "p4", "p5"]
    assert examples["patients"][0]["title"] == "Man aged 62 with hypertension, UACR never ordered"
    assert [t["id"] for t in examples["egfr_trends"]] == ["descenso_rapido", "estable"]

    records = list(demo_patients().values())
    statuses = []
    for example, record in zip(examples["patients"], records):
        assert set(example) == {"id", "title", "assess", "albuminuria"}
        assert example["assess"]["as_of"] == example["albuminuria"]["as_of"] == "2026-11-14"
        assert example["assess"]["urine_samples"] == example["albuminuria"]["samples"]
        assert len(example["albuminuria"]["samples"]) == len(record.urine_samples)
        assert example["albuminuria"]["patient"].get("egfr") == record.measured.get("egfr")
        # The bodies work as they are for the routes.
        statuses.append(post(api, "albuminuria", example["albuminuria"])["status"])
        post(api, "assess", example["assess"])
    assert statuses == ["sin_medir", "dudosa", "confirmada", "dudosa", "dudosa"]

    # The report's two series: woman, 68, with diabetes, one lab test a year.
    for example, reference in zip(examples["egfr_trends"], (FALLING, STABLE)):
        assert set(example) == {"id", "title", "egfr_trend"}
        body = example["egfr_trend"]
        assert (body["age"], body["female"], body["diabetes"], body["as_of"]) == (68, True, True, "2026-11-14")
        assert [(m["date"], m["egfr"]) for m in body["measurements"]] == [
            (m["date"], m["egfr"]) for m in reference["measurements"]
        ]
        assert post(api, "egfr-trend", body) == post(api, "egfr-trend", reference)
    trend_statuses = [post(api, "egfr-trend", t["egfr_trend"])["status"] for t in examples["egfr_trends"]]
    assert trend_statuses == ["descenso_rapido", "estable"]


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------

OK_ALBUMINURIA = {"patient": BASE, "samples": DUDOSA, "as_of": "2026-11-14"}
MANY = [lab((date(2026, 1, 1) + timedelta(days=7 * i)).isoformat(), 20.0 + i) for i in range(31)]

SHAPE_ERRORS = [
    ("albuminuria", {**OK_ALBUMINURIA, "patient": {**BASE, "age": 17}}, "age", "Must be at least 18"),
    ("albuminuria", {**OK_ALBUMINURIA, "patient": {**BASE, "age": 101}}, "age", "Must be at most 100"),
    ("albuminuria", {**OK_ALBUMINURIA, "patient": {**BASE, "egfr": 4}}, "egfr", "Must be at least 5"),
    ("albuminuria", {**OK_ALBUMINURIA, "patient": {**BASE, "egfr": 151}}, "egfr", "Must be at most 150"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [lab("2026-11-02", 0)]}, "uacr", "Must be greater than 0"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [lab("2026-11-02", -3)]}, "uacr", "Must be greater than 0"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [lab("2026-11-02", 30000.5)]}, "uacr", "Must be at most 30000"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": MANY}, "samples", "Allows at most 30 items (got 31)"),
    ("albuminuria", {"patient": BASE, "samples": DUDOSA}, "as_of", "This field is required."),
    ("albuminuria", {"samples": DUDOSA, "as_of": "2026-11-14"}, "patient", "This field is required."),
    ("albuminuria", {**OK_ALBUMINURIA, "as_of": "14/11/2026"}, "as_of", "Invalid date: expected YYYY-MM-DD."),
    ("albuminuria", {**OK_ALBUMINURIA, "as_of": "2026-02-30"}, "as_of", "Invalid date"),
    ("albuminuria", {**OK_ALBUMINURIA, "as_of": "2500-01-01"}, "as_of", "Must be at most 2100-12-31"),
    ("albuminuria", {**OK_ALBUMINURIA, "population": "marte"}, "population", "Value not allowed"),
    ("albuminuria", {**OK_ALBUMINURIA, "hoy": "2026-11-14"}, "hoy", "Unknown field."),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [{**DUDOSA[0], "kind": "sangre"}]}, "samples", "Unknown sample type"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [{"date": "2026-11-02", "uacr": 35}]}, "samples", "The \"kind\" field is missing"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [lab("2026-11-02", 35, "24h")]}, "sample_type", "Value not allowed"),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [{"kind": "tira", "date": "2026-11-02", "albumin_mg_l": 30}]}, "creatinine_mg_dl", "This field is required."),
    ("albuminuria", {**OK_ALBUMINURIA, "samples": [strip("2026-11-02", 30, 100, reader="lupa")]}, "reader", "Value not allowed"),
    ("albuminuria", {**OK_ALBUMINURIA, "patient": {**BASE, "female": "maybe"}}, "female", "Must be true or false."),
    ("egfr-trend", {**FALLING, "age": 12}, "age", "Must be at least 18"),
    ("egfr-trend", {**FALLING, "measurements": [{"date": "2026-10-27", "egfr": 200}]}, "egfr", "Must be at most 150"),
    ("egfr-trend", {**FALLING, "measurements": [{"date": "2026-10-27", "egfr": 60, "source": "casa"}]}, "source", "Value not allowed"),
    ("egfr-trend", {**FALLING, "treatments": [{"date": "2025-01-01", "kind": "estatina"}]}, "kind", "Value not allowed"),
    ("egfr-trend", {**FALLING, "p_a2": 1.2}, "p_a2", "Must be at most 1"),
    ("egfr-trend", {**FALLING, "measurements": yearly([70.0] * 41)}, "measurements", "Allows at most 40 items"),
    ("egfr-trend", {"female": True, "measurements": []}, "age", "This field is required."),
    ("assess", {"age": 10, "female": True, "as_of": "2026-11-14"}, "age", "Must be at least 18"),
    ("assess", {"age": 60, "female": True}, "as_of", "This field is required."),
    ("assess", {"age": 60, "female": True, "as_of": "2026-11-14", "measured": {"creatinina": 1.1}}, "creatinina", "Unknown field."),
    ("assess", {"age": 60, "female": True, "as_of": "2026-11-14", "measured": {"hba1c": 50}}, "hba1c", "Must be at most 20"),
    ("assess", {"age": 60, "female": True, "as_of": "2026-11-14", "sbp": 400}, "sbp", "Must be at most 260"),
    ("assess", {"age": 60, "female": True, "as_of": "2026-11-14", "urine_samples": MANY}, "urine_samples", "Allows at most 30"),
    ("assess", {"age": 60, "female": True, "as_of": "2026-11-14", "egfr_history": []}, "egfr_history", "Unknown field."),
]


@pytest.mark.parametrize(("route", "body", "where", "message"), SHAPE_ERRORS)
def test_shape_errors_are_422_with_a_readable_message(api, route, body, where, message):
    detail = post(api, route, body, status=422)["detail"]
    assert any(error["loc"][0] == "body" and where in error["loc"] and message in error["msg"] for error in detail), detail


DOMAIN_ERRORS = [
    (
        "albuminuria",
        {**OK_ALBUMINURIA, "as_of": "2026-11-01"},
        "The assessment date (as_of, 11/01/2026) cannot be earlier than the last sample (11/02/2026).",
    ),
    (
        "assess",
        {"age": 60, "female": True, "urine_samples": DUDOSA, "as_of": "2026-10-31"},
        "The assessment date (as_of, 10/31/2026) cannot be earlier than the last urine sample (11/02/2026).",
    ),
    (
        "egfr-trend",
        {**FALLING, "as_of": "2026-10-26"},
        "The assessment date (as_of, 10/26/2026) cannot be earlier than the last lab test (10/27/2026).",
    ),
    (
        "egfr-trend",
        {**FALLING, "p_a2": 0.7, "p_a3": 0.6},
        "The albuminuria probabilities p_a2 and p_a3 cannot add up to more than 1.",
    ),
    (
        "egfr-trend",
        {"age": 68, "female": True, "measurements": []},
        "Without lab tests the assessment date (as_of) must be given.",
    ),
]


@pytest.mark.parametrize(("route", "body", "message"), DOMAIN_ERRORS)
def test_domain_errors_are_400_with_a_readable_message(api, route, body, message):
    assert post(api, route, body, status=400) == {"detail": message}


def test_limits_are_inclusive(api):
    edge = {"patient": {"age": 18, "female": True, "diabetes": False, "egfr": 5}, "as_of": "2026-11-02"}
    post(api, "albuminuria", {**edge, "samples": [lab("2026-11-02", 30000)]})  # as_of on the sample day
    post(api, "albuminuria", {**edge, "patient": {**edge["patient"], "age": 100, "egfr": 150}})
    got = post(api, "albuminuria", {"patient": BASE, "samples": MANY[:30], "as_of": "2026-11-14"})
    assert len(got["trajectory"]) == len(got["samples"]) == 30


def test_malformed_bodies_never_give_500(api):
    headers = {"content-type": "application/json"}
    broken = api.post("/api/model/albuminuria", content="{mal", headers=headers)
    assert broken.status_code == 422
    assert strict_json(broken.text)["detail"][0]["msg"] == "The request body is not valid JSON."
    # Python accepts NaN when reading JSON; the error must still be a 422 the browser can read.
    nan = api.post(
        "/api/model/albuminuria",
        content='{"patient": {"age": NaN, "female": false, "diabetes": false}, "as_of": "2026-11-14"}',
        headers=headers,
    )
    assert nan.status_code == 422
    assert strict_json(nan.text)["detail"][0]["loc"] == ["body", "patient", "age"]
    assert api.post("/api/model/assess", json=[1, 2]).status_code == 422
    assert api.post("/api/model/egfr-trend", content="", headers=headers).status_code == 422


# --------------------------------------------------------------------------------------
# Robustness, determinism, timing and docs
# --------------------------------------------------------------------------------------


def random_day(rng: random.Random, first: date, span_days: int) -> str:
    return (first + timedelta(days=rng.randint(0, span_days))).isoformat()


def random_urine_sample(rng: random.Random) -> dict:
    day = random_day(rng, date(2025, 1, 1), 680)
    if rng.random() < 0.4:
        albumin, creatinine = rng.choice([10, 30, 80, 150, 500]), rng.choice([10, 50, 100, 200, 300])
        return strip(day, albumin, creatinine, reader=rng.choice(["movil", "ojo"]))
    uacr = round(10 ** rng.uniform(-1, 4.4), 3)  # from 0.1 to 25000 mg/g
    sample_type, creatinine = rng.choice(["first_morning", "random"]), rng.choice([None, 8, 95, 600])
    return lab(day, uacr, sample_type, creatinine, censored=rng.random() < 0.15)


def test_random_valid_albuminuria_inputs_never_break(api):
    """Random valid inputs (fixed seed): always 200, no NaN and probabilities where they belong."""
    rng = random.Random(20261114)
    for _ in range(12):
        patient = {"age": rng.choice([18, 47, 73, 100]), "female": rng.random() < 0.5, "diabetes": rng.random() < 0.5}
        if rng.random() < 0.6:
            patient["egfr"] = rng.choice([5, 28, 61, 97, 150])
        samples = [random_urine_sample(rng) for _ in range(rng.randint(0, 6))]
        as_of = rng.choice(["2026-11-14", "2031-03-31"])
        got = post(api, "albuminuria", {"patient": patient, "samples": samples, "as_of": as_of})
        assert got["p_a1"] + got["p_a2"] + got["p_a3"] == pytest.approx(1.0, abs=1e-9)
        assert got["low"] <= got["median"] <= got["high"]
        assert sum(got["belief"]["mass"]) == pytest.approx(1.0, abs=1e-9)
        assert len(got["trajectory"]) == len(got["samples"]) == len(samples)


def test_random_valid_trend_inputs_never_break(api):
    rng = random.Random(20261116)
    for _ in range(40):
        measurements = [
            {
                "date": random_day(rng, date(2018, 1, 1), 3200),
                "egfr": round(rng.uniform(5, 150), 1),
                "source": rng.choice(["laboratorio", "capilar"]),
                "above": rng.random() < 0.1,
            }
            for _ in range(rng.randint(0, 9))
        ]
        treatments = [
            {"date": random_day(rng, date(2017, 1, 1), 3600), "kind": rng.choice(["isglt2", "ieca_ara2"])}
            for _ in range(rng.randint(0, 2))
        ]
        p_a2 = rng.random()
        body = {
            "age": rng.choice([18, 52, 79, 100]),
            "female": rng.random() < 0.5,
            "diabetes": rng.random() < 0.5,
            "p_a2": p_a2,
            "p_a3": rng.random() * (1 - p_a2),
            "measurements": measurements,
            "treatments": treatments,
            "as_of": "2026-11-14",
        }
        got = post(api, "egfr-trend", body)
        assert got["level_low"] <= got["level"] <= got["level_high"]
        assert all(0 <= p["low"] <= p["level"] <= p["high"] for p in got["projection"])
        assert len(got["projection"]) == (4 if measurements else 0)
        assert len(got["trajectory"]) == len(got["measurements"]) == got["n"] == len(measurements)


EXTREME_PATIENTS = {
    "joven_sin_datos": {"age": 18, "female": False, "as_of": "2026-11-14"},
    "centenarian_with_everything": {
        "age": 100,
        "female": True,
        "diabetes": True,
        "heart_failure": True,
        "kidney_disease": True,
        "smoker_now": True,
        "as_of": "2026-11-14",
    },
    "valores_en_el_limite": {
        "age": 39,
        "female": True,
        "bmi": 80,
        "waist": 200,
        "sbp": 260,
        "dbp": 160,
        "measured": {"egfr": 5, "nt_probnp": 100000},
        "urine_samples": [lab("2026-11-14", 30000)],
        "as_of": "2026-11-14",
    },
}


@pytest.mark.parametrize("name", EXTREME_PATIENTS)
def test_extreme_patients_never_break(api, name):
    check_kdigo_map(post(api, "assess", EXTREME_PATIENTS[name]))


# Inputs that can be typed in the web and for which the model, summing floating-point masses,
# returns 1.0000000000000002 or -2.2e-16: the A1 bar showed "-0%".
ALL_HIGH = [lab((date(2026, 11, 16) - timedelta(days=i)).isoformat(), 3000.0, "random") for i in range(6)]
ALL_A3 = [lab((date(2026, 11, 16) - timedelta(days=i)).isoformat(), 12000.0) for i in range(6)]
ROUNDING_CASES = [
    (
        "albuminuria",
        {"patient": {"age": 58, "female": True, "diabetes": False, "egfr": 88}, "samples": ALL_HIGH, "as_of": "2026-11-16"},
    ),
    ("albuminuria", {"patient": BASE, "samples": ALL_A3, "as_of": "2026-11-16"}),
    ("assess", {"age": 58, "female": True, "measured": {"egfr": 88}, "urine_samples": ALL_HIGH, "as_of": "2026-11-16"}),
    ("assess", {"age": 62, "female": False, "diabetes": True, "urine_samples": ALL_A3, "as_of": "2026-11-16"}),
    (
        "assess",
        {
            "age": 100,
            "female": True,
            "dbp": 88.6,
            "diabetes": True,
            "prediabetes": True,
            "diabetes_pills": True,
            "coronary": True,
            "measured": {"hba1c": 20, "glucose": 841.58, "non_hdl": 367.27},
            "urine_samples": [
                strip("2026-03-29", 150, 200, reader="ojo", sample_type="random"),
                strip("2025-11-23", 30, 300, reader="ojo"),
            ],
            "as_of": "2026-11-14",
        },
    ),
    (
        "egfr-trend",
        {
            "age": 66,
            "female": False,
            "measurements": [{"date": "2031-12-16", "egfr": 5}, {"date": "2025-01-01", "egfr": 63}],
            "treatments": [{"date": "2024-04-16", "kind": "ieca_ara2"}, {"date": "2025-05-14", "kind": "isglt2"}],
        },
    ),
]


@pytest.mark.parametrize(("route", "body"), ROUNDING_CASES)
def test_probabilities_never_leave_0_1_by_rounding(api, route, body):
    """Regression: ``post`` checks every probability in the response is in [0, 1] and never "-0"."""
    got = post(api, route, body)
    if route == "albuminuria":
        assert got["p_a1"] + got["p_a2"] + got["p_a3"] == pytest.approx(1.0, abs=1e-12)
        assert got["p_a2_plus"] == pytest.approx(got["p_a2"] + got["p_a3"], abs=1e-12)
        assert got["status"] == "pendiente_cronicidad" and got["p_a2_plus"] >= 0.999999
    elif route == "assess":
        check_kdigo_map(got)


def test_the_library_does_give_rounding_errors_for_those_inputs():
    """The previous regression inputs really trigger the error in the library."""
    filt = load_default_filter("espana")
    as_of = date(2026, 11, 16)
    first = filt.assess(Patient(58, True, False, 88, [library_sample(s) for s in ALL_HIGH]), as_of=as_of, detail=False)
    second = filt.assess(Patient(62, False, True, 75, [library_sample(s) for s in ALL_A3]), as_of=as_of, detail=False)
    values = [first.p_a1, first.p_a2_plus, second.p_a2, second.p_a3]
    if all(0.0 <= v <= 1.0 for v in values):
        pytest.skip("on this machine the sum does not exceed 1: the direct cleanup test remains")
    assert all(-1e-12 < v < 1.0 + 1e-12 for v in values)  # it is rounding, not a model bug


def test_probability_cleanup_only_touches_rounding_errors():
    clean_p = model._probability
    assert clean_p(1.0000000000000002) == 1.0
    assert clean_p(-2.220446049250313e-16) == 0.0
    assert math.copysign(1.0, clean_p(-0.0)) == 1.0  # no "-0"
    for untouched in (0.0, 1.0, 0.5, 1e-300, 0.9999999999999999, 2.2e-16):
        assert clean_p(untouched) == untouched
    # Something clearly outside [0, 1] would be a model bug: it is not hidden.
    assert clean_p(1.2) == 1.2 and clean_p(-0.3) == -0.3
    # It applies when building any output, also inside lists and dicts.
    cell = model.KdigoCellOut(a="A1", p=-2.220446049250313e-16, risk="bajo")
    assert cell.p == 0.0 and math.copysign(1.0, cell.p) == 1.0
    assert model.AlbuminuriaBeliefOut(uacr=[1.0, 2.0], mass=[1.0000000000000002, -0.0]).mass == [1.0, 0.0]
    assert model.NextSampleResolvesOut(first_morning=1.0000000000000002, random=0.25).first_morning == 1.0


def clear_caches() -> None:
    for cached in (model._albuminuria_cached, model._egfr_trend_cached, model._assess_cached):
        cached.cache_clear()


def test_routes_are_deterministic(api, examples):
    """The same request computed twice from scratch gives the same response, byte for byte."""
    requests = [
        ("albuminuria", {"patient": BASE, "samples": CON_TIRAS, "as_of": "2026-11-14"}),
        ("albuminuria", examples["patients"][0]["albuminuria"]),
        ("egfr-trend", TREND_CASES["tratamiento_y_albuminuria"]),
        ("assess", examples["patients"][1]["assess"]),
        ("assess", examples["patients"][3]["assess"]),
    ]
    for route, body in requests:
        clear_caches()
        first = api.post(f"/api/model/{route}", json=body)
        clear_caches()
        second = api.post(f"/api/model/{route}", json=body)
        assert first.status_code == second.status_code == 200
        assert first.content == second.content
    # And an already computed response is reused unchanged.
    hits = model._assess_cached.cache_info().hits
    assert api.post("/api/model/assess", json=requests[-1][1]).content == second.content
    assert model._assess_cached.cache_info().hits == hits + 1
    assert api.get("/api/model/examples").content == api.get("/api/model/examples").content


def test_warm_albuminuria_answers_in_time(api):
    post(api, "albuminuria", OK_ALBUMINURIA)  # leaves the filter loaded
    clear_caches()
    # Slow case: in doubt it also computes how much another sample would help, and it has strips.
    samples = [strip("2026-10-30", 30, 100), lab("2026-11-03", 36.5, creatinine=120)]
    body = {"patient": BASE, "samples": samples, "as_of": "2026-11-14"}
    start = time.perf_counter()
    got = post(api, "albuminuria", body)
    elapsed = time.perf_counter() - start
    assert got["status"] == "dudosa" and got["next_sample_resolves"] is not None
    assert elapsed < 2.0, f"warm albuminuria took {elapsed:.2f} s"


def test_warm_up_loads_models_and_leaves_examples_ready(api, examples):
    clear_caches()
    model.warm_up()
    assert model._albuminuria_cached.cache_info().currsize == 5
    assert model._egfr_trend_cached.cache_info().currsize == 2
    assert model._assess_cached.cache_info().currsize == 5
    # What the web sends (the example body, without null fields) finds the response ready.
    for route, cached, body in (
        ("albuminuria", model._albuminuria_cached, examples["patients"][2]["albuminuria"]),
        ("egfr-trend", model._egfr_trend_cached, examples["egfr_trends"][0]["egfr_trend"]),
        ("assess", model._assess_cached, examples["patients"][4]["assess"]),
    ):
        before = cached.cache_info()
        start = time.perf_counter()
        post(api, route, body)
        assert time.perf_counter() - start < 1.0
        after = cached.cache_info()
        assert (after.hits, after.misses) == (before.hits + 1, before.misses)


def test_docs_describe_every_route_and_field(api):
    schema = app.openapi()
    paths = schema["paths"]
    assert set(paths) == {f"/api/model/{name}" for name in ("albuminuria", "egfr-trend", "assess", "examples")}
    for path, methods in paths.items():
        for operation in methods.values():
            assert operation["summary"] and operation["description"]
            assert operation["tags"] == ["Live model"]
            assert "$ref" in operation["responses"]["200"]["content"]["application/json"]["schema"]  # response_model
            if path != "/api/model/examples":
                assert "$ref" in operation["responses"]["400"]["content"]["application/json"]["schema"]
    for name, definition in schema["components"]["schemas"].items():
        if name in ("HTTPValidationError", "ValidationError"):  # FastAPI's own
            continue
        for field, spec in definition.get("properties", {}).items():
            assert spec.get("description"), f"{name}.{field} has no description in /api/docs"
    # The body /api/docs offers in "Try it out" works as is.
    for route, body in (("albuminuria", "AlbuminuriaIn"), ("egfr-trend", "EgfrTrendIn"), ("assess", "AssessIn")):
        (example,) = schema["components"]["schemas"][body]["examples"]
        post(api, route, example)


# --------------------------------------------------------------------------------------
# Spanish (X-Lang: es): the original texts, exactly
# --------------------------------------------------------------------------------------

ES = {"X-Lang": "es"}


def test_status_and_action_in_spanish(api):
    body = {"patient": BASE, "samples": DUDOSA, "as_of": "2026-11-14"}
    spanish = api.post("/api/model/albuminuria", json=body, headers=ES)
    assert spanish.status_code == 200 and spanish.headers["content-language"] == "es"
    got = spanish.json()
    assert (got["status"], got["status_label"]) == ("dudosa", "Dudosa")
    assert "Probabilidad de que resuelva la duda: 7%" in got["action"]
    # The response cache is per language: English right after still comes in English.
    assert post(api, "albuminuria", body)["status_label"] == "Doubtful"
    trend = api.post("/api/model/egfr-trend", json=FALLING, headers=ES).json()
    assert (trend["status"], trend["status_label"]) == ("descenso_rapido", "descenso rápido")
    assert api.get("/api/model/examples", headers=ES).json()["egfr_trends"][1]["title"] == (
        "Mujer de 68 años, diabética: el filtrado se mantiene"
    )


def test_domain_errors_in_spanish(api):
    response = api.post("/api/model/albuminuria", json={**OK_ALBUMINURIA, "as_of": "2026-11-01"}, headers=ES)
    assert response.status_code == 400
    assert response.json() == {
        "detail": "La fecha de evaluación (as_of, 01/11/2026) no puede ser anterior a la última muestra (02/11/2026)."
    }
    response = api.post("/api/model/egfr-trend", json={"age": 68, "female": True, "measurements": []}, headers=ES)
    assert response.json() == {"detail": "Sin analíticas hay que indicar la fecha de evaluación (as_of)."}


@pytest.mark.parametrize(
    ("body", "where", "message"),
    [
        ({**OK_ALBUMINURIA, "patient": {**BASE, "age": 17}}, "age", "Debe ser como mínimo 18"),
        ({"patient": BASE, "samples": DUDOSA}, "as_of", "Falta este campo."),
        ({**OK_ALBUMINURIA, "as_of": "14/11/2026"}, "as_of", "Fecha no válida: se espera AAAA-MM-DD."),
        ({**OK_ALBUMINURIA, "population": "marte"}, "population", "Valor no admitido. Debe ser 'espana' o 'nhanes'"),
        ({**OK_ALBUMINURIA, "samples": [{"date": "2026-11-02", "uacr": 35}]}, "samples", "Falta el campo «kind»"),
    ],
)
def test_shape_errors_in_spanish(api, body, where, message):
    response = api.post("/api/model/albuminuria", json=body, headers=ES)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(where in error["loc"] and message in error["msg"] for error in detail), detail
