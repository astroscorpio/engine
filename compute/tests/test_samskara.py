from conftest import DELHI, call

from astro_compute import samskara as S
from astro_compute.ids import NAKSHATRA_IDS
from astro_compute.meta import AKSHARARAMBH_RULES, ANNAPRASHAN_RULES

DAY_YOGAS = {"utpata", "marana", "kana", "dagdha", "visha"}


def year(kind, y="2027"):
    status, out = call("GET", f"/v1/muhurat/{kind}", {"year": y, **DELHI})
    assert status == 200, out
    return out


def test_annaprashan_days_keep_every_rule():
    out = year("annaprashan")
    assert out["days"]
    tithis = {"dwitiya", "tritiya", "panchami", "saptami", "dashami", "trayodashi"}
    stars = {NAKSHATRA_IDS[i] for i in S.ANNA_STARS}
    for d in out["days"]:
        assert d["vara"] in S.BENEFIC_VARAS and not d["lunarMonth"]["adhika"]
        for w in d["windows"]:
            assert w["start"] < w["end"] and w["paksha"] == "shukla" and w["tithi"] in tithis
            assert w["lagna"] not in ("aries", "scorpio", "pisces") and w["nakshatra"] in stars
    relaxable = {"infancy_old", "venus_set", "sunday"} | DAY_YOGAS
    listed = {d["date"] for d in out["days"]}
    for e in out["excluded"]:
        assert e["date"] not in listed and set(e["rules"]) <= relaxable
        assert [x["rule"] for x in e["details"]] == e["rules"]
    assert {b["rule"] for b in out["blocks"]} <= set(ANNAPRASHAN_RULES)
    assert set(ANNAPRASHAN_RULES) >= relaxable


def test_akshararambh_keeps_what_both_texts_allow():
    out = year("akshararambh")
    assert out["days"]
    tithis = {"dwitiya", "tritiya", "panchami", "dashami", "ekadashi", "dwadashi"}
    stars = {NAKSHATRA_IDS[i] for i in S.AKSHARA_STARS}
    for d in out["days"]:
        assert d["vara"] in S.BENEFIC_VARAS
        for w in d["windows"]:
            assert w["tithi"] in tithis and w["nakshatra"] in stars
            assert w["lagna"] in ("taurus", "gemini", "virgo", "sagittarius", "pisces")
    rules = {r for e in out["excluded"] for r in e["rules"]}
    assert "ds_only" in rules and rules <= {"ds_only", "mc_only"} | DAY_YOGAS
    for e in out["excluded"]:
        assert [x["rule"] for x in e["details"]] == e["rules"]
        assert not {"ds_only", "mc_only"} <= set(e["rules"])  # never allowed by neither text
    assert {b["rule"] for b in out["blocks"]} <= set(AKSHARARAMBH_RULES)
    assert out["vijayadashami"]["date"][:4] == "2027" and "Kerala" in out["vijayadashami"]["note"]
