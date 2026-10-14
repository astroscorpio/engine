"""POST /v1/chart: one birth moment -> the kundli payload in the contract."""

from __future__ import annotations

import re

from jyotisha import ashtakavarga as AV
from jyotisha import dashas as D
from jyotisha import jaimini as J
from jyotisha import panchanga as P
from jyotisha import states as ST
from jyotisha import strength as STR
from jyotisha import upagraha as U
from jyotisha import yogas as Y
from jyotisha.chart import NODE_OWN_BY_SOME, NODE_SIGNS, OWN_SIGNS, SIGN_LORDS, Chart
from jyotisha.ephemeris import DASHA_YEAR, GRAHAS, SEVEN, ayanamsa_value, positions
from jyotisha.vargas import SHODASHAVARGA, VARGA_NAMES

from . import kuja as K
from .errors import invalid
from .fmt import point, provenance, r6, sign_ref
from .ids import (
    GRAHA_ID,
    KARANA_ID,
    NAKSHATRA_IDS,
    NAKSHATRA_LORD,
    SIGN_IDS,
    VARA_ID,
    YOGA_IDS,
    dignity_id,
    functional_id,
    paksha,
    slug,
    tithi_id,
)
from .models import ChartIn, ChartRequest
from .timeutil import Birth, iso, iso_utc, local_jd, parse_instant, resolve_birth

VARGA_CODES = {f"D{d}": d for d in SHODASHAVARGA}
_GRAHA_WORD = re.compile(r"\b(" + "|".join(GRAHAS) + r")\b")

# The engine's own kuja dosha yogas (1,2,4,7,8,12 from the lagna and from the Moon)
# have no source; kuja.py's cited rule replaces them on the chart.
ENGINE_KUJA = {"Kuja Dosha (Mangal)", "Kuja Dosha from the Moon"}

YOGA_ID_OVERRIDES = {
    "Raja Yoga (single lord)": "raja_single_lord",
    "Mala (Srak) Yoga": "mala",
}


def cast(inp: ChartIn) -> tuple[Chart, Birth]:
    birth = resolve_birth(inp.date, inp.time, inp.timeUnknown, inp.place.tz, inp.utcOffset)
    chart = Chart(
        jd=birth.jd,
        lat=inp.place.lat,
        lon=inp.place.lon,
        tz=birth.zone,
        ayanamsa=inp.ayanamsa,
        node=inp.node,
        label=inp.name or "",
    )
    return chart, birth


def at_jd(text: str | None, zone) -> float:
    if text:
        return parse_instant(text, zone)
    from jyotisha.ephemeris import now, parse

    return parse(now().isoformat())


# --- pieces -----------------------------------------------------------------


def moon_uncertainty(inp: ChartIn, birth: Birth) -> tuple[bool, bool]:
    """With the time unknown the Moon could sit anywhere it moved that day."""
    zone = birth.zone
    try:
        start = local_jd(inp.date, 0.0, zone)
        end = local_jd(inp.date, 23.9997, zone)
    except Exception:
        start, end = birth.jd - 0.5, birth.jd + 0.5
    a = positions(start, inp.ayanamsa, inp.node)["Moon"]
    b = positions(end, inp.ayanamsa, inp.node)["Moon"]
    return a.sign != b.sign, a.nakshatra != b.nakshatra


def graha_aspects(chart: Chart, g: str, house_of) -> list[dict]:
    """Graha drishti, BPHS 27.2-3: every graha fully aspects the 7th; Mars also
    the 4th and 8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th. Rahu and
    Ketu have none. Only full aspects are listed."""
    sign = chart.grahas[g].sign
    return [
        {
            "house": house_of((sign + nth - 1) % 12),
            "nth": nth,
            "kind": "full_7th" if nth == 7 else "special",
        }
        for nth in chart.aspects_from(g)
    ]


def dignity_note(chart: Chart, g: str) -> str | None:
    """Rahu and Ketu (BPHS Dasa-phala vv. 35-36): debilitation as the 7th from
    exaltation is our reading; Virgo and Pisces are own signs "according to some"."""
    if g not in NODE_SIGNS:
        return None
    sign = chart.grahas[g].sign
    if sign == NODE_SIGNS[g]["debilitated"]:
        return "node_debilitation_our_reading"
    if sign == NODE_OWN_BY_SOME[g]:
        return "node_own_sign_by_some"
    return None


