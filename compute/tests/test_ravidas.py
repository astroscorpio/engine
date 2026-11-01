"""Ravidas Jayanti (festivals.md s39.2; the lead's ruling 3 of 21 Oct 2026, as corrected on 25 Oct
2026), popular practice: magha-snana's maghi_purnima day, reckoned at Prayagraj for every city.
Checked against the Guru Ravidas Jayanti holidays research read for 2015-2028, by weekday, and
against the magha-snana row; no date is written here."""

import pytest
from conftest import call

DELHI = {"lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}
NEW_YORK = {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"}
# s39.2's table: the year -> the kept day's weekday. 2017 and 2027 hold no sunrise (only_day).
KEPT = {
    2015: "tuesday",
    2016: "monday",
    2017: "friday",
    2018: "wednesday",
    2019: "tuesday",
    2020: "sunday",
    2021: "saturday",
    2022: "wednesday",
    2023: "sunday",
    2024: "saturday",
    2025: "wednesday",
    2026: "sunday",
    2027: "saturday",
    2028: "thursday",
}
ONLY_DAY = {2017, 2027}


def get(kind: str, y: int, place: dict) -> dict:
    status, out = call("GET", f"/v1/festivals/{kind}", {"year": str(y), **place})
    assert status == 200, out
    return out


@pytest.mark.parametrize("y", sorted(KEPT))
def test_the_kept_days_are_prayagrajs_maghi_purnima(y):
    out = get("ravidas-jayanti", y, DELHI)
    assert out["basis"] == "popular_practice" and out["source"] is None
    assert [(c["page"], c["text"]) for c in out["context"]] == [("333", "Nirṇaya-sindhu")]
    assert out["computedAt"]["name"] == "Prayagraj"
    (o,) = out["occurrences"]
    assert o["vara"] == KEPT[y]
    assert o["rule"] == ("only_day" if y in ONLY_DAY else "maghi_later_day")
    season = get("magha-snana", y, DELHI)["occurrences"][0]["bathDays"]
    m = next(d for d in season if d["id"] == "maghi_purnima")
    assert o == {k: m[k] for k in ("date", "vara", "rule", "tithi")}
    assert o["tithi"]["start"] < o["tithi"]["end"]


def test_one_day_for_every_city():
    for y in (2027, 2028):
        ny, delhi = get("ravidas-jayanti", y, NEW_YORK), get("ravidas-jayanti", y, DELHI)
        assert ny["occurrences"] == delhi["occurrences"]
        assert ny["computedAt"] == delhi["computedAt"]


def test_the_meta_never_claims_a_text_gives_the_festival(meta):
    assert meta["festivals"]["ravidas-jayanti"]["name"] == "Ravidas Jayanti"
    rules = meta["festivalRules"]["ravidas-jayanti"]
    assert set(rules) == {"maghi_later_day", "only_day"}
    assert "no text read gives the festival" in rules["maghi_later_day"]["name"]
    note = meta["festivalNotes"]["ravidas-jayanti"]
    assert note.startswith("Popular practice; no text read gives Ravidas Jayanti")
    assert "Nirṇaya-sindhu p. 333" in note and "Prayagraj" in note
