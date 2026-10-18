"""The Chart object: birth data in, a fully derived Parashari chart out.

Nothing here is specific to one nativity.  A Chart can be a natal chart, a
transit snapshot, a varga, a solar return or a prashna -- they differ only in
the moment and place handed to the constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ephemeris import (
    GRAHAS,
    NAKSHATRAS,
    SIGNS,
    Position,
    TimeZone,
    ascendant,
    positions,
)
from .vargas import varga

SIGN_LORDS = [
    "Mars",
    "Venus",
    "Mercury",
    "Moon",
    "Sun",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Saturn",
    "Jupiter",
]
OWN_SIGNS = {
    "Sun": [4],
    "Moon": [3],
    "Mars": [0, 7],
    "Mercury": [2, 5],
    "Jupiter": [8, 11],
    "Venus": [1, 6],
    "Saturn": [9, 10],
    "Rahu": [],
    "Ketu": [],
}
# (sign, exact degree): BPHS (1933) PK 2.46-48, p. 7. The nodes' 20 degrees are not in it:
# our reading.
EXALTATION = {
    "Sun": (0, 10),
    "Moon": (1, 3),
    "Mars": (9, 28),
    "Mercury": (5, 15),
    "Jupiter": (3, 5),
    "Venus": (11, 27),
    "Saturn": (6, 20),
    "Rahu": (1, 20),
    "Ketu": (7, 20),
}
DEBILITATION = {n: ((s + 6) % 12, d) for n, (s, d) in EXALTATION.items()}
# (sign, from_degree, to_degree): BPHS (1933) PK 2.49-52, p. 7.
MOOLATRIKONA = {
    "Sun": (4, 0, 20),
    "Moon": (1, 3, 30),
    "Mars": (0, 0, 12),
    "Mercury": (5, 15, 20),
    "Jupiter": (8, 0, 10),
    "Venus": (6, 0, 15),
    "Saturn": (10, 0, 20),
}
# BPHS (1933) PK 2.49-51, p. 7: in its exaltation sign the Moon is exalted only to 3 degrees and
# Mercury to 15; the rest is mulatrikona (for Mercury, then own sign from 20).
EXALTED_TO = {"Moon": 3.0, "Mercury": 15.0}
# Rahu and Ketu exalted in Taurus and Scorpio: BPHS (1933) PK 36.35, p. 261. Mulatrikona
# in Gemini and Sagittarius, own signs Aquarius and Scorpio ("some": Virgo and Pisces):
# BPHS (1990) Dasa-phala vv. 35-36 (p. 329). Their debilitation as the
# 7th from exaltation is our reading.
NODE_SIGNS = {
    "Rahu": {"exalted": 1, "debilitated": 7, "moolatrikona": 2, "own": 10},
    "Ketu": {"exalted": 7, "debilitated": 1, "moolatrikona": 8, "own": 7},
}
NODE_OWN_BY_SOME = {"Rahu": 5, "Ketu": 11}
NATURAL_FRIENDS = {
    "Sun": ({"Moon", "Mars", "Jupiter"}, {"Mercury"}),
    "Moon": ({"Sun", "Mercury"}, {"Mars", "Jupiter", "Venus", "Saturn"}),
    "Mars": ({"Sun", "Moon", "Jupiter"}, {"Venus", "Saturn"}),
    "Mercury": ({"Sun", "Venus"}, {"Mars", "Jupiter", "Saturn"}),
    "Jupiter": ({"Sun", "Moon", "Mars"}, {"Saturn"}),
    "Venus": ({"Mercury", "Saturn"}, {"Mars", "Jupiter"}),
    "Saturn": ({"Mercury", "Venus"}, {"Jupiter"}),
}
BENEFICS = {"Jupiter", "Venus"}  # Mercury and Moon are conditional
MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

# Special graha drishti beyond the universal 7th.
# Bṛhaj-jātaka 2.13, pp. 48-49: every graha aspects the 7th; Saturn also the 3rd and
# 10th, Jupiter the 5th and 9th, Mars the 4th and 8th, all fully. BJ 2.13 and JP
# 2.30-31 name no aspect for Rahu or Ketu, so they have none here.
SPECIAL_ASPECTS = {
    "Mars": [4, 8],
    "Jupiter": [5, 9],
    "Saturn": [3, 10],
}
NO_ASPECTS = {"Rahu", "Ketu"}

COMBUSTION_ORB = {"Moon": 12, "Mars": 17, "Mercury": 14, "Jupiter": 11, "Venus": 10, "Saturn": 15}
COMBUSTION_ORB_RETRO = {"Mercury": 12, "Venus": 8}

KENDRA, PANAPHARA, APOKLIMA = (1, 4, 7, 10), (2, 5, 8, 11), (3, 6, 9, 12)
TRIKONA, DUSTHANA, UPACHAYA = (1, 5, 9), (6, 8, 12), (3, 6, 10, 11)


@dataclass
class Chart:
    jd: float
    lat: float
    lon: float
    tz: TimeZone = 0.0
    ayanamsa: str = "lahiri"
    node: str = "true"
    label: str = ""
    division: int = 1
    grahas: dict[str, Position] = field(default_factory=dict)
    asc: Position = None  # type: ignore[assignment]
    cusps: list[float] = field(default_factory=list)

    def __post_init__(self):
        if self.division < 1:
            raise ValueError("chart division must be positive")
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude must be in [-90, 90]")
        if not -180 <= self.lon <= 180:
            raise ValueError("longitude must be in [-180, 180]")
        if not self.grahas:
            self.grahas = positions(self.jd, self.ayanamsa, self.node)
            self.asc, self.cusps = ascendant(self.jd, self.lat, self.lon, self.ayanamsa)

    # --- houses -------------------------------------------------------------

    def house(self, name: str) -> int:
        """Whole-sign house occupied by a graha (or 'Ascendant')."""
        body = self.asc if name == "Ascendant" else self.grahas[name]
        return (body.sign - self.asc.sign) % 12 + 1

    def house_sign(self, house: int) -> int:
        return (self.asc.sign + house - 1) % 12

    def house_of_sign(self, sign: int) -> int:
        return (sign - self.asc.sign) % 12 + 1

    def lord(self, house: int) -> str:
        return SIGN_LORDS[self.house_sign(house)]

    def houses_ruled(self, name: str) -> list[int]:
        return sorted(self.house_of_sign(s) for s in OWN_SIGNS.get(name, []))

    def occupants(self, house: int) -> list[str]:
        sign = self.house_sign(house)
        return [g for g in GRAHAS if self.grahas[g].sign == sign]

    # --- dignity ------------------------------------------------------------

    def dignity(self, name: str) -> str | None:
        """Exalted, debilitated, moolatrikona, own, or the compound relation to
        the sign's lord. Rahu and Ketu have no natural friendships (BPHS (1933)
        PK 2.53-58 and the table, pp. 8-9), so outside their own dignities they have
        none: None."""
        p = self.grahas[name]
        if name in NODE_SIGNS:
            return next((k for k, sign in NODE_SIGNS[name].items() if p.sign == sign), None)
        ex_sign, _ = EXALTATION.get(name, (None, 0))
        db_sign, _ = DEBILITATION.get(name, (None, 0))
        if p.sign == ex_sign and p.degree < EXALTED_TO.get(name, 30.0):
            return "exalted"
        if p.sign == db_sign:
            return "debilitated"
        mt = MOOLATRIKONA.get(name)
        if mt and p.sign == mt[0] and mt[1] <= p.degree < mt[2]:
            return "moolatrikona"
        if p.sign in OWN_SIGNS.get(name, []):
            return "own"
        return self.relationship(name, SIGN_LORDS[p.sign])

    def natural_relation(self, a: str, b: str) -> str:
        if a == b or a not in NATURAL_FRIENDS or b not in NATURAL_FRIENDS:
            return "neutral"
        friends, neutrals = NATURAL_FRIENDS[a]
        if b in friends:
            return "friend"
        if b in neutrals:
            return "neutral"
        return "enemy"

    def temporal_relation(self, a: str, b: str) -> str:
        if a == b:
            return "neutral"
        distance = (self.grahas[b].sign - self.grahas[a].sign) % 12 + 1
        return "friend" if distance in (2, 3, 4, 10, 11, 12) else "enemy"

    def relationship(self, a: str, b: str) -> str:
        """Compound (panchadha) relationship used for dignity scoring."""
        scale = ["great enemy", "enemy", "neutral", "friend", "great friend"]
        nat = {"enemy": -1, "neutral": 0, "friend": 1}[self.natural_relation(a, b)]
        tmp = {"enemy": -1, "neutral": 0, "friend": 1}[self.temporal_relation(a, b)]
        return scale[max(0, min(4, nat + tmp + 2))]

    # --- aspects ------------------------------------------------------------

    def aspects_from(self, name: str) -> list[int]:
        """Houses (1-12 from the aspecting graha's own sign) it looks at."""
        if name in NO_ASPECTS:
            return []
        return sorted({7, *SPECIAL_ASPECTS.get(name, [])})

    def aspects_sign(self, name: str, sign: int) -> bool:
        offset = (sign - self.grahas[name].sign) % 12 + 1
        return offset in self.aspects_from(name)

    def aspecting(self, sign: int) -> list[str]:
        return [g for g in GRAHAS if self.aspects_sign(g, sign)]

    def rashi_drishti(self, sign: int) -> list[int]:
        """Jaimini sign aspects: movable signs see fixed (except the adjacent),
        fixed see movable (except adjacent), dual signs see the other duals."""
        mod = sign % 3
        if mod == 0:
            out = [s for s in range(12) if s % 3 == 1 and (s - sign) % 12 != 1]
        elif mod == 1:
            out = [s for s in range(12) if s % 3 == 0 and (sign - s) % 12 != 1]
        else:
            out = [s for s in range(12) if s % 3 == 2 and s != sign]
        return sorted(out)

    # --- states -------------------------------------------------------------

    def combust(self, name: str) -> bool:
        if name not in COMBUSTION_ORB:
            return False
        p = self.grahas[name]
        orb = (
            COMBUSTION_ORB_RETRO.get(name, COMBUSTION_ORB[name])
            if p.retrograde
            else COMBUSTION_ORB[name]
        )
        sep = abs((p.longitude - self.grahas["Sun"].longitude + 180) % 360 - 180)
        return sep <= orb

    def is_benefic(self, name: str) -> bool:
        """Phaladīpikā 2.27, pp. 19-20: the Sun, Mars, Saturn, Rahu, Ketu and the waning Moon are
        malefic, and so is Mercury joined with a malefic; the rest are benefic.
        Waning, per the translator's note to BJ 2.5 (1912, pp. 40-41), runs from
        the 8th of the dark half to the 8th of the bright half, so the Moon is a
        benefic in tithis 9 to 22."""
        if name in BENEFICS:
            return True
        if name == "Moon":
            elongation = (self.grahas["Moon"].longitude - self.grahas["Sun"].longitude) % 360
            return 9 <= int(elongation // 12) + 1 <= 22
        if name == "Mercury":
            sign = self.grahas["Mercury"].sign
            return not any(
                self.grahas[g].sign == sign and not self.is_benefic(g)
                for g in GRAHAS
                if g != "Mercury"
            )
        return False

    def functional_nature(self, name: str) -> str:
        """Yogakaraka / benefic / malefic by house lordship from the lagna."""
        ruled = set(self.houses_ruled(name))
        if not ruled:
            return "nodal"
        good = ruled & set(TRIKONA)
        bad = ruled & set(DUSTHANA)
        if good & {5, 9} and ruled & set(KENDRA):
            return "yogakaraka"
        if good and not bad:
            return "functional benefic"
        if bad and not good:
            return "functional malefic"
        return "mixed"

    # --- derived charts -----------------------------------------------------

    def d(self, division: int) -> Chart:
        """The D<n> varga as a first-class Chart."""
        if division == 1:
            return self
        grahas = {
            n: Position(n, varga(p.longitude, division), p.speed) for n, p in self.grahas.items()
        }
        asc = Position("Ascendant", varga(self.asc.longitude, division))
        return Chart(
            jd=self.jd,
            lat=self.lat,
            lon=self.lon,
            tz=self.tz,
            ayanamsa=self.ayanamsa,
            node=self.node,
            label=f"{self.label} D{division}",
            division=division,
            grahas=grahas,
            asc=asc,
            cusps=[],
        )

    # --- presentation -------------------------------------------------------

    def table(self) -> str:
        rows = [f"{'':10s} {'position':14s} {'nak':13s}{'pd':>3s}{'ho':>4s}  {'dignity':14s} rules"]
        rows.append(
            f"{'Ascendant':10s} {self.asc!s:14s} "
            f"{NAKSHATRAS[self.asc.nakshatra]:13s}{self.asc.pada:3d}"
            f"{1:4d}"
        )
        for name in GRAHAS:
            p = self.grahas[name]
            ruled = ",".join(str(h) for h in self.houses_ruled(name)) or "-"
            flag = "c" if self.combust(name) else " "
            rows.append(
                f"{name:10s} {p!s:14s} {NAKSHATRAS[p.nakshatra]:13s}"
                f"{p.pada:3d}{self.house(name):4d}{flag} {self.dignity(name) or '-':14s}"
                f"{ruled}"
            )
        return "\n".join(rows)

    def grid(self) -> str:
        """South-Indian style 4x4 sign grid -- readable in a terminal."""
        layout = [[11, 0, 1, 2], [10, None, None, 3], [9, None, None, 4], [8, 7, 6, 5]]
        cells = {}
        for s in range(12):
            body = [g[:2] for g in GRAHAS if self.grahas[g].sign == s]
            if s == self.asc.sign:
                body.insert(0, "As")
            cells[s] = " ".join(body)
        out = []
        for row in layout:
            top, mid = [], []
            for s in row:
                if s is None:
                    top.append(" " * 17)
                    mid.append(" " * 17)
                else:
                    top.append(f" {SIGNS[s][:3]:<15s}")
                    mid.append(f" {cells[s]:<15s}")
            out.append("|".join(top))
            out.append("|".join(mid))
            out.append("-" * 71)
        return "\n".join(out)


def natal(
    jd: float,
    lat: float,
    lon: float,
    tz: TimeZone = 0.0,
    ayanamsa: str = "lahiri",
    node: str = "true",
    label: str = "",
) -> Chart:
    return Chart(jd=jd, lat=lat, lon=lon, tz=tz, ayanamsa=ayanamsa, node=node, label=label)
