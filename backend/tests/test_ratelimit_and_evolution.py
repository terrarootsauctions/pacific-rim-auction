from app.services.evolution_rules import PROTECTED, should_auto_revert, validate_change
from app.services.ratelimit import SlidingWindowLimiter

GOOD = {"security_ok": True, "compliance_ok": True, "financial_integrity_ok": True,
        "measurements": {"p95_latency_ms": 41}}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_limiter_blocks_then_recovers():
    c = Clock()
    lim = SlidingWindowLimiter(3, 10, clock=c)
    assert [lim.allow("u") for _ in range(4)] == [True, True, True, False]
    assert lim.allow("other") is True
    c.t = 10.0
    assert lim.allow("u") is True


def test_valid_change_allowed():
    assert validate_change("anti_snipe_window_seconds", 45, GOOD) == (True, "OK")


def test_protected_parameters_never_change():
    for name in PROTECTED:
        ok, reason = validate_change(name, 1, GOOD)
        assert ok is False and reason.startswith("PROTECTED_PARAMETER")


def test_unknown_parameter_refused():
    assert validate_change("something_else", 1, GOOD)[1].startswith("UNKNOWN_PARAMETER")


def test_bounds_enforced():
    assert validate_change("anti_snipe_window_seconds", 9, GOOD)[1].startswith("OUT_OF_BOUNDS")
    assert validate_change("anti_snipe_window_seconds", 121, GOOD)[1].startswith("OUT_OF_BOUNDS")


def test_values_must_be_whole_numbers_not_bool_or_float():
    assert validate_change("anti_snipe_window_seconds", 30.5, GOOD)[1].startswith("INVALID_VALUE")
    assert validate_change("anti_snipe_window_seconds", True, GOOD)[1].startswith("INVALID_VALUE")


def test_uncertain_evidence_is_refused():
    bad = dict(GOOD, security_ok=False)
    assert validate_change("anti_snipe_window_seconds", 45, bad)[1].startswith("EVIDENCE_MISSING")
    assert validate_change("anti_snipe_window_seconds", 45, None)[1].startswith("EVIDENCE_MISSING")
    no_meas = {k: v for k, v in GOOD.items() if k != "measurements"}
    assert validate_change("anti_snipe_window_seconds", 45, no_meas)[1].startswith("EVIDENCE_MISSING")


def test_auto_revert_thresholds():
    limits = {"error_rate": 0.02, "p95_latency_ms": 500}
    assert should_auto_revert({"error_rate": 0.01, "p95_latency_ms": 100}, limits) is None
    assert should_auto_revert({"error_rate": 0.05, "p95_latency_ms": 100}, limits) == "error_rate"
    assert "not reported" in should_auto_revert({"error_rate": 0.01}, limits)
