from app.services import principal_decision_data as pd


def test_only_pending_nodes_are_opened():
    assert pd.should_apply("pending_review")
    for s in ("active", "restricted", "suspended", "check_failed"):
        assert not pd.should_apply(s)


def test_only_hawaii_us_is_listed_with_verbatim_text():
    assert [(d["country_code"], d["region_code"]) for d in pd.DECISIONS] == [("US", "HI")]
    assert pd.DECISIONS[0]["text"] == "I clear Hawaii/US."
    assert pd.PRINCIPAL == "Donovan Vanaman"
