"""Tiny in-memory sliding-window rate limiter (per client IP).

Good enough for a single-process deployment. Behind several workers/instances
use a shared store (Redis) or a gateway limit instead.
"""
import os
import time
from collections import deque

from fastapi import HTTPException, Request

TRUST_PROXY = os.getenv("TRUST_PROXY", "").lower() in {"1", "true", "yes"}


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, name: str = "api"):
        self.limit = limit
        self.window = window_seconds
        self.name = name
        self._hits: dict[str, deque[float]] = {}
        self._calls = 0

    def __call__(self, request: Request) -> None:
        now = time.monotonic()
        ip = client_ip(request)
        q = self._hits.setdefault(ip, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = max(1, int(self.window - (now - q[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Too many {self.name} requests. Try again in {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)

        self._calls += 1
        if self._calls % 500 == 0:  # drop idle clients
            for key in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(key, None)


def limiter(env_name: str, default: int, name: str) -> RateLimiter:
    return RateLimiter(int(os.getenv(env_name, str(default))), 60, name)
