"""The rarer apparatus: chakras, kicks, birds and the fine divisions.

Techniques that survive mostly in regional and manuscript traditions rather
than the standard textbooks -- Sarvatobhadra and Kota chakras, Bhrigu Bindu,
Moorthi Nirnaya, Latta, Pancha Pakshi, Ghataka, the shashtiamsa deities and
the 150 nadi amsas.

They are here because they are the most *specific* things the tradition
offers: several resolve to a single day rather than a season, which makes
them the easiest to falsify and therefore the most worth having.
"""

from __future__ import annotations

from . import panchanga as P
from .ashtakavarga import BAV_RULES
from .chart import SIGN_LORDS, Chart
from .ephemeris import NAKSHATRAS, SEVEN, SIGNS, positions

NAK28 = NAKSHATRAS[:21] + ["Abhijit"] + NAKSHATRAS[21:]


def _location(
    chart: Chart,
    observer_lat: float | None,
    observer_lon: float | None,
) -> tuple[float, float]:
    if (observer_lat is None) != (observer_lon is None):
        raise ValueError("observer latitude and longitude must be supplied together")
    return (
        chart.lat if observer_lat is None else observer_lat,
        chart.lon if observer_lon is None else observer_lon,
    )


# --- Sarvatobhadra chakra ---------------------------------------------------

# The classical *symmetric* nakshatra-vedha pair list, which is a different
# relation from the chakra's own geometry and is kept only under that name.
# Sources disagree on roughly half of it -- everything from Magha onward
# varies -- so it is not used for scoring.  The real chakra, whose three
# directional rays are neither symmetric nor reducible to pairs, lives in
# ``sbc.py`` and is checked cell by cell against an independent reference.
NAKSHATRA_PAIRS = [
    ("Ashwini", "Jyeshtha"),
    ("Bharani", "Anuradha"),
    ("Krittika", "Vishakha"),
    ("Rohini", "Swati"),
    ("Mrigashira", "Chitra"),
    ("Ardra", "Hasta"),
    ("Punarvasu", "U.Phalguni"),
    ("Pushya", "P.Phalguni"),
    ("Ashlesha", "Magha"),
    ("Mula", "Revati"),
    ("P.Ashadha", "U.Bhadrapada"),
    ("U.Ashadha", "P.Bhadrapada"),
    ("Abhijit", "Shatabhisha"),
    ("Shravana", "Dhanishta"),
]


def sarvatobhadra(chart: Chart, jd: float) -> list[dict]:
    """Which natal-sensitive cells are being pierced today."""
    from . import sbc

    out = []
    for h in sbc.strikes(chart, jd):
        out.append(
            {
                "graha": h.graha,
                "arm": h.arm,
                "transiting": sbc.nak28_of(
                    positions(jd, chart.ayanamsa, chart.node)[h.graha].longitude
                ),
                "pierces": sbc.CONTENT[h.cell],
                "what": h.target,
                "kind": h.kind,
                "malefic": not h.benefic,
            }
        )
    return out


# --- Kota chakra ------------------------------------------------------------

KOTA_RINGS = ["Stambha (inner pillar)", "Madhya (middle)", "Prakara (rampart)", "Bahya (outer)"]


