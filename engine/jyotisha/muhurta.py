"""Muhurta: the time windows of one Vedic day, for choosing when to begin a practice.

Calendar arithmetic only.  Every rule below is a textual convention and is
cited where it comes from; none of it is a predictive claim (see README,
"Known evidence limits").  Two kinds of rule are kept apart:

* standard panchanga conventions (kalams, durmuhurta, horas, bhadra), which
  every almanac prints;
* rules taken from the mantra manuals below, cited by book and PDF page:

  CH  L. R. Chawdhri, *Practicals of Mantras and Tantras*
  MF  K. T. Shubhakaran, *Mystical Formulae*, Part 1
  IJ  M. H. K. Shastri and L. K. Vashisth, *Inderjaal* (2023)
  SY  Swami Muktibodhananda, *Swara Yoga*
  UT  *Uddisa Tantra* attributed to Ravana (bilingual edition)

``find`` and ``check`` at the end choose a moment for an ordinary act -- an
application, a payment, enrolment, a journey, moving in -- by the general
muhurta conventions (Muhurta Chintamani), not the mantra manuals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import swisseph as swe

from .chart import EXALTATION, OWN_SIGNS, SIGN_LORDS
from .ephemeris import (
    NAKSHATRAS,
    SIGNS,
    ascendant,
    declination_view,
    luminaries,
    next_sunrise,
    positions,
    sunrise,
    sunset,
    to_datetime,
)
from .panchanga import (
    CHALDEAN,
    FIXED_KARANAS,
    KARANA_NAMES,
    TITHI_NAMES,
    YOGA_NAMES,
    compute,
)
from .rare import (
    AMRITA_ACT_BANS,
    AMRITA_SIDDHI,
    AMRITA_VISHA_TITHI,
    DAGDHA,
    KANA,
    MARANA,
    PANCHAKA,
    SARVARTHA_SIDDHI,
    SIDDHI,
    UTPATA,
    nakshatra_28,
)

TARA_NAMES = [
    "Janma", "Sampat", "Vipat", "Kshema", "Pratyak",
    "Sadhana", "Naidhana", "Mitra", "Parama Mitra",
]  # fmt: skip
TARA_GOOD = {"Sampat", "Kshema", "Sadhana", "Mitra", "Parama Mitra"}

# Eighths of daylight, 1-based.  Gulika is Saturn's eighth and Yamaganda
# Jupiter's when the eighths are dealt out from the weekday lord in weekday
# order; Rahu kalam has no such derivation and is the fixed almanac table.
RAHU_KALAM = {"Sun": 8, "Moon": 2, "Mars": 7, "Mercury": 5, "Jupiter": 6, "Venus": 4, "Saturn": 3}
YAMAGANDA = {"Sun": 5, "Moon": 4, "Mars": 3, "Mercury": 2, "Jupiter": 1, "Venus": 7, "Saturn": 6}
GULIKA = {"Sun": 7, "Moon": 6, "Mars": 5, "Mercury": 4, "Jupiter": 3, "Venus": 2, "Saturn": 1}
# Daytime durmuhurtas (1-based of 15).  Tuesday's night durmuhurta varies
# between almanacs and is not encoded.
DURMUHURTA = {
    "Sun": (14,), "Moon": (9, 12), "Mars": (4,), "Mercury": (8,),
    "Jupiter": (6, 12), "Venus": (4, 9), "Saturn": (1, 2),
}  # fmt: skip

CHOGHADIYA_NAME = {
    "Sun": "Udveg", "Venus": "Char", "Mercury": "Labh", "Moon": "Amrit",
    "Saturn": "Kaal", "Jupiter": "Shubh", "Mars": "Rog",
}  # fmt: skip
CHOGHADIYA_GOOD = {"Amrit", "Shubh", "Labh", "Char"}  # IJ pdf 101: four auspicious, three not

# CH pdf 100-101, quoting Rudrayamala Tantra: what each rising sign does to japa.
# "So Taurus, Gemini, Leo, Sagittarius and Pisces lagnas are to be avoided."
LAGNA_USE = {
    "Aries": (True, "mantras for wealth"),
    "Taurus": (False, "maran and videshan only"),
    "Gemini": (False, "destroys progeny"),
    "Cancer": (True, "siddhi"),
    "Leo": (False, "destroys the intelligence"),
    "Virgo": (True, "Lakshmi mantras"),
    "Libra": (True, "all types of mantras"),
    "Scorpio": (True, "gold gain, victory over enemies"),
    "Sagittarius": (False, "loss of respect"),
    "Capricorn": (True, "works"),
    "Aquarius": (True, "wealth, religious and siddhi mantras"),
    "Pisces": (False, "troublesome"),
}

# MF pdf 40: commencement of a mantra siddhi needs all three to tally.
# MF pdf 34 adds Pushya, Hasta and Mula as the best nakshatras to begin.
COMMENCE_NAKSHATRAS = {"U.Phalguni", "Hasta", "Ashwini", "Shravana", "Vishakha", "Mrigashira"}
COMMENCE_NAKSHATRAS_ALT = {"Pushya", "Hasta", "Mula"}
COMMENCE_VARAS = {"Sun", "Moon", "Mercury", "Jupiter", "Venus"}
COMMENCE_TITHIS = {2, 3, 5, 7, 10, 11, 13, 15}

# IJ pdf 82: Yogini's seat by tithi (the book lists 1-8; the cycle repeats).
# Behind or to the left is auspicious, in front or to the right is not.
# Note IJ puts Chaturthi in the north-west and Saptami in the south-west,
# the reverse of the common almanac table.
YOGINI_DIRS = ["E", "N", "SE", "NW", "S", "W", "SW", "NE"]
# The common almanac table, used for journeys.
YOGINI_ALMANAC = ["E", "N", "SE", "SW", "S", "W", "NW", "NE"]
# IJ pdf 98: the Moon's direction by sign (fire east, earth south, air west,
# water north); IJ pdf 94 calls the Moon in front a giver of wealth.
MOON_DIRS = ["E", "S", "W", "N"]
BEARING = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}

# Muhurta Chintamani 1.4, Kasyapa in the commentary (1945 printing, p. 12):
# Nanda on Friday, Bhadra on Wednesday, Jaya on Tuesday, Rikta on Saturday and
# Purna on Thursday are siddha.
SIDDHA_YOGA = {"Venus": 1, "Mercury": 2, "Mars": 3, "Saturn": 4, "Jupiter": 5}
TITHI_CLASS = ["Nanda", "Bhadra", "Jaya", "Rikta", "Purna"]

# IJ pdf 100-101: the transiting Moon's house from the natal Moon.
MOON_HOUSE_IJ = {
    1: "welfare",
    2: "satisfying",
    3: "wealth",
    4: "jarring",
    5: "increases knowledge",
    6: "profitable",
    7: "repute",
    8: "death",
    9: "fruitful",
    10: "fulfils desires",
    11: "profitable",
    12: "harmful",
}
MOON_HOUSE_BAD_IJ = {4, 8, 12}

# Bhadra (Vishti karana) resides by the Moon's sign, and "its effect falls there"
# (MC 1.45, p. 38): only Bhadra on earth is avoided here.
BHADRA_EARTH = {3, 4, 10, 11}  # Cancer, Leo, Aquarius, Pisces (0-based signs)
BHADRA_HEAVEN = {0, 1, 2, 7}

# Inauspicious yogas: how many ghatis (24 min) from the yoga's start to avoid
# (MC 1.34-35, p. 28; Nirnaya-sindhu p. 33). None is the whole yoga, "half" the
# first half of its actual span. Muhurta Martanda v.2 gives Vajra 9 instead of 3.
BAD_YOGA_GHATIS = {
    "Vishkambha": 3, "Atiganda": 6, "Shula": 5, "Ganda": 6, "Vyaghata": 9,
    "Vajra": 3, "Parigha": "half", "Vyatipata": None, "Vaidhriti": None,
}  # fmt: skip


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    label: str
    note: str = ""

    def contains(self, jd: float) -> bool:
        return self.start <= jd < self.end

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and start < self.end


@dataclass
class Day:
    """Everything one Vedic day (sunrise to next sunrise) offers for timing."""

    sunrise: float
    sunset: float
    next_sunrise: float
    prev_sunset: float
    vara: str
    brahma: Window
    abhijit: Window
    pradosha: Window
    avoid: list[Window] = field(default_factory=list)
    horas: list[Window] = field(default_factory=list)
    choghadiyas: list[Window] = field(default_factory=list)
    lagnas: list[Window] = field(default_factory=list)
    changes: list[tuple[float, str]] = field(default_factory=list)
    bhadra_parts: list[Window] = field(default_factory=list)  # face and tail (MC 1.44)
    mahapatas: list[Window] = field(default_factory=list)  # equal declinations (MC 1.34)

    @property
    def day_muhurta(self) -> float:
        return (self.sunset - self.sunrise) / 15.0

    def at(self, windows: list[Window], jd: float) -> Window | None:
        return next((w for w in windows if w.contains(jd)), None)


def _parts(start: float, end: float, n: int) -> list[tuple[float, float]]:
    span = (end - start) / n
    return [(start + i * span, start + (i + 1) * span) for i in range(n)]


def _bisect(fn, lo: float, hi: float, iterations: int = 32) -> float:
    """First moment in (lo, hi] where fn differs from fn(lo)."""
    v = fn(lo)
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if fn(mid) == v:
            lo = mid
        else:
            hi = mid
    return hi


def _scan(fn, start: float, end: float, step: float) -> list[tuple[float, object]]:
    """Moments where fn changes value inside [start, end), with the new value."""
    out = []
    t, v = start, fn(start)
    while t < end:
        nxt = min(t + step, end)
        w = fn(nxt)
        if w != v:
            edge = _bisect(fn, t, nxt)
            out.append((edge, fn(edge)))
            v = fn(edge)
            t = edge
        else:
            t = nxt
    return out


def tithi_at(jd: float, ayanamsa: str = "lahiri") -> int:
    sun, moon = luminaries(jd, ayanamsa)
    return int(((moon.longitude - sun.longitude) % 360) // 12) + 1


def tithi_label(t: int) -> str:
    paksha = "S" if t <= 15 else "K"
    name = "Purnima" if t == 15 else "Amavasya" if t == 30 else TITHI_NAMES[(t - 1) % 15]
    return f"{paksha}{(t - 1) % 15 + 1} {name}"


def nakshatra_at(jd: float, ayanamsa: str = "lahiri") -> int:
    return luminaries(jd, ayanamsa)[1].nakshatra


def yoga_at(jd: float, ayanamsa: str = "lahiri") -> int:
    sun, moon = luminaries(jd, ayanamsa)
    return int(((sun.longitude + moon.longitude) % 360) // (360 / 27))


def karana_at(jd: float, ayanamsa: str = "lahiri") -> str:
    """Same half-tithi mapping as panchanga.compute, without its rise/set work."""
    sun, moon = luminaries(jd, ayanamsa)
    return _karana((moon.longitude - sun.longitude) % 360)


def _karana(elongation: float) -> str:
    half = min(int(elongation // 6) + 1, 60)
    if half == 1:
        return FIXED_KARANAS[0]
    if half >= 58:
        return FIXED_KARANAS[half - 57]
    return KARANA_NAMES[(half - 2) % 7]


def lagna_at(jd: float, lat: float, lon: float, ayanamsa: str = "lahiri") -> int:
    return ascendant(jd, lat, lon, ayanamsa)[0].sign


def tara(janma_nakshatra: int, moon_nakshatra: int) -> str:
    return TARA_NAMES[((moon_nakshatra - janma_nakshatra) % 27) % 9]


def moon_house(natal_moon_sign: int, moon_sign: int) -> int:
    return (moon_sign - natal_moon_sign) % 12 + 1


def siddha_yoga(tithi: int, vara: str) -> bool:
    cls = ((tithi - 1) % 15) % 5 + 1  # 1 Nanda .. 5 Purna
    return SIDDHA_YOGA.get(vara) == cls


def commencement(tithi: int, vara: str, nakshatra: int) -> dict[str, bool]:
    n = (tithi - 1) % 15 + 1
    name = NAKSHATRAS[nakshatra]
    return {
        "vara": vara in COMMENCE_VARAS,
        "tithi": tithi != 30 and n in COMMENCE_TITHIS,
        "nakshatra": name in COMMENCE_NAKSHATRAS or name in COMMENCE_NAKSHATRAS_ALT,
    }


def yogini_direction(tithi: int, almanac: bool = False) -> str:
    n = (tithi - 1) % 15 + 1 if tithi != 30 else 8
    return (YOGINI_ALMANAC if almanac else YOGINI_DIRS)[(n - 1) % 8]


def moon_direction(moon_sign: int) -> str:
    return MOON_DIRS[moon_sign % 4]


def relative_side(facing: str, direction: str) -> str:
    theta = (BEARING[direction] - BEARING[facing]) % 360
    if theta <= 45 or theta >= 315:
        return "front"
    if theta <= 135:
        return "right"
    if theta <= 225:
        return "back"
    return "left"


def facing_options(tithi: int, moon_sign: int, prefer: tuple[str, ...] = ("N", "E", "W")):
    """Rank seat directions: Yogini behind/left (IJ pdf 82), then the book
    preference order, then the Moon in front (IJ pdf 94)."""
    yogini, moon = yogini_direction(tithi), moon_direction(moon_sign)
    ranked = []
    for rank, facing in enumerate(prefer):
        side = relative_side(facing, yogini)
        ok = side in {"back", "left"}
        ranked.append(
            {
                "facing": facing,
                "yogini": f"{yogini} ({side})",
                "yogini_ok": ok,
                "moon_in_front": moon == facing,
                "key": (not ok, rank - (0.5 if moon == facing else 0.0)),
            }
        )
    return sorted(ranked, key=lambda r: r["key"])


# MC 1.44: for the Bhadra of tithi 4, 8, 11, 15 (bright) and 3, 7, 10, 14 (dark),
# the prahara (an eighth of the tithi) whose first 5 ghatis are its face and the
# one whose last 3 are its tail. DS pp. 94-95 keeps the 5 and 3 ghatis fixed.
BHADRA_FACE_TAIL = {
    4: (5, 8),
    8: (2, 1),
    11: (7, 6),
    15: (4, 3),
    18: (8, 7),
    22: (3, 2),
    25: (6, 5),
    29: (1, 4),
}


def bhadra_face_tail(
    tithi: int, start: float, end: float
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Bhadra's face and tail inside the tithi that runs from start to end."""
    if tithi not in BHADRA_FACE_TAIL:
        return None
    face, tail = BHADRA_FACE_TAIL[tithi]
    prahara, ghati = (end - start) / 8, 24 / 1440
    f0 = start + (face - 1) * prahara
    t1 = start + tail * prahara
    return (f0, f0 + 5 * ghati), (t1 - 3 * ghati, t1)


