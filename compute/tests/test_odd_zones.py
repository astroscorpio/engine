"""The odd-zone sweep (backlog #2, 10 Nov 2026): a date the clocks skipped whole (Apia's
30 Dec 2011, Kiritimati's 31 Dec 1994) has no month row and is refused as a gochara or muhurta
day, as the day view refuses it; a local moment the clocks skipped or doubled is refused with that
reason. Before, the month answered 400, the two searches answered 200 over no time, and the check
said "at must be an ISO 8601 timestamp"."""

import pytest
from conftest import call

APIA = {"lat": "-13.83333", "lon": "-171.76666", "tz": "Pacific/Apia"}
KIRITIMATI = {"lat": "2.01643", "lon": "-157.48773", "tz": "Pacific/Kiritimati"}
LORD_HOWE = {"lat": "-31.5553", "lon": "159.0821", "tz": "Australia/Lord_Howe"}


@pytest.mark.parametrize(
    "place, year, gone", [(APIA, 2011, "2011-12-30"), (KIRITIMATI, 1994, "1994-12-31")]
)
def test_month_has_no_row_for_a_skipped_date(place, year, gone):
    status, out = call("GET", "/v1/panchang/month", {**place, "year": str(year), "month": "12"})
    assert status == 200
    dates = [r["date"] for r in out["days"]]
    assert gone not in dates and gone not in out["refused"]
    assert len(dates) + len(out["refused"]) == 30


def test_day_view_still_refuses_the_skipped_date():
    assert call("GET", "/v1/panchang", {**APIA, "date": "2011-12-30"})[0] == 400


@pytest.mark.parametrize(
    "span, field", [(("2011-12-30", "2011-12-30"), "from"), (("2011-12-28", "2011-12-30"), "until")]
)
def test_gochara_refuses_a_skipped_date(span, field):
    q = {"moonSign": "aries", "tz": "Pacific/Apia", "start": span[0], "end": span[1]}
    status, out = call("GET", "/v1/gochara", q)
    assert status == 400 and out["error"]["field"] == field
    assert "never occurred in Pacific/Apia" in out["error"]["message"]


@pytest.mark.parametrize(
    "span, field", [(("2011-12-30", "2011-12-30"), "from"), (("2011-12-29", "2011-12-30"), "until")]
)
def test_muhurta_refuses_a_skipped_date(span, field):
    status, out = call(
        "GET", "/v1/muhurta", {**APIA, "act": "general", "from": span[0], "until": span[1]}
    )
    assert status == 400 and out["error"]["field"] == field


def test_spans_across_the_skipped_date_still_answer():
    q = {"moonSign": "aries", "tz": "Pacific/Apia", "start": "2011-12-29", "end": "2011-12-31"}
    assert call("GET", "/v1/gochara", q)[0] == 200
    assert (
        call(
            "GET",
            "/v1/muhurta",
            {**APIA, "act": "general", "from": "2011-12-29", "until": "2011-12-31"},
        )[0]
        == 200
    )


def test_check_names_the_missing_and_doubled_local_times():
    def check(at):
        return call("GET", "/v1/muhurta/check", {**LORD_HOWE, "act": "general", "at": at})

    status, out = check("2026-10-04T02:15:00")  # clocks forward, 02:00 to 02:30
    assert status == 400 and "never occurred" in out["error"]["message"]
    status, out = check("2026-04-05T01:45:00")  # clocks back, 02:00 to 01:30
    assert status == 422 and out["error"]["code"] == "ambiguous_time"
    assert check("2026-04-05T01:45:00+11:00")[0] == 200
    assert check("not a time")[1]["error"]["message"] == "at must be an ISO 8601 timestamp"
