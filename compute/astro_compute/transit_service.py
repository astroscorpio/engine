"""GET|POST /v1/transits: the sky now, and how it falls on a birth chart."""

from __future__ import annotations

from jyotisha import ashtakavarga as AV
from jyotisha.chart import Chart
from jyotisha.ephemeris import (
    GRAHAS,
    SEVEN,
    crossings,
    ingress_dates,
    positions,
    station_dates,
)

from .chart_service import at_jd, cast
from .errors import invalid
from .fmt import point, provenance, r6
from .ids import ENGINE_GRAHA, GRAHA_ID, NAKSHATRA_IDS, SIGN_IDS
from .models import EventsQuery, TransitRequest
from .timeutil import iso, iso_utc, parse_instant

# Copies of jyotisha.hypotheses.GOCHARA_GOOD / VEDHA / NO_VEDHA_BETWEEN.
# Importing hypotheses at runtime drags in the whole backtest stack, so the
# tables are mirrored here and tests/test_transits.py pins them to the engine.
GOCHARA_GOOD = {
    "Sun": {3, 6, 10, 11},
    "Moon": {1, 3, 6, 7, 10, 11},
    "Mars": {3, 6, 11},
    "Mercury": {2, 4, 6, 8, 10, 11},
    "Jupiter": {2, 5, 7, 9, 11},
    "Venus": {1, 2, 3, 4, 5, 8, 9, 11, 12},
    "Saturn": {3, 6, 11},
}
VEDHA = {
    "Sun": {3: 9, 6: 12, 10: 4, 11: 5},
    "Moon": {1: 5, 3: 9, 6: 12, 7: 2, 10: 4, 11: 8},
    "Mars": {3: 12, 6: 9, 11: 5},
    "Mercury": {2: 5, 4: 3, 6: 9, 8: 1, 10: 8, 11: 12},
    "Jupiter": {2: 12, 5: 4, 7: 3, 9: 10, 11: 8},
    "Venus": {1: 8, 2: 7, 3: 1, 4: 10, 5: 9, 8: 5, 9: 11, 11: 6, 12: 3},
    "Saturn": {3: 12, 6: 9, 11: 5},
}
NO_VEDHA_BETWEEN = [{"Sun", "Saturn"}, {"Moon", "Mercury"}]
# The nodes have no vedha table; 3, 6 and 11 from the Moon is the common rule.
NODE_GOOD = {3, 6, 11}
STATION_GRAHAS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")
# Longest direct run between stations, padded: how far to look for the
# station that began the current motion and the one that will end it.
STATION_WINDOW = {"Mercury": 130, "Venus": 600, "Mars": 800, "Jupiter": 400, "Saturn": 400}
NAKSHATRA_WIDTH = 360 / 27
MAX_EVENT_DAYS = 1100
MAX_MOON_DAYS = 63
YEAR = 365.25
SADE_SATI_MERGE = 3 * YEAR  # a retrograde dip out of the band does not end it


def _gochara(natal: Chart, moving: dict) -> dict[str, tuple[str, str | None]]:
    moon = natal.grahas["Moon"].sign
    houses = {g: (moving[g].sign - moon) % 12 + 1 for g in GRAHAS}
    out = {}
    for g in GRAHAS:
        h = houses[g]
        good = GOCHARA_GOOD.get(g, NODE_GOOD)
        if h not in good:
            out[g] = ("bad", None)
            continue
        blocker_house = VEDHA.get(g, {}).get(h)
        blocker = next(
            (
                o
                for o in SEVEN
                if o != g and houses[o] == blocker_house and {g, o} not in NO_VEDHA_BETWEEN
            ),
            None,
        )
        out[g] = ("neutral", GRAHA_ID[blocker]) if blocker else ("good", None)
    return out


