# Engineering and evidence audit

## Resolved correctness defects

- Fixed a coherence probe that reported varying techniques as constant. The
  probe ran five years with an event declaring all ten domains, which covers
  all twelve houses and pins every domain-conditional technique to a fixed
  value; the flat trace was then recorded as "immune to date error". Fifteen
  of sixty-one techniques were affected, twelve of them demonstrably varying.
  The gate consequently scored spiky techniques against quarter-precision
  events it should have dropped. The probe now runs thirty years, one domain
  at a time, and keeps the fastest decorrelation. Two techniques remain
  genuinely constant for the development subject and are excluded as degenerate.
- Registered four rare chakras that were implemented but unreachable. Kota
  chakra, the bhrigu bindu, moorthi nirnaya and latta were computed in
  `rare.py` and printed by the `rare` command, but were absent from the
  technique library. The forecast feature matrix is built from that same
  library, so a reading full of those signals had no path into the number the
  forecast produced. Each is restricted to the slow grahas, because the
  Moon-driven form repoints daily and cannot be tested against events dated to
  a month or a quarter. Wiring them changed the career forecast lift from
  0.52x to 0.81x against the calendar opponent, which is a change in the model,
  not evidence for it; the forecast still abstains.
- Keyed technique provenance by id instead of by list position. Introduction
  dates and discovery exclusions were assigned by slicing `LIBRARY`, so
  removing any earlier technique silently relabelled unrelated entries. The
  registry test had the same defect and asserted against whatever happened to
  occupy positions 51 to 57.
- Removed the independence-based event-combination formula.
- Replaced independent event draws with common full-timeline shifts.
- Added empirical joint max-statistic correction across techniques and,
  where searched, ayanamsas or birth-time candidates.
- Removed a second-rank family-correction artifact that could force unrelated
  techniques to the Monte Carlo significance floor.
- Prevented training windows from crossing the cutoff.
- Kept learning and trial grids on local civil midnights across DST changes.
- Fit standardization inside each historical fold and reused the historical
  scaler for future windows.
- Added a calendar opponent and HAC-tested prequential loss comparison.
- Excluded contaminated, imprecise, trivial, interval, notification, and
  marker outcomes from binary learning labels.
- Split natal, observer, and event time/location contexts.
- Made the true/mean lunar-node convention explicit and consistent through
  charts, transits, backtests, forecasts, and frozen trials.
- Routed location-dependent current rare-day timings through the observer
  coordinates instead of formatting birth-place calculations in the
  observer's time zone.
- Added IANA timezone support and rejection of ambiguous/nonexistent wall
  times.
- Corrected hora calculation to twelve daylight and twelve nighttime parts.
- Removed arbitrary scheduled horary casts.
- Corrected Tajika applying/separating detection to use relative angular
  motion across sign boundaries.
- Corrected annual-return chart location handling.
- Made rectification one jointly corrected search across techniques and birth
  times.

## Deliberate protocol changes

- The forecast no longer abstains. It previously refused to display a
  probability unless the model beat the calendar opponent on a HAC-tested
  prequential loss gain. That test still runs, still sets `status`, and still
  travels into the ledger with every sealed record, but it no longer suppresses
  output, and the `--experimental` flag it gated is gone. This is an owner's
  decision about display, taken knowingly: every window now prints the model
  probability, the calendar opponent's probability, and their ratio, so a model
  that is worse than season-and-weekday shows a lift below 1.0 in the output
  instead of being hidden behind a refusal. Nothing about sealing, resolution,
  trial scoring, or the daily blind protocol changed — a displayed probability
  is not a validated one, and the ledger still records which it is.

## Resolved protocol and integrity defects

- Predictions must be prospective, bounded, probabilistic, single-domain,
  unique, and provenance-bearing.
- Outcomes target exact prediction IDs; early no-event, pre-window, duplicate,
  future, and out-of-window resolutions are rejected.
- The ledger validates its chain under a file lock before append, flushes with
  `fsync`, and uses mode `0600`.
