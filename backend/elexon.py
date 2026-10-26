"""Elexon Insights API client with on-disk JSON cache (one file per day)."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from config import (
    ACTUALS_CACHE_DIR,
    DELIVERY_END,
    DELIVERY_START,
    ELEXON_BASE,
    FORECASTS_CACHE_DIR,
)
from cutoff import forecast_fetch_window

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json", "User-Agent": "da-wind-desk/1.0"})


def _iso_z(moment: datetime) -> str:
    utc = moment.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str, params: dict[str, Any], retries: int = 4) -> list[dict[str, Any]]:
    url = f"{ELEXON_BASE}{path}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = SESSION.get(url, params=params, timeout=120)
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict) and "data" in payload:
                return list(payload["data"])
            raise ValueError(f"Unexpected payload from {url}")
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Elexon request failed {path} {params}: {last_error}")


def _write_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def actuals_path(day: date) -> Path:
    return ACTUALS_CACHE_DIR / f"{day.isoformat()}.json"


def forecasts_path(day: date) -> Path:
    return FORECASTS_CACHE_DIR / f"{day.isoformat()}.json"


def fetch_actuals_chunk(start: date, end: date) -> list[dict[str, Any]]:
    """FUELHH/stream: settlementDateFrom/To, fuelType=WIND."""
    return _get(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": start.isoformat(),
            "settlementDateTo": end.isoformat(),
            "fuelType": "WIND",
        },
    )


def fetch_forecasts_window(window_from: datetime, window_to: datetime) -> list[dict[str, Any]]:
    """WINDFOR/stream: publishDateTimeFrom/To (inclusive window, filtered later)."""
    return _get(
        "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": _iso_z(window_from),
            "publishDateTimeTo": _iso_z(window_to),
        },
    )


def _daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def cache_actuals(force: bool = False) -> None:
    """Download January actuals in 7-day chunks and split to one file per day."""
    ACTUALS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    missing = [d for d in _daterange(DELIVERY_START, DELIVERY_END) if force or not actuals_path(d).exists()]
    if not missing:
        return

    chunk_start = DELIVERY_START
    while chunk_start <= DELIVERY_END:
        chunk_end = min(chunk_start + timedelta(days=6), DELIVERY_END)
        rows = fetch_actuals_chunk(chunk_start, chunk_end)
        by_day: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = row.get("settlementDate") or str(row.get("startTime", ""))[:10]
            by_day.setdefault(key, []).append(row)
        for day in _daterange(chunk_start, chunk_end):
            _write_json(actuals_path(day), by_day.get(day.isoformat(), []))
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.25)


def cache_forecasts(force: bool = False) -> None:
    """For each delivery day, cache WINDFOR publishes in the 12h pre-cutoff window."""
    try:
        FORECASTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    for day in _daterange(DELIVERY_START, DELIVERY_END):
        path = forecasts_path(day)
        if path.exists() and not force:
            continue
        window_from, window_to = forecast_fetch_window(day)
        rows = fetch_forecasts_window(window_from, window_to)
        _write_json(path, rows)
        time.sleep(0.25)


def ensure_cache(force: bool = False) -> None:
    cache_actuals(force=force)
    cache_forecasts(force=force)


def clear_cache() -> None:
    for folder in (ACTUALS_CACHE_DIR, FORECASTS_CACHE_DIR):
        if not folder.exists():
            continue
        for file in folder.glob("*.json"):
            try:
                file.unlink()
            except OSError:
                pass


def load_day_actuals(day: date) -> list[dict[str, Any]]:
    path = actuals_path(day)
    if not path.exists():
        return []
    return _read_json(path)


def load_day_forecasts(day: date) -> list[dict[str, Any]]:
    path = forecasts_path(day)
    if not path.exists():
        return []
    return _read_json(path)
