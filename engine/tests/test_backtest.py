from __future__ import annotations

import math

import pytest

from jyotisha import backtest
from jyotisha.ephemeris import parse
from jyotisha.subjects import Event, Subject


def _subject() -> Subject:
    return Subject(
        "Synthetic",
        2000,
        1,
        1,
        12.0,
        0.0,
        0.0,
        0.0,
        events=[
            Event("2024-01-01", "a", ("career",), 1),
            Event("2024-02-01", "b", ("career",), 1),
            Event("2024-03-01", "c", ("career",), 1),
            Event("2024-04-01", "d", ("career",), 1),
        ],
    )


def _lunar_wave(_chart, jd, _event) -> float:
    return math.sin(jd * 2 * math.pi / 29.53059)


def test_identical_techniques_are_not_treated_as_independent() -> None:
    hypotheses = [
        backtest.Hypothesis("same one", _lunar_wave, ("career",)),
        backtest.Hypothesis("same two", _lunar_wave, ("career",)),
    ]
    results = backtest.run(
        _subject(),
        hypotheses,
        n_null=199,
        seed=11,
        gate_precision=False,
    )
    one, two = results
    assert one.empirical_p == two.empirical_p
    assert one.fwer_p == pytest.approx(one.empirical_p)
    assert two.fwer_p == pytest.approx(two.empirical_p)
    assert len(one.null_statistic) == 199


def test_joint_fwer_never_beats_the_unadjusted_tail() -> None:
    hypotheses = [
        backtest.Hypothesis("wave", _lunar_wave, ("career",)),
        backtest.Hypothesis(
            "harmonic",
            lambda _chart, jd, _event: math.cos(jd * 2 * math.pi / 17.0),
            ("career",),
        ),
    ]
    results = backtest.run(
        _subject(),
        hypotheses,
        n_null=199,
        seed=13,
        gate_precision=False,
    )
    assert all(result.fwer_p + 1e-12 >= result.empirical_p for result in results)


def test_joint_fwer_uses_shared_raw_max_not_a_second_rank() -> None:
    strong = backtest.Result(
        "strong",
        1,
        aggregate_percentile=0.9,
        null_statistic=[0.1, 0.2, 0.3],
    )
    competing_null = backtest.Result(
        "competing",
        1,
        aggregate_percentile=0.4,
        null_statistic=[0.95, 0.96, 0.97],
    )
    backtest.joint_fwer([strong, competing_null])
    assert strong.fwer_p == 1.0


def test_parallel_and_serial_null_scores_are_identical() -> None:
    hypothesis = backtest.Hypothesis("wave", _lunar_wave, ("career",))
    options = {
        "n_null": 31,
        "seed": 17,
        "gate_precision": False,
    }
    serial = backtest.run(_subject(), [hypothesis], workers=1, **options)[0]
    parallel = backtest.run(_subject(), [hypothesis], workers=2, **options)[0]
    assert parallel.null_statistic == serial.null_statistic
    assert parallel.aggregate_percentile == serial.aggregate_percentile
    assert parallel.empirical_p == serial.empirical_p


def test_day_precision_samples_the_civil_day_not_adjacent_noons() -> None:
    centre = parse("2026-05-19", "Europe/Paris")
    sampled = []

    def record(_chart, jd, _event):
        sampled.append(jd)
        return jd

    event = Event(
        "2026-05-19",
        "day-known",
        ("career",),
        1,
        tz="Europe/Paris",
    )
    backtest._statistic(record, _subject().chart(), centre, event, "Asia/Kolkata")
    assert len(sampled) == 9
    assert min(sampled) == pytest.approx(centre - 0.5)
    assert max(sampled) == pytest.approx(centre + 0.5)


def test_date_only_event_honours_its_explicit_timezone() -> None:
    event = Event(
        "2026-05-19",
        "located",
        ("career",),
        1,
        tz="Europe/Paris",
    )
    assert backtest._event_jd(event, "Asia/Kolkata") == pytest.approx(
        parse(event.date, "Europe/Paris")
    )


def test_sampling_step_never_refines_below_the_fixed_grid() -> None:
    """Coherence may coarsen a scan, never make it finer than the old grid."""
    for half_width, base in ((0.5, 0.125), (15.0, 1.0), (45.0, 1.0)):
        for coherence in (0.0, 0.5, 1.0, 14.0, 365.0, float("inf")):
            assert backtest._sampling_step(half_width, coherence) >= base


def test_sampling_step_is_capped_so_a_window_keeps_several_samples() -> None:
    # An "immune to date error" technique must still be scanned, not sampled
    # at a single point.
    assert backtest._sampling_step(45.0, float("inf")) == pytest.approx(22.5)


def test_coherence_probe_does_not_call_a_varying_technique_constant() -> None:
    """A probe that cannot make a technique move must not report immunity.

    The probe previously ran five years with an all-domain event, which pinned
    domain-conditional techniques to a constant and was then read as "immune to
    date error" -- the opposite of the truth for a spiky technique.
    """
    from jyotisha import hypotheses

    chart = _subject().chart()
    chart_id = backtest.register_chart(chart)
    proto = Event("2024-01-01", "probe", ("career",), 1)
    grid = [parse("1996-01-01", 0.0) + i * 7 for i in range(1500)]

    for hypothesis in hypotheses.LIBRARY:
        backtest._COHERENCE_HYPOTHESES[hypothesis.name] = hypothesis
        coherence = backtest.coherence_time(hypothesis.name, chart_id)
        if not math.isinf(coherence):
            continue
        values = {hypothesis.score(chart, jd, proto) for jd in grid}
        assert len(values) == 1, (
            f"{hypothesis.technique_id} reported coherence=inf (constant) but takes "
            f"{len(values)} distinct values over thirty years"
        )
