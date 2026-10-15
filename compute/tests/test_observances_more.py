from conftest import call

from astro_compute import observances as O
from astro_compute.meta import OBSERVANCE_RULES

DELHI = {"year": "2026", "lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}


def test_purnima_and_amavasya_fasts_take_the_later_day():
    for kind, tithi_id in (("purnima", "purnima"), ("amavasya", "amavasya")):
        status, out = call("GET", f"/v1/observances/{kind}", DELHI)
        assert status == 200, out
        rows = out["occurrences"]
        assert 12 <= len(rows) <= 14
        for r in rows:
            v = r["vrata"]
            assert v["rule"] in OBSERVANCE_RULES["vrata"]
            day = next(d for d in r["days"] if d["date"] == v["date"])
            if v["rule"] == "later_day":
                # the last day with the tithi at sunrise, joined to the next Pratipada
                assert day["tithiAtSunrise"] == tithi_id and v["earlierDate"] < v["date"]
        assert out["source"]["text"] == "Nirnaya-sindhu"


def test_shraddha_amavasya_follows_aparahna_then_kutapa():
    status, out = call("GET", "/v1/observances/amavasya", DELHI)
    for r in out["occurrences"]:
        sh = r["shraddha"]
        assert sh["rule"] in OBSERVANCE_RULES["shraddha"]
        assert sh["date"] in [a["date"] for a in sh["aparahna"]]
        assert r["differs"] == (sh["date"] != r["vrata"]["date"])
        touched = [a["date"] for a in sh["aparahna"] if a["covered"] > 0]
        if len(touched) == 1:
            assert sh["rule"] == "aparahna" and sh["date"] == touched[0]


def test_kutapa_choice():
    assert O._kutapa_choice([(0, 0.0), (1, 0.4)], False) == (1, "kutapa_one_day")
    assert O._kutapa_choice([(0, 0.7), (1, 0.4)], False) == (0, "kutapa_more")
    assert O._kutapa_choice([(0, 0.5), (1, 0.5)], True) == (0, "kutapa_tie_kshaya_earlier")
    assert O._kutapa_choice([(0, 0.5), (1, 0.5)], False) == (1, "kutapa_tie_later")
    assert O._kutapa_choice([(0, 1.0), (1, 1.0), (2, 0.2)], False)[1] == "kutapa_more"


def test_pradosha_vrata_on_the_trayodashi_covering_pradosha():
    status, out = call("GET", "/v1/observances/pradosha", DELHI)
    assert status == 200, out
    rows = out["occurrences"]
    assert 24 <= len(rows) <= 26
    for r in rows:
        assert r["rule"] in OBSERVANCE_RULES["pradosha"]
        chosen = next(d for d in r["days"] if d["date"] == r["date"])
        assert chosen["vara"] == r["vara"]
        if r["rule"] == "covers_pradosha":
            assert chosen["covered"] == 1 and r["variantDate"] is None
        elif r["rule"] == "more_pradosha":
            assert chosen["covered"] == max(d["covered"] for d in r["days"])
        else:
            assert r["variantDate"] == r["days"][0]["date"] and r["date"] == r["days"][1]["date"]


def test_pradosha_2026_at_delhi_matches_the_cited_rules():
    status, out = call("GET", "/v1/observances/pradosha", DELHI)
    rows = {r["tithi"]["start"][:10]: r for r in out["occurrences"]}
    # 12 Jun: Trayodashi 19:37 to 16:08 next day; 84% of the 12th's pradosha, none of the 13th's.
    assert (rows["2026-06-12"]["date"], rows["2026-06-12"]["rule"]) == (
        "2026-06-12",
        "more_pradosha",
    )
    # 28 Apr: the whole of the 28th's pradosha, 45% of the 29th's.
    assert (rows["2026-04-28"]["date"], rows["2026-04-28"]["rule"]) == (
        "2026-04-28",
        "covers_pradosha",
    )
    # 28 Feb: 3% of that evening, 34% of 1 Mar's.
    assert (rows["2026-02-28"]["date"], rows["2026-02-28"]["rule"]) == (
        "2026-03-01",
        "more_pradosha",
    )


def test_sankashti_on_the_chaturthi_current_at_moonrise():
    status, out = call("GET", "/v1/observances/sankashti", DELHI)
    assert status == 200, out
    rows = out["occurrences"]
    assert 12 <= len(rows) <= 14
    for r in rows:
        assert r["rule"] in OBSERVANCE_RULES["sankashti"]
        chosen = next(d for d in r["days"] if d["date"] == r["date"])
        assert r["angaraki"] == (r["vara"] == "tuesday") == (chosen["vara"] == "tuesday")
        if r["rule"] == "moonrise":
            assert chosen["current"] and sum(d["current"] for d in r["days"]) == 1


def test_named_amavasyas():
    status, out = call("GET", "/v1/observances/amavasya", DELHI)
    by_date = {r["vrata"]["date"]: r for r in out["occurrences"]}
    assert "mahalaya" in by_date["2026-10-10"]["names"]
    assert "mauni" in by_date["2026-01-18"]["names"] and "magha" in by_date["2026-02-17"]["names"]
    for r in out["occurrences"]:
        assert ("somavati" in r["names"]) == (r["vrata"]["vara"] == "monday")


def test_amavasya_touching_no_sunrise_keeps_its_month():
    # Kolkata, 16 May 2026: the Amavasya runs 05:11 to 01:31 and touches no sunrise.
    # The next sunrise is already in adhika Jyeshtha; the month is the one it ends.
    kolkata = {"year": "2026", "lat": "22.5726", "lon": "88.3639", "tz": "Asia/Kolkata"}
    status, out = call("GET", "/v1/observances/amavasya", kolkata)
    (row,) = [r for r in out["occurrences"] if r["vrata"]["date"] == "2026-05-16"]
    assert row["vrata"]["rule"] == "only_day"
    assert row["lunarMonth"] == {"amanta": "vaishakha", "purnimanta": "jyeshtha", "adhika": False}


def test_parana_follows_dharmasindhu():
    status, out = call("GET", "/v1/observances/ekadashi", {**DELHI, "parana": "true"})
    assert status == 200, out
    by_fast = {r["smarta"]["date"]: r for r in out["ekadashis"]}
    for r in out["ekadashis"]:
        for side in ("smarta", "vaishnava"):
            p = r["parana"][side]
            assert p["rule"] in OBSERVANCE_RULES["parana"] and p["start"] < p["end"]
            if p["rule"] != "trayodashi":  # broken inside Dvadashi, after Hari-vasara
                assert p["end"] <= r["dvadashiEnd"] == p["breakBefore"]
                assert p["hariVasaraEnd"] is None or p["start"] >= p["hariVasaraEnd"]
    # 20 Nov: Hari-vasara outlasts the first three muhurtas, so the afternoon; the
    # Vaishnava fast on the 21st finds no Dvadashi left, so Trayodashi (Drik agrees).
    prabodhini = by_fast["2026-11-20"]["parana"]
    assert (prabodhini["smarta"]["rule"], prabodhini["vaishnava"]["rule"]) == (
        "afternoon",
        "trayodashi",
    )
    # Without parana=true the rows are as before.
    status, out = call("GET", "/v1/observances/ekadashi", DELHI)
    assert "parana" not in out["ekadashis"][0]
