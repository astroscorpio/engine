import datetime as dt

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
    assert b["cover"] == "both"  # the Dvitiya starts mid-afternoon on the 10th
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
    assert v["date"] == "2026-03-04" and "popularName" not in v
    assert v["rule"] in FESTIVAL_RULES["vasantotsava"]
    # The colour day is the morning after the fire, every year.
    assert (h["date"], h["colours"]["date"]) == ("2026-03-03", "2026-03-04")
    assert h["colours"]["popularName"] == "Rangwali Holi"


def test_karva_chauth_follows_the_sankashti_rule():
    # 2026 at New Delhi: Thu 29 Oct, the Caturthi current at moonrise (festivals.md s16).
    (k,) = _rows("karva-chauth")
    assert (k["date"], k["vara"], k["rule"]) == ("2026-10-29", "thursday", "moonrise")
    assert k["sunset"] < k["moonrise"] and k["moonrise"][:10] == k["date"]
    assert k["tithi"]["start"] < k["moonrise"] < k["tithi"]["end"]
    assert k["rule"] in FESTIVAL_RULES["karva-chauth"] and "angaraki" not in k


def test_tulsi_vivah_and_tripurotsava():
    # 2026 at New Delhi (festivals.md s17).
    (t,) = _rows("tulsi-vivah")
    assert (t["fastDate"], t["date"], t["rule"]) == (
        "2026-11-20",
        "2026-11-21",
        "parana_day_early_night",
    )
    assert t["window"]["start"][:10] == t["date"] and t["variantDate"] == "2026-11-22"
    (p,) = _rows("tripurotsava")
    assert (p["date"], p["rule"], p["popularName"]) == (
        "2026-11-24",
        "tripura_pradosha",
        "Dev Deepawali",
    )
    assert p["window"]["start"][:10] == p["date"] and p["window"]["end"] <= p["tithi"]["end"]


def test_magha_festivals_2026():
    # Drik Panchang's New Delhi dates for 2026 (festivals.md s18-20).
    (v,) = _rows("vasanta-panchami")
    assert (v["date"], v["rule"], v["popularName"]) == (
        "2026-01-23", "forenoon_later_alone", "Basant Panchami",
    )  # fmt: skip
    assert v["pujaWindow"]["start"][:10] == v["date"] and v["forenoon"][1]["covered"] > 0
    (r,) = _rows("ratha-saptami")
    assert (r["date"], r["rule"]) == ("2026-01-25", "arunodaya")
    dawn = r["arunodaya"]
    assert dawn["end"][:10] == r["date"] and dawn["start"] < dawn["end"]
    (b,) = _rows("bhishma-ashtami")
    assert (b["date"], b["rule"]) == ("2026-01-26", "one_day")
    assert b["tarpanaWindow"]["start"][:10] == b["date"]
    rows = ((v, "vasanta-panchami"), (r, "ratha-saptami"), (b, "bhishma-ashtami"))
    assert all(k["rule"] in FESTIVAL_RULES[n] for k, n in rows)


def test_decision_21_kinds_2026():
    (k,) = _rows("kalashtami")
    assert k["rule"] in FESTIVAL_RULES["kalashtami"] and k["popularName"] == "Kaal Bhairav Jayanti"
    assert k["lunarMonth"]["amanta"] == "kartika" and k["pujaWindow"]["start"][:10] == k["date"]
    (d,) = _rows("dattatreya-jayanti")
    assert d["rule"] in FESTIVAL_RULES["dattatreya-jayanti"]
    assert d["lunarMonth"]["amanta"] == "margashirsha"
    (g,) = _rows("ganesha-jayanti")
    assert g["rule"] in FESTIVAL_RULES["ganesha-jayanti"] and g["lunarMonth"]["amanta"] == "magha"
    (h,) = _rows("holashtak")
    assert h["date"] < h["endDate"] and h["period"]["start"] < h["period"]["end"]
    assert h["rule"] == "holashtak_period" and "pushkar" in h["regions"]


def test_occurrences_carry_their_neighbouring_tithis():
    for kind in ("dipavali", "holashtak"):
        for o in _rows(kind):
            before, after = o["tithiBefore"], o["tithiAfter"]
            assert before["end"] <= after["start"] and before["start"] < before["end"]
            assert after["start"] < after["end"]
    (d,) = _rows("dipavali")
    assert (d["tithiBefore"]["id"], d["tithiAfter"]["id"]) == ("chaturdashi", "pratipada")
    assert (
        d["tithiBefore"]["end"] == d["tithi"]["start"]
        and d["tithiAfter"]["start"] == d["tithi"]["end"]
    )


