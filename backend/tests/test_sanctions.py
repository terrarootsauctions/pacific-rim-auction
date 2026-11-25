from datetime import datetime, timedelta

import pytest

from app.services import sanctions as s

NOW = datetime(2026, 11, 24, 12, 0)
SDN = "\n".join([
    '1,"SMITH, John Michael",individual,PROG,-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-',
    '2,"ROSNEFT",entity,PROG,-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-',
    '3,"ACME TRADING CO",entity,PROG,-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-',
    '4,-0-,individual,PROG,-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-',
])
ALT = '1,10,aka,"JOHNNY SMYTH",-0-\n3,11,aka,"ACME LTD",-0-\n'


def loaded():
    sc = s.Screener()
    sc.load_csv(SDN, ALT, NOW, min_entries=1)
    return sc


def test_tokens_order_and_accents():
    assert s.tokens("SMITH, John") == s.tokens("john smith") == s.tokens("Jöhn  Smith")


def test_not_loaded_blocks():
    assert s.Screener().screen(["Jane Doe"], NOW)["reason"] == "SDN_LIST_NOT_LOADED"


def test_tiny_list_refused():
    with pytest.raises(ValueError):
        s.Screener().load_csv(SDN, ALT, NOW)  # default sanity floor


def test_exact_possible_clear_and_alias():
    sc = loaded()
    assert sc.screen(["John Smith Michael"], NOW)["reason"] == "SDN_EXACT_MATCH"
    assert sc.screen(["Smith, John Michael"], NOW)["clear"] is False
    assert sc.screen(["John Smith"], NOW)["reason"] == "SDN_POSSIBLE_MATCH_REVIEW"
    assert sc.screen(["Johnny Smyth"], NOW)["reason"] == "SDN_EXACT_MATCH"       # alias
    assert sc.screen(["Rosneft"], NOW)["reason"] == "SDN_EXACT_MATCH"
    assert sc.screen(["Jane Doe"], NOW) == {"clear": True, "reason": "NO_MATCH", "matches": []}


def test_single_word_does_not_false_match_partially():
    sc = loaded()
    assert sc.screen(["Smith"], NOW)["clear"] is True          # one word never "possible"-matches
    assert sc.screen(["Acme"], NOW)["clear"] is True


def test_no_name_and_stale_block():
    sc = loaded()
    assert sc.screen([None, "  ", "ab"], NOW)["reason"] == "NO_NAME_TO_SCREEN"
    assert sc.screen(["Jane Doe"], NOW + timedelta(hours=73))["reason"] == "SDN_LIST_STALE"


def test_any_screened_name_hit_blocks():
    assert loaded().screen(["Jane Doe", "Rosneft"], NOW)["clear"] is False


def test_fetch_falls_back_to_next_address(monkeypatch):
    import requests
    big = "\n".join(f'{i},"PERSON{i} NAME{i}",individual,P,-0-' for i in range(1100))

    class R:
        def __init__(self, ok, text=""): self.ok, self.content = ok, text.encode()
        def raise_for_status(self):
            if not self.ok: raise requests.HTTPError("404")

    def fake_get(url, **kw):
        return R("treasury.gov/ofac/downloads" in url, big if "sdn" in url else '1,1,aka,"X Y",-0-')
    monkeypatch.setattr(requests, "get", fake_get)
    sc = s.Screener()
    assert sc.fetch("https://bad.example/sdn.csv", "https://bad.example/alt.csv", NOW) is True
    assert sc.status(NOW)["entries"] >= 1100


def test_fetch_failure_stays_blocked(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("down")))
    sc = s.Screener()
    assert sc.fetch("https://a/sdn.csv", "https://a/alt.csv", NOW) is False
    assert sc.screen(["Jane Doe"], NOW)["reason"] == "SDN_LIST_NOT_LOADED" and sc.last_error
