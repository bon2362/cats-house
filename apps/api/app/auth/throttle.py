"""In-memory limit on failed owner sign-ins, per client address.

One owner and one API process: memory is enough. Behind the public tunnel the
address comes from app.web.limits.client_address (the tunnel's trusted header).
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable


class LoginThrottle:
    def __init__(self, limit: int = 5, window_seconds: int = 900, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> tuple[float, deque[float]]:
        now = self.clock()
        failures = self._failures.get(key, deque())
        while failures and now - failures[0] >= self.window_seconds:
            failures.popleft()
        if failures:
            self._failures[key] = failures
        else:
            self._failures.pop(key, None)
        return now, failures

    def _wait(self, key: str) -> int | None:
        now, failures = self._recent(key)
        if len(failures) < self.limit:
            return None
        return max(1, math.ceil(failures[0] + self.window_seconds - now))

    def retry_after(self, key: str) -> int | None:
        """Seconds until a new attempt is allowed, or None when it is allowed now."""
        with self._lock:
            return self._wait(key)

    def reserve(self, key: str) -> int | None:
        """Count an attempt as failed before the (slow) password check.

        Returns the wait in seconds when the address is blocked. Checking and
        recording happen under one lock, so simultaneous requests cannot all
        pass the check before any failure is written. A successful sign-in
        calls reset(), which removes the reservation.
        """
        with self._lock:
            wait = self._wait(key)
            if wait is None:
                now, failures = self._recent(key)
                failures.append(now)
                self._failures[key] = failures
            return wait

    def record_failure(self, key: str) -> None:
        with self._lock:
            now, failures = self._recent(key)
            failures.append(now)
            self._failures[key] = failures

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