def test_akshaya_tritiya_parashurama_and_guru_purnima_2026():
    (a,) = _rows("akshaya-tritiya")
    assert (
        a["rule"] in FESTIVAL_RULES["akshaya-tritiya"] and a["lunarMonth"]["amanta"] == "vaishakha"
    )
    assert a["pujaWindow"]["start"][:10] == a["date"]
    (p,) = _rows("parashurama-jayanti")
    assert p["rule"] in FESTIVAL_RULES["parashurama-jayanti"]
    assert (
        p["firstWatch"]["start"] < p["firstWatch"]["end"]
        and p["arghyaWindow"]["start"][:10] == p["date"]
    )
    (g,) = _rows("guru-purnima")
    assert g["rule"] in FESTIVAL_RULES["guru-purnima"] and g["lunarMonth"]["amanta"] == "ashadha"
    assert (g["popularName"], g["displayName"]) == ("Guru Purnima", "Vyāsa-pūjā")
    assert len(a["days"]) == 2 and all(0 <= d["forenoon"]["covered"] <= 1 for d in a["days"])
    chosen = next(d for d in g["days"] if d["date"] == g["date"])
    if g["rule"] == "three_muhurtas_later":
        assert chosen["morning"]["covered"] == 1


def test_bengal_durga_puja_follows_the_sunrise_tithi():
    status, out = call(
        "GET",
        "/v1/festivals/durga-puja",
        {"year": "2026", "lat": "22.5726", "lon": "88.3639", "tz": "Asia/Kolkata"},
    )
    assert status == 200, out
    (d,) = out["occurrences"]
    days = [d[k]["date"] for k in ("patrikaPravesha", "mahashtami", "mahanavami", "visarjana")]
    assert days == sorted(days) and len(set(days)) == 4
    assert d["bodhana"]["date"] <= d["amantrana"]["date"] < d["patrikaPravesha"]["date"]
    assert d["sandhiPuja"]["start"] < d["sandhiPuja"]["end"]
    fore = d["visarjana"]["forenoon"]
    for w in d["visarjana"]["movableWindows"]:
        assert fore["start"] <= w["start"] < w["end"] <= fore["end"]
    # TT keeps Mahanavami on the sunrise Navami; NS and DS take the Ashtami day here.
    assert d["mahanavami"]["nsDsDate"] == d["mahashtami"]["date"]
    assert out["source"]["page"] == "63-82"


def test_february_strips_carry_both_candidate_days():
    (r,) = _rows("ratha-saptami")
    assert len(r["days"]) == 2 and r["days"][0]["date"] < r["days"][1]["date"]
    assert any(d["arunodaya"]["covered"] > 0 and d["date"] == r["date"] for d in r["days"])
    (g,) = _rows("ganesha-jayanti")
    assert g["vow"]["rule"] in FESTIVAL_RULES["ganesha-jayanti"]
    assert all("pradosha" in d and "madhyahna" in d for d in g["days"])
    assert g["vow"]["window"]["start"][:10] == g["vow"]["date"]


def test_decision_26_kinds_2026():
    vat = _rows("vat-savitri")
    # 2026 has an adhika Jyeshtha: the Amavasya form falls before it, the Purnima form in the
    # pure month, as no vow is begun or completed in a malamasa (DS p. 4).
    assert [(o["form"], o["date"]) for o in vat] == [
        ("amavasya", "2026-05-16"),
        ("purnima", "2026-06-29"),
    ]
    for o in vat:
        assert o["rule"] in FESTIVAL_RULES["vat-savitri"] and not o["lunarMonth"]["adhika"]
        assert len(o["nights"]) == 3 and o["nights"][-1] == o["date"]
        assert o["paranaAfter"] == o["tithi"]["end"]
    # Ganga-dashahara keeps the adhika month (NS p. 144; DS p. 38).
    (g,) = _rows("ganga-dussehra")
    assert g["date"] == "2026-05-25" and g["lunarMonth"]["adhika"]
    assert {"jyeshtha", "shukla", "dashami"} <= set(g["yogas"]) and g["rule"] in FESTIVAL_RULES[
        "ganga-dussehra"
    ]
    assert g["pujaWindow"]["start"][:10] == g["date"] and len(g["days"]) == 2
    (r,) = _rows("rath-yatra")
    assert (r["date"], r["rule"]) == ("2026-07-16", "sunrise_tritiya_joined") and r["pushya"]
    teej = {k: _rows(k)[0] for k in ("hariyali-teej", "kajari-teej", "hartalika-teej")}
    assert [t["date"] for t in teej.values()] == ["2026-08-15", "2026-08-31", "2026-09-14"]
    assert teej["kajari-teej"]["lunarMonth"]["purnimanta"] == "bhadrapada"
    assert (teej["hariyali-teej"]["popularName"], teej["hariyali-teej"]["displayName"]) == (
        "Hariyali Teej",
        "Madhuśrāvaṇikā",
    )
    for k, t in teej.items():
        assert t["rule"] in FESTIVAL_RULES[k]
    (n,) = _rows("nag-panchami")
    assert n["date"] == "2026-08-17" and n["rule"] in FESTIVAL_RULES["nag-panchami"]
    assert n["muhurtas"]["panchami"] >= 3
    (p,) = _rows("rishi-panchami")
    assert p["date"] == "2026-09-15" and p["pujaWindow"]["start"][:10] == p["date"]
    (a,) = _rows("anant-chaturdashi")
    assert a["date"] == "2026-09-25" and a["rule"] in FESTIVAL_RULES["anant-chaturdashi"]
    assert a["pujaWindow"]["start"][:10] == a["date"]


