"""Vivah phase 2: the marriage lagna inside each listed window (docs/sources/vivah.md,
"Phase 2", V1-V10 as the lead adopted them on 16 Oct 2026), by MC ch. 6 with the
commentary.

A window is cut wherever the lagna's navamsa or the Moon's changes, and each piece is
judged at its middle:
  bars (MC 6.84's houses, which take in the jamitra from the lagna; the Moon's narrow
    jamitra, 6.65; kartari, 6.42; the navamsa, 6.82-83; vimsopaka under 5, 6.90),
  faults (purity, 6.73-76; the Moon's kartari; blind, deaf and lame lagnas, 6.79-81;
    the Dipika's malefic in the Moon's 7th; plain hemming; kuvarga, DS p. 182),
  supports (6.85's places, scored by 6.90's vimsopaka).
6.86 cancels the faults it names; 6.87 lifts only the blind and deaf lagnas.
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.chart import (
    COMBUSTION_ORB,
    COMBUSTION_ORB_RETRO,
    DEBILITATION,
    NATURAL_FRIENDS,
    NODE_SIGNS,
    OWN_SIGNS,
    SIGN_LORDS,
)
from jyotisha.ephemeris import ascendant, positions
from jyotisha.vargas import varga

from .ids import GRAHA_ID, SIGN_IDS
from .timeutil import iso

NAV = 30 / 9  # one navamsa, in degrees
GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
NODES = ("Rahu", "Ketu")
STEP = 1 / 720  # two minutes: a navamsa of the lagna lasts ten or more
# MC 6.73: a quarter on the 3rd and 10th, a half on the 5th and 9th, three quarters on
# the 4th and 8th, the 7th whole; Saturn, Jupiter and Mars see their pairs whole. Any
# fraction counts as seeing (V6, our reading), so only the houses matter here.
ASPECTED = {3, 4, 5, 7, 8, 9, 10}
# MC 6.85's places (supports) and 6.90's points for them.
PLACES = {
    "Sun": {3, 6, 8, 11},
    "Saturn": {3, 6, 8, 11},
    "Rahu": {3, 6, 8, 11},
    "Ketu": {3, 6, 8, 11},
    "Mars": {3, 6, 11},
    "Moon": {2, 3, 11},
    "Mercury": {1, 2, 3, 4, 5, 6, 9, 10, 11},
    "Jupiter": {1, 2, 3, 4, 5, 6, 9, 10, 11},
    "Venus": {1, 2, 4, 5, 9, 10, 11},
}
POINTS = {
    "Moon": 5.0,
    "Sun": 3.5,
    "Jupiter": 3.0,
    "Mercury": 2.0,
    "Venus": 2.0,
    "Saturn": 1.5,
    "Rahu": 1.5,
    "Ketu": 1.5,
    "Mars": 1.5,
}
# MC 6.79: (deaf, blind, lame) by day and by night.
BY_DAY = {"deaf_lagna": {6, 7}, "blind_lagna": {4, 0, 1}, "lame_lagna": {10}}
BY_NIGHT = {"deaf_lagna": {9, 8}, "blind_lagna": {5, 2, 3}, "lame_lagna": {11}}
GOOD_NAVAMSA = {2, 5, 6}  # Gemini, Virgo, Libra; Sagittarius's first half below
DS_NAVAMSA = {1, 3}  # Taurus, Cancer: DS p. 182 only
PISCES = 11
MOVABLE = {0, 3, 6, 9}
LEVEL = {
    "purity_lagna": "heavy",
    "purity_seventh": "heavy",
    "kartari_moon": "fault",
    "kuvarga": "fault",
    "navamsa_pisces": "last_resort",
    "vimsopaka_poor": "last_resort",
    "navamsa_ds_only": "ds_only",
    "blind_lagna": "light",
    "deaf_lagna": "light",
    "lame_lagna": "light",
    "moon_seventh_malefic": "light",
    "hemming_lagna": "light",
    "hemming_moon": "light",
    "kuvarga_three": "light",
}


def _malefic(g: str, bright: bool) -> bool:
    """V1: Vasishtha's malefics, the Moon only in the dark fortnight (our reading)."""
    return g in ("Sun", "Mars", "Saturn", "Rahu", "Ketu") or (g == "Moon" and not bright)


