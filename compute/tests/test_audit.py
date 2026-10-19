"""Research's festival audit (the lead's decisions 41-43, 18 Oct 2026): the kojagara record
(DS p. 74, NS p. 285), the Divodāsīya lamps evening (NS p. 297) and the five-minute
near-boundary caution, at the site's own coordinates. Days and windows are checked against
their rules; no date is written here."""

import datetime as dt

from conftest import call

from astro_compute import observances as O

DELHI = {"lat": "28.65195", "lon": "77.23149", "tz": "Asia/Kolkata"}
LUCKNOW = {"lat": "26.83928", "lon": "80.92313", "tz": "Asia/Kolkata"}
NEW_YORK = {"lat": "40.71427", "lon": "-74.00597", "tz": "America/New_York"}
LONDON = {"lat": "51.50853", "lon": "-0.12574", "tz": "Europe/London"}


def get(path: str, place: dict) -> dict:
    status, out = call("GET", path, {"year": "2026", **place})
    assert status == 200, out
    return out


def day_before(date: str) -> str:
    return (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()


def test_kojagara_rule():
    """DS p. 74, NS p. 285: the first night when it alone has the Purnima at nishitha, else the
    second; some say the second when the first has nishitha only and the second pradosha only."""
    c = O._kojagara_choice
    assert c([True, True], [True, False]) == (0, "kojagara_nishitha", False)
    assert c([False, True], [True, False]) == (0, "kojagara_nishitha", True)
    assert c([True, True], [False, True]) == (1, "kojagara_nishitha", False)
    assert c([True, True], [True, True]) == (1, "kojagara_nishitha_both_later", False)
    assert c([True, True], [False, False]) == (1, "kojagara_nishitha_neither_later", False)


def ashvina(place: dict) -> dict:
    rows = [r for r in get("/v1/observances/purnima", place)["occurrences"] if "kojagara" in r]
    assert len(rows) == 1 and rows[0]["lunarMonth"]["amanta"] == "ashwin"
    return rows[0]


def test_kojagara_beside_the_fast():
    """Delhi: the vigil on the night the Purnima covers nishitha, its window inside the Purnima, the
    fast on NS's later day. New York: the Purnima ends before either nishitha, so the later night,
    with no window. Both carry that evening's visible moonrise, as Karva Chauth's (pages)."""
    row = ashvina(DELHI)
    k, t = row["kojagara"], row["tithi"]
    assert k["rule"] == "kojagara_nishitha" and k["variantDate"] is None
    assert t["start"] <= k["nishitha"]["start"] < k["nishitha"]["end"] <= t["end"]
    assert k["date"] == day_before(row["vrata"]["date"])
    ny = ashvina(NEW_YORK)["kojagara"]
    assert ny["rule"] == "kojagara_nishitha_neither_later" and ny["nishitha"] is None
    assert k["moonrise"][:10] == k["date"] and ny["moonrise"][:10] == ny["date"]


def test_divodasiya_lamps_and_the_eve():
    """NS p. 297: with the bath on the Caturdashi's second day, the lamps at the first evening's
    pradosha while it is current (Delhi); London's Caturdashi begins before the first sunrise, so
    none. Decision 42: eveRow names the row on the eve of the Lakshmi Puja."""
    dip = get("/v1/festivals/dipavali", DELHI)["occurrences"][0]
    naraka, eve = dip["set"]["narakaChaturdashi"], day_before(dip["set"]["lakshmiPuja"]["date"])
    lamps, t = naraka["lampsVariant"], naraka["tithi"]
    assert lamps["rule"] == "naraka_lamps_divodasiya"
    assert lamps["date"] == day_before(naraka["date"])
    assert t["start"] <= lamps["pradosha"]["start"] < lamps["pradosha"]["end"] <= t["end"]
    assert dip["eveRow"] == "lampsVariant" and lamps["date"] == eve
    dip = get("/v1/festivals/dipavali", LONDON)["occurrences"][0]
    naraka = dip["set"]["narakaChaturdashi"]
    assert naraka["lampsVariant"] is None
    assert dip["eveRow"] == "narakaChaturdashi"
    assert naraka["date"] == day_before(dip["set"]["lakshmiPuja"]["date"])


def prabodhini(place: dict) -> dict:
    rows = get("/v1/observances/ekadashi", place)["ekadashis"]
    return next(r for r in rows if r["nameId"] == "kartika_shukla")


def test_near_boundary_caution():
    """The lead: a tithi boundary within five minutes of the deciding moment gives the other day
    too. Lucknow's Prabodhini Ekadashi ends 46 s after sunrise: the Smarta fast and Tulsi Vivah
    each get the day before, and the Vaishnava fast does not move. Delhi's is clear."""
    lk = prabodhini(LUCKNOW)
    assert lk["smarta"]["cautions"] == ["near_boundary"]
    assert lk["smarta"]["nearBoundaryDate"] == day_before(lk["smarta"]["date"])
    assert lk["vaishnava"]["cautions"] == [] and lk["vaishnava"]["nearBoundaryDate"] is None
    tv = get("/v1/festivals/tulsi-vivah", LUCKNOW)["occurrences"][0]
    assert tv["cautions"] == ["near_boundary"] and tv["nearBoundaryDate"] == day_before(tv["date"])
    dl = prabodhini(DELHI)
    assert dl["smarta"]["cautions"] == dl["vaishnava"]["cautions"] == []


def test_audit_labels(meta):
    rules = {"kojagara_nishitha", "kojagara_nishitha_both_later", "kojagara_nishitha_neither_later"}
    assert set(meta["observanceRules"]["kojagara"]) == rules | {"kojagara_some_say"}
    assert "naraka_lamps_divodasiya" in meta["festivalRules"]["dipavali"]
    assert "near_boundary" in meta["festivalCautions"]
