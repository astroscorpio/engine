from types import SimpleNamespace

from conftest import call

from astro_compute import transit_service as T

SIGNS = {g: SimpleNamespace(sign=0) for g in T.GRAHAS}


def table(**houses):
    """Positions with each named graha in that house from an Aries Moon sign."""
    moving = {g: SimpleNamespace(sign=(houses.get(g, 12) - 1) % 12) for g in T.GRAHAS}
    return T._gochara_from(0, moving)


def test_gochara_day_is_cut_where_a_graha_changes_sign():
    status, out = call(
        "GET", "/v1/gochara", {"moonSign": "aries", "start": "2026-10-15", "end": "2026-10-15"}
    )
    assert status == 200, out
    segs = out["segments"]
    assert segs[0]["start"].startswith("2026-10-15T00:00") and segs[-1]["end"].startswith(
        "2026-10-16T00:00"
    )
    assert all(a["end"] == b["start"] for a, b in zip(segs, segs[1:], strict=False))
    for seg in segs:
        assert [g["id"] for g in seg["grahas"]] == [
            "sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu",
        ]  # fmt: skip
        for g in seg["grahas"]:
            assert (
                1 <= g["house"] <= 12
                and g["result"]["text"]
                and g["result"]["verse"].startswith("26.")
            )
    for a, b in zip(segs, segs[1:], strict=False):  # a cut means some graha changed sign
        assert [g["sign"] for g in a["grahas"]] != [g["sign"] for g in b["grahas"]]


def test_gochara_rules():
    # PD 26.2: the nodes are like the Sun, good in 10 too, and never blocked.
    assert table(Rahu=10, Ketu=4)["Rahu"] == ("good", None)
    assert table(Rahu=10, Saturn=4)["Rahu"] == ("good", None)
    # The Sun in the 3rd is blocked from the 9th, but never by Saturn (PD 26.3).
    assert table(Sun=3, Mars=9)["Sun"] == ("neutral", "mars")
    assert table(Sun=3, Saturn=9)["Sun"] == ("good", None)
    # Venus: the 11th is blocked from the 3rd and the 12th from the 6th (PD 26.8).
    assert table(Venus=11, Mars=3)["Venus"] == ("neutral", "mars")
    assert table(Venus=12, Jupiter=6)["Venus"] == ("neutral", "jupiter")
    assert table(Venus=6)["Venus"] == ("bad", None)
    # Ketu quotes Rahu's lines (MC 4 commentary).
    assert T.RESULTS["Ketu"][2] == T.RESULTS["Rahu"][2]
    assert T.RESULTS["Sun"][2][9] == "a very mighty undertaking will be successfully completed"


def test_gochara_range_limit():
    status, out = call(
        "GET", "/v1/gochara", {"moonSign": "leo", "start": "2026-10-15", "end": "2026-10-22"}
    )
    assert status == 400, out
