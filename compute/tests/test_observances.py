import pytest
from conftest import call
from jyotisha import muhurta as Mu

from astro_compute import observances as O
from astro_compute.meta import EKADASHI_RULES
from astro_compute.models import EkadashiQuery
from astro_compute.timeutil import aware

DELHI = {"year": "2026", "lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}
H = 1 / 24


def test_every_ekadashi_of_the_year_with_both_traditions():
    status, out = call("GET", "/v1/observances/ekadashi", DELHI)
    assert status == 200, out
    rows = out["ekadashis"]
    assert 24 <= len(rows) <= 26
    assert out["source"]["text"] == "Nirnaya-sindhu" and out["source"]["page"] == "49-63"
    dates = [r["smarta"]["date"] for r in rows]
    assert dates == sorted(dates) and all(r["paksha"] in ("shukla", "krishna") for r in rows)
    for r in rows:
        assert r["tithi"]["start"] < r["tithi"]["end"] < r["dvadashiEnd"]
        assert r["differs"] == (r["smarta"]["date"] != r["vaishnava"]["date"])
        assert r["smarta"]["rule"] in EKADASHI_RULES["smarta"]
        assert r["vaishnava"]["rule"] in EKADASHI_RULES["vaishnava"]
        pierced = r["vaishnava"]["rule"] == "arunodaya_pierced"
        assert pierced == r["vaishnava"]["dashamiAtArunodaya"]
        if r["smarta"]["rule"] == "sunrise":
            day = next(d for d in r["days"] if d["date"] == r["smarta"]["date"])
            assert day["tithiAtSunrise"] == "ekadashi"
        assert (r["smarta"]["asceticDate"] is not None) == (
            r["smarta"]["rule"] == "ekadashi_increases"
        )


def _an_ekadashi() -> tuple[float, float, float]:
    """A real Ekadashi's start, end and the end of the Dvadashi after it."""
    edges = Mu._scan(Mu.tithi_at, 2461300.0, 2461340.0, 0.25)
    i = next(i for i, (_, num) in enumerate(edges) if num in O.EKADASHI)
    return edges[i][0], edges[i + 1][0], edges[i + 2][0]


@pytest.mark.parametrize(
    "where, smarta, ascetic, vaishnava",
    [
        # Ekadashi at one sunrise, no Dashami in the 96 minutes before it.
        (
            lambda s, e, d: [s - 2 * H, s + 2 * H, e + H, d + H, d + 25 * H],
            (1, "sunrise"),
            None,
            (1, "pure"),
        ),
        # Dashami 36 minutes into the aruṇodaya: Vaishnavas move to the next day.
        (
            lambda s, e, d: [s - 2 * H, s + H, e + H, d + H, d + 25 * H],
            (1, "sunrise"),
            None,
            (2, "arunodaya_pierced"),
        ),
        # Ekadashi at two sunrises, Dvadashi at none: householders first, ascetics second.
        (
            lambda s, e, d: [s - 2 * H, s + 2 * H, e - H, d + H, d + 25 * H],
            (1, "ekadashi_increases"),
            2,
            (2, "increase"),
        ),
        # Dvadashi at two sunrises: Smartas keep the first day, Vaishnavas the later.
        (
            lambda s, e, d: [s - 2 * H, s + 2 * H, e + H, d - H, d + 23 * H],
            (1, "dvadashi_increases"),
            None,
            (2, "increase"),
        ),
        # Ekadashi at no sunrise, Dvadashi at the next: the next day for both.
        (
            lambda s, e, d: [s - 2 * H, e + H, d + H, d + 25 * H, d + 49 * H],
            (1, "pierced_next_day"),
            None,
            (1, "pierced_next_day"),
        ),
        # No Dvadashi on the next day either: Smartas keep the pierced day.
        (
            lambda s, e, d: [s - 2 * H, d + H, d + 25 * H, d + 49 * H, d + 73 * H],
            (0, "no_dvadashi_next_day"),
            None,
            (1, "pierced_next_day"),
        ),
    ],
)
def test_nirnaya_sindhu_cases(monkeypatch, where, smarta, ascetic, vaishnava):
    start, end, dv_end = _an_ekadashi()
    s = where(start, end, dv_end)
    monkeypatch.setattr(O, "_sunrises", lambda first, lat, lon, n: s)
    row = O._one(start, end, dv_end, EkadashiQuery(year=2026, lat=28.6, lon=77.2, tz="UTC"))
    day = [aware(t, "UTC").date().isoformat() for t in s]
    assert (row["smarta"]["date"], row["smarta"]["rule"]) == (day[smarta[0]], smarta[1])
    assert row["smarta"]["asceticDate"] == (day[ascetic] if ascetic else None)
    assert (row["vaishnava"]["date"], row["vaishnava"]["rule"]) == (day[vaishnava[0]], vaishnava[1])
