from __future__ import annotations

from redis import Redis

from app.core.config import get_settings
from app.core.errors import AppError


def enforce_rate_limit(key: str, *, limit: int, window_seconds: int) -> None:
    settings = get_settings()
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        current = int(redis.incr(f"ratelimit:{key}"))
        if current == 1:
            redis.expire(f"ratelimit:{key}", max(int(window_seconds), 1))
        if current > int(limit):
            raise AppError("rate_limited", "too many requests", 429)
    except AppError:
        raise
    except Exception:
        return
