from conftest import DELHI, call

from astro_compute.meta import ECLIPSE_NOTES, ECLIPSE_RULES

LONDON = {"lat": "51.5074", "lon": "-0.1278", "tz": "Europe/London"}


def _eclipses(year, place=DELHI):
    status, out = call("GET", "/v1/eclipses", {**place, "year": str(year)})
    assert status == 200, out
    for e in out["eclipses"]:
        assert e["notReckoned"] is None or e["notReckoned"] in ECLIPSE_NOTES
        if e["vedha"]:
            assert e["vedha"]["rule"] in ECLIPSE_RULES and e["vedha"]["endRule"] in ECLIPSE_RULES
    return {e["id"]: e for e in out["eclipses"]}


def test_vedha_matches_research_delhi_examples():
    """grahana.md s8, worked at Delhi: whole praharas back from the first contact seen."""
    e = _eclipses(2027)["2027-08-02-solar"]
    v = e["vedha"]
    got = (
        e["local"]["type"],
        v["rule"],
        v["start"][:16],
        v["end"][11:16],
        v["popularStart"][11:16],
    )
    assert got == ("partial", "four_praharas_solar", "2027-08-02T03:05", "17:02", "03:53")
    y28 = _eclipses(2028)
    v = y28["2028-07-06-lunar"]["vedha"]
    got = (v["rule"], v["start"][11:16], v["end"][:16], v["popularStart"][11:16])
    assert got == ("three_praharas_lunar", "12:25", "2028-07-07T01:00", "13:38")
    e = y28["2028-12-31-lunar"]
    got = (
        e["vedha"]["start"][11:16],
        e["vedhaVariant"]["start"][11:16],
        e["vedha"]["popularStart"][11:16],
    )
    assert got == ("09:49", "07:14", "11:37")
    m = _eclipses(2026)["2026-03-03-lunar"]
    assert m["local"]["risesEclipsed"] and m["vedha"]["rule"] == "moon_rises_eclipsed_from_sunrise"


def test_only_what_is_seen_counts():
    """DS p. 26: below the horizon, nothing; a penumbral eclipse has no bite (our reading)."""
    y26 = _eclipses(2026, LONDON)
    march = y26["2026-03-03-lunar"]
    assert (march["notReckoned"], march["vedha"]) == ("not_visible", None)
    august = y26["2026-08-28-lunar"]
    assert august["local"]["setsEclipsed"] and august["vedha"]["endRule"] == "next_clear_moonrise"
    penumbral = [e for e in _eclipses(2027).values() if e["type"] == "penumbral"]
    assert len(penumbral) == 3
    assert all(e["notReckoned"] == "penumbral_no_bite" and e["vedha"] is None for e in penumbral)
    y28 = _eclipses(2028, LONDON)
    assert y28["2028-07-06-lunar"]["notReckoned"] == "umbral_not_visible"
    assert y28["2028-01-26-solar"]["vedha"]["endRule"] == "next_clear_sunrise"
    assert y28["2028-12-31-lunar"]["vedha"]["rule"] == "moon_rises_eclipsed_from_sunrise"


def test_eclipsed_body_at_maximum():
    """The lead and seo, 17 Oct 2026: the Moon's sign and star for a lunar eclipse, the Sun's
    for a solar one, at greatest eclipse."""
    from astro_compute.ids import SIGN_IDS

    rows = _eclipses(2028)
    lunar, solar = rows["2028-12-31-lunar"]["atMaximum"], rows["2028-07-22-solar"]["atMaximum"]
    assert (lunar["body"], solar["body"]) == ("moon", "sun")
    assert all(x["sign"] in SIGN_IDS and x["nakshatra"] for x in (lunar, solar))
