"""The complete reading: every technique in the package, applied to a date.

Nothing is selected or filtered here.  If a module can say something about a
moment, it says it.  Selecting which techniques to report *after* seeing them
is the main way a reading becomes unfalsifiable, so the choice is removed.
"""

from __future__ import annotations

from . import ashtakavarga as AV
from . import dashas as D
from . import jaimini as J
from . import panchanga as PA
from . import rare as R
from . import states as ST
from . import strength as STR
from . import tajika as T
from . import upagraha as U
from . import yogas as Y
from .chart import Chart
from .ephemeris import (
    GRAHAS,
    NAKSHATRAS,
    SEVEN,
    SIGNS,
    TimeZone,
    eclipses,
    fmt,
    positions,
    station_dates,
)
from .vargas import varga

TARA = ["Janma", "Sampat", "Vipat", "Kshema", "Pratyari", "Sadhaka", "Vadha", "Mitra", "Ati-mitra"]
GOOD_TARA = {1, 3, 5, 7, 8}


def _trees(chart: Chart) -> dict:
    return {
        "Vimshottari": D.vimshottari(chart, depth=5),
        "Yogini": D.yogini(chart, depth=3),
        "Ashtottari": D.ashtottari(chart, depth=3),
        "Narayana": J.narayana_dasha(chart),
        "Chara (A)": J.chara_dasha(chart, convention="A"),
        "Chara (B)": J.chara_dasha(chart, convention="B"),
        "Drig": J.drig_dasha(chart),
        "Shoola": J.shoola_dasha(chart),
        "Sthira": J.sthira_dasha(chart),
    }


