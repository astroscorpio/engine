"""GET /v1/muhurat/vehicle and /v1/muhurat/property: the year's buying days at a place
(docs/sources/vehicle-purchase.md, as the lead approved it on 15 Oct 2026).

A vehicle day has the Moon in one of MC 2.16's six buying stars on a riding weekday
(Thursday, Monday, Sunday, Friday, Wednesday: the Vyavaharoccaya in MC's commentary
on 2.18) and no rikta tithi (MC 2.18's horse rule, our reading for vehicles).
delivery[] widens the stars to the eleven riding stars, for taking delivery or a
first drive. A property day needs only a buying star (the general buying rule).
The windows are the stretches where the muhurta finder's act raises no veto, so the
list and the finder always agree.
"""

from __future__ import annotations

import datetime as dt

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import NAKSHATRAS, luminaries

from .fmt import provenance
from .ids import NAKSHATRA_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _edges, _rise_set, _vara
from .timeutil import aware, iso, local_jd

BUYING = {i for i, n in enumerate(NAKSHATRAS) if n in Mu.BUYING_STARS}
RIDING = {i for i, n in enumerate(NAKSHATRAS) if n in Mu.RIDING_STARS}
RIDING_VARAS = {"thursday", "monday", "sunday", "friday", "wednesday"}
STEP = 10 / 1440  # every veto stretch lasts longer; the edges are bisected
SOURCE = {
    "text": "Muhūrta-cintāmaṇi",
    "verse": "2.16–18 with the commentary (the Vyavahāroccaya on 2.18)",
    "edition": (
        "Rāma Daivajña (1600), with the Pīyūṣadhārā commentary of Govinda Daivajña (1603), "
        "1945 printing; "
        "the 1925 printing has the same page numbers (2.18 checked in the 1925 printing)"
    ),
    "page": "62–64",
}


def _runs(profile: Mu.Profile, d, month, a: float, b: float, q) -> list[tuple[float, float]]:
    """Unvetoed stretches of [a, b): sampled every 10 minutes, edges bisected."""
    ay = q.ayanamsa

    def ok(t: float) -> bool:
        return Mu.evaluate(profile, d, month, t, q.lat, q.lon, None, None, ayanamsa=ay).ok

    out: list[tuple[float, float]] = []
    t, prev, start = a, ok(a), a
    while t < b:
        nxt = min(t + STEP, b - 1e-7)
        cur = ok(nxt)
        if cur != prev:
            edge = Mu._bisect(ok, t, nxt, 7)
            if prev:
                out.append((start, edge))
            start, prev = edge, cur
        if nxt >= b - 1e-7:
            break
        t = nxt
    if prev:
        out.append((start, b))
    return [(x, y) for x, y in out if (y - x) * 1440 >= 5]


def _year(q: EkadashiQuery, stars: set[int], varas: set[str] | None, profile) -> list[dict]:
    ay, zone = q.ayanamsa, q.tz
    first = local_jd(dt.date(q.year, 1, 1), 0.0, zone, "year")
    last = local_jd(dt.date(q.year, 12, 31), 23.99, zone, "year")
    days, sr = [], _rise_set(first - 1, q.lat, q.lon, True)
    while sr < last:
        nr = _rise_set(sr + 0.1, q.lat, q.lon, True)
        days.append((sr, nr))
        sr = nr
    lo, hi = days[0][0], days[-1][1]
    cuts = {lo, hi} | {t for t, _ in _edges(q) if lo < t < hi}
    cuts |= {t for t, _ in Mu._scan(lambda t: luminaries(t, ay)[1].nakshatra, lo, hi, 1 / 12)}
    cuts = sorted(cuts)
    pieces = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        mid = (a + b) / 2
        nak = luminaries(mid, ay)[1].nakshatra
        if nak in stars:
            pieces.append((a, b, nak, Mu.tithi_at(mid, ay)))
    out = []
    for sr, nr in days:
        date = aware(sr, zone).date()
        vara = _vara(sr, q)
        if date.year != q.year or (varas is not None and vara not in varas):
            continue
        mine = [(max(a, sr), min(b, nr), k, n) for a, b, k, n in pieces if a < nr and b > sr]
        if not mine:
            continue
        d = Mu.day(sr + 1e-4, q.lat, q.lon, ay, zone)
        # The month only weighs defects (adhika, Pitru Paksha), never a veto here.
        month = Mu.lunar_month(sr + 0.5, ay)
        windows = []
        for a, b, nak, num in mine:
            for x, y in _runs(profile, d, month, a, b, q):
                windows.append(
                    {
                        "start": iso(x, zone),
                        "end": iso(y, zone),
                        "nakshatra": NAKSHATRA_IDS[nak],
                        "tithi": tithi_id(num),
                        "paksha": "shukla" if num <= 15 else "krishna",
                    }
                )
        if windows:
            out.append({"date": date.isoformat(), "vara": vara, "windows": windows})
    return out


def vehicle(q: EkadashiQuery) -> dict:
    profile = Mu.PROFILES["vehicle"]
    delivery = _year(q, RIDING, RIDING_VARAS, profile)
    buying = {NAKSHATRA_IDS[i] for i in BUYING}
    days = []
    for d in delivery:
        windows = [w for w in d["windows"] if w["nakshatra"] in buying]
        if windows:
            days.append({**d, "windows": windows})
    return {
        "year": q.year,
        "days": days,
        "delivery": delivery,
        "source": SOURCE,
        "engine": provenance(q.ayanamsa),
    }


def property_(q: EkadashiQuery) -> dict:
    return {
        "year": q.year,
        "days": _year(q, BUYING, None, Mu.PROFILES["property"]),
        "source": {**SOURCE, "verse": "2.16–17"},
        "engine": provenance(q.ayanamsa),
    }
