"""Decision-time cutoff and latest-available forecast selection.

The purchasing desk must not use any wind forecast published after gate
closure. All evaluation of forecast skill is therefore as-of the cutoff,
not as-of the delivery period.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from config import FORECAST_LOOKBACK, GATE_CLOSURE_TIME, HORIZON_BUCKETS, LONDON_TZ


def decision_cutoff(delivery_day: date) -> datetime:
    """Return the timezone-aware cutoff instant for delivery day D.

    Gate closure is ``GATE_CLOSURE_TIME`` on D-1 in ``Europe/London``.
    ``zoneinfo`` converts that local civil time to an unambiguous UTC
    instant, including across the spring-forward and autumn-back
    daylight-saving boundaries.

    Example (winter GMT): delivery 2026-01-15 → 2026-01-14 09:20 London
    = 2026-01-14 09:20 UTC.

    Example (summer BST): delivery 2026-07-15 → 2026-07-14 09:20 London
    = 2026-07-14 08:20 UTC.
    """
    day_before = delivery_day - timedelta(days=1)
    local = datetime.combine(day_before, GATE_CLOSURE_TIME, tzinfo=LONDON_TZ)
    return local.astimezone(timezone.utc)


def forecast_fetch_window(delivery_day: date) -> tuple[datetime, datetime]:
    """Inclusive UTC window of publishes that may be used for day D.

    Only forecasts published in the 12 hours ending at the cutoff are
    fetched. Anything later is unavailable at decision time; anything
    earlier is superseded by a more recent in-window publish.
    """
    cutoff = decision_cutoff(delivery_day)
    return cutoff - FORECAST_LOOKBACK, cutoff


def to_utc(value: Any) -> datetime | None:
    """Parse an Elexon timestamp to UTC, or return None if missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def horizon_bucket(start: datetime, published: datetime) -> str | None:
    """Bucket the forecast horizon ``startTime - publishTime``."""
    if start is None or published is None:
        return None
    hours = (start - published).total_seconds() / 3600.0
    if hours < 0:
        return None
    for upper, label in HORIZON_BUCKETS:
        if upper is None or hours < upper:
            return label
    return "36h+"


def select_latest_forecasts(
    forecasts: pd.DataFrame,
    cutoff: datetime,
) -> pd.DataFrame:
    """Keep, for each ``startTime``, the latest publish at or before cutoff.

    Rows with ``publishTime`` strictly after ``cutoff`` are dropped so
    the evaluation never leaks information that the desk did not have
    at gate closure. If several publishes for the same settlement
    interval are still in-window, the maximum ``publishTime`` wins.

    Returns a frame indexed uniquely by ``startTime`` with columns
    ``forecast`` (MW) and ``publish_time``.
    """
    if forecasts.empty:
        return pd.DataFrame(columns=["forecast", "publish_time"])

    frame = forecasts.copy()
    frame["start_time"] = pd.to_datetime(frame["startTime"], utc=True)
    frame["publish_time"] = pd.to_datetime(frame["publishTime"], utc=True)
    cutoff_ts = pd.Timestamp(cutoff)
    if cutoff_ts.tzinfo is None:
        cutoff_ts = cutoff_ts.tz_localize("UTC")

    in_window = frame.loc[frame["publish_time"] <= cutoff_ts]
    if in_window.empty:
        return pd.DataFrame(columns=["forecast", "publish_time"])

    in_window = in_window.sort_values(["start_time", "publish_time"])
    latest = in_window.groupby("start_time", as_index=True).last()
    return latest.rename(columns={"generation": "forecast"})[["forecast", "publish_time"]]