def test_sawan_somvar_lists_both_month_systems():
    status, out = call("GET", "/v1/festivals/sawan-somvar", DELHI)
    assert status == 200, out
    assert out["shravana"]["purnimanta"] == {"start": "2026-07-30", "end": "2026-08-28"}
    rows = out["occurrences"]
    assert all(r["vara"] == "monday" and r["rule"] == "shravana_monday" for r in rows)
    # Every Monday of purnimanta Shravana, a week apart, none missing at either end.
    pur = [dt.date.fromisoformat(r["date"]) for r in rows if "purnimanta" in r["systems"]]
    first, last = (
        dt.date.fromisoformat(out["shravana"]["purnimanta"][k]) for k in ("start", "end")
    )
    assert len(pur) == 4 and all(
        b - a == dt.timedelta(7) for a, b in zip(pur, pur[1:], strict=False)
    )
    assert pur[0] - first < dt.timedelta(7) and last - pur[-1] < dt.timedelta(7)
    # The two months share only the bright fortnight.
    both = [r for r in rows if len(r["systems"]) == 2]
    assert both and all(r["paksha"] == "shukla" for r in both)
    assert out["source"]["text"] == "Dharmasindhu" and out["alsoSource"] is None


def test_kalashtami_vigil_and_the_new_year_reasoning():
    (k,) = _rows("kalashtami")
    v = k["vigil"]
    assert v["rule"] in FESTIVAL_RULES["kalashtami"] and v["window"]["start"] < v["window"]["end"]
    status, out = call("GET", "/v1/festivals/kalashtami", {**DELHI, "year": "2027"})
    (k27,) = out["occurrences"]
    # 2027: the Ashtami holds only the first night, so the vigil is the eve of the fast.
    assert (k27["vigil"]["date"], k27["vigil"]["rule"]) == ("2027-11-20", "vigil_one_night")
    assert k27["date"] == "2027-11-21"
    (c,) = _rows("chaitra-navaratri")
    ny = c["newYear"]
    assert ny["date"] == c["newYearDate"] and ny["rule"] in FESTIVAL_RULES["chaitra-navaratri"]
    assert len(ny["days"]) == 2
    assert any(d["covered"] for d in ny["days"]) == (ny["rule"] != "neither_earlier")


def test_popular_practice_kinds_carry_their_basis_and_follow_our_rules():
    import datetime as dt

    from astro_compute.meta import FESTIVAL_NOTES

    def days_apart(a, b):
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days

    kinds = ("chhath", "hanuman-jayanti", "radhashtami", "onam", "vishwakarma-puja")
    outs = {}
    for k in kinds:
        status, out = call("GET", f"/v1/festivals/{k}", DELHI)
        assert status == 200, out
        assert out["basis"] == "popular_practice" and out["source"] is None
        assert out["occurrences"] and "Popular practice" in FESTIVAL_NOTES[k]
        assert all(o["rule"] in FESTIVAL_RULES[k] for o in out["occurrences"])
        outs[k] = out
    (c,) = outs["chhath"]["occurrences"]
    s = c["set"]
    order = [s[k]["date"] for k in ("nahayKhay", "kharna", "sandhyaArghya", "ushaArghya")]
    assert [days_apart(a, b) for a, b in zip(order, order[1:], strict=False)] == [1, 1, 1]
    assert s["sandhyaArghya"]["sunset"][:10] == c["date"] and c["lunarMonth"]["amanta"] == "kartika"
    assert outs["chhath"]["context"] and any(
        "Krtyaratnakara" in x["text"] for x in outs["chhath"]["context"]
    )
    # Hanuman Jayanti is the Caitra Purnima's vrata day.
    status, purnima = call("GET", "/v1/observances/purnima", DELHI)
    (h,) = outs["hanuman-jayanti"]["occurrences"]
    caitra = [r for r in purnima["occurrences"] if r["lunarMonth"]["amanta"] == "chaitra"]
    assert h["date"] == caitra[0]["vrata"]["date"]
    (r,) = outs["radhashtami"]["occurrences"]
    assert r["pujaWindow"]["start"][:10] == r["date"]
    onam = outs["onam"]
    span = onam["chingam"]
    assert all(span["start"] <= o["date"] <= span["end"] for o in onam["occurrences"])
    status, sk = call("GET", "/v1/observances/sankranti", DELHI)
    kanya = next(x for x in sk["sankrantis"] if x["sign"] == "virgo")
    (v,) = outs["vishwakarma-puja"]["occurrences"]
    assert v["date"] == kanya["date"]
    status, d = call("GET", "/v1/festivals/dipavali", DELHI)
    assert d["basis"] == "text"
