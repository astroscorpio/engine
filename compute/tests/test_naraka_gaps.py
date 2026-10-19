"""Research's check on the Naraka bath (festivals.md, "Backend check on s10") and the lead's
decision 46, 18 Oct 2026, at research's 17 places: the bath when the Caturdashi holds no sunrise,
over the 15 city-years that put it after the Lakshmi Puja, and no eve row in the 22 city-years
where neither Naraka row falls on the eve. No date is written here."""

import datetime as dt

from conftest import call

PLACES = {
    "pune": ("18.51957", "73.85535", "Asia/Kolkata"),
    "patna": ("25.59408", "85.13563", "Asia/Kolkata"),
    "chennai": ("13.08784", "80.27847", "Asia/Kolkata"),
    "lucknow": ("26.83928", "80.92313", "Asia/Kolkata"),
    "jaipur": ("26.91962", "75.78781", "Asia/Kolkata"),
    "hyderabad": ("17.38405", "78.45636", "Asia/Kolkata"),
    "delhi": ("28.65195", "77.23149", "Asia/Kolkata"),
    "kolkata": ("22.56263", "88.36304", "Asia/Kolkata"),
    "mumbai": ("19.07283", "72.88261", "Asia/Kolkata"),
    "bengaluru": ("12.97194", "77.59369", "Asia/Kolkata"),
    "ahmedabad": ("23.02579", "72.58727", "Asia/Kolkata"),
    "sydney": ("-33.86785", "151.20732", "Australia/Sydney"),
    "dubai": ("25.07725", "55.30927", "Asia/Dubai"),
    "new-york-city": ("40.71427", "-74.00597", "America/New_York"),
    "toronto": ("43.70643", "-79.39864", "America/Toronto"),
}
INDIA = [slug for slug, p in PLACES.items() if p[2] == "Asia/Kolkata"]
NO_SUNRISE = [
    (2029, "new-york-city"),
    (2029, "toronto"),
    *((2030, slug) for slug in INDIA),
    (2038, "new-york-city"),
    (2039, "new-york-city"),
]
GAPS = [
    (2027, "dubai"),
    (2029, "sydney"),
    (2030, "new-york-city"),
    (2030, "toronto"),
    (2031, "kolkata"),
    (2033, "dubai"),
    *((2036, slug) for slug in INDIA if slug != "kolkata"),
    (2036, "dubai"),
    (2037, "dubai"),
    (2037, "sydney"),
    (2038, "sydney"),
    (2039, "sydney"),
    (2039, "toronto"),
]


def dipavali(year: int, slug: str) -> dict:
    lat, lon, tz = PLACES[slug]
    query = {"year": str(year), "lat": lat, "lon": lon, "tz": tz}
    status, out = call("GET", "/v1/festivals/dipavali", query)
    assert status == 200, out
    (occ,) = out["occurrences"]
    return occ


def next_day(date: str) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()


def at(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)  # aware, so instants across a DST change compare


def test_bath_when_the_caturdashi_holds_no_sunrise():
    """DS p. 77: a Caturdashi that begins after one sunrise and ends before the next dawn's
    moonrise has its bath at that dawn, never after the Lakshmi Puja. In India 2030 that is the
    Lakshmi Puja day, and the Divodasiya's lamps fall on the eve."""
    assert len(NO_SUNRISE) == 15
    for year, slug in NO_SUNRISE:
        occ = dipavali(year, slug)
        n, lakshmi = occ["set"]["narakaChaturdashi"], occ["set"]["lakshmiPuja"]["date"]
        assert n["rule"] == "naraka_no_sunrise_next_dawn", (year, slug, n["rule"])
        assert n["date"] == next_day(n["tithi"]["start"][:10]) <= lakshmi, (year, slug)
        bath = [at(n["abhyangaSnana"][k]) for k in ("start", "end")]
        assert at(n["tithi"]["end"]) <= bath[0] < bath[1], (year, slug)
        if slug in INDIA:
            assert n["date"] == lakshmi and occ["eveRow"] == "lampsVariant", (year, slug)


def test_no_eve_row_in_the_gap_years():
    """Decision 46: when the bath falls on the Lakshmi Puja day and the Caturdashi misses the
    eve's pradosha, neither Naraka row is the eve, and eveRow is null (no Choti Diwali label)."""
    assert len(GAPS) == 22
    for year, slug in GAPS:
        occ = dipavali(year, slug)
        n, lakshmi = occ["set"]["narakaChaturdashi"], occ["set"]["lakshmiPuja"]["date"]
        assert n["date"] == lakshmi and n["lampsVariant"] is None, (year, slug)
        assert occ["eveRow"] is None, (year, slug)
