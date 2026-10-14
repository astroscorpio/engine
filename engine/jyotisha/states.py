"""Avasthas and the special conditions: vargottama, pushkara, mrityu bhaga,
marana karaka sthana, badhaka.

These are the qualifiers that decide whether a well-placed graha actually
delivers.  A graha can be exalted and still be in mrityu bhaga or sitting in
its marana karaka sthana, which the classics treat as decisive.
"""

from __future__ import annotations

from .chart import SIGN_LORDS, Chart
from .ephemeris import GRAHAS, SEVEN
from .vargas import varga

BALADI = ["Bala", "Kumara", "Yuva", "Vriddha", "Mrita"]
BALADI_EFFECT = {"Bala": 0.25, "Kumara": 0.5, "Yuva": 1.0, "Vriddha": 0.25, "Mrita": 0.0}
JAGRADADI = ["Jagrat", "Swapna", "Sushupti"]

# The house from the lagna in which each graha is said to lose its karakatva.
MARANA_KARAKA = {
    "Sun": 12,
    "Moon": 8,
    "Mars": 7,
    "Mercury": 7,
    "Jupiter": 3,
    "Venus": 6,
    "Saturn": 1,
    "Rahu": 9,
    "Ketu": 3,
}

# Mrityu bhaga: the fatal degree of each graha in each sign (BPHS).
MRITYU_BHAGA = {
    "Sun": [20, 9, 12, 6, 8, 24, 16, 17, 22, 2, 3, 23],
    "Moon": [26, 12, 13, 25, 24, 11, 26, 14, 13, 25, 5, 12],
    "Mars": [19, 28, 25, 23, 29, 28, 14, 21, 2, 15, 11, 6],
    "Mercury": [15, 14, 13, 12, 8, 18, 20, 10, 21, 22, 7, 5],
    "Jupiter": [19, 29, 12, 27, 6, 4, 13, 10, 17, 11, 15, 28],
    "Venus": [28, 15, 11, 17, 10, 13, 4, 6, 27, 12, 29, 19],
    "Saturn": [10, 4, 7, 9, 12, 16, 3, 18, 28, 14, 13, 15],
    "Rahu": [14, 13, 12, 11, 24, 23, 22, 21, 10, 20, 18, 8],
    "Ketu": [8, 18, 20, 10, 21, 22, 7, 5, 15, 14, 13, 12],
    "Ascendant": [1, 9, 22, 22, 25, 2, 4, 23, 18, 20, 24, 10],
}

# Pushkara navamsas by sign (1-based navamsa index within the sign).
PUSHKARA_NAVAMSA = {
    0: [3, 5],
    1: [6, 8],
    2: [3, 5],
    3: [6, 8],
    4: [3, 5],
    5: [6, 8],
    6: [3, 5],
    7: [6, 8],
    8: [3, 5],
    9: [6, 8],
    10: [3, 5],
    11: [6, 8],
}
PUSHKARA_BHAGA = {0: 21, 1: 14, 2: 24, 3: 7, 4: 21, 5: 14, 6: 24, 7: 7, 8: 21, 9: 14, 10: 24, 11: 7}


