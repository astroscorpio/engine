import datetime as dt

from conftest import AT, EXAMPLE, call

GRAHA_ORDER = ["sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu"]


def ts(text):
    return dt.datetime.fromisoformat(text)


def test_example_chart_matches_the_engine_fixture(chart):
    # The invented EXAMPLE subject was chosen for a Taurus lagna and the Moon in Anuradha.
    assert chart["summary"]["lagna"] == "taurus"
    assert chart["summary"]["moonSign"] == "scorpio"
    assert chart["summary"]["janmaNakshatra"] == "anuradha"
    assert chart["resolved"]["utc"] == "2001-01-19T08:35:00Z"
    assert chart["resolved"]["utcOffset"] == "+05:30"
    assert [g["id"] for g in chart["grahas"]] == GRAHA_ORDER
    assert [h["num"] for h in chart["houses"]] == list(range(1, 13))
    assert chart["houses"][0]["sign"] == "taurus"


def test_graha_rows_are_internally_consistent(chart):
    for g in chart["grahas"]:
        assert 0 <= g["lon"] < 360
        assert g["signNum"] == int(g["lon"] // 30) + 1
        assert abs(g["deg"] - g["lon"] % 30) < 1e-5
        assert g["house"] == (g["signNum"] - chart["asc"]["signNum"]) % 12 + 1
        assert g["retro"] == (g["speed"] < 0)
    rahu, ketu = chart["grahas"][7], chart["grahas"][8]
    assert abs((rahu["lon"] - ketu["lon"]) % 360 - 180) < 1e-6


def test_ashtakavarga_totals(chart):
    av = chart["ashtakavarga"]
    assert sum(av["savBySign"]) == 337
    assert sorted(av["savByHouse"]) == sorted(av["savBySign"])
    assert av["savByHouse"][0] == av["savBySign"][chart["asc"]["signNum"] - 1]
    for g, bindus in av["bav"].items():
        assert len(bindus) == 12 and sum(bindus) == av["bavTotals"][g]


def test_vimshottari_chain_nests_and_contains_the_moment(chart):
    d = chart["dasha"]
    at = ts(AT)
    assert [p["level"] for p in d["current"]] == [1, 2, 3, 4, 5]
    for parent, child in zip(d["current"], d["current"][1:], strict=False):
        assert ts(parent["start"]) <= ts(child["start"]) < ts(child["end"]) <= ts(parent["end"])
    assert all(ts(p["start"]) <= at < ts(p["end"]) for p in d["current"])
    # Mercury-Saturn for EXAMPLE begins 16 Sep 2026 UTC (the engine's predict tests rely on it).
    assert [p["lord"] for p in d["current"][:2]] == ["mercury", "saturn"]
    assert ts(d["current"][1]["start"]).astimezone(dt.UTC).date() == dt.date(2026, 9, 16)


def test_mahadashas_are_contiguous_and_span_120_years(chart):
    mds = chart["dasha"]["mahadashas"]
    assert len(mds) == 9
    for a, b in zip(mds, mds[1:], strict=False):
        assert a["end"] == b["start"]
    years = (ts(mds[-1]["end"]) - ts(mds[0]["start"])).days / 365.2425
    assert abs(years - 120) < 0.01
    for md in mds:
        assert md["antardashas"][0]["lord"] == md["lord"]
        assert md["antardashas"][0]["start"] == md["start"]
        assert md["antardashas"][-1]["end"] == md["end"]


def test_yogas_merge_mirrored_pairs(chart):
    keys = [(y["id"], y["from"], tuple(y["grahas"])) for y in chart["yogas"]]
    assert len(keys) == len(set(keys))
    for y in chart["yogas"]:
        assert y["grahas"], y
        assert y["category"] in {
            "mahapurusha", "raja", "dhana", "vipareeta", "cancellation", "lunar",
            "solar", "exchange", "dosha", "auspicious", "nabhasa", "modern",
        }  # fmt: skip
        # Every yoga but the modern ones carries its text, verse, edition and page.
        if y["category"] == "modern":
            assert y["source"] is None
        else:
            assert set(y["source"]) == {"text", "verse", "edition", "page"}, y
        assert y["from"] in (None, "lagna", "moon")


def test_all_vargas_and_d1_agrees_with_rashi(chart):
    assert len(chart["vargas"]) == 16
    d1 = chart["vargas"]["D1"]
    for g in chart["grahas"]:
        assert d1["grahas"][g["id"]]["sign"] == g["sign"]
    assert d1["asc"]["sign"] == chart["asc"]["sign"]


def test_time_unknown_is_a_moon_chart():
    status, out = call("POST", "/v1/chart", body={**EXAMPLE, "time": None, "timeUnknown": True})
    assert status == 200, out
    assert out["basis"] == "moon" and out["asc"] is None
    assert out["flags"]["moonChart"] and out["flags"]["moonNakshatraUncertain"]
    assert {"asc", "vargas", "yogas:lagna", "ashtakavarga", "dasha.balanceAtBirth"} <= set(
        out["omitted"]
    )
    assert "vargas" not in out and "ashtakavarga" not in out
    assert out["houses"][0]["sign"] == out["summary"]["moonSign"]
    assert out["dasha"]["balanceAtBirth"] is None
    # Only yogas that hold on sign positions alone: nothing counted from the lagna.
    assert all(y["from"] != "lagna" for y in out["yogas"])
    assert all(
        y["category"] in {"lunar", "solar", "mahapurusha", "auspicious", "modern"}
        for y in out["yogas"]
    )


def test_time_required_unless_unknown():
    status, out = call("POST", "/v1/chart", body={**EXAMPLE, "time": None})
    assert status == 400 and "time" in out["error"]["message"]


def test_bad_time_format_names_the_field():
    status, out = call("POST", "/v1/chart", body={**EXAMPLE, "time": "2pm"})
    assert status == 400
    assert out["error"]["field"] == "time" and "HH:MM" in out["error"]["message"]


def test_dst_overlap_and_gap():
    london = {"lat": 51.5074, "lon": -0.1278, "tz": "Europe/London"}
    status, out = call(
        "POST",
        "/v1/chart",
        body={**EXAMPLE, "date": "2026-10-25", "time": "01:30", "place": london},
    )
    assert status == 422 and out["error"]["code"] == "ambiguous_time"
    status, out = call(
        "POST",
        "/v1/chart",
        body={
            **EXAMPLE,
            "date": "2026-10-25",
            "time": "01:30",
            "utcOffset": "+01:00",
            "place": london,
        },
    )
    assert status == 200 and out["resolved"]["utc"] == "2026-10-25T00:30:00Z"
    status, out = call(
        "POST",
        "/v1/chart",
        body={**EXAMPLE, "date": "2026-03-29", "time": "01:30", "place": london},
    )
    assert status == 400 and out["error"]["field"] == "time"


def test_local_mean_time_offsets_stay_parseable():
    status, out = call(
        "POST", "/v1/chart", body={**EXAMPLE, "date": "1850-06-01", "time": "10:00", "include": []}
    )
    assert status == 200
    assert out["resolved"]["utcOffset"] == "+05:53:28"
    local = dt.datetime.fromisoformat(out["resolved"]["local"])
    assert local.utcoffset() == dt.timedelta(hours=5, minutes=53)
    assert local.astimezone(dt.UTC) == dt.datetime(1850, 6, 1, 4, 6, 32, tzinfo=dt.UTC)


def test_unknown_varga_and_zone_are_rejected():
    status, out = call("POST", "/v1/chart", body={**EXAMPLE, "vargas": ["D11"]})
    assert status == 400 and out["error"]["field"] == "vargas"
    bad = {**EXAMPLE, "place": {**EXAMPLE["place"], "tz": "Mars/Olympus"}}
    status, out = call("POST", "/v1/chart", body=bad)
    assert status == 400 and out["error"]["field"] == "tz"


def test_dasha_drill_down_and_systems():
    status, out = call(
        "POST", "/v1/dasha", body={"chart": EXAMPLE, "path": ["mercury", "saturn"], "at": AT}
    )
    assert status == 200
    assert [p["lord"] for p in out["periods"]][:3] == ["saturn", "mercury", "ketu"]
    assert out["periods"][0]["start"] == out["current"][1]["start"]
    for system in ("yogini", "ashtottari", "chara", "narayana"):
        status, out = call("POST", "/v1/dasha", body={"chart": EXAMPLE, "system": system, "at": AT})
        assert status == 200, (system, out)
        assert out["current"], system
    status, out = call(
        "POST", "/v1/dasha", body={"chart": {**EXAMPLE, "timeUnknown": True}, "system": "chara"}
    )
    assert status == 400


def test_both_chara_karaka_schemes(chart):
    j = chart["jaimini"]
    assert set(j["charaKarakas8"]) == {"ak", "amk", "bk", "mk", "pik", "pk", "gk", "dk"}
    assert set(j["charaKarakas7"]) == {"ak", "amk", "bk", "mk", "pk", "gk", "dk"}
    assert "rahu" not in j["charaKarakas7"].values()
    assert j["differs"] == [
        r for r in j["charaKarakas7"] if j["charaKarakas7"][r] != j["charaKarakas8"][r]
    ]
    assert j["karakaSource"].startswith("Jaimini") and j["karakaTie"] is False


def test_graha_aspects_per_graha(chart):
    by_id = {g["id"]: g for g in chart["grahas"]}
    houses = {h["num"]: h for h in chart["houses"]}
    assert [a["nth"] for a in by_id["mars"]["aspects"]] == [4, 7, 8]
    assert [a["nth"] for a in by_id["jupiter"]["aspects"]] == [5, 7, 9]
    assert [a["nth"] for a in by_id["saturn"]["aspects"]] == [3, 7, 10]
    assert [(a["nth"], a["kind"]) for a in by_id["sun"]["aspects"]] == [(7, "full_7th")]
    assert {a["note"] for a in by_id["rahu"]["aspects"] if a["nth"] != 7} == {
        "node_aspect_source_pending"
    }
    for g in chart["grahas"]:
        for a in g["aspects"]:
            assert (a["house"] - g["house"]) % 12 + 1 == a["nth"]
            assert g["id"] in houses[a["house"]]["aspectedBy"]