def _kakshya(natal: Chart, moving: dict, g: str, bav: dict) -> dict:
    p = moving[g]
    idx, lord = AV.kakshya(p.longitude)
    refs = {name: natal.grahas[name].sign for name in SEVEN}
    refs["Asc"] = natal.asc.sign
    active = ((p.sign - refs[lord]) % 12 + 1) in AV.BAV_RULES[g][lord]
    return {"num": idx + 1, "lord": "lagna" if lord == "Asc" else GRAHA_ID[lord], "active": active}


def _sade_sati(moon_sign: int, when: float, ay: str, zone: str) -> dict:
    band = {(moon_sign - 1) % 12, moon_sign, (moon_sign + 1) % 12}
    start, end = when - 8 * YEAR, when + 24 * YEAR
    sign0 = positions(start, ay)["Saturn"].sign
    edges = ingress_dates("Saturn", start, end, ay, step=2.0)
    spans, inside, since = [], sign0 in band, start if sign0 in band else None
    for e in edges:
        now_in = e["sign"] in band
        if now_in and not inside:
            since = e["jd"]
        elif inside and not now_in:
            spans.append([since, e["jd"]])
        inside = now_in
    if inside:
        spans.append([since, None])
    merged: list[list] = []
    for s in spans:
        if merged and merged[-1][1] is not None and s[0] - merged[-1][1] < SADE_SATI_MERGE:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    current = next((s for s in merged if s[0] <= when and (s[1] is None or when < s[1])), None)
    upcoming = next((s for s in merged if s[0] > when), None)
    offset = (positions(when, ay)["Saturn"].sign - moon_sign) % 12
    phase = {11: "rising", 10: "rising", 0: "peak", 1: "setting", 2: "setting"}.get(offset)

    def stamp(jd):
        return iso(jd, zone) if jd is not None else None

    return {
        "active": current is not None,
        "phase": phase if current else None,
        # a span that began before the search window has no known start
        "start": stamp(current[0]) if current and current[0] > start else None,
        "end": stamp(current[1]) if current else None,
        "next": {"start": stamp(upcoming[0]), "end": stamp(upcoming[1])} if upcoming else None,
    }


def _upcoming(when: float, days: int, ay: str, node: str, zone: str) -> list[dict]:
    if days <= 0:
        return []
    end = when + days
    events = []
    for g in GRAHAS:
        if g == "Moon":
            continue
        for e in ingress_dates(g, when, end, ay, step=1.0, node=node):
            events.append(
                (
                    e["jd"],
                    {
                        "type": "ingress",
                        "graha": GRAHA_ID[g],
                        "at": iso(e["jd"], zone),
                        "sign": SIGN_IDS[e["sign"]],
                        "fromSign": SIGN_IDS[e["from_sign"]],
                    },
                )
            )
    for g in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        for e in station_dates(g, when, end, ay):
            events.append(
                (
                    e["jd"],
                    {
                        "type": "station",
                        "graha": GRAHA_ID[g],
                        "at": iso(e["jd"], zone),
                        "direction": e["direction"],
                    },
                )
            )
    return [row for _, row in sorted(events, key=lambda x: x[0])]


def _motion(g: str, when: float, retro: bool, ay: str, zone: str) -> dict:
    if g not in STATION_GRAHAS:
        return {"retro": retro, "since": None, "until": None}
    window = STATION_WINDOW[g]
    before = station_dates(g, when - window, when, ay, step=1.0)
    after = station_dates(g, when, when + window, ay, step=1.0)
    return {
        "retro": retro,
        "since": iso(before[-1]["jd"], zone) if before else None,
        "until": iso(after[0]["jd"], zone) if after else None,
    }


