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
        if y["checks"]:
            assert all(c["id"] in meta["yogaChecks"][y["id"]]["checks"] for c in y["checks"])
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
    assert p["windows"]["abhijit"]["reason"] in (None, *meta["windowReasons"])
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


def test_vargas_cite_bphs_1933_and_label_modern_readings():
    status, out = call("GET", "/v1/meta", {"lang": "en"})
    assert status == 200
    vargas = out["vargas"]
    assert len(vargas) == 16
    for v in vargas.values():
        assert v["signifies"] and v["source"]["page"] == "41"
        assert v["source"]["verse"].startswith("PK 3.10")
    modern = {k for k, v in vargas.items() if v["modernReading"]}
    assert modern == {"D3", "D4", "D10", "D40", "D45", "D60"}


def test_travel_labels_map_to_mc_11_rule_ids():
    from astro_compute.muhurta_service import rule_id

    assert rule_id("Yogini left", "defect") == "yogini_ahead"
    assert rule_id("Yogini right", "support") == "yogini_behind"
    assert rule_id("Moon 2nd from birth Moon", "defect") == "moon_from_birth_moon"
    assert (
        rule_id("Moon 3rd from birth Moon, a good house", "support") == "moon_good_from_birth_moon"
    )
    assert (
        rule_id("K1 Pratipada: best for travel (MC 11.9 commentary)", "support")
        == "travel_best_tithi"
    )
    assert rule_id("Chandrashtama", "defect") == "chandrashtama"


def test_hindi_lane_names_cover_every_kind(meta):
    """The lead, 16 Oct 2026: /hi/ pages take every name from meta, never retyping one."""
    from astro_compute.festivals import FESTIVALS

    assert set(meta["festivals"]) == set(FESTIVALS)
    kinds = set(FESTIVALS) | set(meta["observances"])
    assert all(set(d["kinds"]) <= kinds for d in meta["festivalDays"].values())
    assert len(meta["tithiNames"]) == 30 and set(meta["sankrantis"]) == set(meta["signs"])
    assert meta["tithiNames"]["krishna_chaturdashi"] == {
        "name": "Krishna Chaturdashi",
        "tithi": "chaturdashi",
        "paksha": "krishna",
        "num": 29,
    }
    assert all(m["adhikaName"] == f"Adhika {m['name']}" for m in meta["masas"].values())


def test_pending_hindi_labels_name_real_ids(meta):
    """Labels awaiting the lead's review must merge cleanly once their prefix is dropped."""
    import json
    import pathlib

    path = pathlib.Path(__file__).parents[2] / "api/src/meta/hi.labels.json"
    for key, names in json.loads(path.read_text(encoding="utf-8")).items():
        if not key.startswith("_pending_"):
            continue
        section = meta[key.removeprefix("_pending_")]
        for k, v in names.items():
            assert k in section, (key, k)
            assert set(v if isinstance(v, dict) else {"name": v}) <= set(section[k]), (key, k)


