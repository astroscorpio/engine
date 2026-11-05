"""0pnf's follow-up to 7.3: where clocks change at midnight, the muhurta and gochara searches, the
couple search's partner with no birth time and the chart with none take the date's first instant
(and its last), as the panchang has since 0pnf; and Sawan Somvar's season starts and ends the
same way. The dates are found from the zone rules, so each test follows the years it covers."""

import datetime as dt
from zoneinfo import ZoneInfo

from conftest import call
from jyotisha.ephemeris import positions

from astro_compute.timeutil import day_end, day_start, iso

YEARS = range(2026, 2029)
HAVANA = {"lat": 23.13302, "lon": -82.38304, "tz": "America/Havana"}
CAIRO = {"lat": 30.06263, "lon": 31.24967, "tz": "Africa/Cairo"}
AZORES = {"lat": 37.73952, "lon": -25.66874, "tz": "Atlantic/Azores"}


def _clock_changes(tz: str, hour: int, minute: int, second: int = 0) -> dict[str, list[dt.date]]:
    """The dates in YEARS whose clock time is missing (clocks went forward) or doubled."""
    z, out = ZoneInfo(tz), {"missing": [], "doubled": []}
    d = dt.date(YEARS[0], 1, 1)
    while d.year <= YEARS[-1]:
        a = dt.datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=z)
        if a.utcoffset() != a.replace(fold=1).utcoffset():
            back = a.astimezone(dt.UTC).astimezone(z).replace(tzinfo=None) == a.replace(tzinfo=None)
            out["doubled" if back else "missing"].append(d)
        d += dt.timedelta(days=1)
    return out


def _midnights(tz: str) -> list[dt.date]:
    found = _clock_changes(tz, 0, 0)
    assert found["missing"] and found["doubled"]
    return found["missing"] + found["doubled"]


def _first(d: dt.date, tz: str) -> str:
    return iso(day_start(d, tz), tz)


def _q(place: dict) -> dict:
    return {k: str(v) for k, v in place.items()}


def test_muhurta_searches_from_and_to_a_changed_midnight():
    tz = HAVANA["tz"]
    for d in _midnights(tz):
        after = {
            **_q(HAVANA),
            "act": "general",
            "from": d.isoformat(),
            "until": (d + dt.timedelta(days=2)).isoformat(),
        }
        status, out = call("GET", "/v1/muhurta", after)
        assert status == 200, out
        assert out["from"] == _first(d, tz)
        before = {
            **after,
            "from": (d - dt.timedelta(days=3)).isoformat(),
            "until": (d - dt.timedelta(days=1)).isoformat(),
        }
        status, out = call("GET", "/v1/muhurta", before)
        assert status == 200, out
        assert out["until"] == _first(d, tz)


def test_gochara_from_and_to_a_changed_midnight():
    tz = HAVANA["tz"]
    for d in _midnights(tz):
        q = {
            "moonSign": "aries",
            "start": d.isoformat(),
            "end": (d + dt.timedelta(days=2)).isoformat(),
            "tz": tz,
        }
        status, out = call("GET", "/v1/gochara", q)
        assert status == 200, out
        assert out["segments"][0]["start"] == _first(d, tz)
        q = {
            **q,
            "start": (d - dt.timedelta(days=3)).isoformat(),
            "end": (d - dt.timedelta(days=1)).isoformat(),
        }
        status, out = call("GET", "/v1/gochara", q)
        assert status == 200, out
        assert out["segments"][-1]["end"] == _first(d, tz)


def test_couple_search_with_a_partner_born_on_a_changed_date_and_no_time():
    # Havana's midnights, and Cairo's 23:59:58, doubled when its clocks go back at 24:00.
    late = _clock_changes(CAIRO["tz"], 23, 59, 58)["doubled"]
    assert late
    for place, days in ((HAVANA, _midnights(HAVANA["tz"])), (CAIRO, late)):
        for d in days:
            bride = {"date": d.isoformat(), "timeUnknown": True, "place": place}
            span = {
                "from": (d + dt.timedelta(days=30)).isoformat(),
                "until": (d + dt.timedelta(days=90)).isoformat(),
            }
            body = {**span, **place, "bride": bride, "groom": {"nakshatra": "hasta", "pada": 1}}
            status, out = call("POST", "/v1/muhurat/vivah/personal", body=body)
            assert status == 200, out


def test_a_chart_with_no_time_on_a_changed_date_reads_the_civil_day():
    cases = [(HAVANA, d) for d in _midnights(HAVANA["tz"])]
    cases += [(CAIRO, d) for d in _clock_changes(CAIRO["tz"], 23, 59, 58)["doubled"]]
    for place, d in cases:
        body = {"date": d.isoformat(), "timeUnknown": True, "place": place}
        status, out = call("POST", "/v1/chart", body=body)
        assert status == 200, out
        a = positions(day_start(d, place["tz"]), "lahiri", "true")["Moon"]
        b = positions(day_end(d, place["tz"]), "lahiri", "true")["Moon"]
        assert out["flags"]["moonSignUncertain"] == (a.sign != b.sign)
        assert out["flags"]["moonNakshatraUncertain"] == (a.nakshatra != b.nakshatra)


def test_sawan_somvar_where_its_season_starts_or_ends_on_a_changed_midnight():
    z = ZoneInfo(AZORES["tz"])
    years = [
        y
        for y in range(YEARS[0], YEARS[0] + 10)
        for m, d in ((6, 1), (10, 31))
        if dt.datetime(y, m, d, tzinfo=z).utcoffset()
        != dt.datetime(y, m, d, tzinfo=z, fold=1).utcoffset()
    ]
    assert years
    for y in years:
        status, out = call("GET", "/v1/festivals/sawan-somvar", {"year": str(y), **_q(AZORES)})
        assert status == 200, out
        assert out["occurrences"]
