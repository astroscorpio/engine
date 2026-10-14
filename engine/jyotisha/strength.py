"""Shadbala, bhava bala and the derived strength measures.

The single largest gap in this package until now, and the primary strength
apparatus of Parashara.  Everything is in **virupas**; 60 virupas = 1 rupa.

Where authorities disagree the choice is stated in a comment rather than
buried, because several of these formulae have two or three live readings and
a silent pick would make the numbers unfalsifiable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import panchanga as P
from .chart import EXALTATION, MOOLATRIKONA, OWN_SIGNS, SIGN_LORDS, Chart
from .ephemeris import SEVEN, equatorial, obliquity
from .vargas import varga

SAPTAVARGA = [1, 2, 3, 7, 9, 12, 30]

# Saptavargaja values, in virupas.
DIGNITY_VIRUPAS = {
    "moolatrikona": 45.0,
    "exalted": 45.0,
    "own": 30.0,
    "great friend": 22.5,
    "friend": 15.0,
    "neutral": 7.5,
    "enemy": 3.75,
    "great enemy": 1.875,
    "debilitated": 1.875,
}

NAISARGIKA = {
    "Sun": 60.0,
    "Moon": 51.43,
    "Venus": 42.86,
    "Jupiter": 34.29,
    "Mercury": 25.71,
    "Mars": 17.14,
    "Saturn": 8.57,
}

# Dig bala: the house whose cusp gives each graha full directional strength.
DIG_STRONG_HOUSE = {
    "Jupiter": 1,
    "Mercury": 1,
    "Sun": 10,
    "Mars": 10,
    "Saturn": 7,
    "Moon": 4,
    "Venus": 4,
}

# Nathonnatha: which half of the day-night cycle a graha draws power from.
NIGHT_STRONG = {"Moon", "Mars", "Saturn"}
DAY_STRONG = {"Sun", "Jupiter", "Venus"}

# Tribhaga: which third of day or night each graha rules.
TRIBHAGA_DAY = ["Mercury", "Sun", "Saturn"]
TRIBHAGA_NIGHT = ["Moon", "Venus", "Mars"]

# Drekkana bala: male grahas in the 1st, neuter in the 2nd, female in the 3rd.
DREKKANA_SEX = {"Sun": 0, "Mars": 0, "Jupiter": 0, "Mercury": 1, "Saturn": 1, "Moon": 2, "Venus": 2}

# Ayana bala: which declination sign strengthens each graha.
NORTH_STRONG = {"Sun", "Mars", "Jupiter", "Venus"}
SOUTH_STRONG = {"Saturn", "Moon"}

# Minimum shadbala required, in rupas (BPHS).
REQUIRED_RUPAS = {
    "Sun": 5.0,
    "Moon": 6.0,
    "Mars": 5.0,
    "Mercury": 7.0,
    "Jupiter": 6.5,
    "Venus": 5.5,
    "Saturn": 5.0,
}


@dataclass
class Shadbala:
    graha: str
    sthana: dict = field(default_factory=dict)
    dig: float = 0.0
    kala: dict = field(default_factory=dict)
    chesta: float = 0.0
    naisargika: float = 0.0
    drik: float = 0.0

    @property
    def sthana_total(self) -> float:
        return sum(self.sthana.values())

    @property
    def kala_total(self) -> float:
        return sum(self.kala.values())

    @property
    def total(self) -> float:
        return (
            self.sthana_total
            + self.dig
            + self.kala_total
            + self.chesta
            + self.naisargika
            + self.drik
        )

    @property
    def rupas(self) -> float:
        return self.total / 60.0

    @property
    def ratio(self) -> float:
        return self.rupas / REQUIRED_RUPAS[self.graha]


# --- sthana bala ------------------------------------------------------------


def uchcha_bala(chart: Chart, g: str) -> float:
    """Distance from the debilitation point, one virupa per 3 degrees."""
    ex_sign, ex_deg = EXALTATION[g]
    exalt = ex_sign * 30 + ex_deg
    debil = (exalt + 180) % 360
    d = abs((chart.grahas[g].longitude - debil + 180) % 360 - 180)
    return d / 3.0


def _dignity_in(sign: int, g: str, chart: Chart) -> str:
    mt = MOOLATRIKONA.get(g)
    if mt and sign == mt[0]:
        return "moolatrikona"
    if sign in OWN_SIGNS.get(g, []):
        return "own"
    if EXALTATION.get(g, (None,))[0] == sign:
        return "exalted"
    if EXALTATION.get(g, (None,))[0] is not None and sign == (EXALTATION[g][0] + 6) % 12:
        return "debilitated"
    return chart.relationship(g, SIGN_LORDS[sign])


def saptavargaja_bala(chart: Chart, g: str) -> float:
    """Dignity across the seven vargas D1, D2, D3, D7, D9, D12, D30."""
    lon = chart.grahas[g].longitude
    total = 0.0
    for d in SAPTAVARGA:
        sign = int(varga(lon, d) // 30)
        total += DIGNITY_VIRUPAS[_dignity_in(sign, g, chart)]
    return total


def ojhayugma_bala(chart: Chart, g: str) -> float:
    """Odd/even sign preference, counted in D1 and D9.  Moon and Venus want
    even rashis; the rest want odd."""
    total = 0.0
    for d in (1, 9):
        sign = int(varga(chart.grahas[g].longitude, d) // 30)
        odd = sign % 2 == 0  # 0-based: Aries is odd
        wants_even = g in ("Moon", "Venus")
        if odd != wants_even:
            total += 15.0
    return total


def kendradi_bala(chart: Chart, g: str) -> float:
    h = chart.house(g)
    if h in (1, 4, 7, 10):
        return 60.0
    return 30.0 if h in (2, 5, 8, 11) else 15.0


def drekkana_bala(chart: Chart, g: str) -> float:
    third = int((chart.grahas[g].degree) // 10)
    return 15.0 if third == DREKKANA_SEX[g] else 0.0


# --- dig bala ---------------------------------------------------------------


def dig_bala(chart: Chart, g: str) -> float:
    """Angular distance from the graha's powerless point, over three."""
    house = DIG_STRONG_HOUSE[g]
    # cusp longitudes: whole-sign charts still use the true angles here
    if chart.cusps and len(chart.cusps) >= 12:
        strong = chart.cusps[house - 1]
    else:
        strong = (chart.asc.longitude + (house - 1) * 30) % 360
    weak = (strong + 180) % 360
    d = abs((chart.grahas[g].longitude - weak + 180) % 360 - 180)
    return d / 3.0


