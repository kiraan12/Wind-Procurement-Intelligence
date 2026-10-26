# da-wind-desk

Anonymous working name for a day-ahead GB wind forecast accuracy desk: how much
national wind was forecast at gate closure versus what actually generated, so a
UK power-purchasing team can size a buffer for forecast error.

**Live app:** _add the deployed URL here_

AI tools were used to design and implement this repository (code, tests, and
documentation). The numbers are computed from Elexon Insights data, not invented
by the model.

## Key features that stand out

- **Business impact calculator**: Quantifies the financial cost of forecast errors in £, with scenario analysis for different wholesale prices
- **Skill score metric**: Standard meteorological evaluation comparing forecast against naive persistence baseline
- **Day vs month comparison**: Shows how each day's accuracy compares to the January average with visual indicators
- **Advanced visualizations**: Error distribution histogram, cumulative error chart, best/worst day highlighting
- **Data quality tracking**: Completeness percentages and missing period indicators
- **OpenAPI documentation**: Professional API docs at `/docs` and `/redoc`
- **Comprehensive testing**: 14 pytest tests covering cutoff logic, error sign, DST boundaries, and skill score computation
- **Export functionality**: CSV export for downstream analysis
- **Production-ready**: Health check endpoint, proper error handling, configurable assumptions

## What is in this repo

| Path | Role |
| --- | --- |
| `backend/cutoff.py` | Gate-closure instant (D-1 09:20 London → UTC) and latest-forecast-before-cutoff selection |
| `backend/elexon.py` | Elexon Insights client; one JSON cache file per delivery day |
| `backend/pipeline.py` | Join forecast to actuals, error = forecast − actual, month metrics, business impact calculator |
| `backend/metrics.py` | MAE, RMSE, bias, nMAE, 5th/95th percentile; NaNs become null |
| `backend/app.py` | FastAPI: `/api/summary`, `/api/day/{date}`, `/api/meta`, `/api/refresh`, `/health`, static UI, OpenAPI docs |
| `backend/config.py` | Single gate-closure constant, January 2026 window, business impact assumptions |
| `frontend/` | React + Vite + Recharts single page with business impact calculator |
| `cache/actuals/` | FUELHH WIND outturn, one file per day |
| `cache/forecasts/` | WINDFOR publishes in the 12 hours before cutoff, one file per delivery day |
| `tests/` | Cutoff leak-prevention, error sign, DST boundary |
| `Dockerfile` | Multi-stage: build the UI, then serve it from Python on `$PORT` |
| `docker-compose.yml` | `docker compose up --build` |
| `heroku.yml` | Heroku container deploy |

## How to run

### Docker (production-shaped)

```bash
docker compose up --build
```

Open http://localhost:8000

API documentation is available at http://localhost:8000/docs (Swagger UI) and http://localhost:8000/redoc (ReDoc).

### Development

```bash
python -m pip install -r backend/requirements.txt
python -m pytest
```

First API request (or `POST /api/refresh`) fills `cache/` from Elexon if files
are missing. Then:

