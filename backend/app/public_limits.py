"""Rate limits for public questions (US-027).

Public questions are anonymous and each answer can cost a Claude call, so one visitor must not be
able to use up the organisation's daily answers. Limits are kept in memory per process and keyed
on a salted hash of the visitor's address: nothing is written to the database and the address is
never stored (US-035B). Restarting the server resets the counts, which is acceptable for beta.
"""

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache

from app.config import get_settings


class RateLimiter:
    def __init__(self, per_minute: int, per_hour: int, clock=time.monotonic):
        self.windows = ((60.0, per_minute), (3600.0, per_hour))
        self.clock = clock
        self._salt = secrets.token_bytes(16)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, visitor: str, scope: str) -> str:
        return hashlib.sha256(self._salt + f"{scope}|{visitor}".encode()).hexdigest()

    def allow(self, visitor: str, scope: str) -> bool:
        """Record a request and say whether it is within the limits."""
        now = self.clock()
        key = self._key(visitor, scope)
        with self._lock:
            hits = self._hits[key]
            longest = max(w for w, _ in self.windows)
            while hits and now - hits[0] >= longest:
                hits.popleft()
            for window, limit in self.windows:
                if sum(1 for t in hits if now - t < window) >= limit:
                    return False
            hits.append(now)
            # Keep memory bounded: forget visitors with no recent requests.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= longest]:
                    del self._hits[k]
            return True


@lru_cache
def get_public_limiter() -> RateLimiter:
    settings = get_settings()
    return RateLimiter(settings.public_questions_per_minute, settings.public_questions_per_hour)
