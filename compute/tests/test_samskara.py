from conftest import DELHI, call

from astro_compute import samskara as S
from astro_compute.festivals import KOCHI, festival
from astro_compute.ids import NAKSHATRA_IDS
from astro_compute.meta import AKSHARARAMBH_RULES, ANNAPRASHAN_RULES
from astro_compute.models import EkadashiQuery
from astro_compute.observances import _sunrises
from astro_compute.timeutil import parse_instant

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
    vidya = {"date": "2027-10-10", "nsDate": "2027-10-09", "note": S.VIDYARAMBHAM_NOTE}
    assert out["vijayadashami"] == vidya


# kerala-vidyarambham-sources.md section 3: Kochi's Vidyarambham day (Kerala's holiday lists for
# 2022 to 2026), and our afternoon-rule day there (nsDate).
KERALA_DAYS = {
    2022: ("2022-10-05", "2022-10-04"),
    2023: ("2023-10-24", "2023-10-24"),
    2024: ("2024-10-13", "2024-10-12"),
    2025: ("2025-10-02", "2025-10-02"),
    2026: ("2026-10-21", "2026-10-20"),
    2027: ("2027-10-10", "2027-10-09"),
    2028: ("2028-09-28", "2028-09-27"),
    2029: ("2029-10-16", "2029-10-16"),
}


def _vidyarambham(y, lat=KOCHI["lat"], lon=KOCHI["lon"], tz=KOCHI["tz"]):
    q = EkadashiQuery(year=y, lat=lat, lon=lon, tz=tz)
    vijaya = festival("vijayadashami", q)["occurrences"][0]
    return S._vidyarambham(q, vijaya), vijaya


def test_vidyarambham_is_the_first_sunrise_at_kochi_after_the_dashami_begins():
    for y, days in KERALA_DAYS.items():
        block, _ = _vidyarambham(y)
        assert (block["date"], block["nsDate"]) == days, y


def test_vidyarambham_has_one_date_for_every_city():
    # 2027 and 2028: our afternoon rule gives London the earlier day and Sydney the later.
    for y, sydney_ns in ((2027, "2027-10-10"), (2028, "2028-09-28")):
        london, _ = _vidyarambham(y, 51.5074, -0.1278, "Europe/London")
        sydney, _ = _vidyarambham(y, -33.8688, 151.2093, "Australia/Sydney")
        assert london["date"] == sydney["date"] == KERALA_DAYS[y][0]
        assert (london["nsDate"], sydney["nsDate"]) == (KERALA_DAYS[y][1], sydney_ns)


def test_vidyarambham_when_the_dashami_holds_no_sunrise():
    # 2058 at Kochi: the Dashami runs from 07:26 IST on 26 Oct to 05:02 on 27 Oct, between two
    # sunrises, so Kerala's day is the day after the Mahanavami.
    block, vijaya = _vidyarambham(2058)
    start, end = (parse_instant(vijaya["tithi"][k], KOCHI["tz"]) for k in ("start", "end"))
    (rise,) = _sunrises(end, KOCHI["lat"], KOCHI["lon"], 1)
    assert rise < start  # the last sunrise before the Dashami ends came before it began
    assert (block["date"], block["nsDate"]) == ("2058-10-27", "2058-10-26")


def test_an_empty_annaprashan_year_names_its_nearest_days():
    out = year("annaprashan", "2026")
    assert out["days"] == [] and out["nearest"]
    tests = {"barred_stretches", "vishti_yogas", "lagna", "house_10", "malefic_1_4_7"}
    tests |= {"moon_6_8", "guru_7_8_9"}
    for n in out["nearest"]:
        assert n["rules"] and set(n["rules"]) <= tests and set(n["rules"]) <= set(ANNAPRASHAN_RULES)
    assert year("annaprashan")["nearest"] == []  # 2027 has days


def test_akshararambh_flags_its_night_windows():
    out = year("akshararambh")
    windows = [w for d in out["days"] for w in d["windows"]]
    assert any(w.get("night") for w in windows) and any(not w.get("night") for w in windows)
    for d in out["days"]:
        flags = [bool(w.get("night")) for w in d["windows"]]
        assert flags == sorted(flags)  # the daytime windows first, then the night's


def _middle(w):
    import datetime as dt

    a, b = (dt.datetime.fromisoformat(w[k]) for k in ("start", "end"))
    return (a + (b - a) / 2).isoformat()


def _check(act, at, chart=None, **extra):
    body = {"act": act, "at": at, **{k: float(v) if k != "tz" else v for k, v in DELHI.items()}}
    if chart:
        body["chart"] = chart
    status, out = call("POST", "/v1/muhurta/check", body={**body, **extra})
    assert status == 200, out
    return {r["id"] for r in out["vetoes"]}


def _child(at, days):
    import datetime as dt

    from conftest import EXAMPLE

    born = (dt.datetime.fromisoformat(at) - dt.timedelta(days=days)).date()
    return {"name": "Child", "date": born.isoformat(), "time": "10:00", "place": EXAMPLE["place"]}


def test_the_samskara_finder_acts_agree_with_their_lists():
    anna = year("annaprashan")
    at = _middle(anna["days"][0]["windows"][0])
    assert not {v for v in _check("annaprashan", at) if v.endswith("_annaprashan")}
    # A boy in his 7th month is not due; in his 6th he is (MC 5.17).
    assert "month_of_life" in _check("annaprashan", at, _child(at, 6 * 30.44 + 5), child="boy")
    assert "month_of_life" not in _check("annaprashan", at, _child(at, 5 * 30.44 + 5), child="boy")
    letters = year("akshararambh")
    day = next(d for d in letters["days"] if not d["windows"][0].get("night"))
    at = _middle(day["windows"][0])
    assert not {v for v in _check("akshararambh", at) if v.endswith("_akshararambh")}
    assert "fifth_year" in _check("akshararambh", at, _child(at, 3 * 365))
    assert "fifth_year" not in _check("akshararambh", at, _child(at, 4.5 * 365))
