from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from jyotisha import cli, daily, ledger
from jyotisha.ephemeris import parse
from jyotisha.subjects import EXAMPLE


def _rating(date: str) -> daily.Rating:
    return daily.Rating(date, 3, 3, 3, 3, 3)


def test_daily_rating_is_same_day_and_unique(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    current = dt.datetime(2026, 8, 6, 20, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    daily.log(_rating("2026-08-06"), timezone="Europe/Paris", _now=current)
    with pytest.raises(ValueError, match="already exists"):
        daily.log(
            _rating("2026-08-06"),
            timezone="Europe/Paris",
            _now=current,
        )
    with pytest.raises(ValueError, match="backfill"):
        daily.log(
            _rating("2026-08-05"),
            timezone="Europe/Paris",
            _now=current,
        )
    assert len(daily.load()) == 1


def test_exposure_blocks_same_day_rating(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    current = dt.datetime(2026, 8, 6, 20, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    daily.record_exposure("2026-08-06", "panchanga")
    with pytest.raises(ValueError, match="already exposed"):
        daily.log(
            _rating("2026-08-06"),
            timezone="Europe/Paris",
            _now=current,
        )


def test_future_forecast_exposes_every_touched_civil_date(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JYOTISHA_DATA_DIR", str(tmp_path))
    context = EXAMPLE.observer_context
    cli._record_exposure_window(
        parse("2026-08-13T00:00:00+02:00"),
        parse("2026-08-16T00:00:00+02:00"),
        context,
        "forecast",
    )
    cli._record_exposure_window(
        parse("2026-08-13T00:00:00+02:00"),
        parse("2026-08-16T00:00:00+02:00"),
        context,
        "forecast",
    )
    assert [row["date"] for row in ledger.records("daily_exposure")] == [
        "2026-08-13",
        "2026-08-14",
        "2026-08-15",
    ]


def test_formal_daily_p_value_covers_all_planned_checkpoints(monkeypatch) -> None:
    rows = []
    for i in range(daily.FORMAL_CHECKPOINTS[0]):
        rows.append(
            {
                "date": (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(),
                **{field: 1 + i % 5 for field in daily.FIELDS},
            }
        )
    signal = np.arange(len(rows), dtype=float)[:, None]
    monkeypatch.setattr(daily, "load", lambda: rows)
    monkeypatch.setattr(
        daily,
        "matrix",
        lambda _subject, _rows, **_kwargs: (signal, ["probe"]),
    )
    result = daily.analyze(EXAMPLE, n_perm=50)
    technique = result["techniques"][0]
    assert result["checkpoint_correction"] == len(daily.FORMAL_CHECKPOINTS)
    assert technique["formal_fwer_p"] == pytest.approx(
        min(
            1.0,
            technique["within_checkpoint_fwer_p"] * len(daily.FORMAL_CHECKPOINTS),
        )
    )
