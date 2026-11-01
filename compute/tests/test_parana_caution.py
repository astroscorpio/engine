"""The pāraṇa close call (the lead, 25 Oct 2026, from research's May to July 2027 audit): when
moving the Dvadashi's start or end by five minutes, four ways, changes a window's rule, the window
carries parana_near_boundary and that other window as altWindow. Checked on research's two Sydney
cases and on a Hari-vasara case, and on every window of three places' years; no date is written
here."""

import datetime as dt

import pytest
from conftest import call

SYDNEY = {"lat": "-33.86785", "lon": "151.20732", "tz": "Australia/Sydney"}
DELHI = {"lat": "28.65195", "lon": "77.23149", "tz": "Asia/Kolkata"}
LONDON = {"lat": "51.50853", "lon": "-0.12574", "tz": "Europe/London"}
MARGIN = dt.timedelta(minutes=5)
CAUTION = ["parana_near_boundary"]
RULES = {"morning", "afternoon", "trayodashi", "within_dvadashi"}


def ekadashis(y: int, place: dict) -> list[dict]:
    status, out = call("GET", "/v1/observances/ekadashi", {"year": str(y), "parana": "1", **place})
    assert status == 200, out
    return out["ekadashis"]


def gap(row: dict, side: str) -> dt.timedelta:
    """The Dvadashi's end less the sunrise of the pāraṇa day."""
    p = row["parana"][side]
    sunrise = next(d["sunrise"] for d in row["days"] if d["date"] == p["date"])
    return dt.datetime.fromisoformat(row["dvadashiEnd"]) - dt.datetime.fromisoformat(sunrise)


@pytest.mark.parametrize("place", [SYDNEY, DELHI, LONDON], ids=["sydney", "delhi", "london"])
def test_every_window_carries_its_alternative(place):
    for y in (2026, 2027, 2028):
        for row in ekadashis(y, place):
            for side in ("smarta", "vaishnava"):
                p, why = row["parana"][side], (y, row["nameId"], side)
                alt = p["altWindow"]
                assert p["cautions"] == (CAUTION if alt else []), why
                if alt:
                    assert alt["rule"] in RULES - {p["rule"]} and alt["start"] < alt["end"], why
                if abs(gap(row, side)) <= MARGIN:  # the end at sunrise: the move crosses it
                    assert alt and "trayodashi" in (p["rule"], alt["rule"]), why


def test_research_sydney_cases():
    """Nirjala's Vaishnava parana, the Dvadashi ending just after sunrise, would move to
    Trayodashi; Kamika's, the Dvadashi ending just before it, would be a morning one."""
    rows = ekadashis(2027, SYDNEY)
    nirjala = next(r for r in rows if r["nameId"] == "jyeshtha_shukla")
    kamika = next(r for r in rows if r["nameId"] == "shravana_krishna")
    p = nirjala["parana"]["vaishnava"]
    assert (p["rule"], p["cautions"], p["altWindow"]["rule"]) == ("morning", CAUTION, "trayodashi")
    for side in ("smarta", "vaishnava"):
        p = kamika["parana"][side]
        assert (p["rule"], p["cautions"], p["altWindow"]["rule"]) == (
            "trayodashi",
            CAUTION,
            "morning",
        )


def test_a_hari_vasara_case_moves_by_hours():
    """Delhi's Nirjala, 2027: Hari-vasara ends just past the morning limit, so the window is the
    afternoon one, and five minutes would give the morning."""
    row = next(r for r in ekadashis(2027, DELHI) if r["nameId"] == "jyeshtha_shukla")
    p = row["parana"]["smarta"]
    assert (p["rule"], p["cautions"], p["altWindow"]["rule"]) == ("afternoon", CAUTION, "morning")
    assert p["altWindow"]["end"] < p["start"]


def test_the_label_and_its_phrases(meta):
    assert "{alt}" in meta["festivalCautions"]["parana_near_boundary"]
    assert set(meta["paranaAlt"]["forms"]) == RULES
    assert "{start}" in meta["paranaAlt"]["times"] and "{end}" in meta["paranaAlt"]["times"]
