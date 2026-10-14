from __future__ import annotations

from jyotisha import hypotheses


def test_technique_ids_are_unique_and_provenance_is_explicit() -> None:
    ids = [technique.technique_id for technique in hypotheses.LIBRARY]
    assert len(ids) == len(set(ids))
    assert all(technique.introduced_at for technique in hypotheses.LIBRARY)
    assert all(technique.status for technique in hypotheses.LIBRARY)


def test_postmortem_rules_exclude_discovery_dates() -> None:
    """The six post-mortem additions must carry their discovery exclusions.

    Identified by id rather than by list position: slicing LIBRARY meant that
    removing any earlier technique silently moved the assertion onto unrelated
    entries instead of failing.
    """
    by_id = {technique.technique_id: technique for technique in hypotheses.LIBRARY}
    assert hypotheses._POST_MORTEM <= by_id.keys()
    for technique_id in hypotheses._POST_MORTEM:
        assert "2024-03-18" in by_id[technique_id].discovery_exclusions


def test_only_the_postmortem_rules_carry_discovery_exclusions() -> None:
    excluded = {
        technique.technique_id for technique in hypotheses.LIBRARY if technique.discovery_exclusions
    }
    assert excluded == set(hypotheses._POST_MORTEM)


def test_no_registered_technique_is_constant_for_the_default_subject() -> None:
    """A technique that cannot move carries no information but still costs a
    slot in the max-statistic family correction."""
    import math

    from jyotisha import backtest
    from jyotisha.subjects import EXAMPLE

    chart = EXAMPLE.chart()
    chart_id = backtest.register_chart(chart)
    constant = []
    for technique in hypotheses.LIBRARY:
        backtest._COHERENCE_HYPOTHESES[technique.name] = technique
        if math.isinf(backtest.coherence_time(technique.name, chart_id)):
            constant.append(technique.technique_id)
    assert not constant, f"constant techniques still registered: {constant}"
