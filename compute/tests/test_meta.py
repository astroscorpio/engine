from conftest import AT, DELHI, EXAMPLE, call


def test_every_emitted_id_has_a_meta_entry(chart, panchang, meta):
    for g in chart["grahas"]:
        assert g["id"] in meta["grahas"] and g["sign"] in meta["signs"]
        assert g["nakshatra"] in meta["nakshatras"]
        assert g["dignity"] in meta["dignities"] or (
            g["dignity"] is None and g["id"] in ("rahu", "ketu")
        )
        assert g["dignityNote"] is None or g["dignityNote"] in meta["dignityNotes"]
    for y in chart["yogas"]:
        assert y["id"] in meta["yogas"], y["id"]
        assert meta["yogas"][y["id"]]["category"] == y["category"]
        assert all(n in meta["yogaNotes"] for n in y["notes"]), y["notes"]
    for code, v in chart["vargas"].items():
        assert code in meta["vargas"]
        for gid, row in v["grahas"].items():
            assert row["dignity"] in meta["dignities"] or (
                row["dignity"] is None and gid in ("rahu", "ketu")
            )
    for group, values in chart["states"]["sun"].items():
        if group in meta["states"]:
            ids = values if isinstance(values, list) else [values]
            assert all(i in meta["states"][group] for i in ids), (group, values)
    assert set(chart["jaimini"]["charaKarakas"]) <= set(meta["charaKarakas"])
    p = panchang
    assert p["vara"]["id"] in meta["varas"]
    for row in p["sequence"]["tithi"]:
        assert row["id"] in meta["tithis"] and row["num"] in meta["tithis"][row["id"]]["num"]
    assert all(r["id"] in meta["panchangYogas"] for r in p["sequence"]["yoga"])
    assert all(r["id"] in meta["karanas"] for r in p["sequence"]["karana"])
    assert all(
        r["id"] in meta["choghadiya"] for r in p["choghadiya"]["day"] + p["choghadiya"]["night"]
    )
    assert all(r["id"] in meta["windows"] for r in p["windows"]["avoid"])
    assert all(r["id"] in meta["specialYogas"] for r in p["specialYogas"])
    assert p["lunarMonth"]["amanta"] in meta["masas"]


def test_muhurta_rule_ids_are_known(meta):
    status, out = call(
        "GET",
        "/v1/muhurta",
        {"act": "home", "from": "2026-10-15", "until": "2026-10-16", "top": "50", **DELHI},
    )
    assert status == 200
    status, chk = call(
        "POST",
        "/v1/muhurta/check",
        body={
            "act": "general",
            "at": AT,
            "chart": EXAMPLE,
            "lat": 28.6139,
            "lon": 77.209,
            "tz": "Asia/Kolkata",
        },
    )
    rows = (
        [r for w in out["windows"] for r in w["defects"] + w["supports"]]
        + chk["vetoes"]
        + chk["defects"]
        + chk["supports"]
    )
    assert rows
    for r in rows:
        assert r["id"] in meta["muhurtaRules"], r


def test_meta_is_english_only_for_now():
    assert call("GET", "/v1/meta", {"lang": "hi"})[0] == 400
