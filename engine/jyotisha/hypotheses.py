"""Classical techniques written as falsifiable scorers.

Each one turns a rule from the texts into a number for a given day.  The
backtester then asks whether real events actually score high on it.  Several
of these will not survive, which is the point.

Two controls are included on purpose.  ``noise`` should always fail; if it
ever passes, the harness is broken, not the astrology.
"""

from __future__ import annotations

import math
from functools import lru_cache

from . import ashtakavarga as av
from . import dashas as D
from . import jaimini as JM
from . import panchanga as P
from . import sbc
from . import states as ST
from . import strength as STR
from . import tajika as TJ
from . import upagraha as UP
from .backtest import Hypothesis
from .chart import SIGN_LORDS, Chart
from .ephemeris import SEVEN, positions
from .ephemeris import SIGNS as _SIGNS
from .subjects import DOMAINS, Event

_SLOW = ["Saturn", "Jupiter", "Rahu", "Ketu"]


@lru_cache(maxsize=200_000)
def _pos(jd_key: int, ayanamsa: str, node: str):
    return positions(jd_key / 64.0, ayanamsa, node)


def transit(chart: Chart, jd: float):
    """Cached transit positions, quantised to ~22 minutes."""
    return _pos(int(round(jd * 64)), chart.ayanamsa, chart.node)


_CHARTS: dict[int, Chart] = {}


@lru_cache(maxsize=256)
def _dasha(chart_id: int, kind: str, convention: str):
    chart = _CHARTS[chart_id]
    if kind == "chara":
        return D.chara(chart, convention=convention)
    return {"vimshottari": D.vimshottari, "yogini": D.yogini, "ashtottari": D.ashtottari}[kind](
        chart
    )


def dasha_tree(chart: Chart, kind: str = "vimshottari", convention: str = "A"):
    """Dasha trees are expensive and depend only on the chart -- build once."""
    _CHARTS[id(chart)] = chart
    return _dasha(id(chart), kind, convention)


@lru_cache(maxsize=100_000)
def _active_periods(
    chart_id: int,
    kind: str,
    convention: str,
    jd: float,
) -> tuple[D.Period, ...]:
    chart = _CHARTS[chart_id]
    return tuple(D.active(dasha_tree(chart, kind, convention), jd))


def active_periods(
    chart: Chart,
    jd: float,
    kind: str = "vimshottari",
    convention: str = "A",
) -> tuple[D.Period, ...]:
    _CHARTS[id(chart)] = chart
    return _active_periods(id(chart), kind, convention, jd)


@lru_cache(maxsize=512)
def _varga(chart_id: int, division: int):
    return _CHARTS[chart_id].d(division)


def varga_chart(chart: Chart, division: int) -> Chart:
    _CHARTS[id(chart)] = chart
    return _varga(id(chart), division)


@lru_cache(maxsize=256)
def _bav(chart_id: int):
    chart = _CHARTS[chart_id]
    return av.bhinna(chart), av.sarva(av.bhinna(chart))


def bav_of(chart: Chart):
    _CHARTS[id(chart)] = chart
    return _bav(id(chart))


@lru_cache(maxsize=128)
def _houses_for_domains(domains: tuple[str, ...]) -> frozenset[int]:
    out: set[int] = set()
    for domain in domains:
        out |= set(DOMAINS.get(domain, ()))
    return frozenset(out or set(range(1, 13)))


def houses_for(event: Event) -> set[int]:
    return set(_houses_for_domains(event.domains))


def _signs_for(chart: Chart, houses: set[int]) -> set[int]:
    return {chart.house_sign(h) for h in houses}


# --- techniques -------------------------------------------------------------


def dasha_lord_rules_domain(chart: Chart, jd: float, event: Event) -> float:
    """The running dasha lords own or occupy the houses of the domain."""
    houses = houses_for(event)
    chain = active_periods(chart, jd)
    score = 0.0
    for level, period in enumerate(chain[:4], start=1):
        lord = period.lord
        if lord not in chart.grahas:
            continue
        weight = 1.0 / level
        if set(chart.houses_ruled(lord)) & houses:
            score += weight
        if chart.house(lord) in houses:
            score += weight
    return score


def transit_slow_on_domain(chart: Chart, jd: float, event: Event) -> float:
    """Saturn, Jupiter or the nodes occupying or aspecting a domain sign."""
    houses = houses_for(event)
    signs = _signs_for(chart, houses)
    moving = transit(chart, jd)
    score = 0.0
    for name in _SLOW:
        p = moving[name]
        if p.sign in signs:
            score += 1.0
        for offset in chart.aspects_from(name):
            if (p.sign + offset - 1) % 12 in signs:
                score += 0.5
    return score


def transit_over_natal_dasha_lord(chart: Chart, jd: float, event: Event) -> float:
    """A transiting graha crossing the natal degree of a running dasha lord.

    Scored by closeness, so a 1-degree hit beats a 9-degree one.
    """
    chain = active_periods(chart, jd)
    lords = [p.lord for p in chain[:3] if p.lord in chart.grahas]
    if not lords:
        return 0.0
    moving = transit(chart, jd)
    best = 0.0
    for lord in lords:
        target = chart.grahas[lord].longitude
        for name in SEVEN:
            sep = abs((moving[name].longitude - target + 180) % 360 - 180)
            if sep < 10:
                best = max(best, 1.0 - sep / 10.0)
    return best


def kakshya_vedha(chart: Chart, jd: float, event: Event) -> float:
    """Slow grahas sitting in a kakshya that gave them no bindu.

    The classical claim is that this, not the sign alone, marks the difficult
    stretches -- and it resolves to about three days.
    """
    moving = transit(chart, jd)
    score = 0.0
    for name in ("Saturn", "Jupiter"):
        k = av.kakshya_transit(chart, moving, name)
        if not k["active"]:
            score += 1.0
        if k["sign_bindus"] <= 3:
            score += 0.5
    return score


def low_sav_transit(chart: Chart, jd: float, event: Event) -> float:
    """Slow grahas crossing the chart's weakest signs."""
    sav = bav_of(chart)[1]
    moving = transit(chart, jd)
    return sum(max(0.0, 28 - sav[moving[n].sign]) / 10.0 for n in ("Saturn", "Jupiter"))


