"""Forecast-error metrics. Missing/NaN inputs become JSON nulls."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _finite(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _num(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def compute_metrics(errors: pd.Series, actuals: pd.Series) -> dict[str, Any]:
    """MAE, RMSE, bias, normalised MAE, and 5th/95th percentile error.

    ``error = forecast - actual``. Positive error is an over-forecast:
    the desk would have under-bought the residual after wind.
    """
    err = pd.to_numeric(errors, errors="coerce")
    act = pd.to_numeric(actuals, errors="coerce")
    mask = err.notna() & act.notna()
    err_v = err[mask].to_numpy(dtype=float)
    act_v = act[mask].to_numpy(dtype=float)
    n = int(err_v.size)
    if n == 0:
        return {
            "n": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "nmae_pct": None,
            "p5": None,
            "p95": None,
        }

    mae = float(np.mean(np.abs(err_v)))
    rmse = float(np.sqrt(np.mean(np.square(err_v))))
    bias = float(np.mean(err_v))
    mean_actual = float(np.mean(act_v))
    nmae = (100.0 * mae / mean_actual) if mean_actual else None
    p5 = float(np.percentile(err_v, 5))
    p95 = float(np.percentile(err_v, 95))
    return {
        "n": n,
        "mae": _num(mae),
        "rmse": _num(rmse),
        "bias": _num(bias),
        "nmae_pct": _num(nmae),
        "p5": _num(p5),
        "p95": _num(p95),
    }


def group_metrics(frame: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    """Compute metrics for each value of ``key``, skipping empty groups."""
    if frame.empty or key not in frame.columns:
        return []
    rows: list[dict[str, Any]] = []
    for value, group in frame.groupby(key, dropna=True, sort=True):
        metrics = compute_metrics(group["error"], group["actual"])
        if hasattr(value, "item"):
            value = value.item()
        rows.append({"group": value if not isinstance(value, (float, int)) else value, **metrics})
    return rows


def compute_skill_score(forecasts: pd.Series, actuals: pd.Series) -> dict[str, Any]:
    """Compute forecast skill score compared to persistence forecast.

    Persistence forecast = previous period's actual (naive baseline).
    Skill score = 1 - (MSE_forecast / MSE_persistence).
    Positive skill score means forecast is better than persistence.
    """
    f = pd.to_numeric(forecasts, errors="coerce").dropna()
    a = pd.to_numeric(actuals, errors="coerce").dropna()
    
    if len(f) < 2 or len(a) < 2:
        return {"skill_score": None, "mse_forecast": None, "mse_persistence": None}
    
    # Align forecasts and actuals
    common_index = f.index.intersection(a.index)
    if len(common_index) < 2:
        return {"skill_score": None, "mse_forecast": None, "mse_persistence": None}
    
    f_aligned = f.loc[common_index]
    a_aligned = a.loc[common_index]
    
    # MSE of actual forecast
    mse_forecast = float(np.mean((f_aligned - a_aligned) ** 2))
    
    # MSE of persistence forecast (use previous actual)
    a_shifted = a_aligned.shift(1)
    valid_idx = a_shifted.notna()
    if valid_idx.sum() < 2:
        return {"skill_score": None, "mse_forecast": None, "mse_persistence": None}
    
    mse_persistence = float(np.mean((a_shifted[valid_idx] - a_aligned[valid_idx]) ** 2))
    
    if mse_persistence == 0:
        skill_score = None
    else:
        skill_score = 1.0 - (mse_forecast / mse_persistence)
    
    return {
        "skill_score": _num(skill_score),
        "mse_forecast": _num(mse_forecast),
        "mse_persistence": _num(mse_persistence),
    }