def mahapatas(t0: float, t1: float) -> list[tuple[str, float, float, float]]:
    """Mahapata, the equal declination of the Sun and Moon (MC 1.34 commentary;
    Surya-siddhanta 11, Burgess). Vyatipata: tropical longitudes summing to about
    180 degrees, declinations equal on the same side. Vaidhriti: summing to about
    360, equal and opposite. The half-duration is the sum of the semi-diameters
    over the difference of the daily motions in longitude (11.14-15). Returns
    (kind, moment, start, end) for each one whose span touches [t0, t1]."""

    def total(t: float) -> float:
        return (declination_view(t, "Sun")[0] + declination_view(t, "Moon")[0]) % 360

    out = []
    # Near the solstices the declinations change slowly and the moment can fall
    # more than a day from the crossing, so crossings within two days count.
    step, t = 0.25, t0 - 2
    prev = total(t)
    while t < t1 + 2:
        nxt = t + step
        cur = total(nxt)
        for kind, target, sign in (("vyatipata", 180.0, 1), ("vaidhriti", 0.0, -1)):
            if (prev - target) % 360 > 180 and (cur - target) % 360 <= 180:
                # Near the equator the declinations can meet twice (11.19).
                for moment in _declinations_meet(t - 1.5, nxt + 1.5, sign):
                    _, _, sun_speed, sun_semi = declination_view(moment, "Sun")
                    _, _, moon_speed, moon_semi = declination_view(moment, "Moon")
                    half = (sun_semi + moon_semi) / abs(moon_speed - sun_speed)
                    if moment + half > t0 and moment - half < t1:
                        out.append((kind, moment, moment - half, moment + half))
        t, prev = nxt, cur
    return sorted(out, key=lambda r: r[1])


