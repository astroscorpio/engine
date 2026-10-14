from __future__ import annotations

import json

import pytest

from jyotisha import panchanga, reading, sbc
from jyotisha.ashtakavarga import bhinna
from jyotisha.ephemeris import parse
from jyotisha.storage import RESOURCE_DATA
from jyotisha.subjects import EXAMPLE
from jyotisha.vargas import SHODASHAVARGA


def test_bhinna_canonical_totals() -> None:
    totals = {name: sum(values) for name, values in bhinna(EXAMPLE.chart()).items()}
    assert totals == {
        "Sun": 48,
        "Moon": 49,
        "Mars": 39,
        "Mercury": 54,
        "Jupiter": 56,
        "Venus": 52,
        "Saturn": 39,
    }
    assert sum(totals.values()) == 337


def test_all_shodashavarga_charts_are_bounded() -> None:
    chart = EXAMPLE.chart()
    for division in SHODASHAVARGA:
        divided = chart.d(division)
        assert 0 <= divided.asc.longitude < 360
        assert all(0 <= position.longitude < 360 for position in divided.grahas.values())


def test_sbc_independent_spec() -> None:
    path = RESOURCE_DATA / "sbc_spec.json"
    if not path.exists():  # the reference workbook's tables are not redistributed
        pytest.skip("sbc_spec.json (third-party reference tables) is not present")
    spec = json.loads(path.read_text(encoding="utf-8"))
    assert sbc.validate(spec) == []


def test_horas_split_daylight_and_night_into_twelve() -> None:
    natal = panchanga.compute(
        EXAMPLE.jd,
        EXAMPLE.lat,
        EXAMPLE.lon,
    )
    day_midpoint = panchanga.compute(
        (natal.sunrise + natal.sunset) / 2 + 1 / 86_400,
        EXAMPLE.lat,
        EXAMPLE.lon,
    )
    night_start = panchanga.compute(
        natal.sunset + 1 / 86_400,
        EXAMPLE.lat,
        EXAMPLE.lon,
    )
    start = panchanga.CHALDEAN.index(natal.vara)
    assert day_midpoint.hora_lord == panchanga.CHALDEAN[(start + 6) % 7]
    assert night_start.hora_lord == panchanga.CHALDEAN[(start + 12) % 7]


def test_current_rare_timings_use_observer_location() -> None:
    context = EXAMPLE.observer_context
    payload = reading.everything(
        EXAMPLE.chart(),
        parse("2026-07-29", context.timezone),
        context.timezone,
        observer_lat=context.lat,
        observer_lon=context.lon,
    )
    assert payload["rare"]["chogadiya"][0][1] == payload["panchanga"]["sunrise"]
