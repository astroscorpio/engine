import datetime as dt

from conftest import DELHI, call

from astro_compute.meta import PANCAKA_BARRED, PANCAKA_NAMES, PANCAKA_NOTES
from astro_compute.pancaka import BARRED, POPULAR_NAMES

LONDON = {"lat": "51.5074", "lon": "-0.1278", "tz": "Europe/London"}


def _spans(year, place=DELHI):
    status, out = call("GET", "/v1/observances/pancaka", {**place, "year": str(year)})
    assert status == 200, out
    assert out["barred"] == list(BARRED)
    return {s["start"][:16]: s for s in out["spans"]}


def test_spans_run_from_kumbha_to_the_end_of_mina():
    """pancaka.md s1: the Moon's entry into sidereal Kumbha to its exit from Mina."""
    t = [(dt.datetime.fromisoformat(s["start"]), dt.datetime.fromisoformat(s["end"]))
         for s in _spans(2026).values()]  # fmt: skip
    assert len(t) == 13
    assert all(a[1] < b[0] for a, b in zip(t, t[1:], strict=False))
    hours = [(b - a).total_seconds() / 3600 for a, b in t]
    assert all(90 <= h <= 126 for h in hours), hours  # 60 degrees of the Moon: four to five days


def test_weekday_names_follow_the_vara_at_the_start():
    """The lead, 17 Oct 2026: popular names by the vara the pancaka begins on, sunrise to
    sunrise; the 2025 news reports give Friday 31 Oct 06:48 as cora, and a Wednesday start
    on 24 Dec with no name."""
    y25 = _spans(2025)
    s = y25["2025-10-31T06:48"]
    assert (s["startVara"], s["nameId"], s["nameBasis"]) == ("friday", "cora", "popular_practice")
    assert s["end"][:16] == "2025-11-04T12:34"
    s = y25["2025-12-24T19:46"]
    assert (s["startVara"], s["nameId"], s["nameBasis"]) == ("wednesday", None, None)
    # 02:40 on Saturday 1 Jan 2028 is before sunrise, so Friday's vara.
    s = _spans(2028)["2028-01-01T02:40"]
    assert (s["startVara"], s["nameId"]) == ("friday", "cora")
    assert {s["nameId"] for s in y25.values()} == set(PANCAKA_NAMES) | {None}


def test_a_span_across_the_year_end_is_in_both_years():
    first = "2027-12-31T21:10"
    assert first in _spans(2027, LONDON) and first in _spans(2028, LONDON)
    assert _spans(2027, LONDON)[first]["end"][:16] == "2028-01-05T21:01"
    assert "2028-01-01T02:40" not in _spans(2027)  # Delhi: it starts after the year ends


def test_meta_names_every_id():
    assert set(POPULAR_NAMES.values()) == set(PANCAKA_NAMES)
    assert set(BARRED) == set(PANCAKA_BARRED)
    assert set(POPULAR_NAMES) == {"sunday", "monday", "tuesday", "friday", "saturday"}
    label = "Popular practice; the texts read give the Dhanishtha-panchaka no weekday names"
    assert PANCAKA_NOTES["popular_names"] == label
    assert PANCAKA_BARRED["pillars"][1] == "Dharmasindhu p. 242"