def _declinations_meet(a: float, b: float, sign: int) -> list[float]:
    """Every moment in [a, b] where the Moon's declination equals sign times the
    Sun's (11.9-12); none when they never meet there (11.19)."""

    def gap(t: float) -> float:
        return declination_view(t, "Moon")[1] - sign * declination_view(t, "Sun")[1]

    roots, step = [], 1 / 24
    t, g = a, gap(a)
    while t < b:
        u = min(t + step, b)
        h = gap(u)
        if g == 0 or (g < 0) != (h < 0):
            lo, hi, glo = t, u, g
            for _ in range(40):
                mid = (lo + hi) / 2
                gm = gap(mid)
                if (glo < 0) != (gm < 0):
                    hi = mid
                else:
                    lo, glo = mid, gm
            roots.append((lo + hi) / 2)
        t, g = u, h
    return roots


# Surya-siddhanta 9.6-7: Jupiter and Venus are set within these distances of the
# Sun in time-degrees (Venus 8 while retrograde, 10 otherwise).
SIDEREAL_DAY = 360.9856  # time-degrees per solar day
# MC 5.27: (days old before setting, days infant after rising) by the side of the sky.
OLD_INFANT_DAYS = {
    "Venus": ({"east": 15, "west": 5}, {"east": 3, "west": 10}),
    "Jupiter": ({"east": 15, "west": 15}, {"east": 15, "west": 15}),
}


def kalamsa(name: str, sr: float, ss: float, lat: float, lon: float) -> tuple[float, bool]:
    """Jupiter's or Venus's distance from the Sun in time-degrees, and whether it is
    east of the Sun (an evening planet): the gap between its setting and the Sun's,
    or for a morning planet between their risings, at the place."""
    body = swe.JUPITER if name == "Jupiter" else swe.VENUS
    sun, planet = (swe.calc_ut(sr, b, swe.FLG_SWIEPH)[0][0] for b in (swe.SUN, body))
    east = (planet - sun) % 360 < 180
    if min((planet - sun) % 360, (sun - planet) % 360) > 30:
        return 999.0, east  # far from the Sun; near opposition the nearest setting is ambiguous
    flag = (swe.CALC_SET if east else swe.CALC_RISE) | swe.BIT_DISC_CENTER
    res, tret = swe.rise_trans((ss if east else sr) - 0.5, body, flag, (lon, lat, 0.0))
    if res != 0:
        return 0.0, east
    return ((tret[0] - ss) if east else (sr - tret[0])) * SIDEREAL_DAY, east


