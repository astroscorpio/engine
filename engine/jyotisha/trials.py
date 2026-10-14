"""Immutable prospective trial registration."""

from __future__ import annotations

import datetime as dt
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from . import hypotheses, ledger, provenance
from .learn import brier, hac_one_sided, log_score
from .subjects import DOMAINS, Subject


def _instant(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("trial timestamps must carry an explicit UTC offset")
    return parsed


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown IANA timezone {value!r}") from exc


def register(
    subject: Subject,
    *,
    name: str,
    start: str,
    end: str,
    domains: list[str],
    technique_ids: list[str],
    endpoint: str,
    polarity: str,
    min_magnitude: int,
    checkpoints: list[int],
    ayanamsa: str,
    node: str,
    timezone: str,
    window_days: int,
    model: str,
    _now: dt.datetime | None = None,
) -> dict:
    if not name.strip():
        raise ValueError("trial name is required")
    invalid_domains = [domain for domain in domains if domain not in DOMAINS]
    if invalid_domains:
        raise ValueError(f"unknown domain {invalid_domains[0]!r}")
    if not domains:
        raise ValueError("at least one trial domain is required")
    if domains != list(dict.fromkeys(domains)):
        raise ValueError("trial domains must be unique")
    if not technique_ids:
        raise ValueError("at least one technique must be frozen")
    if technique_ids != list(dict.fromkeys(technique_ids)):
        raise ValueError("trial techniques must be unique")
    for technique_id in technique_ids:
        hypotheses.by_id(technique_id)
    zone = _zone(timezone)
    start_dt, end_dt = _instant(start), _instant(end)
    for label, value in (("start", start_dt), ("end", end_dt)):
        if value.utcoffset() != value.astimezone(zone).utcoffset():
            raise ValueError(f"trial {label} offset disagrees with timezone {timezone!r}")
    current = _now or dt.datetime.now(dt.UTC)
    if start_dt.astimezone(dt.UTC) <= current.astimezone(dt.UTC):
        raise ValueError("a prospective trial must be registered before start")
    if end_dt <= start_dt:
        raise ValueError("trial end must follow start")
    if endpoint != "forecast-windows":
        raise ValueError("only the forecast-windows endpoint is implemented")
    if polarity not in {"any", "gain", "loss", "neutral"}:
        raise ValueError("invalid polarity")
    if min_magnitude not in range(1, 6):
        raise ValueError("min_magnitude must be 1..5")
    if not checkpoints:
        raise ValueError("at least one checkpoint is required")
    if checkpoints != sorted(set(checkpoints)) or any(value < 1 for value in checkpoints):
        raise ValueError("checkpoints must be sorted unique positive integers")
    if window_days < 1:
        raise ValueError("window_days must be positive")
    if node not in {"true", "mean"}:
        raise ValueError("node must be 'true' or 'mean'")
    if not model:
        raise ValueError("model identifier is required")
    trial_id = str(uuid.uuid4())
    config = {
        "name": name.strip(),
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "domains": domains,
        "technique_ids": technique_ids,
        "endpoint": endpoint,
        "polarity": polarity,
        "min_magnitude": min_magnitude,
        "checkpoints": checkpoints,
        "ayanamsa": ayanamsa,
        "node": node,
        "timezone": timezone,
        "window_days": window_days,
        "model": model,
        "efficacy_test": "HAC-log-loss-gain; Bonferroni-fixed-checkpoints",
    }
    body = {
        "trial_id": trial_id,
        "subject": subject.name,
        **config,
        "provenance": provenance.manifest(subject, technique_ids=technique_ids, config=config),
    }

    def unique(rows: list[dict]) -> None:
        if any(
            row.get("kind") == "trial_registration" and row.get("name") == name.strip()
            for row in rows
        ):
            raise ValueError(f"trial name {name!r} is already registered")

    return ledger._append("trial_registration", body, validator=unique)


def registrations() -> list[dict]:
    return ledger.records("trial_registration")


def get(trial_id: str) -> dict:
    matches = [row for row in registrations() if row.get("trial_id") == trial_id]
    if len(matches) != 1:
        raise KeyError(f"unknown trial id {trial_id!r}")
    return matches[0]


def status(row: dict, current: dt.datetime | None = None) -> str:
    current = current or dt.datetime.now(dt.UTC)
    if current < _instant(row["start"]):
        return "registered"
    if current < _instant(row["end"]):
        return "active"
    return "closed"


def validate_prediction(
    trial_id: str,
    *,
    domain: str,
    window_start: str,
    window_end: str,
    technique_ids: list[str],
    manifest: dict,
    model: str,
) -> None:
    row = get(trial_id)
    if domain not in row["domains"]:
        raise ValueError(f"domain {domain!r} is outside trial {trial_id}")
    if technique_ids != row["technique_ids"]:
        raise ValueError("forecast technique manifest differs from frozen trial")
    if model != row["model"]:
        raise ValueError("forecast model differs from frozen trial")
    config = manifest.get("config", {})
    for key in (
        "ayanamsa",
        "node",
        "polarity",
        "min_magnitude",
        "window_days",
        "timezone",
    ):
        if config.get(key) != row.get(key):
            raise ValueError(f"forecast {key} differs from frozen trial")
    if manifest.get("code_sha256") != row.get("provenance", {}).get("code_sha256"):
        raise ValueError("forecast code differs from the frozen trial revision")
    if manifest.get("subject_sha256") != row.get("provenance", {}).get("subject_sha256"):
        raise ValueError("forecast subject data differs from the frozen trial")
    prediction_start = _instant(window_start)
    prediction_end = _instant(window_end)
    trial_start = _instant(row["start"])
    trial_end = _instant(row["end"])
    if prediction_start < trial_start:
        raise ValueError("forecast window begins before trial")
    if prediction_end > trial_end:
        raise ValueError("forecast window extends beyond trial")
    zone = _zone(row["timezone"])
    trial_local = trial_start.astimezone(zone)
    prediction_local = prediction_start.astimezone(zone)
    day_offset = (prediction_local.date() - trial_local.date()).days
    expected_start = trial_local + dt.timedelta(days=day_offset)
    if (
        day_offset < 0
        or day_offset % row["window_days"]
        or abs((prediction_start - expected_start).total_seconds()) > 0.01
    ):
        raise ValueError("forecast window is not aligned to the frozen trial grid")
    expected_end = prediction_local + dt.timedelta(days=row["window_days"])
    if abs((prediction_end - expected_end).total_seconds()) > 0.01:
        raise ValueError("forecast window length differs from the frozen trial")


def efficacy(trial_id: str) -> dict:
    """Score resolved predictions at the latest frozen checkpoint."""
    ok, message = ledger.verify()
    if not ok:
        raise ValueError(f"refusing to score trial: {message}")
    row = get(trial_id)
    all_pairs = sorted(
        (pair for pair in ledger.scored_pairs() if pair.get("trial_id") == trial_id),
        key=lambda pair: (pair["window_start"], pair["domain"]),
    )
    grouped: dict[str, list[dict]] = {}
    for pair in all_pairs:
        grouped.setdefault(pair["window_start"], []).append(pair)
    required_domains = set(row["domains"])
    complete_windows = [
        (window, values)
        for window, values in sorted(grouped.items())
        if len(values) == len(required_domains)
        and {value["domain"] for value in values} == required_domains
    ]
    checkpoint = max(
        (value for value in row["checkpoints"] if value <= len(complete_windows)),
        default=0,
    )
    n_resolved = len(all_pairs)
    if checkpoint == 0:
        return {
            "trial_id": trial_id,
            "status": "collecting",
            "n_resolved": n_resolved,
            "n_complete_windows": len(complete_windows),
            "next_checkpoint": row["checkpoints"][0],
        }
    selected_windows = complete_windows[:checkpoint]
    pairs = [pair for _, values in selected_windows for pair in values]
    if any(
        pair.get("provenance", {}).get("code_sha256")
        != row.get("provenance", {}).get("code_sha256")
        for pair in pairs
    ):
        raise ValueError("trial contains predictions from a different code revision")
    y = np.asarray([float(pair["occurred"]) for pair in pairs])
    model_probability = np.asarray([float(pair["probability"]) for pair in pairs])
    opponent_probability = np.asarray([float(pair["base_rate"]) for pair in pairs])
    model_loss = -(
        y * np.log(np.clip(model_probability, 1e-6, 1 - 1e-6))
        + (1 - y) * np.log(np.clip(1 - model_probability, 1e-6, 1 - 1e-6))
    )
    opponent_loss = -(
        y * np.log(np.clip(opponent_probability, 1e-6, 1 - 1e-6))
        + (1 - y) * np.log(np.clip(1 - opponent_probability, 1e-6, 1 - 1e-6))
    )
    # Predictions for several domains in one forecast window share almost all
    # inputs. Average their loss gains before inference so they are not
    # counted as independent observations.
    window_gain: dict[str, list[float]] = {}
    for pair, value in zip(pairs, opponent_loss - model_loss, strict=True):
        window_gain.setdefault(pair["window_start"], []).append(float(value))
    clustered_gain = np.asarray(
        [np.mean(window_gain[key]) for key in sorted(window_gain)],
        dtype=float,
    )
    gain, hac_z, raw_p = hac_one_sided(clustered_gain)
    formal_p = min(1.0, raw_p * len(row["checkpoints"]))
    next_checkpoint = next(
        (value for value in row["checkpoints"] if value > checkpoint),
        None,
    )
    return {
        "trial_id": trial_id,
        "status": "checkpoint",
        "trial_status": status(row),
        "checkpoint": checkpoint,
        "n_resolved": n_resolved,
        "n_complete_windows": len(complete_windows),
        "n_independent_windows": len(clustered_gain),
        "next_checkpoint": next_checkpoint,
        "observed_rate": float(y.mean()),
        "log_score_model": log_score(y, model_probability),
        "log_score_opponent": log_score(y, opponent_probability),
        "brier_model": brier(y, model_probability),
        "brier_opponent": brier(y, opponent_probability),
        "mean_log_loss_gain": gain,
        "hac_z": hac_z,
        "within_checkpoint_p": raw_p,
        "formal_p": formal_p,
        "survives": gain > 0 and formal_p < 0.05,
    }
