"""FastAPI app: evaluation API plus the built React UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from elexon import clear_cache, ensure_cache
from pipeline import day_payload, meta_payload, reset_evaluation, summary_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="GB Day-Ahead Wind Forecast Accuracy Desk",
    description="API for evaluating GB national wind forecast accuracy at gate closure. "
                "Compares Elexon WINDFOR forecasts available at 09:20 London on D-1 against FUELHH actuals.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", include_in_schema=False)
@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/summary")
def api_summary():
    return summary_payload()


@app.get("/api/day/{day}")
def api_day(day: str, price_per_mwh: float = 100.0):
    try:
        return day_payload(day, price_per_mwh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/meta")
def api_meta():
    return meta_payload()


@app.post("/api/refresh")
def api_refresh():
    clear_cache()
    reset_evaluation()
    ensure_cache(force=True)
    reset_evaluation()
    return {"status": "ok"}


# Static files and SPA must be mounted AFTER all API routes
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def spa_index():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="UI not built")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Don't intercept API routes or API docs
        if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="UI not built")


def run() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, factory=False)


if __name__ == "__main__":
    run()
