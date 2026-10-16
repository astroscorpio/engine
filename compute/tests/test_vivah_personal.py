import datetime as dt

import swisseph as swe
from conftest import call
from jyotisha.ephemeris import positions

from astro_compute.ids import NAKSHATRA_IDS
from astro_compute.meta import VIVAH_LAGNA_RULES, VIVAH_LIFTS, VIVAH_PERSONAL_RULES

PLACE = {"lat": 28.6139, "lon": 77.2090, "tz": "Asia/Kolkata"}
YEAR = 2027
SPAN = {"from": dt.date(YEAR, 1, 1).isoformat(), "until": dt.date(YEAR, 12, 31).isoformat()}
STARS = {"bride": {"nakshatra": "rohini", "pada": 2}, "groom": {"nakshatra": "hasta", "pada": 1}}


def jd(iso):
    t = dt.datetime.fromisoformat(iso).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def search(span, **extra):
    return call("POST", "/v1/muhurat/vivah/personal", body={**span, **PLACE, **STARS, **extra})


def test_the_couple_marks_follow_the_rules():
    status, out = search(SPAN)
    assert status == 200, out
    assert out["days"] and all(SPAN["from"] <= d["date"] <= SPAN["until"] for d in out["days"])
    assert {r for x in out["removed"] for r in x["rules"]} <= set(VIVAH_PERSONAL_RULES)
    assert "eighth_lagna_from_lagna" in out["partners"]["bride"]["skipped"]
    stars = {s: NAKSHATRA_IDS.index(STARS[s]["nakshatra"]) for s in STARS}
    for d in out["days"]:
        assert d["personal"]["jupiterBride"] in ("best", "worship", "condemned")
        rows = [lg for w in d["windows"] for lg in w["lagnas"]]
        assert rows or d["godhuli"]
        for lg in rows:
            marks = lg["personal"]["faults"] + lg["personal"]["supports"]
            assert all(VIVAH_PERSONAL_RULES[m["rule"]][2] != "bar" for m in marks)
            for m in lg["personal"]["lifted"]:
                assert m["rule"] in ("tara_bad", "eighth_lagna") and m["by"] in VIVAH_LIFTS
                if m["rule"] == "eighth_lagna":  # Virgo's 8th is Aries; Taurus's is Sagittarius
                    assert lg["sign"] in ("aries", "sagittarius")
            assert lg["clean"] == (not lg["faults"] and not lg["personal"]["faults"])
            moon = positions((jd(lg["start"]) + jd(lg["end"])) / 2)["Moon"]
            star = int(moon.longitude // (360 / 27)) % 27
            for m in lg["personal"]["faults"]:
                if m["rule"] == "tara_bad":
                    tara = ((star - stars[m["side"]]) % 27 + 1) % 9 or 9
                    assert tara in (3, 5, 7)
        for w in d["windows"]:
            assert all(k in VIVAH_LAGNA_RULES or k in VIVAH_PERSONAL_RULES for k in w["lagnaBars"])
    for r in out["removed"]:
        if r["rules"] == ["no_lagna"]:
            assert "barred" in r and "godhuliBars" in r


def test_the_span_is_capped():
    status, out = search({**SPAN, "until": dt.date(YEAR + 1, 1, 2).isoformat()})
    assert status == 422 and out["error"]["code"] == "span_too_long"
    status, out = search({"from": SPAN["until"], "until": SPAN["from"]})
    assert status == 400


def test_a_first_born_partner_loses_the_birth_month():
    # A groom born on the first listed day's date thirty years earlier, so his birth
    # month is a listed month.
    status, base = search(SPAN)
    first = dt.date.fromisoformat(base["days"][0]["date"])
    groom = {
        "date": first.replace(year=first.year - 30).isoformat(),
        "time": "12:00",
        "place": {"name": "x", **PLACE},
    }
    status, out = call(
        "POST",
        "/v1/muhurat/vivah/personal",
        body={**SPAN, **PLACE, "bride": STARS["bride"], "groom": groom, "groomEldest": True},
    )
    assert status == 200, out
    g = out["partners"]["groom"]
    assert g["eldest"] and g["birthMonth"] and g["lagna"]
    assert all(d["lunarMonth"]["amanta"] != g["birthMonth"] for d in out["days"])
    for d in out["days"]:
        for w in d["windows"]:
            assert w["tithi"] != g["birthTithi"] or not w["lagnas"]
