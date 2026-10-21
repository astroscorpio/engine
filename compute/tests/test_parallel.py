"""The year lists' parallel split (the lead's latency plan, step 2): the same records, explain lines
included, whether the scans and days run in one process or across workers."""

import datetime as dt
import json

import pytest
from conftest import AT, DELHI

from astro_compute import parallel, vivah
from astro_compute.models import EkadashiQuery


def test_run_keeps_the_call_order_and_raises_a_worker_failure(monkeypatch):
    monkeypatch.setenv("ASTRO_WORKERS", "3")
    assert parallel.run([lambda i=i: i * i for i in range(10)]) == [i * i for i in range(10)]
    with pytest.raises(RuntimeError, match="ZeroDivisionError"):
        parallel.run([lambda: 1, lambda: 1 / 0])


def test_a_year_list_is_the_same_in_one_process_and_across_workers(monkeypatch):
    year = dt.datetime.fromisoformat(AT).year
    q = EkadashiQuery(year=year, lat=float(DELHI["lat"]), lon=float(DELHI["lon"]), tz=DELHI["tz"])
    answers = []
    for n in ("1", "3"):
        monkeypatch.setenv("ASTRO_WORKERS", n)
        explain: dict = {}
        answers.append((json.dumps(vivah.vivah(q, explain), ensure_ascii=False), explain))
    assert answers[0] == answers[1]
