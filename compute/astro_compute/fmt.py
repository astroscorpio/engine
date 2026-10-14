"""Engine objects -> contract JSON fragments shared by every service."""

from __future__ import annotations

import os
from functools import cache

from jyotisha import __version__ as ENGINE_VERSION
from jyotisha.ephemeris import Position, backend_info

from .ids import NAKSHATRA_IDS, NAKSHATRA_LORD, SIGN_IDS


def r6(x: float) -> float:
    return round(x, 6)


def dms(deg: float) -> str:
    """Position inside the sign as 23°14'05", rounded to the second."""
    # Clamp so 29.99999 shows as 29°59'59" rather than a 30° that belongs to the next sign.
    total = min(round(deg * 3600), 30 * 3600 - 1)
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}'{s:02d}\""


def sign_ref(sign: int) -> dict:
    return {"sign": SIGN_IDS[sign], "signNum": sign + 1}


def point(p: Position) -> dict:
    return {
        "lon": r6(p.longitude),
        "sign": SIGN_IDS[p.sign],
        "signNum": p.sign + 1,
        "deg": r6(p.degree),
        "dms": dms(p.degree),
        "nakshatra": NAKSHATRA_IDS[p.nakshatra],
        "nakshatraNum": p.nakshatra + 1,
        "pada": p.pada,
        "nakshatraLord": NAKSHATRA_LORD[p.nakshatra],
    }


@cache
def _ephemeris_backend() -> str:
    """ "swiss" (the Swiss Ephemeris data files), or the engine's own name for a fallback."""
    actual = backend_info()["actual"]
    return "swiss" if actual == "swiss-files" else actual


# The public tag of the deployed source (AGPL-3.0), set by the deploy.
SOURCE_URL = os.environ.get("ENGINE_SOURCE_URL") or None


def provenance(ayanamsa: str = "lahiri", node: str = "true") -> dict:
    return {
        "name": "jyotisha",
        "version": ENGINE_VERSION,
        "ephemeris": _ephemeris_backend(),
        "ayanamsa": ayanamsa,
        "node": node,
        "houseSystem": "whole_sign",
        "source": SOURCE_URL,
    }
