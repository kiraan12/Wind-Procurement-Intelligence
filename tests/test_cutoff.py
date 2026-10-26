"""Cutoff selection must never use a forecast published after gate closure."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from cutoff import decision_cutoff, select_latest_forecasts


def test_latest_forecast_at_or_before_cutoff_is_used():
    cutoff = datetime(2026, 1, 14, 9, 20, tzinfo=timezone.utc)
    start = "2026-01-15T12:00:00Z"
    frame = pd.DataFrame(
        [
            {"startTime": start, "publishTime": "2026-01-14T07:30:00Z", "generation": 1000},
            {"startTime": start, "publishTime": "2026-01-14T04:30:00Z", "generation": 900},
        ]
    )
    selected = select_latest_forecasts(frame, cutoff)
    assert selected.loc[pd.Timestamp(start, tz="UTC"), "forecast"] == 1000


def test_forecast_published_after_cutoff_is_never_used():
    cutoff = datetime(2026, 1, 14, 9, 20, tzinfo=timezone.utc)
    start = "2026-01-15T12:00:00Z"
    frame = pd.DataFrame(
        [
            {"startTime": start, "publishTime": "2026-01-14T09:21:00Z", "generation": 5000},
            {"startTime": start, "publishTime": "2026-01-14T07:30:00Z", "generation": 1200},
        ]
    )
    selected = select_latest_forecasts(frame, cutoff)
    row = selected.loc[pd.Timestamp(start, tz="UTC")]
    assert row["forecast"] == 1200
    assert pd.Timestamp(row["publish_time"]) <= pd.Timestamp(cutoff)


def test_only_post_cutoff_forecast_yields_no_row():
    cutoff = datetime(2026, 1, 14, 9, 20, tzinfo=timezone.utc)
    frame = pd.DataFrame(
        [
            {
                "startTime": "2026-01-15T12:00:00Z",
                "publishTime": "2026-01-14T09:20:01Z",
                "generation": 8000,
            }
        ]
    )
    selected = select_latest_forecasts(frame, cutoff)
    assert selected.empty


def test_publish_exactly_at_cutoff_is_allowed():
    cutoff = datetime(2026, 1, 14, 9, 20, tzinfo=timezone.utc)
    start = "2026-01-15T00:00:00Z"
    frame = pd.DataFrame(
        [{"startTime": start, "publishTime": "2026-01-14T09:20:00Z", "generation": 3000}]
    )
    selected = select_latest_forecasts(frame, cutoff)
    assert selected.loc[pd.Timestamp(start, tz="UTC"), "forecast"] == 3000


def test_cutoff_on_spring_forward_boundary():
    """UK clocks spring forward on 2026-03-29. Delivery 30 Mar uses 29 Mar 09:20 BST."""
    london = ZoneInfo("Europe/London")
    cutoff = decision_cutoff(date(2026, 3, 30))
    expected = datetime(2026, 3, 29, 9, 20, tzinfo=london).astimezone(timezone.utc)
    assert cutoff == expected
    assert cutoff.hour == 8 and cutoff.minute == 20


def test_cutoff_on_morning_before_spring_forward():
    """Delivery 29 Mar still uses 28 Mar 09:20 GMT = 09:20 UTC."""
    cutoff = decision_cutoff(date(2026, 3, 29))
    assert cutoff == datetime(2026, 3, 28, 9, 20, tzinfo=timezone.utc)


def test_cutoff_on_autumn_back_boundary():
    """UK clocks fall back on 2026-10-25. Delivery 26 Oct uses 25 Oct 09:20 GMT."""
    cutoff = decision_cutoff(date(2026, 10, 26))
    assert cutoff == datetime(2026, 10, 25, 9, 20, tzinfo=timezone.utc)


def test_cutoff_while_still_on_bst():
    cutoff = decision_cutoff(date(2026, 10, 25))
    london = ZoneInfo("Europe/London")
    expected = datetime(2026, 10, 24, 9, 20, tzinfo=london).astimezone(timezone.utc)
    assert cutoff == expected
    assert cutoff == datetime(2026, 10, 24, 8, 20, tzinfo=timezone.utc)
