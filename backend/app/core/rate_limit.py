"""Small in-memory sliding-window rate limiter.

Limits are per client IP and per process. With several workers or servers, each keeps its own
counters; use a shared store (for example Redis) if you need exact global limits.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])))
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many requests. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit_getter):
    """Dependency factory. `limit_getter` returns the per-minute limit (read at request time)."""

    def dependency(request: Request) -> None:
        limiter.check(f"{name}:{client_ip(request)}", limit_getter())

    return dependency
