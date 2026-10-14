"""Forward readings: which techniques fire, when, and what that means.

The backtest asks whether a technique survives a null. This module asks the
question a reading asks -- *when* does something happen, and *on what grounds*
-- by scoring the whole library across future windows and reporting the
techniques that stand out against their own history.

Two numbers are kept apart on purpose. Most of the library is domain-blind: it
returns the same value whether the question is a job or a marriage, so it moves
every domain at once whenever a dasha turns. Mixing those into one score is
what makes a reading say "everything is strong in October" about nothing in
particular. The domain signal is therefore reported separately from the general
intensity, and only the domain-aware techniques can distinguish one question
from another.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import dashas as D
from . import hypotheses as H
from .chart import Chart
from .ephemeris import TimeZone, fmt, parse
from .subjects import DOMAINS, Event, Subject

# Percentile above which a technique is called out. A technique sitting in the
# top decile of its own multi-decade history is doing something unusual; a raw
# score says nothing, because the scales are not comparable across techniques.
NOTABLE = 0.90

# Span used to build each technique's reference distribution.
_BASELINE_START = "1998-01-01"
_BASELINE_DAYS = 10400  # ~28 years, daily
_BASELINE_STEP = 3  # stride between reference windows


def _top_mean(values: list[float], k: int = 5) -> float:
    if not values:
        return 0.5
    top = sorted(values, reverse=True)[:k]
    return sum(top) / len(top)


@dataclass
class Firing:
    technique: str
    percentile: float
    score: float
    domain_aware: bool


@dataclass
class WindowReading:
    start: dt.date
    end: dt.date
    dasha: str
    transitions: list[str] = field(default_factory=list)
    firing: list[Firing] = field(default_factory=list)

    @property
    def domain_signal(self) -> float:
        """Mean of the strongest domain-aware techniques.

        Averaging the whole set hides the signal: most techniques sit near
        their median in any given window, so a handful of genuine hits get
        diluted by fifty quiet ones. A reading is about what stands out.
        """
        return _top_mean([f.percentile for f in self.firing if f.domain_aware])

    @property
    def general_intensity(self) -> float:
        return _top_mean([f.percentile for f in self.firing if not f.domain_aware])

    @property
    def notable(self) -> list[Firing]:
        return [f for f in self.firing if f.percentile >= NOTABLE]


def _windows(start: dt.date, end: dt.date, window_days: int) -> list[tuple[dt.date, dt.date]]:
    out = []
    cursor = start
    while cursor < end:
        out.append((cursor, cursor + dt.timedelta(days=window_days)))
        cursor += dt.timedelta(days=window_days)
    return out


def domain_aware_ids(chart: Chart, techniques: list[H.Hypothesis]) -> set[str]:
    """Techniques whose output actually responds to the domain being asked.

    Determined by scoring, not by inspection: a technique is domain-aware only
    if changing the domain changes its answer somewhere on a probe grid.
    """
    base = parse("2020-01-01", 0.0)
    grid = [base + i * 7 for i in range(200)]
    probes = ("career", "money", "relationship", "health")
    aware = set()
    for hypothesis in techniques:
        series = {
            domain: [
                hypothesis.score(chart, jd, Event("2024-01-01", "probe", (domain,), 1))
                for jd in grid
            ]
            for domain in probes
        }
        reference = series[probes[0]]
        if any(series[d] != reference for d in probes[1:]):
            aware.add(hypothesis.technique_id)
    return aware


def _baseline(chart: Chart, techniques, proto: Event, window_days: int) -> dict[str, list[float]]:
    """Distribution of each technique's *window peak*, not of its daily value.

    A window is scored by its maximum, so the comparison has to be against
    other windows. Against daily values instead, anything on a monthly cycle
    looks extraordinary in every window: the transiting Moon reaches a domain
    sign within any fortnight, so its peak sits near the top of the daily
    distribution always, and the reading calls it out every time.
    """
    start = parse(_BASELINE_START, 0.0)
    days = [start + i for i in range(_BASELINE_DAYS)]
    out = {}
    for hypothesis in techniques:
        series = [hypothesis.score(chart, jd, proto) for jd in days]
        peaks = [
            max(series[i : i + window_days])
            for i in range(0, len(series) - window_days, _BASELINE_STEP)
        ]
        out[hypothesis.technique_id] = sorted(peaks)
    return out


def _percentile(value: float, reference: list[float]) -> float:
    below = sum(1 for v in reference if v < value)
    equal = sum(1 for v in reference if v == value)
    return (below + 0.5 * equal) / len(reference)


def _transitions(tree, a: float, b: float, tz: TimeZone) -> list[str]:
    """Dasha period boundaries falling inside a window, at any level.

    These are the timing events a classical reading is actually built on; a
    window containing one is different in kind from a window that merely
    scores high.
    """
    out = []

    def walk(periods, depth):
        for period in periods:
            if a < period.start < b and depth <= 3:
                chain = "-".join(p.lord for p in D.active(tree, period.start + 0.5))
                out.append(f"{fmt(period.start, tz)}: begins {chain}")
            if period.children and period.start < b and period.end > a:
                walk(period.children, depth + 1)

    walk(tree, 1)
    return sorted(set(out))


def read(
    subject: Subject,
    domain: str,
    start: dt.date,
    end: dt.date,
    *,
    window_days: int = 14,
    ayanamsa: str = "lahiri",
    node: str = "true",
    timezone: TimeZone | None = None,
) -> list[WindowReading]:
    """Score every technique across each window and rank what stands out."""
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain!r}; choose from {sorted(DOMAINS)}")
    chart = subject.chart(ayanamsa=ayanamsa, node=node)
    tz = subject.birth_zone if timezone is None else timezone
    techniques = [h for h in H.LIBRARY if not h.name.startswith("CONTROL")]
    aware = domain_aware_ids(chart, techniques)
    proto = Event("2024-01-01", "probe", (domain,), 1)
    reference = _baseline(chart, techniques, proto, window_days)
    tree = D.vimshottari(chart)

    readings = []
    for a, b in _windows(start, end, window_days):
        ja = parse(a.isoformat(), tz)
        jb = parse(b.isoformat(), tz)
        days = [ja + i for i in range(int(jb - ja) + 1)]
        firing = []
        for hypothesis in techniques:
            ref = reference[hypothesis.technique_id]
            if ref[0] == ref[-1]:
                continue  # constant for this domain: nothing to say
            peak = max(hypothesis.score(chart, jd, proto) for jd in days)
            firing.append(
                Firing(
                    hypothesis.name,
                    _percentile(peak, ref),
                    peak,
                    hypothesis.technique_id in aware,
                )
            )
        firing.sort(key=lambda f: -f.percentile)
        readings.append(
            WindowReading(
                a,
                b,
                "-".join(p.lord for p in D.active(tree, ja)[:3]),
                _transitions(tree, ja, jb, tz),
                firing,
            )
        )
    return readings


def narrate(readings: list[WindowReading], domain: str) -> str:
    """Human reading: the windows that stand out and the grounds for each."""
    if not readings:
        return "no windows in range"
    lines = [f"=== READING — {domain} ===", ""]

    ranked = sorted(readings, key=lambda r: -r.domain_signal)
    best = ranked[0]
    worst = ranked[-1]
    lines.append(
        f"Strongest {domain} window: {best.start} .. {best.end} "
        f"(domain signal {best.domain_signal:.0%}, general {best.general_intensity:.0%})"
    )
    lines.append(
        f"Weakest:                  {worst.start} .. {worst.end} "
        f"(domain signal {worst.domain_signal:.0%})"
    )
    turns = [t for r in readings for t in r.transitions]
    if turns:
        lines.append("")
        lines.append("Period changes in range (the classical timing events):")
        lines.extend(f"  {t}" for t in turns)
    lines.append("")

    for reading in readings:
        head = (
            f"{reading.start} .. {reading.end}  {reading.dasha}"
            f"   domain {reading.domain_signal:.0%} / general {reading.general_intensity:.0%}"
        )
        lines.append(head)
        for mark in reading.transitions:
            lines.append(f"    ** {mark}")
        shown = [f for f in reading.notable if f.domain_aware][:4]
        if not shown:
            lines.append("     (no domain-specific technique above its 90th percentile)")
        for f in shown:
            lines.append(f"     {f.percentile:5.0%}  {f.technique}")
        blind = [f for f in reading.notable if not f.domain_aware][:3]
        for f in blind:
            lines.append(f"     {f.percentile:5.0%}  {f.technique}  [all domains]")
        lines.append("")
    return "\n".join(lines)
