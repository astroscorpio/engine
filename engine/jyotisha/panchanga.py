"""The five limbs: tithi, vara, nakshatra, yoga, karana -- plus horas.

Needed in its own right, and needed by kala bala, which is scored from the
weekday and hour lords.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ephemeris import NAKSHATRAS, next_sunrise, positions, sunrise, sunset

TITHI_NAMES = [
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
]
YOGA_NAMES = [
    "Vishkambha",
    "Priti",
    "Ayushman",
    "Saubhagya",
    "Shobhana",
    "Atiganda",
    "Sukarman",
    "Dhriti",
    "Shula",
    "Ganda",
    "Vriddhi",
    "Dhruva",
    "Vyaghata",
    "Harshana",
    "Vajra",
    "Siddhi",
    "Vyatipata",
    "Variyan",
    "Parigha",
    "Shiva",
    "Siddha",
    "Sadhya",
    "Shubha",
    "Shukla",
    "Brahma",
    "Indra",
    "Vaidhriti",
]
KARANA_NAMES = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti"]
FIXED_KARANAS = ["Kimstughna", "Shakuni", "Chatushpada", "Naga"]

VARA_LORDS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
# Chaldean order, the sequence horas run in.
CHALDEAN = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]


@dataclass
class Panchanga:
    tithi: int  # 1..30
    tithi_name: str
    paksha: str
    vara: str
    nakshatra: int
    nakshatra_name: str
    yoga: int
    yoga_name: str
    karana: str
    hora_lord: str
    is_day_birth: bool
    sunrise: float
    sunset: float
    next_sunrise: float

    def __str__(self) -> str:
        return (
            f"  tithi      {self.tithi:2d}  {self.tithi_name} "
            f"({self.paksha})\n"
            f"  vara       {self.vara}\n"
            f"  nakshatra  {self.nakshatra + 1:2d}  {self.nakshatra_name}\n"
            f"  yoga       {self.yoga:2d}  {self.yoga_name}\n"
            f"  karana     {self.karana}\n"
            f"  hora lord  {self.hora_lord}\n"
            f"  birth      {'day' if self.is_day_birth else 'night'}"
        )


def vara_index(jd_sunrise: float) -> int:
    """Weekday of the Vedic day, which begins at sunrise, not midnight."""
    return int(math.floor(jd_sunrise + 0.5) + 1) % 7


def compute(jd: float, lat: float, lon: float, ayanamsa: str = "lahiri") -> Panchanga:
    if not -90 <= lat <= 90:
        raise ValueError("latitude must be in [-90, 90]")
    if not -180 <= lon <= 180:
        raise ValueError("longitude must be in [-180, 180]")
    p = positions(jd, ayanamsa)
    sun, moon = p["Sun"].longitude, p["Moon"].longitude
    elong = (moon - sun) % 360

    tithi = int(elong // 12) + 1
    paksha = "shukla" if tithi <= 15 else "krishna"
    if tithi == 15:
        tname = "Purnima"
    elif tithi == 30:
        tname = "Amavasya"
    else:
        tname = TITHI_NAMES[(tithi - 1) % 15]

    yoga = int(((sun + moon) % 360) // (360 / 27)) + 1

    # 60 half-tithis in a lunation.  Half 1 is Kimstughna; halves 2-57 are the
    # seven movable karanas repeating eight times; halves 58-60 are Shakuni,
    # Chatushpada and Naga.  The offset here was 56, which shifted all three
    # fixed karanas by one -- Shakuni was unreachable, Naga was emitted for
    # half 59, and half 60 ran off the end of the list and raised.
    half = min(int(elong // 6) + 1, 60)  # 1..60
    if half == 1:
        karana = FIXED_KARANAS[0]
    elif half >= 58:
        karana = FIXED_KARANAS[half - 57]
    else:
        karana = KARANA_NAMES[(half - 2) % 7]

    sr = sunrise(jd, lat, lon)
    ss = sunset(jd, lat, lon)
    nr = next_sunrise(jd, lat, lon)
    vi = vara_index(sr)
    vara = VARA_LORDS[vi]

    # Twelve equal horas divide daylight and another twelve divide the night.
    # The sequence remains continuous across sunset.
    if sr <= jd < ss:
        span = (ss - sr) / 12.0
        hora_n = min(11, int((jd - sr) / span))
    else:
        span = (nr - ss) / 12.0
        hora_n = 12 + min(11, int((jd - ss) / span))
    start = CHALDEAN.index(vara)
    hora_lord = CHALDEAN[(start + hora_n) % 7]

    return Panchanga(
        tithi,
        tname,
        paksha,
        vara,
        p["Moon"].nakshatra,
        NAKSHATRAS[p["Moon"].nakshatra],
        yoga,
        YOGA_NAMES[yoga - 1],
        karana,
        hora_lord,
        sr <= jd < ss,
        sr,
        ss,
        nr,
    )
