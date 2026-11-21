"""
Self-healing building blocks: retry with backoff and a circuit breaker.

These protect the platform's OUTBOUND calls (for example Reply.io) so a
temporary outage heals by itself instead of cascading:

  - retry_with_backoff: retries transient failures a few times, waiting
    longer each time, then raises the original error. Nothing is hidden.
  - CircuitBreaker: after repeated failures it stops calling the failing
    service for a cool-down period, then lets one trial call through. If the
    trial succeeds the circuit closes again on its own.

What this deliberately does NOT do: it never retries or fakes anything on the
bank-credit path (that is inbound, and a replayed notification is already
safe), and it never reports success for a call that failed. Breaker states
are visible in the SI briefing so the architect can see what is degraded.

Standard library only, so it can be tested without any other dependency.
"""
import functools
import random
import threading
import time
from typing import Callable, Dict, Tuple, Type


class CircuitOpenError(RuntimeError):
    """The circuit is open: the call was refused without contacting the service."""


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = None  # type: ignore[assignment]
        self._trial_in_flight = False
        self._total_failures = 0
        self._total_successes = 0
        self._last_error = None  # type: ignore[assignment]

    @property
    def state(self) -> str:
        with self._lock:
            return self._state_unlocked()

    def _state_unlocked(self) -> str:
        if self._opened_at is None:
            return self.CLOSED
        if self._clock() - self._opened_at >= self.recovery_seconds:
            return self.HALF_OPEN
        return self.OPEN

    def call(
        self,
        fn: Callable,
        *args,
        trip_on: Tuple[Type[BaseException], ...] = (Exception,),
        **kwargs,
    ):
        """Run fn through the breaker. Only exceptions in `trip_on` count as
        service failures; other errors (for example a missing API key) pass
        through without affecting the circuit."""
        with self._lock:
            state = self._state_unlocked()
            if state == self.OPEN:
                raise CircuitOpenError(f"Circuit '{self.name}' is open; call refused.")
            if state == self.HALF_OPEN:
                if self._trial_in_flight:
                    raise CircuitOpenError(f"Circuit '{self.name}' is testing recovery; call refused.")
                self._trial_in_flight = True

        try:
            result = fn(*args, **kwargs)
        except trip_on as exc:
            self._record_failure(exc)
            raise
        except BaseException:
            with self._lock:
                self._trial_in_flight = False
            raise
        else:
            self._record_success()
            return result

    def _record_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._total_failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._trial_in_flight = False
            if self._opened_at is not None:
                # A failed trial reopens the circuit for a fresh cool-down.
                self._opened_at = self._clock()
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = self._clock()

    def _record_success(self) -> None:
        with self._lock:
            self._total_successes += 1
            self._failures = 0
            self._opened_at = None
            self._trial_in_flight = False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state_unlocked(),
                "consecutive_failures": self._failures,
                "total_failures": self._total_failures,
                "total_successes": self._total_successes,
                "last_error": self._last_error,
            }


_registry: Dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    with _registry_lock:
        if name not in _registry:
            _registry[name] = CircuitBreaker(name, **kwargs)
        return _registry[name]


def all_snapshots() -> list:
    with _registry_lock:
        breakers = list(_registry.values())
    return [b.snapshot() for b in breakers]


def retry_with_backoff(
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    jitter: bool = True,
):
    """Retry a function on transient errors with exponential backoff. After
    the last attempt the ORIGINAL exception is raised - failures are never
    swallowed or turned into fake success."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except retry_on:
                    if attempt == attempts:
                        raise
                    wait = min(delay, max_delay)
                    if jitter:
                        wait = wait * (0.5 + random.random() / 2)
                    sleep(wait)
                    delay *= 2
        return wrapper

    return decorator