# --- kala bala --------------------------------------------------------------


def nathonnatha_bala(g: str, pc: P.Panchanga, jd: float) -> float:
    """Diurnal or nocturnal strength.  Mercury is strong at all hours."""
    if g == "Mercury":
        return 60.0
    noon = (pc.sunrise + pc.sunset) / 2.0
    midnight = (pc.sunset + pc.next_sunrise) / 2.0
    if pc.is_day_birth:
        half = (pc.sunset - pc.sunrise) / 2.0
        from_noon = min(1.0, abs(jd - noon) / half) * 0.5
    else:
        half = (pc.next_sunrise - pc.sunset) / 2.0
        ref = midnight if jd >= pc.sunset else midnight - 1.0
        from_noon = 1.0 - min(1.0, abs(jd - ref) / half) * 0.5
    if g in DAY_STRONG:
        return 60.0 * (1.0 - from_noon)
    return 60.0 * from_noon


def paksha_bala(chart: Chart, g: str, moon_literal: bool = True) -> float:
    """Benefics draw on the bright half, malefics on the dark half.

    A live disagreement sits on the Moon.  Read literally, BPHS makes a dark
    Moon a malefic, which then draws the *krishna* value -- so a new-moon birth
    gives the Moon near-maximum paksha bala, doubled.  Several modern
    implementations instead give the Moon its own illuminated fraction, so a
    new Moon is weak.  ``moon_literal`` selects between them; the default
    follows the text.
    """
    elong = (chart.grahas["Moon"].longitude - chart.grahas["Sun"].longitude) % 360
    if elong > 180:
        elong = 360 - elong
    bright = elong / 3.0  # 0..60 as the Moon waxes
    if g == "Moon" and not moon_literal:
        return bright * 2.0
    value = bright if chart.is_benefic(g) else 60.0 - bright
    return value * 2.0 if g == "Moon" else value


