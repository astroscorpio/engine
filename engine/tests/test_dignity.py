"""Dignity, benefic status and the dignity parts of shadbala against BPHS (1939 ed.)."""

from __future__ import annotations

import pytest

from jyotisha import strength as S
from jyotisha.chart import Chart
from jyotisha.ephemeris import Position


def make(lagna: int = 0, **lons: float) -> Chart:
    """Grahas at the given sidereal longitudes; the rest out of the way."""
    base = {"Sun": 200.0, "Moon": 320.0, "Mars": 50.0, "Mercury": 215.0, "Jupiter": 110.0,
            "Venus": 230.0, "Saturn": 290.0, "Rahu": 140.0, "Ketu": 320.0}  # fmt: skip
    base |= lons
    grahas = {g: Position(g, lon, 1.0) for g, lon in base.items()}
    return Chart(
        jd=2451545.0, lat=0.0, lon=0.0, grahas=grahas, asc=Position("Ascendant", lagna * 30 + 1.0)
    )


@pytest.mark.parametrize(
    "graha, lon, dignity",
    [
        # BPHS 3.52-53: the Moon exalted to 3 degrees of Taurus, then mulatrikona.
        ("Moon", 32.0, "exalted"),
        ("Moon", 33.5, "moolatrikona"),
        # Mercury exalted to 15 degrees of Virgo, mulatrikona to 20, then own sign.
        ("Mercury", 160.0, "exalted"),
        ("Mercury", 165.0, "moolatrikona"),
        ("Mercury", 172.0, "own"),
        ("Sun", 125.0, "moolatrikona"),  # Leo 5
        ("Sun", 145.0, "own"),  # Leo 25
        # Rahu and Ketu, BPHS Dasa-phala vv. 35-36; otherwise no dignity at all.
        ("Rahu", 45.0, "exalted"),
        ("Rahu", 75.0, "moolatrikona"),
        ("Rahu", 315.0, "own"),
        ("Rahu", 225.0, "debilitated"),
        ("Rahu", 135.0, None),
        ("Ketu", 225.0, "exalted"),
        ("Ketu", 255.0, "moolatrikona"),
        ("Ketu", 45.0, "debilitated"),
        ("Ketu", 345.0, None),
    ],
)
def test_dignity(graha, lon, dignity):
    assert make(**{graha: lon}).dignity(graha) == dignity


@pytest.mark.parametrize(
    "elongation, benefic",
    [(95.0, False), (97.0, True), (263.0, True), (265.0, False), (180.0, True), (5.0, False)],
)
def test_the_moon_is_a_benefic_in_tithis_9_to_22(elongation, benefic):
    # BJ 2.5, 1912 note: waning from the 8th of the dark half to the 8th of the bright.
    assert make(Sun=0.0, Moon=elongation).is_benefic("Moon") is benefic


def test_mercury_turns_malefic_only_joined_with_a_malefic():
    # BPHS 3.11: "papah papayuto budhah".
    assert make(Mercury=215.0, Venus=220.0, Sun=100.0).is_benefic("Mercury")
    assert make(Mercury=215.0, Moon=220.0, Sun=100.0).is_benefic("Mercury")  # waxing Moon
    assert not make(Mercury=215.0, Sun=225.0).is_benefic("Mercury")
    assert not make(Mercury=215.0, Rahu=218.0, Sun=100.0).is_benefic("Mercury")


def test_bphs_28_dignity_values_and_required_totals():
    assert S.DIGNITY_VIRUPAS == {
        "moolatrikona": 45.0, "own": 30.0, "great friend": 20.0, "friend": 15.0,
        "neutral": 10.0, "enemy": 4.0, "great enemy": 2.0,
    }  # fmt: skip
    assert S.REQUIRED_RUPAS == {
        "Sun": 6.5, "Moon": 6.0, "Mars": 5.0, "Mercury": 7.0, "Jupiter": 6.5, "Venus": 5.5,
        "Saturn": 5.0,
    }  # fmt: skip
    c = make()
    assert S._dignity_in(4, 25.0, "Sun", c) == "own"  # Leo 25: past the mulatrikona span
    assert S._dignity_in(4, 10.0, "Sun", c) == "moolatrikona"
    assert S._dignity_in(0, 10.0, "Sun", c) not in ("exalted", "moolatrikona", "own")


def test_paksha_bala_benefic_group_and_the_moon_counted_twice():
    # BPHS 28.10-11: distance / 3 for the Moon, Mercury, Venus, Jupiter; 60 less for the rest.
    c = make(Sun=0.0, Moon=30.0, Mercury=10.0)
    assert S.paksha_bala(c, "Moon") == pytest.approx(10.0)
    assert S.paksha_bala(c, "Mercury") == pytest.approx(10.0)
    assert S.paksha_bala(c, "Saturn") == pytest.approx(50.0)
    # 28.18: the Moon's chesta bala is its paksha bala, not a further multiple.
    assert S.chesta_bala(c, "Moon", 0.0, S.paksha_bala(c, "Moon")) == pytest.approx(10.0)
