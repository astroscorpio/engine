"""GET /v1/observances/sankranti: the year's twelve sidereal solar ingresses at a place,
with each one's punyakala and the day of the bath and gifts (docs/sources/sankranti.md,
as the lead approved it on 15 Oct 2026; DS pp. 2-3, 41, 85-86; NS pp. 4-11, 161,
326-327). A ghati is 24 minutes and a nadi the same.
"""

from __future__ import annotations

import datetime as dt

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries

from .fmt import provenance
from .ids import SIGN_IDS
from .models import EkadashiQuery
from .observances import _sunrises, _sunset, _vara
from .timeutil import aware, iso, local_jd

GHATI = 24 / 1440
FIVE = 5 * GHATI
# DS p. 2: (class, ghatis before, ghatis after), Mesha first.
WINDOWS = [
    ("vishuva", 15, 15), ("vishnupada", 16, 0), ("shadashiti", 0, 16), ("ayana", 30, 0),
    ("vishnupada", 16, 0), ("shadashiti", 0, 16), ("vishuva", 15, 15), ("vishnupada", 16, 0),
    ("shadashiti", 0, 16), ("ayana", 0, 40), ("vishnupada", 16, 0), ("shadashiti", 0, 16),
]  # fmt: skip
KARKA, MAKARA = 3, 9
SOURCE = {
    "text": "Dharmasindhu",
    "edition": (
        "Kāśīnātha Upādhyāya (1790), edited by Kṛṣṇa Śāstrī Navare, First edition, "
        "Nirṇaya-sāgara Press, Bombay, 1888"
    ),
    "verse": "sankranti",
    "page": "2–3, 41, 85–86",
}
ALSO = {
    "text": "Nirṇaya-sindhu",
    "edition": (
        "Kamalākara Bhaṭṭa (1612), with the Hindi commentary of Jvālāprasāda Miśra (1899), "
        "Gaṅgāviṣṇu Śrīkṛṣṇadās, Lakṣmī-Veṅkaṭeśvara Press, Kalyan, 1918; "
        "Khemrāj Śrīkṛṣṇadās’s 2019 Mumbai printing has the same page numbers"
    ),
    "verse": "sankranti-nirnaya",
    "page": "4–11, 161, 326–327",
}


def _span(a: float, b: float, q) -> dict:
    return {"start": iso(a, q.tz), "end": iso(b, q.tz)}


def _clip(a: float, b: float, lo: float, hi: float) -> tuple[float, float] | None:
    x, y = max(a, lo), min(b, hi)
    return (x, y) if y > x else None


def _half(sr: float, q, first: bool) -> dict:
    """A day's forenoon (sunrise to midday, best its first five nadis) or afternoon
    (midday to sunset, best its last five)."""
    ss = _sunset(sr, q)
    mid = (sr + ss) / 2
    a, b = (sr, mid) if first else (mid, ss)
    best = (a, min(b, a + FIVE)) if first else (max(a, b - FIVE), b)
    return {"date": _date(sr, q), **_span(a, b, q), "best": _span(*best, q)}


def _date(jd: float, q) -> str:
    return aware(jd, q.tz).date().isoformat()


def _split(sr: float, nr: float, t: float, mid: float, q) -> tuple[str, list[dict]]:
    """The midnight split (DS p. 2): before the nishitha the previous afternoon, after it
    the next forenoon, within it both."""
    if t < mid - GHATI:
        return "night_before_midnight", [_half(sr, q, False)]
    if t > mid + GHATI:
        return "night_after_midnight", [_half(nr, q, True)]
    return "night_midnight_both", [_half(sr, q, False), _half(nr, q, True)]


def _one(t: float, sign: int, q) -> dict:
    cls, before, after = WINDOWS[sign]
    sr, nr = _sunrises(t, q.lat, q.lon, 2)
    ss = _sunset(sr, q)
    variants: dict = {}
    twilight = False
    if t < ss:  # a day ingress
        if after and not before and ss - t <= 2 * GHATI:
            before, after, rule = after, 0, "day_sunset_edge"
        elif before and not after and t - sr <= 2 * GHATI:
            before, after, rule = 0, before, "day_sunrise_edge"
        else:
            rule = "day"
        window = _clip(t - before * GHATI, t + after * GHATI, sr, ss)
        if before and after:
            best = (t - FIVE / 2, t + FIVE / 2)
        else:
            best = (t - FIVE, t) if before else (t, t + FIVE)
        best = _clip(*best, *window) if window else None
        rows = [
            {
                "date": _date(sr, q),
                **_span(*(window or (t, t)), q),
                "best": _span(*best, q) if best else None,
            }
        ]
    else:  # a night ingress
        mid = (ss + nr) / 2
        if sign == MAKARA:
            rule, rows = "makara_night_next_day", [_half(nr, q, True)]
            twilight = t <= ss + 3 * GHATI
            variants["baudhayana"] = [_date(sr, q), _date(nr, q)]
            variants["hemadri"] = [
                {"date": r["date"], "best": r["best"]} for r in _split(sr, nr, t, mid, q)[1]
            ]
        elif sign == KARKA:
            rule, rows = "karka_night_previous_day", [_half(sr, q, False)]
            twilight = t >= nr - 3 * GHATI
            variants["hemadri"] = [
                {"date": r["date"], "best": r["best"]} for r in _split(sr, nr, t, mid, q)[1]
            ]
        else:
            rule, rows = _split(sr, nr, t, mid, q)
    first = rows[0]["date"]
    rise = sr if first == _date(sr, q) else nr
    kari = None
    if sign in (KARKA, MAKARA):
        # DS p. 86: the ayana day and the day after (kari) are avoided for auspicious
        # acts; an ingress at or after the night's midpoint makes them the next two.
        start = sr if t < (ss + nr) / 2 else nr
        kari = [_date(x, q) for x in _sunrises(start + 0.01, q.lat, q.lon, 2)]
    return {
        "sign": SIGN_IDS[sign],
        "class": cls,
        "at": iso(t, q.tz),
        "atNight": t >= ss,
        "date": first,
        "vara": _vara(rise, q),
        "rule": rule,
        "punyakala": rows,
        "variants": variants,
        "jyotishaTwilight": twilight,
        "kari": kari,
        "sayana": iso(_sayana(t, sign), q.tz),
    }


def _sayana(t: float, sign: int) -> float:
    """The tropical ingress into the same sign, the one before the sidereal ingress."""

    def tropical(x: float) -> int:
        return luminaries(x, "tropical")[0].sign

    edges = Mu._scan(tropical, t - 40, t + 1e-6, 1.0)
    return next(e for e, s in reversed(edges) if s == sign)


def sankranti(q: EkadashiQuery) -> dict:
    ay = q.ayanamsa
    t0 = local_jd(dt.date(q.year, 1, 1), 0.0, q.tz, "year")
    t1 = local_jd(dt.date(q.year, 12, 31), 23.99, q.tz, "year")
    edges = Mu._scan(lambda t: luminaries(t, ay)[0].sign, t0 - 1, t1 + 1, 1.0)
    rows = [_one(t, sign, q) for t, sign in edges if t0 <= t <= t1]
    return {
        "year": q.year,
        "sankrantis": rows,
        "source": SOURCE,
        "alsoSource": ALSO,
        "engine": provenance(ay),
    }
