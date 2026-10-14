"""The Jaimini layer.

Chara karakas, arudha padas, karakamsa, argala, and four rashi dashas
(Narayana, Chara, Drig, Shoola, Sthira).

Jaimini is the most school-divided part of the tradition.  Where a rule has
more than one live reading the alternatives are exposed as arguments rather
than settled silently -- the point of this package is that a convention can be
tested, not asserted.
"""

from __future__ import annotations

from .chart import EXALTATION, SIGN_LORDS, Chart
from .dashas import Period
from .ephemeris import DASHA_YEAR, GRAHAS, SIGNS
from .vargas import varga

# Vishama pada (odd-footed) rashis.  This, not the odd/even sign split, drives
# direction and counting throughout Jaimini.
ODD_FOOTED = {0, 1, 2, 6, 7, 8}
DEBILITATION_SIGN = {n: (s + 6) % 12 for n, (s, _) in EXALTATION.items()}

KARAKA_8 = ["AK", "AmK", "BK", "MK", "PiK", "PK", "GK", "DK"]
KARAKA_7 = ["AK", "AmK", "BK", "MK", "PK", "GK", "DK"]
KARAKA_FULL = {
    "AK": "Atmakaraka - the self",
    "AmK": "Amatyakaraka - career, counsel",
    "BK": "Bhratrikaraka - siblings, guru",
    "MK": "Matrikaraka - mother",
    "PiK": "Pitrikaraka - father",
    "PK": "Putrakaraka - children",
    "GK": "Gnatikaraka - rivals, obstacles",
    "DK": "Darakaraka - spouse",
}


# --- karakas ----------------------------------------------------------------


def chara_karakas(chart: Chart, scheme: int = 8) -> dict:
    """Ranked by degrees traversed in the sign; Rahu counts backwards."""
    names = GRAHAS[:7] + (["Rahu"] if scheme == 8 else [])
    entries = []
    for n in names:
        deg = chart.grahas[n].degree
        entries.append((n, 30.0 - deg if n == "Rahu" else deg))
    entries.sort(key=lambda e: -e[1])
    labels = KARAKA_8 if scheme == 8 else KARAKA_7
    return {label: entry for label, entry in zip(labels, entries, strict=True)}


# --- arudhas ----------------------------------------------------------------


def arudha(chart: Chart, house: int) -> int:
    """Arudha pada: count house to lord, project the same count from the lord.

    A pada landing in its own house or the 7th from it is unstable; the
    classical remedy is to take the 10th from that point.
    """
    house_sign = chart.house_sign(house)
    lord_sign = chart.grahas[SIGN_LORDS[house_sign]].sign
    count = (lord_sign - house_sign) % 12 + 1
    result = (lord_sign + count - 1) % 12
    offset = (result - house_sign) % 12 + 1
    if offset in (1, 7):
        result = (result + 9) % 12
    return result


def all_arudhas(chart: Chart) -> dict[str, int]:
    out = {f"A{h}": arudha(chart, h) for h in range(1, 13)}
    out["AL"] = out["A1"]
    out["UL"] = out["A12"]
    return out