def _benefic(g: str, bright: bool) -> bool:
    return g in ("Mercury", "Jupiter", "Venus") or (g == "Moon" and bright)


def _sees(p: dict, g: str, sign: int, occupy: bool = True) -> bool:
    """MC 6.73's aspect (any fraction), or occupation when `occupy`. The nodes cast none."""
    if occupy and p[g].sign == sign:
        return True
    return g not in NODES and (sign - p[g].sign) % 12 + 1 in ASPECTED


def _direct(p: dict, g: str) -> bool:
    """V4: the nodes always count as retrograde; the luminaries never are."""
    if g in NODES:
        return False
    return g in ("Sun", "Moon") or p[g].speed >= 0


def _debilitated(p: dict, g: str) -> bool:
    if g in NODES:
        return p[g].sign == NODE_SIGNS[g]["debilitated"]
    return p[g].sign == DEBILITATION[g][0]


def _enemy_sign(p: dict, g: str) -> bool:
    if g in NODES or p[g].sign in OWN_SIGNS[g]:
        return False
    lord = SIGN_LORDS[p[g].sign]
    friends, neutrals = NATURAL_FRIENDS[g]
    return lord != g and lord not in friends and lord not in neutrals


def _combust(p: dict, g: str) -> bool:
    if g not in COMBUSTION_ORB:  # the Sun and the nodes (p. 270)
        return False
    orb = COMBUSTION_ORB_RETRO.get(g, COMBUSTION_ORB[g]) if p[g].speed < 0 else COMBUSTION_ORB[g]
    return abs((p[g].longitude - p["Sun"].longitude + 180) % 360 - 180) <= orb


def _weak(p: dict, g: str) -> bool:
    """MC 6.86's test for kartari's malefics: an enemy's sign, debilitated or combust."""
    return _enemy_sign(p, g) or _debilitated(p, g) or _combust(p, g)


def _kartari(p: dict, base: int, bright: bool) -> tuple[bool, bool]:
    """MC 6.42 from `base`: a direct malefic in the 12th and a retrograde one in the
    2nd, not cancelled by 6.86 (both weak, our reading); and plain hemming, malefics in
    both the 2nd and the 12th."""
    house = {g: (p[g].sign - base) % 12 + 1 for g in GRAHAS}
    bad = [g for g in GRAHAS if _malefic(g, bright)]
    twelfth = [g for g in bad if house[g] == 12]
    second = [g for g in bad if house[g] == 2]
    pairs = [(d, r) for d in twelfth for r in second if _direct(p, d) and not _direct(p, r)]
    kartari = any(not (_weak(p, d) and _weak(p, r)) for d, r in pairs)
    return kartari, bool(twelfth and second and not pairs)


def _moon_lifted(p: dict) -> bool:
    """MC p. 286 (Rajamartanda, Vyavaharasamuccaya): the Moon exalted, in its own sign,
    in a benefic's or a friend's sign, or aspected by a benefic."""
    sign = p["Moon"].sign
    lord = SIGN_LORDS[sign]
    if sign in (1, 3) or lord in ("Mercury", "Jupiter", "Venus"):
        return True
    if lord in NATURAL_FRIENDS["Moon"][0]:
        return True
    return any(_sees(p, g, sign, occupy=False) for g in ("Mercury", "Jupiter", "Venus"))


def _pure(p: dict, sign: int, nav: int, bright: bool) -> bool:
    """MC 6.74-76 for one side: the navamsa's lord sees the navamsa sign or the sign; or
    the sign's lord sees the sign, or the two lords see each other's; or a benefic
    friend of the navamsa's lord sees either (V6: by sign, no D9 chart)."""
    nav_lord, lord = SIGN_LORDS[nav], SIGN_LORDS[sign]
    if _sees(p, nav_lord, nav) or _sees(p, nav_lord, sign):
        return True
    if _sees(p, lord, sign) or _sees(p, lord, nav):
        return True
    friends = [f for f in NATURAL_FRIENDS[nav_lord][0] if _benefic(f, bright)]
    return any(_sees(p, f, nav) or _sees(p, f, sign) for f in friends)