def jupiter_venus_states(
    days: list[tuple[float, float]],
    lat: float,
    lon: float,
    counts: dict | None = None,
    venus_direct: float = 10.0,
) -> dict[str, dict[int, tuple[str, str | None]]]:
    """Per planet, day index (of consecutive (sunrise, sunset) days) -> (set | old |
    infant, detail), by MC 5.27's counts unless ``counts`` replaces them: an evening
    planet sets in the west and a morning one rises in the east. ``venus_direct`` is
    Venus's distance near superior conjunction (SS 9.6-7: 10)."""
    counts = counts or OLD_INFANT_DAYS
    out = {}
    for name in ("Jupiter", "Venus"):
        flags, sides = [], []
        for sr, ss in days:
            if name == "Jupiter":
                limit = 11.0
            else:
                speed = swe.calc_ut(sr, swe.VENUS, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][3]
                limit = 8.0 if speed < 0 else venus_direct
            gap, east = kalamsa(name, sr, ss, lat, lon)
            flags.append(gap < limit)
            sides.append(east)
        state: dict[int, tuple[str, str | None]] = {}
        i = 0
        while i < len(flags):
            if not flags[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            setting = "west" if i > 0 and sides[i - 1] else "east"
            rising = "west" if j + 1 < len(flags) and sides[j + 1] else "east"
            old_days, infant_days = counts[name]
            before, after = old_days[setting], infant_days[rising]
            for k in range(max(0, i - before), i):
                state.setdefault(k, ("old", f"{before} days before setting in the {setting}"))
            for k in range(i, j + 1):
                state[k] = ("set", None)
            for k in range(j + 1, min(len(flags), j + 1 + after)):
                state.setdefault(k, ("infant", f"{after} days after rising in the {rising}"))
            i = j + 1
        out[name] = state
    return out


def planet_states_around(start: float, end: float, lat: float, lon: float) -> dict[int, dict]:
    """Jupiter's and Venus's states for each Vedic day touching [start, end], keyed
    by the day's sunrise to the minute; the runs reach 16 days either side."""
    sr = sunrise(start - 16, lat, lon)
    days = []
    while sr < end + 16:
        days.append((sr, sunset(sr + 0.01, lat, lon)))
        sr = next_sunrise(sr + 0.01, lat, lon)
    states = jupiter_venus_states(days, lat, lon)
    return {
        round(sr * 1440): {g: states[g][i][0] for g in states if i in states[g]}
        for i, (sr, _) in enumerate(days)
    }


def bhadra_residence(moon_sign: int) -> str:
    if moon_sign in BHADRA_EARTH:
        return "earth"
    return "heaven" if moon_sign in BHADRA_HEAVEN else "patala"


def day(jd: float, lat: float, lon: float, ayanamsa: str = "lahiri", tz=None) -> Day:
    """The Vedic day whose sunrise governs jd (pass any moment after sunrise).
    ``tz`` names the weekday by the local civil date of the sunrise."""
    sr = sunrise(jd, lat, lon)
    ss = sunset(jd, lat, lon)
    nr = next_sunrise(jd, lat, lon)
    prev_ss = sunset(sr - 1e-3, lat, lon)
    vara = compute(sr + 1e-4, lat, lon, ayanamsa, tz).vara
    dm, nm, pm = (ss - sr) / 15, (nr - ss) / 15, (sr - prev_ss) / 15

    out = Day(
        sunrise=sr,
        sunset=ss,
        next_sunrise=nr,
        prev_sunset=prev_ss,
        vara=vara,
        # 14th of the 15 muhurtas of the preceding night.
        brahma=Window(sr - 2 * pm, sr - pm, "Brahma muhurta"),
        abhijit=Window(
            sr + 7 * dm,
            sr + 8 * dm,
            "Abhijit",
            "avoided on Wednesdays" if vara == "Mercury" else "",
        ),
        # "tri-muhurtah pradoshah": three muhurtas after sunset.
        pradosha=Window(ss, ss + 3 * nm, "Pradosha"),
    )
    eighths = _parts(sr, ss, 8)
    for table, label in ((RAHU_KALAM, "Rahu kalam"), (YAMAGANDA, "Yamaganda"), (GULIKA, "Gulika")):
        a, b = eighths[table[vara] - 1]
        out.avoid.append(Window(a, b, label))
    for i in DURMUHURTA[vara]:
        out.avoid.append(Window(sr + (i - 1) * dm, sr + i * dm, "Durmuhurta"))

    start = CHALDEAN.index(vara)
    for k, (a, b) in enumerate(_parts(sr, ss, 12) + _parts(ss, nr, 12)):
        out.horas.append(Window(a, b, CHALDEAN[(start + k) % 7]))
    for k, (a, b) in enumerate(_parts(sr, ss, 8)):
        lord = CHALDEAN[(start + k) % 7]
        out.choghadiyas.append(Window(a, b, CHOGHADIYA_NAME[lord], lord))
    for k, (a, b) in enumerate(_parts(ss, nr, 8)):
        lord = CHALDEAN[(start + 5 + 5 * k) % 7]
        out.choghadiyas.append(Window(a, b, CHOGHADIYA_NAME[lord], lord))

    t0, t1 = out.brahma.start, nr
    edges = [(t0, lagna_at(t0, lat, lon, ayanamsa))]
    edges += _scan(lambda t: lagna_at(t, lat, lon, ayanamsa), t0, t1, 3 / 1440)
    for (a, sign), (b, _) in zip(edges, edges[1:] + [(t1, None)], strict=True):
        good, use = LAGNA_USE[SIGNS[sign]]
        out.lagnas.append(Window(a, b, SIGNS[sign], ("ok: " if good else "avoid: ") + use))

    step = 1 / 24
    for name, (a, b) in _yoga_spans(t0, t1, ayanamsa):
        if name in BAD_YOGA_GHATIS:
            n = BAD_YOGA_GHATIS[name]
            if n is None:
                end, what = b, "whole yoga"
            elif n == "half":
                end, what = a + (b - a) / 2, "first half"
            else:
                end, what = min(b, a + n * 24 / 1440), f"first {n} ghatis"
            if end > t0:
                out.avoid.append(Window(a, end, f"{name} yoga ({what})"))
    for num, (a, b) in _tithi_spans(t0, t1, ayanamsa):
        parts = bhadra_face_tail(num, a, b)
        if parts:
            out.bhadra_parts += [Window(*parts[0], "face"), Window(*parts[1], "tail")]
    out.mahapatas = [Window(a, b, kind) for kind, _, a, b in mahapatas(t0, t1)]
    for t, v in _scan(lambda t: tithi_at(t, ayanamsa), t0, t1, step):
        out.changes.append((t, f"tithi -> {tithi_label(v)}"))
    for t, v in _scan(lambda t: nakshatra_at(t, ayanamsa), t0, t1, step):
        out.changes.append((t, f"nakshatra -> {NAKSHATRAS[v]}"))
    for t, v in _scan(lambda t: yoga_at(t, ayanamsa), t0, t1, step):
        out.changes.append((t, f"yoga -> {YOGA_NAMES[v]}"))
    for t, v in _scan(lambda t: karana_at(t, ayanamsa), t0, t1, step / 2):
        out.changes.append((t, f"karana -> {v}"))
    for t, v in _scan(lambda t: luminaries(t, ayanamsa)[1].sign, t0, t1, step):
        out.changes.append((t, f"Moon -> {SIGNS[v]}"))
    out.changes.sort()
    return out


def _tithi_spans(t0: float, t1: float, ayanamsa: str = "lahiri"):
    """(number, (start, end)) for every tithi touching [t0, t1], with true bounds."""
    fn = lambda t: tithi_at(t, ayanamsa)  # noqa: E731
    start = t0
    while fn(start - 1 / 24) == fn(t0):
        start -= 1 / 24
    start = _bisect(fn, start - 1 / 24, start)
    edges = [start] + [t for t, _ in _scan(fn, t0, t1 + 1.2, 1 / 24)]
    return [(fn(a + 1e-6), (a, b)) for a, b in zip(edges, edges[1:], strict=False) if a <= t1]


def _yoga_spans(t0: float, t1: float, ayanamsa: str = "lahiri"):
    """(name, (start, end)) for every yoga touching [t0, t1], with true start times."""
    fn = lambda t: yoga_at(t, ayanamsa)  # noqa: E731
    start = t0
    while fn(start - 1 / 24) == fn(t0):
        start -= 1 / 24
    start = _bisect(fn, start - 1 / 24, start)
    edges = [start] + [t for t, _ in _scan(fn, t0, t1 + 1.2, 1 / 24)]
    spans = []
    for a, b in zip(edges, edges[1:], strict=False):
        if a > t1:
            break
        spans.append((YOGA_NAMES[fn(a + 1e-6)], (a, b)))
    return spans


def conditions(d: Day, jd: float, lat: float, lon: float, natal_moon, ayanamsa: str = "lahiri"):
    """The state of every rule at one moment, for scoring a candidate start."""
    p = positions(jd, ayanamsa)
    t = tithi_at(jd, ayanamsa)
    moon = p["Moon"]
    lagna = SIGNS[lagna_at(jd, lat, lon, ayanamsa)]
    hora = d.at(d.horas, jd)
    chog = d.at(d.choghadiyas, jd)
    karana = karana_at(jd, ayanamsa)
    return {
        "tithi": t,
        "tithi_label": tithi_label(t),
        "nakshatra": NAKSHATRAS[moon.nakshatra],
        "yoga": YOGA_NAMES[yoga_at(jd, ayanamsa)],
        "karana": karana,
        "bhadra": karana == KARANA_NAMES[6],
        "bhadra_residence": bhadra_residence(moon.sign),
        "moon_sign": SIGNS[moon.sign],
        "lagna": lagna,
        "lagna_ok": LAGNA_USE[lagna][0],
        "lagna_use": LAGNA_USE[lagna][1],
        "hora": hora.label if hora else "",
        "choghadiya": chog.label if chog else "",
        "choghadiya_ok": bool(chog and chog.label in CHOGHADIYA_GOOD),
        "avoid": [w.label for w in d.avoid if w.contains(jd)],
        "tara": tara(natal_moon.nakshatra, moon.nakshatra),
        "moon_house": moon_house(natal_moon.sign, moon.sign),
        "siddha_yoga": siddha_yoga(t, d.vara),
        "commencement": commencement(t, d.vara, moon.nakshatra),
    }


def report(d: Day, tz, natal_moon=None, ayanamsa: str = "lahiri") -> str:
    from .ephemeris import to_datetime

    def hm(jd: float) -> str:
        return to_datetime(jd, tz).strftime("%H:%M")

    lines = [
        f"{to_datetime(d.sunrise, tz):%a %d %b %Y}  vara {d.vara}  "
        f"sunrise {hm(d.sunrise)}  sunset {hm(d.sunset)}  next sunrise {hm(d.next_sunrise)}",
        f"  Brahma muhurta {hm(d.brahma.start)}-{hm(d.brahma.end)}   "
        f"Abhijit {hm(d.abhijit.start)}-{hm(d.abhijit.end)}"
        + (f" ({d.abhijit.note})" if d.abhijit.note else "")
        + f"   Pradosha {hm(d.pradosha.start)}-{hm(d.pradosha.end)}",
        "  avoid: " + ", ".join(f"{w.label} {hm(w.start)}-{hm(w.end)}" for w in d.avoid),
        "  changes: " + "; ".join(f"{hm(t)} {s}" for t, s in d.changes),
        "  lagna: "
        + ", ".join(
            f"{w.label[:3]} {hm(w.start)}-{hm(w.end)}{'' if w.note.startswith('ok') else ' x'}"
            for w in d.lagnas
        ),
        "  hora (day): " + " ".join(f"{hm(w.start)} {w.label[:3]}" for w in d.horas[:12]),
        "  choghadiya: "
        + " ".join(
            f"{hm(w.start)} {w.label}{'' if w.label in CHOGHADIYA_GOOD else '*'}"
            for w in d.choghadiyas
        ),
    ]
    return "\n".join(lines)


# --- choosing a moment for an act -------------------------------------------
#
# ``find`` scores every minute of a span for one kind of act and keeps the
# windows no rule vetoes.  Everything short of a veto carries a weighted
# defect, so windows with different flaws can be compared rather than all
# being called "bad".  The weights encode the tradition's own ordering --
# karana, yoga, tithi and the kalams above panchaka, panchaka above
# choghadiya -- not a measured effect.

MASA = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashwin", "Kartika", "Margashirsha", "Pausha", "Magha", "Phalguna",
]  # fmt: skip
VARA_NAME = {
    "Sun": "Sunday", "Moon": "Monday", "Mars": "Tuesday", "Mercury": "Wednesday",
    "Jupiter": "Thursday", "Venus": "Friday", "Saturn": "Saturday",
}  # fmt: skip
WEEKDAY_INDEX = {lord: i for i, lord in enumerate(VARA_NAME)}
# The direction a journey may not set out in on each weekday.
DISHA_SHOOL = {
    "Sun": "W", "Moon": "E", "Mars": "N", "Mercury": "N",
    "Jupiter": "S", "Venus": "W", "Saturn": "E",
}  # fmt: skip
NAKSHATRA_CLASS = {
    **dict.fromkeys(("Punarvasu", "Swati", "Shravana", "Dhanishta", "Shatabhisha"), "chara"),
    **dict.fromkeys(("Mrigashira", "Chitra", "Anuradha", "Revati"), "mridu"),
    **dict.fromkeys(("Ashwini", "Pushya", "Hasta"), "kshipra"),
    **dict.fromkeys(("Rohini", "U.Phalguni", "U.Ashadha", "U.Bhadrapada"), "dhruva"),
    **dict.fromkeys(("Bharani", "Magha", "P.Phalguni", "P.Ashadha", "P.Bhadrapada"), "ugra"),
    **dict.fromkeys(("Krittika", "Vishakha"), "misra"),
    **dict.fromkeys(("Ardra", "Ashlesha", "Jyeshtha", "Mula"), "tikshna"),
}
HARSH = {"ugra", "tikshna"}
MALEFICS = ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
BAD_TARA = {"Vipat", "Pratyak", "Naidhana"}


@dataclass(frozen=True)
class Profile:
    """What one kind of act favours.  Anything outside a favoured set costs."""

    name: str
    about: str
    nakshatras: frozenset[str]
    other_nakshatra: float
    harsh: float  # added for an ugra or tikshna nakshatra outside the set
    tithis: frozenset[int]  # within the paksha; 15 is Purnima
    other_tithi: float
    varas: frozenset[str]
    other_vara: float
    horas: frozenset[str]
    season: float  # Pitru Paksha and adhika masa, for a new beginning
    travel: bool = False
    home: bool = False
    mundan: bool = False
    barred_nakshatras: frozenset[str] = frozenset()  # vetoed, not merely unfavoured
    barred_varas: frozenset[str] = frozenset()
    rikta_only: bool = False  # bar the rikta tithis and Amavasya but not Ashtami