def yoga_id(y: Y.Yoga) -> str:
    if y.name == "Shakata Yoga" and y.category == "nabhasa/akriti":
        return "shakata_akriti"
    if y.name in YOGA_ID_OVERRIDES:
        return YOGA_ID_OVERRIDES[y.name]
    return slug(y.name.removesuffix(" Yoga"))


def yoga_participants(chart: Chart, y: Y.Yoga) -> list[str]:
    if y.grahas:
        named = set(y.grahas)
    else:
        named = set(_GRAHA_WORD.findall(y.detail))
        if y.category == "lunar":
            named.add("Moon")
        elif y.category == "solar":
            named.add("Sun")
    if y.category in ("nabhasa/sankhya", "nabhasa/ashraya", "nabhasa/akriti"):
        named.update(SEVEN)
    if y.name == "Kala Sarpa Yoga":
        named.update(GRAHAS)
    return [g for g in GRAHAS if g in named]


KUJA_SOURCE = {
    "text": "Sulabh Jyotish Gyan",
    "verse": None,
    "edition": "Vasudev Sadashiva Khankhoje, Hindi, 1943",
    "page": "223-226",
}


def yogas_payload(chart: Chart, house_of, moon_chart: bool) -> list[dict]:
    """One row per (yoga, reference point, participants). The engine reports a
    kendra-trikona pair once from each lord's side; those rows merge, keeping
    both reasons. With the birth time unknown only yogas that hold on sign
    positions alone are listed."""
    out: list[dict] = []
    seen: dict[tuple, dict] = {}
    for y in Y.all_yogas(chart, lagna_known=not moon_chart):
        if y.name in ENGINE_KUJA:
            continue
        category, _, sub = y.category.partition("/")
        grahas = yoga_participants(chart, y)
        key = (yoga_id(y), y.reckoned_from, tuple(grahas))
        if key in seen:
            row = seen[key]
            if y.detail not in row["reason"]:
                row["reason"] += "; " + y.detail
            row["strength"] = max(row["strength"], y.strength)
            continue
        seen[key] = row = {
            "id": yoga_id(y),
            "category": category if y.source else "modern",
            "subcategory": (sub or None) if y.source else None,
            "from": y.reckoned_from,
            "reason": y.detail,
            "grahas": [GRAHA_ID[g] for g in grahas],
            "houses": sorted({house_of(chart.grahas[g].sign) for g in grahas}),
            "strength": y.strength,
            "source": Y.SOURCES[y.source] if y.source else None,
            "notes": list(y.notes),
            "checks": [{"id": k, "holds": v} for k, v in y.checks],
            "bphs": {"met": y.variants["bphs"]} if "bphs" in y.variants else None,
            "phaladipika": (
                {"met": y.variants["phaladipika"]} if "phaladipika" in y.variants else None
            ),
        }
        out.append(row)
    kuja = K.status(chart, not moon_chart)
    if kuja["verdict"]:
        out.append(
            {
                "id": "kuja_dosha",
                "category": "dosha",
                "subcategory": None,
                "from": "lagna",
                "reason": f"Mars in house {kuja['marsHouse']['lagna']} from the lagna ({K.SOURCE})",
                "grahas": ["mars"],
                "houses": [house_of(chart.grahas["Mars"].sign)],
                "strength": 1.0,
                "source": KUJA_SOURCE,
                "notes": [],
                "checks": [],
                "bphs": None,
                "phaladipika": None,
            }
        )
    return out


