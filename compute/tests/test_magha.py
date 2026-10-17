from conftest import call

from astro_compute.festivals import MAGHA_STAR, SHRAVANA, VYATIPATA
from astro_compute.ids import NAKSHATRA_IDS, YOGA_IDS
from astro_compute.meta import FESTIVAL_RULES, MAGHA_MARKS, OBSERVANCE_RULES

DELHI = {"lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}
LONDON = {"lat": "51.5074", "lon": "-0.1278", "tz": "Europe/London"}


def _season(year, place=DELHI):
    status, out = call("GET", "/v1/festivals/magha-snana", {**place, "year": str(year)})
    assert status == 200, out
    (row,) = out["occurrences"]
    return out, row


def _days(row):
    return {d["id"]: d for d in row["bathDays"]}


def test_2026_bath_days_match_research():
    """magha-snana.md: the 2026 season at Prayagraj, its Shivaratri after the Kumbha
    ingress (the lead's yearly rule)."""
    out, row = _season(2026)
    days = _days(row)
    got = {k: days[k]["date"] for k in ("pausha_purnima", "mauni_amavasya", "maghi_purnima")}
    assert got == {
        "pausha_purnima": "2026-01-03",
        "mauni_amavasya": "2026-01-18",
        "maghi_purnima": "2026-02-01",
    }
    assert days["vasanta_panchami"]["date"] == "2026-01-23"
    assert days["mauni_amavasya"]["popularName"] == "Mauni Amavasya"
    s = row["shivaratri"]
    assert (s["date"], s["kumbhaSankranti"][:10], s["insideSolarSpan"]) == (
        "2026-02-15",
        "2026-02-13",
        False,
    )
    assert out["computedAt"]["name"] == "Prayagraj" and row["month"]["rule"] == "month_regular"
    prayagraj = {"lat": "25.4358", "lon": "81.8463", "tz": "Asia/Kolkata"}
    status, sk = call("GET", "/v1/observances/sankranti", {**prayagraj, "year": "2026"})
    makara = next(r for r in sk["sankrantis"] if r["sign"] == "capricorn")
    assert days["makara_sankranti"]["date"] == makara["date"]


def test_every_day_carries_a_known_rule_and_mark():
    for year in (2026, 2027, 2028):
        _, row = _season(year)
        dates = [d["date"] for d in row["bathDays"]]
        assert dates == sorted(dates) and len(dates) == 6
        for d in row["bathDays"]:
            kind = d.get("ruleKind")
            rules = (
                OBSERVANCE_RULES["sankranti"]
                if kind == "sankranti"
                else FESTIVAL_RULES[kind or "magha-snana"]
            )
            assert d["rule"] in rules and d["mark"] in MAGHA_MARKS, d
        assert row["month"]["rule"] in FESTIVAL_RULES["magha-snana"]
        assert row["shivaratri"]["mark"] in MAGHA_MARKS
        assert row["ardhodaya"] is None and row["mahamaghi"] is None  # none in 2026-2028


def test_one_answer_for_every_city():
    _, delhi = _season(2027)
    _, london = _season(2027, LONDON)
    assert delhi == london
    assert delhi["month"]["solar"]["start"]["at"].endswith("+05:30")


def test_three_days_end_on_the_maghi_purnima():
    """v2 decision 2: three civil days ending on the Maghi Purnima, the headline first; in
    2027 the Purnima holds no sunrise."""
    _, row = _season(2027)
    maghi = _days(row)["maghi_purnima"]
    assert maghi["rule"] == "only_day"
    views = row["threeDays"]
    assert views[0] == {
        "id": "trayodashi",
        "dates": ["2027-02-18", "2027-02-19", maghi["date"]],
        "headline": True,
    }
    assert [v["id"] for v in views[1:]] == [
        "makara_ratha_maghi",
        "from_dashami",
        "makara_first_three",
        "magha_first_three",
    ]
    assert all(len(v["dates"]) == 3 and v["id"] in FESTIVAL_RULES["magha-snana"] for v in views)


def test_ardhodaya_by_night_and_by_day():
    """v2 decision 3: the four meet within the Sunday; a night meeting is NS's alone."""
    night = _season(2016)[1]["ardhodaya"]
    assert night["start"][:10] == "2016-02-07" and night["daylight"] is False
    day = _season(2084)[1]["ardhodaya"]
    assert day["start"][:10] == "2084-02-06" and day["daylight"] is True


def test_mahamaghi_needs_jupiter_and_the_moon_in_magha():
    assert _season(2051)[1]["mahamaghi"]["start"][:10] == "2051-02-24"


def test_lost_months():
    """DS p. 4 (v3): with Margashirsha lost into Pausha, the bathing begins on the Purnima
    of the month holding the Makara ingress. v4: when one month holds both ingresses, DS p.
    86's Makara-to-Kumbha span is the month and its one full moon shows once."""
    _, row = _season(2124)
    assert row["month"]["rule"] == "month_kshaya"
    assert _days(row)["pausha_purnima"]["date"] == "2124-01-01"
    _, row = _season(1983)
    m, days = row["month"], _days(row)
    assert (m["rule"], m["lunar"]) == ("month_kshaya_solar", None)
    assert (m["solar"]["start"]["date"], m["solar"]["end"]["date"]) == ("1983-01-14", "1983-02-13")
    assert "pausha_purnima" not in days and len(days) == 5
    maghi, mauni, s = days["maghi_purnima"], days["mauni_amavasya"], row["shivaratri"]
    assert (maghi["date"], maghi["mark"]) == ("1983-01-28", "lost_month_purnima")
    assert (mauni["date"], mauni["mark"]) == ("1983-02-12", "lost_month_amavasya")
    assert mauni["popularName"] == "Mauni Amavasya"
    assert (s["date"], s["insideSolarSpan"], s["mark"]) == (
        "1983-02-11",
        True,
        "inside_month_not_named",
    )
    assert row["ardhodaya"] is None and row["mahamaghi"] is None  # v5: Saturday; Jupiter Scorpio
    for d in row["bathDays"]:
        rules = OBSERVANCE_RULES["sankranti"] if d.get("ruleKind") == "sankranti" else None
        assert d["rule"] in (rules or FESTIVAL_RULES[d.get("ruleKind") or "magha-snana"])
        assert d["mark"] in MAGHA_MARKS, d
    assert m["rule"] in FESTIVAL_RULES["magha-snana"]
    assert _season(1906)[1]["month"]["rule"] == "month_regular"  # 1 Jan 1906 had no midnight


def test_indexes():
    assert NAKSHATRA_IDS[SHRAVANA] == "shravana" and NAKSHATRA_IDS[MAGHA_STAR] == "magha"
    assert YOGA_IDS[VYATIPATA] == "vyatipata"