def sade_sati(chart: Chart, jd: float, event: Event) -> float:
    """Saturn in the 12th, 1st or 2nd from the natal Moon."""
    moon = chart.grahas["Moon"].sign
    s = transit(chart, jd)["Saturn"].sign
    d = (s - moon) % 12
    return {11: 0.6, 0: 1.0, 1: 0.6}.get(d, 0.0)


def moon_trigger(chart: Chart, jd: float, event: Event) -> float:
    """Fast trigger: the transit Moon in a domain sign, or on a dasha lord."""
    houses = houses_for(event)
    signs = _signs_for(chart, houses)
    moon = transit(chart, jd)["Moon"]
    score = 1.0 if moon.sign in signs else 0.0
    chain = active_periods(chart, jd)
    for period in chain[:3]:
        if period.lord in chart.grahas:
            sep = abs((moon.longitude - chart.grahas[period.lord].longitude + 180) % 360 - 180)
            if sep < 6:
                score += 1.0 - sep / 6.0
    return score


def malefic_on_lagna(chart: Chart, jd: float, event: Event) -> float:
    """Mars, Saturn or the nodes crossing the ascendant degree."""
    moving = transit(chart, jd)
    best = 0.0
    for name in ("Mars", "Saturn", "Rahu", "Ketu"):
        sep = abs((moving[name].longitude - chart.asc.longitude + 180) % 360 - 180)
        if sep < 8:
            best = max(best, 1.0 - sep / 8.0)
    return best


def domain_lord_afflicted(chart: Chart, jd: float, event: Event) -> float:
    """The natal lord of a domain house under transit from a malefic."""
    houses = houses_for(event)
    lords = {SIGN_LORDS[chart.house_sign(h)] for h in houses}
    moving = transit(chart, jd)
    score = 0.0
    for lord in lords:
        target = chart.grahas[lord].longitude
        for name in ("Mars", "Saturn", "Rahu", "Ketu"):
            sep = abs((moving[name].longitude - target + 180) % 360 - 180)
            if sep < 8:
                score += 1.0 - sep / 8.0
    return score


def station_proximity(chart: Chart, jd: float, event: Event) -> float:
    """Nearness to a station of Saturn, Jupiter, Mercury or Venus."""
    moving = transit(chart, jd)
    best = 0.0
    for name in ("Saturn", "Jupiter", "Mercury", "Venus", "Mars"):
        speed = abs(moving[name].speed)
        typical = {"Saturn": 0.11, "Jupiter": 0.23, "Mercury": 1.4, "Venus": 1.2, "Mars": 0.6}[name]
        best = max(best, max(0.0, 1.0 - speed / (typical * 0.25)))
    return best


# --- controls ---------------------------------------------------------------


def noise(chart: Chart, jd: float, event: Event) -> float:
    """Deterministic pseudo-random. Must fail. Validates the harness."""
    return math.sin(jd * 12.9898) * 43758.5453 % 1.0


def sun_longitude(chart: Chart, jd: float, event: Event) -> float:
    """Pure seasonality. Should fail unless the event set is season-biased."""
    return transit(chart, jd)["Sun"].longitude / 360.0


LIBRARY = [
    Hypothesis("dasha lord rules the domain house", dasha_lord_rules_domain),
    Hypothesis("slow transit on/aspecting domain", transit_slow_on_domain),
    Hypothesis("transit over natal dasha lord", transit_over_natal_dasha_lord),
    Hypothesis("kakshya vedha (Sat/Jup inert kakshya)", kakshya_vedha),
    Hypothesis("slow transit through low-SAV sign", low_sav_transit),
    Hypothesis("sade sati", sade_sati),
    Hypothesis("transit Moon trigger", moon_trigger),
    Hypothesis("malefic crossing the lagna", malefic_on_lagna),
    Hypothesis("domain lord under malefic transit", domain_lord_afflicted),
    Hypothesis("near a planetary station", station_proximity),
    Hypothesis("CONTROL: pseudo-random noise", noise),
    Hypothesis("CONTROL: solar longitude (seasonality)", sun_longitude),
]


# ============================================================================
# Second batch: the techniques the classics lean on hardest.
# ============================================================================

# Favourable transit houses counted from the natal Moon (gochara).
GOCHARA_GOOD = {
    "Sun": {3, 6, 10, 11},
    "Moon": {1, 3, 6, 7, 10, 11},
    "Mars": {3, 6, 11},
    "Mercury": {2, 4, 6, 8, 10, 11},
    "Jupiter": {2, 5, 7, 9, 11},
    "Venus": {1, 2, 3, 4, 5, 8, 9, 11, 12},
    "Saturn": {3, 6, 11},
}
# Vedha (obstruction): transit house -> the house whose occupancy blocks it.
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

TARA = ["Janma", "Sampat", "Vipat", "Kshema", "Pratyari", "Sadhaka", "Vadha", "Mitra", "Ati-mitra"]
TARA_GOOD = {1, 3, 5, 7, 8}  # 0-based indices of the benefic taras

# Which varga the classics say to read for each domain.
DOMAIN_VARGA = {
    "education": 24,
    "career": 10,
    "relationship": 9,
    "money": 2,
    "home": 4,
    "travel": 3,
    "health": 30,
    "recognition": 10,
    "conflict": 6,
    "loss": 30,
}
DOMAIN_KARAKA = {
    "education": "Jupiter",
    "career": "Saturn",
    "relationship": "Venus",
    "money": "Jupiter",
    "home": "Moon",
    "travel": "Rahu",
    "health": "Sun",
    "recognition": "Sun",
    "conflict": "Mars",
    "loss": "Saturn",
}


def _from_moon(chart: Chart, moving, name: str) -> int:
    return (moving[name].sign - chart.grahas["Moon"].sign) % 12 + 1


def gochara_plain(chart: Chart, jd: float, event: Event) -> float:
    """Transits in their favourable houses from the natal Moon."""
    moving = transit(chart, jd)
    return sum(1.0 for n in SEVEN if _from_moon(chart, moving, n) in GOCHARA_GOOD[n])


