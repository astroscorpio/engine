"""Dasha systems.

Nakshatra dashas (Vimshottari, Yogini, Ashtottari) share one engine: a lord
cycle, a total span, and a starting point set by the Moon.  Rashi dashas
(Chara) work on signs and need their own.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chart import EXALTATION, SIGN_LORDS, Chart
from .ephemeris import DASHA_YEAR, SIGNS

VIMSHOTTARI = [
    ("Ketu", 7),
    ("Venus", 20),
    ("Sun", 6),
    ("Moon", 10),
    ("Mars", 7),
    ("Rahu", 18),
    ("Jupiter", 16),
    ("Saturn", 19),
    ("Mercury", 17),
]

YOGINI = [
    ("Mangala", 1, "Moon"),
    ("Pingala", 2, "Sun"),
    ("Dhanya", 3, "Jupiter"),
    ("Bhramari", 4, "Mars"),
    ("Bhadrika", 5, "Mercury"),
    ("Ulka", 6, "Saturn"),
    ("Siddha", 7, "Venus"),
    ("Sankata", 8, "Rahu"),
]

ASHTOTTARI = [
    ("Sun", 6),
    ("Moon", 15),
    ("Mars", 8),
    ("Mercury", 17),
    ("Saturn", 10),
    ("Jupiter", 19),
    ("Rahu", 12),
    ("Venus", 21),
]
# Nakshatra counts per lord, starting at Ardra (index 5).
ASHTOTTARI_GROUPS = [3, 4, 3, 4, 3, 4, 3, 3]


@dataclass
class Period:
    lord: str
    start: float
    end: float
    level: int
    children: list[Period] | None = None

    @property
    def days(self) -> float:
        return self.end - self.start

    def at(self, jd: float) -> bool:
        return self.start <= jd < self.end


def _build(
    start_jd: float,
    cycle: list[tuple[str, float]],
    total: float,
    span_days: float,
    level: int,
    depth: int,
) -> list[Period]:
    out, cursor = [], start_jd
    for name, share in cycle:
        length = span_days * share / total
        node = Period(name, cursor, cursor + length, level)
        if level < depth:
            i = [c[0] for c in cycle].index(name)
            node.children = _build(cursor, cycle[i:] + cycle[:i], total, length, level + 1, depth)
        out.append(node)
        cursor = node.end
    return out


def vimshottari(chart: Chart, depth: int = 5) -> list[Period]:
    moon = chart.grahas["Moon"]
    span = 360 / 27
    lord_index = moon.nakshatra % 9
    consumed = (moon.longitude % span) / span
    cycle = VIMSHOTTARI[lord_index:] + VIMSHOTTARI[:lord_index]
    total = sum(y for _, y in VIMSHOTTARI)
    start = chart.jd - consumed * cycle[0][1] * DASHA_YEAR
    return _build(start, cycle, total, total * DASHA_YEAR, 1, depth)


def yogini(chart: Chart, depth: int = 3) -> list[Period]:
    moon = chart.grahas["Moon"]
    span = 360 / 27
    r = (moon.nakshatra + 1 + 3) % 8 or 8
    idx = r - 1
    cycle = [(f"{n} ({g})", y) for n, y, g in YOGINI]
    cycle = cycle[idx:] + cycle[:idx]
    total = sum(y for _, y in cycle)
    consumed = (moon.longitude % span) / span
    start = chart.jd - consumed * cycle[0][1] * DASHA_YEAR
    return _build(start, cycle, total, total * DASHA_YEAR, 1, depth)


def ashtottari(chart: Chart, depth: int = 3) -> list[Period]:
    """Applicable, by most authorities, only when Rahu sits in a kendra or
    trikona from the lagna lord -- ``applies`` says whether that holds."""
    moon = chart.grahas["Moon"]
    order, n = [], 5  # Ardra
    for (lord, _), count in zip(ASHTOTTARI, ASHTOTTARI_GROUPS, strict=True):
        for _ in range(count):
            order.append((n % 27, lord))
            n += 1
    lord_of = dict(order)
    lord = lord_of[moon.nakshatra]
    idx = [name for name, _ in ASHTOTTARI].index(lord)
    cycle = ASHTOTTARI[idx:] + ASHTOTTARI[:idx]
    total = sum(y for _, y in ASHTOTTARI)
    group = [k for k, v in order if v == lord]
    pos = group.index(moon.nakshatra)
    span = 360 / 27
    consumed = (pos + (moon.longitude % span) / span) / len(group)
    start = chart.jd - consumed * cycle[0][1] * DASHA_YEAR
    return _build(start, cycle, total, total * DASHA_YEAR, 1, depth)


def ashtottari_applies(chart: Chart) -> bool:
    lagna_lord = SIGN_LORDS[chart.asc.sign]
    d = (chart.grahas["Rahu"].sign - chart.grahas[lagna_lord].sign) % 12 + 1
    return d in (1, 4, 5, 7, 9, 10)


# --- Jaimini rashi dasha ----------------------------------------------------

# Vishama pada (odd-footed) rashis.  This, not odd/even signs, sets both the
# direction of the chara dasha and the direction of counting.
ODD_FOOTED = {0, 1, 2, 6, 7, 8}
DEBILITATION_SIGN = {n: (s + 6) % 12 for n, (s, _) in EXALTATION.items()}


def sign_lord(sign: int, chart: Chart) -> str:
    """Scorpio and Aquarius are co-lorded; an occupying node takes precedence."""
    if sign == 7 and chart.grahas["Ketu"].sign == 7:
        return "Ketu"
    if sign == 10 and chart.grahas["Rahu"].sign == 10:
        return "Rahu"
    return SIGN_LORDS[sign]


def chara_years(sign: int, chart: Chart) -> int:
    lord = sign_lord(sign, chart)
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
    if EXALTATION.get(lord, (None, 0))[0] == lord_sign:
        years += 1
    elif DEBILITATION_SIGN.get(lord) == lord_sign:
        years -= 1
    return max(years, 1)


def chara(chart: Chart, depth: int = 2, convention: str = "A") -> list[Period]:
    """Chara dasha from the lagna.

    ``convention`` picks how sub-periods are seeded: A starts them on the
    dasha rashi itself, B one sign further on.  Both are taught; the
    backtester exists to decide which one this chart actually obeys.
    """
    forward = chart.asc.sign in ODD_FOOTED
    step = 1 if forward else -1
    order = [(chart.asc.sign + step * i) % 12 for i in range(12)]

    out, cursor = [], chart.jd
    for sign in order:
        years = chara_years(sign, chart)
        node = Period(SIGNS[sign], cursor, cursor + years * DASHA_YEAR, 1)
        if depth > 1:
            seed = sign if convention == "A" else (sign + step) % 12
            span = node.days / 12
            node.children = []
            c2 = node.start
            for i in range(12):
                s2 = (seed + step * i) % 12
                node.children.append(Period(SIGNS[s2], c2, c2 + span, 2))
                c2 += span
        out.append(node)
        cursor = node.end
    return out


# --- queries ----------------------------------------------------------------


def active(tree: list[Period], jd: float) -> list[Period]:
    chain = []
    nodes = tree
    while nodes:
        found = next((n for n in nodes if n.at(jd)), None)
        if not found:
            break
        chain.append(found)
        nodes = found.children or []
    return chain


def chain_label(tree: list[Period], jd: float, sep: str = "-") -> str:
    return sep.join(p.lord for p in active(tree, jd))


def siblings(tree: list[Period], jd: float, level: int) -> list[Period]:
    """The full list of periods at ``level`` containing jd's ancestry."""
    chain = active(tree, jd)
    if level == 1:
        return tree
    if len(chain) < level - 1:
        return []
    return chain[level - 2].children or []