- Daily ratings are same-day, non-backfillable, unique, and blocked after a
  persistent exposure for that date, even if the forecast was viewed earlier.
- Daily analysis preserves serial dependence, controls the searched
  technique/outcome family, and corrects all fixed checkpoints.
- Trial registration freezes code, subject, model, technique, context,
  endpoint, and checkpoint configuration; attached forecasts cannot drift.
- Trial windows must match the frozen duration and grid; efficacy checkpoints
  count only windows with every frozen domain resolved.
- A ledger head can be exported honestly as a commitment, without claiming
  that a local hash proves wall time.

## Resolved operational defects

- Added `pyproject.toml`, console entry point, pinned verification
  environments, CI, linting, and regression tests.
- Added canonical JSON inspection and explicit failures for unsupported
  machine-output combinations.
- Added dependency, code, subject, configuration, and actual ephemeris-backend
  provenance to sealed forecasts.
- Added checksums for declared data snapshots and warnings for provenance
  gaps.
- Removed redundant Swiss-Ephemeris work from Sarvatobhadra scoring and cached
  repeated static/dasha calculations without lowering timestamp precision.
- Scaled uncertainty-window scans to each technique's coherence time instead of
  a fixed one-day grid. A quarter-precision window previously cost ninety-one
  ephemeris evaluations for techniques that cannot move that fast. Against a
  0.125-day reference grid the new scan tracks the reference more closely than
  the fixed grid it replaces (max deviation 0.021 versus 0.041) while
  evaluating fewer points. The observed and null statistics share one grid, so
  the comparison stays symmetric, and both controls keep their previous
  p-values.
- Memoised per-instance graha sign/degree/nakshatra/pada, the civil-day window
  half-width, and sustained-state span; replaced `strptime` on the date-only
  parse path. Verified bit-identical against a stored family run.
- Retired nine techniques on structural grounds, never on their p-values.
  Two could not vary at all for the development subject: no graha in that chart is
  vargottama, and the special-lagna rule held one value across a thirty-year
  probe. Four duplicated a technique already registered, measured on a
  twenty-seven-year daily grid: both chara-dasha conventions against Narayana
  dasha (r = 0.91 and 0.81), sthira against shoola dasha (r = 0.76), and
  vimshopaka bala against shadbala (r = 0.83). Three were generic almanac
  binaries — tara bala, chandra bala and guru bala — each a two-state coin
  flip, and the first two decorrelate in a day, so only the seventeen
  day-precision events could carry them at all. Three of the nine held the
  best raw p-values in the family at the time of removal, which is the
  opposite of outcome-driven pruning; none survived family correction, and the
  Monte Carlo floor at 40 replicates is 0.024. The D-60 shashtiamsa was
  written and deliberately left unregistered for the reasons recorded beside
  it in `hypotheses.py`.
- Removed the group-comparison corpus path: `corpus.py`, `grouptest.py`,
  `mortality.py`, and `features.py` had no importer anywhere in the package,
  tests, or CLI, and the 24 data files they read were unreachable. That
  retired the Gauquelin volumes and the Wikidata mortality snapshot, whose
  incomplete retrieval provenance was a standing evidence blocker. The corpus
  carried birth data without recorded life events, so it could not feed the
  event-window inference this package now rests on. `data/` now holds only the
  Sarvatobhadra reference table and its manifest.

## Open evidence blockers

These cannot be repaired honestly by adding code or inventing metadata:

- 56 classical scorer encodings lack exact source citations and convention
  verification. No technique carries a `source` or `convention` field; the
  docstrings are the only record of what each one encodes.
- Without SE_EPHE_PATH the engine falls back to Moshier. astroscorpio runs it
  with the Swiss Ephemeris data files (AGPL edition; see engine/ephe).
- Existing event counts and prospective outcomes do not demonstrate reliable
  incremental forecast skill.

`jyotisha doctor` reports these conditions. They are warnings or evidence
limits, not hidden assumptions.
