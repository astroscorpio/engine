# jyotisha

A headless Jyotisha calculation engine with an explicit separation between:

- deterministic astronomical and rule calculations;
- exploratory retrospective tests;
- sealed prospective forecasts and trials.

The package does not treat a retrospective fit or an interpretive reading as
validated predictive evidence.

## Install

Python 3.12 or newer is required.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,research]"
.venv/bin/jyotisha doctor
.venv/bin/python verify.py
```

`requirements.lock` and `requirements-dev.lock` record the exact direct
dependency versions used for the current verification run.

[PySwissEph and Swiss Ephemeris](https://www.astro.com/swisseph/swephinfo_e.htm)
have their own dual-license terms. Configure and distribute them only under a
license appropriate to your use. Ephemeris files are not vendored here.

## Context is explicit

Natal calculations always use the recorded birth place and birth timezone.
Panchanga, prashna, annual-return houses, and current readings use the observer
context. Override that context with global options:

```bash
jyotisha \
  --timezone Europe/Paris \
  --lat 48.8566 \
  --lon 2.3522 \
  --place Paris \
  panchanga
```

The true lunar node is the declared default. Use global `--node mean` to run a
different node convention consistently through charts, transits, tests, and
trial manifests.

IANA timezones are DST-aware. Ambiguous or nonexistent local timestamps are
rejected unless an explicit UTC offset is supplied.

## Calculation and inspection

Commands run against the bundled `example` subject, whose birth data and events
are invented, unless `--subject` names another entry in `jyotisha/subjects.py`.

```bash
jyotisha chart
jyotisha dasha --on 2026-07-29T12:00:00+02:00
jyotisha transit --on 2026-07-29T12:00:00+02:00
jyotisha panchanga --on 2026-07-29T12:00:00+02:00
jyotisha --format json inspect --at 2026-07-29T12:00:00+02:00
jyotisha techniques
jyotisha techniques slow-transit-on-aspecting-domain
```

`inspect` is the canonical structured query. JSON, JSONL, and flat CSV are
emitted only by commands that support them; unsupported combinations fail
instead of mixing human text into machine-readable output.

## Muhurta

`muhurta` prints each day's windows. `--find ACT` instead judges every minute
of a span for one kind of act and ranks the windows no rule vetoes:

```bash
jyotisha muhurta --find general --at now --days 1 --by time   # "can I do it now?"
jyotisha muhurta --find education --until 2026-09-16 --hours 08:00-20:00
jyotisha muhurta --find travel --toward W --first-leg S --start 2026-09-22 --until 2026-09-28
```

Acts are `general` (applications, accounts, payments), `education`, `travel`
(needs `--toward`) and `home`. Vetoes: the kalams and durmuhurta, Vishti while
Bhadra resides on earth, the opening ghatis of the bad yogas, Rikta and Ashtami
tithis and Amavasya, Marana and Dagdha pairings, the Moon in the 8th or in
chandrashtama, and a journey's disha shool. Everything else is a weighted
defect: tara, panchaka, lagna shuddhi, choghadiya, hora, the act's favoured
nakshatras, tithis and weekdays, Pitru Paksha and adhika masa from the computed
amanta month, and for journeys the side the Moon and Yogini are on. The weights
order conventions; they are not measured effects.

## Retrospective inference

```bash
jyotisha backtest --nulls 999 --null-mode matched
jyotisha learn --domains education
```

Larger CLI backtests automatically use up to eight CPU worker processes;
`--workers 1` forces serial execution. The rule and ephemeris workload is
branch-heavy, so moving it to a GPU would add transfer and rewrite overhead
without changing the exact calculations.

Cost is dominated by ephemeris evaluations, not by rule logic, so each
uncertainty window is scanned on a grid derived from the technique's measured
coherence time rather than a fixed one-day step. A technique is never sampled
more finely than the old fixed grid, the observed and null statistics always
share one grid, and the first run for a given code version pays a one-off
thirty-year coherence probe that is then cached to disk.

The event backtest uses one common timeline shift per null replicate. That
preserves event gaps and clustering. Replicate indices are also aligned across
techniques, so the empirical max statistic controls the searched family
without assuming independent events or independent rules. Reports include:

- an empirical per-technique p-value;
- joint max-statistic FWER p-value;
- Benjamini-Hochberg q-value;
- Monte Carlo standard error.

Date-uncertainty windows are applied identically to observed and null events.
Notifications, markers, contaminated dates, and techniques too fast for the
recorded date precision are excluded by declared rules.

Learning uses complete half-open local-civil-day windows that end before the cutoff. Every
walk-forward fold fits its scaler on prior windows only. Future windows reuse
the historical scaler. Civil days are sampled at local noon, so daylight-saving
changes neither shift boundaries nor duplicate a date. A calendar model
containing season, weekday, and trend is the primary opponent. Positive
retrospective skill is only a signal for a prospective test, never a validation
claim.

All current classical technique encodings remain exploratory. `doctor` reports
missing exact source citations rather than silently presenting them as
textually verified.

## Readings

```bash
jyotisha predict --domain career --until 2027-06-01
```

`predict` answers "when, and on what grounds" rather than returning a bare
probability. It scores every registered technique across each window and
reports the ones standing out against *their own* history, so techniques on
different scales can be compared at all. The reference distribution is built
from rolling window peaks rather than daily values: a window is scored by its
maximum, so anything on a monthly cycle — the transiting Moon reaching a domain
sign — would otherwise sit near the top of the daily distribution in every
window and be called out every time.

Two figures are reported per window and deliberately kept apart:

- **domain** — the strongest techniques that actually respond to the question
  asked;
- **general** — the strongest techniques that do not.

Most of the library is domain-blind: it returns the same number whether the
question is a job, a move or a marriage. Those techniques move every domain
together whenever a dasha turns, so folding them into one score is what makes a
reading claim "everything is strong in October" about nothing in particular.
Lines marked `[all domains]` are carrying no information about the specific
question. Dasha period boundaries falling inside a window are flagged with
`**`, since a window containing one differs in kind from a window that merely
scores well.

## Forecasting

```bash
jyotisha forecast --domains career --ahead 2
```

The forecast always prints. Every window shows the model probability beside the
calendar opponent's probability and their ratio, so the comparison that decides
whether the model is worth anything is visible in the output itself rather than
enforced by suppressing it. A `lift` below 1.0 means the calendar opponent —
season, weekday and trend alone — assigns the event a higher probability than
the astrology model does.

Skill is still measured. `status` reports `prospective-test-eligible` only when
the model has enough scored windows and events and shows a positive HAC-tested
prequential loss gain over that opponent, and every sealed record carries its
skill metadata into the ledger. Displaying a probability is not a claim that it
is calibrated.

Predictions are one domain per record with explicit start, end, timezone,
opponent probability, model identifier, and provenance. `--seal` writes them
to the append-only ledger before their window starts.

## Prospective trials

Register a trial before its first window:

```bash
jyotisha trial register \
  --name career-v1 \
  --start 2026-09-01 \
  --end 2027-09-01 \
  --domains career \
  --techniques all \
  --polarity any \
  --min-magnitude 2 \
  --checkpoints 30,60,120