def gochara_vedha(chart: Chart, jd: float, event: Event) -> float:
    """The same, but only counting transits whose vedha point is empty.

    This is the refinement the texts insist on and almost no software applies.
    """
    moving = transit(chart, jd)
    houses = {n: _from_moon(chart, moving, n) for n in SEVEN}
    score = 0.0
    for name in SEVEN:
        h = houses[name]
        if h not in GOCHARA_GOOD[name]:
            continue
        blocker = VEDHA[name].get(h)
        if blocker is None:
            score += 1.0
            continue
        obstructed = any(
            other != name and houses[other] == blocker and {name, other} not in NO_VEDHA_BETWEEN
            for other in SEVEN
        )
        if not obstructed:
            score += 1.0
    return score


def kantaka_shani(chart: Chart, jd: float, event: Event) -> float:
    """Saturn in the 4th, 7th, 8th or 10th from the natal Moon."""
    d = (transit(chart, jd)["Saturn"].sign - chart.grahas["Moon"].sign) % 12 + 1
    return {4: 1.0, 7: 0.8, 8: 1.0, 10: 1.0}.get(d, 0.0)


def own_bav_transit(chart: Chart, jd: float, event: Event) -> float:
    """The classical rule: judge a transit by the bindus the *transiting*
    graha holds in its own ashtakavarga in that sign, not by the sign total."""
    bav = bav_of(chart)[0]
    moving = transit(chart, jd)
    return sum(bav[n][moving[n].sign] for n in ("Saturn", "Jupiter")) / 8.0


def dasha_lord_dignity(chart: Chart, jd: float, event: Event) -> float:
    """Strength of the running dasha lords by dignity and house class."""
    weights = {
        "exalted": 1.0,
        "moolatrikona": 0.9,
        "own": 0.8,
        "great friend": 0.6,
        "friend": 0.5,
        "neutral": 0.3,
        "enemy": 0.15,
        "great enemy": 0.05,
        "debilitated": 0.0,
    }
    chain = active_periods(chart, jd)
    score = 0.0
    for level, period in enumerate(chain[:3], start=1):
        if period.lord not in chart.grahas:
            continue
        score += weights.get(chart.dignity(period.lord), 0.3) / level
        if chart.house(period.lord) in (1, 4, 5, 7, 9, 10):
            score += 0.3 / level
    return score


def dasha_lord_in_domain_varga(chart: Chart, jd: float, event: Event) -> float:
    """The dasha lord placed in a domain house of the *relevant divisional*
    chart -- D24 for study, D10 for work, D9 for partnership."""
    houses = houses_for(event)
    divisions = {DOMAIN_VARGA.get(d) for d in event.domains} - {None}
    if not divisions:
        return 0.0
    chain = active_periods(chart, jd)
    score = 0.0
    for level, period in enumerate(chain[:3], start=1):
        if period.lord not in chart.grahas:
            continue
        for d in divisions:
            if varga_chart(chart, d).house(period.lord) in houses:
                score += 1.0 / level
    return score


def karaka_on_domain(chart: Chart, jd: float, event: Event) -> float:
    """The natural significator of the domain transiting its houses."""
    houses = houses_for(event)
    signs = _signs_for(chart, houses)
    moving = transit(chart, jd)
    score = 0.0
    for domain in event.domains:
        karaka = DOMAIN_KARAKA.get(domain)
        if not karaka:
            continue
        if moving[karaka].sign in signs:
            score += 1.0
        for offset in chart.aspects_from(karaka):
            if (moving[karaka].sign + offset - 1) % 12 in signs:
                score += 0.4
    return score


def sudarshana(chart: Chart, jd: float, event: Event) -> float:
    """Sudarshana chakra: a house counted from the lagna, the Moon and the
    Sun at once.  Activation in all three rings is the classical claim."""
    houses = houses_for(event)
    moving = transit(chart, jd)
    rings = (chart.asc.sign, chart.grahas["Moon"].sign, chart.grahas["Sun"].sign)
    score = 0.0
    for name in ("Jupiter", "Saturn", "Mars"):
        hit = sum(1 for base in rings if (moving[name].sign - base) % 12 + 1 in houses)
        if hit == 3:
            score += 1.0
        elif hit == 2:
            score += 0.3
    return score


def argala_on_domain(chart: Chart, jd: float, event: Event) -> float:
    """Jaimini argala: intervention from the 2nd, 4th and 11th, net of the
    obstruction (virodha argala) from the 12th, 10th and 3rd."""
    houses = houses_for(event)
    moving = transit(chart, jd)
    occupied = {moving[n].sign for n in SEVEN}
    score = 0.0
    for h in houses:
        base = chart.house_sign(h)
        for gain, block in ((2, 12), (4, 10), (11, 3)):
            has = (base + gain - 1) % 12 in occupied
            stopped = (base + block - 1) % 12 in occupied
            if has and not stopped:
                score += 1.0
    return score


