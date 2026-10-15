from conftest import call

from astro_compute import observances as O
from astro_compute.meta import OBSERVANCE_RULES

DELHI = {"year": "2026", "lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}


def test_purnima_and_amavasya_fasts_take_the_later_day():
    for kind, tithi_id in (("purnima", "purnima"), ("amavasya", "amavasya")):
        status, out = call("GET", f"/v1/observances/{kind}", DELHI)
        assert status == 200, out
        rows = out["occurrences"]
        assert 12 <= len(rows) <= 14
        for r in rows:
            v = r["vrata"]
            assert v["rule"] in OBSERVANCE_RULES["vrata"]
            day = next(d for d in r["days"] if d["date"] == v["date"])
            if v["rule"] == "later_day":
                # the last day with the tithi at sunrise, joined to the next Pratipada
                assert day["tithiAtSunrise"] == tithi_id and v["earlierDate"] < v["date"]
        assert out["source"]["text"] == "Nirnaya-sindhu"


def test_shraddha_amavasya_follows_aparahna_then_kutapa():
    status, out = call("GET", "/v1/observances/amavasya", DELHI)
    for r in out["occurrences"]:
        sh = r["shraddha"]
        assert sh["rule"] in OBSERVANCE_RULES["shraddha"]
        assert sh["date"] in [a["date"] for a in sh["aparahna"]]
        assert r["differs"] == (sh["date"] != r["vrata"]["date"])
        touched = [a["date"] for a in sh["aparahna"] if a["covered"] > 0]
        if len(touched) == 1:
            assert sh["rule"] == "aparahna" and sh["date"] == touched[0]


def test_kutapa_choice():
    assert O._kutapa_choice([(0, 0.0), (1, 0.4)], False) == (1, "kutapa_one_day")
    assert O._kutapa_choice([(0, 0.7), (1, 0.4)], False) == (0, "kutapa_more")
    assert O._kutapa_choice([(0, 0.5), (1, 0.5)], True) == (0, "kutapa_tie_kshaya_earlier")
    assert O._kutapa_choice([(0, 0.5), (1, 0.5)], False) == (1, "kutapa_tie_later")
    assert O._kutapa_choice([(0, 1.0), (1, 1.0), (2, 0.2)], False)[1] == "kutapa_more"


def test_pradosha_vrata_on_the_trayodashi_covering_pradosha():
    status, out = call("GET", "/v1/observances/pradosha", DELHI)
    assert status == 200, out
    rows = out["occurrences"]
    assert 24 <= len(rows) <= 26
    for r in rows:
        assert r["rule"] in OBSERVANCE_RULES["pradosha"]
        chosen = next(d for d in r["days"] if d["date"] == r["date"])
        assert chosen["vara"] == r["vara"]
        if r["rule"] == "covers_pradosha":
            assert chosen["covered"] == 1 and r["variantDate"] is None
        else:
            assert r["variantDate"] == r["days"][0]["date"] and r["date"] == r["days"][1]["date"]
