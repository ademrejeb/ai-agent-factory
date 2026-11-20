"""Small in-process fixed-window limiter for unauthenticated entry points.

It is intentionally per process: the control plane is a single-replica service
today. The gateway also keeps its per-credential limiter here. If the API is
scaled horizontally, move this to Redis/Postgres before relying on it for
abuse protection.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.errors import AppError

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)
_last_prune = 0.0
MAX_KEYS = 20_000


def _prune(now: float, window_seconds: int) -> None:
    global _last_prune
    if len(_hits) <= MAX_KEYS or now - _last_prune < 5:
        return
    _last_prune = now
    cutoff = now - max(window_seconds, 3600)
    for key in [key for key, hits in _hits.items() if not hits or hits[-1] <= cutoff]:
        _hits.pop(key, None)
    if len(_hits) > MAX_KEYS:
        for key in list(_hits)[: len(_hits) // 10]:
            _hits.pop(key, None)


def enforce_rate_limit(key: str, limit: int, *, window_seconds: int = 60) -> None:
    if limit <= 0:
        return
    now = time.time()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise AppError("rate_limited", "Rate limit exceeded. Try again shortly.", 429)
        hits.append(now)
        _prune(now, window_seconds)