def test_mc_cites_give_the_plain_page():
    """The 1925 and 1945 Muhūrta-cintāmaṇi printings share their pages, and /sources names
    the 1945, so a cite gives the page and names no printing; a verse cited with its
    commentary reads "X, p. N, with the commentary, p. M" (the lead's rulings on cite forms).
    The verse and commentary pages are research's, from its map and its reading of each
    commentary."""
    status, out = call("GET", "/v1/meta", {"lang": "en"})
    assert status == 200
    lagna, griha = out["vivahLagnaRules"], out["grihaPraveshRules"]
    for k in ("h1", "h3_venus", "h10_mars", "h12_saturn"):
        assert lagna[k]["source"] == "Muhūrta-cintāmaṇi 6.84, p. 296"
    assert griha["jupiter_sign"]["source"] == "Muhūrta-cintāmaṇi 1.48, p. 40; 13.2, p. 440"
    c, pd = "with the commentary", "Phaladīpikā 26.2–3, pp. 286–287"
    cites = {
        ("vivahLagnaRules", "jamitra_moon"): f"6.65, p. 285, {c}, p. 286",
        ("vivahLagnaRules", "vimsopaka"): f"6.90, p. 301, {c}, p. 302",
        ("vivahLagnaRules", "vimsopaka_poor"): f"6.90, p. 301, {c}, p. 302",
        ("vivahRules", "off_season"): f"6.13, p. 234, {c}, p. 235",
        ("vivahPersonalRules", "sun_groom"): f"6.12, p. 232, {c}, p. 234; {pd}",
        ("vivahPersonalRules", "sun_groom_weak"): f"6.12, p. 232, {c}, pp. 233–234",
        ("grihaPraveshRules", "off_season"): f"13.1, p. 437, {c}, p. 438; 13.4, p. 442",
        ("grihaPraveshRules", "houses_4_8"): f"13.4, p. 442, {c}, p. 443",
    }
    for (section, key), cite in cites.items():
        assert out[section][key]["source"] == f"Muhūrta-cintāmaṇi {cite}", key
    holashtak = out["festivalRules"]["holashtak"]["holashtak_period"]["source"]
    assert holashtak == f"Muhūrta-cintāmaṇi 1.40, p. 33, {c}, p. 34, which quotes the Śīghrabodha"
    assert out["muhurtaRules"]["not_buying_star"]["name"].endswith(f"(MC 2.16, p. 62, {c}, p. 63)")
    sources = [r["source"] for d in (lagna, griha) for r in d.values()]
    assert not [s for s in sources if "printing" in s]
    vastu = out["grihaPraveshNotes"]["vastuPuja"]
    assert "(Muhūrta-cintāmaṇi 13.3a, p. 441; Dharmasindhu p. 242)" in vastu
    yogini = out["muhurtaRules"]["yogini_ahead"]["note"]
    assert out["muhurtaRules"]["yogini_behind"]["note"] == yogini
    notes = ("(MC 11.31, p. 348)", f"(MC 11.31, p. 348, {c}, p. 349)")
    assert all(n in yogini for n in (*notes, "(MC 11.32 commentary, p. 352)"))
    assert "printing" not in vastu + yogini

    def strings(x):
        if isinstance(x, dict):
            x = list(x.values())
        if isinstance(x, list):
            for v in x:
                yield from strings(v)
        elif isinstance(x, str):
            yield x

    assert not [s for s in strings(out) if "and commentary" in s or "and its commentary" in s]
    assert not [s for s in strings(out) if "1.30's" in s or "6.45's" in s]
    middling = out["vivahRules"]["middling_weekday_dvadashi_trayodashi"]["name"]
    assert "(Vasiṣṭha, MC 6.53 commentary, p. 275)" in middling


def test_window_reasons_are_served_not_composed(meta):
    """The lead, 18 Oct 2026: the Abhijit note comes from meta in en and hi, never from the web.
    The English is the wording the web composed."""
    assert meta["windowReasons"] == {"wednesday": {"name": "Not used on Wednesdays"}}


def test_gulika_and_yamaganda_share_the_eighths_note(meta):
    """The lead, 18 Oct 2026: the two windows share one note, served once under windowNotes, with
    BPHS 1933's names of the eighths first (hindi-terms.md decisions 1-2)."""
    w = meta["windows"]
    assert w["gulika"]["noteKey"] == w["yamaganda"]["noteKey"] == "eighths"
    assert w["gulika"]["note"] is None and w["yamaganda"]["note"] is None
    assert all(v["noteKey"] in (None, *meta["windowNotes"]) for v in w.values())
    note = meta["windowNotes"]["eighths"]
    assert note.startswith("In the Bṛhat Parāśara Horā-śāstra (1933 printing)")
    assert note.index("(BPHS 1933 PK 2.67–70, pp. 11–12)") < note.index("these same eighths")


def test_bphs_1933_cites_carry_their_page(meta):
    """The lead, 18 Oct 2026: every cite a reader sees carries its page."""
    import json
    import re

    text = json.dumps(meta, ensure_ascii=False)
    bare = re.findall(r"BPHS 1933 [PU]K [\d.–-]+(?![\d.–-])(?!, pp?\. )", text)
    assert not bare, bare


def test_hindi_sources_keep_the_cite(meta):
    """The lead, 18 Oct 2026: a Hindi source keeps the cite's work and locator byte for byte. Only
    the gloss (in parentheses, or after the colon that ends the reference) is Hindi, so the web's
    short cut still ends at the reference."""
    import json
    import pathlib
    import re

    def skeleton(s: str) -> str:
        head = re.split(r": |\.\s+(?=[A-Z])", s)[0]
        return re.sub(r" ?\([^()]*\)", "", head)

    path = pathlib.Path(__file__).parents[2] / "api/src/meta/hi.labels.json"
    seen = 0
    for section, labels in json.loads(path.read_text(encoding="utf-8")).items():
        if section.startswith("_"):
            continue
        for key, label in labels.items():
            if isinstance(label, dict) and isinstance(label.get("source"), str):
                # the lead: a qualifier outside the cite, such as "main reading", is Hindi
                en = meta[section][key]["source"].replace(", main reading", ", मुख्य पाठ")
                assert skeleton(label["source"]) == skeleton(en), (section, key)
                assert re.search("[\u0900-\u097f]", label["source"]), (section, key)
                seen += 1
    assert seen >= 11
