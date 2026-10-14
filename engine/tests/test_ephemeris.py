from __future__ import annotations

import pytest

from jyotisha.ephemeris import backend_info, fmt, parse
from jyotisha.subjects import EXAMPLE


def test_natal_positions_golden() -> None:
    # Swiss Ephemeris data files (sepl_18/semo_18, DE441). Under the built-in
    # Moshier fallback the Moon differs by about 0.6" and these fail.
    assert backend_info()["actual"] == "swiss-files", "set SE_EPHE_PATH (scripts/fetch_ephe.sh)"
    chart = EXAMPLE.chart()
    expected = {
        "Sun": 275.467092115,
        "Moon": 218.701853256,
        "Mars": 201.647511149,
        "Mercury": 290.612653624,
        "Jupiter": 37.382392892,
        "Venus": 322.545625115,
        "Saturn": 30.222373107,
        "Rahu": 81.631042279,
        "Ketu": 261.631042279,
    }
    assert chart.asc.longitude == pytest.approx(45.204993017, abs=1e-8)
    for name, longitude in expected.items():
        assert chart.grahas[name].longitude == pytest.approx(longitude, abs=1e-8)


def test_iana_timezone_handles_dst_transition() -> None:
    before = parse("2026-03-29 01:30", "Europe/Paris")
    after = parse("2026-03-29 03:30", "Europe/Paris")
    assert (after - before) * 24 == pytest.approx(1.0, abs=1e-7)


def test_exact_midnight_round_trip() -> None:
    value = parse("2026-07-29 00:00", "Europe/Paris")
    assert fmt(value, "Europe/Paris", True) == "29 Jul 2026 00:00"


def test_invalid_dst_wall_times_require_an_explicit_offset() -> None:
    with pytest.raises(ValueError, match="nonexistent local time"):
        parse("2026-03-29 02:30", "Europe/Paris")
    with pytest.raises(ValueError, match="ambiguous local time"):
        parse("2026-10-25 02:30", "Europe/Paris")
    assert parse("2026-10-25T02:30:00+01:00") != parse("2026-10-25T02:30:00+02:00")
