"""Error sign: forecast minus actual. Positive is over-forecast / under-buy risk."""

from __future__ import annotations

import pandas as pd

from metrics import compute_metrics, compute_skill_score


def test_overforecast_is_positive_error():
    forecast, actual = 5000.0, 4200.0
    error = forecast - actual
    assert error == 800.0
    metrics = compute_metrics(pd.Series([error]), pd.Series([actual]))
    assert metrics["bias"] == 800.0
    assert metrics["mae"] == 800.0


def test_underforecast_is_negative_error():
    forecast, actual = 3000.0, 4500.0
    error = forecast - actual
    assert error == -1500.0
    metrics = compute_metrics(pd.Series([error]), pd.Series([actual]))
    assert metrics["bias"] == -1500.0
    assert metrics["mae"] == 1500.0


def test_missing_values_become_null():
    metrics = compute_metrics(pd.Series([float("nan")]), pd.Series([float("nan")]))
    assert metrics["n"] == 0
    assert metrics["mae"] is None
    assert metrics["rmse"] is None
    assert metrics["bias"] is None
    assert metrics["nmae_pct"] is None
    assert metrics["p5"] is None
    assert metrics["p95"] is None


def test_skill_score_better_than_persistence():
    """Forecast that's better than persistence should have positive skill score."""
    forecasts = pd.Series([100, 110, 120, 130])
    actuals = pd.Series([95, 105, 115, 125])
    result = compute_skill_score(forecasts, actuals)
    assert result["skill_score"] is not None
    assert result["skill_score"] > 0


def test_skill_score_worse_than_persistence():
    """Forecast that's worse than persistence should have negative skill score."""
    forecasts = pd.Series([100, 100, 100, 100])  # Constant forecast
    actuals = pd.Series([95, 105, 115, 125])  # Trending up
    result = compute_skill_score(forecasts, actuals)
    assert result["skill_score"] is not None
    assert result["skill_score"] < 0


def test_skill_score_insufficient_data():
    """Insufficient data should return null skill score."""
    result = compute_skill_score(pd.Series([100]), pd.Series([95]))
    assert result["skill_score"] is None
