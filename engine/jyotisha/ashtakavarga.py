"""Ashtakavarga, carried through to the parts most software stops short of.

The chain is: bhinna -> sarva -> trikona shodhana -> ekadhipatya shodhana ->
sodhya pinda, plus the kakshya subdivision, which is what takes a transit
judgement from month-resolution down to roughly three days.
"""

from __future__ import annotations

import weakref

from .chart import Chart
from .ephemeris import SEVEN, SIGNS

# Benefic places contributed by each reference point, counted from itself.
BAV_RULES = {
    "Sun": {
        "Sun": [1, 2, 4, 7, 8, 9, 10, 11],
        "Moon": [3, 6, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [5, 6, 9, 11],
        "Venus": [6, 7, 12],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Asc": [3, 4, 6, 10, 11, 12],
    },
    "Moon": {
        "Sun": [3, 6, 7, 8, 10, 11],
        "Moon": [1, 3, 6, 7, 10, 11],
        "Mars": [2, 3, 5, 6, 9, 10, 11],
        "Mercury": [1, 3, 4, 5, 7, 8, 10, 11],
        "Jupiter": [1, 4, 7, 8, 10, 11, 12],
        "Venus": [3, 4, 5, 7, 9, 10, 11],
        "Saturn": [3, 5, 6, 11],
        "Asc": [3, 6, 10, 11],
    },
    "Mars": {
        "Sun": [3, 5, 6, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [3, 5, 6, 11],
        "Jupiter": [6, 10, 11, 12],
        "Venus": [6, 8, 11, 12],
        "Saturn": [1, 4, 7, 8, 9, 10, 11],
        "Asc": [1, 3, 6, 10, 11],
    },
    "Mercury": {
        "Sun": [5, 6, 9, 11, 12],
        "Moon": [2, 4, 6, 8, 10, 11],
        "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
        "Mercury": [1, 3, 5, 6, 9, 10, 11, 12],
        "Jupiter": [6, 8, 11, 12],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 11],
        "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
        "Asc": [1, 2, 4, 6, 8, 10, 11],
    },
    "Jupiter": {
        "Sun": [1, 2, 3, 4, 7, 8, 9, 10, 11],
        "Moon": [2, 5, 7, 9, 11],
        "Mars": [1, 2, 4, 7, 8, 10, 11],
        "Mercury": [1, 2, 4, 5, 6, 9, 10, 11],
        "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
        "Venus": [2, 5, 6, 9, 10, 11],
        "Saturn": [3, 5, 6, 12],
        "Asc": [1, 2, 4, 5, 6, 7, 9, 10, 11],
    },
    "Venus": {
        "Sun": [8, 11, 12],
        "Moon": [1, 2, 3, 4, 5, 8, 9, 11, 12],
        "Mars": [3, 5, 6, 9, 11, 12],
        "Mercury": [3, 5, 6, 9, 11],
        "Jupiter": [5, 8, 9, 10, 11],
        "Venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
        "Saturn": [3, 4, 5, 8, 9, 10, 11],
        "Asc": [1, 2, 3, 4, 5, 8, 9, 11],
    },
    "Saturn": {
        "Sun": [1, 2, 4, 7, 8, 10, 11],
        "Moon": [3, 6, 11],
        "Mars": [3, 5, 6, 10, 11, 12],
        "Mercury": [6, 8, 9, 10, 11, 12],
        "Jupiter": [5, 6, 11, 12],
        "Venus": [6, 11, 12],
        "Saturn": [3, 5, 6, 11],
        "Asc": [1, 3, 4, 6, 10, 11],
    },
}

# Each sign is split into eight kakshyas of 3°45', ruled in this order.
KAKSHYA_LORDS = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon", "Asc"]
KAKSHYA_SPAN = 30.0 / 8

RASHI_MULTIPLIER = [7, 10, 8, 4, 10, 5, 7, 8, 9, 5, 11, 12]
GRAHA_MULTIPLIER = {
    "Sun": 5,
    "Moon": 5,
    "Mars": 8,
    "Mercury": 5,
    "Jupiter": 10,
    "Venus": 7,
    "Saturn": 5,
}

TRIKONAS = [[0, 4, 8], [1, 5, 9], [2, 6, 10], [3, 7, 11]]
DUAL_RULERSHIP = [(0, 7), (1, 6), (2, 5), (8, 11), (9, 10)]


def bhinna(chart: Chart) -> dict[str, list[int]]:
    """Bindus per sign for each of the seven grahas."""
    refs = {name: chart.grahas[name].sign for name in SEVEN}
    refs["Asc"] = chart.asc.sign
    out = {}
    for planet, rules in BAV_RULES.items():
        bindus = [0] * 12
        for ref, houses in rules.items():
            base = refs[ref]
            for h in houses:
                bindus[(base + h - 1) % 12] += 1
        out[planet] = bindus
    return out


def sarva(bav: dict[str, list[int]]) -> list[int]:
    return [sum(bav[p][s] for p in SEVEN) for s in range(12)]


def trikona_shodhana(bindus: list[int]) -> list[int]:
    """Within each trikona: a zero wipes the group, else subtract the least."""
    out = list(bindus)
    for group in TRIKONAS:
        values = [out[s] for s in group]
        least = min(values)
        if least == 0:
            for s in group:
                out[s] = 0
        else:
            for s in group:
                out[s] -= least
    return out


def ekadhipatya_shodhana(bindus: list[int], chart: Chart) -> list[int]:
    """Reduction across the two signs a single graha rules."""
    out = list(bindus)
    occupied = {chart.grahas[g].sign for g in SEVEN}
    for a, b in DUAL_RULERSHIP:
        va, vb = out[a], out[b]
        if va == 0 or vb == 0:
            continue
        oa, ob = a in occupied, b in occupied
        if oa and ob:
            continue
        if not oa and not ob:
            if va == vb:
                out[a] = out[b] = 0
            else:
                out[a] = out[b] = min(va, vb)
        else:
            vacant = b if oa else a
            other = va if oa else vb
            if out[vacant] == other:
                out[vacant] = 0
            else:
                out[vacant] = min(va, vb)
    return out


def sodhya_pinda(chart: Chart, planet: str) -> dict:
    """Reduced bindus weighted by sign and by occupying graha."""
    reduced = ekadhipatya_shodhana(trikona_shodhana(bhinna(chart)[planet]), chart)
    rashi = sum(reduced[s] * RASHI_MULTIPLIER[s] for s in range(12))
    graha = sum(reduced[chart.grahas[g].sign] * GRAHA_MULTIPLIER[g] for g in SEVEN)
    return {
        "reduced": reduced,
        "rashi_pinda": rashi,
        "graha_pinda": graha,
        "sodhya_pinda": rashi + graha,
    }


_BHINNA_CACHE: dict[int, tuple[weakref.ref, dict]] = {}
_BHINNA_CACHE_LIMIT = 4096


def _bhinna_cached(key: int, chart: Chart) -> dict[str, list[int]]:
    # Keyed by id(chart), so an entry is only trusted while it still points at
    # the same live object: in a long-running process a freed chart's id is
    # reused by the next one, and a bare id key then served the dead chart's
    # bindus to the new chart.
    hit = _BHINNA_CACHE.get(key)
    if hit is not None and hit[0]() is chart:
        return hit[1]
    if len(_BHINNA_CACHE) >= _BHINNA_CACHE_LIMIT:
        _BHINNA_CACHE.clear()
    bav = bhinna(chart)
    _BHINNA_CACHE[key] = (weakref.ref(chart), bav)
    return bav


def kakshya(longitude: float) -> tuple[int, str]:
    """Which of the eight kakshyas a longitude falls in, and its lord."""
    idx = min(int((longitude % 30) / KAKSHYA_SPAN), 7)
    return idx, KAKSHYA_LORDS[idx]


def kakshya_transit(chart: Chart, moving: dict, planet: str) -> dict:
    """Is a transiting graha in a kakshya that gave it a bindu?

    This is the technique that turns 'Saturn in Pisces for two years' into a
    ladder of roughly three-day windows that alternate active and inert.
    """
    p = moving[planet]
    idx, lord = kakshya(p.longitude)
    bav = _bhinna_cached(id(chart), chart)[planet]
    refs = {name: chart.grahas[name].sign for name in SEVEN}
    refs["Asc"] = chart.asc.sign
    contributed = ((p.sign - refs[lord]) % 12 + 1) in BAV_RULES[planet][lord]
    return {
        "planet": planet,
        "sign": p.sign,
        "degree": p.degree,
        "kakshya": idx + 1,
        "kakshya_lord": lord,
        "active": contributed,
        "sign_bindus": bav[p.sign],
        "house": (p.sign - chart.asc.sign) % 12 + 1,
    }


def report(chart: Chart) -> str:
    bav = bhinna(chart)
    sav = sarva(bav)
    lines = [f"{'Sign':10s}" + "".join(f"{p[:3]:>5s}" for p in SEVEN) + f"{'SAV':>6s}{'ho':>4s}"]
    for s in range(12):
        row = "".join(f"{bav[p][s]:5d}" for p in SEVEN)
        lines.append(f"{SIGNS[s]:10s}{row}{sav[s]:6d}{(s - chart.asc.sign) % 12 + 1:4d}")
    lines.append(f"{'TOTAL':10s}" + "".join(f"{sum(bav[p]):5d}" for p in SEVEN) + f"{sum(sav):6d}")
    lines.append("")
    lines.append(f"{'':10s}{'rashi':>8s}{'graha':>8s}{'sodhya':>8s}")
    for p in SEVEN:
        sp = sodhya_pinda(chart, p)
        lines.append(f"{p:10s}{sp['rashi_pinda']:8d}{sp['graha_pinda']:8d}{sp['sodhya_pinda']:8d}")
    return "\n".join(lines)