def eclipse_on_natal(chart: Chart, jd: float, event: Event) -> float:
    """An eclipse within 15 days, weighted by contact with a natal point."""
    found = _eclipse_cache(int(jd // 200))
    best = 0.0
    for e in found:
        gap = abs(e["jd"] - jd)
        if gap > 15:
            continue
        near = min(abs((e["lon"] - g.longitude + 180) % 360 - 180) for g in chart.grahas.values())
        best = max(best, (1 - gap / 15) * (1.0 if near < 10 else 0.4))
    return best


@lru_cache(maxsize=256)
def _eclipse_cache(bucket: int):
    from .ephemeris import eclipses
    from .ephemeris import positions as _p

    lo = bucket * 200
    out = []
    for e in eclipses(lo - 30, lo + 230):
        e = dict(e)
        e["lon"] = _p(e["jd"])["Sun"].longitude
        out.append(e)
    return out


def yogini_domain(chart: Chart, jd: float, event: Event) -> float:
    """Yogini dasha lord ruling or occupying a domain house."""
    houses = houses_for(event)
    chain = active_periods(chart, jd, "yogini")
    score = 0.0
    for level, period in enumerate(chain[:2], start=1):
        lord = period.lord.split("(")[-1].rstrip(")")
        if lord not in chart.grahas:
            continue
        if set(chart.houses_ruled(lord)) & houses:
            score += 1.0 / level
        if chart.house(lord) in houses:
            score += 1.0 / level
    return score


def muntha_in_domain(chart: Chart, jd: float, event: Event) -> float:
    """Tajika: the muntha advances one sign per year of life."""
    years = int((jd - chart.jd) / 365.2563)
    muntha = (chart.asc.sign + years) % 12
    return 1.0 if chart.house_of_sign(muntha) in houses_for(event) else 0.0


def dasha_pair_harmony(chart: Chart, jd: float, event: Event) -> float:
    """Compound relationship between the maha and antar lords."""
    chain = active_periods(chart, jd)
    if len(chain) < 2:
        return 0.0
    a, b = chain[0].lord, chain[1].lord
    if a not in chart.grahas or b not in chart.grahas:
        return 0.0
    return {
        "great friend": 1.0,
        "friend": 0.75,
        "neutral": 0.5,
        "enemy": 0.25,
        "great enemy": 0.0,
    }.get(chart.relationship(a, b), 0.5)


def slow_transit_on_natal_lagna_lord(chart: Chart, jd: float, event: Event) -> float:
    """Saturn or Jupiter within orb of the natal lagna lord."""
    lord = SIGN_LORDS[chart.asc.sign]
    target = chart.grahas[lord].longitude
    moving = transit(chart, jd)
    best = 0.0
    for name in ("Saturn", "Jupiter"):
        sep = abs((moving[name].longitude - target + 180) % 360 - 180)
        if sep < 8:
            best = max(best, 1.0 - sep / 8.0)
    return best


LIBRARY += [
    Hypothesis("gochara (transits good from Moon)", gochara_plain),
    Hypothesis("gochara WITH vedha obstruction", gochara_vedha),
    Hypothesis("kantaka / ashtama Shani", kantaka_shani),
    Hypothesis("own-BAV bindus of transiting Sat/Jup", own_bav_transit),
    Hypothesis("dasha lord dignity + kendra/trikona", dasha_lord_dignity),
    Hypothesis("dasha lord in domain house of D24/D10/D9", dasha_lord_in_domain_varga),
    Hypothesis("domain karaka transiting domain houses", karaka_on_domain),
    Hypothesis("sudarshana chakra triple activation", sudarshana),
    Hypothesis("Jaimini argala on domain house", argala_on_domain),
    Hypothesis("eclipse within 15d touching a natal point", eclipse_on_natal),
    Hypothesis("yogini dasha lord rules domain", yogini_domain),
    Hypothesis("tajika muntha in domain house", muntha_in_domain),
    Hypothesis("maha/antar lord harmony", dasha_pair_harmony),
    Hypothesis("Sat/Jup on the natal lagna lord", slow_transit_on_natal_lagna_lord),
]


# ============================================================================
# Third batch: everything the coverage audit found missing.
#
# A hypothesis has to *vary over time* to be testable in the window framework,
# so static natal facts are encoded through the running dasha lord -- "the
# lord now ruling is vargottama" changes as the dasha changes, where "the
# chart contains a vargottama graha" never does.
# ============================================================================


@lru_cache(maxsize=64)
def _shadbala(chart_id: int):
    c = _CHARTS[chart_id]
    b = STR.shadbala(c)
    return b, STR.bhava_bala(c, b), STR.ishta_kashta(c, b), STR.vimshopaka(c)


def strength_of(chart: Chart):
    _CHARTS[id(chart)] = chart
    return _shadbala(id(chart))


@lru_cache(maxsize=64)
def _points(chart_id: int):
    c = _CHARTS[chart_id]
    return UP.all_points(c), JM.all_arudhas(c), JM.karakamsa(c)


def points_of(chart: Chart):
    _CHARTS[id(chart)] = chart
    return _points(id(chart))


@lru_cache(maxsize=64)
def _sahams(chart_id: int):
    return TJ.sahams(_CHARTS[chart_id])


@lru_cache(maxsize=768)
def _argala(chart_id: int, sign: int):
    return JM.argala(_CHARTS[chart_id], sign)


def _lords(chart: Chart, jd: float, levels: int = 3):
    return [
        (i + 1, p.lord)
        for i, p in enumerate(active_periods(chart, jd)[:levels])
        if p.lord in chart.grahas
    ]


def dasha_lord_shadbala(chart: Chart, jd: float, event: Event) -> float:
    """How strong, in rupas over requirement, is the graha now ruling."""
    balas, _, _, _ = strength_of(chart)
    score = 0.0
    for level, lord in _lords(chart, jd):
        if lord in balas:
            score += balas[lord].ratio / level
    return score


def domain_house_bhava_bala(chart: Chart, jd: float, event: Event) -> float:
    """Bhava bala of the domain houses, gated on the dasha lord touching
    one of them -- otherwise the value never changes."""
    _, bhava, _, _ = strength_of(chart)
    houses = houses_for(event)
    active_h = set()
    for _, lord in _lords(chart, jd):
        active_h |= set(chart.houses_ruled(lord)) | {chart.house(lord)}
    hit = houses & active_h
    if not hit:
        return 0.0
    return sum(bhava[h]["total"] for h in hit) / (600.0 * len(hit))


def dasha_lord_ishta(chart: Chart, jd: float, event: Event) -> float:
    _, _, ik, _ = strength_of(chart)
    return sum(ik[lord]["ishta"] / 60.0 / level for level, lord in _lords(chart, jd) if lord in ik)


def dasha_lord_kashta(chart: Chart, jd: float, event: Event) -> float:
    _, _, ik, _ = strength_of(chart)
    return sum(ik[lord]["kashta"] / 60.0 / level for level, lord in _lords(chart, jd) if lord in ik)


def dasha_lord_avastha(chart: Chart, jd: float, event: Event) -> float:
    """Baladi and deeptadi states of the running lords."""
    good_deepta = {"Deepta", "Swastha", "Pramudita", "Shanta"}
    score = 0.0
    for level, lord in _lords(chart, jd):
        score += ST.BALADI_EFFECT[ST.baladi(chart, lord)] / level
        if ST.deeptadi(chart, lord) in good_deepta:
            score += 0.5 / level
    return score


def dasha_lord_marana(chart: Chart, jd: float, event: Event) -> float:
    """A running lord sitting in its marana karaka sthana."""
    return sum(1.0 / level for level, lord in _lords(chart, jd) if ST.marana_karaka(chart, lord))


def badhakesha_active(chart: Chart, jd: float, event: Event) -> float:
    b = ST.badhaka(chart)
    hit = sum(1.0 / level for level, lord in _lords(chart, jd) if lord == b["badhakesha"])
    moving = transit(chart, jd)
    if moving["Saturn"].sign == b["badhaka_sign"]:
        hit += 0.5
    return hit


def transit_on_arudha(chart: Chart, jd: float, event: Event) -> float:
    """Slow transits over the arudha lagna and upapada."""
    _, arudhas, _ = points_of(chart)
    moving = transit(chart, jd)
    score = 0.0
    for key, weight in (("AL", 1.0), ("UL", 0.7)):
        sign = arudhas[key]
        for g in ("Saturn", "Jupiter", "Rahu", "Ketu"):
            if moving[g].sign == sign:
                score += weight
    return score


def transit_on_karakamsa(chart: Chart, jd: float, event: Event) -> float:
    _, _, km = points_of(chart)
    moving = transit(chart, jd)
    return sum(1.0 for g in ("Saturn", "Jupiter") if moving[g].sign == km["karakamsa_sign"])


def transit_on_gulika(chart: Chart, jd: float, event: Event) -> float:
    pts, _, _ = points_of(chart)
    if "Gulika" not in pts:
        return 0.0
    target = pts["Gulika"].longitude
    moving = transit(chart, jd)
    best = 0.0
    for g in ("Saturn", "Mars", "Rahu", "Ketu", "Sun"):
        sep = abs((moving[g].longitude - target + 180) % 360 - 180)
        if sep < 8:
            best = max(best, 1.0 - sep / 8.0)
    return best


def _rashi_dasha_domain(chart: Chart, jd: float, event: Event, which: str) -> float:
    houses = houses_for(event)
    tree = _rashi_tree(id(_register(chart)), which)
    score = 0.0
    for level, p in enumerate(D.active(tree, jd)[:2], start=1):
        sign = _SIGNS.index(p.lord)
        if chart.house_of_sign(sign) in houses:
            score += 1.0 / level
    return score


def narayana_dasha_domain(chart: Chart, jd: float, event: Event) -> float:
    return _rashi_dasha_domain(chart, jd, event, "narayana")


def drig_dasha_domain(chart: Chart, jd: float, event: Event) -> float:
    return _rashi_dasha_domain(chart, jd, event, "drig")


def shoola_dasha_domain(chart: Chart, jd: float, event: Event) -> float:
    return _rashi_dasha_domain(chart, jd, event, "shoola")


def _register(chart: Chart) -> Chart:
    _CHARTS[id(chart)] = chart
    return chart


@lru_cache(maxsize=256)
def _rashi_tree(chart_id: int, which: str):
    c = _CHARTS[chart_id]
    return {
        "narayana": JM.narayana_dasha,
        "drig": JM.drig_dasha,
        "shoola": JM.shoola_dasha,
        "sthira": JM.sthira_dasha,
    }[which](c)


def argala_on_domain_full(chart: Chart, jd: float, event: Event) -> float:
    """Proper argala: primary and secondary, net of virodha, gated on the
    dasha lord ruling one of the domain houses."""
    houses = houses_for(event)
    ruling = set()
    for _, lord in _lords(chart, jd):
        ruling |= set(chart.houses_ruled(lord))
    if not (houses & ruling):
        return 0.0
    score = 0.0
    for h in houses & ruling:
        for a in _argala(id(_register(chart)), chart.house_sign(h)):
            if not a["obstructed"]:
                score += 1.0 if a["kind"] == "primary" else 0.5
    return score


def muntha_lord_active(chart: Chart, jd: float, event: Event) -> float:
    """Is the muntha lord also a running dasha lord?"""
    years = int((jd - chart.jd) / 365.2563)
    muntha = (chart.asc.sign + years) % 12
    lord = SIGN_LORDS[muntha]
    return sum(1.0 / level for level, active_lord in _lords(chart, jd) if active_lord == lord)


def saham_activation(chart: Chart, jd: float, event: Event) -> float:
    """Slow transits over the domain-relevant Tajika saham."""
    which = {
        "career": "Karma",
        "education": "Vidya",
        "money": "Punya",
        "recognition": "Yasas",
        "relationship": "Vivaha",
        "conflict": "Kali",
        "health": "Roga",
        "travel": "Paradesha",
    }
    sh = _sahams(id(_register(chart)))
    moving = transit(chart, jd)
    score = 0.0
    for dom in event.domains:
        key = which.get(dom)
        if not key:
            continue
        match = next((v for k, v in sh.items() if k.startswith(key)), None)
        if match is None:
            continue
        for g in ("Saturn", "Jupiter"):
            sep = abs((moving[g].longitude - match.longitude + 180) % 360 - 180)
            if sep < 10:
                score += 1.0 - sep / 10.0
    return score


LIBRARY += [
    Hypothesis("dasha lord shadbala (rupas over requirement)", dasha_lord_shadbala),
    Hypothesis("bhava bala of the activated domain house", domain_house_bhava_bala),
    Hypothesis("dasha lord ishta phala", dasha_lord_ishta),
    Hypothesis("dasha lord kashta phala", dasha_lord_kashta),
    Hypothesis("dasha lord avastha (baladi + deeptadi)", dasha_lord_avastha),
    Hypothesis("dasha lord in marana karaka sthana", dasha_lord_marana),
    Hypothesis("badhakesha running or Saturn on badhaka sign", badhakesha_active),
    Hypothesis("slow transit on arudha lagna / upapada", transit_on_arudha),
    Hypothesis("Sat/Jup transit on karakamsa", transit_on_karakamsa),
    Hypothesis("malefic transit on Gulika", transit_on_gulika),
    Hypothesis("Narayana dasha rashi = domain", narayana_dasha_domain),
    Hypothesis("Drig dasha rashi = domain", drig_dasha_domain),
    Hypothesis("Shoola dasha rashi = domain", shoola_dasha_domain),
    Hypothesis("full argala on the activated domain house", argala_on_domain_full),
    Hypothesis("muntha lord is a running dasha lord", muntha_lord_active),
    Hypothesis("Sat/Jup transit on the domain saham", saham_activation),
]


# ============================================================================
# Fourth batch, added after a forecast review.
#
# A review of a missed forecast found one concrete defect and one omission,
# both fixed here.
#
# DEFECT: gochara was only ever computed from the natal Moon.  Reading the
# same transits from the lagna and from the Sun is equally classical, and the
# three wheels can disagree sharply: a slow graha can sit in an unfavourable
# house from the Moon and in a favourable one from the lagna, and only the
# first was ever reported.
#
# OMISSION: the three-wheel check existed but was collapsed to unanimity and
# reported as "no agreement on any day", discarding the 2-of-3 case entirely.
#
# These are PRE-REGISTERED for future windows.  They are scored below against
# the event bank *excluding* the discovery dates, because a rule invented to
# explain two days cannot be tested on those days.
# ============================================================================


def _from_point(chart: Chart, moving, name: str, ref_sign: int) -> int:
    return (moving[name].sign - ref_sign) % 12 + 1


def gochara_from_lagna(chart: Chart, jd: float, event: Event) -> float:
    """The same gochara table, counted from the ascendant rather than the Moon."""
    moving = transit(chart, jd)
    return sum(
        1.0 for n in SEVEN if _from_point(chart, moving, n, chart.asc.sign) in GOCHARA_GOOD[n]
    )


def gochara_from_sun(chart: Chart, jd: float, event: Event) -> float:
    """Counted from the natal Sun -- the third wheel of the sudarshana."""
    moving = transit(chart, jd)
    ref = chart.grahas["Sun"].sign
    return sum(1.0 for n in SEVEN if _from_point(chart, moving, n, ref) in GOCHARA_GOOD[n])


def gochara_wheel_agreement(chart: Chart, jd: float, event: Event) -> float:
    """Mean number of wheels (lagna, Moon, Sun) calling each transit good.

    Graded, not unanimous.  Unanimity is rare enough that reporting only it
    throws away most of the information.
    """
    moving = transit(chart, jd)
    refs = (chart.asc.sign, chart.grahas["Moon"].sign, chart.grahas["Sun"].sign)
    total = 0.0
    for n in SEVEN:
        total += sum(1.0 for r in refs if _from_point(chart, moving, n, r) in GOCHARA_GOOD[n])
    return total / 3.0


def yogakaraka_upachaya(chart: Chart, jd: float, event: Event) -> float:
    """Is the chart's yogakaraka transiting an upachaya house from the lagna?

    The yogakaraka -- one graha owning both a kendra and a trikona -- is the
    single most load-bearing planet in a chart that has one.  3/6/10/11 are the
    growth houses.  For a Taurus lagna the yogakaraka is Saturn.
    """
    # The lagna is both a kendra and a trikona, so a naive intersection test
    # makes every lagna lord a yogakaraka.  The kendra and the trikona have to
    # be *different* houses for the combination to mean anything.
    yk = None
    for g in SEVEN:
        owns = {h for h in range(1, 13) if SIGN_LORDS[(chart.asc.sign + h - 1) % 12] == g}
        if any(k != t for k in owns & {1, 4, 7, 10} for t in owns & {1, 5, 9}):
            yk = g
            break
    if yk is None:
        return 0.0
    h = _from_point(chart, transit(chart, jd), yk, chart.asc.sign)
    return 1.0 if h in (3, 6, 10, 11) else 0.0


def dasha_lord_stationing(chart: Chart, jd: float, event: Event) -> float:
    """Is a graha that currently rules a dasha level also near a station?

    ``station_proximity`` already measured stations, but blind to whether the
    stationing graha had any role in the running period.  A dasha lord that
    stations while its period runs is what the flat station measure could never
    see.
    """
    lords = {period.lord for period in active_periods(chart, jd)}
    moving = transit(chart, jd)
    best = 0.0
    for name in ("Saturn", "Jupiter", "Mercury", "Venus", "Mars"):
        if name not in lords:
            continue
        typical = {"Saturn": 0.11, "Jupiter": 0.23, "Mercury": 1.4, "Venus": 1.2, "Mars": 0.6}[name]
        best = max(best, max(0.0, 1.0 - abs(moving[name].speed) / (typical * 0.25)))
    return best


def transit_square_natal_self(chart: Chart, jd: float, event: Event) -> float:
    """A slow graha at 90/180 degrees to its own natal position.

    The 'return-cycle quarter points'.  Deterministic in age, so this is a
    weak hypothesis at population scale -- but within one nativity it marks
    the structural turning points of that graha's own cycle.
    """
    moving = transit(chart, jd)
    best = 0.0
    for name in ("Saturn", "Jupiter"):
        d = abs((moving[name].longitude - chart.grahas[name].longitude + 180) % 360 - 180)
        for ang in (90, 180):
            best = max(best, max(0.0, 1.0 - abs(d - ang) / 5.0))
    return best


LIBRARY += [
    Hypothesis("gochara counted from the lagna", gochara_from_lagna),
    Hypothesis("gochara counted from the Sun", gochara_from_sun),
    Hypothesis("three-wheel gochara agreement (graded)", gochara_wheel_agreement),
    Hypothesis("yogakaraka in an upachaya from lagna", yogakaraka_upachaya),
    Hypothesis("running dasha lord near its station", dasha_lord_stationing),
    Hypothesis("slow graha square/opposite its natal self", transit_square_natal_self),
]


# --- Sarvatobhadra chakra ---------------------------------------------------
#
# The one classical technique in the package with day-level resolution.  The
# chakra is repointed by the transiting Moon every day and by the 112-pada
# layer roughly every six hours, so unlike a dasha or a slow transit it makes
# a claim narrow enough for a day-dated event to falsify.


def _sbc_natal(chart: Chart) -> dict[int, str]:
    key = id(chart)
    hit = _SBC_NATAL.get(key)
    if hit is None:
        pan = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
        hit = sbc.natal_cells(chart, sbc.tithi_group(pan.tithi), pan.vara)
        _SBC_NATAL[key] = hit
    return hit


_SBC_NATAL: dict[int, dict[int, str]] = {}


@lru_cache(maxsize=10_000)
def _sbc_hits(chart_id: int, jd: float) -> tuple[sbc.Vedha, ...]:
    chart = _CHARTS[chart_id]
    return tuple(
        sbc.strikes(
            chart,
            jd,
            _sbc_natal(chart),
            moving=transit(chart, jd),
        )
    )


def sbc_vedha(chart: Chart, jd: float, event: Event) -> float:
    """Net benefic-minus-malefic vedha on every cell the native stands in."""
    _register(chart)
    per_cell: dict[int, list[bool]] = {}
    for hit in _sbc_hits(id(chart), jd):
        per_cell.setdefault(hit.cell, []).append(hit.benefic)
    total = 0.0
    for flags in per_cell.values():
        good = sum(flags)
        bad = len(flags) - good
        total += good - bad * (1.0 + 0.25 * max(0, bad - 1))
    return total


def sbc_clear_janma(chart: Chart, jd: float, event: Event) -> float:
    """The classical test: is the janma nakshatra free of malefic vedha?

    Vedha on the birth star is the single thing the texts warn about most --
    one strike is friction, four is fatal -- so a day with none of it should
    be when things are allowed to happen at all.
    """
    _register(chart)
    hits = [
        hit for hit in _sbc_hits(id(chart), jd) if hit.target in ("janma nakshatra", "janma rasi")
    ]
    bad = sum(1 for h in hits if not h.benefic)
    good = sum(1 for h in hits if h.benefic)
    return good - bad


def sbc_pada_vedha(chart: Chart, jd: float, event: Event) -> float:
    """The same, at 112-pada resolution rather than 28-nakshatra.

    Each nakshatra's four padas face each other across the chakra, so a graha
    in the first pada strikes the fourth of whatever its ray lands on.  This
    quarters the window a strike is live for.
    """
    per = sbc.peripheral_vedha()
    natal = {
        sbc.pada112(chart.grahas[g].longitude): g
        for g in SEVEN + ["Rahu", "Ketu"]
        if g in chart.grahas
    }
    natal[sbc.pada112(chart.asc.longitude)] = "Lagna"
    moving = transit(chart, jd)
    good = bad = 0
    for name in SEVEN + ["Rahu", "Ketu"]:
        for target in per.get(sbc.pada112(moving[name].longitude), {}).values():
            if target in natal:
                if name in sbc.BENEFICS:
                    good += 1
                else:
                    bad += 1
    return good - bad


def sbc_slow_vedha(chart: Chart, jd: float, event: Event) -> float:
    """Vedha cast by Saturn, Jupiter and the nodes only.

    The Moon repoints daily and washes out; the slow grahas hold a ray on a
    natal cell for months, which is the timescale a life event actually has.
    """
    _register(chart)
    hits = [hit for hit in _sbc_hits(id(chart), jd) if hit.graha in _SLOW]
    return sum(1 if h.benefic else -1 for h in hits)


LIBRARY += [
    Hypothesis("SBC vedha on natal cells", sbc_vedha),
    Hypothesis("SBC janma nakshatra clear of vedha", sbc_clear_janma),
    Hypothesis("SBC vedha at 112-pada resolution", sbc_pada_vedha),
    Hypothesis("SBC vedha from the slow grahas only", sbc_slow_vedha),
]


# ============================================================================
# Rare chakras.
#
# These were implemented in `rare.py` and shown by the `rare` command, but were
# never registered here -- so they reached the display and nothing else. The
# forecast feature matrix is built from this library, which meant a reading
# full of kota, bhrigu-bindu and moorthi detail had no path into the number the
# forecast actually produced. Each is restricted to the slow grahas, because a
# Moon-driven variant repoints daily and cannot be tested against events dated
# to a month or a quarter.
# ============================================================================

_KOTA_MALEFICS = ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
_MURTI_VALUE = {0: 1.0, 1: 0.66, 2: 0.33, 3: 0.0}


def kota_siege(chart: Chart, jd: float, event: Event) -> float:
    """Slow malefics inside the kota fort, weighted by how deep they stand.

    Twenty-eight nakshatras from the janma nakshatra form four concentric
    rings. A malefic in the inner ring is an assault on the fort; the classical
    reading is danger to the native rather than to a particular affair.
    """
    janma = chart.grahas["Moon"].nakshatra
    moving = transit(chart, jd)
    score = 0.0
    for name in _SLOW + ["Mars"]:
        if name not in _KOTA_MALEFICS:
            continue
        offset = (moving[name].nakshatra - janma) % 27
        ring = min(offset // 7, 3)
        score += (4 - ring) / 4.0  # innermost ring counts hardest
    return score


def bhrigu_bindu_transit(chart: Chart, jd: float, event: Event) -> float:
    """Slow grahas within orb of the Rahu/Moon midpoint.

    Absent from the standard textbooks, but the Bhrigu lineages treat transits
    over this point as decisive for turning points, which is a sharp enough
    claim to be worth testing.
    """
    rahu = chart.grahas["Rahu"].longitude
    moon = chart.grahas["Moon"].longitude
    bindu = (rahu + ((moon - rahu) % 360) / 2.0) % 360
    moving = transit(chart, jd)
    score = 0.0
    for name in _SLOW:
        sep = abs((moving[name].longitude - bindu + 180) % 360 - 180)
        if sep <= 8.0:
            score += 1.0 - sep / 8.0
    return score


def moorthi_nirnaya(chart: Chart, jd: float, event: Event) -> float:
    """Gold/silver/copper/iron grading of the slow transits.

    Counted from the janma nakshatra to the nakshatra each graha occupies.
    Gold is held to deliver the full result of a transit and iron almost none,
    so this grades transits the other techniques merely detect.
    """
    janma = chart.grahas["Moon"].nakshatra
    moving = transit(chart, jd)
    return sum(_MURTI_VALUE[((moving[name].nakshatra - janma) % 27) % 4] for name in _SLOW)


_LATTA = {"Sun": 12, "Moon": 22, "Mars": -3, "Jupiter": 6, "Saturn": -8, "Rahu": -9, "Ketu": -9}


def latta_on_janma(chart: Chart, jd: float, event: Event) -> float:
    """A graha's latta ("kick") landing on the janma nakshatra.

    Each graha spoils a nakshatra a fixed count away, forward for some and
    backward for others. The struck nakshatra is held to be unusable while the
    kick lasts.
    """
    janma = chart.grahas["Moon"].nakshatra
    moving = transit(chart, jd)
    return float(
        sum(1 for name, step in _LATTA.items() if (moving[name].nakshatra + step) % 27 == janma)
    )


# The shashtiamsa (D-60) was tried here and is deliberately not registered.
# The natal form is fixed for a chart, so within one nativity it carries no
# information over time; the transit form crosses a 0.5-degree
# division in roughly six to fifteen days for Jupiter and Saturn, which is far
# below the precision of the recorded event dates, so the gate would drop it
# for all but the day-precision events. `rare.shashtiamsa` also counts the
# deities forward in every sign, and the odd/even reversal is unverified.


LIBRARY += [
    Hypothesis("kota chakra: slow malefic under siege", kota_siege),
    Hypothesis("slow transit on the bhrigu bindu", bhrigu_bindu_transit),
    Hypothesis("moorthi nirnaya of the slow transits", moorthi_nirnaya),
    Hypothesis("latta kick on the janma nakshatra", latta_on_janma),
]


# ============================================================================
# Domain-aware activation.
#
# Most of this library is domain-blind: it returns the same number whether the
# question is a job, a move or a marriage, which is why every domain moves
# together whenever a dasha changes. These three ask what is happening to *the
# houses of the domain being asked about*, so a question about work and a
# question about money can separate.
# ============================================================================

_BENEFICS = ("Jupiter", "Venus", "Mercury", "Moon")


def dasha_lord_aspects_domain(chart: Chart, jd: float, event: Event) -> float:
    """A running dasha lord casting graha drishti on a domain house.

    Rulership and occupation are already tested elsewhere. Drishti is the third
    classical way a lord activates a bhava, and it is the one that catches a
    lord sitting far from the house it is about to move -- a fourth-house
    Jupiter throwing its aspect onto the tenth times a career change without
    ever occupying or owning it.
    """
    signs = _signs_for(chart, houses_for(event))
    score = 0.0
    for level, lord in _lords(chart, jd):
        for sign in signs:
            if chart.aspects_sign(lord, sign):
                score += 1.0 / level
    return score


def domain_lord_supported(chart: Chart, jd: float, event: Event) -> float:
    """The natal lord of a domain house receiving a benefic transit.

    The positive counterpart to the affliction test: the same lord, the same
    orb, but asking whether a benefic is on it rather than a malefic.
    """
    houses = houses_for(event)
    lords = {SIGN_LORDS[chart.house_sign(h)] for h in houses}
    moving = transit(chart, jd)
    score = 0.0
    for lord in lords:
        target = chart.grahas[lord].longitude
        for name in _BENEFICS:
            sep = abs((moving[name].longitude - target + 180) % 360 - 180)
            if sep < 8:
                score += 1.0 - sep / 8.0
    return score


def benefic_transit_on_domain(chart: Chart, jd: float, event: Event) -> float:
    """A transiting benefic occupying or aspecting a domain house."""
    signs = _signs_for(chart, houses_for(event))
    moving = transit(chart, jd)
    score = 0.0
    for name in _BENEFICS:
        position = moving[name]
        if position.sign in signs:
            score += 1.0
        for offset in chart.aspects_from(name):
            if (position.sign + offset - 1) % 12 in signs:
                score += 0.5
    return score


LIBRARY += [
    Hypothesis("running dasha lord aspects the domain house", dasha_lord_aspects_domain),
    Hypothesis("domain lord under benefic transit", domain_lord_supported),
    Hypothesis("benefic transit in or aspecting the domain house", benefic_transit_on_domain),
]


# Provenance is explicit so retrospective exploration cannot masquerade as a
# prospective test. Dates follow the construction history recorded in AUDIT.md.
# Exact textual citations remain blank unless independently checked.
#
# Keyed by technique id, not by list position: provenance used to be assigned
# by slicing LIBRARY, so removing any earlier entry silently relabelled the
# introduction date and discovery exclusions of unrelated techniques.
_POST_MORTEM = frozenset(
    {
        "gochara-counted-from-the-lagna",
        "gochara-counted-from-the-sun",
        "three-wheel-gochara-agreement-graded",
        "yogakaraka-in-an-upachaya-from-lagna",
        "running-dasha-lord-near-its-station",
        "slow-graha-square-opposite-its-natal-self",
    }
)
_SBC_BATCH = frozenset(
    {
        "sbc-vedha-on-natal-cells",
        "sbc-janma-nakshatra-clear-of-vedha",
        "sbc-vedha-at-112-pada-resolution",
        "sbc-vedha-from-the-slow-grahas-only",
    }
)
# Rare chakras that were implemented but never registered, so they reached the
# `rare` display and nothing else -- neither the backtest nor the forecast
# feature matrix, which is built from this same library.
_RARE_BATCH = frozenset(
    {
        "kota-chakra-slow-malefic-under-siege",
        "slow-transit-on-the-bhrigu-bindu",
        "moorthi-nirnaya-of-the-slow-transits",
        "latta-kick-on-the-janma-nakshatra",
        "running-dasha-lord-aspects-the-domain-house",
        "domain-lord-under-benefic-transit",
        "benefic-transit-in-or-aspecting-the-domain-house",
    }
)

for _hypothesis in LIBRARY:
    _tid = _hypothesis.technique_id
    if _hypothesis.name.startswith("CONTROL"):
        _hypothesis.introduced_at = "batch-1"
        _hypothesis.status = "control"
        _hypothesis.family = "control"
        continue
    if _tid in _RARE_BATCH:
        _hypothesis.introduced_at = "batch-5"
    elif _tid in _POST_MORTEM or _tid in _SBC_BATCH:
        _hypothesis.introduced_at = "batch-4"
    else:
        _hypothesis.introduced_at = "batch-1"
    _hypothesis.status = "exploratory"
    if _tid in _POST_MORTEM:
        _hypothesis.discovery_exclusions = ("2024-03-18", "2024-04-09")
        _hypothesis.note = (
            (_hypothesis.note + " ").strip()
            + "Added after a forecast review; the dates that prompted it are "
            "mechanically excluded."
        ).strip()


def by_id(technique_id: str) -> Hypothesis:
    matches = [h for h in LIBRARY if h.technique_id == technique_id]
    if not matches:
        raise KeyError(f"unknown technique id {technique_id!r}")
    if len(matches) > 1:
        raise RuntimeError(f"duplicate technique id {technique_id!r}")
    return matches[0]


def registry() -> list[dict]:
    return [h.metadata() for h in LIBRARY]