def everything(
    chart: Chart,
    jd: float,
    tz: TimeZone = 0.0,
    trees: dict | None = None,
    cache: dict | None = None,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> dict:
    """Every reading this package can produce for one moment."""
    cache = cache if cache is not None else {}
    trees = trees or _trees(chart)
    observer_lat = chart.lat if observer_lat is None else observer_lat
    observer_lon = chart.lon if observer_lon is None else observer_lon
    m = positions(jd, chart.ayanamsa, chart.node)
    pc = PA.compute(jd, observer_lat, observer_lon, chart.ayanamsa)
    out: dict[str, object] = {"date": fmt(jd, tz), "vara": pc.vara}

    # 1. every dasha system, every level
    out["dashas"] = {name: "-".join(p.lord for p in D.active(t, jd)) for name, t in trees.items()}
    out["dasha_dates"] = [
        (p.level, p.lord, fmt(p.start, tz), fmt(p.end, tz))
        for p in D.active(trees["Vimshottari"], jd)
    ]

    # 2. panchanga, all five limbs plus hora
    out["panchanga"] = {
        "tithi": f"{pc.tithi} {pc.tithi_name} ({pc.paksha})",
        "vara": pc.vara,
        "nakshatra": pc.nakshatra_name,
        "yoga": pc.yoga_name,
        "karana": pc.karana,
        "hora": pc.hora_lord,
        "sunrise": fmt(pc.sunrise, tz, True)[-5:],
        "sunset": fmt(pc.sunset, tz, True)[-5:],
    }

    # 3. transiting positions, states and house placement
    tr = {}
    for g in GRAHAS:
        p = m[g]
        house = (p.sign - chart.asc.sign) % 12 + 1
        from_moon = (p.sign - chart.grahas["Moon"].sign) % 12 + 1
        vgo = int(p.longitude // 30) == int(varga(p.longitude, 9) // 30)
        sixty = R.shashtiamsa(p.longitude)
        tr[g] = {
            "position": str(p),
            "house": house,
            "from_moon": from_moon,
            "nakshatra": NAKSHATRAS[p.nakshatra],
            "pada": p.pada,
            "retrograde": p.retrograde,
            "sav": AV.sarva(AV.bhinna(chart))[p.sign],
            "vargottama": vgo,
            "shashtiamsa": f"{sixty[0]} ({'benign' if sixty[1] else 'harsh'})",
            "nadi_amsa": R.nadi_amsa(p.longitude),
            "D9": SIGNS[int(varga(p.longitude, 9) // 30)],
            "D10": SIGNS[int(varga(p.longitude, 10) // 30)],
            "D24": SIGNS[int(varga(p.longitude, 24) // 30)],
            "D60": SIGNS[int(varga(p.longitude, 60) // 30)],
        }
    out["transits"] = tr

    # 4. kakshya for all seven, not just the slow pair
    out["kakshya"] = {g: AV.kakshya_transit(chart, m, g) for g in SEVEN}

    # 5. gochara from the Moon, with vedha
    from .hypotheses import GOCHARA_GOOD, NO_VEDHA_BETWEEN, VEDHA

    houses = {g: (m[g].sign - chart.grahas["Moon"].sign) % 12 + 1 for g in SEVEN}
    goc = {}
    for g in SEVEN:
        h = houses[g]
        good = h in GOCHARA_GOOD[g]
        blocker = VEDHA[g].get(h)
        obstructed = bool(blocker) and any(
            o != g and houses[o] == blocker and {g, o} not in NO_VEDHA_BETWEEN for o in SEVEN
        )
        goc[g] = {
            "house_from_moon": h,
            "favourable": good,
            "obstructed": obstructed,
            "net": good and not obstructed,
        }
    out["gochara"] = goc

    # 6. transit-to-natal contacts, by aspect and by degree
    contacts = []
    special_aspects = {
        "Mars": (90.0, 210.0),
        "Jupiter": (120.0, 240.0),
        "Saturn": (60.0, 270.0),
    }
    for g in GRAHAS:
        for n in GRAHAS + ["Ascendant"]:
            target = chart.asc.longitude if n == "Ascendant" else chart.grahas[n].longitude
            sep = abs((m[g].longitude - target + 180) % 360 - 180)
            if sep <= 3.0:
                contacts.append(f"transit {g} on natal {n} ({sep:.1f} deg)")
            elif abs(sep - 180) <= 3.0:
                contacts.append(f"transit {g} opposite natal {n}")
            directed = (target - m[g].longitude) % 360
            for angle in special_aspects.get(g, ()):
                orb = abs((directed - angle + 180) % 360 - 180)
                if orb <= 3.0:
                    contacts.append(
                        f"transit {g} special aspect {angle:.0f}° to natal {n} (orb {orb:.1f}°)"
                    )
    out["natal_contacts"] = contacts

    # 7. sensitive points: upagrahas, special lagnas, arudhas, karakamsa,
    #    Bhrigu Bindu, sahams
    if "points" not in cache:
        cache["points"] = U.all_points(chart)
        cache["arudhas"] = J.all_arudhas(chart)
        cache["karakamsa"] = J.karakamsa(chart)
        cache["sahams"] = T.sahams(chart)
        cache["bb"] = R.bhrigu_bindu(chart)
    hits = []
    for name, p in cache["points"].items():
        for g in ("Saturn", "Jupiter", "Mars", "Rahu", "Ketu", "Sun"):
            sep = abs((m[g].longitude - p.longitude + 180) % 360 - 180)
            if sep <= 5.0:
                hits.append(f"{g} on {name} ({sep:.1f} deg)")
    for key, sign in cache["arudhas"].items():
        if key in ("AL", "UL"):
            for g in ("Saturn", "Jupiter", "Rahu", "Ketu", "Mars"):
                if m[g].sign == sign:
                    hits.append(f"{g} in {key} sign ({SIGNS[sign]})")
    for g in ("Saturn", "Jupiter"):
        if m[g].sign == cache["karakamsa"]["karakamsa_sign"]:
            hits.append(f"{g} on karakamsa")
    for name, p in cache["sahams"].items():
        for g in ("Saturn", "Jupiter", "Mars", "Sun"):
            sep = abs((m[g].longitude - p.longitude + 180) % 360 - 180)
            if sep <= 5.0:
                hits.append(f"{g} on saham {name} ({sep:.1f} deg)")
    out["point_hits"] = hits
    out["bhrigu"] = R.bhrigu_hits(chart, jd, orb=5.0)

    # 8. the rare chakras and cycles
    out["rare"] = {
        "kota": R.kota_chakra(chart, jd),
        "sarvatobhadra": R.sarvatobhadra(chart, jd),
        "latta": R.latta(chart, jd),
        "ghataka": R.ghataka(
            chart,
            jd,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
        ),
        "moorthi": R.moorthi(chart, jd),
        "pancha_pakshi": R.pancha_pakshi(
            chart,
            jd,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
        ),
        "panchaka": R.panchaka(
            chart,
            jd,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
        ),
        "vara_nakshatra": R.vara_nakshatra_yogas(
            chart,
            jd,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
        ),
        "sudarshana": R.sudarshana(chart, jd),
        "tripataki": R.tripataki(chart, jd),
        "abhijit": tuple(
            fmt(x, tz, True)[-5:]
            for x in R.abhijit_muhurta(
                chart,
                jd,
                observer_lat=observer_lat,
                observer_lon=observer_lon,
            )
        ),
        "chogadiya": [
            (x["name"], fmt(x["start"], tz, True)[-5:], x["quality"])
            for x in R.chogadiya(
                chart,
                jd,
                observer_lat=observer_lat,
                observer_lon=observer_lon,
            )
        ],
        "kalas": {
            k: (fmt(v[0], tz, True)[-5:], fmt(v[1], tz, True)[-5:])
            for k, v in R.daily_kalas(
                chart,
                jd,
                observer_lat=observer_lat,
                observer_lon=observer_lon,
            ).items()
        },
    }

    # 9. balas
    t_i = ((m["Moon"].nakshatra - chart.grahas["Moon"].nakshatra) % 27) % 9
    out["balas"] = {
        "tara": f"{TARA[t_i]} ({'good' if t_i in GOOD_TARA else 'adverse'})",
        "chandra": (m["Moon"].sign - chart.grahas["Moon"].sign) % 12 + 1,
        "guru": (m["Jupiter"].sign - chart.grahas["Moon"].sign) % 12 + 1,
    }

    # 10. the running lords, in full
    if "shadbala" not in cache:
        cache["shadbala"] = STR.shadbala(chart)
        cache["ik"] = STR.ishta_kashta(chart, cache["shadbala"])
        cache["vp"] = STR.vimshopaka(chart)
        cache["bhava"] = STR.bhava_bala(chart, cache["shadbala"])
    lords = []
    for p in D.active(trees["Vimshottari"], jd)[:5]:
        g = p.lord
        if g not in chart.grahas:
            continue
        row = {
            "level": p.level,
            "lord": g,
            "dignity": chart.dignity(g),
            "house": chart.house(g),
            "rules": chart.houses_ruled(g),
            "baladi": ST.baladi(chart, g),
            "deeptadi": ST.deeptadi(chart, g),
            "jagradadi": ST.jagradadi(chart, g),
            "lajjitadi": ST.lajjitadi(chart, g),
            "vargottama": ST.vargottama(chart, g),
            "marana_karaka": ST.marana_karaka(chart, g),
            "mrityu_bhaga": ST.mrityu_bhaga(chart, g),
        }
        if g in SEVEN:
            row["shadbala_rupas"] = round(cache["shadbala"][g].rupas, 2)
            row["shadbala_ratio"] = round(cache["shadbala"][g].ratio, 2)
            row["ishta"] = round(cache["ik"][g]["ishta"], 1)
            row["kashta"] = round(cache["ik"][g]["kashta"], 1)
            row["vimshopaka"] = round(cache["vp"][g], 2)
        lords.append(row)
    out["running_lords"] = lords

    # 11. annual chart
    years = int((jd - chart.jd) / 365.2563)
    annual_key = f"varsha:{years}:{observer_lat}:{observer_lon}:{tz}"
    if annual_key not in cache:
        annual = T.varsha_chart(
            chart,
            years,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
            observer_timezone=tz,
        )
        cache[annual_key] = (annual, T.mudda_dasha(annual), T.patyayini_dasha(annual))
    v, mudda, patya = cache[annual_key]
    out["annual"] = {
        "muntha_sign": SIGNS[v.muntha_sign],
        "muntha_house": v.muntha_house,
        "varshesha": v.varshesha,
        "mudda": next((d["lord"] for d in mudda if d["start"] <= jd < d["end"]), "-"),
        "patyayini": next((d["lord"] for d in patya if d["start"] <= jd < d["end"]), "-"),
    }

    # 12. Tajika aspects among the transiting grahas
    day_chart = Chart(
        jd=jd,
        lat=observer_lat,
        lon=observer_lon,
        tz=tz,
        ayanamsa=chart.ayanamsa,
        node=chart.node,
    )
    out["tajika_today"] = [
        f"{a['a']} {a['aspect']} {a['b']} - {a['kind']}" for a in T.tajika_aspects(day_chart)
    ][:8]
    out["yogas_today"] = [y.name for y in Y.all_yogas(day_chart)]
    out["prashna"] = {
        "cast": False,
        "reason": "Horary requires a real question asked at this moment.",
    }

    # 13. sky events
    out["events"] = []
    for g in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        for s in station_dates(g, jd - 3, jd + 3, chart.ayanamsa):
            out["events"].append(f"{g} stations {s['direction']} {fmt(s['jd'], tz)}")
    for e in eclipses(jd - 20, jd + 20):
        out["events"].append(f"{e['kind']} eclipse {fmt(e['jd'], tz)}")
    for g in SEVEN:
        if g != "Sun" and day_chart.combust(g):
            out["events"].append(f"{g} combust")
    return out