def _classes(*names: str) -> frozenset[str]:
    return frozenset(n for n, c in NAKSHATRA_CLASS.items() if c in names)


# MC 2.16: the buying stars, and the selling stars of 2.17 barred for buying.
BUYING_STARS = frozenset({"Revati", "Shatabhisha", "Ashwini", "Swati", "Shravana", "Chitra"})
SELLING_STARS = frozenset(
    {"P.Phalguni", "P.Ashadha", "P.Bhadrapada", "Vishakha", "Krittika", "Ashlesha", "Bharani"}
)
# The Vyavaharoccaya in MC's commentary on 2.18: mounting an elephant, horse or
# chariot, under eleven stars and on the days of Jupiter, the Moon, the Sun, Venus and
# Mercury.
RIDING_STARS = BUYING_STARS | {"Mrigashira", "Punarvasu", "Hasta", "Pushya", "Dhanishta"}
RIDING_VARAS = frozenset({"Jupiter", "Moon", "Sun", "Venus", "Mercury"})

MUNDAN_STARS = frozenset(
    {
        "Ashwini", "Mrigashira", "Punarvasu", "Pushya", "Hasta", "Chitra", "Swati",
        "Jyeshtha", "Shravana", "Dhanishta", "Shatabhisha", "Revati",
    }
)  # fmt: skip

PROFILES = {
    p.name: p
    for p in (
        Profile(
            "general",
            "applications, accounts, payments, documents, admin",
            _classes("chara", "mridu", "kshipra", "dhruva"),
            1.0,
            2.0,
            frozenset({2, 3, 5, 6, 7, 10, 11, 12, 13, 15}),
            0.5,
            frozenset({"Sun", "Moon", "Mercury", "Jupiter", "Venus"}),
            0.5,
            frozenset({"Mercury", "Jupiter"}),
            1.0,
        ),
        # Vidyarambha (Muhurta Chintamani): Mrigashira, Hasta and Shravana with
        # the two after each, Ashwini, Mula, the three Purvas and Pushya.
        Profile(
            "education",
            "enrolment, starting a course, exams, beginning study",
            frozenset(
                {
                    "Mrigashira",
                    "Ardra",
                    "Punarvasu",
                    "Hasta",
                    "Chitra",
                    "Swati",
                    "Shravana",
                    "Dhanishta",
                    "Shatabhisha",
                    "Ashwini",
                    "Mula",
                    "P.Phalguni",
                    "P.Ashadha",
                    "P.Bhadrapada",
                    "Pushya",
                }
            ),  # fmt: skip
            1.5,
            1.0,
            frozenset({2, 3, 5, 6, 10, 11, 12}),
            1.0,
            frozenset({"Sun", "Mercury", "Jupiter", "Venus"}),
            1.0,
            frozenset({"Jupiter", "Mercury"}),
            1.5,
        ),
        # Yatra: the movable, soft and swift nakshatras; weekday is judged by
        # direction (disha shool) rather than by a favoured list.
        Profile(
            "travel",
            "setting out on a journey or doing its prasthana (needs --toward)",
            _classes("chara", "mridu", "kshipra"),
            2.0,
            1.0,
            frozenset({2, 3, 5, 7, 10, 11, 13}),
            1.0,
            frozenset(VARA_NAME),
            0.0,
            frozenset({"Jupiter", "Venus", "Mercury"}),
            1.5,
            travel=True,
        ),
        # Griha pravesh: the fixed and soft nakshatras plus Dhanishta and
        # Shatabhisha; fixed lagnas; the 4th free of malefics.
        Profile(
            "home",
            "moving in, first entry, signing or collecting keys",
            _classes("dhruva", "mridu") | {"Dhanishta", "Shatabhisha"},
            1.5,
            1.5,
            frozenset(range(1, 16)),  # MC 13.4 bars only rikta and Amavasya (vetoed)
            1.0,
            frozenset({"Moon", "Mercury", "Jupiter", "Venus", "Saturn"}),
            1.0,
            frozenset({"Jupiter", "Venus", "Moon"}),
            2.5,
            home=True,
        ),
        # Cudakarana (MC 5.29): the soft, movable and swift nakshatras with Jyeshtha,
        # without Anuradha; the weekdays of Mercury, the Moon, Venus and Jupiter.
        # Its own vetoes are in _mundan_vetoes.
        # Buying a vehicle: a buying star (MC 2.16), a riding weekday (the
        # Vyavaharoccaya, MC 2.18 commentary), no rikta tithi (MC 2.18's horse rule,
        # our reading for vehicles).
        Profile(
            "vehicle",
            "buying a vehicle (the riding stars suit taking delivery)",
            BUYING_STARS,
            1.0,
            1.0,
            frozenset(range(1, 16)),
            0.0,
            RIDING_VARAS,
            0.0,
            frozenset({"Jupiter", "Venus", "Mercury"}),
            1.0,
            barred_nakshatras=SELLING_STARS,
            barred_varas=frozenset(VARA_NAME) - RIDING_VARAS,
            rikta_only=True,
        ),
        # Buying property or land: no specific rule survives, so the general buying
        # rule (MC 2.16).
        Profile(
            "property",
            "buying property or land (the general buying rule)",
            BUYING_STARS,
            1.0,
            1.0,
            frozenset(range(1, 16)),
            0.0,
            frozenset(VARA_NAME),
            0.0,
            frozenset({"Jupiter", "Venus", "Mercury"}),
            1.0,
            barred_nakshatras=SELLING_STARS,
            rikta_only=True,
        ),
        Profile(
            "mundan",
            "a child's first tonsure (mundan, cudakarana)",
            MUNDAN_STARS,
            2.0,
            1.0,
            frozenset({2, 3, 5, 7, 10, 11, 13}),
            1.0,
            frozenset({"Moon", "Mercury", "Jupiter", "Venus"}),
            1.0,
            frozenset({"Jupiter", "Venus", "Mercury", "Moon"}),
            2.5,
            mundan=True,
        ),
    )
}


def _elongation(jd: float) -> float:
    sun, moon = luminaries(jd)
    return (moon.longitude - sun.longitude) % 360


def new_moon_before(jd: float) -> float:
    t = jd
    while _elongation(t - 1) < _elongation(t):
        t -= 1
    return _bisect(lambda x: _elongation(x) < 180, t - 1, t)


def new_moon_after(jd: float) -> float:
    t = jd
    while _elongation(t + 1) > _elongation(t):
        t += 1
    return _bisect(lambda x: _elongation(x) < 180, t, t + 1)


@dataclass(frozen=True)
class LunarMonth:
    name: str
    adhika: bool
    start: float
    end: float

    @property
    def label(self) -> str:
        return ("Adhika " if self.adhika else "") + self.name


def lunar_month(jd: float, ayanamsa: str = "lahiri") -> LunarMonth:
    """The amanta month containing jd, named for the sidereal sign the Sun
    enters during it (Mesha -> Chaitra).  A month with no ingress is adhika
    and borrows the next month's name.  Assuming the month instead of
    computing it is how a Bhadrapada gets mistaken for Ashwin in an adhika
    year, and Pitru Paksha gets missed."""
    start = new_moon_before(jd)
    end = new_moon_after(start + 1)
    a = positions(start, ayanamsa)["Sun"].sign
    b = positions(end, ayanamsa)["Sun"].sign
    if a == b:
        return LunarMonth(MASA[(a + 1) % 12], True, start, end)
    return LunarMonth(MASA[b], False, start, end)


