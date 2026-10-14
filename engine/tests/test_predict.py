from __future__ import annotations

import datetime as dt

import pytest

from jyotisha import hypotheses, predict
from jyotisha.subjects import EXAMPLE


@pytest.fixture(scope="module")
def readings():
    return predict.read(
        EXAMPLE,
        "career",
        dt.date(2026, 8, 5),
        dt.date(2026, 11, 11),
        timezone="Europe/Paris",
    )


def test_read_covers_the_requested_range(readings) -> None:
    assert readings
    assert readings[0].start == dt.date(2026, 8, 5)
    assert readings[-1].end <= dt.date(2026, 11, 11) + dt.timedelta(days=14)
    for earlier, later in zip(readings, readings[1:], strict=False):
        assert earlier.end == later.start


def test_unknown_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown domain"):
        predict.read(EXAMPLE, "lottery", dt.date(2026, 8, 5), dt.date(2026, 9, 1))


def test_domain_aware_split_is_measured_not_assumed() -> None:
    """Most of the library returns the same answer for every domain."""
    chart = EXAMPLE.chart()
    techniques = [h for h in hypotheses.LIBRARY if not h.name.startswith("CONTROL")]
    aware = predict.domain_aware_ids(chart, techniques)
    assert aware, "no technique responds to the domain at all"
    assert len(aware) < len(techniques), "every technique looks domain-aware; probe is broken"
    # The rule that reads a dasha lord's drishti onto the domain house must be
    # domain-aware, or a question about work cannot differ from one about money.
    assert "running-dasha-lord-aspects-the-domain-house" in aware


def test_fast_techniques_are_not_extreme_in_every_window(readings) -> None:
    """A monthly technique peaks inside any fortnight.

    Scored against its daily distribution the transiting Moon looks like a
    once-in-a-decade event every single window. The baseline therefore has to
    be built from window peaks, and this is the regression that proves it.
    """
    percentiles = [
        firing.percentile
        for reading in readings
        for firing in reading.firing
        if firing.technique == "transit Moon trigger"
    ]
    assert percentiles, "technique missing from the reading"
    assert not all(p >= predict.NOTABLE for p in percentiles), (
        "transit Moon trigger is above its 90th percentile in every window; "
        "the baseline is being taken from daily values rather than window peaks"
    )


def test_window_peak_baseline_spans_the_full_reference(readings) -> None:
    for reading in readings:
        for firing in reading.firing:
            assert 0.0 <= firing.percentile <= 1.0


def test_dasha_transitions_are_reported(readings) -> None:
    """The antardasha change is the timing event the reading is built on."""
    marks = [t for reading in readings for t in reading.transitions]
    assert any("Sep 2026" in mark and "Mercury-Saturn" in mark for mark in marks)


def test_narrate_reports_grounds_not_just_a_score(readings) -> None:
    text = predict.narrate(readings, "career")
    assert "READING — career" in text
    assert "Period changes in range" in text
    # Domain-blind techniques must be labelled as such, so a reading cannot
    # pass off an all-domains signal as being about the question asked.
    assert "[all domains]" in text
