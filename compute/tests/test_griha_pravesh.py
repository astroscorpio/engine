import datetime as dt

import swisseph as swe
from conftest import DELHI, call
from jyotisha.ephemeris import ascendant, luminaries, positions
from test_vivah import day_yoga

from astro_compute import griha_pravesh as G
from astro_compute.ids import NAKSHATRA_IDS, SIGN_IDS
from astro_compute.meta import GRIHA_PRAVESH_RULES
from astro_compute.models import EkadashiQuery

STARS = {
    "chitra", "uttara_phalguni", "uttara_ashadha", "uttara_bhadrapada", "rohini",
    "mrigashira", "anuradha", "dhanishta", "revati", "shatabhisha",
}  # fmt: skip
FIXED_DUAL = {"taurus", "leo", "scorpio", "aquarius", "gemini", "virgo", "sagittarius", "pisces"}


def year(y):
    status, out = call("GET", "/v1/muhurat/griha-pravesh", {"year": y, **DELHI})
    assert status == 200, out
    return out


def jd(iso):
    t = dt.datetime.fromisoformat(iso).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def test_every_window_keeps_every_rule_at_its_middle():
    out = year("2026")
    assert out["days"]
    lat, lon = float(DELHI["lat"]), float(DELHI["lon"])
    for d in out["days"]:
        assert d["vara"] not in ("sunday", "tuesday")
        assert d["lunarMonth"]["amanta"] in ("magha", "phalguna", "vaishakha", "jyeshtha")
        assert set(d["cautions"]) <= {"krishna_after_dashami", "saturday"}
        for w in d["windows"]:
            assert w["start"] < w["end"] and w["nakshatra"] in STARS
            assert w["lagna"] in FIXED_DUAL
            assert w["tithi"] not in ("chaturthi", "navami", "chaturdashi", "amavasya")
            t = (jd(w["start"]) + jd(w["end"])) / 2
            sun, moon = luminaries(t)
            assert NAKSHATRA_IDS[moon.nakshatra] == w["nakshatra"]
            assert sun.sign in G.UTTARAYANA and sun.sign not in G.BARRED_SUN
            assert G._pot_chakra(sun.nakshatra, moon.nakshatra)
            asc = ascendant(t, lat, lon)[0].longitude
            lagna = int(asc // 30)
            assert SIGN_IDS[lagna] == w["lagna"]
            assert int(asc // (30 / 9)) % 12 not in G.MOVABLE
            p = positions(t)
            house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
            assert not any(h in (4, 8) for h in house.values()), (w, house)
            assert house["Moon"] not in (1, 6, 8, 12)
            assert p["Jupiter"].sign not in G.BARRED_JUPITER
            assert not day_yoga(w, d["vara"]), (d["date"], w)


def test_blocks_and_rejections_use_known_rules():
    q = EkadashiQuery(year=2027, lat=28.6139, lon=77.2090, tz="Asia/Kolkata")
    why: dict = {}
    out = G.griha_pravesh(q, why)
    for b in out["blocks"]:
        assert b["rule"] in GRIHA_PRAVESH_RULES
    for b in out["blocks"]:
        if b["rule"] in ("jupiter_set", "venus_set", "dakshinayana", "jupiter_sign"):
            inside = [d["date"] for d in out["days"] if b["start"][:10] < d["date"] < b["end"][:10]]
            assert not inside, (b, inside)
    # The pot chakra turns away days that pass the month and the rest of the day filter.
    reasons = set(why.values())
    assert {"pot_chakra", "listed", "month"} <= reasons
    assert sum(v == "listed" for v in why.values()) == len(out["days"])


def test_excluded_days_carry_only_the_relaxed_rules():
    out = year("2026")
    relaxable = {
        "middling_month", "sun_sign", "infancy_old", "venus_set", "jupiter_sign",
        "utpata", "marana", "kana", "dagdha", "visha",
    }  # fmt: skip
    assert set(GRIHA_PRAVESH_RULES) >= relaxable
    listed = {d["date"] for d in out["days"]}
    assert out["excluded"]
    for d in out["excluded"]:
        assert d["date"] not in listed and d["windows"]
        assert d["vara"] not in ("sunday", "tuesday")
        assert set(d["rules"]) <= relaxable and len(d["reasons"]) == len(d["rules"])
        for w in d["windows"]:
            assert w["nakshatra"] in STARS and w["lagna"] in FIXED_DUAL
    # November 2026 is Kartika and Margashirsha, with Jupiter in Leo.
    late = [d for d in out["excluded"] if d["date"] >= "2026-11-21"]
    assert late and all({"middling_month", "jupiter_sign"} <= set(d["rules"]) for d in late)
    for d in late:
        facts = {x["rule"]: x for x in d["details"]}
        assert [x["rule"] for x in d["details"]] == d["rules"]
        assert facts["jupiter_sign"]["sign"] == "leo"
        assert facts["middling_month"]["month"] in ("kartika", "margashirsha")


def test_windows_carry_the_doors_that_pass_mc_13_5():
    from jyotisha import muhurta as Mu

    out = year("2026")
    windows = [w for d in out["days"] + out["excluded"] for w in d["windows"]]
    assert windows and all(set(w["doors"]) <= set("NESW") for w in windows)
    assert any(w["doors"] for w in windows)
    classes = {"purnima": "E", "panchami": "E", "dashami": "E", "pratipada": "S", "shashthi": "S"}
    classes |= {"ekadashi": "S", "dwitiya": "W", "saptami": "W", "dwadashi": "W"}
    classes |= {"tritiya": "N", "ashtami": "N", "trayodashi": "N"}
    quarter = {n: d for d, stars in Mu.DOOR_STARS.items() for n in stars}
    ids = dict(zip(Mu.NAKSHATRAS, NAKSHATRA_IDS, strict=True))
    for w in windows:
        # One tithi class per door (MC 13.5) and one quarter per star (MC 11.33): a window
        # can pass at most the door its tithi and its star both point to.
        star = next(n for n, i in ids.items() if i == w["nakshatra"])
        assert set(w["doors"]) <= {classes[w["tithi"]]} & {quarter[star]}
    assert Mu.DOOR_TITHIS["E"] == {5, 10, 15}


def test_blocks_carry_the_barred_lunar_months():
    out = year("2026")
    off = {b["detail"] for b in out["blocks"] if b["rule"] == "off_season"}
    assert {"chaitra", "ashadha", "pausha"} <= off
    assert off <= {"chaitra", "ashadha", "shravana", "bhadrapada", "ashwin", "pausha"}
    assert {b["detail"] for b in out["blocks"] if b["rule"] == "adhika_month"} == {"jyeshtha"}
    assert {b["rule"] for b in out["blocks"]} <= set(GRIHA_PRAVESH_RULES)
