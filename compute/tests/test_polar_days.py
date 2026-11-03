"""The Vedic day far north (the lead's rulings, 30 Oct 2026): a date's day runs from its own
sunrise, the first after the place's local mean midnight, to the next sunrise, and carries the
date's weekday. A date with no sunrise of its own, or whose day lacks its sunset, next sunrise or
previous sunset, answers 422; the month lists such dates in `refused`. The cases, with the times
the rule gives (Unix seconds), are in data/polar_days.json; no date is written here. Times may
differ by 1 s, since the searches agree within 12 ms from any starting point."""

import datetime as dt
import json
from pathlib import Path

import pytest
from conftest import call
from jyotisha import ephemeris as E
from jyotisha import muhurta as Mu

from astro_compute.observances import _own_sunrise

DATA = json.loads((Path(__file__).parent / "data" / "polar_days.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in DATA["cases"]}
MONTHS = {m["id"]: m for m in DATA["months"]}
JD_SECOND = 1 / 86400


def near(got: str, want: int) -> bool:
    return abs(dt.datetime.fromisoformat(got).timestamp() - want) <= 1


def place(case: dict) -> tuple[float, float, str]:
    p = case["place"]
    return p["lat"], p["lon"], p["tz"]


@pytest.mark.parametrize("cid", CASES)
def test_each_day(cid):
    want = CASES[cid]["correct"]
    status, out = call("GET", "/v1/panchang", CASES[cid]["query"])
    assert status == want["status"], out
    if status == 422:
        assert out["error"]["code"] == "unsupported_location"
        return
    assert out["vara"]["id"] == want["vara"]
    for k in ("sunrise", "sunset", "nextSunrise"):
        assert near(out[k], want[k]), (k, out[k], want[k])
    for k in ("brahma", "abhijit", "pradosha"):
        for end in ("start", "end"):
            assert near(out["windows"][k][end], want[k][end]), (k, end)


@pytest.mark.parametrize("mid", MONTHS)
def test_each_month(mid):
    case = MONTHS[mid]
    want = case["correct"]
    status, out = call("GET", "/v1/panchang/month", case["query"])
    assert status == 200, out
    assert out["refused"] == want["daysRefusedWhenFixed"]
    rows = {r["date"]: r for r in out["days"]}
    assert not rows.keys() & set(out["refused"])
    for date, w in want["rows"].items():
        r = rows[date]
        assert r["vara"] == w["vara"], date
        assert near(r["sunrise"], w["sunrise"]) and near(r["sunset"], w["sunset"]), date


@pytest.mark.parametrize("mid", MONTHS)
def test_day_and_month_agree(mid):
    case = MONTHS[mid]
    q = case["query"]
    status, out = call("GET", "/v1/panchang/month", q)
    assert status == 200, out
    rows = {r["date"]: r for r in out["days"]}
    near_rows = set()
    for date in case["correct"]["rows"]:
        d = dt.date.fromisoformat(date)
        near_rows |= {(d + dt.timedelta(days=k)).isoformat() for k in range(-3, 4)}
    for date in sorted(near_rows):
        if dt.date.fromisoformat(date).month != int(q["month"]):
            continue
        place_q = {k: q[k] for k in ("lat", "lon", "tz")}
        status, day = call("GET", "/v1/panchang", {"date": date, **place_q})
        if date in out["refused"]:
            assert status == 422, date
            continue
        assert status == 200, (date, day)
        r = rows[date]
        assert (r["sunrise"], r["sunset"], r["vara"]) == (
            day["sunrise"],
            day["sunset"],
            day["vara"]["id"],
        ), date


@pytest.mark.parametrize("cid", CASES)
def test_engine_events(cid):
    case = CASES[cid]
    want, (lat, lon, tz) = case["correct"], place(case)
    day = dt.date.fromisoformat(case["query"]["date"])
    jd = want.get("jd", {})
    if "sunrise" not in jd:
        with pytest.raises(RuntimeError):
            _own_sunrise(day, tz, lat, lon, "date")
        return
    if want["status"] != 200:  # the day lacks an event, which these searches need; 422 above
        return
    sr, mean = _own_sunrise(day, tz, lat, lon, "date")
    assert abs(sr - jd["sunrise"]) <= JD_SECOND
    assert abs(E.sunset(jd["sunrise"] + 1e-4, lat, lon) - jd["sunset"]) <= JD_SECOND
    assert abs(Mu.day(jd["sunrise"] + 1e-3, lat, lon).prev_sunset - jd["prevSunset"]) <= JD_SECOND
    midnight = dt.datetime.fromtimestamp(want["meanMidnight"], dt.UTC).replace(tzinfo=None)
    assert (
        abs(mean - (dt.datetime.combine(day, dt.time()) - midnight) / dt.timedelta(hours=1))
        <= 1 / 3600
    )