def tribhaga_bala(g: str, pc: P.Panchanga, jd: float) -> float:
    """One third of the day or night belongs to a graha; Jupiter always
    receives it."""
    if g == "Jupiter":
        return 60.0
    if pc.is_day_birth:
        part = int((jd - pc.sunrise) / ((pc.sunset - pc.sunrise) / 3.0))
        ruler = TRIBHAGA_DAY[min(part, 2)]
    else:
        start = pc.sunset if jd >= pc.sunset else pc.sunset - 1.0
        part = int((jd - start) / ((pc.next_sunrise - pc.sunset) / 3.0))
        ruler = TRIBHAGA_NIGHT[min(max(part, 0), 2)]
    return 60.0 if ruler == g else 0.0


def varsha_masa_dina_hora(g: str, pc: P.Panchanga, jd: float) -> float:
    """Year 15, month 30, weekday 45, hora 60 to the ruling graha.

    The year and month lords are derived by the classical count of whole days
    since a reference sunrise -- 360-day civil years and 30-day months, which
    is the convention BPHS uses for this bala specifically.
    """
    total = 0.0
    day_index = math.floor(pc.sunrise + 0.5)
    abda_lord = P.VARA_LORDS[int(day_index / 360) % 7]
    masa_lord = P.VARA_LORDS[int(day_index / 30) % 7]
    if g == abda_lord:
        total += 15.0
    if g == masa_lord:
        total += 30.0
    if g == pc.vara:
        total += 45.0
    if g == pc.hora_lord:
        total += 60.0
    return total


def ayana_bala(chart: Chart, g: str) -> float:
    """From declination.  The Sun's value is doubled."""
    eq = equatorial(chart.jd)
    decl = eq[g][1]
    eps = obliquity(chart.jd)
    if g == "Mercury":
        value = (eps + abs(decl)) * 60.0 / (2 * eps)
    elif g in NORTH_STRONG:
        value = (eps + decl) * 60.0 / (2 * eps)
    else:
        value = (eps - decl) * 60.0 / (2 * eps)
    value = max(0.0, min(60.0, value))
    return value * 2.0 if g == "Sun" else value


def yuddha_bala(chart: Chart, g: str, others: dict) -> float:
    """Planetary war: two non-luminaries within one degree.  The northern one
    wins; the loser is docked the difference."""
    if g in ("Sun", "Moon"):
        return 0.0
    eq = equatorial(chart.jd)
    adj = 0.0
    for other in SEVEN:
        if other in ("Sun", "Moon") or other == g:
            continue
        sep = abs((chart.grahas[g].longitude - chart.grahas[other].longitude + 180) % 360 - 180)
        if sep > 1.0:
            continue
        diff = abs(others.get(g, 0.0) - others.get(other, 0.0)) / max(sep, 1e-6)
        adj += diff if eq[g][1] > eq[other][1] else -diff
    return max(-60.0, min(60.0, adj))


# --- chesta bala ------------------------------------------------------------


def chesta_bala(chart: Chart, g: str, ayana: float, paksha: float) -> float:
    """Motional strength.

    The Sun's is taken as its ayana bala and the Moon's as its paksha bala,
    per BPHS.  For the rest this uses the eight-fold motion states, which is
    the reading that keeps retrogression the dominant term -- the alternative
    'chesta kendra' arc formula is noted where the two diverge.
    """
    if g == "Sun":
        return ayana
    if g == "Moon":
        return paksha
    speed = chart.grahas[g].speed
    mean = {"Mars": 0.524, "Mercury": 1.383, "Jupiter": 0.083, "Venus": 1.602, "Saturn": 0.033}[g]
    if speed < 0:
        return 60.0  # vakra
    if abs(speed) < 0.02 * mean:
        return 15.0  # vikala, stationary
    r = speed / mean
    if r < 0.5:
        return 15.0  # mandatara
    if r < 0.9:
        return 30.0  # manda
    if r <= 1.1:
        return 7.5  # sama
    if r <= 1.5:
        return 30.0  # chara
    return 45.0  # atichara


