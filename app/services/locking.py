from redis import Redis

from app.core.config import get_settings
from app.core.errors import AppError


class RedisLockManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True)

    def acquire(self, key: str, ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds or self.settings.generation_lock_ttl_seconds
        return bool(self.redis.set(key, "1", nx=True, ex=ttl))

    def release(self, key: str) -> None:
        self.redis.delete(key)


def acquire_generation_locks(session_id: str, user_id: str | None = None, guest_id: str | None = None) -> list[str]:
    manager = RedisLockManager()
    session_lock = f"lock:session:{session_id}:generation"
    if (user_id is None and guest_id is None) or (user_id is not None and guest_id is not None):
        raise AppError("invalid_request", "generation lock owner required", 400)
    owner_lock = f"lock:user:{user_id}:generation" if user_id is not None else f"lock:guest:{guest_id}:generation"
    acquired: list[str] = []

    try:
        if manager.acquire(session_lock):
            acquired.append(session_lock)
        else:
            raise AppError("job_already_running", http_status=409)

        if manager.acquire(owner_lock):
            acquired.append(owner_lock)
        else:
            raise AppError("job_already_running", http_status=409)
    except AppError:
        for key in acquired:
            manager.release(key)
        raise
    except Exception:
        # Redis 不可用时退回 DB 并发检查
        return []
    return acquired


def release_locks(lock_keys: list[str]) -> None:
    if not lock_keys:
        return
    manager = RedisLockManager()
    for key in lock_keys:
        try:
            manager.release(key)
        except Exception:
            continue
