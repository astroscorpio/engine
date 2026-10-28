import datetime as dt

import swisseph as swe
from conftest import call
from jyotisha.ephemeris import luminaries
from jyotisha.muhurta import NAKSHATRAS
from jyotisha.rare import (
    AMRITA_SIDDHI,
    DAGDHA,
    KANA,
    MARANA,
    RAVI_YOGA_COUNTS,
    SARVARTHA_SIDDHI,
    SIDDHI,
    UTPATA,
    nakshatra_28,
)

from astro_compute.meta import VIVAH_RULES

DELHI = {"lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}
ALLOWED = {
    "mrigashira", "hasta", "mula", "anuradha", "magha", "rohini", "revati",
    "uttara_phalguni", "uttara_ashadha", "uttara_bhadrapada", "swati",
}  # fmt: skip


WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def jd(iso):
    t = dt.datetime.fromisoformat(iso).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def day_yoga(w, vara):
    """MC 1.30's utpata, mrtyu or kana, or Narada's dagdha, at a window's middle, unless a
    Ravi or siddhi yoga lifts it there (MC 1.27, 1.42)."""
    sun, moon = luminaries((jd(w["start"]) + jd(w["end"])) / 2)
    i = WEEKDAYS.index(vara)
    n28, n27 = nakshatra_28(moon.longitude), NAKSHATRAS[int(moon.longitude // (360 / 27))]
    if (moon.nakshatra - sun.nakshatra) % 27 + 1 in RAVI_YOGA_COUNTS:
        return False
    if n27 in SARVARTHA_SIDDHI.get(i, set()) or SIDDHI.get(i) == n28 or AMRITA_SIDDHI.get(i) == n27:
        return False
    return any(t.get(i) == n28 for t in (UTPATA, MARANA, KANA)) or DAGDHA.get(i) == n27


def year(y):
    status, out = call("GET", "/v1/muhurat/vivah", {"year": y, **DELHI})
    assert status == 200, out
    return out


def test_listed_days_keep_every_day_rule():
    out = year("2026")
    assert out["days"]
    for d in out["days"]:
        assert d["vara"] != "tuesday" and d["grade"] in ("best", "middling")
        assert d["lunarMonth"]["amanta"] in (
            "magha", "phalguna", "vaishakha", "jyeshtha", "ashadha", "kartika", "margashirsha",
        )  # fmt: skip
        for w in d["windows"]:
            assert w["start"] < w["end"] and w["nakshatra"] in ALLOWED
            assert w["tithi"] not in ("chaturthi", "navami", "chaturdashi", "amavasya")
            assert not day_yoga(w, d["vara"]), (d["date"], w)
        assert set(d["cautions"]) <= set(VIVAH_RULES)
        g = d["godhuli"]
        if g:  # MC 6.99's weekday halves: test_godhuli_thursday_after_sunset_saturday_before
            assert g["start"] < g["end"]
    for b in out["blocks"]:
        assert b["rule"] in VIVAH_RULES


def test_godhuli_thursday_after_sunset_saturday_before():
    """MC 6.99 and its commentary (p. 307): Thursday's godhuli only after sunset (ardhayama
    falls before it), Saturday's only before (kulika after); elsewhere half a ghatika either
    side. Each window against the day's sunset, in minutes."""
    want = {"thursday": (0, 12), "saturday": (-12, 0)}
    seen = set()
    for d in year("2026")["days"]:
        g = d["godhuli"]
        if not g or (d["vara"] in seen and d["vara"] not in want):
            continue
        seen.add(d["vara"])
        status, p = call("GET", "/v1/panchang", {"date": d["date"], **DELHI})
        assert status == 200, p
        ss = jd(p["sunset"])
        got = (round((jd(g["start"]) - ss) * 1440), round((jd(g["end"]) - ss) * 1440))
        assert got == want.get(d["vara"], (-12, 12)), (d["date"], d["vara"], got)
    assert set(want) <= seen


def test_venus_infancy_follows_the_side_it_rises_on():
    # MC 5.27: 10 days after rising in the west (Jan 2026's superior conjunction),
    # 3 after rising in the east (Oct 2026's inferior conjunction).
    blocks = [b for b in year("2026")["blocks"] if b["rule"] == "venus_infant"]
    assert [b["detail"] for b in blocks] == [
        "10 days after rising in the west",
        "3 days after rising in the east",
    ]


def test_no_listed_day_inside_a_block():
    out = year("2027")
    for b in out["blocks"]:
        if b["rule"] in ("jupiter_set", "venus_set", "jupiter_sign", "eclipse"):
            inside = [d["date"] for d in out["days"] if b["start"][:10] < d["date"] < b["end"][:10]]
            assert not inside, (b, inside)


def test_excluded_days_carry_their_relaxed_rules():
    out = year("2026")
    relaxable = {
        "vedha_slow", "jupiter_sign", "tuesday", "rikta", "solar_month", "infancy_old",
        "venus_set", "eclipse", "utpata", "marana", "kana", "dagdha", "visha", "no_lagna",
    }  # fmt: skip
    listed = {d["date"] for d in out["days"]}
    assert out["excluded"]
    for d in out["excluded"]:
        assert d["date"] not in listed and d["windows"]
        assert set(d["rules"]) <= relaxable and len(d["reasons"]) == len(d["rules"])
        assert all(not k.startswith("_") for w in d["windows"] for k in w)
    assert set(VIVAH_RULES) >= relaxable
    # Jupiter enters Leo on 31 Oct 2026: November's candidates are excluded, with the reason.
    late = [d for d in out["excluded"] if d["date"] >= "2026-11-21"]
    assert late and all("jupiter_sign" in d["rules"] for d in late)


def test_blocks_carry_the_season_and_excluded_days_their_facts():
    from astro_compute.ids import SIGN_IDS

    out = year("2026")
    rules = {b["rule"] for b in out["blocks"]}
    assert {"chaturmas", "off_season", "adhika_month"} <= rules  # 2026 has an adhika Jyeshtha
    off = {b["detail"] for b in out["blocks"] if b["rule"] == "off_season"}
    assert "shravana" in off and off <= {"pausha", "chaitra", "shravana", "bhadrapada", "ashwin"}
    assert {b["detail"] for b in out["blocks"] if b["rule"] == "adhika_month"} == {"jyeshtha"}
    assert all(
        b["detail"] in SIGN_IDS for b in out["blocks"] if b["rule"] in ("jupiter_sign", "sun_sign")
    )
    # Month runs follow the month's own new moons: consecutive ones meet.
    runs = sorted(
        (b["start"], b["end"]) for b in out["blocks"] if b["rule"] in ("off_season", "adhika_month")
    )
    assert all(a[1] <= b[0] for a, b in zip(runs, runs[1:], strict=False))
    assert runs[0][0] < "2025-12-25"  # the Pausha begun in 2025, from its new moon
    (chaturmas,) = [b for b in out["blocks"] if b["rule"] == "chaturmas"]
    assert chaturmas["start"] < chaturmas["end"]
    facts = {}
    for e in out["excluded"]:
        assert [d["rule"] for d in e["details"]] == e["rules"] and len(e["reasons"]) == len(
            e["rules"]
        )
        facts |= {d["rule"]: d for d in e["details"]}
    assert facts, "2026 has excluded days"
    for d in facts.values():
        if d["rule"] == "vedha_slow":
            assert d["planets"] and d["star"] and d["pierces"]
        if d["rule"] in ("utpata", "marana", "kana", "dagdha", "visha"):
            assert d["weekday"] and d["star"]
        if d["rule"] == "infancy_old":
            assert d["planet"] in ("jupiter", "venus") and d["state"] in ("infant", "old")


def test_listed_lagnas_pass_the_bars():
    """Phase 2 (V1-V10): every lagna shown clears MC 6.84's houses and the navamsa rule,
    checked here from the ephemeris at the lagna's middle."""
    from jyotisha.ephemeris import ascendant, positions

    from astro_compute.meta import VIVAH_LAGNA_RULES, VIVAH_LIFTS

    level = {k: v[2] for k, v in VIVAH_LAGNA_RULES.items()}
    malefic = {"Sun", "Mars", "Saturn", "Rahu", "Ketu", "Moon"}
    shown = 0
    for d in year("2028")["days"]:
        rows = [lg for w in d["windows"] for lg in w["lagnas"]]
        assert ("no_clean_lagna" in d["cautions"]) == (not any(lg["clean"] for lg in rows))
        status = "clean" if any(lg["clean"] for lg in rows) else "faulted" if rows else "godhuli"
        assert d["lagnaStatus"] == status and (rows or d["godhuli"])
        for w in d["windows"]:
            assert all(level[k] == "bar" for k in w["lagnaBars"])
            for lg in w["lagnas"]:
                shown += 1
                assert w["start"] <= lg["start"] < lg["end"] <= w["end"]
                assert all(level[f] != "bar" for f in lg["faults"])
                assert lg["clean"] == (lg["faults"] == [])
                for lift in lg["lifted"]:  # a lifted rule is shown, never also applied
                    assert lift["rule"] in level and lift["by"] in VIVAH_LIFTS
                    assert lift["rule"] not in lg["faults"]
                pts = lg["points"]
                grade = "best" if pts >= 15 else "middling" if pts >= 10 else "poor"
                assert pts >= 5 and lg["grade"] == grade
                t = (jd(lg["start"]) + jd(lg["end"])) / 2
                p = positions(t)
                asc = ascendant(t, 28.6139, 77.2090)[0].longitude
                lagna = int(asc // 30)
                house = {g: (x.sign - lagna) % 12 + 1 for g, x in p.items()}
                assert not any(h == 7 for h in house.values())  # jamitra from the lagna
                assert not any(house[g] == 1 for g in malefic)
                assert house["Mars"] not in (8, 10) and house["Saturn"] != 12
                assert house["Venus"] not in (3, 8)
                nav = int(asc // (30 / 9)) % 12
                assert nav in (2, 5, 6, 8) or set(lg["faults"]) & {
                    "navamsa_ds_only",
                    "navamsa_pisces",
                }
    assert shown


def test_kartari_needs_a_direct_malefic_behind_and_a_retrograde_one_ahead():
    from jyotisha.ephemeris import Position

    from astro_compute import vivah_lagna as V

    def chart(**at):
        base = {g: (195.0, 1.0) for g in V.GRAHAS}  # all in Libra, direct
        base.update(at)
        return {g: Position(g, lon, speed) for g, (lon, speed) in base.items()}

    # Taurus rising: the 12th is Aries, the 2nd Gemini.
    assert V._kartari(chart(Sun=(15.0, 1.0), Saturn=(75.0, -0.05)), 1, True)[:2] == (True, False)
    assert V._kartari(chart(Sun=(15.0, 1.0), Rahu=(75.0, 0.02)), 1, True)[0]  # nodes retrograde
    assert V._kartari(chart(Sun=(15.0, 1.0), Mars=(75.0, 0.6)), 1, True)[:2] == (False, True)
    # The dark fortnight's Moon is a malefic (V1, our reading); the bright one is not.
    moon_behind = chart(Moon=(20.0, 13.0), Saturn=(75.0, -0.05))
    assert V._kartari(moon_behind, 1, False)[0] and not V._kartari(moon_behind, 1, True)[0]


def test_a_day_with_no_lagna_and_no_godhuli_is_excluded():
    out = year("2028")
    gone = [e for e in out["excluded"] if e["rules"] == ["no_lagna"]]
    assert gone and not {e["date"] for e in gone} & {d["date"] for d in out["days"]}
    for e in gone:
        (detail,) = e["details"]
        assert detail["rule"] == "no_lagna" and detail["barred"] and e["windows"]
        assert all("lagnas" not in w for w in e["windows"])
