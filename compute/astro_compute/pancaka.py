"""The Dhanishtha-pancaka (contract 7s; research's docs/sources/pancaka.md, adopted by the
lead on 17 Oct 2026): the Moon from the second half of Dhanishtha through Revati, which is
its run through sidereal Kumbha and Mina (MC 2.48 and commentary, p. 84; NS p. 943).

The instants are global; the place sets the zone and the weekday. The weekday-start
names are popular practice, attributed to no text: the texts read give the pancaka no
weekday names, and the five names are MC's separate bana count (6.71-72)."""

from __future__ import annotations

import datetime as dt

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries

from .fmt import provenance
from .models import EkadashiQuery
from .observances import SOURCE as NS
from .observances import _sunrises, _vara
from .timeutil import iso, local_jd

KUMBHA, MESHA = 10, 0
# News reports of 2025 (practice evidence only; research, 17 Oct 2026): no name for a
# Wednesday or Thursday start.
POPULAR_NAMES = {"sunday": "roga", "monday": "raja", "tuesday": "agni", "friday": "cora",
                 "saturday": "mrtyu"}  # fmt: skip
MC = {
    "text": "Muhūrta-cintāmaṇi",
    "verse": "2.48, with the Pīyūṣadhārā",
    "edition": (
        "Rāma Daivajña (1600), with the Pīyūṣadhārā commentary of Govinda Daivajña (1603), "
        "1945 printing; the 1925 printing has the same page numbers"
    ),
    "page": "84–86",
}
DS = {
    "text": "Dharmasindhu",
    "edition": (
        "Kāśīnātha Upādhyāya (1790), edited by Kṛṣṇa Śāstrī Navare, First edition, "
        "Nirṇaya-sāgara Press, Bombay, 1888"
    ),
    "verse": "building a house: the pillars",
    "page": "242",
}
BARRED = ("cremation", "travel_south", "weaving_cot", "roofing", "grass_wood", "pillars")


def pancaka(q: EkadashiQuery) -> dict:
    """Every pancaka touching the year at the place (one crossing a year end is in both)."""
    t0 = local_jd(dt.date(q.year, 1, 1), 0.0, q.tz, "year")
    t1 = local_jd(dt.date(q.year + 1, 1, 1), 0.0, q.tz, "year")
    sign = lambda t: luminaries(t, q.ayanamsa)[1].sign  # noqa: E731
    rows, start = [], None
    for t, s in Mu._scan(sign, t0 - 8, t1 + 8, 0.25):  # a run lasts about five days
        if s == KUMBHA:
            start = t
        elif s == MESHA and start is not None:
            if start < t1 and t > t0:
                (sr,) = _sunrises(start, q.lat, q.lon, 1)  # the vara runs from sunrise
                vara = _vara(sr, q)
                nid = POPULAR_NAMES.get(vara)
                rows.append(
                    {
                        "start": iso(start, q.tz),
                        "end": iso(t, q.tz),
                        "startVara": vara,
                        "nameId": nid,
                        "nameBasis": "popular_practice" if nid else None,
                    }
                )
            start = None
    return {
        "year": q.year,
        "spans": rows,
        "barred": list(BARRED),
        "source": MC,
        "alsoSource": [{**NS, "verse": "the Garuḍa via the Madanaratna", "page": "943–944"}, DS],
        "engine": provenance(q.ayanamsa),
    }
