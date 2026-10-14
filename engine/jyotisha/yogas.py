"""Yoga detection.

Every yoga is checked against a public-domain printing; SOURCES gives the
text, verse, edition and printed page:

  PD    Mantresvara, Phaladipika, tr. V. Subrahmanya Sastri, 1937
  BJ    Varahamihira, Brihat Jataka, tr. Swami Vijnanananda, 1912
  BPHS  Brihat Parasara Hora Sastra, with Devachandra Jha's commentary, 1939

Yogas that none of these (nor Jataka Parijata or Saravali) defines carry
source=None and are reported as modern usage: Budha-Aditya, Chandra-Mangala
and Kala Sarpa.

Each detector returns a Yoga with the reason it fired, so a claim can be
audited rather than taken on trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .chart import EXALTATION, OWN_SIGNS, SIGN_LORDS, Chart
from .ephemeris import SEVEN, SIGNS

KENDRA = (1, 4, 7, 10)
TRIKONA = (1, 5, 9)
DUSTHANA = (6, 8, 12)
# The benefics PD 6.19 (Amala) means and BJ 13.2 (Adhi) names: Mercury, Jupiter, Venus.
NATURAL_BENEFICS = ("Mercury", "Jupiter", "Venus")

PD = ("Phaladipika", "Mantresvara, tr. V. Subrahmanya Sastri, 1937")
BJ = ("Brihat Jataka", "Varahamihira, tr. Swami Vijnanananda, 1912")
BPHS = ("Brihat Parasara Hora Sastra", "with Devachandra Jha's Vimarsa-sudha, 1939")


def _src(book: tuple[str, str], verse: str, page: str) -> dict:
    return {"text": book[0], "verse": verse, "edition": book[1], "page": page}


SOURCES = {
    "mahapurusha_lagna": _src(PD, "6.1", "47"),
    "mahapurusha_moon": _src(PD, "6.4", "48"),
    "mahapurusha_bphs": _src(BPHS, "75.1-2", "584"),
    "chandra": _src(PD, "6.5", "48"),  # BJ 13.3, p. 225 agrees
    "gaja_kesari": _src(PD, "6.14", "52"),
    "gaja_kesari_bphs": _src(BPHS, "Bahuvidha-yoga 3", "211"),
    "shakata": _src(PD, "6.14", "52"),
    "adhi_moon": _src(BJ, "13.2", "224"),  # PD 6.42 agrees
    "adhi_lagna": _src(PD, "6.42", "63"),
    "solar": _src(PD, "6.8", "50"),
    "parivartana": _src(PD, "6.33", "59"),
    "amala": _src(PD, "6.19", "54"),  # BPHS Bahuvidha-yoga 5 agrees
    "saraswati": _src(PD, "6.26", "56"),
    "lakshmi": _src(BPHS, "Bahuvidha-yoga 27", "214"),
    "lakshmi_pd": _src(PD, "6.24", "55"),
    "vipareeta": _src(PD, "6.57", "68"),
    "neecha_bhanga": _src(PD, "7.27-30", "81-82"),
    "raja": _src(BPHS, "Yogakaraka 11-15", "198-199"),
    "nabhasa_ashraya": _src(BJ, "12.2, 12.12", "205, 213"),
    "nabhasa_dala": _src(BJ, "12.2", "205"),
    "nabhasa_akriti": _src(BJ, "12.4-9", "207-211"),
    "nabhasa_sankhya": _src(BJ, "12.10", "212"),
}


@dataclass
class Yoga:
    name: str
    category: str
    detail: str
    strength: float = 1.0
    source: str | None = None  # key into SOURCES; None: no classical source found
    reckoned_from: str | None = None  # "lagna" or "moon", where a text counts from either
    grahas: tuple[str, ...] = ()  # the grahas that form it, when not every one named in detail
    notes: tuple[str, ...] = ()
    # Another text's version of the same yoga and whether it also holds: {"bphs": True}.
    variants: dict[str, bool] = field(default_factory=dict)
    # Conditions a text mentions without applying, and whether each holds (None: unknown).
    checks: tuple[tuple[str, bool | None], ...] = ()
    reads_lagna: bool = True  # False: holds on sign positions alone, without the birth time

    def __str__(self) -> str:
        return f"{self.name:32s} {self.category:16s} {self.detail}"


class Strength:
    """Shadbala against BPHS's required rupas, computed once per chart and only
    when a yoga asks. "Strong" (BPHS sabala) as rupas >= the required minimum is
    our reading; every yoga that uses it carries the note strength_our_reading_of_bphs."""

    def __init__(self, chart: Chart):
        self.chart = chart
        self._balas = None

    def strong(self, g: str) -> bool:
        if self._balas is None:
            from .strength import shadbala

            self._balas = shadbala(self.chart)
        return self._balas[g].ratio >= 1.0


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


def _in_signs_of(chart: Chart, a: str, b: str) -> bool:
    """a stands in a sign that b owns."""
    return chart.grahas[a].sign in OWN_SIGNS.get(b, [])


def _from(chart: Chart, g: str, sign: int) -> int:
    """House of g counted from the sign `sign` (1..12)."""
    return (chart.grahas[g].sign - sign) % 12 + 1


def _own_or_exalted(chart: Chart, g: str) -> str | None:
    sign = chart.grahas[g].sign
    if sign == EXALTATION[g][0]:
        return "exalted"
    if sign in OWN_SIGNS.get(g, []):
        return "own sign"
    return None


# --- pancha mahapurusha -----------------------------------------------------

MAHAPURUSHA = {
    "Mars": "Ruchaka",
    "Mercury": "Bhadra",
    "Jupiter": "Hamsa",
    "Venus": "Malavya",
    "Saturn": "Sasa",
}


def mahapurusha(chart: Chart, strength: Strength | None = None, lagna_known: bool = True):
    """PD 6.1: Mars to Saturn, each "occupies a Kendra identical with its
    Swakshetra or Swochcha"; PD 6.4: "similarly ... counted even from the Moon's
    place". BPHS 75.1-2 adds sabalaih ("strong"), reported as the bphs variant
    of the lagna form."""
    strength = strength or Strength(chart)
    moon = chart.grahas["Moon"].sign
    out = []
    for g, name in MAHAPURUSHA.items():
        d = _own_or_exalted(chart, g)
        if d is None:
            continue
        h = chart.house(g)
        if lagna_known and h in KENDRA:
            out.append(
                Yoga(
                    f"{name} Yoga", "mahapurusha", f"{g} {d} in house {h}",
                    source="mahapurusha_lagna", reckoned_from="lagna", grahas=(g,),
                    notes=("strength_our_reading_of_bphs",),
                    variants={"bphs": strength.strong(g)},
                )
            )  # fmt: skip
        m = _from(chart, g, moon)
        if m in KENDRA:
            out.append(
                Yoga(
                    f"{name} Yoga", "mahapurusha", f"{g} {d} in house {m} from the Moon",
                    source="mahapurusha_moon", reckoned_from="moon", grahas=(g,),
                    reads_lagna=False,
                )
            )  # fmt: skip
    return out


# --- raja and dhana ---------------------------------------------------------


def _raja_link(chart: Chart, a: str, b: str) -> str | None:
    """BPHS Yogakaraka vv. 11-12: a kendra lord and a trikona lord form the yoga
    if each is in the other's sign, both are in one sign, one is in the other's
    sign and aspected by it, or each fully aspects the other."""
    if a == b:
        return None
    if _in_signs_of(chart, a, b) and _in_signs_of(chart, b, a):
        return "exchange"
    if _conjunct(chart, a, b):
        return "conjunct"
    for x, y in ((a, b), (b, a)):
        if _in_signs_of(chart, x, y) and chart.aspects_sign(y, chart.grahas[x].sign):
            return f"{x} in {y}'s sign, aspected by {y}"
    if _mutual_aspect(chart, a, b):
        return "mutual aspect"
    return None


# BPHS Yogakaraka v.4 "patayas trisadayanam sada papaphalapradah"; Jha's gloss on
# vv. 13-17 (p. 199) names v.15's krura-sthanas as the 3rd, 6th and 11th.
KRURA = {3, 6, 11}


def raja_yogas(chart: Chart) -> list[Yoga]:
    """A kendra lord linked to a trikona lord (BPHS Yogakaraka vv. 11-12), or one
    graha ruling both (v.13). The 9th and 10th lords together are the strongest.
    v.15: no yoga from the link alone when both lords also rule a krura house."""
    out = []
    kendra_lords = {chart.lord(h): h for h in KENDRA}
    trikona_lords = {chart.lord(h): h for h in TRIKONA}
    for a, ha in kendra_lords.items():
        for b, hb in trikona_lords.items():
            if a == b:
                if ha != hb:
                    out.append(
                        Yoga(
                            "Raja Yoga (single lord)", "raja",
                            f"{a} rules kendra {ha} and trikona {hb}", source="raja",
                        )
                    )  # fmt: skip
                continue
            if KRURA & set(chart.houses_ruled(a)) and KRURA & set(chart.houses_ruled(b)):
                continue
            link = _raja_link(chart, a, b)
            if link:
                strong = 1.5 if {ha, hb} == {10, 9} else 1.0
                out.append(
                    Yoga(
                        "Raja Yoga", "raja", f"{a} (kendra {ha}) {link} {b} (trikona {hb})",
                        strong, source="raja", grahas=(a, b),
                    )
                )  # fmt: skip
    return out


# BPHS 42.2-8 (p. 228): the 5th house in a graha's own sign with that graha in
# it, and the named grahas in the 11th. (verse, graha, grahas in the 11th)
DHANA_FIFTH = [
    (2, "Venus", ("Mars",)),
    (3, "Mercury", ("Moon", "Mars", "Jupiter")),
    (4, "Sun", ("Saturn", "Moon", "Jupiter")),
    (5, "Saturn", ("Sun", "Moon")),
    (6, "Jupiter", ("Mercury",)),
    (7, "Mars", ("Venus",)),
    (8, "Moon", ("Saturn",)),
]
# BPHS 42.9-15 (pp. 228-229): the lagna in a graha's own sign with that graha in
# it, "joined or aspected" by the named grahas. (verse, graha, joining grahas)
DHANA_LAGNA = [
    (9, "Sun", ("Mars", "Jupiter")),
    (10, "Moon", ("Jupiter", "Mercury")),
    (11, "Mars", ("Mercury", "Venus", "Saturn")),
    (12, "Mercury", ("Jupiter", "Saturn")),
    (13, "Jupiter", ("Mercury", "Mars")),
    (14, "Venus", ("Mercury", "Saturn")),
    (15, "Saturn", ("Mars", "Jupiter")),
]
for _v, *_ in DHANA_FIFTH + DHANA_LAGNA:
    SOURCES[f"dhana_{_v}"] = _src(BPHS, f"42.{_v}", "228" if _v <= 8 else "228-229")


def dhana_yogas(chart: Chart) -> list[Yoga]:
    """BPHS ch. 42's fourteen wealth combinations. Our reading: in the first
    group every named graha is in the 11th; in the second every named graha is
    in the lagna or aspects it."""
    out = []
    for verse, lord, eleventh in DHANA_FIFTH:
        if chart.house(lord) == 5 and chart.house_sign(5) in OWN_SIGNS[lord]:
            if all(chart.house(g) == 11 for g in eleventh):
                out.append(
                    Yoga(
                        "Dhana Yoga", "dhana",
                        f"{lord} in the 5th, its own sign {SIGNS[chart.house_sign(5)]}; "
                        f"{'+'.join(eleventh)} in the 11th",
                        source=f"dhana_{verse}", grahas=(lord, *eleventh),
                        notes=("bphs_42_our_reading",),
                    )
                )  # fmt: skip
    lagna = chart.house_sign(1)
    for verse, lord, joined in DHANA_LAGNA:
        if chart.house(lord) == 1 and lagna in OWN_SIGNS[lord]:
            if all(chart.house(g) == 1 or chart.aspects_sign(g, lagna) for g in joined):
                out.append(
                    Yoga(
                        "Dhana Yoga", "dhana",
                        f"{lord} in the lagna, its own sign {SIGNS[lagna]}; joined or aspected by "
                        f"{'+'.join(joined)}",
                        source=f"dhana_{verse}", grahas=(lord, *joined),
                        notes=("bphs_42_our_reading",),
                    )
                )  # fmt: skip
    return out


def vipareeta_raja(chart: Chart) -> list[Yoga]:
    """PD 6.57: the lord of the 6th, 8th or 12th in a dusthana gives Harsha,
    Sarala or Vimala."""
    names = {6: "Harsha", 8: "Sarala", 12: "Vimala"}
    out = []
    for h, name in names.items():
        lord = chart.lord(h)
        where = chart.house(lord)
        if where in DUSTHANA:
            out.append(
                Yoga(
                    f"{name} Yoga", "vipareeta", f"lord of {h} ({lord}) in house {where}",
                    source="vipareeta",
                )
            )  # fmt: skip
    return out


def neecha_bhanga(chart: Chart) -> list[Yoga]:
    """Cancellation of debilitation, PD 7.27-30:
    7.27 the lord of the debilitation sign and the lord of the exaltation sign
         in kendras from each other;
    7.28 the debilitated graha aspected by the lord of its sign;
    7.29-30 either lord in a kendra from the lagna or the Moon."""
    out = []
    moon = chart.grahas["Moon"].sign
    for g in SEVEN:
        if chart.dignity(g) != "debilitated":
            continue
        sign = chart.grahas[g].sign
        dispositor = SIGN_LORDS[sign]
        exalt_lord = SIGN_LORDS[(sign + 6) % 12]
        reasons, lords = [], []
        if _from(chart, exalt_lord, chart.grahas[dispositor].sign) in KENDRA:
            reasons.append(f"{dispositor} and {exalt_lord} in kendras from each other (7.27)")
            lords += [dispositor, exalt_lord]
        if chart.aspects_sign(dispositor, sign):
            reasons.append(f"aspected by its dispositor {dispositor} (7.28)")
            lords.append(dispositor)
        for other in dict.fromkeys((dispositor, exalt_lord)):
            if chart.house(other) in KENDRA:
                reasons.append(f"{other} in a kendra from the lagna (7.29)")
                lords.append(other)
            if other != "Moon" and _from(chart, other, moon) in KENDRA:
                reasons.append(f"{other} in a kendra from the Moon (7.29)")
                lords.append(other)
        if reasons:
            out.append(
                Yoga(
                    "Neecha Bhanga Raja Yoga", "cancellation",
                    f"{g} debilitated in {SIGNS[sign]}; " + "; ".join(reasons),
                    source="neecha_bhanga", grahas=tuple(dict.fromkeys((g, *lords))),
                )
            )  # fmt: skip
    return out


# --- lunar and solar --------------------------------------------------------

# PD 6.5 "planets other than the Sun"; BJ 13.3 hitvarkam, "not taking the Sun".
CHANDRA_GRAHAS = ("Mars", "Mercury", "Jupiter", "Venus", "Saturn")


def _gaja_kesari_bphs(chart: Chart) -> bool:
    """BPHS Bahuvidha-yoga v.3: Jupiter in a kendra from the lagna or the Moon,
    joined or aspected by a benefic, and not debilitated, combust or in the sign
    of a (natural) enemy."""
    sign = chart.grahas["Jupiter"].sign
    helped = any(
        chart.is_benefic(g) and (chart.grahas[g].sign == sign or chart.aspects_sign(g, sign))
        for g in SEVEN
        if g != "Jupiter"
    )
    return (
        helped
        and chart.dignity("Jupiter") != "debilitated"
        and not chart.combust("Jupiter")
        and chart.natural_relation("Jupiter", SIGN_LORDS[sign]) != "enemy"
    )


def _adhi(chart: Chart, ref: int) -> list[str] | None:
    """Mercury, Jupiter and Venus all in the 6th, 7th or 8th from `ref`."""
    places = [g for g in NATURAL_BENEFICS if _from(chart, g, ref) in (6, 7, 8)]
    return places if len(places) == len(NATURAL_BENEFICS) else None


def lunar_yogas(chart: Chart, lagna_known: bool = True) -> list[Yoga]:
    out = []
    moon = chart.grahas["Moon"].sign
    second = [g for g in CHANDRA_GRAHAS if chart.grahas[g].sign == (moon + 1) % 12]
    twelfth = [g for g in CHANDRA_GRAHAS if chart.grahas[g].sign == (moon - 1) % 12]
    chandra = dict(source="chandra", reckoned_from="moon", reads_lagna=False)
    if second and twelfth:
        out.append(
            Yoga(
                "Durudhara Yoga", "lunar",
                f"2nd from Moon: {'+'.join(second)}; 12th: {'+'.join(twelfth)}", **chandra,
            )
        )  # fmt: skip
    elif second:
        out.append(Yoga("Sunapha Yoga", "lunar", f"2nd from Moon: {'+'.join(second)}", **chandra))
    elif twelfth:
        out.append(Yoga("Anapha Yoga", "lunar", f"12th from Moon: {'+'.join(twelfth)}", **chandra))
    else:
        # PD 6.5: "There are some who declare that there is no Kemadruma where [the
        # Moon is in] a Kendra or the Moon is associated with a planet, or where
        # planets occupy a Kendra house reckoned from the Moon." Each is reported
        # as holding or not (None: needs the birth time), never applied.
        others = [g for g in SEVEN if g != "Moon"]
        checks = (
            ("moon_in_kendra", chart.house("Moon") in KENDRA if lagna_known else None),
            ("planet_with_moon", any(chart.grahas[g].sign == moon for g in others)),
            (
                "planet_in_kendra_from_moon",
                any(_from(chart, g, moon) in (4, 7, 10) for g in others),
            ),
        )
        out.append(
            Yoga(
                "Kemadruma Yoga", "lunar",
                "no graha but the Sun in the 2nd or 12th from the Moon",
                grahas=("Moon",), checks=checks, **chandra,
            )
        )  # fmt: skip

    jup_from_moon = _from(chart, "Jupiter", moon)
    if jup_from_moon in KENDRA:  # PD 6.14: "The Moon in a Kendra position to Jupiter"
        out.append(
            Yoga(
                "Gaja Kesari Yoga", "lunar", f"Jupiter in house {jup_from_moon} from the Moon",
                source="gaja_kesari", reckoned_from="moon", reads_lagna=False,
                variants={"bphs": _gaja_kesari_bphs(chart)},
            )
        )  # fmt: skip
    if _conjunct(chart, "Moon", "Mars"):
        out.append(Yoga("Chandra-Mangala Yoga", "lunar", "Moon conjunct Mars", reads_lagna=False))

    # BJ 13.2: "the benefics Mercury, Jupiter, and Venus ... in the sixth, seventh and
    # eighth houses from the Moon"; PD 6.42 also counts from the lagna.
    adhi = _adhi(chart, moon)
    if adhi:
        out.append(
            Yoga(
                "Adhi Yoga", "lunar", f"{'+'.join(adhi)} in the 6th to 8th from the Moon",
                source="adhi_moon", reckoned_from="moon", reads_lagna=False,
            )
        )  # fmt: skip
    adhi = _adhi(chart, chart.house_sign(1))
    if adhi:
        out.append(
            Yoga(
                "Adhi Yoga", "lunar", f"{'+'.join(adhi)} in the 6th to 8th from the lagna",
                source="adhi_lagna", reckoned_from="lagna", grahas=tuple(adhi),
            )
        )  # fmt: skip

    # PD 6.14: "The Moon in the 12th, 8th or 6th house from Jupiter causes Sakata.
    # But if the Moon be in a Kendra house from the Lagna, there is no Sakata."
    jup = _from(chart, "Moon", chart.grahas["Jupiter"].sign)
    if jup in (6, 8, 12) and chart.house("Moon") not in KENDRA:
        out.append(
            Yoga(
                "Shakata Yoga", "lunar",
                f"Moon in house {jup} from Jupiter and not in a kendra from the lagna",
                source="shakata",
            )
        )  # fmt: skip
    return out


def solar_yogas(chart: Chart) -> list[Yoga]:
    """PD 6.8: grahas other than the Moon in the 2nd, 12th or both from the Sun."""
    out = []
    sun = chart.grahas["Sun"].sign
    ignore = {"Sun", "Moon"}
    second = [g for g in SEVEN if g not in ignore and chart.grahas[g].sign == (sun + 1) % 12]
    twelfth = [g for g in SEVEN if g not in ignore and chart.grahas[g].sign == (sun - 1) % 12]
    solar = dict(source="solar", reckoned_from=None, reads_lagna=False)
    if second and twelfth:
        out.append(
            Yoga("Ubhayachari Yoga", "solar", f"{'+'.join(second)} / {'+'.join(twelfth)}", **solar)
        )
    elif second:
        out.append(Yoga("Vesi Yoga", "solar", f"2nd from Sun: {'+'.join(second)}", **solar))
    elif twelfth:
        out.append(Yoga("Vasi Yoga", "solar", f"12th from Sun: {'+'.join(twelfth)}", **solar))
    if _conjunct(chart, "Sun", "Mercury") and not chart.combust("Mercury"):
        out.append(
            Yoga(
                "Budha-Aditya Yoga", "solar", "Sun with Mercury, Mercury not combust",
                reads_lagna=False,
            )
        )  # fmt: skip
    return out


# --- exchanges and doshas ---------------------------------------------------


def parivartana(chart: Chart) -> list[Yoga]:
    """PD 6.33: exchanges involving the 6th, 8th or 12th are Dainya, the 3rd
    Khala, the rest Maha."""
    out = []
    for a, b in combinations(SEVEN, 2):
        if _in_signs_of(chart, a, b) and _in_signs_of(chart, b, a):
            ha, hb = chart.house(a), chart.house(b)
            if ha in DUSTHANA or hb in DUSTHANA:
                kind = "Dainya Parivartana"
            elif 3 in (ha, hb):
                kind = "Khala Parivartana"
            else:
                kind = "Maha Parivartana"
            out.append(
                Yoga(
                    kind, "exchange", f"{a} (house {ha}) exchanges with {b} (house {hb})",
                    source="parivartana",
                )
            )  # fmt: skip
    return out


def doshas(chart: Chart) -> list[Yoga]:
    out = []
    mars_house = chart.house("Mars")
    if mars_house in (1, 2, 4, 7, 8, 12):
        out.append(
            Yoga("Kuja Dosha (Mangal)", "dosha", f"Mars in house {mars_house} from the lagna")
        )
    from_moon = _from(chart, "Mars", chart.grahas["Moon"].sign)
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
            Yoga(
                "Kala Sarpa Yoga", "dosha", "every graha falls on one side of the nodal axis",
                reads_lagna=False,
            )
        )  # fmt: skip
    return out


def amala_saraswati_lakshmi(
    chart: Chart, strength: Strength | None = None, lagna_known: bool = True
) -> list[Yoga]:
    strength = strength or Strength(chart)
    out = []
    # PD 6.19: "benefics occupy the 10th house counted from the Lagna or the Moon".
    for where, ref in (("lagna", chart.house_sign(1)), ("moon", chart.grahas["Moon"].sign)):
        good = [g for g in NATURAL_BENEFICS if _from(chart, g, ref) == 10]
        if good:
            out.append(
                Yoga(
                    "Amala Yoga", "auspicious",
                    f"{'+'.join(good)} in the 10th from the {'Moon' if where == 'moon' else where}",
                    source="amala", reckoned_from=where, grahas=tuple(good),
                    reads_lagna=where == "lagna",
                )
            )  # fmt: skip
    if not lagna_known:
        return out

    # PD 6.26: Venus, Jupiter and Mercury in a kendra, a trikona or the 2nd, "and
    # Jupiter be also in his exaltation, his own or a friendly house and possess
    # strength". Friendly: a natural friend's sign.
    trio = ("Mercury", "Jupiter", "Venus")
    jup_sign = chart.grahas["Jupiter"].sign
    jup_placed = _own_or_exalted(chart, "Jupiter") or (
        chart.natural_relation("Jupiter", SIGN_LORDS[jup_sign]) == "friend"
    )
    if (
        all(chart.house(g) in KENDRA + TRIKONA + (2,) for g in trio)
        and jup_placed
        and strength.strong("Jupiter")
    ):
        out.append(
            Yoga(
                "Saraswati Yoga", "auspicious",
                "Mercury, Jupiter and Venus in kendra, trikona or the 2nd; Jupiter "
                f"in {SIGNS[jup_sign]} and strong",
                source="saraswati", notes=("strength_our_reading_of_bphs",),
            )
        )  # fmt: skip

    # BPHS Bahuvidha-yoga v.27: a strong lagna lord, and the 9th lord in its own
    # sign, exaltation or moolatrikona in a kendra. PD 6.24 instead wants the 9th
    # lord and Venus in own or exaltation signs that are kendras or trikonas.
    ninth, first = chart.lord(9), chart.lord(1)
    h9 = chart.house(ninth)
    if (
        chart.dignity(ninth) in ("exalted", "own", "moolatrikona")
        and h9 in KENDRA
        and strength.strong(first)
    ):
        pd = all(
            _own_or_exalted(chart, g) and chart.house(g) in KENDRA + TRIKONA
            for g in (ninth, "Venus")
        )
        out.append(
            Yoga(
                "Lakshmi Yoga", "auspicious",
                f"9th lord {ninth} {chart.dignity(ninth)} in house {h9}; lagna lord {first} strong",
                source="lakshmi", grahas=tuple(dict.fromkeys((ninth, first))),
                notes=("strength_our_reading_of_bphs",), variants={"phaladipika": pd},
            )
        )  # fmt: skip
    return out


# --- nabhasa (BJ ch. 12) ----------------------------------------------------

SANKHYA = {1: "Gola", 2: "Yuga", 3: "Shoola", 4: "Kedara", 5: "Pasha", 6: "Damini", 7: "Veena"}
DALA_MALEFICS = ("Sun", "Mars", "Saturn")
ASHRAYA = {0: "Rajju", 1: "Musala", 2: "Nala"}  # movable, fixed, dual signs


def _run(start: int, n: int) -> set[int]:
    return {(start - 1 + i) % 12 + 1 for i in range(n)}


# BJ 12.4-9: the planets fill exactly these houses (every named house occupied,
# none elsewhere), so a chart with all seven in the 1st and 7th is Shakata, not
# also Kamala.
AKRITI = [
    ("Gada", [{1, 4}, {4, 7}, {7, 10}, {10, 1}]),
    ("Shakata", [{1, 7}]),
    ("Vihaga", [{4, 10}]),
    ("Shringataka", [{1, 5, 9}]),
    ("Hala", [{2, 6, 10}, {3, 7, 11}, {4, 8, 12}]),
    ("Kamala", [set(KENDRA)]),
    ("Vapi", [{2, 5, 8, 11}, {3, 6, 9, 12}]),
    ("Yupa", [_run(1, 4)]),
    ("Shara", [_run(4, 4)]),
    ("Shakti", [_run(7, 4)]),
    ("Danda", [_run(10, 4)]),
    ("Nauka", [_run(1, 7)]),
    ("Kuta", [_run(4, 7)]),
    ("Chhatra", [_run(7, 7)]),
    ("Chapa", [_run(10, 7)]),
    ("Ardhachandra", [_run(s, 7) for s in (2, 3, 5, 6, 8, 9, 11, 12)]),
    ("Chakra", [{1, 3, 5, 7, 9, 11}]),
    ("Samudra", [{2, 4, 6, 8, 10, 12}]),
]


def nabhasa(chart: Chart) -> list[Yoga]:
    houses = {chart.house(g) for g in SEVEN}
    ben_h = {chart.house(g) for g in _benefics(chart)}
    mal_h = {chart.house(g) for g in _malefics(chart)}
    occupied = f"grahas fill houses {sorted(houses)}"

    akriti = [
        Yoga(f"{name} Yoga", "nabhasa/akriti", occupied, source="nabhasa_akriti")
        for name, shapes in AKRITI
        if houses in shapes
    ]
    # BJ: Vajra, benefics in the 1st and 7th and malefics in the 4th and 10th; Yava the reverse.
    for name, ben, mal in (("Vajra", {1, 7}, {4, 10}), ("Yava", {4, 10}, {1, 7})):
        if ben_h == ben and mal_h == mal:
            akriti.append(
                Yoga(
                    f"{name} Yoga", "nabhasa/akriti",
                    f"benefics in houses {sorted(ben)}, malefics in {sorted(mal)}",
                    source="nabhasa_akriti",
                )
            )  # fmt: skip

    # BJ 12.2 with the translator's note (pp. 205-206): Srak when Mercury, Jupiter
    # and Venus are in any three kendras, Sarpa when the Sun, Mars and Saturn are.
    dala = []
    for name, trio in (("Mala (Srak)", ("Mercury", "Jupiter", "Venus")), ("Sarpa", DALA_MALEFICS)):
        places = {chart.house(g) for g in trio}
        if places <= set(KENDRA) and len(places) == 3:
            dala.append(
                Yoga(
                    f"{name} Yoga", "nabhasa/dala",
                    f"{', '.join(trio)} in houses {sorted(places)}",
                    source="nabhasa_dala", grahas=trio,
                )
            )  # fmt: skip

    # BJ 12.2 and 12.12: Rajju, Musala, Nala give way to any akriti yoga.
    ashraya = []
    mods = {chart.grahas[g].sign % 3 for g in SEVEN}
    if len(mods) == 1 and not akriti:
        name = ASHRAYA[mods.pop()]
        ashraya.append(
            Yoga(
                f"{name} Yoga", "nabhasa/ashraya", "all grahas in one modality",
                source="nabhasa_ashraya",
            )
        )  # fmt: skip

    out = ashraya + dala + akriti
    if not out:
        # BJ 12.10: the sankhya yogas apply only when no other nabhasa yoga does.
        n = len({chart.grahas[g].sign for g in SEVEN})
        out.append(
            Yoga(
                f"{SANKHYA[n]} Yoga", "nabhasa/sankhya",
                f"the seven grahas occupy {n} sign{'' if n == 1 else 's'}",
                source="nabhasa_sankhya",
            )
        )  # fmt: skip
    return out


def all_yogas(chart: Chart, lagna_known: bool = True) -> list[Yoga]:
    """Every yoga that holds. With lagna_known=False (birth time unknown) only
    those that hold on sign positions alone are returned."""
    strength = Strength(chart)
    out = [
        *mahapurusha(chart, strength, lagna_known),
        *raja_yogas(chart),
        *dhana_yogas(chart),
        *vipareeta_raja(chart),
        *neecha_bhanga(chart),
        *lunar_yogas(chart, lagna_known),
        *solar_yogas(chart),
        *parivartana(chart),
        *doshas(chart),
        *amala_saraswati_lakshmi(chart, strength, lagna_known),
        *nabhasa(chart),
    ]
    return out if lagna_known else [y for y in out if not y.reads_lagna]


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
