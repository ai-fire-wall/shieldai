"""
main.py — FastAPI application entry point.
Render-compatible: reads PORT from environment, auto-runs DB migrations on startup.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository
from app.db.session import close_db, get_session, init_db
from app.firewall import process_request
from app.middleware.rate_limiter import RateLimiterMiddleware, close_redis
from app.ml.classifier import get_classifier
from app.models.schemas import (
    BlockedResponse,
    FirewallRequest,
    FirewallResponse,
    HealthResponse,
)
from app.utils.config import get_settings
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger("api")

_mem_stats: dict[str, Any] = defaultdict(int)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info(f"{settings.app_name} v{settings.app_version} starting")
    _mem_stats["started_at"] = time.time()

    # Warm up ML classifier (trains in ~80ms, done once at startup)
    await asyncio.get_event_loop().run_in_executor(None, get_classifier)
    logger.info("ML classifier ready")

    # Auto-create DB tables on startup (safe to run multiple times)
    if settings.log_to_db:
        await init_db()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Open-core AI security firewall. Intercepts every prompt and response, "
        "blocking prompt injection, data leakage, and harmful outputs."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)


# ── Auth ───────────────────────────────────────────────────────────────────────

async def _check_auth(request: Request) -> None:
    if not settings.api_keys:
        return
    key = request.headers.get(settings.api_key_header, "")
    if key not in settings.api_keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health():
    """Liveness probe — Render pings this to verify the service is up."""
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        filters=["input_filter", "ml_classifier", "output_filter"],
    )


@app.get("/v1/stats", tags=["ops"])
async def stats(
    hours: int = Query(24, ge=1, le=168),
    session: AsyncSession = Depends(get_session),
):
    try:
        db_stats = await repository.get_stats(session, hours=hours)
        return {"uptime_seconds": round(time.time() - _mem_stats.get("started_at", time.time()), 1), **db_stats}
    except Exception as exc:
        logger.error(f"Stats query failed: {exc}")
        total = _mem_stats["total"]
        blocked = _mem_stats["blocked"]
        return {
            "uptime_seconds": round(time.time() - _mem_stats.get("started_at", time.time()), 1),
            "total": total, "blocked": blocked,
            "passed": total - blocked,
            "block_rate_pct": round(blocked / max(total, 1) * 100, 1),
            "avg_latency_ms": 0, "hourly_series": [],
            "threat_breakdown": {}, "source": "in_memory",
        }


@app.get("/v1/logs", tags=["ops"])
async def logs(
    limit: int = Query(50, ge=1, le=200),
    blocked_only: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        rows = await repository.get_recent_logs(
            session, limit=limit,
            allowed_only=(False if blocked_only else None),
        )
        return {"logs": rows, "count": len(rows)}
    except Exception as exc:
        logger.error(f"Logs query failed: {exc}")
        return {"logs": [], "count": 0, "error": str(exc)}


@app.post("/v1/chat", response_model=FirewallResponse | BlockedResponse, tags=["firewall"])
async def chat(
    payload: FirewallRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Main firewall endpoint.
    Drop-in replacement for OpenAI/Anthropic — change one URL in your code.
    """
    await _check_auth(request)
    _mem_stats["total"] += 1

    try:
        result = await process_request(payload, db_session=session)
    except Exception as exc:
        _mem_stats["errors"] += 1
        logger.error(f"Unhandled error: {exc}", exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM provider error: {exc}")

    if isinstance(result, BlockedResponse):
        _mem_stats["blocked"] += 1
        return JSONResponse(status_code=400, content=result.model_dump())

    _mem_stats["passed"] += 1
    return result


# ── Entry point ────────────────────────────────────────────────────────────────
# Render sets PORT automatically. We read it here so gunicorn can use it.

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