def _kuvarga(asc: float, bright: bool) -> int:
    """V10: how many of Vasishtha's six vargas of the lagna have a benefic lord."""
    signs = [int(varga(asc, d) // 30) % 12 for d in (1, 2, 3, 9, 12, 30)]
    return sum(_benefic(SIGN_LORDS[s], bright) for s in signs)


def judge(t: float, q, bright: bool, day: bool) -> dict:
    """Every V1-V10 test for the lagna rising at t."""
    p = positions(t, q.ayanamsa)
    asc = ascendant(t, q.lat, q.lon, q.ayanamsa)[0].longitude
    lagna = int(asc // 30) % 12
    nav = int(asc // NAV) % 12
    part = int((asc % 30) // NAV)  # 0-8 within the sign
    half = (asc % NAV) / NAV < 0.5
    house = {g: (p[g].sign - lagna) % 12 + 1 for g in GRAHAS}
    lord = SIGN_LORDS[lagna]
    bars: list[str] = []
    faults: list[str] = []

    # MC 6.84: the placements that break the lagna, with 6.86's cancellations.
    def at(h: int) -> list[str]:
        return [g for g in GRAHAS if house[g] == h]

    if any(g == "Moon" or _malefic(g, bright) for g in at(1)):
        bars.append("h1")
    if "Venus" in at(3):
        bars.append("h3_venus")
    six = [g for g in at(6) if g in (lord, "Venus", "Moon")]
    six = [
        g
        for g in six
        if g == lord
        or not (
            (g == "Venus" and (_enemy_sign(p, g) or _debilitated(p, g)))
            or (g == "Moon" and _moon_low(p))
        )
    ]
    if six:
        bars.append("h6")
    if at(7):
        bars.append("h7")  # also the jamitra from the lagna (MC 6.65), nodes included
    eight = [g for g in at(8) if g in (lord, "Moon", "Mars") or _benefic(g, bright)]
    eight = [
        g
        for g in eight
        if g == lord
        or not (
            (g == "Mars" and (_combust(p, g) or _enemy_sign(p, g) or _debilitated(p, g)))
            or (g == "Moon" and _moon_low(p))
        )
    ]
    if eight:
        bars.append("h8")
    if "Mars" in at(10):
        bars.append("h10_mars")
    if "Saturn" in at(12):
        bars.append("h12_saturn")

    # MC 6.65: the Moon in the 55th navamsa from a malefic, and the Dipika's lighter
    # fault of a malefic elsewhere in its 7th; both lapse with a well-placed Moon.
    moon_nav = int(p["Moon"].longitude // NAV)
    lifted = _moon_lifted(p)
    if not lifted:
        opposite = [
            g
            for g in ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
            if (moon_nav - int(p[g].longitude // NAV)) % 108 == 54
        ]
        seventh = [
            g
            for g in ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
            if (p[g].sign - p["Moon"].sign) % 12 == 6 and g not in opposite
        ]
        if opposite:
            bars.append("jamitra_moon")
        if seventh:
            faults.append("moon_seventh_malefic")

    # MC 6.42: kartari from the lagna is a bar, from the Moon a fault unless a benefic
    # sees the Moon; plain hemming is the lesser fault.
    kartari, hemmed = _kartari(p, lagna, bright)
    if kartari:
        bars.append("kartari")
    elif hemmed:
        faults.append("hemming_lagna")
    kartari_m, hemmed_m = _kartari(p, p["Moon"].sign, bright)
    moon_seen = any(
        _sees(p, g, p["Moon"].sign, occupy=False) for g in ("Mercury", "Jupiter", "Venus")
    )
    if kartari_m and not moon_seen:
        faults.append("kartari_moon")
    elif hemmed_m or kartari_m:
        if not kartari_m:
            faults.append("hemming_moon")

    # MC 6.82-83: the lagna's navamsa.
    if nav in GOOD_NAVAMSA or (nav == 8 and half):
        pass
    elif nav in DS_NAVAMSA:
        faults.append("navamsa_ds_only")
    elif nav == PISCES:
        faults.append("navamsa_pisces")
    else:
        bars.append("navamsa")
    if part == 8 and nav != lagna:
        bars.append("last_navamsa")
    if p["Moon"].sign in (6, 9) and lagna in MOVABLE and nav in MOVABLE:
        bars.append("movable_navamsa")

    # MC 6.85 and 6.90: the points of the planets in their places.
    supports = [g for g in GRAHAS if house[g] in PLACES[g]]
    points = sum(POINTS[g] for g in supports)
    if points < 5:
        bars.append("vimsopaka")
        grade = "rejected"
    elif points < 10:
        faults.append("vimsopaka_poor")
        grade = "poor"
    else:
        grade = "middling" if points <= 15 else "best"

    # MC 6.73-76: the purity of the lagna (the groom's side) and the 7th (the bride's).
    if not _pure(p, lagna, nav, bright):
        faults.append("purity_lagna")
    if not _pure(p, (lagna + 6) % 12, (nav + 6) % 12, bright):
        faults.append("purity_seventh")

    # MC 6.79-81: blind, deaf and lame at their own time, lifted by the sign's lord or
    # Jupiter seeing it; 6.87 lifts the blind and deaf with Mercury, Jupiter or Venus
    # in a kendra other than the 7th or in a trine.
    table = BY_DAY if day else BY_NIGHT
    lift87 = any(house[g] in (1, 4, 10, 5, 9) for g in ("Mercury", "Jupiter", "Venus"))
    for rule, signs in table.items():
        if lagna not in signs:
            continue
        if _sees(p, lord, lagna, occupy=False) or _sees(p, "Jupiter", lagna, occupy=False):
            continue
        if lift87 and rule != "lame_lagna":
            continue
        faults.append(rule)

    # DS p. 182, no. 12: kuvarga.
    good = _kuvarga(asc, bright)
    if good < 3:
        faults.append("kuvarga")
    elif good == 3:
        faults.append("kuvarga_three")

    return {
        "sign": SIGN_IDS[lagna],
        "navamsa": SIGN_IDS[nav],
        "points": points,
        "grade": grade,
        "bars": bars,
        "faults": faults,
        "supports": [GRAHA_ID[g] for g in supports],
    }


def _moon_low(p: dict) -> bool:
    """MC 6.86: the Moon debilitated, or in a debilitated (Scorpio) navamsa."""
    return p["Moon"].sign == 7 or int(p["Moon"].longitude // NAV) % 12 == 7


def window(a: float, b: float, q, bright: bool, sunrise: float, sunset: float) -> dict:
    """The lagnas of one window: its unbarred pieces, each with faults and supports,
    and the minutes barred by each rule."""

    def key(t: float) -> tuple[int, int]:
        asc = ascendant(t, q.lat, q.lon, q.ayanamsa)[0].longitude
        moon = positions(t, q.ayanamsa)["Moon"].longitude
        return int(asc // NAV), int(moon // NAV)

    cuts = [a, *(t for t, _ in Mu._scan(key, a, b, STEP)), b]
    lagnas, barred = [], {}
    for x, y in zip(cuts, cuts[1:], strict=False):
        if y - x <= 0:
            continue
        mid = (x + y) / 2
        v = judge(mid, q, bright, sunrise <= mid < sunset)
        if v["bars"]:
            for rule in v["bars"]:
                barred[rule] = barred.get(rule, 0) + (y - x) * 1440
            continue
        row = {"start": iso(x, q.tz), "end": iso(y, q.tz), **v}
        del row["bars"]
        row["clean"] = not v["faults"]
        if lagnas and _same(lagnas[-1], row):
            lagnas[-1]["end"] = row["end"]
        else:
            lagnas.append(row)
    return {"lagnas": lagnas, "lagnaBars": {k: round(m) for k, m in sorted(barred.items())}}


def _same(a: dict, b: dict) -> bool:
    keys = ("sign", "navamsa", "points", "grade", "faults", "supports")
    return a["end"] == b["start"] and all(a[k] == b[k] for k in keys)


def light_only(faults: list[str]) -> bool:
    return all(LEVEL[f] == "light" for f in faults)


GRAHA_IDS = {g: GRAHA_ID[g] for g in GRAHAS}
