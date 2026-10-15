import datetime as dt

from conftest import DELHI, call


def ts(text):
    return dt.datetime.fromisoformat(text)


def contiguous(rows):
    return all(a["end"] == b["start"] for a, b in zip(rows, rows[1:], strict=False))


def test_day_bounds_and_vara(panchang):
    p = panchang
    assert p["vara"] == {"id": "wednesday", "lord": "mercury"}
    assert ts(p["sunrise"]) < ts(p["sunset"]) < ts(p["nextSunrise"])
    assert p["sunrise"].startswith("2026-10-14T06:2")
    assert p["windows"]["abhijit"]["avoided"] is True  # Wednesday


def test_limbs_cover_the_day_without_gaps(panchang):
    rise, next_rise = ts(panchang["sunrise"]), ts(panchang["nextSunrise"])
    for limb, rows in panchang["sequence"].items():
        assert contiguous(rows), limb
        assert ts(rows[0]["start"]) <= rise < ts(rows[0]["end"]), limb
        assert ts(rows[-1]["start"]) < next_rise <= ts(rows[-1]["end"]), limb
    assert panchang["tithi"] == panchang["sequence"]["tithi"][0]


def test_choghadiya_hora_and_lagna_tables(panchang):
    day, night = panchang["choghadiya"]["day"], panchang["choghadiya"]["night"]
    assert len(day) == 8 and len(night) == 8
    assert day[0]["start"] == panchang["sunrise"] and day[-1]["end"] == night[0]["start"]
    assert night[-1]["end"] == panchang["nextSunrise"]
    assert contiguous(day + night)
    assert len(panchang["hora"]) == 24 and contiguous(panchang["hora"])
    assert panchang["hora"][0]["lord"] == "mercury"  # the first hora is the vara lord's
    assert contiguous(panchang["lagna"])
    assert panchang["lagna"][-1]["end"] == panchang["nextSunrise"]


def test_avoid_windows_are_sorted_and_named(panchang):
    rows = panchang["windows"]["avoid"]
    assert {r["id"] for r in rows} >= {"rahu_kalam", "yamaganda", "gulika", "durmuhurta"}
    starts = [ts(r["start"]) for r in rows]
    assert starts == sorted(starts)


def test_polar_night_is_unsupported():
    status, out = call(
        "GET",
        "/v1/panchang",
        {"date": "2026-12-21", "lat": "78.2232", "lon": "15.6267", "tz": "Arctic/Longyearbyen"},
    )
    assert status == 422 and out["error"]["code"] == "unsupported_location"


def test_dst_day_keeps_each_time_in_its_own_offset():
    status, out = call(
        "GET",
        "/v1/panchang",
        {"date": "2026-10-25", "lat": "51.5074", "lon": "-0.1278", "tz": "Europe/London"},
    )
    assert status == 200
    assert out["sunrise"].endswith("+00:00")  # BST ended at 02:00 that morning
    assert contiguous(out["hora"])


def test_invalid_query_reports_the_field():
    status, out = call("GET", "/v1/panchang", {"date": "2026-13-01", **DELHI})
    assert status == 400 and out["error"]["field"] == "date"


def test_month_rows_agree_with_the_day_view(panchang):
    status, out = call("GET", "/v1/panchang/month", {"year": "2026", "month": "10", **DELHI})
    assert status == 200, out
    assert [r["date"] for r in out["days"]][:2] == ["2026-10-01", "2026-10-02"]
    assert len(out["days"]) == 31
    row = out["days"][13]
    assert row["date"] == "2026-10-14"
    assert row["sunrise"] == panchang["sunrise"] and row["vara"] == panchang["vara"]["id"]
    assert row["tithi"]["id"] == panchang["tithi"]["id"]
    assert row["tithi"]["end"] == panchang["tithi"]["end"]
    assert row["nakshatra"]["end"] == panchang["nakshatra"]["end"]
    assert row["lunarMonth"] == panchang["lunarMonth"]
    # The sidereal Sun enters Libra around 17 October.
    assert [r["date"] for r in out["days"] if r["sankranti"]] == ["2026-10-17"]


def test_siddhi_pair_turns_to_visha_on_its_tithi():
    # 15 Apr 2027 at Delhi: Thursday, Pushya, Shukla Navami (MC 1.20-21).
    status, out = call("GET", "/v1/panchang", {**DELHI, "date": "2027-04-15"})
    assert status == 200, out
    assert "visha" in [r["id"] for r in out["specialYogas"]]


def test_bhadra_is_avoided_only_while_on_earth():
    seen = set()
    for day in range(1, 16):
        status, out = call("GET", "/v1/panchang", {**DELHI, "date": f"2026-10-{day:02d}"})
        bhadra = out["windows"]["bhadra"]
        avoid = [w for w in out["windows"]["avoid"] if w["id"] == "vishti"]
        seen |= {b["residence"] for b in bhadra}
        on_earth = [(b["start"], b["end"]) for b in bhadra if b["residence"] == "earth"]
        assert [(w["start"], w["end"]) for w in avoid] == on_earth
        assert all(w["detail"] == "bhadra_earth" for w in avoid)
    assert seen <= {"earth", "heaven", "patala"} and len(seen) >= 2


def test_weekday_east_of_utc_plus_six():
    # Thursday 15 Oct 2026 in Sydney: sunrise falls on Wednesday in UT.
    sydney = {"lat": "-33.8688", "lon": "151.2093", "tz": "Australia/Sydney"}
    status, out = call("GET", "/v1/panchang", {**sydney, "date": "2026-10-15"})
    assert status == 200 and out["vara"]["id"] == "thursday", out["vara"]
    status, out = call("GET", "/v1/panchang/month", {**sydney, "year": "2026", "month": "10"})
    assert next(r for r in out["days"] if r["date"] == "2026-10-15")["vara"] == "thursday"
