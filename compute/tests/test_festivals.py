from conftest import call

from astro_compute import festivals as F
from astro_compute.meta import FESTIVAL_RULES

DELHI = {"year": "2026", "lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}


def _rows(kind):
    status, out = call("GET", f"/v1/festivals/{kind}", DELHI)
    assert status == 200, out
    return out["occurrences"]


def test_single_festivals_2026_at_delhi():
    # Checked against Drik Panchang's New Delhi dates for 2026.
    (d,) = _rows("dipavali")
    assert (d["date"], d["rule"]) == ("2026-11-08", "pradosha") and d["lakshmiPuja"]
    (m,) = _rows("mahashivaratri")
    assert m["date"] == "2026-02-15" and m["rule"] in FESTIVAL_RULES["shivaratri"]
    (g,) = _rows("ganesha-chaturthi")
    assert (g["date"], g["rule"]) == ("2026-09-14", "trtiya_joined_earlier")
    assert g["pujaWindow"]["start"] < g["pujaWindow"]["end"]


def test_masik_shivaratri_2026_at_delhi():
    rows = _rows("masik-shivaratri")
    assert [r["date"] for r in rows] == [
        "2026-01-16", "2026-02-15", "2026-03-17", "2026-04-15", "2026-05-15", "2026-06-13",
        "2026-07-12", "2026-08-11", "2026-09-09", "2026-10-08", "2026-11-07", "2026-12-07",
    ]  # fmt: skip
    # 16 Jan: all of midnight on the 16th, a sliver on the 17th with its pradosha.
    assert rows[0]["rule"] == "by_midnight"


def test_new_festivals_2026_at_delhi_match_drik():
    (j,) = _rows("janmashtami")
    # Ashtami 4 Sep 02:25 to 00:14: only the 4th's midnight; Rohini ends at 23:04.
    assert (j["date"], j["rule"], j["jayanti"], j["udayaDate"]) == (
        "2026-09-04",
        "second_only",
        None,
        "2026-09-04",
    )
    (n,) = _rows("sharad-navaratri")
    assert (n["date"], n["rule"], n["twoMuhurtas"]) == ("2026-10-11", "pratipada_at_sunrise", True)
    (v,) = _rows("vijayadashami")
    # The Dashami touches both afternoons; Shravana ends on the 20th.
    assert (v["date"], v["rule"]) == ("2026-10-20", "aparahna_both_earlier")
    assert not v["shravanaInLaterAparahna"]


def test_raksha_and_holika_windows_avoid_bhadra():
    for kind in ("raksha-bandhan", "holika-dahana"):
        (r,) = _rows(kind)
        assert r["rule"] in FESTIVAL_RULES[kind]
        window = r["tieWindow" if kind == "raksha-bandhan" else "dahanWindow"]
        assert window["start"] >= r["bhadra"]["end"] and window["start"] < window["end"]
        if r["rule"] != "shrinking_later":  # that one is lit in Pratipada
            assert r["tithi"]["start"] <= window["start"] and window["end"] <= r["tithi"]["end"]


def test_janmashtami_tables():
    assert F._by_midnight([0.4, 0]) == (0, "first_only")
    assert F._by_midnight([0, 0.4]) == (1, "second_only")
    assert F._by_midnight([1, 1]) == (1, "both_later")
    assert F._by_midnight([0, 0]) == (1, "neither_later")
    assert F._by_midnight([1, 0.3]) == (0, "more")
    assert F._jayanti([True, False], [1, 0], [True, False], True) == (0, "first", None)
    assert F._jayanti([True, True], [1, 1], [True, True], True) == (1, "both_later", None)
    # Ashtami at the first midnight, Rohini at the second: Madhava's later day.
    assert F._jayanti([False, False], [1, 0], [False, True], True) == (1, "split_later", 0)
    assert F._jayanti([False, False], [1, 0], [False, False], False) is None
