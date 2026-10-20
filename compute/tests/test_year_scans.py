"""The year lists' scans made cheaper without changing a value (the lead's latency plan): the
Moon-pada scan reads the Moon alone, and each lunar month's new moons are searched once."""

import datetime as dt

import swisseph as swe
from conftest import AT, DELHI
from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries, moon_longitude, positions

from astro_compute.models import EkadashiQuery
from astro_compute.observances import _edges
from astro_compute.vivah import _month


def _jd(at: str) -> float:
    t = dt.datetime.fromisoformat(at).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def test_moon_longitude_is_the_luminaries_moon_to_the_bit():
    t0 = _jd(AT)
    for i in range(300):
        t = t0 + i * 0.37
        first = moon_longitude(t)
        assert first == luminaries(t)[1].longitude == moon_longitude(t), t


def _month_before(jd: float, ay: str, cache: dict) -> tuple:
    """_month as it was: a new-moon search for every call."""
    lm = Mu.lunar_month(jd, ay)
    key = round(lm.start, 4)
    if key not in cache:
        a = positions(lm.start, ay)["Sun"].sign
        b = positions(lm.end, ay)["Sun"].sign
        cache[key] = (lm.name, lm.adhika, (b - a) % 12 == 2, lm.start)
    return cache[key]


def test_month_searches_each_lunation_once_and_returns_the_same(monkeypatch):
    year = dt.datetime.fromisoformat(AT).year
    q = EkadashiQuery(year=year, lat=float(DELHI["lat"]), lon=float(DELHI["lon"]), tz=DELHI["tz"])
    edges = _edges(q)[:61]
    mids = [(a + b) / 2 for (a, _), (b, _) in zip(edges, edges[1:], strict=False)]
    before: dict = {}
    expected = [_month_before(m, q.ayanamsa, before) for m in mids]
    calls = []
    search = Mu.lunar_month
    monkeypatch.setattr(Mu, "lunar_month", lambda jd, ay: calls.append(jd) or search(jd, ay))
    cache: dict = {}
    assert [_month(m, q.ayanamsa, cache) for m in mids] == expected
    assert len(calls) <= 3
