import datetime as dt

import swisseph as swe
from conftest import DELHI, call
from jyotisha.ephemeris import ascendant, luminaries, positions

from astro_compute import mundan as M
from astro_compute.ids import NAKSHATRA_IDS, SIGN_IDS
from astro_compute.meta import MUNDAN_RULES


def jd(iso):
    t = dt.datetime.fromisoformat(iso).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def test_every_window_keeps_the_tonsure_rules_at_its_middle():
    status, out = call("GET", "/v1/muhurat/mundan", {"year": "2027", **DELHI})
    assert status == 200, out
    assert out["days"]
    lat, lon = float(DELHI["lat"]), float(DELHI["lon"])
    for d in out["days"]:
        assert d["vara"] in M.VARAS and d["lunarMonth"]["amanta"] != "chaitra"
        assert set(d["cautions"]) <= set(MUNDAN_RULES)
        for w in d["windows"]:
            t = (jd(w["start"]) + jd(w["end"])) / 2
            sun, moon = luminaries(t)
            assert NAKSHATRA_IDS[moon.nakshatra] == w["nakshatra"] and moon.nakshatra in M.STARS
            assert sun.sign in (9, 10, 11, 0, 1, 2)
            lagna = int(ascendant(t, lat, lon)[0].longitude // 30)
            assert SIGN_IDS[lagna] == w["lagna"] and lagna in M.BENEFIC_SIGNS
            p = positions(t)
            house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
            assert all(g == "Venus" for g, h in house.items() if h == 8)
            assert all(house[g] not in M.KENDRA for g in ("Sun", "Mars", "Saturn"))
            assert not (d["vara"] == "monday" and w["paksha"] == "krishna")
    for b in out["blocks"]:
        assert b["rule"] in MUNDAN_RULES and b["rule"] != "sun_sign"


def test_finder_mundan_act_vetoes_the_wrong_weekday_and_the_eldest_jyeshtha():
    def vetoes(at, **extra):
        query = {"act": "mundan", "at": at, **DELHI, **extra}
        status, out = call("GET", "/v1/muhurta/check", query)
        assert status == 200, out
        return {r["id"] for r in out["vetoes"]}

    day = dt.date(2027, 5, 10)
    sunday = day + dt.timedelta((6 - day.weekday()) % 7)
    assert "weekday_mundan" in vetoes(f"{sunday.isoformat()}T10:00:00+05:30")
    # 2027's Jyeshtha (amanta) runs from the new moon of 5 June.
    at = "2027-06-10T10:00:00+05:30"
    assert "eldest_jyeshtha" in vetoes(at, eldest="true")
    assert "eldest_jyeshtha" not in vetoes(at)
