"""Varshaphala: the Tajika annual chart.

Previously this package had muntha and nothing else.  This is the system:
the varsha pravesha moment, muntha, panchavargiya bala, the five candidates
for year lord, the Tajika aspects (ithasala and its relatives), the sahams,
and mudda and patyayini dashas.

Tajika came into Jyotisha from Perso-Arabic astrology, which is why the
machinery -- terms, applying and separating aspects, translation and
collection of light, lots -- looks Hellenistic rather than Parashari.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chart import SIGN_LORDS, Chart
from .ephemeris import (
    GRAHAS,
    SEVEN,
    SIGNS,
    Position,
    fmt,
    solar_return,
)
from .vargas import varga

# Deeptamsha: the orb of influence each graha carries, in degrees.
DEEPTAMSHA = {
    "Sun": 15.0,
    "Moon": 12.0,
    "Mars": 8.0,
    "Mercury": 7.0,
    "Jupiter": 9.0,
    "Venus": 7.0,
    "Saturn": 9.0,
}

# Egyptian terms (hadda), as used in Tajika: (upper bound, lord) per sign.
HADDA = {
    0: [(6, "Jupiter"), (12, "Venus"), (20, "Mercury"), (25, "Mars"), (30, "Saturn")],
    1: [(8, "Venus"), (14, "Mercury"), (22, "Jupiter"), (27, "Saturn"), (30, "Mars")],
    2: [(6, "Mercury"), (12, "Jupiter"), (17, "Venus"), (24, "Mars"), (30, "Saturn")],
    3: [(7, "Mars"), (13, "Venus"), (19, "Mercury"), (26, "Jupiter"), (30, "Saturn")],
    4: [(6, "Jupiter"), (11, "Venus"), (18, "Saturn"), (24, "Mercury"), (30, "Mars")],
    5: [(7, "Mercury"), (17, "Venus"), (21, "Jupiter"), (28, "Mars"), (30, "Saturn")],
    6: [(6, "Saturn"), (14, "Mercury"), (21, "Jupiter"), (28, "Venus"), (30, "Mars")],
    7: [(7, "Mars"), (11, "Venus"), (19, "Mercury"), (24, "Jupiter"), (30, "Saturn")],
    8: [(12, "Jupiter"), (17, "Venus"), (21, "Mercury"), (26, "Saturn"), (30, "Mars")],
    9: [(7, "Mercury"), (14, "Jupiter"), (22, "Venus"), (26, "Saturn"), (30, "Mars")],
    10: [(7, "Mercury"), (13, "Venus"), (20, "Jupiter"), (25, "Mars"), (30, "Saturn")],
    11: [(12, "Venus"), (16, "Jupiter"), (19, "Mercury"), (28, "Mars"), (30, "Saturn")],
}


@dataclass
class Varsha:
    year: int
    jd: float
    chart: Chart
    muntha_sign: int
    muntha_house: int
    varshesha: str
    candidates: dict


def hadda_lord(longitude: float) -> str:
    sign, deg = int(longitude // 30), longitude % 30
    for bound, lord in HADDA[sign]:
        if deg < bound:
            return lord
    return HADDA[sign][-1][1]


def panchavargiya(chart: Chart, g: str) -> dict:
    """The Tajika five-fold strength, in vishwa units (20 maximum)."""
    lon = chart.grahas[g].longitude
    sign = chart.grahas[g].sign

    # Grahottama: full marks when the graha holds the same sign in D1 and D9.
    same_nav = int(varga(lon, 9) // 30) == sign
    grahottama = 20.0 if same_nav else 5.0

    hadda = (
        15.0 if hadda_lord(lon) == g else (7.5 if hadda_lord(lon) in ("Jupiter", "Venus") else 3.75)
    )

    drek_lord = SIGN_LORDS[int(varga(lon, 3) // 30)]
    drekkana = (
        10.0
        if drek_lord == g
        else (5.0 if chart.natural_relation(g, drek_lord) == "friend" else 2.5)
    )

    nav_lord = SIGN_LORDS[int(varga(lon, 9) // 30)]
    navamsa = (
        15.0
        if nav_lord == g
        else (7.5 if chart.natural_relation(g, nav_lord) == "friend" else 3.75)
    )

    h = chart.house(g)
    kendradi = 60.0 if h in (1, 4, 7, 10) else (30.0 if h in (2, 5, 8, 11) else 15.0)

    # scaled so the five parts sum to at most 20 vishwas
    total = (
        grahottama / 20 * 3.5
        + hadda / 15 * 3.0
        + drekkana / 10 * 3.5
        + navamsa / 15 * 4.0
        + kendradi / 60 * 6.0
    )
    return {
        "grahottama": grahottama,
        "hadda": hadda,
        "drekkana": drekkana,
        "navamsa": navamsa,
        "kendradi": kendradi,
        "vishwa": total,
    }


def varsha_chart(
    natal: Chart,
    year_index: int,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
    observer_timezone=None,
) -> Varsha:
    """Annual return calculated for the observer's location that year."""
    jd = solar_return(natal.jd, natal.grahas["Sun"].longitude, year_index, natal.ayanamsa)
    lat = natal.lat if observer_lat is None else observer_lat
    lon = natal.lon if observer_lon is None else observer_lon
    timezone = natal.tz if observer_timezone is None else observer_timezone
    ann = Chart(
        jd=jd,
        lat=lat,
        lon=lon,
        tz=timezone,
        ayanamsa=natal.ayanamsa,
        node=natal.node,
        label=f"varsha {year_index}",
    )
    muntha = (natal.asc.sign + year_index) % 12
    muntha_house = (muntha - ann.asc.sign) % 12 + 1

    # The five offices from which the year lord is chosen.
    trirashi = SIGN_LORDS[ann.asc.sign]  # simplified triplicity lord
    from . import panchanga as P

    pc = P.compute(jd, lat, lon, natal.ayanamsa)
    candidates = {
        "janma lagnesha": SIGN_LORDS[natal.asc.sign],
        "varsha lagnesha": SIGN_LORDS[ann.asc.sign],
        "muntha pati": SIGN_LORDS[muntha],
        "trirashi pati": trirashi,
        "dina-ratri pati": "Sun" if pc.is_day_birth else "Moon",
    }
    scored = {
        role: (g, panchavargiya(ann, g)["vishwa"]) for role, g in candidates.items() if g in SEVEN
    }
    varshesha = max(scored.values(), key=lambda t: t[1])[0] if scored else "Sun"
    return Varsha(year_index, jd, ann, muntha, muntha_house, varshesha, scored)