# --- drik bala --------------------------------------------------------------


def sputa_drishti(distance: float) -> float:
    """Graded aspect strength in virupas, by angular distance.

    BPHS gives this as a piecewise table and translators render it slightly
    differently; this is the common reading, rising to a full 60 at the
    opposition.
    """
    d = distance % 360
    if d > 180:
        d = 360 - d
    if d < 30:
        return 0.0
    if d < 60:
        return (d - 30) / 2.0
    if d < 90:
        return (d - 60) + 15.0
    if d < 120:
        return (120 - d) / 2.0 + 30.0
    if d < 150:
        return (d - 120) / 2.0 + 30.0
    return (d - 150) + 45.0


def drik_bala(chart: Chart, g: str) -> float:
    """Benefic aspects add, malefic subtract, the sum divided by four."""
    target = chart.grahas[g].longitude
    total = 0.0
    for other in SEVEN:
        if other == g:
            continue
        source = chart.grahas[other].longitude
        v = sputa_drishti((target - source) % 360)
        # special aspects get their full value regardless of the arc
        offset = (chart.grahas[g].sign - chart.grahas[other].sign) % 12 + 1
        if offset in chart.aspects_from(other) and offset != 7:
            v = max(v, 45.0)
        total += v if chart.is_benefic(other) else -v
    return total / 4.0


# --- assembly ---------------------------------------------------------------


def shadbala(chart: Chart) -> dict[str, Shadbala]:
    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    out: dict[str, Shadbala] = {}
    for g in SEVEN:
        s = Shadbala(g)
        s.sthana = {
            "uchcha": uchcha_bala(chart, g),
            "saptavargaja": saptavargaja_bala(chart, g),
            "ojhayugma": ojhayugma_bala(chart, g),
            "kendradi": kendradi_bala(chart, g),
            "drekkana": drekkana_bala(chart, g),
        }
        s.dig = dig_bala(chart, g)
        ayana = ayana_bala(chart, g)
        paksha = paksha_bala(chart, g)
        s.kala = {
            "nathonnatha": nathonnatha_bala(g, pc, chart.jd),
            "paksha": paksha,
            "tribhaga": tribhaga_bala(g, pc, chart.jd),
            "varsha_masa_dina_hora": varsha_masa_dina_hora(g, pc, chart.jd),
            "ayana": ayana,
        }
        s.chesta = chesta_bala(chart, g, ayana, paksha)
        s.naisargika = NAISARGIKA[g]
        s.drik = drik_bala(chart, g)
        out[g] = s
    # yuddha bala needs the provisional totals of everyone else
    totals = {g: out[g].total for g in SEVEN}
    for g in SEVEN:
        adj = yuddha_bala(chart, g, totals)
        if adj:
            out[g].kala["yuddha"] = adj
    return out


# --- bhava bala -------------------------------------------------------------

BHAVA_DIG = {
    # house -> the graha class that gains there (BPHS bhava digbala)
    1: 60.0,
    2: 60.0,
    3: 60.0,
    4: 60.0,
    5: 60.0,
    6: 60.0,
    7: 60.0,
    8: 60.0,
    9: 60.0,
    10: 60.0,
    11: 60.0,
    12: 60.0,
}
# Which grahas confer digbala on which houses.
BHAVA_DIG_LORDS = {
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12): None,
}


