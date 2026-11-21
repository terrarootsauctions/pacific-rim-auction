"""Per-user sliding-window rate limiter (pure, standard library only).

In-process: with several server instances each keeps its own counts, so the
effective limit is per instance. Fine for one Render instance; use a shared
store (for example Redis) if the service is scaled out."""
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.max_events = max_events
        self.window = window_seconds
        self._clock = clock
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            q = self._events[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.max_events:
                return False
            q.append(now)
            if not q:
                del self._events[key]
            return True
