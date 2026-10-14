from types import SimpleNamespace as NS

from conftest import EXAMPLE, call

from astro_compute import kuja as K


def fake(asc: int, **signs: int):
    """A chart reduced to what kuja.py reads: the lagna and some graha signs."""
    base = {"Moon": 0, "Venus": 0, "Mars": 0, "Saturn": 0}
    base.update(signs)
    return NS(asc=NS(sign=asc), grahas={g: NS(sign=s) for g, s in base.items()})


def test_the_sourced_houses_decide_the_verdict():
    for house in range(1, 13):
        status = K.status(fake(0, Mars=house - 1), time_known=True)
        assert status["marsHouse"]["lagna"] == house
        assert status["verdict"] == (house in (1, 4, 7, 8, 12))  # Khankhoje, SJG p. 223
        assert status["conventions"]["second_house"] == (house == 2)


def test_conventions_never_change_the_verdict():
    s = K.status(fake(0, Mars=1, Moon=0, Venus=0), time_known=True)  # Mars 2nd from all three
    assert s["verdict"] is False
    assert s["conventions"] == {"second_house": True, "from_moon": True, "from_venus": True}


def test_unknown_birth_time_gives_no_verdict():
    s = K.status(fake(0, Mars=0), time_known=False)
    assert s["verdict"] is None and s["marsHouse"]["lagna"] is None
    assert s["conventions"]["second_house"] is None and s["conventions"]["from_moon"] is True


def test_partner_rule_from_page_226():
    groom = fake(0, Mars=3)  # Mars 4th from the groom's lagna
    assert K.cancellation(groom, fake(0, Mars=11))["applies"] is True  # bride's Mars 12th
    assert K.cancellation(groom, fake(0, Mars=5, Saturn=0))["applies"] is True  # bride's Saturn 1st
    assert K.cancellation(groom, fake(0, Mars=5, Saturn=5))["applies"] is False
    assert K.cancellation(fake(0, Mars=6), fake(0)) is None  # groom's Mars in the 7th: rule silent
    assert K.cancellation(None, fake(0)) is None


def test_chart_page_uses_the_same_rule():
    status, out = call("POST", "/v1/chart", body={**EXAMPLE, "include": ["yogas"]})
    assert status == 200
    m = out["mangal"]
    # EXAMPLE: Mars in Libra, lagna Taurus (6th), Moon in Scorpio (12th from it).
    assert m["marsHouse"]["lagna"] == 6 and m["verdict"] is False
    assert m["conventions"]["from_moon"] is True
    assert all(y["id"] != "kuja_dosha" for y in out["yogas"])
    assert all(not y["id"].startswith("kuja_dosha_") for y in out["yogas"])
    status, unknown = call("POST", "/v1/chart", body={**EXAMPLE, "time": None, "timeUnknown": True})
    assert unknown["mangal"]["verdict"] is None
