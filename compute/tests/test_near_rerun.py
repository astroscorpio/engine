"""Decision 43 for every kind (the lead, 19 Oct 2026): each kind's own rule rerun with the tithi's
start or end moved by five minutes, four ways, the other day on the record whose day moved. No date
is written here."""

import datetime as dt

from conftest import call

from astro_compute import observances as O

DELHI = {"year": "2026", "lat": "28.65195", "lon": "77.23149", "tz": "Asia/Kolkata"}
LUCKNOW = {"year": "2026", "lat": "26.83928", "lon": "80.92313", "tz": "Asia/Kolkata"}
SINGAPORE = {"lat": "1.28967", "lon": "103.85007", "tz": "Asia/Singapore"}
EDGE = 10.0  # a rule's boundary: a tithi ending after it gives day "a", else "b"


def rule(start: float, end: float, _next: float, _q) -> dict:
    return {"date": "a" if end > EDGE else "b", "cautions": []}


def test_a_five_minute_move_gives_the_other_day():
    near = O._near_rerun(rule)
    row = near(9.0, EDGE + 2 / 1440, 11.0, None)
    assert (row["date"], row["nearBoundaryDate"], row["cautions"]) == ("a", "b", ["near_boundary"])
    row = near(9.0, EDGE + 30 / 1440, 11.0, None)
    assert (row["nearBoundaryDate"], row["cautions"]) == (None, [])


def test_a_margin_day_stays_with_its_margin():
    """A day the one-ghatika margin already shows gains no second caution."""

    def chhath(start, end, nxt, q):
        return {**rule(start, end, nxt, q), "cautions": ["ghatika_margin"], "variantDate": "b"}

    row = O._near_rerun(chhath)(9.0, EDGE + 2 / 1440, 11.0, None)
    assert (row["nearBoundaryDate"], row["cautions"]) == (None, ["ghatika_margin"])


def test_own_cautions_are_kept_and_reruns_never_rerun():
    calls = []

    def own(start, end, nxt, q):
        calls.append(end)
        return {"date": "a", "nearBoundaryDate": None}

    O._near_rerun(own)(9.0, EDGE, 11.0, None)
    assert len(calls) == 1
    nested = O._near_rerun(lambda a, b, c, q: O._near_rerun(rule)(a, b, c, q))
    row = nested(9.0, EDGE + 2 / 1440, 11.0, None)
    assert row["nearBoundaryDate"] == "b" and row["cautions"] == ["near_boundary"]


def test_every_tithi_record_is_checked():
    """The Dipavali set's days, the Purnima vrata (and Kojagara), Pradosha and the Pitru-paksha
    days carry nearBoundaryDate; Lucknow's Tulsi Vivah keeps its own single caution."""
    status, out = call("GET", "/v1/festivals/dipavali", DELHI)
    assert status == 200, out
    (occ,) = out["occurrences"]
    assert "nearBoundaryDate" in occ
    assert all("nearBoundaryDate" in occ["set"][k] for k in ("dhanteras", "narakaChaturdashi"))
    assert all("nearBoundaryDate" in occ["set"][k] for k in ("govardhan", "bhaiDooj"))
    status, out = call("GET", "/v1/observances/purnima", DELHI)
    assert all("nearBoundaryDate" in r["vrata"] for r in out["occurrences"])
    assert all("nearBoundaryDate" in r["kojagara"] for r in out["occurrences"] if "kojagara" in r)
    status, out = call("GET", "/v1/observances/pradosha", DELHI)
    assert all("nearBoundaryDate" in r for r in out["occurrences"])
    status, out = call("GET", "/v1/observances/pitru-paksha", DELHI)
    assert status == 200, out
    assert all("nearBoundaryDate" in t for t in out["tithis"])
    status, out = call("GET", "/v1/festivals/tulsi-vivah", LUCKNOW)
    assert out["occurrences"][0]["cautions"] == ["near_boundary"]
    status, out = call("GET", "/v1/festivals/durga-puja", DELHI)  # its own one-ghatika caution
    assert all("nearBoundaryDate" not in r for r in out["occurrences"])


def test_a_fast_day_a_move_changes_gets_its_own_fields():
    """0nf (the lead, 28 Oct 2026): a five-minute move that gives another fast day, the puja day
    staying, adds fastNearBoundaryDate and fastCautions and leaves the puja day's fields alone; a
    null fastDate is a fast on the date."""

    def vow(start, end, _next, _q):
        return {"date": "b", "fastDate": "a" if end > EDGE else None}

    near = O._near_rerun(vow)
    row = near(9.0, EDGE + 2 / 1440, 11.0, None)
    assert (row["nearBoundaryDate"], row["fastNearBoundaryDate"], row["fastCautions"]) == (
        None,
        "b",
        ["near_boundary"],
    )
    assert "cautions" not in row
    row = near(9.0, EDGE - 2 / 1440, 11.0, None)
    assert (row["fastDate"], row["fastNearBoundaryDate"]) == (None, "a")
    row = near(9.0, EDGE + 30 / 1440, 11.0, None)
    assert "fastNearBoundaryDate" not in row and "fastCautions" not in row


def _day_before(d: str) -> str:
    return (dt.date.fromisoformat(d) - dt.timedelta(1)).isoformat()


def test_singapores_vat_savitri_fast_rests_on_seconds():
    """Research's 0ma finding 3: Singapore's 2028 Amavasya form keeps the fast on the puja day,
    the tithi starting seconds short of three muhurtas before sunset; a five-minute move gives the
    day before. The Purnima form is clear."""
    status, out = call("GET", "/v1/festivals/vat-savitri", {"year": "2028", **SINGAPORE})
    assert status == 200, out
    (a,) = [o for o in out["occurrences"] if o["form"] == "amavasya"]
    assert (a["rule"], a["fastDate"], a["nearBoundaryDate"]) == (
        "under_three_muhurtas_later",
        None,
        None,
    )
    assert (a["fastNearBoundaryDate"], a["fastCautions"]) == (
        _day_before(a["date"]),
        ["near_boundary"],
    )
    assert "cautions" not in a
    (p,) = [o for o in out["occurrences"] if o["form"] == "purnima"]
    assert "fastNearBoundaryDate" not in p and "fastCautions" not in p


def test_tulsi_vivahs_fast_carries_its_ekadashis_other_day():
    """Lucknow's Tulsi Vivah: the Smarta Ekadashi fast's other day, a day before the puja's."""
    status, out = call("GET", "/v1/festivals/tulsi-vivah", LUCKNOW)
    assert status == 200, out
    (o,) = out["occurrences"]
    assert o["cautions"] == ["near_boundary"] and o["fastCautions"] == ["near_boundary"]
    assert o["fastNearBoundaryDate"] == _day_before(o["nearBoundaryDate"])
    assert o["fastNearBoundaryDate"] != o["fastDate"]
