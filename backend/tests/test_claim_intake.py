import pytest

from app.services import claim_intake as ci
from app.services import signing_chain as sc

DOC = sc.sha256_hex(b"authorization agreement v1")


def signed_chain():
    chain = []
    for event_type, actor in (
        (sc.EVENT_DOCUMENT_CREATED, "system"),
        (sc.EVENT_CONSENT_GIVEN, "owner@example.com"),
        (sc.EVENT_SIGNED, "owner@example.com"),
    ):
        chain.append(sc.new_event(chain, event_type, actor, "2026-11-22T00:00:00Z", DOC))
    return chain


def good(**overrides):
    args = dict(
        claimant_name="Pat Example",
        contact_email="Pat@Example.com",
        country="us",
        relationship="heir",
        description="Dormant bank account of my late uncle.",
        region="hi",
    )
    args.update(overrides)
    return args


def test_valid_intake_is_cleaned():
    out = ci.validate_intake(**good())
    assert out["contact_email"] == "pat@example.com"
    assert out["country"] == "US"
    assert out["region"] == "HI"
    assert out["relationship"] == ci.Relationship.HEIR


@pytest.mark.parametrize(
    "bad",
    [
        {"claimant_name": ""},
        {"claimant_name": "x" * 201},
        {"contact_email": "not-an-email"},
        {"country": "USA"},
        {"country": ""},
        {"relationship": "stranger"},
        {"description": "y" * 4001},
    ],
)
def test_invalid_intake_is_refused(bad):
    with pytest.raises(ValueError):
        ci.validate_intake(**good(**bad))


@pytest.mark.parametrize(
    "text",
    [
        "My SSN is 123-45-6789",
        "card 4111 1111 1111 1111",
        "account 123456789012",
    ],
)
def test_sensitive_numbers_are_refused(text):
    with pytest.raises(ValueError):
        ci.validate_intake(**good(description=text))


def test_ordinary_numbers_are_allowed():
    out = ci.validate_intake(**good(description="Left in 1998, about 2,500 dollars, claim 1234."))
    assert out["description"].startswith("Left in 1998")


def test_fee_needs_a_recorded_cap():
    with pytest.raises(ValueError):
        ci.validate_fee(1000, None)


def test_fee_over_cap_is_refused_and_within_cap_is_kept():
    with pytest.raises(ValueError):
        ci.validate_fee(1001, 1000)
    assert ci.validate_fee(1000, 1000) == 1000
    assert ci.validate_fee(0, 1000) == 0


def test_fee_must_be_whole_non_negative_int():
    for bad in (-1, 10.5, "10", True):
        with pytest.raises(ValueError):
            ci.validate_fee(bad, 1000)


def test_normal_path_through_review():
    S = ci.IntakeStatus
    status, _ = ci.advance_status(S.SUBMITTED, S.IDENTITY_REVIEW, jurisdiction_cleared=False)
    assert status == S.IDENTITY_REVIEW
    status, _ = ci.advance_status(S.IDENTITY_REVIEW, S.AWAITING_SIGNATURE, jurisdiction_cleared=True)
    assert status == S.AWAITING_SIGNATURE


def test_uncleared_jurisdiction_blocks_the_agreement():
    S = ci.IntakeStatus
    with pytest.raises(ValueError):
        ci.advance_status(S.IDENTITY_REVIEW, S.AWAITING_SIGNATURE, jurisdiction_cleared=False)


def test_cannot_skip_steps():
    S = ci.IntakeStatus
    with pytest.raises(ValueError):
        ci.advance_status(S.SUBMITTED, S.AUTHORIZED, jurisdiction_cleared=True)
    with pytest.raises(ValueError):
        ci.advance_status(S.SUBMITTED, S.AWAITING_SIGNATURE, jurisdiction_cleared=True)


def test_authorized_needs_a_real_signature():
    S = ci.IntakeStatus
    with pytest.raises(ValueError):
        ci.advance_status(S.AWAITING_SIGNATURE, S.AUTHORIZED, True, [], DOC)
    with pytest.raises(ValueError):
        ci.advance_status(S.AWAITING_SIGNATURE, S.AUTHORIZED, True, signed_chain(), None)
    status, _ = ci.advance_status(S.AWAITING_SIGNATURE, S.AUTHORIZED, True, signed_chain(), DOC)
    assert status == S.AUTHORIZED


def test_tampered_chain_cannot_authorize():
    S = ci.IntakeStatus
    chain = signed_chain()
    chain[1] = {**chain[1], "actor": "someone.else@example.com"}
    with pytest.raises(ValueError):
        ci.advance_status(S.AWAITING_SIGNATURE, S.AUTHORIZED, True, chain, DOC)


def test_signature_for_another_document_cannot_authorize():
    S = ci.IntakeStatus
    with pytest.raises(ValueError):
        ci.advance_status(S.AWAITING_SIGNATURE, S.AUTHORIZED, True, signed_chain(), sc.sha256_hex(b"other"))


def test_final_states_stay_final():
    S = ci.IntakeStatus
    for final in (S.REJECTED, S.WITHDRAWN):
        for target in S:
            with pytest.raises(ValueError):
                ci.advance_status(final, target, True, signed_chain(), DOC)
