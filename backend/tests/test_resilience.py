import pytest

from app.services.resilience import CircuitBreaker, CircuitOpenError, retry_with_backoff


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_retry_succeeds_after_transient_failures_with_growing_waits():
    waits, calls = [], {"n": 0}

    @retry_with_backoff(attempts=3, base_delay=1.0, retry_on=(ConnectionError,), sleep=waits.append, jitter=False)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("temporary")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    assert waits == [1.0, 2.0]


def test_retry_raises_the_original_error_after_last_attempt():
    @retry_with_backoff(attempts=2, retry_on=(ConnectionError,), sleep=lambda s: None, jitter=False)
    def always_down():
        raise ConnectionError("still down")

    with pytest.raises(ConnectionError, match="still down"):
        always_down()


def test_retry_does_not_catch_other_errors():
    calls = {"n": 0}

    @retry_with_backoff(attempts=3, retry_on=(ConnectionError,), sleep=lambda s: None)
    def bad_request():
        calls["n"] += 1
        raise ValueError("bad key")

    with pytest.raises(ValueError):
        bad_request()
    assert calls["n"] == 1


def _fail():
    raise ConnectionError("down")


def test_breaker_opens_after_threshold_and_refuses_calls():
    clock = FakeClock()
    b = CircuitBreaker("t", failure_threshold=3, recovery_seconds=60, clock=clock)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            b.call(_fail)
    assert b.state == "open"
    with pytest.raises(CircuitOpenError):
        b.call(lambda: "never runs")


def test_breaker_recovers_through_half_open_trial():
    clock = FakeClock()
    b = CircuitBreaker("t", failure_threshold=2, recovery_seconds=60, clock=clock)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            b.call(_fail)
    assert b.state == "open"
    clock.now += 61
    assert b.state == "half_open"
    assert b.call(lambda: "healed") == "healed"
    assert b.state == "closed"
    assert b.snapshot()["consecutive_failures"] == 0


def test_failed_trial_reopens_circuit():
    clock = FakeClock()
    b = CircuitBreaker("t", failure_threshold=1, recovery_seconds=60, clock=clock)
    with pytest.raises(ConnectionError):
        b.call(_fail)
    clock.now += 61
    with pytest.raises(ConnectionError):
        b.call(_fail)
    assert b.state == "open"
    clock.now += 30
    assert b.state == "open"


def test_errors_outside_trip_on_do_not_count():
    b = CircuitBreaker("t", failure_threshold=1)

    def config_error():
        raise RuntimeError("API key missing")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            b.call(config_error, trip_on=(ConnectionError,))
    assert b.state == "closed"