```

Registration freezes the code and subject hashes, model, ayanamsa, node,
timezone, window length, technique IDs, outcome definition, and fixed
checkpoints.
Forecasts attached with `--trial-id` must match that manifest exactly.
Checkpoints count complete forecast windows, not correlated domain records.

```bash
jyotisha trial list
jyotisha trial score --trial-id UUID
```

Trial efficacy compares sealed model and opponent log loss at the latest fixed
checkpoint, uses a HAC one-sided loss-gain test, and Bonferroni-corrects the
predeclared looks.

## Daily blind protocol

Rate the day before viewing same-day astrology:

```bash
jyotisha rate \
  --mood 3 \
  --energy 4 \
  --self-presentation 3 \
  --social-ease 4 \
  --focus 4
jyotisha ratings
```

Ratings cannot be backfilled or duplicated. Commands exposing astrology for
a civil date—including a future date—write a persistent exposure record,
which blocks a later rating for that date.
Formal analysis starts at day 120 and uses fixed checkpoints. Circular shifts
preserve the complete outcome sequence; one max statistic controls all tested
daily techniques and outcomes, followed by correction across all planned
checkpoints.

## Ledger and privacy

The ledger uses file locking, append-time chain verification, fsync, unique
prediction IDs, and mode `0600`. A local hash chain detects edits but cannot
prove wall time by itself:

```bash
jyotisha --format json anchor
```

Publish or externally timestamp that head commitment if independent timing
evidence is required.

Writable records use `JYOTISHA_DATA_DIR`, otherwise the XDG data directory.
An existing checkout ledger remains in place to avoid silently splitting its
history. Declared data snapshots use `JYOTISHA_RESOURCE_DIR`.

## Ephemeris backend

```bash
SE_EPHE_PATH=/licensed/path/to/ephe jyotisha doctor
```

The engine requests Swiss Ephemeris files and reports the backend actually
returned. If files are unavailable, the library may fall back to Moshier;
`doctor` exposes that fallback. Backend details are included in sealed
forecast provenance.

## Verification

```bash
ruff check jyotisha tests verify.py
pytest
python verify.py
```

The suite covers natal golden longitudes, DST edge cases, canonical
Ashtakavarga totals, all shodashavarga bounds, the independent
Sarvatobhadra reference, leakage and scaling invariants, dependence-aware
family correction, ledger protocol, daily blinding, structured CLI output,
and frozen trial manifests.

## Known evidence limits

- The bundled `example` subject is invented; its birth data and events are illustrative.
- Exact textual citations for the encoded classical rules are incomplete.
- A local ledger needs an external commitment receipt to establish timing.
- No current result establishes reliable life-event predictive skill.
