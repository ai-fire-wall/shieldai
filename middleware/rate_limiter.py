"""
Redis-backed sliding window rate limiter.

Strategy: INCR + EXPIRE per (client_key : minute_bucket).
Fails open — if Redis is unreachable the request passes through,
so a Redis outage never takes down the firewall service.
"""

from __future__ import annotations

import time

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.utils.config import get_settings
from app.utils.logger import get_logger

settings = get_settings()
logger = get_logger("rate_limiter")

# Paths that bypass rate-limiting (ops endpoints)
_BYPASS_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})

# Singleton Redis client — lazily initialized
_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _redis


def _client_id(request: Request) -> str:
    """
    Prefer the API key as the rate-limit identity so different keys
    get independent buckets. Fall back to IP address.
    """
    key = request.headers.get(settings.api_key_header, "").strip()
    if key:
        return f"key:{key}"
    ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _BYPASS_PATHS:
            return await call_next(request)

        client = _client_id(request)
        limit = settings.rate_limit_per_minute
        window = int(time.time() // 60)
        redis_key = f"rl:{client}:{window}"

        try:
            r = await _get_redis()

            # Atomic increment; set TTL on first write (covers window boundary)
            async with r.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, 120)   # 2-minute TTL
                results = await pipe.execute()

            count: int = results[0]
            remaining = max(0, limit - count)

            if count > limit:
                logger.warning(
                    f"Rate limit hit",
                    extra={"extra": {"client": client, "count": count, "limit": limit}},
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error":               "rate_limit_exceeded",
                        "message":             f"Max {limit} requests per minute.",
                        "retry_after_seconds": 60 - (int(time.time()) % 60),
                    },
                    headers={
                        "X-RateLimit-Limit":     str(limit),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After":           "60",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        except Exception as exc:
            # Fail open — Redis unavailable should not block legitimate requests
            logger.error(f"Rate limiter error (failing open): {type(exc).__name__}: {exc}")
            return await call_next(request)


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