def events(q: EventsQuery) -> dict:
    """Sign ingresses, nakshatra ingresses and stations in [start, end)."""
    start = parse_instant(q.start, "UTC", "start")
    end = parse_instant(q.end, "UTC", "end")
    if end <= start:
        raise invalid("end must follow start", "end")
    names = [ENGINE_GRAHA.get(g.strip(), "") for g in q.grahas.split(",") if g.strip()]
    if not names or "" in names:
        raise invalid("grahas must be a comma list of graha ids", "grahas")
    kinds = {k.strip() for k in q.kinds.split(",") if k.strip()}
    if not kinds or kinds - {"sign", "nakshatra", "station"}:
        raise invalid("kinds must be drawn from sign, nakshatra, station", "kinds")
    span = end - start
    if span > MAX_EVENT_DAYS or ("Moon" in names and span > MAX_MOON_DAYS):
        raise invalid("span too long (Moon: 62 days, others: 1096 days)", "end")

    rows: list[tuple[float, dict]] = []
    for g in names:
        step = 0.25 if g == "Moon" else 1.0
        gid = GRAHA_ID[g]
        for kind, width, ids, a, b in (
            ("sign", 30.0, SIGN_IDS, "sign", "fromSign"),
            ("nakshatra", NAKSHATRA_WIDTH, NAKSHATRA_IDS, "nakshatra", "fromNakshatra"),
        ):
            if kind not in kinds:
                continue
            for e in crossings(g, start, end, width, q.ayanamsa, step, node=q.node):
                rows.append(
                    (
                        e["jd"],
                        {
                            "type": kind,
                            "graha": gid,
                            "jd": round(e["jd"], 7),
                            "at": iso_utc(e["jd"]),
                            "lon": r6(e["longitude"]),
                            "retro": e["speed"] < 0,
                            a: ids[e["index"]],
                            b: ids[e["from_index"]],
                        },
                    )
                )
        if "station" in kinds and g in STATION_GRAHAS:
            for e in station_dates(g, start, end, q.ayanamsa, step=1.0):
                rows.append(
                    (
                        e["jd"],
                        {
                            "type": "station",
                            "graha": gid,
                            "jd": round(e["jd"], 7),
                            "at": iso_utc(e["jd"]),
                            "lon": r6(e["longitude"]),
                            "retro": e["direction"] == "retrograde",
                            "direction": e["direction"],
                        },
                    )
                )
    rows.sort(key=lambda r: r[0])
    return {
        "start": iso_utc(start),
        "end": iso_utc(end),
        "ayanamsa": q.ayanamsa,
        "node": q.node,
        "events": [row for _, row in rows],
        "engine": provenance(q.ayanamsa, q.node),
    }


def build(req: TransitRequest) -> dict:
    natal = birth = None
    if req.chart is not None:
        natal, birth = cast(req.chart)
        ay, node, zone = req.chart.ayanamsa, req.chart.node, birth.display
    else:
        ay, node, zone = req.ayanamsa, req.node, "UTC"
    when = at_jd(req.at, zone)
    moving = positions(when, ay, node)
    known_time = natal is not None and not req.chart.timeUnknown

    gochara = _gochara(natal, moving) if natal else {}
    bav = AV.bhinna(natal) if known_time else None
    sav = AV.sarva(bav) if bav else None
    rows = []
    for g in GRAHAS:
        p = moving[g]
        row = {"id": GRAHA_ID[g], **point(p), "speed": round(p.speed, 6), "retro": p.retrograde}
        row["houseFromLagna"] = (p.sign - natal.asc.sign) % 12 + 1 if known_time else None
        row["houseFromMoon"] = (p.sign - natal.grahas["Moon"].sign) % 12 + 1 if natal else None
        row["gochara"], row["vedhaBy"] = gochara.get(g, (None, None))
        row["sav"] = sav[p.sign] if sav else None
        row["kakshya"] = _kakshya(natal, moving, g, bav) if bav and g in SEVEN else None
        row["motion"] = _motion(g, when, p.retrograde, ay, zone)
        rows.append(row)

    return {
        "at": iso(when, zone),
        "grahas": rows,
        "sadeSati": _sade_sati(natal.grahas["Moon"].sign, when, ay, zone) if natal else None,
        "upcoming": _upcoming(when, req.days, ay, node, zone),
        "engine": provenance(ay, node),
    }