def bhava_bala(chart: Chart, balas: dict[str, Shadbala] | None = None) -> dict:
    """Strength of each house: its lord's shadbala, plus what occupies and
    aspects it, less what afflicts it."""
    balas = balas or shadbala(chart)
    out = {}
    for house in range(1, 13):
        sign = chart.house_sign(house)
        lord = SIGN_LORDS[sign]
        adhipati = balas[lord].total if lord in balas else 0.0

        drishti = 0.0
        for g in SEVEN:
            v = sputa_drishti((sign * 30 + 15 - chart.grahas[g].longitude) % 360)
            offset = (sign - chart.grahas[g].sign) % 12 + 1
            if offset in chart.aspects_from(g) and offset != 7:
                v = max(v, 45.0)
            drishti += v if chart.is_benefic(g) else -v

        occupants = 0.0
        for g in chart.occupants(house):
            occupants += 30.0 if chart.is_benefic(g) else -30.0

        # Digbala of a bhava: the natural karaka classes by house group.
        dig = {1: 60.0, 4: 60.0, 7: 60.0, 10: 60.0}.get(house, 30.0)

        out[house] = {
            "adhipati": adhipati,
            "drishti": drishti,
            "occupants": occupants,
            "dig": dig,
            "total": adhipati + drishti + occupants + dig,
        }
    return out


def ishta_kashta(chart: Chart, balas: dict[str, Shadbala] | None = None):
    """Benefic and malefic potential: the geometric mean of uchcha and chesta
    bala, and its complement."""
    balas = balas or shadbala(chart)
    out = {}
    for g in SEVEN:
        u = uchcha_bala(chart, g)
        c = balas[g].chesta
        ishta = math.sqrt(max(u, 0.0) * max(c, 0.0))
        kashta = math.sqrt(max(60.0 - u, 0.0) * max(60.0 - c, 0.0))
        out[g] = {"ishta": ishta, "kashta": kashta}
    return out


def vimshopaka(chart: Chart, scheme: str = "shodashavarga") -> dict[str, float]:
    """Weighted dignity across a varga group, scaled to 20."""
    from .vargas import VIMSHOPAKA

    weights = VIMSHOPAKA[scheme]
    out = {}
    for g in SEVEN:
        lon = chart.grahas[g].longitude
        total = 0.0
        for d, w in weights.items():
            dign = _dignity_in(int(varga(lon, d) // 30), g, chart)
            frac = DIGNITY_VIRUPAS[dign] / 45.0
            total += w * frac
        out[g] = total
    return out


def report(chart: Chart) -> str:
    balas = shadbala(chart)
    lines = [
        f"{'':9s}{'sthana':>8s}{'dig':>7s}{'kala':>8s}{'chesta':>8s}"
        f"{'naisar':>8s}{'drik':>8s}{'TOTAL':>9s}{'rupas':>7s}"
        f"{'req':>6s}{'ratio':>7s}"
    ]
    for g in SEVEN:
        s = balas[g]
        lines.append(
            f"{g:9s}{s.sthana_total:8.1f}{s.dig:7.1f}{s.kala_total:8.1f}"
            f"{s.chesta:8.1f}{s.naisargika:8.1f}{s.drik:8.1f}"
            f"{s.total:9.1f}{s.rupas:7.2f}{REQUIRED_RUPAS[g]:6.1f}"
            f"{s.ratio:7.2f}"
        )
    ranked = sorted(SEVEN, key=lambda g: -balas[g].total)
    lines.append("")
    lines.append("  strongest to weakest: " + " > ".join(ranked))
    weak = [g for g in SEVEN if balas[g].ratio < 1.0]
    lines.append(f"  below the required minimum: {', '.join(weak) or 'none'}")
    ik = ishta_kashta(chart, balas)
    lines.append("")
    lines.append(f"{'':9s}{'ishta':>8s}{'kashta':>8s}{'vimshopaka':>12s}")
    vp = vimshopaka(chart)
    for g in SEVEN:
        lines.append(f"{g:9s}{ik[g]['ishta']:8.1f}{ik[g]['kashta']:8.1f}{vp[g]:12.2f}")
    return "\n".join(lines)
