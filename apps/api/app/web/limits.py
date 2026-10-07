"""Public mode: the visitor's address behind the tunnel and a per-address request limit."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import is_owner

LOCAL = {"127.0.0.1", "::1"}


def client_address(request: Request) -> str:
    """The tunnel's CF-Connecting-IP is trusted only in public mode and only from a local connection."""
    host = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if request.app.state.settings.public_mode and host in LOCAL and forwarded:
        return forwarded
    return host


class RequestLimiter:
    def __init__(self, limit: int = 120, window_seconds: int = 60, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_seconds, self.clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a request; seconds to wait when the address is over the limit (that request is not recorded)."""
        with self._lock:
            now = self.clock()
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, math.ceil(hits[0] + self.window_seconds - now))
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle addresses so memory stays bounded
                for stale in [name for name, value in self._hits.items() if not value or now - value[-1] >= self.window_seconds]:
                    self._hits.pop(stale, None)
            return None


def add_rate_limit(app: FastAPI) -> None:
    """Must be added before SessionMiddleware so the owner's session is readable here."""
    app.state.request_limiter = RequestLimiter()

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.app.state.settings.public_mode and request.url.path.startswith("/api/") and not is_owner(request):
            wait = request.app.state.request_limiter.hit(client_address(request))
            if wait is not None:
                return JSONResponse({"detail": "Слишком много запросов. Подождите минуту."}, status_code=429, headers={"Retry-After": str(wait)})
        return await call_next(request)
