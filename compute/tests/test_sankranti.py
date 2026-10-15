from conftest import DELHI, call

from astro_compute.meta import OBSERVANCE_RULES


def year(y):
    status, out = call("GET", "/v1/observances/sankranti", {"year": y, **DELHI})
    assert status == 200, out
    return out


def test_twelve_ingresses_with_windows_in_daylight():
    out = year("2026")
    rows = out["sankrantis"]
    assert len(rows) == 12 and len({r["sign"] for r in rows}) == 12
    classes = {r["sign"]: r["class"] for r in rows}
    assert classes["aries"] == classes["libra"] == "vishuva"
    assert classes["cancer"] == classes["capricorn"] == "ayana"
    for r in rows:
        assert r["rule"] in OBSERVANCE_RULES["sankranti"]
        assert r["sayana"] < r["at"] and r["punyakala"]
        for p in r["punyakala"]:
            assert p["start"] <= p["end"]
            if p["best"]:
                assert p["start"] <= p["best"]["start"] <= p["best"]["end"] <= p["end"]
        if not r["atNight"]:
            assert r["date"] == r["at"][:10]


def test_makara_matches_the_southern_rule():
    # Drik Panchang, New Delhi: 14 Jan 2026 (a day ingress), 15 Jan 2027 (at night,
    # so the next day's forenoon; Baudhayana keeps both days).
    m26 = next(r for r in year("2026")["sankrantis"] if r["sign"] == "capricorn")
    assert (m26["date"], m26["rule"], m26["atNight"]) == ("2026-01-14", "day", False)
    assert m26["punyakala"][0]["start"] == m26["at"]
    m27 = next(r for r in year("2027")["sankrantis"] if r["sign"] == "capricorn")
    assert (m27["date"], m27["rule"]) == ("2027-01-15", "makara_night_next_day")
    assert m27["variants"]["baudhayana"] == ["2027-01-14", "2027-01-15"]
