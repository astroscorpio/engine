"""The new year's day in an adhika Caitra (festivals.md s14; research's 0md audit, finding 1).
DS p. 31 puts the new year's bath and sankalpa on the adhika month's Pratipada, by the new year's
own rule, and keeps the flag, neem, forecast and Navaratri in the nija month. chaitra-navaratri's
newYear carries that day as a labelled variant, in cheti-chand's form (decision 37), and nothing
else in the answer moves. Each day is checked against the panchang's own tithi at sunrise and
month; no date is written here."""

import datetime as dt

import pytest
from conftest import call

from astro_compute.meta import FESTIVAL_CAUTIONS

PLACES = {
    "delhi": {"lat": "28.65195", "lon": "77.23149", "tz": "Asia/Kolkata"},
    "london": {"lat": "51.50853", "lon": "-0.12574", "tz": "Europe/London"},
    "new-york-city": {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"},
}
# Lahiri's one adhika Caitra in 2026-2040, and the adhika day's weekday at each place (0md).
ADHIKA = {2029: {"delhi": "friday", "london": "thursday", "new-york-city": "thursday"}}


def get(path: str, query: dict) -> dict:
    status, out = call("GET", path, query)
    assert status == 200, out
    return out


def new_year(y: int, place: dict, **extra: str) -> dict:
    (o,) = get("/v1/festivals/chaitra-navaratri", {"year": str(y), **place, **extra})["occurrences"]
    assert o["lunarMonth"] == {"amanta": "chaitra", "purnimanta": "chaitra", "adhika": False}
    assert o["newYearDate"] == o["newYear"]["date"]
    return o["newYear"]


def the_adhika_pratipadas_day(v: dict, place: dict, **extra: str) -> None:
    """DS p. 31's day for the adhika Pratipada: the first sunrise it holds; holding none, the day
    it falls on, with the Amavasya at that day's sunrise and the adhika Dvitiya at the next."""

    def at(shift: int) -> dict:
        d = dt.date.fromisoformat(v["date"]) + dt.timedelta(days=shift)
        return get("/v1/panchang", {"date": d.isoformat(), **place, **extra})

    day, adhika = at(0), {"amanta": "chaitra", "purnimanta": "chaitra", "adhika": True}
    assert day["vara"]["id"] == v["vara"]
    if day["tithi"]["num"] == 1:
        assert day["tithi"]["paksha"] == "shukla" and day["lunarMonth"] == adhika
        assert at(-1)["tithi"]["num"] != 1
    else:
        after = at(1)
        assert day["tithi"]["num"] == 30 and after["tithi"]["num"] == 2
        assert after["lunarMonth"] == adhika


@pytest.mark.parametrize("y", range(2026, 2041))
@pytest.mark.parametrize("city", sorted(PLACES))
def test_the_adhika_day_comes_only_in_an_adhika_caitra(city, y):
    ny = new_year(y, PLACES[city])
    if y not in ADHIKA:
        assert "variants" not in ny
        return
    (v,) = ny["variants"]
    assert v["reason"] == "adhika_new_year" and v["vara"] == ADHIKA[y][city]
    assert v["date"] < ny["date"]
    the_adhika_pratipadas_day(v, PLACES[city])


def test_the_month_is_the_one_the_ayanamsa_asked_gives():
    # Raman's reckoning has an adhika Caitra in 2040; Lahiri's has none. Its Pratipada holds no
    # sunrise at New Delhi, so the day it falls on.
    assert "variants" not in new_year(2040, PLACES["delhi"])
    (v,) = new_year(2040, PLACES["delhi"], ayanamsa="raman")["variants"]
    the_adhika_pratipadas_day(v, PLACES["delhi"], ayanamsa="raman")


def test_the_label_keeps_to_ds_p31(meta):
    label = FESTIVAL_CAUTIONS["adhika_new_year"]
    assert "bath and sankalpa" in label and label.endswith("(Dharmasindhu p. 31)")
    assert "popular practice" not in label and meta["festivalCautions"]["adhika_new_year"] == label