# --- Tajika aspects ---------------------------------------------------------

TAJIKA_ANGLES = {0: "conjunction", 60: "sextile", 90: "square", 120: "trine", 180: "opposition"}
FRIENDLY = {60, 120, 0}


def tajika_aspects(chart: Chart) -> list[dict]:
    """Ithasala, Ishrafa and their relatives.

    The distinguishing idea is applying versus separating: the faster graha
    approaching an exact angle with the slower is *ithasala* and the matter
    completes; past it, *ishrafa*, and it slips away.
    """
    out = []
    for i, a in enumerate(SEVEN):
        for b in SEVEN[i + 1 :]:
            la, lb = chart.grahas[a].longitude, chart.grahas[b].longitude
            sa, sb = chart.grahas[a].speed, chart.grahas[b].speed
            sep = abs((la - lb + 180) % 360 - 180)
            orb = (DEEPTAMSHA[a] + DEEPTAMSHA[b]) / 2.0
            for angle, name in TAJIKA_ANGLES.items():
                diff = abs(sep - angle)
                if diff > orb:
                    continue
                faster, slower = (a, b) if abs(sa) > abs(sb) else (b, a)
                # applying if the faster graha still has ground to cover
                deg_f = chart.grahas[faster].degree
                deg_s = chart.grahas[slower].degree
                applying = deg_f < deg_s
                kind = "Ithasala (applying)" if applying else "Ishrafa (separating)"
                if chart.grahas[faster].retrograde:
                    kind += " with retrograde motion"
                out.append(
                    {
                        "a": a,
                        "b": b,
                        "angle": angle,
                        "aspect": name,
                        "separation": sep,
                        "orb": orb,
                        "kind": kind,
                        "benefic": angle in FRIENDLY,
                        "faster": faster,
                        "slower": slower,
                    }
                )
    return out


