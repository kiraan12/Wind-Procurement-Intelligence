"""Configurable assumptions for the day-ahead wind evaluation."""

from __future__ import annotations

import os
from datetime import date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Gate closure: 09:20 Europe/London on the calendar day before delivery.
# Kept as a single constant so the whole pipeline moves together if the
# desk's decision deadline changes.
GATE_CLOSURE_TIME = time(9, 20)
LONDON_TZ = ZoneInfo("Europe/London")

FORECAST_LOOKBACK = timedelta(hours=12)

DELIVERY_START = date(2026, 1, 1)
DELIVERY_END = date(2026, 1, 31)

ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1"

CACHE_DIR = Path(os.environ.get("CACHE_DIR", Path(__file__).resolve().parent.parent / "cache"))
ACTUALS_CACHE_DIR = CACHE_DIR / "actuals"
FORECASTS_CACHE_DIR = CACHE_DIR / "forecasts"

HORIZON_BUCKETS = (
    (6, "0–6h"),
    (12, "6–12h"),
    (18, "12–18h"),
    (24, "18–24h"),
    (36, "24–36h"),
    (None, "36h+"),
)

# Business impact assumptions (configurable for scenario analysis)
# Typical UK wholesale power price range in £/MWh
WHOLESALE_PRICE_LOW = 50.0
WHOLESALE_PRICE_HIGH = 150.0
WHOLESALE_PRICE_BASE = 100.0

# Balancing mechanism penalty for imbalance
BALANCING_PENALTY_MULTIPLIER = 1.5
