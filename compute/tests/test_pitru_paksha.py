from conftest import call

from astro_compute.meta import OBSERVANCE_RULES

DELHI = {"year": "2026", "lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}


def test_pitru_paksha_2026_at_delhi_matches_drik():
    status, out = call("GET", "/v1/observances/pitru-paksha", DELHI)
    assert status == 200, out
    assert out["lunarMonth"] == {"amanta": "bhadrapada", "purnimanta": "ashwin", "adhika": False}
    days = [r["date"][5:] for r in out["tithis"]]
    # Checked against Drik Panchang's New Delhi list: Chaturthi and Panchami share 30 Sep.
    assert days == [
        "09-27", "09-28", "09-29", "09-30", "09-30", "10-01", "10-02", "10-03",
        "10-04", "10-05", "10-06", "10-07", "10-08", "10-09", "10-10",
    ]  # fmt: skip
    assert (out["bharani"]["date"], out["magha"]["date"]) == ("2026-09-29", "2026-10-07")
    assert out["matamaha"]["date"] == "2026-10-11"
    for r in out["tithis"]:
        group = {"chaturdashi": "ekoddishta", "amavasya": "shraddha"}.get(r["tithi"], "mahalaya")
        assert r["rule"] in OBSERVANCE_RULES[group]
    assert "kutapaRauhina" in out["tithis"][13] and "gajacchaya" in out["tithis"][14]


def test_pitru_paksha_2027_chaturdashi_takes_the_earlier_day_when_neither_midday():
    status, out = call("GET", "/v1/observances/pitru-paksha", {**DELHI, "year": "2027"})
    ch = out["tithis"][13]
    # 28 Sep 13:55 to 29 Sep 10:55: neither day's kutapa-rauhina (Drik: 28 Sep).
    assert (ch["date"], ch["rule"], ch["variantDate"]) == ("2027-09-28", "neither_earlier", None)