def nakta_yamaya(chart: Chart) -> list[dict]:
    """Translation (nakta) and collection (yamaya) of light.

    Nakta: two grahas out of orb, a third faster one carries the light from
    one to the other.  Yamaya: both apply to a third, slower graha which
    gathers their light.
    """
    out = []
    for i, a in enumerate(SEVEN):
        for b in SEVEN[i + 1 :]:
            sep = abs((chart.grahas[a].longitude - chart.grahas[b].longitude + 180) % 360 - 180)
            orb = (DEEPTAMSHA[a] + DEEPTAMSHA[b]) / 2.0
            if sep <= orb:
                continue
            for c in SEVEN:
                if c in (a, b):
                    continue
                sa = abs((chart.grahas[c].longitude - chart.grahas[a].longitude + 180) % 360 - 180)
                sb = abs((chart.grahas[c].longitude - chart.grahas[b].longitude + 180) % 360 - 180)
                oa = (DEEPTAMSHA[a] + DEEPTAMSHA[c]) / 2.0
                ob = (DEEPTAMSHA[b] + DEEPTAMSHA[c]) / 2.0
                if sa <= oa and sb <= ob:
                    speeds = {x: abs(chart.grahas[x].speed) for x in (a, b, c)}
                    if speeds[c] > max(speeds[a], speeds[b]):
                        out.append(
                            {"kind": "Nakta (translation of light)", "between": (a, b), "via": c}
                        )
                    elif speeds[c] < min(speeds[a], speeds[b]):
                        out.append(
                            {"kind": "Yamaya (collection of light)", "between": (a, b), "via": c}
                        )
    return out


# --- sahams -----------------------------------------------------------------

# (name, positive term, negative term, third term, reverse_by_day)
SAHAM_RULES = [
    ("Punya (fortune)", "Moon", "Sun", "Lagna", True),
    ("Vidya (learning)", "Sun", "Moon", "Lagna", True),
    ("Yasas (fame)", "Jupiter", "Punya", "Lagna", True),
    ("Mitra (friends)", "Jupiter", "Punya", "Venus", True),
    ("Mahatmya (greatness)", "Punya", "Mars", "Lagna", True),
    ("Asha (hope)", "Saturn", "Mars", "Lagna", False),
    ("Samartha (capability)", "Mars", "Lagnesha", "Lagna", True),
    ("Bhratri (siblings)", "Jupiter", "Saturn", "Lagna", False),
    ("Gaurava (respect)", "Jupiter", "Sun", "Lagna", False),
    ("Pitri (father)", "Saturn", "Sun", "Lagna", True),
    ("Matri (mother)", "Moon", "Venus", "Lagna", True),
    ("Putra (children)", "Jupiter", "Moon", "Lagna", False),
    ("Jeeva (vitality)", "Saturn", "Jupiter", "Lagna", False),
    ("Karma (action)", "Mars", "Mercury", "Lagna", False),
    ("Roga (illness)", "Lagna", "Moon", "Saturn", False),
    ("Kali (strife)", "Jupiter", "Mars", "Lagna", False),
    ("Vivaha (marriage)", "Venus", "Saturn", "Lagna", False),
    ("Santapa (sorrow)", "Saturn", "Moon", "Lagna", False),
    ("Shraddha (faith)", "Venus", "Mars", "Lagna", False),
    ("Vanik (trade)", "Mercury", "Sun", "Lagna", False),
    ("Mrityu (death)", "Moon", "Saturn", "Lagna", False),
    ("Paradesha (foreign travel)", "Moon", "Saturn", "Lagna", False),
]


