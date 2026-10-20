"""Vaikuntha Ekadashi (festivals.md s37, the lead's rulings of 19 Oct 2026), popular practice:
the shukla Ekadashi whose leading (Smarta-side) day falls in Margazhi by the Tamil Rule, chosen
at Chennai for every city, each city's days its own /ekadashi row. Checked against research's
seasons by weekday and Ekadashi, against the Madras notice years and against the rule; no date
is written here."""

import datetime as dt

from conftest import call

from astro_compute.festivals import CHENNAI as AT_CHENNAI

CHENNAI = {"lat": str(AT_CHENNAI["lat"]), "lon": str(AT_CHENNAI["lon"]), "tz": AT_CHENNAI["tz"]}
NEW_YORK = {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"}
MOKSHADA, PUTRADA = "margashirsha_shukla", "pausha_shukla"
# Research's table (s37, rule 1 restated): the year a season's Margazhi begins -> the leading
# day's weekday at Chennai, its Ekadashi, and whether the Vaishnava day differs.
SEASONS = {
    2022: ("monday", PUTRADA, False),
    2023: ("saturday", MOKSHADA, False),
    2024: ("friday", PUTRADA, False),
    2025: ("tuesday", PUTRADA, True),
    2026: ("sunday", MOKSHADA, False),
    2027: ("saturday", PUTRADA, False),
    2028: ("wednesday", PUTRADA, False),
    2029: ("sunday", MOKSHADA, False),
    2030: ("saturday", PUTRADA, False),
    2031: ("wednesday", MOKSHADA, False),
    2032: ("tuesday", PUTRADA, False),
    2033: ("sunday", PUTRADA, False),
    2034: ("thursday", MOKSHADA, True),
    2035: ("thursday", PUTRADA, False),
    2036: ("monday", PUTRADA, False),
    2037: ("friday", MOKSHADA, False),
    2038: ("thursday", PUTRADA, False),
    2039: ("monday", MOKSHADA, False),
    2040: ("saturday", PUTRADA, False),
}
NONE = {2024, 2027, 2030, 2032, 2035, 2038, 2040}
TWO = {2023, 2025, 2028, 2031, 2034, 2036, 2039}


def year(y: int, place: dict = CHENNAI) -> list[dict]:
    status, out = call("GET", "/v1/festivals/vaikuntha-ekadashi", {"year": str(y), **place})
    assert status == 200, out
    assert out["basis"] == "popular_practice" and out["source"] is None and out["context"]
    assert out["computedAt"]["name"] == "Chennai"
    return out["occurrences"]


def next_day(date: str) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()


def check(o: dict, vara: str, name: str, differs: bool) -> None:
    assert (o["vara"], o["nameId"], o["paksha"]) == (vara, name, "shukla"), o["season"]
    assert o["margazhi"]["start"] <= o["chennaiDate"] <= o["margazhi"]["end"], o["season"]
    assert o["date"] == o["smarta"]["date"] and o["rule"] == "margazhi_leading_day"
    assert o["variantDate"] == (next_day(o["date"]) if differs else None), o["season"]
    assert o["variantDate"] in (None, o["vaishnava"]["date"])
    assert o["variantBasis"] == ("vaishnava" if differs else None)


def test_research_seasons_at_chennai():
    seen = {o["season"]: o for y in range(2023, 2042) for o in year(y)}
    for season, expected in SEASONS.items():
        check(seen[season], *expected)
        assert seen[season]["date"] == seen[season]["chennaiDate"]


def test_civil_years_hold_none_one_or_two():
    for y in range(2023, 2041):
        assert len(year(y)) == (0 if y in NONE else 2 if y in TWO else 1), y


def test_the_madras_notice_years():
    (o,) = year(1923)  # the notice kept the Vaishnava day, our variant
    assert o["season"] == 1923
    check(o, "tuesday", MOKSHADA, True)
    a, b = year(1925)
    assert (a["season"], b["season"]) == (1924, 1925)
    check(a, "monday", PUTRADA, False)
    check(b, "friday", PUTRADA, False)
    assert year(1926) == []  # "as it does not occur within the year"
    o, later = year(1930)  # the notice's day; the 1930-31 season's falls in its Christmas holidays
    assert (o["season"], later["season"]) == (1929, 1930)
    check(o, "saturday", PUTRADA, False)
    (o,) = year(1931)  # the 1931 list names it on a Sunday, 20 December
    assert o["season"] == 1931
    check(o, "sunday", MOKSHADA, False)
    assert year(1932) == []  # the 1932 list names none


def test_each_city_keeps_its_own_ekadashi_day():
    for place in (CHENNAI, NEW_YORK):
        (o,) = year(2026, place)
        assert o["nameId"] == MOKSHADA and o["chennaiDate"] == year(2026)[0]["date"]
        status, out = call("GET", "/v1/observances/ekadashi", {"year": "2026", **place})
        assert status == 200
        (row,) = [r for r in out["ekadashis"] if r["tithi"] == o["tithi"]]
        assert {k: o[k] for k in row} == row
