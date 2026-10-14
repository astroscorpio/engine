"""The sixteen divisional charts (shodashavarga) of Parashara.

Each rule returns a *longitude*, not just a sign, so a varga chart can be fed
back into anything that consumes a D1 -- including its own ashtakavarga or a
second division.
"""

from __future__ import annotations

MOVABLE, FIXED, DUAL = 0, 1, 2
FIRE, EARTH, AIR, WATER = 0, 1, 2, 3


def modality(sign: int) -> int:
    return sign % 3  # 0 movable, 1 fixed, 2 dual


def element(sign: int) -> int:
    return sign % 4  # 0 fire, 1 earth, 2 air, 3 water


def is_odd(sign: int) -> bool:
    """Odd *rashi* (Aries, Gemini, ...) -- sign index is 0-based."""
    return sign % 2 == 0


# Trimshamsha is the one division with unequal parts.
TRIMSHAMSHA_ODD = [(5, 0), (10, 10), (18, 8), (25, 2), (30, 6)]  # Ma Sa Ju Me Ve
TRIMSHAMSHA_EVEN = [(5, 1), (12, 5), (20, 11), (25, 9), (30, 7)]  # Ve Me Ju Sa Ma


def varga(longitude: float, d: int) -> float:
    """Divisional longitude for D<d>."""
    longitude %= 360
    sign = int(longitude // 30)
    deg = longitude % 30

    if d == 1:
        return longitude

    if d == 30:
        table = TRIMSHAMSHA_ODD if is_odd(sign) else TRIMSHAMSHA_EVEN
        lo = 0.0
        for hi, target in table:
            if deg < hi:
                frac = (deg - lo) / (hi - lo)
                return target * 30 + frac * 30
            lo = hi
        return table[-1][1] * 30 + 29.999

    span = 30.0 / d
    part = min(int(deg / span), d - 1)
    frac = (deg - part * span) / span  # 0..1 within the amsha

    if d == 2:
        # Sun's hora (Leo) then Moon's hora (Cancer) in odd signs; reversed
        # in even signs.
        start = (4, 3) if is_odd(sign) else (3, 4)
        target = start[part]
    elif d == 3:
        target = (sign + part * 4) % 12
    elif d == 4:
        target = (sign + part * 3) % 12
    elif d == 7:
        target = ((sign if is_odd(sign) else (sign + 6) % 12) + part) % 12
    elif d == 9:
        target = ({FIRE: 0, EARTH: 9, AIR: 6, WATER: 3}[element(sign)] + part) % 12
    elif d == 10:
        target = ((sign if is_odd(sign) else (sign + 8) % 12) + part) % 12
    elif d == 12:
        target = (sign + part) % 12
    elif d == 16:
        target = ({MOVABLE: 0, FIXED: 4, DUAL: 8}[modality(sign)] + part) % 12
    elif d == 20:
        target = ({MOVABLE: 0, FIXED: 8, DUAL: 4}[modality(sign)] + part) % 12
    elif d == 24:
        target = ((4 if is_odd(sign) else 3) + part) % 12
    elif d == 27:
        target = ({FIRE: 0, EARTH: 3, AIR: 6, WATER: 9}[element(sign)] + part) % 12
    elif d == 40:
        target = ((0 if is_odd(sign) else 6) + part) % 12
    elif d == 45:
        target = ({MOVABLE: 0, FIXED: 4, DUAL: 8}[modality(sign)] + part) % 12
    elif d == 60:
        target = (sign + int(deg * 2)) % 12
        frac = (deg * 2) % 1
    else:
        # Cyclic fallback for non-standard divisions (D5, D6, D8, D11 ...).
        target = (sign + part) % 12

    return target * 30 + frac * 30


SHODASHAVARGA = [1, 2, 3, 4, 7, 9, 10, 12, 16, 20, 24, 27, 30, 40, 45, 60]
SHADVARGA = [1, 2, 3, 9, 12, 30]
SAPTAVARGA = [1, 2, 3, 7, 9, 12, 30]
DASHAVARGA = [1, 2, 3, 7, 9, 10, 12, 16, 30, 60]

# Vimshopaka weights (total 20 in every scheme).
VIMSHOPAKA = {
    "shadvarga": {1: 6, 2: 2, 3: 4, 9: 5, 12: 2, 30: 1},
    "saptavarga": {1: 5, 2: 2, 3: 3, 7: 2.5, 9: 4.5, 12: 2, 30: 1},
    "dashavarga": {1: 3, 2: 1, 3: 3, 7: 2, 9: 3, 10: 1, 12: 1, 16: 2, 30: 2, 60: 2},
    "shodashavarga": {
        1: 3.5,
        2: 1,
        3: 1,
        4: 0.5,
        7: 0.5,
        9: 3,
        10: 0.5,
        12: 0.5,
        16: 2,
        20: 0.5,
        24: 0.5,
        27: 0.5,
        30: 1,
        40: 0.5,
        45: 0.5,
        60: 4,
    },
}

VARGA_NAMES = {
    1: "Rashi",
    2: "Hora",
    3: "Drekkana",
    4: "Chaturthamsha",
    7: "Saptamsha",
    9: "Navamsha",
    10: "Dashamsha",
    12: "Dwadashamsha",
    16: "Shodashamsha",
    20: "Vimshamsha",
    24: "Chaturvimshamsha",
    27: "Bhamsha",
    30: "Trimshamsha",
    40: "Khavedamsha",
    45: "Akshavedamsha",
    60: "Shashtiamsha",
}

VARGA_SIGNIFIES = {
    1: "body, the whole life",
    2: "wealth",
    3: "siblings, courage",
    4: "home, fortune",
    7: "children, progeny",
    9: "spouse, dharma, the core",
    10: "career, action",
    12: "parents",
    16: "vehicles, comforts",
    20: "spiritual practice",
    24: "learning, education",
    27: "strengths and weaknesses",
    30: "misfortunes",
    40: "maternal legacy",
    45: "paternal legacy",
    60: "the sum of past karma",
}