def baladi(chart: Chart, g: str) -> str:
    """Infancy to death by position within the sign; reversed in even signs."""
    p = chart.grahas[g]
    deg = p.degree if p.sign % 2 == 0 else 30.0 - p.degree
    return BALADI[min(int(deg // 6), 4)]


def jagradadi(chart: Chart, g: str) -> str:
    d = chart.dignity(g)
    if d in ("exalted", "moolatrikona", "own"):
        return "Jagrat"
    if d in ("great friend", "friend", "neutral"):
        return "Swapna"
    return "Sushupti"


def deeptadi(chart: Chart, g: str) -> str:
    """The nine-fold state.  Order matters: war and combustion override
    dignity, which is the point of the scheme."""
    if g in SEVEN and chart.combust(g):
        return "Vikala (combust)"
    for other in SEVEN:
        if other in ("Sun", "Moon") or other == g or g in ("Sun", "Moon"):
            continue
        sep = abs((chart.grahas[g].longitude - chart.grahas[other].longitude + 180) % 360 - 180)
        if sep <= 1.0:
            return "Kopa (in planetary war)"
    d = chart.dignity(g)
    return {
        "exalted": "Deepta",
        "moolatrikona": "Deepta",
        "own": "Swastha",
        "great friend": "Pramudita",
        "friend": "Shanta",
        "neutral": "Deena",
        "enemy": "Dukhita",
        "great enemy": "Dukhita",
        "debilitated": "Khala",
    }.get(d, "Deena")


def lajjitadi(chart: Chart, g: str) -> list[str]:
    """The six-fold emotional states; a graha can hold several at once."""
    out = []
    house = chart.house(g)
    with_it = [x for x in chart.occupants(house) if x != g]
    dign = chart.dignity(g)
    if house == 5 and any(x in ("Rahu", "Ketu", "Sun", "Saturn", "Mars") for x in with_it):
        out.append("Lajjita (ashamed)")
    if dign in ("exalted", "moolatrikona"):
        out.append("Garvita (proud)")
    if dign in ("enemy", "great enemy"):
        out.append("Kshudita (hungry)")
    if chart.grahas[g].sign in (3, 7, 11) and any(
        not chart.is_benefic(x) for x in chart.aspecting(chart.grahas[g].sign)
    ):
        out.append("Trishita (thirsty)")
    if dign in ("friend", "great friend") or any(chart.is_benefic(x) for x in with_it):
        out.append("Mudita (delighted)")
    if g != "Sun" and "Sun" in with_it:
        out.append("Kshobhita (agitated)")
    return out or ["-"]


def vargottama(chart: Chart, g: str) -> bool:
    lon = chart.grahas[g].longitude
    return int(lon // 30) == int(varga(lon, 9) // 30)


def pushkara(chart: Chart, g: str) -> str:
    lon = chart.grahas[g].longitude
    sign, deg = int(lon // 30), lon % 30
    navamsa_index = int(deg / (30 / 9)) + 1
    marks = []
    if navamsa_index in PUSHKARA_NAVAMSA[sign]:
        marks.append("pushkara navamsa")
    if abs(deg - PUSHKARA_BHAGA[sign]) < 1.0:
        marks.append("pushkara bhaga")
    return ", ".join(marks) or "-"


def mrityu_bhaga(chart: Chart, g: str) -> bool:
    body = chart.asc if g == "Ascendant" else chart.grahas[g]
    table = MRITYU_BHAGA.get(g)
    if not table:
        return False
    return abs(body.degree - table[body.sign]) < 1.0


def marana_karaka(chart: Chart, g: str) -> bool:
    return chart.house(g) == MARANA_KARAKA.get(g)


def badhaka(chart: Chart) -> dict:
    """The obstructing house and its lord, by lagna modality."""
    mod = chart.asc.sign % 3
    house = {0: 11, 1: 9, 2: 7}[mod]
    sign = chart.house_sign(house)
    kind = {0: "movable", 1: "fixed", 2: "dual"}[mod]
    return {
        "lagna_type": kind,
        "badhaka_house": house,
        "badhaka_sign": sign,
        "badhakesha": SIGN_LORDS[sign],
    }


def report(chart: Chart) -> str:
    b = badhaka(chart)
    lines = [f"{'':10s}{'baladi':10s}{'jagradadi':11s}{'deeptadi':22s}{'flags':28s}lajjitadi"]
    for g in GRAHAS:
        flags = []
        if vargottama(chart, g):
            flags.append("vargottama")
        pk = pushkara(chart, g)
        if pk != "-":
            flags.append(pk)
        if mrityu_bhaga(chart, g):
            flags.append("MRITYU BHAGA")
        if marana_karaka(chart, g):
            flags.append("marana karaka sthana")
        lines.append(
            f"{g:10s}{baladi(chart, g):10s}{jagradadi(chart, g):11s}"
            f"{deeptadi(chart, g):22s}{', '.join(flags) or '-':28s}"
            f"{'; '.join(lajjitadi(chart, g))}"
        )
    lines.append("")
    lines.append(
        f"  badhaka: {b['lagna_type']} lagna -> {b['badhaka_house']}th "
        f"house, badhakesha {b['badhakesha']}"
    )
    return "\n".join(lines)
