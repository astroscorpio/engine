"""0pnf's follow-ups 7.1 and 7.2: the sunset after a sunrise and the sunrise after a sunset are
the first ones, on the shortest days and nights too. The searches started 72 and 14.4 minutes on,
and a longer day or night keeps their answers to the millisecond."""

from jyotisha import ephemeris as E

from astro_compute import festivals, observances
from astro_compute.models import EkadashiQuery

YEAR = 2026
# Tromsø's days shrink below 72 minutes on either side of its polar night; Inta, just inside the
# midnight sun's reach, has nights below 14.4 minutes in some years.
TROMSO = {"lat": 69.6489, "lon": 18.95508, "tz": "Europe/Oslo"}
INTA = {"lat": 66.03169, "lon": 60.16594, "tz": "Europe/Moscow"}
DELHI = {"lat": 28.6139, "lon": 77.2090, "tz": "Asia/Kolkata"}


def _turns(place: dict, years: int = 3) -> list[tuple[float, float, float]]:
    """Each sunrise from YEAR on, the first sunset after it and the first sunrise after that."""
    lat, lon = place["lat"], place["lon"]
    t, end, out = E.jd(YEAR, 1, 1, 0.0, 0.0), E.jd(YEAR + years, 1, 1, 0.0, 0.0), []
    while t < end:
        try:
            sr = E._rise_set(t, lat, lon, True)
            ss = E._rise_set(sr, lat, lon, False)
            nr = E._rise_set(ss, lat, lon, True)
        except RuntimeError:  # polar day or night
            t += 1.0
            continue
        out.append((sr, ss, nr))
        t = nr - 0.001
    return out


def _query(place: dict) -> EkadashiQuery:
    return EkadashiQuery(year=YEAR, **place)


def _old(t: float, q: EkadashiQuery, rising: bool) -> float | None:
    """The old search's answer, or None where it found nothing (the polar day or night begun)."""
    try:
        return E._rise_set(t, q.lat, q.lon, rising)
    except RuntimeError:
        return None


def test_a_day_shorter_than_72_minutes_keeps_its_own_sunset():
    q = _query(TROMSO)
    short = [(sr, ss) for sr, ss, _ in _turns(TROMSO) if ss - sr < 0.05]
    assert short
    for sr, ss in short:
        assert observances._sunset(sr, q) == ss
        assert festivals._night(sr, q)[0] == ss
        # The old search went on to the next day's sunset, or found none.
        old = _old(sr + 0.05, q, False)
        assert old is None or old - ss > 0.5


def test_a_night_shorter_than_14_minutes_keeps_its_own_sunrise():
    q = _query(INTA)
    short = [sr for sr, ss, nr in _turns(INTA) if nr - ss < 0.01]
    assert short
    for sr in short:
        ss = observances._sunset(sr, q)
        nr = E._rise_set(ss, q.lat, q.lon, True)
        assert nr - ss < 0.01
        assert festivals._night(sr, q) == (ss, nr)
        assert observances._pradosha_window(sr, q) == (ss, ss + 3 * (nr - ss) / 15)
        assert observances._night_parts(sr, q)[0] == (ss, ss + 3 * (nr - ss) / 15)
        old = _old(ss + 0.01, q, True)
        assert old is None or old - nr > 0.5


def test_longer_days_and_nights_keep_the_old_searches():
    for place in (DELHI, TROMSO, INTA):
        q = _query(place)
        for sr, ss, nr in _turns(place, 1)[::5]:
            if ss - sr < 0.05 or nr - ss < 0.01:
                continue
            old = E._rise_set(sr + 0.05, q.lat, q.lon, False)
            assert observances._sunset(sr, q) == old
            assert festivals._night(sr, q) == (old, E._rise_set(old + 0.01, q.lat, q.lon, True))
