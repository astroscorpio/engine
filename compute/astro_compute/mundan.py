"""GET /v1/muhurat/mundan: the year's days for a child's first tonsure (cudakarana) at
a place (docs/sources/mundan.md, as the lead approved it on 15 Oct 2026).

A day is listed when, at some moment of it, the Sun is in its northern course and
the amanta month is not Caitra (MC 5.29), adhika or kshaya (1.47); Jupiter and Venus
are clear (5.26-27) and Jupiter is not in Leo or Capricorn (1.48; DS p. 5); the Moon
is in one of the twelve stars of MC 5.29 (Vasishtha; DS p. 137); the tithi is 2, 3,
5, 7, 10, 11 or 13; and the day is a Wednesday, Thursday or Friday, or a Monday in
the bright fortnight (Parashara). Its windows add a benefic's lagna (Kashyapa), the
8th empty but for Venus, and no waning Moon, Mars, Saturn or Sun in a kendra (5.30),
less the barred stretches and day yogas the other date lists remove.
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, positions

from .fmt import provenance
from .griha_pravesh import BARRED_JUPITER, UTTARAYANA, _blocks, _public, _windows
from .ids import MASA_IDS
from .models import EkadashiQuery
from .observances import _vara
from .timeutil import aware
from .vivah import DS, _day_yogas, _spans, _subtract, _Year

# MC 5.29 "shakropetair vimaitrair mrdu-cara-laghu-bhaih": Ashvini, Mrgashira,
# Punarvasu, Pushya, Hasta, Citra, Svati, Jyeshtha, Shravana, Dhanishtha,
# Shatabhisha, Revati (0-based indexes).
STARS = {0, 4, 6, 7, 12, 13, 14, 17, 21, 22, 23, 26}
TITHIS = {2, 3, 5, 7, 10, 11, 13}  # within either fortnight
VARAS = {"monday", "wednesday", "thursday", "friday"}  # Monday in the bright fortnight only
BENEFIC_SIGNS = {1, 2, 3, 5, 6, 8, 11}  # Kashyapa: the signs of Mercury, Moon, Venus, Jupiter
KENDRA = {1, 4, 7, 10}
SOURCE = {
    "text": "Muhurta-cintamani",
    "verse": "5.26-30; 1.47-48",
    "edition": "with Govinda's Piyushadhara, 1945 (5.27-30 from the 1925 printing)",
    "page": "40-41, 186-193",
}


def _lagna_windows(a: float, b: float, num: int, q) -> list[tuple[float, float, int]]:
    """Stretches of [a, b] with a benefic's lagna, the 8th empty but for Venus, and no
    waning Moon (outside tithis 9-22, BJ 2.5 as the engine reads it), Mars, Saturn or
    Sun in a kendra."""
    ay = q.ayanamsa
    bad = {"Mars", "Saturn", "Sun"} | (set() if 9 <= num <= 22 else {"Moon"})
    out = []
    for x, y, lagna in _spans(
        lambda t: int(ascendant(t, q.lat, q.lon, ay)[0].longitude // 30), a, b, 1 / 96
    ):
        if lagna not in BENEFIC_SIGNS:
            continue
        p = positions((x + y) / 2, ay)
        house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
        if any(h == 8 and g != "Venus" for g, h in house.items()):
            continue
        if any(house[g] in KENDRA for g in bad):
            continue
        out.append((x, y, lagna))
    return out


def mundan(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the rule that rejected it."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    out_days = []
    for i, (sr, _ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        why = None if vara in VARAS else "weekday"
        if not why:
            hit = next((p for p in y.states if i in y.states[p]), None)
            why = hit and f"{hit.lower()}_{y.states[hit][i][0]}"
        if why:
            if explain is not None:
                explain[date.isoformat()] = why
            continue
        reasons: list[str] = []
        pieces = []
        cuts = y.cuts(sr, nr)
        for a, b in zip(cuts, cuts[1:], strict=False):
            mid = (a + b) / 2
            num, (name, adhika, kshaya, _) = y.tithi(mid)
            sun, moon = luminaries(mid, ay)
            if adhika or kshaya or name == "Chaitra":
                reasons.append("month")
            elif sun.sign not in UTTARAYANA:
                reasons.append("dakshinayana")
            elif positions(mid, ay)["Jupiter"].sign in BARRED_JUPITER:
                reasons.append("jupiter_sign")
            elif moon.nakshatra not in STARS:
                reasons.append("nakshatra")
            elif (num - 1) % 15 + 1 not in TITHIS:
                reasons.append("tithi")
            elif vara == "monday" and num > 15:
                reasons.append("weekday")
            else:
                pieces.append((a, b, num, moon.nakshatra, name))
        if not pieces:
            if explain is not None:
                order = ("weekday", "tithi", "nakshatra", "jupiter_sign", "dakshinayana", "month")
                explain[date.isoformat()] = next((r for r in order if r in reasons), "none")
            continue
        free = _subtract([(a, b) for a, b, *_ in pieces], [(x, y_) for x, y_, _ in y.bars])
        rows = []
        for a, b in free:
            num, nak, name = next((n, k, m) for x, y_, n, k, m in pieces if x <= a < y_)
            rows += [
                (x, y_, num, nak, name, {}, lagna) for x, y_, lagna in _lagna_windows(a, b, num, q)
            ]
        rows, _inside, _ = _day_yogas(rows, vara, ay)
        if not rows:
            if explain is not None:
                explain[date.isoformat()] = "lagna" if free else "window"
            continue
        if explain is not None:
            explain[date.isoformat()] = "listed"
        windows = _windows(rows, zone)
        nums = {w["_n"] for w in windows}
        masa = Mu.MASA.index(windows[0]["_m"])
        out_days.append(
            {
                "date": date.isoformat(),
                "vara": vara,
                "lunarMonth": {
                    "amanta": MASA_IDS[masa],
                    "purnimanta": MASA_IDS[(masa + 1) % 12] if min(nums) > 15 else MASA_IDS[masa],
                    "adhika": False,
                },
                "windows": _public(windows),
                "cautions": ["krishna_last_three"] if 28 in nums else [],
            }
        )
    return {
        "year": q.year,
        "days": out_days,
        "blocks": _blocks(y, q, frozenset()),
        "source": SOURCE,
        "alsoSource": {**DS, "page": "5, 137"},
        "engine": provenance(ay),
    }
