from conftest import call

from astro_compute.meta import VIVAH_RULES

DELHI = {"lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}
ALLOWED = {
    "mrigashira", "hasta", "mula", "anuradha", "magha", "rohini", "revati",
    "uttara_phalguni", "uttara_ashadha", "uttara_bhadrapada", "swati",
}  # fmt: skip


def year(y):
    status, out = call("GET", "/v1/muhurat/vivah", {"year": y, **DELHI})
    assert status == 200, out
    return out


def test_listed_days_keep_every_day_rule():
    out = year("2026")
    assert out["days"]
    for d in out["days"]:
        assert d["vara"] != "tuesday" and d["grade"] in ("best", "middling")
        assert d["lunarMonth"]["amanta"] in (
            "magha", "phalguna", "vaishakha", "jyeshtha", "ashadha", "kartika", "margashirsha",
        )  # fmt: skip
        for w in d["windows"]:
            assert w["start"] < w["end"] and w["nakshatra"] in ALLOWED
            assert w["tithi"] not in ("chaturthi", "navami", "chaturdashi", "amavasya")
        assert set(d["cautions"]) <= set(VIVAH_RULES)
        g = d["godhuli"]
        if g and d["vara"] == "thursday":  # MC 6.99: only before sunset
            assert g["start"] < g["end"]
    for b in out["blocks"]:
        assert b["rule"] in VIVAH_RULES


def test_venus_infancy_follows_the_side_it_rises_on():
    # MC 5.27: 10 days after rising in the west (Jan 2026's superior conjunction),
    # 3 after rising in the east (Oct 2026's inferior conjunction).
    blocks = [b for b in year("2026")["blocks"] if b["rule"] == "venus_infant"]
    assert [b["detail"] for b in blocks] == [
        "10 days after rising in the west",
        "3 days after rising in the east",
    ]


def test_no_listed_day_inside_a_block():
    out = year("2027")
    for b in out["blocks"]:
        if b["rule"] in ("jupiter_set", "venus_set", "jupiter_sign", "eclipse"):
            inside = [d["date"] for d in out["days"] if b["start"][:10] < d["date"] < b["end"][:10]]
            assert not inside, (b, inside)


def test_excluded_days_carry_their_relaxed_rules():
    out = year("2026")
    relaxable = {
        "vedha_slow", "jupiter_sign", "tuesday", "rikta", "solar_month", "infancy_old",
        "venus_set", "eclipse",
    }  # fmt: skip
    listed = {d["date"] for d in out["days"]}
    assert out["excluded"]
    for d in out["excluded"]:
        assert d["date"] not in listed and d["windows"]
        assert set(d["rules"]) <= relaxable and len(d["reasons"]) == len(d["rules"])
        assert all(not k.startswith("_") for w in d["windows"] for k in w)
    # Jupiter enters Leo on 31 Oct 2026: November's candidates are excluded, with the reason.
    late = [d for d in out["excluded"] if d["date"] >= "2026-11-21"]
    assert late and all("jupiter_sign" in d["rules"] for d in late)
