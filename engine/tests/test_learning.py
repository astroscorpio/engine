from __future__ import annotations

import numpy as np
import pytest

from jyotisha import learn
from jyotisha.ephemeris import parse, to_datetime
from jyotisha.subjects import EXAMPLE


def test_windows_never_cross_cutoff() -> None:
    start = parse("2019-01-01", "Europe/Paris")
    cutoff = parse("2026-07-26", "Europe/Paris")
    result = learn.windows(start, cutoff)
    assert result[-1][1] <= cutoff
    assert cutoff - result[-1][1] < learn.WINDOW_DAYS


def test_civil_windows_keep_local_midnight_across_dst() -> None:
    zone = "Europe/Paris"
    start = parse("2026-10-18", zone, date_hour=0)
    end = parse("2026-11-15", zone, date_hour=0)
    result = learn.windows(start, end, timezone=zone)
    assert len(result) == 2
    boundaries = [result[0][0], result[0][1], result[1][1]]
    local = [to_datetime(value, zone) for value in boundaries]
    assert [value.date().isoformat() for value in local] == [
        "2026-10-18",
        "2026-11-01",
        "2026-11-15",
    ]
    assert all(value.hour == 0 for value in local)
    assert (result[0][1] - result[0][0]) * 24 == pytest.approx(337)
    assert (result[1][1] - result[1][0]) * 24 == pytest.approx(336)


def test_future_civil_windows_match_training_grid() -> None:
    zone = "Europe/Paris"
    start = parse("2026-03-22", zone, date_hour=0)
    result = learn.future_windows(start, 2, timezone=zone)
    local = [to_datetime(result[0][0], zone), to_datetime(result[0][1], zone)]
    assert [value.isoformat() for value in local] == [
        "2026-03-22T00:00:00+01:00",
        "2026-04-05T00:00:00+02:00",
    ]
    assert (result[0][1] - result[0][0]) * 24 == pytest.approx(335)


def test_fitted_scaler_is_horizon_invariant() -> None:
    history = np.array([[0.0, 10.0], [1.0, 11.0], [2.0, 12.0]])
    first = np.array([[3.0, 13.0]])
    two = np.array([[3.0, 13.0], [100.0, -50.0]])
    scaler = learn.Standardizer().fit(history)
    assert scaler.transform(first)[0] == pytest.approx(scaler.transform(two)[0])


def test_labels_drop_contaminated_imprecise_and_trivial_events() -> None:
    wins = learn.windows(
        parse("2024-03-01", EXAMPLE.birth_zone),
        parse("2024-04-15", EXAMPLE.birth_zone),
    )
    career = learn.label(EXAMPLE, wins, "career", min_magnitude=2)
    home = learn.label(EXAMPLE, wins, "home", min_magnitude=2)
    assert career.sum() == 0  # side-project month contaminated; panel invite is a notification
    assert home.sum() == 1  # the flat move; the magnitude-1 leak is excluded


def test_hac_reports_descriptive_gain_but_no_inference_below_three() -> None:
    gain, z_score, p_value = learn.hac_one_sided(np.array([0.2, 0.4]))
    assert gain == pytest.approx(0.3)
    assert z_score == 0.0
    assert p_value == 1.0
