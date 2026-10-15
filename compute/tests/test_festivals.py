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
    assert (n["date"], n["rule"]) == ("2026-10-11", "pratipada_at_sunrise")
    # Ten ghatikas from sunrise; Drik flags Chitra and Vaidhriti that morning too.
    assert n["sthapanaWindow"]["start"][11:16] == "06:20" and n["cautions"] == [
        "chitra",
        "vaidhriti",
    ]
    (v,) = _rows("vijayadashami")
    # The Dashami touches both afternoons; Shravana ends on the 20th.
    assert (v["date"], v["rule"]) == ("2026-10-20", "aparahna_both_earlier")
    assert not v["shravanaInLaterAparahna"]
    # The Dashami covers all of the 20th's afternoon, the 4th fifth of the day.
    afternoon = v["days"][0]["aparahna"]
    assert v["pujaWindow"] == {"start": afternoon["start"], "end": afternoon["end"]}


def test_raksha_and_holika_follow_dharmasindhu_with_ns_as_variant():
    (r,) = _rows("raksha-bandhan")
    # The Purnima runs 3h51m past the 28th's sunrise (over three muhurtas): DS keeps
    # the 28th, its afternoon; NS keeps the 27th, after Bhadra at night.
    assert (r["date"], r["rule"], r["variantDate"]) == (
        "2026-08-28",
        "udaya_three_muhurtas",
        "2026-08-27",
    )
    assert r["tieWindow"]["start"] >= r["bhadra"]["end"]
    (h,) = _rows("holika-dahana")
    # Bhadra fills the 2nd's pradosha; the Purnima lasts 3 1/2 yamas into the 3rd
    # and the Pratipada grows: the 3rd's pradosha (DS p. 94), NS's 2nd as variant.
    assert (h["date"], h["rule"], h["variantDate"]) == (
        "2026-03-03",
        "sardha_triyama_later",
        "2026-03-02",
    )
    assert h["dahanWindow"]["start"][11:16] == "18:21"
    assert r["rule"] in FESTIVAL_RULES["raksha-bandhan"]
    assert h["rule"] in FESTIVAL_RULES["holika-dahana"]


def test_split_years_and_bhadra_face():
    def one(kind, year):
        status, out = call("GET", f"/v1/festivals/{kind}", {**DELHI, "year": year})
        assert status == 200, out
        (row,) = out["occurrences"]
        return row

    # 2027: the Ashtami holds the 24th's midnight and meets Rohini on the 25th.
    j = one("janmashtami", "2027")
    assert (j["date"], j["rule"], j["variantDate"]) == (
        "2027-08-25",
        "split_rohini_day",
        "2027-08-24",
    )
    # 2027: a Pratipada touching no sunrise is kept on its Amavasya-joined day (DS p. 65).
    n = one("sharad-navaratri", "2027")
    assert (n["date"], n["rule"]) == ("2027-09-30", "no_sunrise_amavasya_joined")
    # 2027: Bhadra ends after midnight, so the fire is at pradosha in Bhadra, clear of its face.
    h = one("holika-dahana", "2027")
    assert h["rule"] == "bhadra_avoiding_face"
    assert (
        h["dahanWindow"]["end"] <= h["bhadraFace"]["start"]
        or h["dahanWindow"]["start"] >= h["bhadraFace"]["end"]
    )


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


def test_dipavali_set_of_five_days():
    # Drik Panchang's New Delhi dates for 2026 (festivals.md v4 s9-12).
    (d,) = _rows("dipavali")
    five = d["set"]
    assert [five[k]["date"] for k in five] == [
        "2026-11-06", "2026-11-08", "2026-11-08", "2026-11-10", "2026-11-11",
    ]  # fmt: skip
    for k, v in five.items():
        if k != "lakshmiPuja":
            assert v["rule"] in FESTIVAL_RULES["dipavali"], (k, v["rule"])
    n = five["narakaChaturdashi"]
    # The bath runs from the moonrise inside the Caturdashi to sunrise.
    assert n["moonrise"] == n["abhyangaSnana"]["start"] < n["abhyangaSnana"]["end"]
    assert n["tithi"]["start"] < n["moonrise"] < n["tithi"]["end"]
    assert n["arunodaya"]["end"] == n["abhyangaSnana"]["end"]
    g = five["govardhan"]
    # The Pratipada lasts past nine muhurtas but not into the sayahna: NS takes the day before.
    assert (g["rule"], g["variantDate"], g["bathDate"]) == (
        "govardhan_nine_muhurtas",
        "2026-11-09",
        None,
    )
    assert (
        g["govardhanPuja"]["start"][:10] == g["date"] and g["baliPuja"]["start"][:10] == g["date"]
    )
    b = five["bhaiDooj"]
    assert b["yamaPuja"]["start"][:10] == b["date"] and b["rule"] == "bhai_dooj_later"
    assert five["dhanteras"]["yamaDipa"]["start"][:10] == five["dhanteras"]["date"]


def test_navaratri_days_ashtami_navami_and_rama_navami():
    # Drik Panchang's New Delhi dates for 2026 (festivals.md v5 s13-15).
    (n,) = _rows("sharad-navaratri")
    days = n["navaratriDays"]
    assert len(days) == 10 and days[6]["tithis"] == days[7]["tithis"] == ["saptami"]
    assert n["ashtami"]["date"] == n["navami"]["date"] == "2026-10-19"
    assert n["ashtami"]["rule"] in FESTIVAL_RULES["durgashtami"]
    assert n["navami"]["rule"] in FESTIVAL_RULES["mahanavami"]
    # Sandhi-puja straddles the Ashtami's end by a ghatika each way.
    assert n["sandhiPuja"]["start"] < n["ashtami"]["tithi"]["end"] < n["sandhiPuja"]["end"]
    (c,) = _rows("chaitra-navaratri")
    assert (c["date"], c["rule"], c["newYearDate"]) == (
        "2026-03-19", "no_sunrise_amavasya_joined", "2026-03-19",
    )  # fmt: skip
    assert c["navaratriDays"][0]["tithis"] == ["pratipada"] and "sandhiPuja" not in c
    (r,) = _rows("ramanavami")
    assert (r["date"], r["rule"], r["smartaDate"]) == ("2026-03-26", "midday_earlier_only", None)
    (h,) = _rows("holika-dahana")
    v = h["vasantotsava"]
    assert (v["date"], v["popularName"]) == ("2026-03-04", "Rangwali Holi")
    assert v["rule"] in FESTIVAL_RULES["vasantotsava"]
