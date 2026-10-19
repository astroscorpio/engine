"""Kali Puja and Ahoi Ashtami (festivals.md s35-36, the lead's decisions 44-45, 18 Oct 2026),
popular practice: each weighs one window on the day the tithi begins and the next, with decision
43's five-minute caution at its edges. Days are checked against the rule and against each other;
no date is written here."""

import datetime as dt

from conftest import call

from astro_compute import festivals as F

KOLKATA = {"lat": "22.56263", "lon": "88.36304", "tz": "Asia/Kolkata"}
DELHI = {"lat": "28.65195", "lon": "77.23149", "tz": "Asia/Kolkata"}
MUMBAI = {"lat": "19.07283", "lon": "72.88261", "tz": "Asia/Kolkata"}
NEW_YORK = {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"}


def only(kind: str, year: int, place: dict) -> dict:
    status, out = call("GET", f"/v1/festivals/{kind}", {"year": str(year), **place})
    assert status == 200, out
    (row,) = out["occurrences"]
    return {**row, "basis": out["basis"], "context": out.get("context")}


def day_before(date: str) -> str:
    return (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()


def test_window_rule():
    """Decisions 44-45: the day whose window the tithi covers; covering both, the day with more
    of it, the earlier if equal; covering neither, the later day (our reading)."""
    c = F._window_choice
    assert c([1.0, 0.0], "nishitha") == (0, "nishitha")
    assert c([0.0, 0.4], "nishitha") == (1, "nishitha")
    assert c([1.0, 0.43], "nishitha") == (0, "nishitha_both_more")
    assert c([0.36, 1.0], "nishitha") == (1, "nishitha_both_more")
    assert c([1.0, 1.0], "pradosha") == (0, "pradosha_both_more")
    assert c([0.0, 0.0], "pradosha") == (1, "pradosha_neither_later")


def test_kali_puja_follows_midnight():
    """s35: the night whose nishitha the Amavasya covers. Kolkata 2026 keeps the Lakshmi Puja
    night, the window inside the Amavasya; 2027 the night before the Lakshmi Puja, which goes by
    pradosha. 2016 covers both nights, the first more. New York 2028 covers neither: the later
    night, which is Kolkata's day, with no window."""
    k, dip = only("kali-puja", 2026, KOLKATA), only("dipavali", 2026, KOLKATA)
    assert k["basis"] == "popular_practice" and len(k["context"]) == 3
    assert (k["rule"], k["date"]) == ("nishitha", dip["date"])
    t, w = k["tithi"], k["pujaWindow"]
    assert t["start"] <= w["start"] < w["end"] <= t["end"]
    assert [d["nishitha"]["covered"] for d in k["days"]] == [1.0, 0.0]
    assert k["cautions"] == [] and k["nearBoundaryDate"] is None
    k27 = only("kali-puja", 2027, KOLKATA)
    assert k27["date"] == day_before(only("dipavali", 2027, KOLKATA)["date"])
    k16 = only("kali-puja", 2016, KOLKATA)
    assert k16["rule"] == "nishitha_both_more" and k16["date"] == k16["days"][0]["date"]
    ny = only("kali-puja", 2028, NEW_YORK)
    assert ny["rule"] == "nishitha_neither_later" and ny["pujaWindow"] is None
    assert ny["date"] == ny["days"][1]["date"] == only("kali-puja", 2028, KOLKATA)["date"]


def test_ahoi_ashtami_by_the_evening():
    """s36: the day whose pradosha the Ashtami covers, with that day's sunset and its moonrise.
    Delhi 2026 keeps the first day and sees the Moon rise that night; Mumbai keeps the same day,
    its moonrise after midnight. Delhi 2013 covers both evenings, the first more. In 2020 Ashvina
    is adhika: the nija month's Ashtami, days after Karva Chauth."""
    a = only("ahoi-ashtami", 2026, DELHI)
    assert a["basis"] == "popular_practice"
    assert a["rule"] == "pradosha" and a["date"] == a["days"][0]["date"]
    assert a["sunset"] == a["days"][0]["pradosha"]["start"]
    assert a["sunset"] < a["moonrise"] and a["moonrise"][:10] == a["date"]
    m = only("ahoi-ashtami", 2026, MUMBAI)
    assert m["date"] == a["date"] and m["moonrise"][:10] > m["date"]
    a13 = only("ahoi-ashtami", 2013, DELHI)
    assert a13["rule"] == "pradosha_both_more" and a13["date"] == a13["days"][0]["date"]
    a20, karva = only("ahoi-ashtami", 2020, DELHI), only("karva-chauth", 2020, DELHI)
    assert not a20["lunarMonth"]["adhika"]
    gap = dt.date.fromisoformat(a20["date"]) - dt.date.fromisoformat(karva["date"])
    assert 0 < gap.days <= 5


def test_near_boundary_on_the_window():
    """Decision 43 at the window's edges: a tithi ending a minute inside one evening's pradosha
    gives that day; ended five minutes earlier it would give the next."""
    ws = [(10.0, 10.1), (11.0, 11.1)]
    k = F._window_choice([F._share(9.5, 10.0 + 1 / 1440, w) for w in ws], "pradosha")[0]
    assert k == 0 and F._near_window(9.5, 10.0 + 1 / 1440, ws, "pradosha", k) == 1
    assert F._near_window(9.5, 10.05, ws, "pradosha", 0) is None
