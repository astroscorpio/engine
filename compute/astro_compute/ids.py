"""Stable public ids for engine names.

docs/api-contract.md promises these never change: the UI and the meta
dictionary key everything on them. Engine names ("U.Ashadha", "great friend")
stay internal to the engine.
"""

from __future__ import annotations

import re

from jyotisha.dashas import VIMSHOTTARI
from jyotisha.ephemeris import GRAHAS, NAKSHATRAS, SIGNS
from jyotisha.muhurta import MASA
from jyotisha.panchanga import FIXED_KARANAS, KARANA_NAMES, VARA_LORDS, YOGA_NAMES

GRAHA_ID = {g: g.lower() for g in GRAHAS}
GRAHA_IDS = [GRAHA_ID[g] for g in GRAHAS]
ENGINE_GRAHA = {v: k for k, v in GRAHA_ID.items()}

SIGN_IDS = [s.lower() for s in SIGNS]

NAKSHATRA_IDS = [
    "ashwini", "bharani", "krittika", "rohini", "mrigashira", "ardra", "punarvasu",
    "pushya", "ashlesha", "magha", "purva_phalguni", "uttara_phalguni", "hasta",
    "chitra", "swati", "vishakha", "anuradha", "jyeshtha", "mula", "purva_ashadha",
    "uttara_ashadha", "shravana", "dhanishta", "shatabhisha", "purva_bhadrapada",
    "uttara_bhadrapada", "revati",
]  # fmt: skip
assert len(NAKSHATRA_IDS) == len(NAKSHATRAS) == 27
NAKSHATRA_ID = dict(zip(NAKSHATRAS, NAKSHATRA_IDS, strict=True))
# Vimshottari lordship: Ashwini -> Ketu, Bharani -> Venus, ... repeating every 9.
NAKSHATRA_LORD = [GRAHA_ID[VIMSHOTTARI[i % 9][0]] for i in range(27)]

TITHI_BASE = [
    "pratipada", "dwitiya", "tritiya", "chaturthi", "panchami", "shashthi", "saptami",
    "ashtami", "navami", "dashami", "ekadashi", "dwadashi", "trayodashi", "chaturdashi",
]  # fmt: skip


def tithi_id(num: int) -> str:
    """1..30 -> id; 15 is Purnima and 30 Amavasya, the rest repeat by paksha."""
    if num == 15:
        return "purnima"
    if num == 30:
        return "amavasya"
    return TITHI_BASE[(num - 1) % 15]


def paksha(num: int) -> str:
    return "shukla" if num <= 15 else "krishna"


YOGA_IDS = [y.lower() for y in YOGA_NAMES]
KARANA_ID = {k: k.lower() for k in KARANA_NAMES + FIXED_KARANAS}

VARA_ID = {
    "Sun": "sunday", "Moon": "monday", "Mars": "tuesday", "Mercury": "wednesday",
    "Jupiter": "thursday", "Venus": "friday", "Saturn": "saturday",
}  # fmt: skip
assert set(VARA_ID) == set(VARA_LORDS)

MASA_ID = {m: m.lower() for m in MASA}
MASA_IDS = [MASA_ID[m] for m in MASA]

CHOGHADIYA_QUALITY = {
    "amrit": "good", "shubh": "good", "labh": "good", "char": "neutral",
    "udveg": "avoid", "kaal": "avoid", "rog": "avoid",
}  # fmt: skip


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def dignity_id(name: str | None) -> str | None:
    return name.replace(" ", "_") if name else None


def functional_id(name: str) -> str:
    return name.replace(" ", "_")
