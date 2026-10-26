"""Join as-of-cutoff forecasts to half-hourly actuals and compute metrics."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd

from config import (
    BALANCING_PENALTY_MULTIPLIER,
    DELIVERY_END,
    DELIVERY_START,
    GATE_CLOSURE_TIME,
    LONDON_TZ,
    WHOLESALE_PRICE_BASE,
)
from cutoff import decision_cutoff, horizon_bucket, select_latest_forecasts
from elexon import ensure_cache, load_day_actuals, load_day_forecasts
from metrics import compute_metrics, compute_skill_score, group_metrics


def _delivery_days() -> list[date]:
    days: list[date] = []
    day = DELIVERY_START
    while day <= DELIVERY_END:
        days.append(day)
        day += timedelta(days=1)
    return days


def _align_forecast(
    start: pd.Timestamp,
    selected: pd.DataFrame,
) -> tuple[float | None, pd.Timestamp | None]:
    """Map a half-hour actual onto the hourly WINDFOR series.

    WINDFOR publishes MW for hourly ``startTime`` values (xx:00). FUELHH
    actuals are 30-minute. When there is no exact ``startTime`` match,
    the forecast for the containing hour is used for both settlement
    periods. This does not change publishTime, so it does not leak
    post-cutoff information.
    """
    if start in selected.index:
        row = selected.loc[start]
        return _scalar(row["forecast"]), row["publish_time"]
    hour = start.floor("h")
    if hour in selected.index:
        row = selected.loc[hour]
        return _scalar(row["forecast"]), row["publish_time"]
    return None, None


def _scalar(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def build_day_frame(delivery_day: date) -> tuple[pd.DataFrame, dict[str, Any]]:
    cutoff = decision_cutoff(delivery_day)
    actual_rows = load_day_actuals(delivery_day)
    forecast_rows = load_day_forecasts(delivery_day)
    forecasts = pd.DataFrame(forecast_rows)
    selected = select_latest_forecasts(forecasts, cutoff) if not forecasts.empty else pd.DataFrame()

    records: list[dict[str, Any]] = []
    for row in actual_rows:
        start = pd.to_datetime(row.get("startTime"), utc=True)
        if pd.isna(start):
            continue
        actual = _scalar(row.get("generation"))
        forecast, published = _align_forecast(start, selected) if not selected.empty else (None, None)
        error = None
        if forecast is not None and actual is not None:
            error = forecast - actual
        published_dt = published.to_pydatetime() if published is not None and not pd.isna(published) else None
        start_dt = start.to_pydatetime()
        london_hour = start.tz_convert(LONDON_TZ).hour
        records.append(
            {
                "delivery_day": delivery_day.isoformat(),
                "start_time": start_dt,
                "actual": actual,
                "forecast": forecast,
                "error": error,
                "publish_time": published_dt,
                "london_hour": int(london_hour),
                "horizon_bucket": horizon_bucket(start_dt, published_dt) if published_dt else None,
            }
        )

    frame = pd.DataFrame.from_records(records)
    latest_publish = None
    if not frame.empty and frame["publish_time"].notna().any():
        latest_publish = pd.to_datetime(frame["publish_time"], utc=True).max().isoformat()
    meta = {
        "delivery_day": delivery_day.isoformat(),
        "cutoff": cutoff.isoformat(),
        "latest_publish": latest_publish,
    }
    return frame, meta


def _iso(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@lru_cache(maxsize=1)
def evaluate_month() -> dict[str, Any]:
    ensure_cache()
    frames: list[pd.DataFrame] = []
    day_meta: dict[str, dict[str, Any]] = {}
    for day in _delivery_days():
        frame, meta = build_day_frame(day)
        day_meta[day.isoformat()] = meta
        if not frame.empty:
            frames.append(frame)

    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    overall = compute_metrics(
        all_rows["error"] if not all_rows.empty else pd.Series(dtype=float),
        all_rows["actual"] if not all_rows.empty else pd.Series(dtype=float),
    )

    daily: list[dict[str, Any]] = []
    for day in _delivery_days():
        key = day.isoformat()
        subset = all_rows[all_rows["delivery_day"] == key] if not all_rows.empty else pd.DataFrame()
        metrics = compute_metrics(
            subset["error"] if not subset.empty else pd.Series(dtype=float),
            subset["actual"] if not subset.empty else pd.Series(dtype=float),
        )
        daily.append({**day_meta[key], "metrics": metrics})

    by_hour = group_metrics(all_rows, "london_hour") if not all_rows.empty else []
    by_horizon = group_metrics(all_rows, "horizon_bucket") if not all_rows.empty else []
    if by_horizon:
        order = {label: i for i, (_, label) in enumerate(
            ((6, "0–6h"), (12, "6–12h"), (18, "12–18h"), (24, "18–24h"), (36, "24–36h"), (None, "36h+"))
        )}
        by_horizon.sort(key=lambda row: order.get(row["group"], 99))

    return {
        "overall": overall,
        "daily": daily,
        "by_hour": by_hour,
        "by_horizon": by_horizon,
        "frames": all_rows,
        "day_meta": day_meta,
    }


def summary_payload() -> dict[str, Any]:
    result = evaluate_month()
    return {
        "overall": result["overall"],
        "daily": result["daily"],
        "by_hour": result["by_hour"],
        "by_horizon": result["by_horizon"],
    }


def day_payload(day_str: str, price_per_mwh: float = WHOLESALE_PRICE_BASE) -> dict[str, Any]:
    day = date.fromisoformat(day_str)
    if day < DELIVERY_START or day > DELIVERY_END:
        raise ValueError("Delivery day is outside the January 2026 evaluation window.")
    result = evaluate_month()
    frames: pd.DataFrame = result["frames"]
    subset = frames[frames["delivery_day"] == day.isoformat()] if not frames.empty else pd.DataFrame()
    meta = result["day_meta"][day.isoformat()]
    metrics = compute_metrics(
        subset["error"] if not subset.empty else pd.Series(dtype=float),
        subset["actual"] if not subset.empty else pd.Series(dtype=float),
    )
    skill_score = compute_skill_score(
        subset["forecast"] if not subset.empty else pd.Series(dtype=float),
        subset["actual"] if not subset.empty else pd.Series(dtype=float),
    )
    business_impact = calculate_business_impact(
        subset["error"] if not subset.empty else pd.Series(dtype=float),
        price_per_mwh,
    )
    p5 = result["overall"].get("p5")
    p95 = result["overall"].get("p95")
    series = []
    data_quality = {
        "total_periods": 48,
        "available_periods": 0,
        "missing_periods": 0,
        "completeness_pct": 0,
    }
    if not subset.empty:
        ordered = subset.sort_values("start_time")
        for _, row in ordered.iterrows():
            forecast = _scalar(row["forecast"])
            band_low = None
            band_high = None
            if forecast is not None and p5 is not None and p95 is not None:
                # actual = forecast - error, error in [p5, p95]
                band_low = forecast - p95
                band_high = forecast - p5
            series.append(
                {
                    "t": _iso(row["start_time"]),
                    "actual": _scalar(row["actual"]),
                    "forecast": forecast,
                    "error": _scalar(row["error"]),
                    "publish": _iso(row["publish_time"]),
                    "band_low": band_low,
                    "band_high": band_high,
                }
            )
        data_quality["available_periods"] = len(series)
        data_quality["missing_periods"] = 48 - len(series)
        data_quality["completeness_pct"] = round((len(series) / 48) * 100, 1)
    return {
        "cutoff": meta["cutoff"],
        "latest_publish": meta["latest_publish"],
        "metrics": metrics,
        "overall": result["overall"],
        "business_impact": business_impact,
        "skill_score": skill_score,
        "series": series,
        "data_quality": data_quality,
    }


def meta_payload() -> dict[str, Any]:
    return {
        "gate_closure": f"{GATE_CLOSURE_TIME.strftime('%H:%M')} {LONDON_TZ.key} on D-1",
        "gate_closure_time": GATE_CLOSURE_TIME.strftime("%H:%M"),
        "timezone": LONDON_TZ.key,
        "delivery_window": {
            "from": DELIVERY_START.isoformat(),
            "to": DELIVERY_END.isoformat(),
        },
        "scope": "National GB wind only",
        "sources": [
            {
                "name": "FUELHH",
                "url": "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream",
                "role": "Half-hourly wind outturn (fuelType=WIND)",
            },
            {
                "name": "WINDFOR",
                "url": "https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream",
                "role": "Wind generation forecast as published",
            },
        ],
        "error_definition": "error = forecast - actual (positive = over-forecast / under-buy risk)",
        "error_band": (
            "The 90% band around the forecast uses the 5th and 95th percentile "
            "errors computed on the full January sample. That is slightly "
            "optimistic for early days in the month."
        ),
        "forecast_alignment": (
            "WINDFOR is hourly. The hour's forecast is applied to both "
            "30-minute settlement periods in that hour."
        ),
    }


def reset_evaluation() -> None:
    evaluate_month.cache_clear()


def calculate_business_impact(
    errors: pd.Series,
    price_per_mwh: float = WHOLESALE_PRICE_BASE,
) -> dict[str, Any]:
    """Calculate the financial impact of forecast errors.

    Args:
        errors: Series of forecast errors (forecast - actual) in MW
        price_per_mwh: Wholesale power price in £/MWh

    Returns:
        Dictionary with cost metrics in £
    """
    err = pd.to_numeric(errors, errors="coerce").dropna()
    if err.empty:
        return {
            "total_cost": None,
            "under_buy_cost": None,
            "over_buy_cost": None,
            "max_single_period_cost": None,
        }

    # Positive error = over-forecast = under-bought = need to buy at spot price
    under_buy_errors = err[err > 0]
    under_buy_mwh = under_buy_errors.sum() * 0.5  # 30-min periods
    under_buy_cost = under_buy_mwh * price_per_mwh * BALANCING_PENALTY_MULTIPLIER

    # Negative error = under-forecast = over-bought = sell at lower price
    over_buy_errors = err[err < 0]
    over_buy_mwh = abs(over_buy_errors.sum()) * 0.5
    over_buy_cost = over_buy_mwh * price_per_mwh * 0.5  # Assume sell at 50% of buy price

    total_cost = under_buy_cost + over_buy_cost
    max_single_period_cost = err.abs().max() * 0.5 * price_per_mwh * BALANCING_PENALTY_MULTIPLIER

    return {
        "total_cost": round(total_cost, 2),
        "under_buy_cost": round(under_buy_cost, 2),
        "over_buy_cost": round(over_buy_cost, 2),
        "max_single_period_cost": round(max_single_period_cost, 2),
        "price_assumption": price_per_mwh,
    }
