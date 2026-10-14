"""Daily self-ratings, and the only layer in this package with enough events
to ever reach statistical power on one nativity.

The problem this solves.  Career and recognition events happen roughly four
times in seven years.  No amount of technique fixes that: with four positives
the walk-forward scorer cannot distinguish a real effect from luck, and the
guard in ``learn.report`` will correctly refuse to claim anything for years.

But a large part of the classical apparatus makes *daily* claims -- the tithi
class, the nine-fold tara cycle, chandra bala, the weekday, the Moon's house.
Those are testable at one observation per day.  A year of honest ratings is
365 observations against techniques that predict every one of them.  That is
the only route from "this fits my life" to a number with a p-value on it.

The ratings have to be logged *before* the day's astrology is viewed, or this
measures suggestion rather than astrology. Exposure and ratings are therefore
recorded in the same verified ledger, and an exposure blocks a later rating
for that local day.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict, dataclass

import numpy as np

from . import panchanga as P
from .chart import SIGN_LORDS, Chart
from .ephemeris import TimeZone, now, parse
from .subjects import Subject

FORMAL_CHECKPOINTS = (120, 240, 365, 540, 730, 1095, 1460)

# The five-fold tithi classification.  Rikta ("empty") is the one the texts
# single out as unfit for beginning anything.
TITHI_CLASS = {1: "Nanda", 2: "Bhadra", 3: "Jaya", 4: "Rikta", 5: "Purna"}
TARA = ["Janma", "Sampat", "Vipat", "Kshema", "Pratyari", "Sadhaka", "Vadha", "Mitra", "Ati-mitra"]
TARA_GOOD = {1, 3, 5, 7, 8}

# What to rate.  Deliberately short -- a long form gets abandoned, and an
# abandoned log is worse than none because the days that get skipped are not
# a random sample of days.
FIELDS = ("mood", "energy", "self_presentation", "social_ease", "focus")


@dataclass
class Rating:
    date: str  # YYYY-MM-DD
    mood: int  # 1 low .. 5 high
    energy: int
    self_presentation: int  # how much you attended to how you looked
    social_ease: int
    focus: int
    note: str = ""
    rated_at: str = ""
    timezone: str = ""
    rating_id: str = ""

    def validate(self) -> None:
        for f in FIELDS:
            v = getattr(self, f)
            if not isinstance(v, int) or not 1 <= v <= 5:
                raise ValueError(f"{f} must be an integer 1-5, got {v!r}")


def log(
    rating: Rating,
    *,
    timezone: TimeZone,
    allow_backfill: bool = False,
    _now: dt.datetime | None = None,
) -> dict:
    """Seal one rating as the canonical ledger record."""
    from . import ledger

    rating.validate()
    current = _now or now(timezone)
    local_date = current.date().isoformat()
    if rating.date != local_date and not allow_backfill:
        raise ValueError(
            f"ratings must be sealed on their local day ({local_date}); backfill is disabled"
        )
    rating.rated_at = current.isoformat(timespec="seconds")
    rating.timezone = str(timezone)
    rating.rating_id = rating.rating_id or str(uuid.uuid4())
    row = asdict(rating)

    def protocol_guard(rows: list[dict]) -> None:
        if any(r.get("kind") == "daily_rating" and r.get("date") == rating.date for r in rows):
            raise ValueError(f"a rating for {rating.date} already exists")
        if any(r.get("kind") == "daily_exposure" and r.get("date") == rating.date for r in rows):
            raise ValueError(
                "today's astrology output was already exposed; rating would not be blind"
            )

    ledger._append("daily_rating", row, validator=protocol_guard)
    return row


def load() -> list[dict]:
    """Verified, non-retracted ratings from the canonical ledger."""
    from . import ledger

    ok, message = ledger.verify()
    if not ok:
        raise ValueError(f"refusing to load ratings: {message}")
    rows = ledger.records()
    retracted = {
        r.get("retracts", "").removeprefix("daily_rating ")
        for r in rows
        if r.get("kind") == "retraction" and r.get("retracts", "").startswith("daily_rating ")
    }
    latest: dict[str, dict] = {}
    for row in rows:
        if row.get("kind") == "daily_rating" and row.get("date") not in retracted:
            latest[row["date"]] = {
                key: value
                for key, value in row.items()
                if key not in ("kind", "schema", "at", "prev", "hash")
            }
    return list(latest.values())


def record_exposure(date: str, command: str) -> None:
    """Record that astrological information for a civil date was displayed."""
    from . import ledger

    class ExposureExists(Exception):
        pass

    def unique(rows: list[dict]) -> None:
        if any(
            row.get("kind") == "daily_exposure"
            and row.get("date") == date
            and row.get("command") == command
            for row in rows
        ):
            raise ExposureExists

    try:
        ledger._append(
            "daily_exposure",
            {"date": date, "command": command},
            validator=unique,
        )
    except ExposureExists:
        return


# --- the daily techniques, each returning one number per day ----------------


def features(subject: Subject, chart: Chart, date: str) -> dict[str, float]:
    """Every technique in the package that makes a claim about a single day."""
    context = subject.observer_context
    jd = parse(date + " 12:00", context.timezone)
    pc = P.compute(jd, context.lat, context.lon, chart.ayanamsa)
    from .hypotheses import transit

    moving = transit(chart, jd)
    natal_nak = chart.grahas["Moon"].nakshatra
    tara = ((moving["Moon"].nakshatra - natal_nak) % 27) % 9
    moon_h = (moving["Moon"].sign - chart.asc.sign) % 12 + 1
    moon_from_moon = (moving["Moon"].sign - chart.grahas["Moon"].sign) % 12 + 1
    t_in_paksha = ((pc.tithi - 1) % 15) + 1

    # The sarvatobhadra chakra is the only classical technique here that
    # decorrelates inside a week (five days at pada resolution), so it is the
    # only one a daily rating can test at its own timescale rather than
    # smeared across a season.
    from . import sbc

    natal_pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    natal_cells = sbc.natal_cells(chart, sbc.tithi_group(natal_pc.tithi), natal_pc.vara)
    janma = {c: w for c, w in natal_cells.items() if w in ("janma nakshatra", "janma rasi")}
    janma_hits = sbc.strikes(chart, jd, janma, moving=moving)

    return {
        "sbc_janma_clear": 0.0 if any(not h.benefic for h in janma_hits) else 1.0,
        "sbc_janma_net": float(sum(1 if h.benefic else -1 for h in janma_hits)),
        "sbc_net_vedha": float(sbc.score(chart, jd, natal_cells, moving=moving)),
        "tithi_class_rikta": 1.0 if t_in_paksha % 5 == 4 else 0.0,
        "tithi_class_jaya": 1.0 if t_in_paksha % 5 == 3 else 0.0,
        "tithi_class_nanda": 1.0 if t_in_paksha % 5 == 1 else 0.0,
        "shukla_paksha": 1.0 if pc.paksha.startswith("shukla") else 0.0,
        "tara_bala_good": 1.0 if tara in TARA_GOOD else 0.0,
        "chandra_bala": 1.0 if moon_from_moon in (1, 3, 6, 7, 10, 11) else 0.0,
        "moon_house_kendra": 1.0 if moon_h in (1, 4, 7, 10) else 0.0,
        "moon_house_dusthana": 1.0 if moon_h in (6, 8, 12) else 0.0,
        "moon_house_upachaya": 1.0 if moon_h in (3, 6, 10, 11) else 0.0,
        "vara_lord_benefic": 1.0 if pc.vara in ("Moon", "Mercury", "Jupiter", "Venus") else 0.0,
        "lagna_lord_angular": (
            1.0 if _graha_house(chart, moving, SIGN_LORDS[chart.asc.sign]) in (1, 4, 7, 10) else 0.0
        ),
        "moon_longitude_speed": float(moving["Moon"].speed),
        "sun_moon_phase_sin": float(
            np.sin(np.deg2rad((moving["Moon"].longitude - moving["Sun"].longitude) % 360))
        ),
        "sun_moon_phase_cos": float(
            np.cos(np.deg2rad((moving["Moon"].longitude - moving["Sun"].longitude) % 360))
        ),
    }


def _graha_house(chart: Chart, moving, name: str) -> int:
    return (moving[name].sign - chart.asc.sign) % 12 + 1


def matrix(
    subject: Subject,
    rows: list[dict],
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
) -> tuple[np.ndarray, list[str]]:
    chart = subject.chart(ayanamsa=ayanamsa, node=node)
    feats = [features(subject, chart, r["date"]) for r in rows]
    names = list(feats[0])
    X = np.array([[float(f[n]) for n in names] for f in feats])
    return X, names


def analyze(
    subject: Subject,
    field: str = "all",
    n_perm: int = 5000,
    seed: int = 7,
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
) -> dict:
    """Correlate daily techniques with ratings using fixed-look inference.

    Circular shifts preserve serial dependence in the complete outcome
    sequence. A max statistic controls the searched techniques and outcomes;
    Bonferroni across the predeclared checkpoints controls repeated looks.
    """
    if n_perm < 1:
        raise ValueError("n_perm must be positive")
    rows = sorted(load(), key=lambda r: r["date"])
    n_logged = len(rows)
    checkpoint = max((n for n in FORMAL_CHECKPOINTS if n <= len(rows)), default=0)
    if checkpoint == 0:
        return {
            "status": "collecting",
            "n_logged": n_logged,
            "next_checkpoint": FORMAL_CHECKPOINTS[0],
            "checkpoint": 0,
            "outcomes": [],
            "n_null": 0,
            "checkpoint_correction": len(FORMAL_CHECKPOINTS),
            "techniques": [],
        }
    rows = rows[:checkpoint]
    fields = list(FIELDS) if field == "all" else [field]
    unknown = [name for name in fields if name not in FIELDS]
    if unknown:
        raise ValueError(f"unknown rating field {unknown[0]!r}")
    Y = np.column_stack([np.array([float(r[name]) for r in rows]) for name in fields])
    X, names = matrix(subject, rows, ayanamsa=ayanamsa, node=node)
    X = (X - X.mean(0)) / np.where(X.std(0) < 1e-9, 1.0, X.std(0))
    Y = (Y - Y.mean(0)) / np.where(Y.std(0) < 1e-9, 1.0, Y.std(0))
    obs_matrix = np.abs(X.T @ Y) / len(rows)
    obs = obs_matrix.max(axis=1)

    # Circular shifts preserve the complete rating sequence, including its
    # serial dependence. Repeating a shift cannot manufacture resolution, so
    # use each admissible shift once.
    min_shift = max(7, int(round(len(rows) ** (1 / 3))))
    shifts = np.arange(min_shift, len(rows) - min_shift + 1)
    if len(shifts) > n_perm:
        rng = np.random.default_rng(seed)
        shifts = np.sort(rng.choice(shifts, n_perm, replace=False))
    null_max = np.array(
        [np.abs(X.T @ np.roll(Y, int(shift), axis=0)).max() / len(rows) for shift in shifts]
    )

    techniques = []
    order = np.argsort(-obs)
    for j in order:
        raw_p = float((np.sum(null_max >= obs[j]) + 1) / (len(null_max) + 1))
        formal_p = min(1.0, raw_p * len(FORMAL_CHECKPOINTS))
        techniques.append(
            {
                "technique": names[j],
                "max_abs_r": float(obs[j]),
                "within_checkpoint_fwer_p": raw_p,
                "formal_fwer_p": formal_p,
                "survives": formal_p < 0.05,
            }
        )
    return {
        "status": "complete",
        "n_logged": n_logged,
        "checkpoint": checkpoint,
        "next_checkpoint": next(
            (value for value in FORMAL_CHECKPOINTS if value > checkpoint),
            None,
        ),
        "outcomes": fields,
        "n_null": len(null_max),
        "checkpoint_correction": len(FORMAL_CHECKPOINTS),
        "techniques": techniques,
    }


def score(
    subject: Subject,
    field: str = "all",
    n_perm: int = 5000,
    seed: int = 7,
    *,
    ayanamsa: str = "lahiri",
    node: str = "true",
) -> str:
    """Human-readable wrapper around :func:`analyze`."""
    result = analyze(
        subject,
        field=field,
        n_perm=n_perm,
        seed=seed,
        ayanamsa=ayanamsa,
        node=node,
    )
    if result["status"] == "collecting":
        return (
            f"  {result['n_logged']} valid days logged. Formal inference starts at "
            f"{result['next_checkpoint']} on a fixed checkpoint schedule."
        )
    out = [
        f"  outcomes={','.join(result['outcomes'])}; "
        f"checkpoint={result['checkpoint']} days; nulls={result['n_null']}",
        f"  {'technique':32s}{'max |r|':>8s}{'formal p':>10s}",
    ]
    for row in result["techniques"]:
        flag = "  <-- survives" if row["survives"] else ""
        out.append(
            f"  {row['technique'][:31]:32s}{row['max_abs_r']:8.3f}"
            f"{row['formal_fwer_p']:10.4f}{flag}"
        )
    if not any(row["survives"] for row in result["techniques"]):
        out.append("")
        out.append(
            "  Nothing survives correction. With enough days that is a "
            "real answer, not a failure to find one."
        )
    return "\n".join(out)
