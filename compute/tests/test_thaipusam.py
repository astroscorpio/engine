"""Thaipusam (festivals.md s38; the lead's rulings of 19 and 20 Oct 2026), popular practice:
the civil day of Tai that Pusam covers most in the city's own time, the next day as the variant
where Pusam holds its sunrise instead, and the Pusam nearest Tai's full moon when Tai holds two.
Checked against s38's days for 2026-2040 at Chennai, Kuala Lumpur and Singapore, by weekday; no
date is written here."""

import datetime as dt

import pytest
from conftest import call

PLACES = {
    "chennai": {"lat": "13.08784", "lon": "80.27847", "tz": "Asia/Kolkata"},
    "kuala-lumpur": {"lat": "3.1412", "lon": "101.68653", "tz": "Asia/Kuala_Lumpur"},
    "singapore": {"lat": "1.28967", "lon": "103.85007", "tz": "Asia/Singapore"},
}
NEW_YORK = {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"}
# s38's table: the year -> (the day's weekday, the sunrise variant's weekday or None), the same
# at the three cities except Chennai in 2036.
DAYS = {
    2026: ("sunday", None),
    2027: ("friday", "saturday"),
    2028: ("wednesday", None),
    2029: ("tuesday", None),
    2030: ("sunday", None),
    2031: ("thursday", None),
    2032: ("tuesday", None),
    2033: ("sunday", None),
    2034: ("thursday", "friday"),
    2035: ("wednesday", None),
    2036: ("monday", None),
    2037: ("saturday", None),
    2038: ("thursday", None),
    2039: ("tuesday", None),
    2040: ("sunday", None),
}
CHENNAI_2036 = ("sunday", "monday")
NO_SUNRISE = {2028}  # s38: Pusam holds no sunrise anywhere
SUNRISE_HELD = {2026, 2029, 2030}  # s38's first table: the day Pusam covers most also holds it
TWO_PUSAMS = {2025, 2033}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def get(y: int, place: dict) -> dict:
    status, out = call("GET", "/v1/festivals/thaipusam", {"year": str(y), **place})
    assert status == 200, out
    return out


def day(stamp: str) -> dt.date:
    return dt.date.fromisoformat(stamp[:10])


@pytest.mark.parametrize("y", sorted(DAYS))
@pytest.mark.parametrize("city", sorted(PLACES))
def test_section_38s_days(city, y):
    out = get(y, PLACES[city])
    assert out["basis"] == "popular_practice" and out["source"] is None
    assert "computedAt" not in out
    (o,) = out["occurrences"]
    weekday, variant = CHENNAI_2036 if (city, y) == ("chennai", 2036) else DAYS[y]
    assert o["vara"] == weekday and WEEKDAYS[day(o["date"]).weekday()] == weekday
    tai = {
        c["date"]: c["hours"]
        for c in o["coverage"]
        if out["tai"]["start"] <= c["date"] <= out["tai"]["end"]
    }
    assert o["date"] in tai and tai[o["date"]] == max(tai.values())
    if variant:
        assert o["rule"] == "majority_sunrise_variant" and o["variantBasis"] == "sunrise_rule"
        assert day(o["variantDate"]) - day(o["date"]) == dt.timedelta(days=1)
        assert WEEKDAYS[day(o["variantDate"]).weekday()] == variant
    else:
        assert o["variantDate"] is None and o["variantBasis"] is None
        assert o["rule"] != "majority_sunrise_variant"
    if y in NO_SUNRISE:
        assert o["rule"] == "majority_no_sunrise"
    if y in SUNRISE_HELD:
        assert o["rule"] == "majority_with_sunrise"
    assert o["pusam"]["start"] < o["pusam"]["end"] and o["cautions"] == []
    assert ("twoPusam" in o) == (y in TWO_PUSAMS)


@pytest.mark.parametrize("y", sorted(TWO_PUSAMS))
def test_two_pusams_take_the_one_nearest_tais_full_moon(y):
    for place in PLACES.values():
        (o,) = get(y, place)["occurrences"]
        assert o["twoPusam"] is True
        assert abs((day(o["date"]) - day(o["fullMoon"])).days) <= 1


def test_each_city_is_reckoned_in_its_own_time():
    out = get(2027, NEW_YORK)
    assert "computedAt" not in out
    (o,) = out["occurrences"]
    assert o["pusam"]["start"].endswith("-05:00") and o["fullMoon"].endswith("-05:00")


def test_the_context_and_the_meta_keep_the_texts_to_what_they_say(meta):
    out = get(2027, PLACES["chennai"])
    assert [(c["text"], c["page"]) for c in out["context"]] == [
        ("South Indian Festivities", "31"),
        ("The Indian Calendar", "12"),
    ]
    assert meta["festivals"]["thaipusam"]["name"] == "Thaipusam"
    rules = meta["festivalRules"]["thaipusam"]
    assert set(rules) == {
        "majority_with_sunrise",
        "majority_sunrise_variant",
        "majority_no_sunrise",
    }
    assert all(
        "our reading of the days kept" in r["name"] and r["source"] is None for r in rules.values()
    )
    note = meta["festivalNotes"]["thaipusam"]
    assert note.startswith(
        "Popular practice. Tai Pusam is kept on the day over which the asterism Pushya"
    )
    assert "p. 31" in note and "Lexicon" not in note and "twoPusam" in note
