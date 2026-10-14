"""Append-only forecast and observation ledger.

The local hash chain detects accidental edits. A head commitment can also be
exported for publication or an external timestamping service; without that
external receipt, the chain is not claimed to prove authorship or wall time.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import uuid
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

from .storage import ensure_private_parent, secure_file, user_path

SCHEMA_VERSION = 2


def ledger_path() -> Path:
    return user_path("ledger.jsonl")


def _hash(payload: dict, prev: str) -> str:
    blob = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=payload.get("schema", 1) < 2,
    )
    return hashlib.sha256((prev + blob).encode()).hexdigest()


def _decode(text: str) -> list[dict]:
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid ledger JSON at line {line_number}") from exc
    return rows


def _read() -> list[dict]:
    path = ledger_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        try:
            return _decode(fh.read())
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _chain_error(rows: list[dict]) -> str | None:
    prev = "genesis"
    for i, row in enumerate(rows):
        if "prev" not in row or "hash" not in row:
            return f"record {i + 1} lacks chain fields"
        payload = {k: v for k, v in row.items() if k not in ("prev", "hash")}
        if row["prev"] != prev or row["hash"] != _hash(payload, prev):
            return f"chain broken at record {i + 1}"
        prev = row["hash"]
    return None


def _append(
    kind: str,
    body: dict,
    *,
    validator: Callable[[list[dict]], None] | None = None,
) -> dict:
    path = ledger_path()
    ensure_private_parent(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            rows = _decode(fh.read())
            error = _chain_error(rows)
            if error:
                raise ValueError(f"refusing to append: {error}")
            if validator:
                validator(rows)
            prev = rows[-1]["hash"] if rows else "genesis"
            payload = {
                "schema": SCHEMA_VERSION,
                "kind": kind,
                "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                **body,
            }
            record = {
                **payload,
                "prev": prev,
                "hash": _hash(payload, prev),
            }
            fh.seek(0, os.SEEK_END)
            fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            secure_file(path)
            return record
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _zone(timezone: str | float) -> dt.tzinfo:
    if isinstance(timezone, str):
        return ZoneInfo(timezone)
    return dt.timezone(dt.timedelta(hours=float(timezone)))


def _civil_datetime(stamp: str, timezone: str | float) -> dt.datetime:
    value = stamp.strip().replace("Z", "+00:00")
    parsed: dt.datetime
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(value, "%d %b %Y")
        except ValueError as exc:
            raise ValueError(f"invalid civil timestamp {stamp!r}; use ISO-8601") from exc
    if parsed.tzinfo is None:
        zone = _zone(timezone)
        if isinstance(zone, ZoneInfo):
            candidates = []
            for fold in (0, 1):
                candidate = parsed.replace(tzinfo=zone, fold=fold)
                if candidate.astimezone(dt.UTC).astimezone(zone).replace(
                    tzinfo=None
                ) == parsed and all(
                    existing.astimezone(dt.UTC) != candidate.astimezone(dt.UTC)
                    for existing in candidates
                ):
                    candidates.append(candidate)
            if len(candidates) != 1:
                condition = "nonexistent" if not candidates else "ambiguous"
                raise ValueError(
                    f"{condition} local time {parsed.isoformat(sep=' ')} in {zone.key}; "
                    "use an explicit UTC offset"
                )
            parsed = candidates[0]
        else:
            parsed = parsed.replace(tzinfo=zone)
    return parsed


def predict(
    subject: str,
    window_start: str,
    window_end: str,
    domain: str,
    probability: float,
    base_rate: float,
    model: str,
    note: str = "",
    *,
    timezone: str | float = "UTC",
    trial_id: str = "",
    provenance: dict | None = None,
    experimental: bool = False,
    _now: dt.datetime | None = None,
) -> dict:
    start = _civil_datetime(window_start, timezone)
    end = _civil_datetime(window_end, timezone)
    current = _now or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.UTC)
    if end <= start:
        raise ValueError("prediction window end must follow its start")
    if start.astimezone(dt.UTC) <= current.astimezone(dt.UTC):
        raise ValueError("cannot seal a prediction after its window begins")
    if not 0 <= probability <= 1 or not 0 <= base_rate <= 1:
        raise ValueError("probability and base_rate must be in [0, 1]")
    if not domain or "," in domain:
        raise ValueError("seal one explicit domain per prediction")
    if trial_id:
        from . import trials

        if not provenance:
            raise ValueError("trial predictions require a provenance manifest")
        trials.validate_prediction(
            trial_id,
            domain=domain,
            window_start=start.isoformat(),
            window_end=end.isoformat(),
            technique_ids=provenance.get("technique_ids", []),
            manifest=provenance,
            model=model,
        )
    prediction_id = str(uuid.uuid4())
    body = {
        "prediction_id": prediction_id,
        "subject": subject,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "timezone": str(timezone),
        "domain": domain,
        "probability": round(float(probability), 6),
        "base_rate": round(float(base_rate), 6),
        "model": model,
        "trial_id": trial_id,
        "experimental": bool(experimental),
        "provenance": provenance or {},
        "note": note,
    }

    def unique(rows: list[dict]) -> None:
        for row in rows:
            if row.get("kind") != "prediction":
                continue
            if (
                row.get("subject") == subject
                and row.get("window_start") == body["window_start"]
                and row.get("domain") == domain
                and row.get("trial_id", "") == trial_id
            ):
                raise ValueError("duplicate prediction for subject/window/domain/trial")

    return _append("prediction", body, validator=unique)


def resolve(
    window_start: str | None,
    domain: str | None,
    occurred: bool,
    detail: str = "",
    *,
    prediction_id: str | None = None,
    occurrence_at: str | None = None,
    polarity: int | None = None,
    magnitude: int | None = None,
    source: str = "",
    _now: dt.datetime | None = None,
) -> dict:
    rows = _read()
    predictions = [r for r in rows if r.get("kind") == "prediction"]
    if prediction_id:
        matches = [r for r in predictions if r.get("prediction_id") == prediction_id]
    else:
        matches = [
            r
            for r in predictions
            if r.get("window_start") == window_start and r.get("domain") == domain
        ]
    if len(matches) != 1:
        raise ValueError(
            f"resolution target is {'missing' if not matches else 'ambiguous'}; "
            "use an exact prediction_id"
        )
    prediction = matches[0]
    prediction_id = prediction.get("prediction_id")
    if not prediction_id:
        prediction_id = "legacy:" + prediction["hash"]
    current = _now or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.UTC)
    start = _civil_datetime(
        prediction["window_start"],
        prediction.get("timezone", "UTC"),
    )
    end = _civil_datetime(prediction["window_end"], prediction.get("timezone", "UTC"))
    if current.astimezone(dt.UTC) < start.astimezone(dt.UTC):
        raise ValueError("cannot resolve a prediction before its window begins")
    if not occurred and current.astimezone(dt.UTC) < end.astimezone(dt.UTC):
        raise ValueError("cannot resolve a still-open window as no-event")
    if not occurred and occurrence_at:
        raise ValueError("a no-event outcome cannot carry occurrence_at")
    if polarity is not None and polarity not in {-1, 0, 1}:
        raise ValueError("polarity must be -1, 0, or 1")
    if magnitude is not None and magnitude not in range(1, 6):
        raise ValueError("magnitude must be 1..5")
    normalized_occurrence = None
    if occurrence_at:
        occurrence = _civil_datetime(
            occurrence_at,
            prediction.get("timezone", "UTC"),
        )
        if not start <= occurrence < end:
            raise ValueError("occurrence_at must fall inside the prediction window")
        if occurrence.astimezone(dt.UTC) > current.astimezone(dt.UTC):
            raise ValueError("occurrence_at cannot be in the future")
        normalized_occurrence = occurrence.isoformat()
    if prediction.get("trial_id") and occurred:
        from . import trials

        trial = trials.get(prediction["trial_id"])
        if not normalized_occurrence or polarity is None or magnitude is None or not source.strip():
            raise ValueError("trial events require occurrence_at, polarity, magnitude, and source")
        required_polarity = {
            "any": None,
            "gain": 1,
            "loss": -1,
            "neutral": 0,
        }[trial["polarity"]]
        if required_polarity is not None and polarity != required_polarity:
            raise ValueError("event polarity does not match the frozen trial endpoint")
        if magnitude < trial["min_magnitude"]:
            raise ValueError("event magnitude is below the frozen trial endpoint")
    body = {
        "prediction_id": prediction_id,
        "window_start": prediction["window_start"],
        "domain": prediction["domain"],
        "occurred": bool(occurred),
        "occurrence_at": normalized_occurrence,
        "polarity": polarity if occurred else None,
        "magnitude": magnitude if occurred else None,
        "source": source.strip() if occurred else "",
        "detail": detail,
    }

    def unresolved(current_rows: list[dict]) -> None:
        if any(
            r.get("kind") == "outcome" and r.get("prediction_id") == prediction_id
            for r in current_rows
        ):
            raise ValueError(f"prediction {prediction_id} is already resolved")

    return _append("outcome", body, validator=unresolved)


def verify() -> tuple[bool, str]:
    rows = _read()
    error = _chain_error(rows)
    if error:
        return False, error
    return True, f"chain intact ({len(rows)} records)"


def records(kind: str | None = None) -> list[dict]:
    rows = _read()
    return rows if kind is None else [r for r in rows if r.get("kind") == kind]


def head_commitment() -> dict:
    rows = _read()
    error = _chain_error(rows)
    if error:
        raise ValueError(error)
    return {
        "schema": 1,
        "ledger_records": len(rows),
        "ledger_head": rows[-1]["hash"] if rows else "genesis",
        "generated_at": dt.datetime.now(dt.UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "warning": (
            "Publish or externally timestamp this commitment. A local copy "
            "alone is not independent proof of time."
        ),
    }


def scored_pairs() -> list[dict]:
    rows = _read()
    predictions = [r for r in rows if r.get("kind") == "prediction"]
    by_id = {r.get("prediction_id", "legacy:" + r["hash"]): r for r in predictions}
    outcomes_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("kind") == "outcome" and row.get("prediction_id"):
            outcomes_by_id[row["prediction_id"]].append(row)
    pairs = []
    for prediction_id, prediction in by_id.items():
        outcomes = outcomes_by_id.get(prediction_id, [])
        if len(outcomes) == 1:
            outcome = outcomes[0]
            pairs.append(
                {
                    **prediction,
                    "occurred": outcome["occurred"],
                    "occurrence_at": outcome.get("occurrence_at"),
                    "outcome_polarity": outcome.get("polarity"),
                    "outcome_magnitude": outcome.get("magnitude"),
                    "outcome_source": outcome.get("source", ""),
                    "detail": outcome.get("detail", ""),
                }
            )

    # Legacy outcomes are accepted only for an unambiguous legacy prediction.
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for prediction in predictions:
        grouped[
            (
                prediction.get("window_start", ""),
                prediction.get("domain", ""),
            )
        ].append(prediction)
    for outcome in rows:
        if outcome.get("kind") != "outcome" or outcome.get("prediction_id"):
            continue
        matches = grouped.get((outcome.get("window_start", ""), outcome.get("domain", "")), [])
        if len(matches) == 1:
            pairs.append(
                {
                    **matches[0],
                    "occurred": outcome["occurred"],
                    "occurrence_at": outcome.get("occurrence_at"),
                    "outcome_polarity": outcome.get("polarity"),
                    "outcome_magnitude": outcome.get("magnitude"),
                    "outcome_source": outcome.get("source", ""),
                    "detail": outcome.get("detail", ""),
                }
            )
    return pairs


def scoreboard() -> str:
    import numpy as np

    from .learn import brier, log_score

    ok, message = verify()
    lines = [
        f"  ledger: {message}",
    ]
    if not ok:
        lines.append("  REFUSING TO SCORE -- the chain does not verify")
        return "\n".join(lines)
    pairs = scored_pairs()
    lines.append(f"  unique resolved forecasts: {len(pairs)}")
    if len(pairs) < 30:
        lines.append("  too few to estimate skill; need at least 30 unique resolutions")
        return "\n".join(lines)
    y = np.array([1.0 if p["occurred"] else 0.0 for p in pairs])
    model_p = np.array([p["probability"] for p in pairs])
    base_p = np.array([p["base_rate"] for p in pairs])
    model_loss, base_loss = log_score(y, model_p), log_score(y, base_p)
    skill = 1 - model_loss / base_loss if base_loss > 0 else 0.0
    lines += [
        f"  base rate observed  {y.mean():.3f}",
        f"  log score model     {model_loss:.4f}",
        f"  log score opponent  {base_loss:.4f}",
        f"  skill               {skill:+.4f}",
        f"  Brier model/base    {brier(y, model_p):.4f} / {brier(y, base_p):.4f}",
        "",
        "  descriptive only; use a frozen trial checkpoint for an efficacy claim",
    ]
    return "\n".join(lines)