def resolve_direction(value: str | float | None) -> str | None:
    """Compass point, or degrees snapped to the nearest of the eight."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in BEARING:
        return text
    try:
        degrees = float(text) % 360
    except ValueError as exc:
        raise ValueError(f"direction {value!r} is not a compass point or bearing") from exc
    return min(
        BEARING, key=lambda k: min(abs(BEARING[k] - degrees), 360 - abs(BEARING[k] - degrees))
    )


@dataclass
class Verdict:
    jd: float
    facts: dict[str, str]
    vetoes: list[str] = field(default_factory=list)
    defects: list[tuple[str, float]] = field(default_factory=list)
    supports: list[tuple[str, float]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.vetoes

    @property
    def score(self) -> float:
        """Lower is better; zero is a moment with nothing for or against."""
        return sum(w for _, w in self.defects) - sum(w for _, w in self.supports)


def evaluate(
    profile: Profile,
    d: Day,
    month: LunarMonth,
    jd: float,
    lat: float,
    lon: float,
    natal_moon,
    natal_lagna: int | None,
    *,
    toward: str | None = None,
    first_leg: str | None = None,
    ayanamsa: str = "lahiri",
    door: str | None = None,
    old_house: bool = False,
    planet_states: dict[str, str] | None = None,
    natal_month: str | None = None,
    eldest: bool = False,
) -> Verdict:
    """Judge one moment.  ``natal_moon`` (and ``natal_lagna``) may be None when
    no birth chart is known; the birth-relative rules (tara, chandrashtama,
    lagna 8th from birth, Moon 4th/12th from the birth Moon) are then skipped
    rather than guessed."""
    p = positions(jd, ayanamsa)
    moon = p["Moon"]
    elongation = (moon.longitude - p["Sun"].longitude) % 360
    t = int(elongation // 12) + 1
    n = (t - 1) % 15 + 1
    yoga = YOGA_NAMES[int(((p["Sun"].longitude + moon.longitude) % 360) // (360 / 27))]
    karana = _karana(elongation)
    asc = ascendant(jd, lat, lon, ayanamsa)[0]
    lagna = asc.sign
    nak = NAKSHATRAS[moon.nakshatra]
    w = WEEKDAY_INDEX[d.vara]
    hora, chog = d.at(d.horas, jd), d.at(d.choghadiyas, jd)
    tr = tara(natal_moon.nakshatra, moon.nakshatra) if natal_moon is not None else ""

    def house(g: str) -> int:
        return (p[g].sign - lagna) % 12 + 1

    v = Verdict(
        jd,
        {
            "vara": d.vara,
            "tithi": tithi_label(t),
            "nakshatra": nak,
            "yoga": yoga,
            "karana": karana,
            "lagna": SIGNS[lagna],
            "hora": hora.label if hora else "",
            "choghadiya": chog.label if chog else "",
            "tara": tr,
            "month": month.label,
        },
    )
    bad, good = v.defects.append, v.supports.append

    # Vetoes.  Day.avoid already holds the kalams, durmuhurta and the opening
    # ghatis of the bad yogas.
    v.vetoes += [a.label for a in d.avoid if a.contains(jd)]
    if karana == "Vishti" and bhadra_residence(moon.sign) == "earth":
        # MC 1.45: Bhadra's effect falls where it resides; in heaven or below, no
        # penalty. MC 1.44: its face is never used and its tail is auspicious; a
        # Bhadra in a tithi's second half is auspicious by day, in its first half
        # at night (research's reading; the lead's ruling of 15 Oct 2026).
        part = d.at(d.bhadra_parts, jd)
        first_half = elongation % 12 < 6
        by_day = d.sunrise <= jd < d.sunset
        if part and part.label == "face":
            v.vetoes.append("Bhadra's face (MC 1.44)")
        elif part and part.label == "tail":
            good(("Bhadra's tail: no penalty (MC 1.44)", 0.0))
        elif first_half != by_day:
            good((f"Bhadra {'by day' if by_day else 'at night'}: no penalty (MC 1.44)", 0.0))
        else:
            v.vetoes.append("Vishti (Bhadra on earth)")
    if t == 30:
        v.vetoes.append("Amavasya")
    elif n in ((4, 9, 14) if profile.home or profile.rikta_only else (4, 8, 9, 14)):
        v.vetoes.append(tithi_label(t))
    if nak in profile.barred_nakshatras:
        v.vetoes.append(f"{nak}: a selling star, barred for buying (MC 2.16-17)")
    if d.vara in profile.barred_varas:
        v.vetoes.append(f"{VARA_NAME[d.vara]}: not a riding weekday (MC 2.18 commentary)")
    # MC 1.30 counts 28 nakshatras (Monday's kana is Abhijit). Utpata and kana
    # carry marana's veto (the lead's ruling); siddhi is a support below.
    nak28 = nakshatra_28(moon.longitude)
    if UTPATA.get(w) == nak28:
        v.vetoes.append("Utpata yoga")
    if MARANA.get(w) == nak28:
        v.vetoes.append("Marana yoga")
    if KANA.get(w) == nak28:
        v.vetoes.append("Kana yoga")
    mahapata = d.at(d.mahapatas, jd)
    if mahapata:
        v.vetoes.append(f"Mahapata ({mahapata.label})")
    if DAGDHA.get(w) == nak:
        v.vetoes.append("Dagdha yoga")
    if house("Moon") == 8:
        v.vetoes.append("Moon in the 8th")
    if natal_moon is not None and moon_house(natal_moon.sign, moon.sign) == 8:
        v.vetoes.append("Chandrashtama")
    if profile.travel and toward and relative_side(toward, DISHA_SHOOL[d.vara]) == "front":
        v.vetoes.append(f"disha shool {DISHA_SHOOL[d.vara]}")

    if profile.home:
        _home_vetoes(v, month, p, moon, asc, house, n, door, old_house, planet_states, d.vara)
    if profile.mundan:
        _mundan_vetoes(v, month, p, moon, asc, house, t, d.vara, planet_states)
        _mundan_child(v, month, moon, asc, natal_moon, natal_lagna, natal_month, eldest)

    # Defects.
    if tr in BAD_TARA:
        bad((f"{tr} tara", 3.0))
    elif tr == "Janma":
        bad(("Janma tara", 2.0))
    pk = PANCHAKA.get(((moon.nakshatra + 1) + t + (w + 1) + (lagna + 1)) % 9)
    if pk:
        bad((pk.split(" (")[0], 3.0 if pk.startswith("Mrityu") else 2.0))
    for g in MALEFICS:
        if house(g) == 1:
            bad((f"{g} in the 1st", 2.0))
        elif house(g) == 7:
            bad((f"{g} in the 7th", 1.5))
    for g in p:
        if g != "Moon" and house(g) == 8:
            bad((f"{g} in the 8th", 2.0))
    eighths = set()
    if natal_lagna is not None:
        eighths.add((natal_lagna + 7) % 12)
    if natal_moon is not None:
        eighths.add((natal_moon.sign + 7) % 12)
    if lagna in eighths and not profile.mundan:  # a veto for the tonsure (MC 5.29)
        bad(("lagna 8th from birth", 1.5))
    if chog and chog.label not in CHOGHADIYA_GOOD:
        bad((f"{chog.label} choghadiya", 1.0))
    if hora and hora.label in profile.horas:
        good((f"{hora.label} hora", 0.5))
    elif hora and hora.label in ("Mars", "Saturn"):
        bad((f"{hora.label} hora", 0.5))
    if natal_moon is not None and moon_house(natal_moon.sign, moon.sign) in (4, 12):
        bad((f"Moon {moon_house(natal_moon.sign, moon.sign)}th from birth Moon", 1.0))
    if yoga in BAD_YOGA_GHATIS and not v.vetoes:
        bad((f"{yoga} yoga, past its opening", 0.5))
    stars = profile.nakshatras | (OLD_HOUSE_STARS if profile.home and old_house else set())
    if profile.barred_nakshatras and nak not in stars | profile.barred_nakshatras:
        bad((f"{nak}: not a buying star (MC 2.16)", profile.other_nakshatra))  # middling
    elif nak not in stars and not profile.mundan and not profile.barred_nakshatras:
        cls = NAKSHATRA_CLASS[nak]
        bad((f"{nak} ({cls})", profile.other_nakshatra + (profile.harsh if cls in HARSH else 0)))
    if t != 30 and n not in profile.tithis and n not in (4, 8, 9, 14) and not profile.mundan:
        bad((tithi_label(t), profile.other_tithi))
    vetoed_vara = (
        (profile.home and d.vara in HOME_BARRED_VARAS)
        or profile.mundan
        or d.vara in profile.barred_varas
    )
    if d.vara not in profile.varas and not vetoed_vara:
        bad((VARA_NAME[d.vara], profile.other_vara))
    if month.adhika and not profile.home:  # the home act vetoes it (MC 1.47)
        bad((f"adhika {month.name}", profile.season))
    if month.name == "Bhadrapada" and not month.adhika and t >= 16:
        bad(("Pitru Paksha", profile.season))

    # Supports. A siddhi (amrta) pair turns to visha on its tithi (MC 1.20-21) and
    # is avoided for its act (MC 1.22); it never lifts a veto (MC p. 35).
    if AMRITA_SIDDHI.get(w) == nak:
        if AMRITA_VISHA_TITHI[w] == n:
            v.vetoes.append("Visha yoga")
        elif AMRITA_ACT_BANS.get(profile.name) == w:
            v.vetoes.append(f"{VARA_NAME[d.vara]}-{nak} avoided for this act")
        else:
            good(("Amrita Siddhi", 1.5))
    if nak in SARVARTHA_SIDDHI.get(w, set()):
        good(("Sarvartha Siddhi", 1.0))
    if SIDDHI.get(w) == nak28:
        good(("Siddhi yoga", 1.0))
    lord = SIGN_LORDS[lagna]
    if house(lord) in (1, 4, 5, 7, 9, 10) and (
        p[lord].sign in OWN_SIGNS[lord] or p[lord].sign == EXALTATION[lord][0]
    ):
        good((f"lagna lord {lord} strong", 0.5))
    if any(house(g) in (1, 4, 7, 10) for g in ("Jupiter", "Venus", "Mercury")):
        good(("benefic in a kendra", 0.5))
    south = any(x and relative_side(x, "S") == "front" for x in (toward, first_leg))
    if d.abhijit.contains(jd) and d.vara != "Mercury" and not (profile.travel and south):
        good(("Abhijit", 1.0))

    if profile.travel and toward:
        side = relative_side(toward, moon_direction(moon.sign))
        if side == "back":
            bad(("Moon behind (Chandra vasa)", 3.0))
        elif side == "left":
            bad(("Moon on the left", 1.5))
        else:
            good((f"Moon {'ahead' if side == 'front' else 'on the right'}", 0.5))
        yside = relative_side(toward, yogini_direction(t, almanac=True))
        if yside in ("front", "right"):
            bad((f"Yogini {yside}", 1.5))
        else:
            good((f"Yogini {yside}", 0.5))
        if first_leg and relative_side(first_leg, DISHA_SHOOL[d.vara]) == "front":
            bad((f"disha shool {DISHA_SHOOL[d.vara]} on the first leg", 1.5))
        if chog and chog.label == "Char":
            good(("Char choghadiya", 0.5))
        if lagna in (0, 3, 6, 9):
            good(("movable lagna", 0.5))
    if profile.home and lagna in (1, 4, 7, 10):
        good(("fixed lagna", 0.5))  # MC 13.1 ("sthire"); dual signs are allowed (Vasishtha)
    return v


# MC 13 (griha-pravesh.md; the lead's rulings of 15 Oct 2026).
HOME_BEST = {"Magha", "Phalguna", "Vaishakha", "Jyeshtha"}  # in uttarayana
HOME_MIDDLING = {"Kartika", "Margashirsha"}  # Narada: for necessity
UTTARAYANA = {9, 10, 11, 0, 1, 2}  # the Sun in Capricorn to Gemini
MOVABLE = {0, 3, 6, 9}
OLD_HOUSE_STARS = {"Shatabhisha", "Pushya", "Swati", "Dhanishta"}  # MC 13.2
HOME_BARRED_VARAS = {"Sun", "Mars"}  # MC 13.4: "vy-arkari", without Sunday and Tuesday
DOOR_TITHIS = {"E": {5, 10, 15}, "S": {1, 6, 11}, "W": {2, 7, 12}, "N": {3, 8, 13}}  # MC 13.5
DOOR_SUN = {  # the Sun "on the left": the five houses from the 8th, 5th, 2nd or 11th
    "E": {8, 9, 10, 11, 12}, "S": {5, 6, 7, 8, 9}, "W": {2, 3, 4, 5, 6}, "N": {11, 12, 1, 2, 3},
}  # fmt: skip


def _home_vetoes(v, month, p, moon, asc, house, n, door, old_house, planet_states, vara) -> None:
    """House entry (MC 13): the month (13.1, 13.4; Guru on the Sun's sign), Jupiter
    and Venus (1.46-48, 5.27; not for an old house, 13.2), no Sunday or Tuesday, no
    movable lagna or navamsa and the 4th and 8th empty (13.4), the Moon not in the
    1st, 6th or 12th (the 8th is vetoed for every act), the pot chakra (13.6), and
    with a door direction its tithi class and the Sun on the left (13.4-5)."""
    sun = p["Sun"].sign
    if vara in HOME_BARRED_VARAS:
        v.vetoes.append(f"{VARA_NAME[vara]} (MC 13.4)")
    if month.adhika:
        v.vetoes.append(f"adhika {month.name} (MC 1.47)")
    if month.name in ("Chaitra", "Ashadha"):
        v.vetoes.append(f"{month.name}: no house entry (MC 13.4)")
    elif month.name in HOME_BEST:
        if sun not in UTTARAYANA:
            v.vetoes.append("dakshinayana (MC 13.1)")
    elif month.name in HOME_MIDDLING or (old_house and month.name == "Shravana"):
        if not old_house:
            v.defects.append(("middling month for house entry (Narada)", 1.5))
    else:
        v.vetoes.append(f"{month.name}: no house entry (MC 13.1)")
    if sun in (3, 5, 10):
        v.vetoes.append(f"Sun in {SIGNS[sun]} (Guru, MC 13.1)")
    if not old_house:
        for g, state in sorted((planet_states or {}).items()):
            v.vetoes.append(f"{g} {state} (MC 1.46-48, 5.27)")
        if p["Jupiter"].sign in (4, 9):
            v.vetoes.append(f"Jupiter in {SIGNS[p['Jupiter'].sign]} (MC 1.48)")
    if asc.sign in MOVABLE:
        v.vetoes.append("movable lagna (MC 13.4)")
    elif int(asc.longitude // (30 / 9)) % 12 in MOVABLE:
        v.vetoes.append("movable navamsa (MC 13.4)")
    held = [g for g in p if house(g) in (4, 8) and not (g == "Moon" and house(g) == 8)]
    if held:
        v.vetoes.append(f"{', '.join(held)} in the 4th or 8th (MC 13.4)")
    if house("Moon") in (1, 6, 12):
        v.vetoes.append(f"Moon in the {ORDINAL[house('Moon')]} (MC 13.3-4)")
    count = (moon.nakshatra - p["Sun"].nakshatra) % 27 + 1
    if count <= 5 or 14 <= count <= 21:
        v.vetoes.append(f"pot chakra {count} (MC 13.6)")
    if door:
        if n not in DOOR_TITHIS[door]:
            v.vetoes.append(f"tithi not for a {door} door (MC 13.5)")
        if house("Sun") not in DOOR_SUN[door]:
            v.vetoes.append(f"Sun not on the left for a {door} door (MC 13.4-5)")


ORDINAL = {1: "1st", 6: "6th", 12: "12th"}
BENEFIC_SIGNS = {
    1,
    2,
    3,
    5,
    6,
    8,
    11,
}  # Kashyapa in MC 5.29: Mercury's, the Moon's, Venus's, Jupiter's
MUNDAN_TITHIS = {2, 3, 5, 7, 10, 11, 13}


def _mundan_vetoes(v, month, p, moon, asc, house, t, vara, planet_states) -> None:
    """The first tonsure (MC 5.26-30; DS p. 137): the Sun's northern course and not
    Caitra (5.29) or an adhika month (1.47); Jupiter and Venus clear (5.26-27) and
    Jupiter not in Leo or Capricorn (1.48); the twelve stars, tithis 2, 3, 5, 7, 10,
    11, 13 and the weekdays of Mercury, Jupiter, Venus and (bright fortnight only)
    the Moon (5.29; Parashara); a benefic's lagna and navamsa, the 8th empty but for
    Venus, and no waning Moon, Mars, Saturn or Sun in a kendra (5.29-30)."""
    if month.adhika:
        v.vetoes.append(f"adhika {month.name} (MC 1.47)")
    if month.name == "Chaitra":
        v.vetoes.append("Chaitra: no tonsure (MC 5.29)")
    if p["Sun"].sign not in UTTARAYANA:
        v.vetoes.append("dakshinayana (MC 5.26, 5.29)")
    for g, state in sorted((planet_states or {}).items()):
        v.vetoes.append(f"{g} {state} (MC 5.26-27)")
    if p["Jupiter"].sign in (4, 9):
        v.vetoes.append(f"Jupiter in {SIGNS[p['Jupiter'].sign]} (MC 1.48)")
    nak = NAKSHATRAS[moon.nakshatra]
    if nak not in MUNDAN_STARS:
        v.vetoes.append(f"{nak}: not a tonsure star (MC 5.29)")
    if (t - 1) % 15 + 1 not in MUNDAN_TITHIS:
        v.vetoes.append(f"{tithi_label(t)}: not a tonsure tithi (MC 5.29)")
    if vara not in ("Moon", "Mercury", "Jupiter", "Venus") or (vara == "Moon" and t > 15):
        v.vetoes.append(f"{VARA_NAME[vara]}: not a tonsure weekday (MC 5.29; Parashara)")
    if asc.sign not in BENEFIC_SIGNS:
        v.vetoes.append(f"{SIGNS[asc.sign]} lagna: not a benefic's (MC 5.29)")
    elif (nav := int(asc.longitude // (30 / 9)) % 12) not in BENEFIC_SIGNS:
        v.vetoes.append(f"{SIGNS[nav]} navamsa: not a benefic's (MC 5.29)")
    held = [g for g in p if house(g) == 8 and g != "Venus"]
    if held:
        v.vetoes.append(f"{', '.join(held)} in the 8th (MC 5.29)")
    bad = ["Sun", "Mars", "Saturn"] + ([] if 9 <= t <= 22 else ["Moon"])
    hit = [g for g in bad if house(g) in (1, 4, 7, 10)]
    if hit:
        v.vetoes.append(f"{', '.join(hit)} in a kendra (MC 5.30)")


def _mundan_child(v, month, moon, asc, natal_moon, natal_lagna, natal_month, eldest) -> None:
    """The child's own rules, when known: not the birth star (DS p. 137; Kashyapa
    allows it for a Vedic tonsure, MC p. 190), not the birth month (Rajamartanda, MC
    p. 190), not the 8th sign from the birth lagna or Moon sign (MC 5.29), and no
    Jyeshtha for an eldest child (Ratnamala, MC 5.33 commentary)."""
    if natal_moon is not None and natal_moon.nakshatra == moon.nakshatra:
        v.vetoes.append("the child's birth star (DS p. 137)")
    if natal_month and natal_month == month.name:
        v.vetoes.append("the child's birth month (MC p. 190)")
    eighths = set()
    if natal_lagna is not None:
        eighths.add((natal_lagna + 7) % 12)
    if natal_moon is not None:
        eighths.add((natal_moon.sign + 7) % 12)
    if asc.sign in eighths:
        v.vetoes.append("lagna 8th from the child's birth (MC 5.29)")
    if eldest and month.name == "Jyeshtha":
        v.vetoes.append("Jyeshtha, for an eldest child (MC 5.33 commentary)")


def check(
    profile: Profile,
    jd: float,
    lat: float,
    lon: float,
    natal_moon,
    natal_lagna: int | None,
    **kw,
) -> Verdict:
    """One moment, for "can I do it now?"."""
    ayanamsa = kw.get("ayanamsa", "lahiri")
    tz = kw.pop("tz", None)
    d = day(jd, lat, lon, ayanamsa, tz)
    if (profile.home and not kw.get("old_house")) or profile.mundan:
        states = planet_states_around(jd, jd, lat, lon)
        kw["planet_states"] = states.get(round(d.sunrise * 1440), {})
    return evaluate(
        profile,
        d,
        lunar_month(jd, ayanamsa),
        jd,
        lat,
        lon,
        natal_moon,
        natal_lagna,
        **kw,
    )


@dataclass
class Choice:
    start: float
    end: float
    score: float
    facts: dict[str, str]
    defects: list[tuple[str, float]]
    supports: list[tuple[str, float]]
    key: tuple = field(default=(), repr=False)


def _in_hours(jd: float, tz, hours: tuple[int, int]) -> bool:
    local = to_datetime(jd, tz)
    m = local.hour * 60 + local.minute
    h0, h1 = hours
    return h0 <= m < h1 if h0 <= h1 else (m >= h0 or m < h1)


def parse_hours(text: str) -> tuple[int, int]:
    """'08:00-20:00' as minutes of the local day."""
    try:
        a, b = (x.strip().split(":") for x in text.split("-"))
        return int(a[0]) * 60 + int(a[1]), int(b[0]) * 60 + int(b[1])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"hours {text!r} must look like 08:00-20:00") from exc


def find(
    profile: Profile,
    start: float,
    end: float,
    lat: float,
    lon: float,
    natal_moon,
    natal_lagna: int | None,
    *,
    tz=0.0,
    hours: tuple[int, int] | None = None,
    toward: str | None = None,
    first_leg: str | None = None,
    ayanamsa: str = "lahiri",
    step_minutes: int = 1,
    min_minutes: int = 5,
    door: str | None = None,
    old_house: bool = False,
    natal_month: str | None = None,
    eldest: bool = False,
) -> list[Choice]:
    """Unvetoed windows in [start, end), best score first.

    Every minute is judged on its own: tara, the vara-nakshatra pairings and
    the rest are read at that minute, never at a noon snapshot, because a
    nakshatra or tithi that ends at 09:37 decides the morning.
    """
    if profile.travel and not toward:
        raise ValueError("a travel search needs the destination direction (--toward)")
    step = step_minutes / 1440
    d, month = day(start, lat, lon, ayanamsa, tz), lunar_month(start, ayanamsa)
    wanted = (profile.home and not old_house) or profile.mundan
    states = planet_states_around(start, end, lat, lon) if wanted else {}
    out: list[Choice] = []
    t = start
    while t < end:
        if t >= d.next_sunrise:
            d = day(t, lat, lon, ayanamsa, tz)
        if t >= month.end:
            month = lunar_month(t, ayanamsa)
        if hours is None or _in_hours(t, tz, hours):
            v = evaluate(
                profile,
                d,
                month,
                t,
                lat,
                lon,
                natal_moon,
                natal_lagna,
                toward=toward,
                first_leg=first_leg,
                ayanamsa=ayanamsa,
                door=door,
                old_house=old_house,
                planet_states=states.get(round(d.sunrise * 1440), {}),
                natal_month=natal_month,
                eldest=eldest,
            )
            if v.ok:
                key = (tuple(v.defects), tuple(v.supports), tuple(v.facts.items()))
                last = out[-1] if out else None
                if last and last.key == key and abs(last.end - t) < step / 2:
                    last.end = t + step
                else:
                    out.append(Choice(t, t + step, v.score, v.facts, v.defects, v.supports, key))
        t += step
    keep = [c for c in out if (c.end - c.start) * 1440 >= min_minutes - 1e-6]
    return sorted(keep, key=lambda c: (c.score, c.start))


def verdict_report(v: Verdict, tz, profile: Profile) -> str:
    when = to_datetime(v.jd, tz).strftime("%a %d %b %Y %H:%M")
    f = v.facts
    head = f"{when}  {profile.name}: " + (
        "NOT NOW -- " + ", ".join(v.vetoes) if v.vetoes else f"acceptable, score {v.score:+.1f}"
    )
    lines = [
        head,
        f"  {f['tithi']}, {f['nakshatra']} ({f['tara']} tara), {f['yoga']}, {f['karana']}, "
        f"{f['lagna']} lagna, {f['hora']} hora, {f['choghadiya']}, {f['month']}",
    ]
    if v.supports:
        lines.append("  + " + ", ".join(label for label, _ in v.supports))
    if v.defects:
        lines.append("  - " + ", ".join(f"{label} ({w:g})" for label, w in v.defects))
    return "\n".join(lines)


def find_report(choices: list[Choice], tz, profile: Profile) -> str:
    lines = [f"{profile.name}: {profile.about}"]
    if not choices:
        lines.append("  no unvetoed window in this span")
    for i, c in enumerate(choices, 1):
        f = c.facts
        a, b = to_datetime(c.start, tz), to_datetime(c.end, tz)
        lines.append(
            f"{i:2d}. {a:%a %d %b %H:%M}-{b:%H:%M}  score {c.score:+.1f}  "
            f"{f['lagna']} lagna, {f['hora']} hora, {f['choghadiya']}"
        )
        lines.append(
            f"      {f['tithi']}, {f['nakshatra']} ({f['tara']} tara), {f['yoga']}, "
            f"{f['karana']}, {f['month']}"
        )
        if c.supports:
            lines.append("      + " + ", ".join(label for label, _ in c.supports))
        if c.defects:
            lines.append("      - " + ", ".join(f"{label} ({w:g})" for label, w in c.defects))
    return "\n".join(lines)
