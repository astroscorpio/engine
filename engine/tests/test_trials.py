from __future__ import annotations

import datetime as dt

import pytest

from jyotisha import ledger, provenance, trials
from jyotisha.subjects import EXAMPLE

NOW = dt.datetime(2026, 8, 12, 12, tzinfo=dt.UTC)
TECHNIQUE_IDS = ["dasha-lord-rules-the-domain-house"]
MODEL = "test-model-v1"


def _register(tmp_path, monkeypatch) -> dict:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    return trials.register(
        EXAMPLE,
        name="prospective test",
        start="2026-08-16T00:00:00+02:00",
        end="2027-08-01T00:00:00+02:00",
        domains=["career"],
        technique_ids=TECHNIQUE_IDS,
        endpoint="forecast-windows",
        polarity="any",
        min_magnitude=2,
        checkpoints=[30, 60],
        ayanamsa="lahiri",
        node="true",
        timezone="Europe/Paris",
        window_days=14,
        model=MODEL,
        _now=NOW,
    )


def test_trial_freezes_the_forecast_configuration(tmp_path, monkeypatch) -> None:
    row = _register(tmp_path, monkeypatch)
    manifest = provenance.manifest(
        EXAMPLE,
        technique_ids=TECHNIQUE_IDS,
        config={
            "domain": "career",
            "polarity": "any",
            "min_magnitude": 2,
            "ayanamsa": "lahiri",
            "node": "true",
            "window_days": 14,
            "training_cutoff": "2026-08-16T00:00:00+02:00",
            "timezone": "Europe/Paris",
        },
    )
    trials.validate_prediction(
        row["trial_id"],
        domain="career",
        window_start="2026-08-16T00:00:00+02:00",
        window_end="2026-08-30T00:00:00+02:00",
        technique_ids=TECHNIQUE_IDS,
        manifest=manifest,
        model=MODEL,
    )
    prediction = ledger.predict(
        EXAMPLE.name,
        "2026-08-16T00:00:00+02:00",
        "2026-08-30T00:00:00+02:00",
        "career",
        0.25,
        0.10,
        MODEL,
        timezone="Europe/Paris",
        trial_id=row["trial_id"],
        provenance=manifest,
        _now=NOW,
    )
    with pytest.raises(ValueError, match="trial events require"):
        ledger.resolve(
            None,
            None,
            True,
            prediction_id=prediction["prediction_id"],
            _now=dt.datetime(2026, 8, 20, 12, tzinfo=dt.UTC),
        )
    ledger.resolve(
        None,
        None,
        True,
        prediction_id=prediction["prediction_id"],
        occurrence_at="2026-08-17T12:00:00+02:00",
        polarity=1,
        magnitude=3,
        source="contemporaneous record",
        _now=dt.datetime(2026, 8, 20, 12, tzinfo=dt.UTC),
    )
    with pytest.raises(ValueError, match="ayanamsa"):
        bad_manifest = {**manifest, "config": {**manifest["config"], "ayanamsa": "raman"}}
        trials.validate_prediction(
            row["trial_id"],
            domain="career",
            window_start="2026-08-16T00:00:00+02:00",
            window_end="2026-08-30T00:00:00+02:00",
            technique_ids=TECHNIQUE_IDS,
            manifest=bad_manifest,
            model=MODEL,
        )
    assert trials.efficacy(row["trial_id"])["status"] == "collecting"


def test_unimplemented_trial_endpoint_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="only the forecast-windows"):
        trials.register(
            EXAMPLE,
            name="unsupported",
            start="2026-08-16T00:00:00+02:00",
            end="2027-08-01T00:00:00+02:00",
            domains=["career"],
            technique_ids=TECHNIQUE_IDS,
            endpoint="daily-ratings",
            polarity="any",
            min_magnitude=2,
            checkpoints=[30],
            ayanamsa="lahiri",
            node="true",
            timezone="Europe/Paris",
            window_days=14,
            model=MODEL,
            _now=NOW,
        )


def test_trial_grid_uses_civil_days_across_dst(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    row = trials.register(
        EXAMPLE,
        name="dst grid",
        start="2026-10-18T00:00:00+02:00",
        end="2027-02-01T00:00:00+01:00",
        domains=["career"],
        technique_ids=TECHNIQUE_IDS,
        endpoint="forecast-windows",
        polarity="any",
        min_magnitude=2,
        checkpoints=[2],
        ayanamsa="lahiri",
        node="true",
        timezone="Europe/Paris",
        window_days=14,
        model=MODEL,
        _now=NOW,
    )
    manifest = provenance.manifest(
        EXAMPLE,
        technique_ids=TECHNIQUE_IDS,
        config={
            "domain": "career",
            "polarity": "any",
            "min_magnitude": 2,
            "ayanamsa": "lahiri",
            "node": "true",
            "window_days": 14,
            "training_cutoff": "2026-10-18T00:00:00+02:00",
            "timezone": "Europe/Paris",
        },
    )
    trials.validate_prediction(
        row["trial_id"],
        domain="career",
        window_start="2026-10-18T00:00:00+02:00",
        window_end="2026-11-01T00:00:00+01:00",
        technique_ids=TECHNIQUE_IDS,
        manifest=manifest,
        model=MODEL,
    )
    with pytest.raises(ValueError, match="length"):
        trials.validate_prediction(
            row["trial_id"],
            domain="career",
            window_start="2026-10-18T00:00:00+02:00",
            window_end="2026-11-01T00:00:00+02:00",
            technique_ids=TECHNIQUE_IDS,
            manifest=manifest,
            model=MODEL,
        )


def test_trial_efficacy_clusters_domains_by_forecast_window(monkeypatch) -> None:
    trial = {
        "trial_id": "trial",
        "start": "2020-01-01T00:00:00Z",
        "end": "2030-01-01T00:00:00Z",
        "domains": ["career", "education"],
        "checkpoints": [2],
        "provenance": {"code_sha256": "revision"},
    }
    pairs = [
        {
            "trial_id": "trial",
            "window_start": window,
            "domain": domain,
            "occurred": (i + j) % 2,
            "probability": 0.6,
            "base_rate": 0.5,
            "provenance": {"code_sha256": "revision"},
        }
        for i, window in enumerate(("2026-08-16T00:00:00Z", "2026-08-30T00:00:00Z"))
        for j, domain in enumerate(("career", "education"))
    ]
    observed = {}

    def capture(values):
        observed["n"] = len(values)
        return float(values.mean()), 0.0, 1.0

    monkeypatch.setattr(trials, "get", lambda _trial_id: trial)
    monkeypatch.setattr(ledger, "verify", lambda: (True, "chain intact"))
    monkeypatch.setattr(ledger, "scored_pairs", lambda: pairs)
    monkeypatch.setattr(trials, "hac_one_sided", capture)
    result = trials.efficacy("trial")
    assert observed["n"] == 2
    assert result["n_independent_windows"] == 2