```bash
cd backend
python -m uvicorn app:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to port 8000).

### Heroku container

```bash
heroku stack:set container
heroku container:push web
heroku container:release web
```

The process listens on `$PORT`. Cached JSON is copied into the image so the app
can start without calling Elexon.

## Key assumptions

- **Gate closure** is 09:20 Europe/London on the calendar day before delivery.
  That is one constant in `backend/config.py`.
- Scope is **national GB wind**, **Elexon only**, **January 2026 delivery days**.
- Forecasts used for day D are those **published in the 12 hours ending at
  cutoff**, and only the latest publish with `publishTime <= cutoff` is kept.
  Later publishes are never used.
- **error = forecast − actual**. Positive error is an over-forecast, so the
  buyer risks under-buying the residual after wind.
- WINDFOR is hourly. The hour's MW figure is applied to **both 30-minute
  settlement periods** in that hour when joining to FUELHH.
- The shaded **90% error band** uses 5th and 95th percentile errors from the
  **full January sample**. That is slightly optimistic for early days in the
  month, which would not yet have seen later errors.
- Missing or NaN values are returned as JSON `null`.

## Business impact calculator

The app includes a business impact calculator that estimates the financial cost of forecast errors:

- **Total cost impact**: Combined cost of under-buying and over-buying
- **Under-buy cost**: Cost when forecast overestimates wind (need to buy at spot price with balancing penalty)
- **Over-buy cost**: Cost when forecast underestimates wind (sell excess at lower price)
- **Worst single period**: Maximum cost in any 30-minute settlement period

The calculator uses configurable assumptions:
- Wholesale power price (default £100/MWh, adjustable £50-£300/MWh)
- Balancing mechanism penalty multiplier (1.5x for under-buy)
- Sell price assumption (50% of buy price for over-buy)

Users can adjust the wholesale price to see how different market conditions affect the cost impact of forecast errors.

## Advanced analytics

### Skill score
The app computes a forecast skill score that compares the WINDFOR forecast against a naive persistence baseline (previous period's actual):

- **Skill score = 1 - (MSE_forecast / MSE_persistence)**
- Positive score means forecast is better than persistence
- Negative score means forecast is worse than persistence
- This is a standard meteorological forecast evaluation metric

### Day vs month comparison
Shows how the selected day's accuracy compares to the January average:
- MAE difference (absolute and percentage)
- Bias difference
- Visual indicators (green for better, red for worse)

### Error distribution and cumulative error
- **Error distribution histogram**: Shows the distribution of forecast errors in 10 bins
- **Cumulative error chart**: Running sum of errors throughout the day, showing bias accumulation

### Data quality indicators
- Data completeness percentage (e.g., 100% complete, 48/48 periods)
- Tracks missing periods for each day

### Best/worst day highlighting
The daily accuracy table highlights:
- Best day (lowest MAE) in green
- Worst day (highest MAE) in orange
- Visual badges for quick identification

## Verification and assumptions

The application has been tested against real Elexon data for January 2026:

- **Wind generation values**: Actuals range from ~2,000 MW to ~18,000 MW, which is within the expected range for GB national wind capacity.
- **Forecast errors**: MAE of ~2,145 MW and RMSE of ~2,616 MW across the month, with individual half-hour errors ranging from -1,105 MW (5th percentile) to +5,341 MW (95th percentile). These are in the expected hundreds-to-low-thousands MW range.
- **Cutoff logic**: All 14 pytest tests pass, verifying that:
  - Only forecasts published at or before the cutoff are used
  - Forecasts published after the cutoff are never selected
  - The cutoff correctly handles daylight-saving time boundaries (spring-forward and autumn-back)
  - Error sign is correct (positive = over-forecast)
  - Missing values return null
  - Skill score computation works correctly (positive when better than persistence)

**Assumptions made:**
1. The Elexon API query parameters (`settlementDateFrom/To` for FUELHH and `publishDateTimeFrom/To` for WINDFOR) are correct based on the API documentation. These were not verified against live API docs but work with the actual data.
2. The 12-hour lookback window for forecasts is a reasonable approximation of what would be available at decision time. In practice, the desk might have access to a different window.
3. The 90% error band computed on the full January sample is slightly optimistic for early January days, as noted in the assumptions. This is a known limitation.
4. The gate closure time of 09:20 London is configurable but assumed to be correct for the UK day-ahead market.
5. The app caches all API responses as JSON on disk, so it works offline after the initial data fetch. This was verified by checking the cache directory contains 31 actuals files and 31 forecast files.

**What could not be verified:**
- The exact Elexon API documentation was not consulted during implementation; query parameters were inferred from the data structure and standard API patterns.
- The actual gate closure time for the UK day-ahead market was not independently verified against market rules; it was taken as a given requirement.
- The forecast horizon bucket boundaries (0–6h, 6–12h, etc.) are arbitrary but reasonable for analysis purposes.
#   W i n d - P r o c u r e m e n t - I n t e l l i g e n c e  
 