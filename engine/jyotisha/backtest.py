"""Dependence-preserving empirical tests for registered techniques.

Each null replicate applies one common date shift to the complete event
timeline. This preserves event clustering. The same replicate is shared by
all techniques, allowing a max-statistic correction that also preserves
dependence between techniques. Date-uncertainty windows are applied equally
to observed and null events.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import marshal
import math
import os
import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field

from .chart import Chart
from .ephemeris import TimeZone, parse
from .storage import ensure_private_parent, secure_file, user_path
from .subjects import Event, Subject

UNCERTAINTY_DAYS = {"day": 0.5, "week": 3.5, "month": 15.0, "quarter": 45.0}

# A scorer sees the event it is being asked about, so it can look at the
# right houses.  Null draws pass the *same* event with a random date, which
# is what keeps the comparison fair.
Scorer = Callable[[Chart, float, "Event"], float]


def event_uncertainty(event: Event) -> float:
    """Half-width of the interval in which the event moment is known."""
    if event.time:
        hours = event.time_uncertainty_hours
        return (1.2 if hours is None else hours) / 24.0
    return UNCERTAINTY_DAYS.get(event.confidence, 15.0)


@dataclass
class Hypothesis:
    name: str
    score: Scorer
    domains: tuple[str, ...] = ()  # empty = claims to mark any event
    note: str = ""
    source: str = ""
    convention: str = ""
    introduced_at: str = ""
    discovery_exclusions: tuple[str, ...] = ()
    polarity: tuple[int, ...] = (-1, 0, 1)
    min_magnitude: int = 1
    status: str = "exploratory"
    family: str = "classical"

    def applies_to(self, event: Event) -> bool:
        domain_match = not self.domains or bool(set(self.domains) & set(event.domains))
        return (
            domain_match
            and event.polarity in self.polarity
            and event.magnitude >= self.min_magnitude
            and event.date not in self.discovery_exclusions
        )

    @property
    def technique_id(self) -> str:
        clean = "".join(c if c.isalnum() else "-" for c in self.name.lower()).strip("-")
        return "-".join(part for part in clean.split("-") if part)

    def metadata(self) -> dict:
        return {
            "id": self.technique_id,
            "name": self.name,
            "domains": list(self.domains),
            "note": self.note,
            "source": self.source,
            "convention": self.convention,
            "introduced_at": self.introduced_at,
            "discovery_exclusions": list(self.discovery_exclusions),
            "polarity": list(self.polarity),
            "min_magnitude": self.min_magnitude,
            "status": self.status,
            "family": self.family,
        }


@dataclass
class Result:
    hypothesis: str
    n_events: int
    per_event: list[dict] = field(default_factory=list)
    empirical_p: float = 1.0
    aggregate_percentile: float = 0.5
    verdict: str = ""
    degenerate: int = 0  # events whose null had zero spread
    fwer_p: float = 1.0
    bh_q: float = 1.0
    null_statistic: list[float] = field(default_factory=list, repr=False)

    def __str__(self) -> str:
        head = (
            f"{self.hypothesis:44s} n={self.n_events}  "
            f"p={self.empirical_p:.4f}  FWER={self.fwer_p:.4f}  "
            f"aggregate pct={self.aggregate_percentile:.2f}  {self.verdict}"
        )
        rows = [
            f"    {e['date']:11s} {e['label'][:34]:34s} "
            f"score={e['score']:6.2f}  better than {1 - e['p']:5.1%} of chance"
            for e in self.per_event
        ]
        return "\n".join([head, *rows])


def _pad(date: str) -> str:
    return date if len(date) > 7 else date + "-15"


def _event_jd(event: Event, tz: TimeZone) -> float:
    """Julian day of the event, using the clock time when it is known."""
    if event.tz is not None:
        tz = event.tz
    stamp = _pad(event.date)
    if getattr(event, "time", None) and len(event.date) > 7:
        stamp = f"{event.date} {event.time}"
    elif event.confidence == "day" and len(event.date) == 10:
        date = dt.date.fromisoformat(event.date)
        start = parse(date.isoformat(), tz, date_hour=0)
        end = parse((date + dt.timedelta(days=1)).isoformat(), tz, date_hour=0)
        return (start + end) / 2
    return parse(stamp, tz)


# Samples across one coherence length. Measured against a 0.125-day reference
# grid, 16 tracks that reference more closely than the fixed 1-day grid it
# replaces while evaluating fewer points; 4 is visibly too coarse and disturbs
# the pseudo-random control.
_COHERENCE_SAMPLES_PER_CYCLE = 16.0


def _sampling_step(half_width: float, coherence: float) -> float:
    """Grid spacing for scanning an uncertainty window.

    A technique cannot resolve detail finer than its own coherence time, so
    sampling a window far below that scale buys nothing but ephemeris calls.
    The step never goes below the historical fixed grid, and the same grid is
    used for the observed and null statistics, so the comparison the inference
    rests on stays symmetric.
    """
    base = 0.125 if half_width <= 0.5 else 1.0
    if coherence <= 0 or half_width <= 0:
        return base
    return max(base, min(coherence / _COHERENCE_SAMPLES_PER_CYCLE, half_width / 2.0))


def _window_max(
    score: Scorer,
    chart: Chart,
    centre: float,
    half_width: float,
    event: Event,
    coherence: float = 0.0,
) -> float:
    """Maximum over the declared uncertainty interval, sampled uniformly."""
    step = _sampling_step(half_width, coherence)
    intervals = max(2, math.ceil(2 * half_width / step))
    return max(
        score(chart, centre - half_width + i * 2 * half_width / intervals, event)
        for i in range(intervals + 1)
    )


def _interval_mean(
    score: Scorer, chart: Chart, start: float, length: float, event: Event, step: float = 7.0
) -> float:
    """Sustained states get a mean over the span, not a best day.

    A three-year run of topping the class is a claim about the whole period;
    scoring it by its single best day would let any technique win.
    """
    n = max(2, min(60, int(length / step)))  # cap: 60 samples is plenty
    return statistics.fmean(score(chart, start + i * length / (n - 1), event) for i in range(n))


@functools.lru_cache(maxsize=4096)
def _civil_day_half_width(date: str, zone: TimeZone) -> float:
    """Half a calendar day in the event's own civil zone.

    Depends only on the date and the zone, but sat in the per-replicate scoring
    path, so it re-parsed timestamps millions of times across a family run.
    """
    day = dt.date.fromisoformat(date)
    start = parse(day.isoformat(), zone, date_hour=0)
    end = parse((day + dt.timedelta(days=1)).isoformat(), zone, date_hour=0)
    return (end - start) / 2


_INTERVAL_LENGTHS: dict[tuple[int, TimeZone], tuple[Event, float]] = {}


def _interval_length(event: Event, tz: TimeZone) -> float:
    """Span of a sustained state. Shift-invariant, so it is computed once.

    The cached value keeps its event alive, so the ``id`` key cannot be reused
    by a different object.
    """
    key = (id(event), tz)
    cached = _INTERVAL_LENGTHS.get(key)
    if cached is not None and cached[0] is event:
        return cached[1]
    length = parse(_pad(event.end), tz) - _event_jd(event, tz)
    _INTERVAL_LENGTHS[key] = (event, length)
    return length


def _statistic(
    score: Scorer,
    chart: Chart,
    centre: float,
    event: Event,
    tz: TimeZone,
    coherence: float = 0.0,
) -> float:
    if event.is_interval:
        length = _interval_length(event, tz)
        return _interval_mean(score, chart, centre, length, event)
    half_width = event_uncertainty(event)
    if not event.time and event.confidence == "day" and len(event.date) == 10:
        zone = event.tz if event.tz is not None else tz
        half_width = _civil_day_half_width(event.date, zone)
    return _window_max(score, chart, centre, half_width, event, coherence)


TROPICAL_YEAR = 365.2422


def _timeline_shifts(
    rng: random.Random,
    n: int,
    *,
    span_years: float,
    mode: str,
) -> list[float]:
    """Common shifts for the complete event timeline.

    A single shift is applied to every event in a replicate. This preserves
    event gaps and clustering instead of pretending nearby events are
    independent confirmations.
    """
    if n < 1:
        raise ValueError("n_null must be positive")
    half_years = max(2.0, span_years / 2)
    shifts: list[float] = []
    while len(shifts) < n:
        if mode == "uniform":
            years = rng.uniform(-half_years, half_years)
            if abs(years) < 0.25:
                continue
        elif mode == "seasonal":
            year = rng.choice([i for i in range(-int(half_years), int(half_years) + 1) if i])
            years = year + rng.uniform(-14.0, 14.0) / TROPICAL_YEAR
        elif mode == "matched":
            year = rng.choice((-2, -1, 1, 2))
            # Local enough to condition on the slow era and season-matched
            # enough not to turn academic scheduling into an astrology result.
            years = year + rng.uniform(-14.0, 14.0) / TROPICAL_YEAR
        else:
            raise ValueError("null_mode must be uniform, seasonal, or matched")
        shifts.append(years * TROPICAL_YEAR)
    return shifts


def _midrank_strength(value: float, reference: list[float]) -> float:
    """Fraction of a reference distribution below ``value``, splitting ties."""
    if not reference:
        return 0.5
    lower = sum(v < value for v in reference)
    equal = sum(v == value for v in reference)
    return (lower + 0.5 * equal) / len(reference)


@dataclass
class _FamilyBundle:
    results: list[Result]
    shifts: list[float]


@dataclass
class _TechniqueWork:
    hypothesis: Hypothesis
    result: Result
    events: list[Event]
    jds: list[float]
    actual: list[float]
    null_by_event: list[list[float]]
    null_by_rep: list[list[float]] = field(default_factory=list)
    coherence: float = 0.0


def _score_shift_chunk(payload) -> list[list[list[float]]]:
    """Score one contiguous shift chunk in an isolated worker process."""
    chart, specifications, shifts, timezone = payload
    rows_by_technique: list[list[list[float]]] = [[] for _ in specifications]
    for shift in shifts:
        for index, (hypothesis, events, jds, coherence) in enumerate(specifications):
            rows_by_technique[index].append(
                [
                    _statistic(
                        hypothesis.score,
                        chart,
                        event_jd + shift,
                        event,
                        timezone,
                        coherence,
                    )
                    for event, event_jd in zip(events, jds, strict=True)
                ]
            )
    return rows_by_technique


def _events_for(
    subject: Subject,
    chart: Chart,
    hypothesis: Hypothesis,
    gate_precision: bool,
) -> list[Event]:
    events = [
        e
        for e in subject.events
        if hypothesis.applies_to(e)
        and getattr(e, "kind", "event") == "event"
        and not getattr(e, "contaminated", "")
    ]
    if gate_precision:
        events, _ = gate(chart, hypothesis, events)
    return events


def _family_inference(
    subject: Subject,
    hypotheses: list[Hypothesis],
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
    n_null: int = 999,
    span_years: float = 12.0,
    seed: int = 7,
    null_mode: str = "matched",
    gate_precision: bool = True,
    workers: int = 1,
) -> _FamilyBundle:
    """Empirical timeline-shift inference, including max-statistic FWER.

    Every replicate shifts the entire event timeline by the same amount.
    Aggregate null statistics therefore retain event dependence, while the
    same replicate index across techniques retains technique dependence.
    """
    names = [hypothesis.name for hypothesis in hypotheses]
    if len(names) != len(set(names)):
        raise ValueError("hypothesis names must be unique within a family")
    chart = subject.chart(ayanamsa=ayanamsa, node=node)
    if gate_precision:
        warm_coherence_cache(chart, hypotheses)
    rng = random.Random(seed)
    shifts = _timeline_shifts(rng, n_null, span_years=span_years, mode=null_mode)
    results: list[Result] = []
    work_items: list[_TechniqueWork] = []

    chart_id = register_chart(chart)
    for hypothesis in hypotheses:
        events = _events_for(subject, chart, hypothesis, gate_precision)
        result = Result(hypothesis.name, len(events))
        results.append(result)
        if not events:
            result.verdict = "no matching events"
            continue
        # Observed and null statistics must share one sampling grid, so the
        # coherence-derived step is resolved once per technique here.
        _COHERENCE_HYPOTHESES[hypothesis.name] = hypothesis
        coherence = coherence_time(hypothesis.name, chart_id) if gate_precision else 0.0
        jds = [_event_jd(e, subject.birth_zone) for e in events]
        actual = [
            _statistic(hypothesis.score, chart, jd, event, subject.birth_zone, coherence)
            for event, jd in zip(events, jds, strict=True)
        ]
        work_items.append(
            _TechniqueWork(
                hypothesis,
                result,
                events,
                jds,
                actual,
                [[] for _ in events],
                coherence=coherence,
            )
        )

    if workers < 0:
        raise ValueError("workers must be nonnegative")
    resolved_workers = workers
    if resolved_workers == 0:
        resolved_workers = min(8, os.cpu_count() or 1) if n_null >= 64 else 1
    resolved_workers = max(1, min(resolved_workers, n_null))
    specifications = [
        (work.hypothesis, work.events, work.jds, work.coherence) for work in work_items
    ]

    if resolved_workers == 1:
        chunks = [_score_shift_chunk((chart, specifications, shifts, subject.birth_zone))]
    else:
        from concurrent.futures import ProcessPoolExecutor

        chunk_size = math.ceil(len(shifts) / resolved_workers)
        payloads = [
            (
                chart,
                specifications,
                shifts[start : start + chunk_size],
                subject.birth_zone,
            )
            for start in range(0, len(shifts), chunk_size)
        ]
        with ProcessPoolExecutor(max_workers=resolved_workers) as executor:
            chunks = list(executor.map(_score_shift_chunk, payloads))

    for chunk in chunks:
        for work, rows in zip(work_items, chunk, strict=True):
            work.null_by_rep.extend(rows)
    for work in work_items:
        for row in work.null_by_rep:
            for index, value in enumerate(row):
                work.null_by_event[index].append(value)

    for work in work_items:
        result = work.result
        actual_strength = []
        for event, score_value, null in zip(
            work.events,
            work.actual,
            work.null_by_event,
            strict=True,
        ):
            strength = _midrank_strength(score_value, null)
            spread = statistics.pstdev(null) if len(null) > 1 else 0.0
            if spread == 0:
                result.degenerate += 1
            actual_strength.append(strength)
            result.per_event.append(
                {
                    "date": event.date,
                    "label": event.label,
                    "score": score_value,
                    "p": 1 - strength,
                    "null_mean": statistics.fmean(null),
                    "null_sd": spread,
                }
            )

        null_strength_by_event = [
            [_midrank_strength(value, work.null_by_event[i]) for i, value in enumerate(row)]
            for row in work.null_by_rep
        ]
        observed_stat = statistics.fmean(actual_strength)
        null_stat = [statistics.fmean(row) for row in null_strength_by_event]
        result.aggregate_percentile = observed_stat
        result.null_statistic = null_stat
        result.empirical_p = (sum(v >= observed_stat for v in null_stat) + 1) / (len(null_stat) + 1)
        if result.degenerate == len(events):
            result.verdict = "NOT APPLICABLE (scorer never varies)"
        else:
            result.verdict = "exploratory; see family-adjusted p"

    real = [
        r
        for r in results
        if not r.hypothesis.startswith("CONTROL") and r.n_events and r.degenerate < r.n_events
    ]
    if real:
        joint_fwer(real)
        ordered = sorted(real, key=lambda r: r.empirical_p)
        q_next = 1.0
        for rank in range(len(ordered), 0, -1):
            r = ordered[rank - 1]
            q_next = min(q_next, r.empirical_p * len(ordered) / rank)
            r.bh_q = q_next
        status_by_name = {h.name: h.status for h in hypotheses}
        for r in real:
            r.verdict = (
                "CONFIRMATORY SURVIVOR"
                if r.fwer_p < 0.05 and status_by_name[r.hypothesis] == "confirmatory"
                else "exploratory signal"
                if r.fwer_p < 0.05
                else "no family-adjusted evidence"
            )
    for r in results:
        if r.hypothesis.startswith("CONTROL"):
            r.fwer_p = r.empirical_p
            r.bh_q = 1.0
            if r.degenerate < r.n_events:
                r.verdict = "CONTROL WARNING" if r.empirical_p < 0.05 else "control behaves"
    results.sort(key=lambda r: r.empirical_p)
    return _FamilyBundle(results, shifts)


def evaluate(
    subject: Subject,
    hypothesis: Hypothesis,
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
    n_null: int = 999,
    span_years: float = 12.0,
    seed: int = 7,
    null_mode: str = "matched",
    gate_precision: bool = True,
    workers: int = 1,
) -> Result:
    """Score one hypothesis with the same empirical kernel as a family run."""
    return _family_inference(
        subject,
        [hypothesis],
        ayanamsa=ayanamsa,
        node=node,
        n_null=n_null,
        span_years=span_years,
        seed=seed,
        null_mode=null_mode,
        gate_precision=gate_precision,
        workers=workers,
    ).results[0]


def joint_fwer(results: list[Result]) -> None:
    """Apply maxT correction to aligned aggregate-percentile null replicates."""
    if not results:
        return
    lengths = {len(result.null_statistic) for result in results}
    if len(lengths) != 1 or not lengths or 0 in lengths:
        raise ValueError("joint FWER requires equally sized, non-empty null replicates")
    n_rep = lengths.pop()
    # All statistics are already means of event-level percentiles on [0, 1].
    # Ranking them a second time makes an observation above its finite null
    # maximum equal 1 while no leave-in null rank can reach 1, spuriously
    # forcing its adjusted p-value to the Monte Carlo floor.
    max_null = [max(result.null_statistic[i] for result in results) for i in range(n_rep)]
    for result in results:
        result.fwer_p = (sum(value >= result.aggregate_percentile for value in max_null) + 1) / (
            n_rep + 1
        )


def compare_ayanamsas(
    subject: Subject, hypotheses: list[Hypothesis], names: list[str] | None = None, **kw
) -> str:
    """The test the collection's Tier-4 polemic demands: does the sidereal
    assumption actually earn its keep against a tropical chart?"""
    # true_citra / true_revati are omitted: they resolve the ayanamsa from a
    # star position and need sefstars.txt, which is not bundled.
    names = names or [
        "lahiri",
        "raman",
        "krishnamurti",
        "yukteshwar",
        "suryasiddhanta",
        "fagan_bradley",
        "tropical",
    ]
    bundles = {name: _family_inference(subject, hypotheses, ayanamsa=name, **kw) for name in names}
    candidates = [
        r
        for bundle in bundles.values()
        for r in bundle.results
        if not r.hypothesis.startswith("CONTROL") and r.n_events and r.degenerate < r.n_events
    ]
    if candidates:
        joint_fwer(candidates)
    rows = [f"{'hypothesis':44s}" + "".join(f"{n[:9]:>17s}" for n in names)]
    for h in hypotheses:
        cells = []
        for name in names:
            r = next(result for result in bundles[name].results if result.hypothesis == h.name)
            cells.append(f"{r.empirical_p:.3f}/{r.fwer_p:.3f}".rjust(17))
        rows.append(f"{h.name:44s}" + "".join(cells))
    rows.append("")
    rows.append(
        "cells are empirical p / FWER p, corrected jointly across "
        "all displayed hypotheses and ayanamsas"
    )
    return "\n".join(rows)


def run(subject: Subject, hypotheses: list[Hypothesis], **kw) -> list[Result]:
    return _family_inference(subject, hypotheses, **kw).results


def family_report(subject: Subject, hypotheses: list[Hypothesis], **kw) -> str:
    """Results with the multiple-comparison correction applied.

    Testing more techniques does not make a finding more likely to be real --
    it makes a low p-value cheaper.  With k hypotheses the best one under pure
    chance lands near 1/(k+1), so that is the bar, not 0.05.
    """
    results = run(subject, hypotheses, **kw)
    real = [r for r in results if not r.hypothesis.startswith("CONTROL") and r.n_events]
    controls = [r for r in results if r.hypothesis.startswith("CONTROL")]
    informative = [r for r in real if r.degenerate < r.n_events]
    k = len(informative)

    lines = [f"{'hypothesis':46s}{'n':>4s}{'p':>9s}{'FWER':>9s}{'BH q':>9s}  verdict"]
    ordered = sorted(real, key=lambda r: r.empirical_p)
    for r in ordered:
        lines.append(
            f"{r.hypothesis:46s}{r.n_events:4d}{r.empirical_p:9.4f}"
            f"{r.fwer_p:9.4f}{r.bh_q:9.4f}  {r.verdict}"
        )
    for r in controls:
        lines.append(
            f"{r.hypothesis:46s}{r.n_events:4d}{r.empirical_p:9.4f}{'-':>9s}{'-':>9s}  {r.verdict}"
        )

    best_raw = min(informative, key=lambda r: r.empirical_p) if informative else None
    family_best = min(informative, key=lambda r: r.fwer_p) if informative else None
    omnibus = family_best.fwer_p if family_best else 1.0
    n_null = len(family_best.null_statistic) if family_best else 0
    mc_se = math.sqrt(omnibus * (1 - omnibus) / max(n_null, 1))
    lines += [
        "",
        f"  informative techniques     k = {k}",
        f"  joint timeline nulls       B = {n_null}",
        f"  best empirical p               {best_raw.empirical_p if best_raw else 1.0:.4f}",
        f"  max-statistic family p         {omnibus:.4f}",
        f"  Monte Carlo SE                 {mc_se:.4f}",
        f"  smallest BH q                  {min((r.bh_q for r in informative), default=1.0):.4f}",
        "",
        (
            "  VERDICT: a preregistered technique survives empirical family correction."
            if any(r.verdict == "CONFIRMATORY SURVIVOR" for r in informative)
            else "  VERDICT: no confirmatory family-adjusted evidence."
        ),
    ]
    return "\n".join(lines)


# ============================================================================
# Precision gating.
#
# Every hypothesis in the library was being scored against every event,
# regardless of whether the event's date was known well enough for that
# hypothesis to mean anything.  A tithi-based rule tested against an exam
# result dated to the month the result came out is scored against a date that
# can be wrong by fifty days, and the tithi changes every twelve hours.  That
# is not a weak test, it is a test of noise, and it dilutes the family-wise
# correction for every other hypothesis by adding rows that could never have
# shown anything.
#
# Rather than hand-label 57 hypotheses, measure each one: how long does its
# output stay put?  The coherence time is the lag at which its autocorrelation
# falls below 0.5.  An event may only be scored by a hypothesis whose coherence
# time exceeds the event's date uncertainty.
# ============================================================================


def _scorer_fingerprint(score: Scorer) -> str:
    """Fingerprint scorer code, including code supplied outside this package."""
    digest = hashlib.sha256()
    digest.update(getattr(score, "__module__", "").encode())
    digest.update(b"\0")
    digest.update(getattr(score, "__qualname__", type(score).__qualname__).encode())
    code = getattr(score, "__code__", None)
    if code is not None:
        digest.update(marshal.dumps(code))
    digest.update(repr(getattr(score, "__defaults__", None)).encode())
    digest.update(repr(getattr(score, "__kwdefaults__", None)).encode())
    closure = getattr(score, "__closure__", None)
    if closure:
        digest.update(repr(tuple(cell.cell_contents for cell in closure)).encode())
    return digest.hexdigest()


# Probe span. Saturn's cycle is 29.5 years and the rashi dashas run in
# multi-year blocks, so a five-year probe reported several genuinely varying
# techniques as constant.
_COHERENCE_PROBE_DAYS = 10958  # 30 tropical years, daily
_COHERENCE_PROBE_START = "1996-01-01"
_COHERENCE_LAGS = (1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 120, 180, 365, 730, 1460, 2920)

# One probe per distinct house signature in DOMAINS. A probe that declares
# every domain covers all twelve houses, which pins any domain-conditional
# technique to a constant -- that was being read as "immune to date error"
# when it only meant "the probe could not make it move".
_COHERENCE_PROBE_DOMAINS = ("career", "education", "relationship", "travel", "health")


def _decorrelation_lag(values: list[float]) -> float:
    """Smallest lag whose autocorrelation falls below 0.5."""
    n = len(values)
    mean = sum(values) / n
    dev = [x - mean for x in values]
    var = sum(d * d for d in dev)
    if var < 1e-12:
        return float("inf")  # genuinely constant over the probe
    for lag in _COHERENCE_LAGS:
        if lag >= n:
            break
        cov = sum(dev[i] * dev[i + lag] for i in range(n - lag))
        if cov / var * n / (n - lag) < 0.5:
            return float(lag)
    return float(_COHERENCE_LAGS[-1])


@functools.cache
def _compute_coherence_time(
    hyp_name: str,
    chart_id: int,
    scorer_fingerprint: str,
) -> float:
    """Days until a hypothesis's output decorrelates from itself.

    Probed on a thirty-year daily grid, once per representative domain, and
    cached. The result is the *fastest* decorrelation over those probes: the
    gate uses it to drop techniques that move faster than an event's recorded
    date precision, so the conservative bound is the short one.
    """
    hyp = _COHERENCE_HYPOTHESES.get(hyp_name)
    if hyp is None:
        from .hypotheses import LIBRARY

        hyp = next(h for h in LIBRARY if h.name == hyp_name)
    chart = _CHART_REGISTRY[chart_id]
    base = parse(_COHERENCE_PROBE_START, 0.0)
    grid = [base + i for i in range(_COHERENCE_PROBE_DAYS)]
    # A technique that names its own domains can only be probed on those.
    domains = hyp.domains or _COHERENCE_PROBE_DOMAINS
    best = float("inf")
    for domain in domains:
        proto = Event("2024-01-01", "probe", (domain,), 1, "day")
        best = min(best, _decorrelation_lag([hyp.score(chart, j, proto) for j in grid]))
    return best


_CHART_REGISTRY: dict[int, Chart] = {}
_COHERENCE_OVERRIDES: dict[tuple[str, str, int], float] = {}
_COHERENCE_HYPOTHESES: dict[str, Hypothesis] = {}


def register_chart(chart: Chart) -> int:
    _CHART_REGISTRY[id(chart)] = chart
    return id(chart)


def coherence_time(hyp_name: str, chart_id: int) -> float:
    hypothesis = _COHERENCE_HYPOTHESES.get(hyp_name)
    if hypothesis is None:
        from .hypotheses import LIBRARY

        try:
            hypothesis = next(item for item in LIBRARY if item.name == hyp_name)
        except StopIteration as exc:
            raise KeyError(f"unknown hypothesis {hyp_name!r}") from exc
    fingerprint = _scorer_fingerprint(hypothesis.score)
    cached = _COHERENCE_OVERRIDES.get((hyp_name, fingerprint, chart_id))
    return _compute_coherence_time(hyp_name, chart_id, fingerprint) if cached is None else cached


@functools.cache
def _code_hash() -> str:
    from .provenance import code_hash

    return code_hash()


def _coherence_namespace(chart: Chart) -> str:
    payload = json.dumps(
        {
            "code": _code_hash(),
            "jd": chart.jd,
            "lat": chart.lat,
            "lon": chart.lon,
            "ayanamsa": chart.ayanamsa,
            "node": chart.node,
            "division": chart.division,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def warm_coherence_cache(chart: Chart, hypotheses: list[Hypothesis]) -> None:
    """Load or atomically build coherence values for this code and chart."""
    import fcntl

    chart_id = register_chart(chart)
    namespace = _coherence_namespace(chart)
    path = user_path("coherence_cache.json")
    lock_path = user_path("coherence_cache.lock")
    ensure_private_parent(path)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    secure_file(lock_path)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            values: dict[str, dict] = {}
            if path.exists():
                try:
                    document = json.loads(path.read_text(encoding="utf-8"))
                    if (
                        document.get("schema") == 2
                        and document.get("namespace") == namespace
                        and isinstance(document.get("values"), dict)
                    ):
                        values = document["values"]
                except (OSError, json.JSONDecodeError):
                    values = {}
            changed = False
            for hypothesis in hypotheses:
                _COHERENCE_HYPOTHESES[hypothesis.name] = hypothesis
                fingerprint = _scorer_fingerprint(hypothesis.score)
                entry = values.get(hypothesis.name, {})
                if not isinstance(entry, dict):
                    entry = {}
                raw = entry.get("coherence") if entry.get("scorer_sha256") == fingerprint else None
                if raw == "inf":
                    value = float("inf")
                elif isinstance(raw, (int, float)) and raw > 0:
                    value = float(raw)
                else:
                    value = _compute_coherence_time(
                        hypothesis.name,
                        chart_id,
                        fingerprint,
                    )
                    values[hypothesis.name] = {
                        "scorer_sha256": fingerprint,
                        "coherence": "inf" if math.isinf(value) else value,
                    }
                    changed = True
                _COHERENCE_OVERRIDES[(hypothesis.name, fingerprint, chart_id)] = value
            if changed or not path.exists():
                temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                try:
                    with temp.open("x", encoding="utf-8") as output:
                        json.dump(
                            {
                                "schema": 2,
                                "namespace": namespace,
                                "values": values,
                            },
                            output,
                            sort_keys=True,
                        )
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temp, path)
                    secure_file(path)
                finally:
                    if temp.exists():
                        temp.unlink()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def gate(
    chart: Chart, hypothesis: Hypothesis, events: list[Event]
) -> tuple[list[Event], list[Event]]:
    """Split events into those this hypothesis may be scored against, and not."""
    _COHERENCE_HYPOTHESES[hypothesis.name] = hypothesis
    ct = coherence_time(hypothesis.name, register_chart(chart))
    keep, drop = [], []
    for e in events:
        (keep if ct >= event_uncertainty(e) else drop).append(e)
    return keep, drop


def precision_report(
    subject: Subject,
    hypotheses: list[Hypothesis],
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
) -> str:
    chart = subject.chart(ayanamsa=ayanamsa, node=node)
    warm_coherence_cache(chart, hypotheses)
    evs = [
        e
        for e in subject.events
        if not e.is_interval
        and getattr(e, "kind", "event") == "event"
        and not getattr(e, "contaminated", "")
    ]
    rows = []
    for h in hypotheses:
        ct = coherence_time(h.name, register_chart(chart))
        keep, drop = gate(chart, h, evs)
        rows.append((ct, h.name, len(keep), len(drop)))
    rows.sort()
    out = [
        f"  {len(evs)} scoreable point events",
        f"  {'technique':46s}{'coherence':>10s}{'usable':>8s}{'dropped':>9s}",
    ]
    for ct, name, k, d in rows:
        ctxt = "const" if ct == float("inf") else f"{ct:.0f}d"
        out.append(f"  {name[:45]:46s}{ctxt:>10s}{k:8d}{d:9d}")
    return "\n".join(out)
