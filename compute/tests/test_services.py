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


def test_muhurta_scorer_rules_of_15_oct():
    import datetime as dt

    def day(date):
        status, out = call("GET", "/v1/panchang", {"date": date, **DELHI})
        assert status == 200, out
        return out

    def check(moment, minutes):
        at = (dt.datetime.fromisoformat(moment) + dt.timedelta(minutes=minutes)).isoformat()
        status, out = call("GET", "/v1/muhurta/check", {"act": "general", "at": at, **DELHI})
        assert status == 200, out
        return {r["id"] for r in out["vetoes"]}, {r["id"] for r in out["supports"]}

    # 2 Mar 2026: the Purnima's Bhadra, on earth (Moon in Leo), runs through the night.
    holi = day("2026-03-02")["windows"]
    vetoes, _ = check(holi["bhadraFace"][0]["start"], 30)
    assert "bhadra_face" in vetoes  # MC 1.44: never in the face
    vetoes, supports = check(holi["bhadraTail"][0]["start"], 10)
    assert "bhadra_tail" in supports and not {"bhadra_face", "bhadra_earth"} & vetoes
    # A first-half Bhadra at night carries no penalty (MC 1.44).
    vetoes, supports = check(holi["bhadra"][0]["start"], 120)
    assert "bhadra_day_night" in supports and "bhadra_earth" not in vetoes
    # Tuesday 20 Oct: Dhanishta is utpata, a veto like marana.
    tuesday = {r["id"]: r for r in day("2026-10-20")["specialYogas"]}
    vetoes, _ = check(tuesday["utpata"]["start"], 30)
    assert "utpata_yoga" in vetoes
    # Monday 19 Oct: Shravana after Abhijit is siddhi, a support.
    monday = {r["id"]: r for r in day("2026-10-19")["specialYogas"]}
    _, supports = check(monday["siddhi"]["start"], 30)
    assert "siddhi_yoga" in supports
    # 21 Oct: the mahapata moment is vetoed.
    pata = next(r for r in day("2026-10-21")["specialYogas"] if r["id"] == "mahapata")
    vetoes, _ = check(pata["moment"], 0)
    assert "mahapata" in vetoes


def test_home_profile_follows_mc_13():
    import datetime as dt

    def moment(date, minutes):
        status, out = call("GET", "/v1/panchang", {"date": date, **DELHI})
        assert status == 200, out
        at = dt.datetime.fromisoformat(out["sunrise"]) + dt.timedelta(minutes=minutes)
        return at.isoformat(), out["tithi"]["num"]

    def vetoes(at, **extra):
        query = {"act": "home", "at": at, **DELHI, **extra}
        status, out = call("GET", "/v1/muhurta/check", query)
        assert status == 200, out
        return {r["id"] for r in out["vetoes"]}

    # Shravana (2026's runs from 12 Aug, after the adhika Jyeshtha): no entry into a new
    # house (MC 13.1), but an old one may (MC 13.2).
    at, _ = moment("2026-08-25", 300)
    assert "month_home" in vetoes(at)
    assert "month_home" not in vetoes(at, oldHouse="true")
    # MC 13.4: never on a Sunday or Tuesday, for a new house or an old one.
    day = dt.date(2027, 5, 10)
    sunday = day + dt.timedelta((6 - day.weekday()) % 7)
    at, _ = moment(sunday.isoformat(), 600)
    assert "weekday_home" in vetoes(at) and "weekday_home" in vetoes(at, oldHouse="true")
    at, _ = moment((sunday + dt.timedelta(1)).isoformat(), 600)
    assert "weekday_home" not in vetoes(at)
    # The door decides the tithi class (MC 13.5): East Purna, South Nanda, West
    # Bhadra, North Jaya.
    at, num = moment("2027-02-10", 10)
    n = (num - 1) % 15 + 1
    classes = {"E": {5, 10, 15}, "S": {1, 6, 11}, "W": {2, 7, 12}, "N": {3, 8, 13}}
    wrong = next(d for d, c in classes.items() if n not in c)
    assert "door_tithi" in vetoes(at, door=wrong)
    right = next((d for d, c in classes.items() if n in c), None)
    if right:
        assert "door_tithi" not in vetoes(at, door=right)


def test_vehicle_act_bars_selling_stars_and_non_riding_weekdays():
    import datetime as dt

    def vetoes(at, act="vehicle"):
        status, out = call("GET", "/v1/muhurta/check", {"act": act, "at": at, **DELHI})
        assert status == 200, out
        return {r["id"] for r in out["vetoes"]}

    day = dt.date(2027, 5, 10)
    tuesday = day + dt.timedelta((1 - day.weekday()) % 7)
    at = f"{tuesday.isoformat()}T12:00:00+05:30"
    assert "riding_weekday" in vetoes(at) and "riding_weekday" not in vetoes(at, "property")


def test_season_rules_follow_the_texts():
    # 2026: adhika Jyeshtha from 17 May; Pitru Paksha (the dark Bhadrapada) in early October.
    def check(act, at, **extra):
        status, out = call("GET", "/v1/muhurta/check", {"act": act, "at": at, **DELHI, **extra})
        assert status == 200, out
        return out

    adhika = "2026-05-27T10:00:00+05:30"
    ids = lambda rows: {r["id"] for r in rows}  # noqa: E731
    assert "adhika_masa" in ids(check("travel", adhika, toward="E")["defects"])
    assert "adhika_masa" not in ids(check("general", adhika)["defects"])
    pitru = check("vehicle", "2026-10-05T10:00:00+05:30")
    assert ids(pitru["notes"]) == {"pitru_paksha_practice"}
    assert not any("pitru" in r["id"] for r in pitru["defects"])
    assert not check("education", "2026-10-05T10:00:00+05:30")["notes"]
