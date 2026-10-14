"""Yoga detection.

Previously this package knew five yogas.  This is the corpus: pancha
mahapurusha, raja and dhana yogas, vipareeta, neecha bhanga, the lunar and
solar yogas, parivartana, the doshas, and the nabhasa families (sankhya,
ashraya, dala, akriti).

Each detector returns a Yoga with the reason it fired, so a claim can be
audited rather than taken on trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .chart import OWN_SIGNS, SIGN_LORDS, Chart
from .ephemeris import SEVEN, SIGNS

KENDRA = (1, 4, 7, 10)
TRIKONA = (1, 5, 9)
DUSTHANA = (6, 8, 12)
NATURAL_BENEFICS = {"Jupiter", "Venus"}


@dataclass
class Yoga:
    name: str
    category: str
    detail: str
    strength: float = 1.0

    def __str__(self) -> str:
        return f"{self.name:32s} {self.category:16s} {self.detail}"


def _benefics(chart: Chart) -> list[str]:
    return [g for g in SEVEN if chart.is_benefic(g)]


def _malefics(chart: Chart) -> list[str]:
    return [g for g in SEVEN if not chart.is_benefic(g)]


def _conjunct(chart: Chart, a: str, b: str) -> bool:
    return chart.grahas[a].sign == chart.grahas[b].sign


def _mutual_aspect(chart: Chart, a: str, b: str) -> bool:
    return chart.aspects_sign(a, chart.grahas[b].sign) and chart.aspects_sign(
        b, chart.grahas[a].sign
    )


def _related(chart: Chart, a: str, b: str) -> str | None:
    if a == b:
        return None
    if _conjunct(chart, a, b):
        return "conjunct"
    if _mutual_aspect(chart, a, b):
        return "mutual aspect"
    if chart.grahas[a].sign in OWN_SIGNS.get(b, []) and chart.grahas[b].sign in OWN_SIGNS.get(
        a, []
    ):
        return "exchange"
    return None


# --- pancha mahapurusha -----------------------------------------------------

MAHAPURUSHA = {
    "Mars": "Ruchaka",
    "Mercury": "Bhadra",
    "Jupiter": "Hamsa",
    "Venus": "Malavya",
    "Saturn": "Sasa",
}


def mahapurusha(chart: Chart) -> list[Yoga]:
    out = []
    for g, name in MAHAPURUSHA.items():
        d = chart.dignity(g)
        h = chart.house(g)
        if d in ("exalted", "own", "moolatrikona") and h in KENDRA:
            out.append(Yoga(f"{name} Yoga", "mahapurusha", f"{g} {d} in house {h}"))
    return out


# --- raja and dhana ---------------------------------------------------------


def raja_yogas(chart: Chart) -> list[Yoga]:
    """A kendra lord joined to a trikona lord.  The 9th and 10th lords
    together is the strongest form."""
    out = []
    kendra_lords = {chart.lord(h): h for h in KENDRA}
    trikona_lords = {chart.lord(h): h for h in TRIKONA}
    for a, ha in kendra_lords.items():
        for b, hb in trikona_lords.items():
            if a == b:
                if ha != hb:
                    out.append(
                        Yoga(
                            "Raja Yoga (single lord)",
                            "raja",
                            f"{a} rules kendra {ha} and trikona {hb}",
                        )
                    )
                continue
            rel = _related(chart, a, b)
            if rel:
                strong = 1.5 if {ha, hb} == {10, 9} else 1.0
                out.append(
                    Yoga("Raja Yoga", "raja", f"{a} (kendra {ha}) {rel} {b} (trikona {hb})", strong)
                )
    return out


def dhana_yogas(chart: Chart) -> list[Yoga]:
    """Wealth: the 2nd and 11th lords linked to the 1st, 5th or 9th."""
    out = []
    wealth = {chart.lord(h): h for h in (2, 11)}
    source = {chart.lord(h): h for h in (1, 5, 9)}
    for a, ha in wealth.items():
        for b, hb in source.items():
            if a == b:
                continue
            rel = _related(chart, a, b)
            if rel:
                out.append(
                    Yoga("Dhana Yoga", "dhana", f"{a} (lord of {ha}) {rel} {b} (lord of {hb})")
                )
    return out


def vipareeta_raja(chart: Chart) -> list[Yoga]:
    """A dusthana lord placed in another dusthana: harm cancels harm."""
    names = {6: "Harsha", 8: "Sarala", 12: "Vimala"}
    out = []
    for h, name in names.items():
        lord = chart.lord(h)
        where = chart.house(lord)
        if where in DUSTHANA:
            out.append(Yoga(f"{name} Yoga", "vipareeta", f"lord of {h} ({lord}) in house {where}"))
    return out


def neecha_bhanga(chart: Chart) -> list[Yoga]:
    """Cancellation of debilitation.

    Several cancellation clauses are taught; the three most widely accepted
    are used -- the dispositor or the exaltation lord in a kendra from the
    lagna or the Moon, or the debilitated graha aspected by its dispositor.
    """
    out = []
    for g in SEVEN:
        if chart.dignity(g) != "debilitated":
            continue
        sign = chart.grahas[g].sign
        dispositor = SIGN_LORDS[sign]
        exalt_lord = SIGN_LORDS[(sign + 6) % 12]
        reasons = []
        for other in {dispositor, exalt_lord}:
            if chart.house(other) in KENDRA:
                reasons.append(f"{other} in kendra from lagna")
            if (chart.grahas[other].sign - chart.grahas["Moon"].sign) % 12 + 1 in KENDRA:
                reasons.append(f"{other} in kendra from the Moon")
        if chart.aspects_sign(dispositor, sign):
            reasons.append(f"aspected by its dispositor {dispositor}")
        if reasons:
            out.append(
                Yoga(
                    "Neecha Bhanga Raja Yoga",
                    "cancellation",
                    f"{g} debilitated in {SIGNS[sign]}; " + "; ".join(sorted(set(reasons))),
                )
            )
    return out


# --- lunar and solar --------------------------------------------------------


def lunar_yogas(chart: Chart) -> list[Yoga]:
    out = []
    moon = chart.grahas["Moon"].sign
    second = [g for g in SEVEN if g != "Moon" and chart.grahas[g].sign == (moon + 1) % 12]
    twelfth = [g for g in SEVEN if g != "Moon" and chart.grahas[g].sign == (moon - 1) % 12]
    with_moon = [g for g in SEVEN if g != "Moon" and chart.grahas[g].sign == moon]
    if second and twelfth:
        out.append(
            Yoga(
                "Durudhara Yoga",
                "lunar",
                f"2nd from Moon: {'+'.join(second)}; 12th: {'+'.join(twelfth)}",
            )
        )
    elif second:
        out.append(Yoga("Sunapha Yoga", "lunar", f"2nd from Moon: {'+'.join(second)}"))
    elif twelfth:
        out.append(Yoga("Anapha Yoga", "lunar", f"12th from Moon: {'+'.join(twelfth)}"))
    elif not with_moon:
        out.append(Yoga("Kemadruma Yoga", "lunar", "no graha in the 2nd, 12th or with the Moon"))

    jup_from_moon = (chart.grahas["Jupiter"].sign - moon) % 12 + 1
    if jup_from_moon in KENDRA:
        out.append(
            Yoga("Gaja Kesari Yoga", "lunar", f"Jupiter in house {jup_from_moon} from the Moon")
        )
    if _conjunct(chart, "Moon", "Mars"):
        out.append(Yoga("Chandra-Mangala Yoga", "lunar", "Moon conjunct Mars"))
    adhi = [
        g
        for g in ("Jupiter", "Venus", "Mercury")
        if (chart.grahas[g].sign - moon) % 12 + 1 in (6, 7, 8)
    ]
    if len(adhi) >= 2:
        out.append(Yoga("Adhi Yoga", "lunar", f"benefics in 6/7/8 from Moon: {'+'.join(adhi)}"))
    jup = (moon - chart.grahas["Jupiter"].sign) % 12 + 1
    if jup in (6, 8, 12):
        out.append(Yoga("Shakata Yoga", "lunar", f"Moon in house {jup} from Jupiter"))
    return out


def solar_yogas(chart: Chart) -> list[Yoga]:
    out = []
    sun = chart.grahas["Sun"].sign
    ignore = {"Sun", "Moon"}
    second = [g for g in SEVEN if g not in ignore and chart.grahas[g].sign == (sun + 1) % 12]
    twelfth = [g for g in SEVEN if g not in ignore and chart.grahas[g].sign == (sun - 1) % 12]
    if second and twelfth:
        out.append(Yoga("Ubhayachari Yoga", "solar", f"{'+'.join(second)} / {'+'.join(twelfth)}"))
    elif second:
        out.append(Yoga("Vesi Yoga", "solar", f"2nd from Sun: {'+'.join(second)}"))
    elif twelfth:
        out.append(Yoga("Vasi Yoga", "solar", f"12th from Sun: {'+'.join(twelfth)}"))
    if _conjunct(chart, "Sun", "Mercury") and not chart.combust("Mercury"):
        out.append(Yoga("Budha-Aditya Yoga", "solar", "Sun with Mercury, Mercury not combust"))
    return out


# --- exchanges and doshas ---------------------------------------------------


def parivartana(chart: Chart) -> list[Yoga]:
    """Mutual exchange of signs, graded by the houses involved."""
    out = []
    for a, b in combinations(SEVEN, 2):
        if chart.grahas[a].sign in OWN_SIGNS.get(b, []) and chart.grahas[b].sign in OWN_SIGNS.get(
            a, []
        ):
            ha, hb = chart.house(a), chart.house(b)
            if ha in DUSTHANA or hb in DUSTHANA:
                kind = (
                    "Dainya Parivartana"
                    if 6 in (ha, hb) or 8 in (ha, hb) or 12 in (ha, hb)
                    else "Khala Parivartana"
                )
            elif 3 in (ha, hb):
                kind = "Khala Parivartana"
            else:
                kind = "Maha Parivartana"
            out.append(Yoga(kind, "exchange", f"{a} (house {ha}) exchanges with {b} (house {hb})"))
    return out


def doshas(chart: Chart) -> list[Yoga]:
    out = []
    mars_house = chart.house("Mars")
    if mars_house in (1, 2, 4, 7, 8, 12):
        out.append(
            Yoga("Kuja Dosha (Mangal)", "dosha", f"Mars in house {mars_house} from the lagna")
        )
    from_moon = (chart.grahas["Mars"].sign - chart.grahas["Moon"].sign) % 12 + 1
    if from_moon in (1, 2, 4, 7, 8, 12):
        out.append(
            Yoga("Kuja Dosha from the Moon", "dosha", f"Mars in house {from_moon} from the Moon")
        )

    rahu = chart.grahas["Rahu"].longitude
    ketu = chart.grahas["Ketu"].longitude
    arc = (ketu - rahu) % 360
    inside = all(((chart.grahas[g].longitude - rahu) % 360) < arc for g in SEVEN)
    outside = all(((chart.grahas[g].longitude - rahu) % 360) > arc for g in SEVEN)
    if inside or outside:
        out.append(
            Yoga("Kala Sarpa Yoga", "dosha", "every graha falls on one side of the nodal axis")
        )
    return out


def amala_saraswati_lakshmi(chart: Chart) -> list[Yoga]:
    out = []
    tenth_from_lagna = chart.occupants(10)
    tenth_from_moon = [
        g for g in SEVEN if (chart.grahas[g].sign - chart.grahas["Moon"].sign) % 12 + 1 == 10
    ]
    for where, occ in (("lagna", tenth_from_lagna), ("Moon", tenth_from_moon)):
        good = [g for g in occ if g in NATURAL_BENEFICS]
        if good:
            out.append(
                Yoga("Amala Yoga", "auspicious", f"{'+'.join(good)} in the 10th from the {where}")
            )
    trio = ("Mercury", "Jupiter", "Venus")
    if all(chart.house(g) in KENDRA + TRIKONA + (2,) for g in trio):
        out.append(
            Yoga(
                "Saraswati Yoga",
                "auspicious",
                "Mercury, Jupiter and Venus all in kendra, trikona or the 2nd",
            )
        )
    ninth_lord = chart.lord(9)
    lagna_lord = chart.lord(1)
    if (
        chart.dignity(ninth_lord) in ("exalted", "own", "moolatrikona")
        and chart.house(ninth_lord) in KENDRA + TRIKONA
        and chart.dignity(lagna_lord)
        in ("exalted", "own", "moolatrikona", "great friend", "friend")
    ):
        out.append(
            Yoga("Lakshmi Yoga", "auspicious", f"9th lord {ninth_lord} dignified and angular")
        )
    return out


# --- nabhasa ----------------------------------------------------------------

SANKHYA = {1: "Gola", 2: "Yuga", 3: "Shoola", 4: "Kedara", 5: "Pasha", 6: "Damini", 7: "Veena"}


def nabhasa(chart: Chart) -> list[Yoga]:
    out = []
    signs = {chart.grahas[g].sign for g in SEVEN}
    houses = {chart.house(g) for g in SEVEN}
    n = len(signs)
    if n in SANKHYA:
        out.append(
            Yoga(
                f"{SANKHYA[n]} Yoga",
                "nabhasa/sankhya",
                f"the seven grahas occupy {n} sign{'' if n == 1 else 's'}",
            )
        )

    mods = {s % 3 for s in signs}
    if len(mods) == 1:
        name = {0: "Rajju", 1: "Musala", 2: "Nala"}[mods.pop()]
        out.append(Yoga(f"{name} Yoga", "nabhasa/ashraya", "all grahas in one modality"))

    ben_h = {chart.house(g) for g in _benefics(chart)}
    mal_h = {chart.house(g) for g in _malefics(chart)}
    if ben_h and ben_h <= set(KENDRA) and not (mal_h & set(KENDRA)):
        out.append(Yoga("Mala (Srak) Yoga", "nabhasa/dala", "benefics hold the kendras alone"))
    if mal_h and mal_h <= set(KENDRA) and not (ben_h & set(KENDRA)):
        out.append(Yoga("Sarpa Yoga", "nabhasa/dala", "malefics hold the kendras alone"))

    akriti = [
        ("Kamala", houses <= set(KENDRA)),
        ("Shringataka", houses <= set(TRIKONA)),
        ("Shakata", houses <= {1, 7}),
        ("Vihaga", houses <= {4, 10}),
        ("Hala", houses <= {2, 6, 10} or houses <= {3, 7, 11} or houses <= {4, 8, 12}),
        ("Vapi", houses <= {2, 5, 8, 11} or houses <= {3, 6, 9, 12}),
        ("Yupa", houses <= {1, 2, 3, 4}),
        ("Shara", houses <= {4, 5, 6, 7}),
        ("Shakti", houses <= {7, 8, 9, 10}),
        ("Danda", houses <= {10, 11, 12, 1}),
        ("Nauka", houses <= {1, 2, 3, 4, 5, 6, 7}),
        ("Kuta", houses <= {4, 5, 6, 7, 8, 9, 10}),
        ("Chhatra", houses <= {7, 8, 9, 10, 11, 12, 1}),
        ("Chapa", houses <= {10, 11, 12, 1, 2, 3, 4}),
        ("Chakra", houses <= {1, 3, 5, 7, 9, 11}),
        ("Samudra", houses <= {2, 4, 6, 8, 10, 12}),
    ]
    for name, cond in akriti:
        if cond:
            out.append(
                Yoga(
                    f"{name} Yoga", "nabhasa/akriti", f"grahas confined to houses {sorted(houses)}"
                )
            )
    return out


def all_yogas(chart: Chart) -> list[Yoga]:
    out = []
    for fn in (
        mahapurusha,
        raja_yogas,
        dhana_yogas,
        vipareeta_raja,
        neecha_bhanga,
        lunar_yogas,
        solar_yogas,
        parivartana,
        doshas,
        amala_saraswati_lakshmi,
        nabhasa,
    ):
        out.extend(fn(chart))
    return out


def report(chart: Chart) -> str:
    ys = all_yogas(chart)
    if not ys:
        return "  no yogas detected"
    lines = []
    for cat in sorted({y.category for y in ys}):
        lines.append(f"-- {cat}")
        for y in ys:
            if y.category == cat:
                lines.append(f"   {y.name:32s} {y.detail}")
    lines.append("")
    lines.append(f"  {len(ys)} yogas detected across {len({y.category for y in ys})} categories")
    return "\n".join(lines)