def kota_chakra(chart: Chart, jd: float) -> dict:
    """The fort. Twenty-eight nakshatras from the janma nakshatra form four
    concentric rings; a malefic moving inward is an assault, outward relief."""
    janma = chart.grahas["Moon"].nakshatra
    moving = positions(jd, chart.ayanamsa, chart.node)
    rows = []
    for g in SEVEN + ["Rahu", "Ketu"]:
        offset = (moving[g].nakshatra - janma) % 27
        ring = KOTA_RINGS[min(offset // 7, 3)]
        rows.append(
            {
                "graha": g,
                "offset": offset + 1,
                "ring": ring,
                "inward": offset < 7,
                "malefic": g in ("Sun", "Mars", "Saturn", "Rahu", "Ketu"),
            }
        )
    swami = SIGN_LORDS[chart.grahas["Moon"].sign]
    return {
        "kota_swami": swami,
        "entries": rows,
        "under_siege": [r for r in rows if r["malefic"] and r["inward"]],
    }


# --- Bhrigu Bindu -----------------------------------------------------------


def bhrigu_bindu(chart: Chart) -> float:
    """Midpoint of Rahu and the Moon, taken along the arc from Rahu.

    Not in the standard textbooks at all, but heavily used in the Bhrigu
    lineages, where transits over it are held to be decisive.
    """
    rahu = chart.grahas["Rahu"].longitude
    moon = chart.grahas["Moon"].longitude
    return (rahu + ((moon - rahu) % 360) / 2.0) % 360


def bhrigu_hits(chart: Chart, jd: float, orb: float = 3.0) -> list[dict]:
    bb = bhrigu_bindu(chart)
    moving = positions(jd, chart.ayanamsa, chart.node)
    out = []
    for g in SEVEN + ["Rahu", "Ketu"]:
        sep = abs((moving[g].longitude - bb + 180) % 360 - 180)
        if sep <= orb:
            out.append({"graha": g, "orb": sep})
    return out


# --- Moorthi nirnaya --------------------------------------------------------

MURTI = ["Swarna (gold)", "Rajata (silver)", "Tamra (copper)", "Loha (iron)"]
MURTI_VALUE = {0: 1.0, 1: 0.66, 2: 0.33, 3: 0.0}


def moorthi(chart: Chart, jd: float) -> dict[str, str]:
    """The metal of a transit: counted from the janma nakshatra to the
    nakshatra the graha occupied when it entered its present sign.

    Gold delivers the full result of the transit, iron almost none.
    """
    janma = chart.grahas["Moon"].nakshatra
    moving = positions(jd, chart.ayanamsa, chart.node)
    out = {}
    for g in ("Jupiter", "Saturn", "Mars", "Rahu", "Ketu"):
        count = (moving[g].nakshatra - janma) % 27 + 1
        out[g] = MURTI[(count - 1) % 4]
    return out


# --- Latta ------------------------------------------------------------------

# Each graha kicks a nakshatra a fixed count away; forward for some, back for
# others.  The struck nakshatra is spoiled for the duration.
LATTA = {
    "Sun": 12,
    "Moon": 22,
    "Mars": -3,
    "Mercury": 7,
    "Jupiter": 6,
    "Venus": -5,
    "Saturn": -8,
    "Rahu": -9,
    "Ketu": -9,
}


def latta(chart: Chart, jd: float) -> list[dict]:
    janma = chart.grahas["Moon"].nakshatra
    moving = positions(jd, chart.ayanamsa, chart.node)
    out = []
    for g, step in LATTA.items():
        struck = (moving[g].nakshatra + step) % 27
        if struck == janma:
            out.append(
                {
                    "graha": g,
                    "step": step,
                    "from": NAKSHATRAS[moving[g].nakshatra],
                    "strikes": NAKSHATRAS[struck],
                }
            )
    return out


# --- Pancha Pakshi ----------------------------------------------------------

BIRDS = ["Vulture", "Owl", "Crow", "Cock", "Peacock"]
BIRD_BY_NAK = [0] * 5 + [1] * 6 + [2] * 5 + [3] * 5 + [4] * 6
ACTIVITIES = ["Rule", "Eat", "Walk", "Sleep", "Die"]
ACTIVITY_VALUE = {"Rule": 1.0, "Eat": 0.8, "Walk": 0.5, "Sleep": 0.2, "Die": 0.0}


def pancha_pakshi(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> dict:
    """The five-bird system: which bird you are, and what it is doing now.

    From the Tamil siddha tradition rather than the Sanskrit textbooks.  The
    day and night are each cut into five parts and the bird's activity in each
    is read as the quality of that stretch.
    """
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    nak = chart.grahas["Moon"].nakshatra
    idx = BIRD_BY_NAK[nak]
    if pc.paksha == "krishna":
        idx = (idx + 2) % 5  # the dark half reverses the order
    bird = BIRDS[idx]

    if pc.is_day_birth:
        start, span, is_day = pc.sunrise, (pc.sunset - pc.sunrise) / 5.0, True
    else:
        start, span, is_day = pc.sunset, (pc.next_sunrise - pc.sunset) / 5.0, False
    part = min(int((jd - start) / span), 4) if span > 0 else 0
    activity = ACTIVITIES[(idx + part) % 5]
    return {
        "bird": bird,
        "part": part + 1,
        "half": "day" if is_day else "night",
        "activity": activity,
        "value": ACTIVITY_VALUE[activity],
    }


# --- Ghataka ----------------------------------------------------------------

# Harmful rashi, nakshatra, tithi and vara for each janma rashi.
GHATAKA = {
    0: {"rashi": 4, "vara": "Sunday", "nak": 15, "tithi": 12},
    1: {"rashi": 5, "vara": "Saturday", "nak": 18, "tithi": 11},
    2: {"rashi": 6, "vara": "Monday", "nak": 21, "tithi": 10},
    3: {"rashi": 7, "vara": "Wednesday", "nak": 24, "tithi": 9},
    4: {"rashi": 8, "vara": "Saturday", "nak": 0, "tithi": 8},
    5: {"rashi": 9, "vara": "Thursday", "nak": 3, "tithi": 7},
    6: {"rashi": 10, "vara": "Friday", "nak": 6, "tithi": 6},
    7: {"rashi": 11, "vara": "Wednesday", "nak": 9, "tithi": 5},
    8: {"rashi": 0, "vara": "Tuesday", "nak": 12, "tithi": 4},
    9: {"rashi": 1, "vara": "Friday", "nak": 15, "tithi": 3},
    10: {"rashi": 2, "vara": "Thursday", "nak": 18, "tithi": 2},
    11: {"rashi": 3, "vara": "Tuesday", "nak": 21, "tithi": 1},
}


def ghataka(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> list[str]:
    """Which of the four ghataka conditions are live today."""
    g = GHATAKA[chart.grahas["Moon"].sign]
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    moving = positions(jd, chart.ayanamsa, chart.node)
    hits = []
    if moving["Moon"].sign == g["rashi"]:
        hits.append(f"ghataka rashi ({SIGNS[g['rashi']]})")
    if moving["Moon"].nakshatra == g["nak"]:
        hits.append(f"ghataka nakshatra ({NAKSHATRAS[g['nak']]})")
    weekday = {
        "Sun": "Sunday",
        "Moon": "Monday",
        "Mars": "Tuesday",
        "Mercury": "Wednesday",
        "Jupiter": "Thursday",
        "Venus": "Friday",
        "Saturn": "Saturday",
    }[pc.vara]
    if weekday == g["vara"]:
        hits.append(f"ghataka vara ({weekday})")
    if (pc.tithi - 1) % 15 + 1 == g["tithi"]:
        hits.append(f"ghataka tithi ({g['tithi']})")
    return hits


# --- prastara ashtakavarga --------------------------------------------------


def prastara(chart: Chart, planet: str) -> dict:
    """The full grid: which reference point contributed each bindu.

    Ordinary software prints only the totals; the prastara is what lets you
    see *why* a sign is strong, and it is what kakshya judgement needs.
    """
    refs = {n: chart.grahas[n].sign for n in SEVEN}
    refs["Asc"] = chart.asc.sign
    grid = {}
    for ref, houses in BAV_RULES[planet].items():
        base = refs[ref]
        grid[ref] = [1 if ((s - base) % 12 + 1) in houses else 0 for s in range(12)]
    return grid


# --- fine divisions ---------------------------------------------------------

# The sixty shashtiamsa deities, in order; roughly half are malefic.
SHASHTIAMSA = [
    ("Ghora", 0),
    ("Rakshasa", 0),
    ("Deva", 1),
    ("Kubera", 1),
    ("Yaksha", 1),
    ("Kinnara", 1),
    ("Bhrashta", 0),
    ("Kulaghna", 0),
    ("Garala", 0),
    ("Agni", 0),
    ("Maya", 0),
    ("Purishaka", 0),
    ("Apampathi", 1),
    ("Marutwan", 1),
    ("Kaala", 0),
    ("Sarpa", 0),
    ("Amrita", 1),
    ("Indu", 1),
    ("Mridu", 1),
    ("Komala", 1),
    ("Heramba", 1),
    ("Brahma", 1),
    ("Vishnu", 1),
    ("Maheshwara", 1),
    ("Deva", 1),
    ("Ardra", 0),
    ("Kalinasa", 0),
    ("Kshiteesa", 1),
    ("Kamalakara", 1),
    ("Gulika", 0),
    ("Mrityu", 0),
    ("Kaala", 0),
    ("Davagni", 0),
    ("Ghora", 0),
    ("Yama", 0),
    ("Kantaka", 0),
    ("Sudha", 1),
    ("Amrita", 1),
    ("Purnachandra", 1),
    ("Vishadagdha", 0),
    ("Kulanasa", 0),
    ("Vamshakshaya", 0),
    ("Utpata", 0),
    ("Kaala", 0),
    ("Saumya", 1),
    ("Komala", 1),
    ("Sheetala", 1),
    ("Karaladamshtra", 0),
    ("Chandramukhi", 1),
    ("Praveena", 1),
    ("Kaalapavaka", 0),
    ("Dhannayudha", 0),
    ("Nirmala", 1),
    ("Saumya", 1),
    ("Kroora", 0),
    ("Atisheetala", 1),
    ("Amrita", 1),
    ("Payodhi", 1),
    ("Bhramana", 0),
    ("Chandrarekha", 1),
]


def shashtiamsa(longitude: float) -> tuple[str, bool]:
    """Which of the sixty deities holds a degree, and whether it is benign."""
    deg = longitude % 30
    idx = int(deg * 2) % 60
    name, good = SHASHTIAMSA[idx]
    return name, bool(good)


def nadi_amsa(longitude: float) -> int:
    """The 150 nadi amsas: the finest division in use, 12 arcminutes wide.

    At this resolution a birth time wrong by ninety seconds changes the
    answer, which is exactly why nadi practitioners rectify first.
    """
    return int((longitude % 30) / (30.0 / 150)) + 1


# --- daily inauspicious spans -----------------------------------------------

RAHU_KALAM_PART = {
    "Sunday": 8,
    "Monday": 2,
    "Tuesday": 7,
    "Wednesday": 5,
    "Thursday": 6,
    "Friday": 4,
    "Saturday": 3,
}
YAMA_PART = {
    "Sunday": 5,
    "Monday": 4,
    "Tuesday": 3,
    "Wednesday": 2,
    "Thursday": 1,
    "Friday": 7,
    "Saturday": 6,
}
GULIKA_PART = {
    "Sunday": 7,
    "Monday": 6,
    "Tuesday": 5,
    "Wednesday": 4,
    "Thursday": 3,
    "Friday": 2,
    "Saturday": 1,
}


def daily_kalas(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> dict:
    """Rahu kalam, Yamaganda and Gulika kalam: eighths of the daylight span."""
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    weekday = {
        "Sun": "Sunday",
        "Moon": "Monday",
        "Mars": "Tuesday",
        "Mercury": "Wednesday",
        "Jupiter": "Thursday",
        "Venus": "Friday",
        "Saturn": "Saturday",
    }[pc.vara]
    span = (pc.sunset - pc.sunrise) / 8.0
    out = {}
    for name, table in (
        ("Rahu kalam", RAHU_KALAM_PART),
        ("Yamaganda", YAMA_PART),
        ("Gulika kalam", GULIKA_PART),
    ):
        i = table[weekday] - 1
        out[name] = (pc.sunrise + i * span, pc.sunrise + (i + 1) * span)
    return out


# --- nakshatra-and-weekday combinations ------------------------------------

# Weekday index 0 = Sunday.  These pairings are the muhurta tradition's
# strongest single-day verdicts, good and bad.
# Siddhi (amrta) pairs: Narada, quoted in Muhurta Chintamani 1.21's commentary
# (1945 printing, p. 20).
AMRITA_SIDDHI = {
    0: "Hasta",
    1: "Mrigashira",
    2: "Ashwini",
    3: "Anuradha",
    4: "Pushya",
    5: "Revati",
    6: "Rohini",
}
# MC 1.20-21 (pp. 19-20): each pair turns to visha on one tithi of either paksha.
AMRITA_VISHA_TITHI = {0: 5, 1: 6, 2: 7, 3: 8, 4: 9, 5: 10, 6: 11}
# MC 1.22 (p. 20): the pair to avoid for entering a house, a journey, a marriage.
AMRITA_ACT_BANS = {"home": 2, "travel": 6, "marriage": 4}
# The Mrtyu column of MC 1.30 (p. 23).
MARANA = {
    0: "Anuradha",
    1: "U.Ashadha",
    2: "Shatabhisha",
    3: "Ashwini",
    4: "Mrigashira",
    5: "Ashlesha",
    6: "Hasta",
}
# The other columns of MC 1.30 (p. 23). From Sunday, four nakshatras each from
# Vishakha, P.Ashadha, Dhanishta, Revati, Rohini, Pushya and U.Phalguni are utpata,
# mrtyu (MARANA), kana and siddhi. Monday's kana is Abhijit, the 28th nakshatra,
# which these 27-nakshatra tables leave out.
UTPATA = {
    0: "Vishakha",
    1: "P.Ashadha",
    2: "Dhanishta",
    3: "Revati",
    4: "Rohini",
    5: "Pushya",
    6: "U.Phalguni",
}
KANA = {
    0: "Jyeshtha",
    1: "Abhijit",
    2: "P.Bhadrapada",
    3: "Bharani",
    4: "Ardra",
    5: "Magha",
    6: "Chitra",
}
# Abhijit, the 28th nakshatra: the last quarter of U.Ashadha and the first fifteenth
# of Shravana (Muhurta-martanda 1909, travel v. 4, p. 139), in sidereal degrees.
ABHIJIT = (276 + 40 / 60, 280 + 53 / 60 + 20 / 3600)


def nakshatra_28(longitude: float) -> str:
    """The nakshatra of a sidereal longitude, with Abhijit carved out of its two
    neighbours, as MC 1.30's 28-nakshatra count needs."""
    if ABHIJIT[0] <= longitude < ABHIJIT[1]:
        return "Abhijit"
    return NAKSHATRAS[int(longitude // (360 / 27)) % 27]


SIDDHI = {
    0: "Mula",
    1: "Shravana",
    2: "U.Bhadrapada",
    3: "Krittika",
    4: "Punarvasu",
    5: "P.Phalguni",
    6: "Swati",
}
# MC 1.27 (p. 22): the Moon's nakshatra the 4th, 9th, 6th, 10th, 13th or 20th from the Sun's.
RAVI_YOGA_COUNTS = frozenset({4, 6, 9, 10, 13, 20})
# Narada in MC 1.5's commentary (p. 13).
DAGDHA = {
    0: "Bharani",
    1: "Chitra",
    2: "U.Ashadha",
    3: "Dhanishta",
    4: "U.Phalguni",
    5: "Jyeshtha",
    6: "Revati",
}
# MC 1.28-29 (p. 22), the main reading. The commentary (p. 23) notes that the two
# verses have no sage-text basis and that later digests list more or fewer.
SARVARTHA_SIDDHI = {
    0: {"Hasta", "Mula", "U.Ashadha", "U.Phalguni", "U.Bhadrapada", "Pushya", "Ashwini"},
    1: {"Rohini", "Mrigashira", "Pushya", "Anuradha", "Shravana"},
    2: {"Ashwini", "U.Bhadrapada", "Krittika", "Ashlesha"},
    3: {"Rohini", "Mrigashira", "Krittika", "Anuradha", "Hasta"},
    4: {"Ashwini", "Punarvasu", "Pushya", "Anuradha", "Revati"},
    5: {"Ashwini", "Punarvasu", "P.Phalguni", "Shravana", "Revati"},
    6: {"Rohini", "Swati", "Shravana"},
}
# MC's footnoted variant reads Anuradha for P.Phalguni on Friday.
SARVARTHA_SIDDHI_VARIANT = {5: {"Anuradha"}}
_WEEKDAY = {"Sun": 0, "Moon": 1, "Mars": 2, "Mercury": 3, "Jupiter": 4, "Venus": 5, "Saturn": 6}


def vara_nakshatra_yogas(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> list[str]:
    """The weekday-plus-nakshatra verdicts of the muhurta tradition."""
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    w = _WEEKDAY[pc.vara]
    nak = pc.nakshatra_name
    out = []
    if AMRITA_SIDDHI.get(w) == nak:
        out.append("Amrita Siddhi (nectar) - one of the best days in the cycle")
    if nak in SARVARTHA_SIDDHI.get(w, set()):
        out.append("Sarvartha Siddhi - all undertakings supported")
    if MARANA.get(w) == nak:
        out.append("Marana yoga - avoid beginnings")
    if DAGDHA.get(w) == nak:
        out.append("Dagdha (burnt) yoga - efforts consumed")
    return out


# --- panchaka ---------------------------------------------------------------

PANCHAKA = {
    1: "Mrityu panchaka (danger)",
    2: "Agni panchaka (fire, loss)",
    4: "Raja panchaka (contention with authority)",
    6: "Chora panchaka (theft)",
    8: "Roga panchaka (illness)",
}


def panchaka(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> str:
    """The five-fold defect: nakshatra, tithi, weekday and rising sign summed."""
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    from .ephemeris import ascendant

    asc, _ = ascendant(jd, lat, lon, chart.ayanamsa)
    total = (pc.nakshatra + 1) + pc.tithi + (_WEEKDAY[pc.vara] + 1) + (asc.sign + 1)
    return PANCHAKA.get(total % 9, "clear of panchaka")


# --- chogadiya --------------------------------------------------------------

CHOGADIYA_ORDER = ["Udveg", "Char", "Labh", "Amrit", "Kaal", "Shubh", "Rog"]
CHOGADIYA_START = {0: 0, 1: 3, 2: 6, 3: 2, 4: 5, 5: 1, 6: 4}
CHOGADIYA_QUALITY = {
    "Amrit": "excellent",
    "Shubh": "good",
    "Labh": "gainful",
    "Char": "neutral, good for movement",
    "Udveg": "anxious",
    "Rog": "unwell",
    "Kaal": "obstructed",
}


def chogadiya(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> list[dict]:
    """Eight divisions of the daylight span, each with a settled quality."""
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    w = _WEEKDAY[pc.vara]
    span = (pc.sunset - pc.sunrise) / 8.0
    start = CHOGADIYA_START[w]
    out = []
    for i in range(8):
        name = CHOGADIYA_ORDER[(start + i) % 7]
        out.append(
            {
                "name": name,
                "quality": CHOGADIYA_QUALITY[name],
                "start": pc.sunrise + i * span,
                "end": pc.sunrise + (i + 1) * span,
            }
        )
    return out


def abhijit_muhurta(
    chart: Chart,
    jd: float,
    *,
    observer_lat: float | None = None,
    observer_lon: float | None = None,
) -> tuple[float, float]:
    """The eighth of fifteen daylight muhurtas -- the one span the tradition
    treats as auspicious almost regardless of anything else."""
    lat, lon = _location(chart, observer_lat, observer_lon)
    pc = P.compute(jd, lat, lon, chart.ayanamsa)
    span = (pc.sunset - pc.sunrise) / 15.0
    return pc.sunrise + 7 * span, pc.sunrise + 8 * span


# --- sudarshana chakra ------------------------------------------------------


def sudarshana(chart: Chart, jd: float) -> dict[str, dict]:
    """The same house counted three ways at once -- from the rising sign, from
    the Moon and from the Sun.  Agreement across all three is the claim."""
    moving = positions(jd, chart.ayanamsa, chart.node)
    rings = {
        "lagna": chart.asc.sign,
        "Moon": chart.grahas["Moon"].sign,
        "Sun": chart.grahas["Sun"].sign,
    }
    out = {}
    for g in ("Jupiter", "Saturn", "Mars", "Rahu"):
        houses = {k: (moving[g].sign - base) % 12 + 1 for k, base in rings.items()}
        out[g] = {"houses": houses, "unanimous": len(set(houses.values())) == 1}
    return out


# --- longevity --------------------------------------------------------------

PINDAYU_FULL = {
    "Sun": 19,
    "Moon": 25,
    "Mars": 15,
    "Mercury": 12,
    "Jupiter": 15,
    "Venus": 21,
    "Saturn": 20,
}


def pindayu(chart: Chart) -> dict:
    """Pindayu: years contributed by each graha, scaled by its distance from
    debilitation, then reduced for hostile placement.

    One of three classical longevity methods and the one most often quoted.
    Included for completeness; longevity claims are the part of this tradition
    I would trust least and act on never.
    """
    from .chart import EXALTATION

    total = 0.0
    parts = {}
    for g, full in PINDAYU_FULL.items():
        ex_sign, ex_deg = EXALTATION[g]
        debil = ((ex_sign * 30 + ex_deg) + 180) % 360
        arc = abs((chart.grahas[g].longitude - debil + 180) % 360 - 180)
        years = full * arc / 180.0
        if chart.grahas[g].retrograde:
            years *= 1.5
        if chart.combust(g):
            years *= 0.5
        h = chart.house(g)
        if h in (12, 11, 10, 9, 8, 7):
            years *= {12: 1 / 12, 11: 2 / 12, 10: 3 / 12, 9: 4 / 12, 8: 5 / 12, 7: 6 / 12}[h] + 0.5
        parts[g] = years
        total += years
    return {"parts": parts, "years": total}


# --- tripataki --------------------------------------------------------------


def tripataki(chart: Chart, jd: float) -> dict:
    """Tajika's three-banner chakra: the annual Moon's nakshatra sets a grid
    and transits falling on its lines are read as the year's flashpoints."""
    moving = positions(jd, chart.ayanamsa, chart.node)
    base = moving["Moon"].nakshatra
    lines = {}
    for g in SEVEN + ["Rahu", "Ketu"]:
        offset = (moving[g].nakshatra - base) % 27
        lines[g] = {"offset": offset + 1, "on_line": offset % 3 == 0}
    return lines
