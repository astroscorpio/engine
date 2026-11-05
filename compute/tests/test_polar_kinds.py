"""The polar 500s (0pnf's follow-ups, found while building): where a day a kind needs has no
sunrise, in the polar night or the midnight sun, the kind answers its 422 unsupported_location, as
the others do; where every day it needs has one, it answers. Before, a sunrise search that found
none ended in a 500."""

import datetime as dt

import pytest
from conftest import call

from astro_compute import festivals, sankranti
from astro_compute.models import EkadashiQuery

TROMSO = {"lat": 69.6489, "lon": 18.95508, "tz": "Europe/Oslo"}
INTA = {"lat": 66.03169, "lon": 60.16594, "tz": "Europe/Moscow"}
LONGYEARBYEN = {"lat": 78.22334, "lon": 15.64689, "tz": "Arctic/Longyearbyen"}


def _q(place: dict, year: int) -> dict:
    return {"year": str(year), **{k: str(v) for k, v in place.items()}}


@pytest.mark.parametrize(
    "path, place, year",
    [
        ("/v1/observances/sankranti", TROMSO, 2026),  # Makara, 14 January, in the polar night
        ("/v1/observances/pancaka", TROMSO, 2026),  # a run begun in the midnight sun
        ("/v1/muhurat/vehicle", INTA, 2026),  # the midnight sun, 16 to 26 June
        ("/v1/muhurat/property", INTA, 2026),
        ("/v1/eclipses", LONGYEARBYEN, 2026),  # 12 August's eclipse, in the midnight sun
        ("/v1/festivals/thaipusam", TROMSO, 2027),  # Tai begins in the polar night
        ("/v1/festivals/onam", LONGYEARBYEN, 2026),  # Chingam begins in the midnight sun
        ("/v1/festivals/sawan-somvar", TROMSO, 2027),  # Shravana begins in it
    ],
    ids=["sankranti", "pancaka", "vehicle", "property", "eclipses", "thaipusam", "onam", "sawan"],
)
def test_a_needed_day_without_a_sunrise_is_the_kinds_own_422(path, place, year):
    status, out = call("GET", path, _q(place, year))
    assert status == 422
    assert out["error"]["code"] == "unsupported_location"


def test_vishwakarma_puja_reckons_the_kanya_ingress_alone():
    q = EkadashiQuery(year=2026, **TROMSO)
    status, out = call("GET", "/v1/festivals/vishwakarma-puja", _q(TROMSO, 2026))
    assert status == 200
    ((t, sign),) = [(t, s) for t, s in sankranti._ingresses(q) if s == festivals.VIRGO]
    r = sankranti._one(t, sign, q)
    assert [(o["date"], o["sankranti"]) for o in out["occurrences"]] == [
        (r["date"], {k: r[k] for k in ("at", "rule", "punyakala")})
    ]
    # The year's other ingresses include ones in the polar night and the midnight sun.
    assert call("GET", "/v1/observances/sankranti", _q(TROMSO, 2026))[0] == 422


def test_onam_counts_from_the_first_sunrise_after_the_midnight_sun(monkeypatch):
    # Tromsø's midnight sun lasts to 24 July 2026; Chingam begins on 17 August.
    status, out = call("GET", "/v1/festivals/onam", _q(TROMSO, 2026))
    assert status == 200
    assert len(out["occurrences"]) == 1
    real = festivals.local_jd

    def later(day, hours, zone, field):  # the scan starts on 1 August, past the midnight sun
        return real(dt.date(2026, 8, 1) if day == dt.date(2026, 7, 15) else day, hours, zone, field)

    monkeypatch.setattr(festivals, "local_jd", later)
    rows, extra = festivals._onam(EkadashiQuery(year=2026, **TROMSO))
    assert out["occurrences"] == rows
    assert out["chingam"] == extra["chingam"]


def test_sawan_somvar_steps_over_a_midnight_sun_before_shravana(monkeypatch):
    # Purnimanta Shravana begins on 29 July 2026, after Tromsø's midnight sun.
    status, out = call("GET", "/v1/festivals/sawan-somvar", _q(TROMSO, 2026))
    assert status == 200
    assert out["occurrences"]
    real = festivals.day_start

    def later(day, zone):  # the walk starts on 27 July, past the midnight sun
        return real(dt.date(2026, 7, 27) if day == dt.date(2026, 6, 1) else day, zone)

    monkeypatch.setattr(festivals, "day_start", later)
    rows, months = festivals._sawan(EkadashiQuery(year=2026, **TROMSO))
    assert out["occurrences"] == rows
    assert out["shravana"] == months
