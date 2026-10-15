import datetime as dt

from conftest import DELHI, call

from astro_compute import purchase as P
from astro_compute.ids import NAKSHATRA_IDS

BUYING = {NAKSHATRA_IDS[i] for i in P.BUYING}
RIDING = {NAKSHATRA_IDS[i] for i in P.RIDING}


def middle(w):
    a, b = (dt.datetime.fromisoformat(w[k]) for k in ("start", "end"))
    return (a + (b - a) / 2).isoformat(timespec="seconds")


def test_vehicle_days_keep_the_rules_and_the_finder_agrees():
    status, out = call("GET", "/v1/muhurat/vehicle", {"year": "2027", **DELHI})
    assert status == 200, out
    assert out["days"] and out["delivery"]
    dates = {d["date"] for d in out["delivery"]}
    for d in out["days"]:
        assert d["date"] in dates and d["vara"] in P.RIDING_VARAS
        for w in d["windows"]:
            assert w["start"] < w["end"] and w["nakshatra"] in BUYING
            assert w["tithi"] not in ("chaturthi", "navami", "chaturdashi", "amavasya")
    for d in out["delivery"]:
        assert all(w["nakshatra"] in RIDING for w in d["windows"])
    for w in [w for d in out["days"] for w in d["windows"]][:12]:
        query = {"act": "vehicle", "at": middle(w), **DELHI}
        status, chk = call("GET", "/v1/muhurta/check", query)
        assert status == 200 and chk["ok"], (w, chk["vetoes"])


def test_property_days_use_the_buying_stars_on_any_weekday():
    status, out = call("GET", "/v1/muhurat/property", {"year": "2027", **DELHI})
    assert status == 200, out
    assert {d["vara"] for d in out["days"]} >= {"tuesday", "saturday"}
    assert all(w["nakshatra"] in BUYING for d in out["days"] for w in d["windows"])
