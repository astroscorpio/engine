import datetime as dt

from conftest import AT, DELHI, EXAMPLE, call

from astro_compute import transit_service


def test_gochara_tables_mirror_the_engine():
    from jyotisha import hypotheses as H

    assert transit_service.GOCHARA_GOOD == H.GOCHARA_GOOD
    assert transit_service.VEDHA == H.VEDHA
    assert transit_service.NO_VEDHA_BETWEEN == H.NO_VEDHA_BETWEEN


def test_personal_transits():
    status, out = call("POST", "/v1/transits", body={"chart": EXAMPLE, "at": AT, "days": 60})
    assert status == 200, out
    assert len(out["grahas"]) == 9
    for g in out["grahas"]:
        assert g["gochara"] in {"good", "neutral", "bad"}
        assert 1 <= g["houseFromMoon"] <= 12
    assert out["grahas"][0]["kakshya"] is not None and out["grahas"][7]["kakshya"] is None
    times = [dt.datetime.fromisoformat(e["at"]) for e in out["upcoming"]]
    assert times == sorted(times)
    assert out["sadeSati"]["active"] is False and out["sadeSati"]["next"]["start"] > AT[:10]
    assert (
        out["sadeSati"]["saturnHouse"] is None and out["sadeSati"]["source"]["verse"] == "26.22-23"
    )
    assert (
        "Khankhoje 1943" in out["sadeSati"]["nameNote"] and "our" in out["sadeSati"]["convention"]
    )


def test_general_transits_have_no_personal_fields():
    status, out = call("GET", "/v1/transits", {"at": "2026-10-14T00:00:00Z", "days": "30"})
    assert status == 200
    assert out["sadeSati"] is None
    assert all(g["houseFromMoon"] is None and g["gochara"] is None for g in out["grahas"])


def test_muhurta_find_never_returns_a_veto():
    status, out = call(
        "GET",
        "/v1/muhurta",
        {"act": "general", "from": "2026-10-15", "until": "2026-10-15", "top": "5", **DELHI},
    )
    assert status == 200, out
    assert out["windows"] and out["natalApplied"] is False
    scores = [w["score"] for w in out["windows"]]
    assert scores == sorted(scores)


def test_muhurta_with_a_birth_chart_applies_tara():
    status, out = call(
        "POST",
        "/v1/muhurta/check",
        body={
            "act": "general",
            "at": AT,
            "chart": EXAMPLE,
            **{k: float(v) if k != "tz" else v for k, v in DELHI.items()},
        },
    )
    assert status == 200, out
    assert out["natalApplied"] is True and out["facts"]["tara"]


def test_muhurta_limits():
    status, out = call(
        "GET",
        "/v1/muhurta",
        {"act": "travel", "from": "2026-10-15", "until": "2026-10-15", **DELHI},
    )
    assert status == 400 and out["error"]["field"] == "toward"
    status, out = call(
        "GET",
        "/v1/muhurta",
        {"act": "general", "from": "2026-10-01", "until": "2026-12-01", **DELHI},
    )
    assert status == 400 and out["error"]["field"] == "until"


def test_routing_and_auth(monkeypatch):
    assert call("GET", "/v1/nope")[0] == 404
    assert call("GET", "/v1/chart")[0] == 405
    monkeypatch.setenv("COMPUTE_KEY", "s3cret")
    assert call("GET", "/v1/health")[0] == 401
    assert call("GET", "/v1/health", headers={"x-compute-key": "s3cret"})[0] == 200


def test_transit_events_agree_with_upcoming_and_each_other():
    status, out = call(
        "GET",
        "/v1/transits/events",
        {"start": "2026-10-14T00:00:00Z", "end": "2027-10-14T00:00:00Z"},
    )
    assert status == 200, out
    ev = out["events"]
    assert [e["jd"] for e in ev] == sorted(e["jd"] for e in ev)
    assert {e["graha"] for e in ev} >= {"sun", "mercury", "saturn", "rahu"} and "moon" not in {
        e["graha"] for e in ev
    }
    # The Sun takes a sidereal sign a month: 12 forward ingresses a year, each on a 30° boundary.
    sun = [e for e in ev if e["graha"] == "sun" and e["type"] == "sign"]
    assert len(sun) == 12 and not any(e["retro"] for e in sun)
    assert all(abs(e["lon"] % 30) < 1e-9 or abs(e["lon"] % 30 - 30) < 1e-9 for e in sun)
    # Stations alternate direction for each planet.
    for g in ("mercury", "jupiter", "saturn"):
        dirs = [e["direction"] for e in ev if e["graha"] == g and e["type"] == "station"]
        assert dirs and all(a != b for a, b in zip(dirs, dirs[1:], strict=False)), (g, dirs)
    # Same instants as the /v1/transits "upcoming" list.
    status, tr = call("GET", "/v1/transits", {"at": "2026-10-14T00:00:00Z", "days": "60"})
    sun_ingress = next(u for u in tr["upcoming"] if u["graha"] == "sun" and u["type"] == "ingress")
    assert sun_ingress["at"].startswith(sun[0]["at"][:16])


def test_moon_events_only_for_short_spans():
    q = {"start": "2026-10-14T00:00:00Z", "end": "2026-10-21T00:00:00Z", "grahas": "moon"}
    status, out = call("GET", "/v1/transits/events", q)
    assert status == 200
    signs = [e for e in out["events"] if e["type"] == "sign"]
    naks = [e for e in out["events"] if e["type"] == "nakshatra"]
    assert 2 <= len(signs) <= 4 and 6 <= len(naks) <= 9
    status, out = call("GET", "/v1/transits/events", {**q, "end": "2027-01-14T00:00:00Z"})
    assert status == 400


def test_motion_runs_from_station_to_station():
    status, out = call("GET", "/v1/transits", {"at": "2026-10-14T00:00:00Z", "days": "0"})
    assert status == 200
    sat = next(g for g in out["grahas"] if g["id"] == "saturn")
    assert sat["retro"] is True and sat["motion"]["retro"] is True
    assert sat["motion"]["since"] < "2026-10-14" < sat["motion"]["until"]
    sun = next(g for g in out["grahas"] if g["id"] == "sun")
    assert sun["motion"] == {"retro": False, "since": None, "until": None}


def test_swiss_ephemeris_files_are_in_use():
    status, out = call("GET", "/v1/health")
    assert status == 200 and out["engine"]["ephemeris"] == "swiss"


def test_sade_sati_runs_by_sign_from_the_natal_moon():
    from jyotisha.ephemeris import positions

    from astro_compute import transit_service as T
    from astro_compute.timeutil import parse_instant

    when = parse_instant(AT, "UTC")
    saturn = positions(when, "lahiri")["Saturn"].sign
    for moon, phase, house in ((saturn, "peak", 1), ((saturn + 1) % 12, "rising", 12)):
        out = T._sade_sati(moon, when, "lahiri", "UTC")
        assert out["active"] and out["phase"] == phase and out["saturnHouse"] == house, out
        assert out["end"] > AT[:10] and (out["start"] is None or out["start"] < AT)
    out = T._sade_sati((saturn + 4) % 12, when, "lahiri", "UTC")
    assert not out["active"] and out["phase"] is None and out["next"]["start"] > AT[:10]