def karakamsa(chart: Chart, scheme: int = 8) -> dict:
    """The Atmakaraka's navamsa sign, read in the rashi chart (karakamsa) and
    in the navamsa itself (swamsa)."""
    ak = chara_karakas(chart, scheme)["AK"][0]
    nav_sign = int(varga(chart.grahas[ak].longitude, 9) // 30)
    d9 = chart.d(9)
    return {
        "atmakaraka": ak,
        "karakamsa_sign": nav_sign,
        "karakamsa_house": chart.house_of_sign(nav_sign),
        "swamsa_house": d9.house_of_sign(nav_sign),
        "occupants": [g for g in GRAHAS if chart.grahas[g].sign == nav_sign],
    }


# --- argala -----------------------------------------------------------------

# Primary argala from the 2nd, 4th and 11th; secondary from the 5th and 8th.
# Each is obstructed (virodha) by its counterpart.
ARGALA_PAIRS = [(2, 12), (4, 10), (11, 3), (5, 9), (8, 6)]


def argala(chart: Chart, sign: int) -> list[dict]:
    """Intervention on a sign, net of its obstruction.

    A count of occupants decides: obstruction only holds when the obstructing
    house has at least as many grahas as the intervening one.
    """
    out = []
    for gain, block in ARGALA_PAIRS:
        g_sign = (sign + gain - 1) % 12
        b_sign = (sign + block - 1) % 12
        givers = [g for g in GRAHAS if chart.grahas[g].sign == g_sign]
        blockers = [g for g in GRAHAS if chart.grahas[g].sign == b_sign]
        if not givers:
            continue
        out.append(
            {
                "from_house": gain,
                "sign": SIGNS[g_sign],
                "grahas": givers,
                "obstruction_house": block,
                "obstructors": blockers,
                "obstructed": len(blockers) >= len(givers),
                "kind": "primary" if gain in (2, 4, 11) else "secondary",
            }
        )
    return out


# --- rashi dashas -----------------------------------------------------------


def sign_lord(chart: Chart, sign: int) -> str:
    """Scorpio and Aquarius are co-lorded; an occupying node takes over."""
    if sign == 7 and chart.grahas["Ketu"].sign == 7:
        return "Ketu"
    if sign == 10 and chart.grahas["Rahu"].sign == 10:
        return "Rahu"
    return SIGN_LORDS[sign]


def rashi_years(chart: Chart, sign: int) -> int:
    """Count from the sign to its lord, less one; adjusted for dignity."""
    lord = sign_lord(chart, sign)
    if lord in ("Rahu", "Ketu"):
        return 12
    lord_sign = chart.grahas[lord].sign
    if lord_sign == sign:
        return 12
    if sign in ODD_FOOTED:
        count = (lord_sign - sign) % 12 + 1
    else:
        count = (sign - lord_sign) % 12 + 1
    years = count - 1
    if EXALTATION.get(lord, (None,))[0] == lord_sign:
        years += 1
    elif DEBILITATION_SIGN.get(lord) == lord_sign:
        years -= 1
    return max(years, 1)


def _rashi_dasha(
    chart: Chart, order: list[int], years_fn, depth: int, antar_from_self: bool
) -> list[Period]:
    out, cursor = [], chart.jd
    for sign in order:
        yrs = years_fn(sign)
        node = Period(SIGNS[sign], cursor, cursor + yrs * DASHA_YEAR, 1)
        if depth > 1:
            # Narayana rule: the sub-period direction follows the *dasha
            # rashi's* own footedness, not the lagna's.  That is the main
            # thing separating it from chara dasha.
            step = 1 if sign in ODD_FOOTED else -1
            seed = sign if antar_from_self else (sign + step) % 12
            span = node.days / 12.0
            node.children, c2 = [], node.start
            for i in range(12):
                s2 = (seed + step * i) % 12
                node.children.append(Period(SIGNS[s2], c2, c2 + span, 2))
                c2 += span
        out.append(node)
        cursor = node.end
    return out


def narayana_dasha(chart: Chart, depth: int = 2, from_house: int = 1) -> list[Period]:
    """Narayana dasha: sequence from a bhava, direction by its footedness."""
    start = chart.house_sign(from_house)
    step = 1 if start in ODD_FOOTED else -1
    order = [(start + step * i) % 12 for i in range(12)]
    return _rashi_dasha(chart, order, lambda s: rashi_years(chart, s), depth, antar_from_self=True)


def chara_dasha(chart: Chart, depth: int = 2, convention: str = "A") -> list[Period]:
    """Chara dasha (K.N. Rao school): sequence and sub-period direction both
    set by the lagna."""
    start = chart.asc.sign
    step = 1 if start in ODD_FOOTED else -1
    order = [(start + step * i) % 12 for i in range(12)]
    out, cursor = [], chart.jd
    for sign in order:
        yrs = rashi_years(chart, sign)
        node = Period(SIGNS[sign], cursor, cursor + yrs * DASHA_YEAR, 1)
        if depth > 1:
            seed = sign if convention == "A" else (sign + step) % 12
            span = node.days / 12.0
            node.children, c2 = [], node.start
            for i in range(12):
                s2 = (seed + step * i) % 12
                node.children.append(Period(SIGNS[s2], c2, c2 + span, 2))
                c2 += span
        out.append(node)
        cursor = node.end
    return out


def drig_dasha(chart: Chart, depth: int = 2) -> list[Period]:
    """Drig dasha: for dharma and spiritual life.  Runs from the 9th house,
    ordering the signs by rashi drishti rather than by simple succession."""
    start = chart.house_sign(9)
    step = 1 if start in ODD_FOOTED else -1
    seen, order = set(), []
    cursor = start
    for _ in range(12):
        if cursor not in seen:
            seen.add(cursor)
            order.append(cursor)
        for s in chart.rashi_drishti(cursor):
            if s not in seen:
                seen.add(s)
                order.append(s)
        cursor = (cursor + step) % 12
    order = order[:12]
    for s in range(12):
        if s not in order:
            order.append(s)
    return _rashi_dasha(
        chart, order[:12], lambda s: rashi_years(chart, s), depth, antar_from_self=True
    )


def shoola_dasha(chart: Chart, depth: int = 2) -> list[Period]:
    """Shoola dasha: longevity and maraka work.  Nine years to every sign,
    counted zodiacally from the lagna."""
    start = chart.asc.sign
    order = [(start + i) % 12 for i in range(12)]
    return _rashi_dasha(chart, order, lambda s: 9, depth, antar_from_self=True)


def sthira_dasha(chart: Chart, depth: int = 2) -> list[Period]:
    """Sthira (fixed) dasha: movable signs 7 years, fixed 8, dual 9."""
    start = chart.asc.sign
    order = [(start + i) % 12 for i in range(12)]
    fixed = {0: 7, 1: 8, 2: 9}
    return _rashi_dasha(chart, order, lambda s: fixed[s % 3], depth, antar_from_self=True)


def report(chart: Chart) -> str:
    lines = ["=== CHARA KARAKAS (8-karaka scheme, Rahu reversed) ==="]
    k8 = chara_karakas(chart, 8)
    for lab, (name, deg) in k8.items():
        lines.append(
            f"  {lab:4s} {name:8s} {deg:6.2f}deg  "
            f"{SIGNS[chart.grahas[name].sign]:12s}"
            f"house {chart.house(name):2d}   {KARAKA_FULL[lab]}"
        )
    k7 = chara_karakas(chart, 7)
    diff = [
        f"{label}={k7[label][0]}" for label in KARAKA_7 if k7[label][0] != k8.get(label, ("",))[0]
    ]
    lines.append(f"  7-karaka scheme differs at: {', '.join(diff) or 'nothing'}")

    lines.append("")
    lines.append("=== ARUDHA PADAS ===")
    ar = all_arudhas(chart)
    for h in range(1, 13):
        s = ar[f"A{h}"]
        tag = "  <- Arudha Lagna" if h == 1 else ("  <- Upapada" if h == 12 else "")
        lines.append(f"  A{h:<2d} {SIGNS[s]:12s} house {chart.house_of_sign(s):2d}{tag}")

    km = karakamsa(chart)
    lines.append("")
    lines.append("=== KARAKAMSA ===")
    lines.append(f"  Atmakaraka {km['atmakaraka']}, navamsa {SIGNS[km['karakamsa_sign']]}")
    lines.append(
        f"  karakamsa in house {km['karakamsa_house']} of the rashi, "
        f"swamsa in house {km['swamsa_house']} of the navamsa"
    )
    lines.append(f"  grahas in that rashi: {', '.join(km['occupants']) or 'none'}")

    lines.append("")
    lines.append("=== ARGALA on the lagna ===")
    for a in argala(chart, chart.asc.sign):
        state = "obstructed" if a["obstructed"] else "operative"
        lines.append(
            f"  {a['kind']:9s} from the {a['from_house']:2d}th "
            f"({a['sign']:11s} {'+'.join(a['grahas']):22s}) "
            f"-> {state}"
        )

    lines.append("")
    lines.append("=== RASHI DASHAS at birth+23y ===")
    from .dashas import active

    probe = chart.jd + 23 * DASHA_YEAR
    for name, tree in (
        ("Narayana", narayana_dasha(chart)),
        ("Chara (A)", chara_dasha(chart, convention="A")),
        ("Drig", drig_dasha(chart)),
        ("Shoola", shoola_dasha(chart)),
        ("Sthira", sthira_dasha(chart)),
    ):
        chain = active(tree, probe)
        label = "-".join(p.lord for p in chain) or "-"
        lines.append(f"  {name:11s} {label}")
    return "\n".join(lines)
