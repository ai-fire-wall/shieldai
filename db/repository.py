"""
Repository — all database interactions live here.
Business logic never touches SQLAlchemy directly.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FirewallLog
from app.utils.logger import get_logger

logger = get_logger("db.repository")


# ── Write ─────────────────────────────────────────────────────────────────────

async def save_log(
    session: AsyncSession,
    *,
    request_id: str,
    prompt_preview: str,
    provider: str,
    model: str,
    allowed: bool,
    input_threat_level: str,
    input_threats: list[str],
    input_ml_score: float | None = None,
    output_threat_level: str | None = None,
    output_issues: list[str] | None = None,
    latency_ms: float,
    metadata: dict[str, Any] | None = None,
) -> None:
    log = FirewallLog(
        request_id=request_id,
        prompt_preview=prompt_preview[:120],
        provider=provider,
        model=model or "default",
        allowed=allowed,
        input_threat_level=input_threat_level,
        input_threats=input_threats,
        input_ml_score=input_ml_score,
        output_threat_level=output_threat_level,
        output_issues=output_issues or [],
        latency_ms=latency_ms,
        meta=metadata or {},
    )
    session.add(log)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(f"DB write failed for {request_id}: {exc}")


# ── Read ──────────────────────────────────────────────────────────────────────

async def get_recent_logs(
    session: AsyncSession,
    limit: int = 50,
    allowed_only: bool | None = None,
    min_threat: str | None = None,
) -> list[dict]:
    q = select(FirewallLog).order_by(FirewallLog.created_at.desc()).limit(limit)
    if allowed_only is not None:
        q = q.where(FirewallLog.allowed == allowed_only)
    result = await session.execute(q)
    return [row.to_dict() for row in result.scalars().all()]


async def get_stats(
    session: AsyncSession,
    hours: int = 24,
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    total = await session.scalar(
        select(func.count()).where(FirewallLog.created_at >= since)
    ) or 0

    blocked = await session.scalar(
        select(func.count()).where(
            FirewallLog.created_at >= since,
            FirewallLog.allowed == False,  # noqa: E712
        )
    ) or 0

    avg_latency = await session.scalar(
        select(func.avg(FirewallLog.latency_ms)).where(
            FirewallLog.created_at >= since
        )
    ) or 0.0

    # Threat level breakdown
    threat_rows = await session.execute(
        select(FirewallLog.input_threat_level, func.count())
        .where(FirewallLog.created_at >= since)
        .group_by(FirewallLog.input_threat_level)
    )
    threat_breakdown: dict[str, int] = {row[0]: row[1] for row in threat_rows}

    # Provider breakdown
    provider_rows = await session.execute(
        select(FirewallLog.provider, func.count())
        .where(FirewallLog.created_at >= since)
        .group_by(FirewallLog.provider)
    )
    provider_breakdown: dict[str, int] = {row[0]: row[1] for row in provider_rows}

    # Hourly request counts (last 24 buckets for time-series chart)
    hourly: list[dict] = []
    for i in range(hours, 0, -1):
        bucket_start = datetime.now(timezone.utc) - timedelta(hours=i)
        bucket_end = bucket_start + timedelta(hours=1)
        count = await session.scalar(
            select(func.count()).where(
                FirewallLog.created_at >= bucket_start,
                FirewallLog.created_at < bucket_end,
            )
        ) or 0
        blocked_count = await session.scalar(
            select(func.count()).where(
                FirewallLog.created_at >= bucket_start,
                FirewallLog.created_at < bucket_end,
                FirewallLog.allowed == False,  # noqa: E712
            )
        ) or 0
        hourly.append({
            "hour":    bucket_start.strftime("%H:%M"),
            "total":   count,
            "blocked": blocked_count,
        })

    return {
        "period_hours":       hours,
        "total":              total,
        "blocked":            blocked,
        "passed":             total - blocked,
        "block_rate_pct":     round(blocked / max(total, 1) * 100, 1),
        "avg_latency_ms":     round(float(avg_latency), 1),
        "threat_breakdown":   threat_breakdown,
        "provider_breakdown": provider_breakdown,
        "hourly_series":      hourly,
    }
