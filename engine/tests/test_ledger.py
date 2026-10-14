from __future__ import annotations

import datetime as dt

import pytest

from jyotisha import ledger

NOW = dt.datetime(2026, 8, 12, 12, tzinfo=dt.UTC)


def test_prospective_unique_prediction_and_resolution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    prediction = ledger.predict(
        "Example",
        "2026-08-13T00:00:00+02:00",
        "2026-08-27T00:00:00+02:00",
        "education",
        0.2,
        0.1,
        "test-model",
        timezone="Europe/Paris",
        experimental=True,
        _now=NOW,
    )
    with pytest.raises(ValueError, match="duplicate"):
        ledger.predict(
            "Example",
            "2026-08-13T00:00:00+02:00",
            "2026-08-27T00:00:00+02:00",
            "education",
            0.2,
            0.1,
            "test-model",
            timezone="Europe/Paris",
            experimental=True,
            _now=NOW,
        )
    ledger.resolve(
        None,
        None,
        True,
        prediction_id=prediction["prediction_id"],
        _now=dt.datetime(2026, 8, 14, tzinfo=dt.UTC),
    )
    assert ledger.verify()[0]
    assert len(ledger.scored_pairs()) == 1
    assert ledger.ledger_path().stat().st_mode & 0o777 == 0o600


def test_rejects_retroactive_prediction(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="after its window begins"):
        ledger.predict(
            "Example",
            "2026-08-10T00:00:00Z",
            "2026-08-16T00:00:00Z",
            "career",
            0.2,
            0.1,
            "test",
            _now=NOW,
        )


def test_resolution_respects_the_registered_window(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    prediction = ledger.predict(
        "Example",
        "2026-08-13T00:00:00+02:00",
        "2026-08-27T00:00:00+02:00",
        "career",
        0.2,
        0.1,
        "test",
        _now=NOW,
    )
    with pytest.raises(ValueError, match="before its window begins"):
        ledger.resolve(
            None,
            None,
            True,
            prediction_id=prediction["prediction_id"],
            _now=NOW,
        )
    inside = dt.datetime(2026, 8, 14, 12, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match="still-open"):
        ledger.resolve(
            None,
            None,
            False,
            prediction_id=prediction["prediction_id"],
            _now=inside,
        )
    with pytest.raises(ValueError, match="inside the prediction window"):
        ledger.resolve(
            None,
            None,
            True,
            prediction_id=prediction["prediction_id"],
            occurrence_at="2026-09-04T12:00:00+02:00",
            _now=inside,
        )