def sahams(chart: Chart, is_day: bool = True) -> dict[str, Position]:
    """Tajika lots.  Several reverse their terms for a night birth."""
    base = {g: chart.grahas[g].longitude for g in GRAHAS}
    base["Lagna"] = chart.asc.longitude
    base["Lagnesha"] = chart.grahas[SIGN_LORDS[chart.asc.sign]].longitude
    out: dict[str, Position] = {}
    for name, plus, minus, third, reverses in SAHAM_RULES:
        p = out[plus].longitude if plus in out else base.get(plus)
        m = out[minus].longitude if minus in out else base.get(minus)
        t = out[third].longitude if third in out else base.get(third)
        if None in (p, m, t):
            continue
        if reverses and not is_day:
            p, m = m, p
        value = (p - m + t) % 360
        # a saham must fall between its own first two terms; if not, add a sign
        out[name] = Position(name, value)
        out[name.split(" ")[0]] = out[name]
    return {k: v for k, v in out.items() if " " in k}


# --- annual dashas ----------------------------------------------------------

VIMSHOTTARI_SHARE = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}


def mudda_dasha(v: Varsha) -> list[dict]:
    """Vimshottari proportions compressed into the 365-day year, starting
    from the lord of the birth nakshatra of the annual Moon."""
    order = list(VIMSHOTTARI_SHARE)
    nak = v.chart.grahas["Moon"].nakshatra
    start = nak % 9
    seq = order[start:] + order[:start]
    out, cursor = [], v.jd
    for lord in seq:
        days = 365.25 * VIMSHOTTARI_SHARE[lord] / 120.0
        out.append({"lord": lord, "start": cursor, "end": cursor + days})
        cursor += days
    return out


def patyayini_dasha(v: Varsha) -> list[dict]:
    """Periods proportional to each graha's panchavargiya strength."""
    weights = {g: panchavargiya(v.chart, g)["vishwa"] for g in SEVEN}
    total = sum(weights.values()) or 1.0
    out, cursor = [], v.jd
    for g in sorted(SEVEN, key=lambda x: -weights[x]):
        days = 365.25 * weights[g] / total
        out.append({"lord": g, "start": cursor, "end": cursor + days, "vishwa": weights[g]})
        cursor += days
    return out


def report(
    natal: Chart,
    year_index: int,
    tz=0.0,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> str:
    v = varsha_chart(
        natal,
        year_index,
        observer_lat=observer_lat,
        observer_lon=observer_lon,
        observer_timezone=tz,
    )
    lines = [
        f"=== VARSHAPHALA year {year_index} (pravesha {fmt(v.jd, tz, True)}) ===",
        f"  varsha lagna   {v.chart.asc}",
        f"  muntha         {SIGNS[v.muntha_sign]} (house {v.muntha_house} of the annual chart)",
        f"  varshesha      {v.varshesha}",
        "",
    ]
    lines.append(f"{'office':18s}{'graha':10s}{'vishwa bala':>12s}")
    for role, (g, val) in v.candidates.items():
        mark = "  <-- year lord" if g == v.varshesha else ""
        lines.append(f"{role:18s}{g:10s}{val:12.2f}{mark}")

    lines.append("")
    lines.append("-- Tajika aspects")
    asp = tajika_aspects(v.chart)
    for a in asp[:12]:
        lines.append(
            f"   {a['a']:8s}{a['aspect']:13s}{a['b']:9s} "
            f"sep {a['separation']:6.2f} orb {a['orb']:5.2f}  "
            f"{a['kind']}"
        )
    if not asp:
        lines.append("   none within orb")
    for n in nakta_yamaya(v.chart)[:6]:
        lines.append(f"   {n['kind']}: {n['between'][0]}-{n['between'][1]} via {n['via']}")

    lines.append("")
    lines.append("-- sahams")
    sh = sahams(v.chart)
    for name, p in list(sh.items())[:14]:
        lines.append(f"   {name:28s}{str(p):14s} house {(p.sign - v.chart.asc.sign) % 12 + 1:2d}")

    lines.append("")
    lines.append("-- patyayini dasha (strength-proportional)")
    for d in patyayini_dasha(v):
        lines.append(
            f"   {d['lord']:9s}{fmt(d['start'], tz)} -> "
            f"{fmt(d['end'], tz)}  vishwa {d['vishwa']:.2f}"
        )
    return "\n".join(lines)
