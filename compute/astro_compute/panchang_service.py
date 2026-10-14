"""GET /v1/panchang: one Vedic day (sunrise to next sunrise) at one place."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from jyotisha import muhurta as Mu
from jyotisha import panchanga as P
from jyotisha.ephemeris import (
    NAKSHATRAS,
    SIGNS,
    luminaries,
    moon_rise_set,
    positions,
    sunrise,
    sunset,
)
from jyotisha.rare import AMRITA_SIDDHI, DAGDHA, MARANA, SARVARTHA_SIDDHI

from .errors import unsupported_location
from .fmt import provenance
from .ids import (
    CHOGHADIYA_QUALITY,
    GRAHA_ID,
    KARANA_ID,
    MASA_IDS,
    NAKSHATRA_IDS,
    NAKSHATRA_LORD,
    SIGN_IDS,
    VARA_ID,
    YOGA_IDS,
    paksha,
    slug,
    tithi_id,
)
from .models import MonthQuery, PanchangQuery
from .timeutil import aware, iso, local_jd, offset_text

WEEKDAY = {"Sun": 0, "Moon": 1, "Mars": 2, "Mercury": 3, "Jupiter": 4, "Venus": 5, "Saturn": 6}
UTTARAYANA_SIGNS = {9, 10, 11, 0, 1, 2}  # Sun from Makara to the end of Mithuna (sidereal)
AVOID_IDS = {
    "Rahu kalam": "rahu_kalam",
    "Yamaganda": "yamaganda",
    "Gulika": "gulika",
    "Durmuhurta": "durmuhurta",
}

type Span = tuple[object, float, float]


def _edge(fn: Callable[[float], object], lo: float, hi: float) -> float:
    """First moment in (lo, hi] where fn differs from fn(lo), to ~0.2 s."""
    v = fn(lo)
    for _ in range(26):
        mid = (lo + hi) / 2
        if fn(mid) == v:
            lo = mid
        else:
            hi = mid
    return hi


def spans(fn: Callable[[float], object], t0: float, t1: float, step: float = 1 / 24) -> list[Span]:
    """Every value fn takes across [t0, t1), with its true start and end.

    The first span starts before t0 and the last ends after t1 when the limb
    does: a tithi that began yesterday evening is reported with that start.
    ``step`` must be shorter than the shortest span (karanas need 1/48).
    """
    v = fn(t0)
    a = t0
    for _ in range(2000):
        if fn(a - step) != v:
            break
        a -= step
    start = _edge(fn, a - step, a)
    out: list[Span] = []
    t = t0
    while True:
        for _ in range(2000):
            if fn(t + step) != v:
                break
            t += step
        end = _edge(fn, t, t + step)
        out.append((v, start, end))
        if end >= t1:
            return out
        start, v, t = end, fn(end), end


def _clip(a: float, b: float, lo: float, hi: float) -> tuple[float, float] | None:
    a, b = max(a, lo), min(b, hi)
    return (a, b) if a < b else None


def build(q: PanchangQuery) -> dict:
    zone, ay = q.tz, q.ayanamsa
    noon = local_jd(q.date, 12.0, zone, "date")
    try:
        d = Mu.day(noon, q.lat, q.lon, ay)
    except RuntimeError as exc:
        raise unsupported_location(
            "the Sun does not rise or set on this date here; a Vedic day cannot be formed"
        ) from exc
    sr, ss, nr = d.sunrise, d.sunset, d.next_sunrise

    def at(jd: float) -> str:
        return iso(jd, zone)

    def win(a: float, b: float) -> dict:
        return {"start": at(a), "end": at(b)}

    tithis = spans(lambda t: Mu.tithi_at(t, ay), sr, nr)
    naks = spans(lambda t: Mu.nakshatra_at(t, ay), sr, nr)
    yogas = spans(lambda t: Mu.yoga_at(t, ay), sr, nr)
    karanas = spans(lambda t: Mu.karana_at(t, ay), sr, nr, step=1 / 48)
    moon_signs = spans(lambda t: luminaries(t, ay)[1].sign, sr, nr)

    def tithi_row(s: Span) -> dict:
        num, a, b = s
        return {"id": tithi_id(num), "num": num, "paksha": paksha(num), **win(a, b)}

    def nak_row(s: Span) -> dict:
        n, a, b = s
        return {"id": NAKSHATRA_IDS[n], "num": n + 1, "lord": NAKSHATRA_LORD[n], **win(a, b)}

    def yoga_row(s: Span) -> dict:
        n, a, b = s
        return {"id": YOGA_IDS[n], "num": n + 1, **win(a, b)}

    def karana_row(s: Span) -> dict:
        name, a, b = s
        return {"id": KARANA_ID[name], **win(a, b)}

    # Civil-date bounds for moonrise/moonset.
    day_start = local_jd(q.date, 0.0, zone, "date")
    day_end = day_start + 1.0
    rise, set_ = moon_rise_set(day_start, day_end, q.lat, q.lon)

    at_rise = positions(sr, ay)
    month = Mu.lunar_month(sr, ay)
    masa = Mu.MASA.index(month.name)
    tithi_now = tithis[0][0]

    # (start jd, row) pairs: ISO strings don't sort across a DST change.
    avoid: list[tuple[float, dict]] = []
    for w in d.avoid:
        if w.label in AVOID_IDS:
            row = {"id": AVOID_IDS[w.label], "detail": None}
        else:  # "<Name> yoga (first N ghatis)" / "(whole yoga)"
            row = {"id": "bad_yoga", "detail": slug(w.label.split(" yoga")[0])}
        avoid.append((w.start, {**row, **win(w.start, w.end)}))
    for name, a, b in karanas:
        if name != "Vishti":
            continue
        clipped = _clip(a, b, sr, nr)
        if clipped:
            mid_sign = luminaries((a + b) / 2, ay)[1].sign
            residence = Mu.bhadra_residence(mid_sign)
            avoid.append((a, {"id": "vishti", "detail": f"bhadra_{residence}", **win(a, b)}))
    avoid.sort(key=lambda r: r[0])

    chog = [
        {
            "id": w.label.lower(),
            "lord": GRAHA_ID[w.note],
            "quality": CHOGHADIYA_QUALITY[w.label.lower()],
            **win(w.start, w.end),
        }
        for w in d.choghadiyas
    ]

    weekday = WEEKDAY[d.vara]
    special: list[tuple[float, dict]] = []
    for n, a, b in naks:
        clipped = _clip(a, b, sr, nr)
        if not clipped:
            continue
        name = NAKSHATRAS[n]
        for yid, hit in (
            ("amrita_siddhi", AMRITA_SIDDHI.get(weekday) == name),
            ("sarvartha_siddhi", name in SARVARTHA_SIDDHI.get(weekday, set())),
            ("marana", MARANA.get(weekday) == name),
            ("dagdha", DAGDHA.get(weekday) == name),
        ):
            if hit:
                special.append((clipped[0], {"id": yid, **win(*clipped)}))
    for num, a, b in tithis:
        clipped = _clip(a, b, sr, nr)
        if clipped and Mu.siddha_yoga(num, d.vara):
            special.append((clipped[0], {"id": "siddha", **win(*clipped)}))
    special.sort(key=lambda r: r[0])

    return {
        "date": q.date.isoformat(),
        "place": {"lat": q.lat, "lon": q.lon, "tz": zone},
        "utcOffset": offset_text(aware(noon, zone)),
        "vara": {"id": VARA_ID[d.vara], "lord": GRAHA_ID[d.vara]},
        "sunrise": at(sr),
        "sunset": at(ss),
        "nextSunrise": at(nr),
        "moonrise": at(rise) if rise else None,
        "moonset": at(set_) if set_ else None,
        "tithi": tithi_row(tithis[0]),
        "nakshatra": nak_row(naks[0]),
        "yoga": yoga_row(yogas[0]),
        "karana": karana_row(karanas[0]),
        "sequence": {
            "tithi": [tithi_row(s) for s in tithis],
            "nakshatra": [nak_row(s) for s in naks],
            "yoga": [yoga_row(s) for s in yogas],
            "karana": [karana_row(s) for s in karanas],
            "moonSign": [{"sign": SIGN_IDS[s], **win(a, b)} for s, a, b in moon_signs],
        },
        "sunSign": SIGN_IDS[at_rise["Sun"].sign],
        "moonSign": SIGN_IDS[at_rise["Moon"].sign],
        "lunarMonth": {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if tithi_now > 15 else MASA_IDS[masa],
            "adhika": month.adhika,
        },
        "ayana": "uttarayana" if at_rise["Sun"].sign in UTTARAYANA_SIGNS else "dakshinayana",
        "windows": {
            "brahma": win(d.brahma.start, d.brahma.end),
            "abhijit": {
                **win(d.abhijit.start, d.abhijit.end),
                "avoided": d.vara == "Mercury",
                "reason": "wednesday" if d.vara == "Mercury" else None,
            },
            "pradosha": win(d.pradosha.start, d.pradosha.end),
            "avoid": [row for _, row in avoid],
        },
        "choghadiya": {"day": chog[:8], "night": chog[8:]},
        "hora": [
            {
                "lord": GRAHA_ID[w.label],
                "period": "day" if i < 12 else "night",
                **win(w.start, w.end),
            }
            for i, w in enumerate(d.horas)
        ],
        "lagna": [
            {"sign": SIGN_IDS[SIGNS.index(w.label)], **win(w.start, w.end)} for w in d.lagnas
        ],
        "specialYogas": [row for _, row in special],
        "engine": provenance(ay),
    }


# --- month calendar ------------------------------------------------------------


def _end(fn: Callable[[float], object], t: float, step: float = 1 / 24) -> float:
    """When the value fn holds at t stops holding."""
    v = fn(t)
    for _ in range(2000):
        if fn(t + step) != v:
            break
        t += step
    return _edge(fn, t, t + step)


def month(q: MonthQuery) -> dict:
    """One compact row per civil day, for calendar pages."""
    zone, ay = q.tz, q.ayanamsa
    first = dt.date(q.year, q.month, 1)
    days = (dt.date(q.year + (q.month == 12), q.month % 12 + 1, 1) - first).days
    rows, lunar = [], None

    def at(jd: float) -> str:
        return iso(jd, zone)

    for i in range(days):
        day = first + dt.timedelta(days=i)
        noon = local_jd(day, 12.0, zone, "month")
        try:
            sr = sunrise(noon, q.lat, q.lon)
            ss = sunset(noon, q.lat, q.lon)
        except RuntimeError as exc:
            raise unsupported_location(
                f"the Sun does not rise or set on {day} here; a Vedic day cannot be formed"
            ) from exc
        if lunar is None or sr >= lunar.end:
            lunar = Mu.lunar_month(sr, ay)
        sun, moon = luminaries(sr, ay)
        tithi = Mu.tithi_at(sr, ay)
        nak, yoga = moon.nakshatra, Mu.yoga_at(sr, ay)
        start = local_jd(day, 0.0, zone, "month")
        sun_now = sun.sign
        sun_end = luminaries(start + 1.0, ay)[0].sign
        sankranti = None
        if luminaries(start, ay)[0].sign != sun_end:
            edge = _edge(lambda t: luminaries(t, ay)[0].sign, start, start + 1.0)
            sankranti = {"sign": SIGN_IDS[sun_end], "at": at(edge)}
        vara = P.VARA_LORDS[P.vara_index(sr)]
        masa = Mu.MASA.index(lunar.name)
        rows.append(
            {
                "date": day.isoformat(),
                "vara": VARA_ID[vara],
                "sunrise": at(sr),
                "sunset": at(ss),
                "tithi": {
                    "id": tithi_id(tithi),
                    "num": tithi,
                    "paksha": paksha(tithi),
                    "end": at(_end(lambda t: Mu.tithi_at(t, ay), sr)),
                },
                "nakshatra": {
                    "id": NAKSHATRA_IDS[nak],
                    "num": nak + 1,
                    "end": at(_end(lambda t: Mu.nakshatra_at(t, ay), sr)),
                },
                "yoga": {
                    "id": YOGA_IDS[yoga],
                    "num": yoga + 1,
                    "end": at(_end(lambda t: Mu.yoga_at(t, ay), sr)),
                },
                "moonSign": SIGN_IDS[moon.sign],
                "sunSign": SIGN_IDS[sun_now],
                "sankranti": sankranti,
                "lunarMonth": {
                    "amanta": MASA_IDS[masa],
                    "purnimanta": MASA_IDS[(masa + 1) % 12] if tithi > 15 else MASA_IDS[masa],
                    "adhika": lunar.adhika,
                },
            }
        )
    return {
        "year": q.year,
        "month": q.month,
        "place": {"lat": q.lat, "lon": q.lon, "tz": zone},
        "days": rows,
        "engine": provenance(ay),
    }