def balance(first: D.Period, jd: float) -> dict:
    remaining = max(first.end - jd, 0.0)
    years = int(remaining // DASHA_YEAR)
    rest = remaining - years * DASHA_YEAR
    month = DASHA_YEAR / 12
    months = int(rest // month)
    days = int(round(rest - months * month))
    return {"lord": GRAHA_ID[first.lord], "years": years, "months": months, "days": days}


def vimshottari_children(parent: D.Period) -> list[D.Period]:
    """The nine sub-periods of any Vimshottari period, built with the engine's
    own arithmetic, so a five-level chain costs 45 periods instead of 59,049."""
    names = [n for n, _ in D.VIMSHOTTARI]
    i = names.index(parent.lord)
    cycle = D.VIMSHOTTARI[i:] + D.VIMSHOTTARI[:i]
    total = sum(y for _, y in D.VIMSHOTTARI)
    return D._build(parent.start, cycle, total, parent.days, parent.level + 1, parent.level + 1)


def vimshottari_chain(tree: list[D.Period], jd: float, depth: int = 5) -> list[D.Period]:
    chain = D.active(tree, jd)[:1]
    while chain and len(chain) < depth:
        kids = chain[-1].children or vimshottari_children(chain[-1])
        found = next((k for k in kids if k.at(jd)), None)
        if found is None:
            break
        chain.append(found)
    return chain


def period_row(p: D.Period, zone: str) -> dict:
    return {
        "lord": GRAHA_ID.get(p.lord, p.lord),
        "start": iso(p.start, zone),
        "end": iso(p.end, zone),
    }


def dasha_payload(chart: Chart, birth: Birth, when: float, show_balance: bool) -> dict:
    zone = birth.display
    tree = D.vimshottari(chart, depth=2)
    chain = vimshottari_chain(tree, when)
    return {
        "system": "vimshottari",
        "balanceAtBirth": balance(tree[0], chart.jd) if show_balance else None,
        "at": iso(when, zone),
        "current": [{"level": p.level, **period_row(p, zone)} for p in chain],
        "mahadashas": [
            {**period_row(md, zone), "antardashas": [period_row(ad, zone) for ad in md.children]}
            for md in tree
        ],
    }


def ashtakavarga_payload(chart: Chart, basis: int) -> dict:
    bav = AV.bhinna(chart)
    sav = AV.sarva(bav)
    return {
        "bav": {GRAHA_ID[g]: bav[g] for g in SEVEN},
        "bavTotals": {GRAHA_ID[g]: sum(bav[g]) for g in SEVEN},
        "savBySign": sav,
        "savByHouse": [sav[(basis + i) % 12] for i in range(12)],
    }


def varga_payload(chart: Chart, codes: list[str]) -> dict:
    out = {}
    for code in codes:
        d = VARGA_CODES[code]
        vc = chart.d(d)
        out[code] = {
            "name": VARGA_NAMES[d],
            "asc": sign_ref(vc.asc.sign),
            "grahas": {
                GRAHA_ID[g]: {**sign_ref(vc.grahas[g].sign), "dignity": dignity_id(vc.dignity(g))}
                for g in GRAHAS
            },
        }
    return out


def strength_payload(chart: Chart) -> dict:
    balas = STR.shadbala(chart)
    bhava = STR.bhava_bala(chart, balas)
    ik = STR.ishta_kashta(chart, balas)
    vimshopaka = STR.vimshopaka(chart)
    return {
        "shadbala": {
            GRAHA_ID[g]: {
                "total": round(b.total, 2),
                "rupas": round(b.rupas, 3),
                "required": STR.REQUIRED_RUPAS[g],
                "ratio": round(b.ratio, 3),
                "sthana": round(b.sthana_total, 2),
                "dig": round(b.dig, 2),
                "kala": round(b.kala_total, 2),
                "chesta": round(b.chesta, 2),
                "naisargika": round(b.naisargika, 2),
                "drik": round(b.drik, 2),
            }
            for g, b in balas.items()
        },
        "bhavaBala": [{"house": h, "total": round(bhava[h]["total"], 2)} for h in range(1, 13)],
        "vimshopaka": {GRAHA_ID[g]: round(v, 2) for g, v in vimshopaka.items()},
        "ishtaKashta": {
            GRAHA_ID[g]: {"ishta": round(v["ishta"], 2), "kashta": round(v["kashta"], 2)}
            for g, v in ik.items()
        },
    }


def _state_id(text: str) -> str:
    return slug(text.split(" (")[0])


def states_payload(chart: Chart) -> dict:
    out = {}
    for g in GRAHAS:
        pushkara = ST.pushkara(chart, g)
        lajjita = ST.lajjitadi(chart, g)
        out[GRAHA_ID[g]] = {
            "baladi": _state_id(ST.baladi(chart, g)),
            "jagradadi": _state_id(ST.jagradadi(chart, g)),
            "deeptadi": _state_id(ST.deeptadi(chart, g)),
            "lajjitadi": [] if lajjita == ["-"] else [_state_id(x) for x in lajjita],
            "pushkara": [] if pushkara == "-" else [slug(x) for x in pushkara.split(", ")],
            "mrityuBhaga": ST.mrityu_bhaga(chart, g),
            "maranaKaraka": ST.marana_karaka(chart, g),
        }
    return out


# Both schemes are textual (docs/sources/chara-karakas.md): Jaimini Upadesa-sutra
# 1.1.10-19 and BPHS 32.1-15 allow seven karakas (Sun to Saturn) or eight (with
# Rahu, counted as 30 minus its degrees). Neither is favoured, so both are returned.
KARAKA_SOURCE = "Jaimini Upadesa-sutra 1.1.10; BPHS 32.1-2"


def _karakas(chart: Chart, scheme: int) -> tuple[dict[str, str], list[float]]:
    ranked = J.chara_karakas(chart, scheme)
    return (
        {label.lower(): GRAHA_ID[name] for label, (name, _) in ranked.items()},
        [deg for _, deg in ranked.values()],
    )


def jaimini_payload(chart: Chart) -> dict:
    eight, degrees = _karakas(chart, 8)
    seven, _ = _karakas(chart, 7)
    seconds = [round(d * 3600) for d in degrees]
    arudhas = J.all_arudhas(chart)
    return {
        "charaKarakas8": eight,
        "charaKarakas7": seven,
        "differs": [role for role, graha in seven.items() if eight.get(role) != graha],
        # BPHS 32.16-17: two grahas on the same degree (to the second) are read from the
        # sthira karakas instead; not computed here, only flagged.
        "karakaTie": len(set(seconds)) < len(seconds),
        "karakaSource": KARAKA_SOURCE,
        "charaKarakas": eight,  # deprecated alias of charaKarakas8, until ui switches
        "arudhas": {key.lower(): SIGN_IDS[sign] for key, sign in arudhas.items()},
        "karakamsa": SIGN_IDS[J.karakamsa(chart, 8)["karakamsa_sign"]],
    }


def points_payload(chart: Chart) -> dict:
    return {slug(name): point(p) for name, p in U.all_points(chart).items()}


def birth_panchang(chart: Chart, birth: Birth, moon_chart: bool) -> dict:
    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    return {
        "tithi": {"num": pc.tithi, "id": tithi_id(pc.tithi), "paksha": paksha(pc.tithi)},
        "vara": {"id": VARA_ID[pc.vara], "lord": GRAHA_ID[pc.vara]},
        "nakshatra": {"id": NAKSHATRA_IDS[pc.nakshatra], "pada": chart.grahas["Moon"].pada},
        "yoga": {"num": pc.yoga, "id": YOGA_IDS[pc.yoga - 1]},
        "karana": {"id": KARANA_ID[pc.karana]},
        "sunrise": iso(pc.sunrise, birth.display),
        "sunset": iso(pc.sunset, birth.display),
        "dayBirth": None if moon_chart else pc.is_day_birth,
    }


# --- assembly ---------------------------------------------------------------


def build(req: ChartRequest) -> dict:
    codes = list(VARGA_CODES) if req.vargas == "all" else list(dict.fromkeys(req.vargas))
    unknown = [c for c in codes if c not in VARGA_CODES]
    if unknown:
        raise invalid(
            f"unknown varga {unknown[0]!r}; use one of {', '.join(VARGA_CODES)}", "vargas"
        )

    chart, birth = cast(req)
    moon_chart = req.timeUnknown
    moon = chart.grahas["Moon"]
    basis = moon.sign if moon_chart else chart.asc.sign

    def house_of(sign: int) -> int:
        return (sign - basis) % 12 + 1

    sign_unsure, nak_unsure = moon_uncertainty(req, birth) if moon_chart else (False, False)
    include = set(req.include)
    omitted: list[str] = []
    if moon_chart:
        omitted += ["asc", "vargas", "yogas:lagna", "panchang.dayBirth"]
        dropped = include & {"ashtakavarga", "strength", "states", "jaimini", "points"}
        omitted += sorted(dropped)
        include -= dropped
        codes = []
        if nak_unsure:
            omitted.append("dasha.balanceAtBirth")

    sav = None
    payload: dict = {
        "input": req.echo(),
        "resolved": {
            "utc": iso_utc(birth.jd),
            "local": birth.local.isoformat(),
            "utcOffset": birth.utc_offset,
            "jd": round(birth.jd, 8),
            "ayanamsaDeg": r6(ayanamsa_value(birth.jd, req.ayanamsa)),
        },
        "basis": "moon" if moon_chart else "lagna",
        "flags": {
            "timeUnknown": req.timeUnknown,
            "moonChart": moon_chart,
            "moonSignUncertain": sign_unsure,
            "moonNakshatraUncertain": nak_unsure,
        },
        "omitted": omitted,
        "asc": None if moon_chart else point(chart.asc),
    }
    if "ashtakavarga" in include:
        av = ashtakavarga_payload(chart, basis)
        sav = av["savBySign"]

    payload["grahas"] = [
        {
            "id": GRAHA_ID[g],
            **point(chart.grahas[g]),
            "house": house_of(chart.grahas[g].sign),
            "speed": round(chart.grahas[g].speed, 6),
            "retro": chart.grahas[g].retrograde,
            "combust": chart.combust(g),
            "dignity": dignity_id(chart.dignity(g)),
            "dignityNote": dignity_note(chart, g),
            "aspects": graha_aspects(chart, g, house_of),
            "functional": None if moon_chart else functional_id(chart.functional_nature(g)),
            "rules": sorted(house_of(s) for s in OWN_SIGNS.get(g, [])),
            "vargottama": ST.vargottama(chart, g),
        }
        for g in GRAHAS
    ]
    payload["houses"] = [
        {
            "num": h,
            **sign_ref(s),
            "lord": GRAHA_ID[SIGN_LORDS[s]],
            "occupants": [GRAHA_ID[g] for g in GRAHAS if chart.grahas[g].sign == s],
            "aspectedBy": [GRAHA_ID[g] for g in chart.aspecting(s)],
            "sav": sav[s] if sav else None,
        }
        for h in range(1, 13)
        for s in [(basis + h - 1) % 12]
    ]
    payload["mangal"] = K.status(chart, not moon_chart)
    payload["summary"] = {
        "lagna": None if moon_chart else SIGN_IDS[chart.asc.sign],
        "lagnaLord": None if moon_chart else GRAHA_ID[SIGN_LORDS[chart.asc.sign]],
        "moonSign": SIGN_IDS[moon.sign],
        "sunSign": SIGN_IDS[chart.grahas["Sun"].sign],
        "janmaNakshatra": NAKSHATRA_IDS[moon.nakshatra],
        "janmaPada": moon.pada,
        "nakshatraLord": NAKSHATRA_LORD[moon.nakshatra],
    }
    try:
        payload["panchang"] = birth_panchang(chart, birth, moon_chart)
    except RuntimeError:  # no sunrise at polar latitudes
        payload["panchang"] = None
        omitted.append("panchang")

    if "dasha" in include:
        when = at_jd(req.at, birth.display)
        payload["dasha"] = dasha_payload(chart, birth, when, not (moon_chart and nak_unsure))
    if "yogas" in include:
        payload["yogas"] = yogas_payload(chart, house_of, moon_chart)
    if "ashtakavarga" in include:
        payload["ashtakavarga"] = av
    if codes:
        payload["vargas"] = varga_payload(chart, codes)
    if "strength" in include:
        payload["strength"] = strength_payload(chart)
    if "states" in include:
        payload["states"] = states_payload(chart)
    if "jaimini" in include:
        payload["jaimini"] = jaimini_payload(chart)
    if "points" in include:
        payload["points"] = points_payload(chart)
    payload["engine"] = provenance(req.ayanamsa, req.node)
    return payload
