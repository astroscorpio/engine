"""GET /v1/muhurat/mundan: the year's days for a child's first tonsure (cudakarana) at
a place (docs/sources/mundan.md, as the lead approved it on 15 Oct 2026).

A day is listed when, at some moment of it, the Sun is in its northern course and
the amanta month is not Caitra (MC 5.29), adhika or kshaya (1.47); Jupiter and Venus
are clear (5.26-27) and Jupiter is not in Leo or Capricorn (1.48; DS p. 5); the Moon
is in one of the twelve stars of MC 5.29 (Vasishtha; DS p. 137); the tithi is 2, 3,
5, 7, 10, 11 or 13; and the day is a Wednesday, Thursday or Friday, or a Monday in
the bright fortnight (Parashara). Its windows add a benefic's lagna and navamsa
(Kashyapa), the 8th empty but for Venus, and no waning Moon, Mars, Saturn or Sun in a kendra (5.30),
less the barred stretches and day yogas the other date lists remove.
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, positions

from .fmt import provenance
from .griha_pravesh import BARRED_JUPITER, UTTARAYANA, _blocks, _public, _windows
from .ids import MASA_IDS, SIGN_IDS
from .models import EkadashiQuery
from .observances import _vara
from .timeutil import aware
from .vivah import (
    DS,
    _day_yogas,
    _details,
    _lagna_gandanta,
    _spans,
    _state_facts,
    _subtract,
    _venus_facts,
    _Year,
)

# MC 5.29 "shakropetair vimaitrair mrdu-cara-laghu-bhaih": Ashvini, Mrgashira,
# Punarvasu, Pushya, Hasta, Citra, Svati, Jyeshtha, Shravana, Dhanishtha,
# Shatabhisha, Revati (0-based indexes).
STARS = {0, 4, 6, 7, 12, 13, 14, 17, 21, 22, 23, 26}
TITHIS = {2, 3, 5, 7, 10, 11, 13}  # within either fortnight
VARAS = {"monday", "wednesday", "thursday", "friday"}  # Monday in the bright fortnight only
BENEFIC_SIGNS = {1, 2, 3, 5, 6, 8, 11}  # Kashyapa: the signs of Mercury, Moon, Venus, Jupiter
KENDRA = {1, 4, 7, 10}
SOURCE = {
    "text": "Muhūrta-cintāmaṇi",
    "verse": "5.26–30; 1.47–48",
    "edition": (
        "Rāma Daivajña (1600 CE), with the Pīyūṣadhārā commentary of Govinda Daivajña (1603), "
        "1945 printing; "
        "the 1925 printing has the same page numbers (5.27–30 from the 1925 printing)"
    ),
    "page": "40–41, 186–193",
}


def _lagna_windows(
    a: float, b: float, num: int, q, fails: dict | None = None
) -> list[tuple[float, float, int]]:
    """Stretches of [a, b] with the lagna and its navamsa in a benefic's sign (MC 5.29
    "lagnamshayoh"), the 8th empty but for Venus, and no waning Moon (outside tithis
    9-22, BJ 2.5 as the engine reads it), Mars, Saturn or Sun in a kendra. fails, if
    given, gathers the minutes each test removes."""
    fails = {} if fails is None else fails

    def fail(rule: str, x: float, y: float) -> None:
        fails[rule] = fails.get(rule, 0.0) + (y - x) * 1440

    ay = q.ayanamsa
    bad = {"Mars", "Saturn", "Sun"} | (set() if 9 <= num <= 22 else {"Moon"})

    def asc(t: float) -> float:
        return ascendant(t, q.lat, q.lon, ay)[0].longitude

    out = []
    for x0, y0, lagna in _spans(lambda t: int(asc(t) // 30), a, b, 1 / 96):
        if lagna not in BENEFIC_SIGNS:
            fail("lagna", x0, y0)
            continue
        for x, y, idx in _spans(lambda t: int(asc(t) // (30 / 9)), x0, y0, 1 / 288):
            if idx % 12 not in BENEFIC_SIGNS:
                fail("lagna", x, y)
                continue
            p = positions((x + y) / 2, ay)
            house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
            if any(h == 8 and g != "Venus" for g, h in house.items()):
                fail("house_8", x, y)
                continue
            if any(house[g] in KENDRA for g in bad):
                fail("kendra_malefic", x, y)
                continue
            out.append((x, y, lagna))
    return out


def mundan(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the rule that rejected it. excluded[]
    holds the days that pass every rule except ones almanacs relax, as in griha-pravesh:
    infancy and old age beyond 3 days, Venus set at 10 time-degrees but not 8, Jupiter
    in Leo or Capricorn, and a day yoga that covers every window."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    out_days, excluded, near = [], [], []
    for i, (sr, _ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        day_relax: dict[str, tuple[str, dict]] = {}
        why = None if vara in VARAS else "weekday"
        for planet, state in y.states.items():
            if why or i not in state:
                continue
            kind, detail = state[i]
            if i in y.relaxed[planet]:
                why = f"{planet.lower()}_{kind}"
            elif kind == "set":
                day_relax["venus_set"] = (
                    "Venus is within the Sūrya-siddhānta's 10 time-degrees of the Sun (9.6–7)",
                    _venus_facts(*y.days[i][:2], q),
                )
            else:
                day_relax["infancy_old"] = (
                    f"{planet} is in its {'infancy' if kind == 'infant' else 'old age'}, "
                    f"{detail} (Muhūrta-cintāmaṇi 5.27)",
                    _state_facts(planet, kind, detail),
                )
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
            relax: dict[str, tuple[str, dict]] = {}
            jupiter = positions(mid, ay)["Jupiter"].sign
            if jupiter in BARRED_JUPITER:
                relax["jupiter_sign"] = (
                    f"Jupiter is in {Mu.SIGNS[jupiter]}; Muhūrta-cintāmaṇi 1.48 bars the "
                    "whole of its stay",
                    {"sign": SIGN_IDS[jupiter]},
                )
            if adhika or kshaya or name == "Chaitra":
                reasons.append("month")
            elif sun.sign not in UTTARAYANA:
                reasons.append("dakshinayana")
            elif moon.nakshatra not in STARS:
                reasons.append("nakshatra")
            elif (num - 1) % 15 + 1 not in TITHIS:
                reasons.append("tithi")
            elif vara == "monday" and num > 15:
                reasons.append("weekday")
            else:
                pieces.append((a, b, num, moon.nakshatra, name, relax))
        if not pieces:
            if explain is not None:
                order = ("weekday", "tithi", "nakshatra", "dakshinayana", "month")
                explain[date.isoformat()] = next((r for r in order if r in reasons), "none")
            continue
        bars = [(x, y_) for x, y_, _ in y.bars] + _lagna_gandanta(sr, nr, q)
        spans = [(a, b) for a, b, *_ in pieces]
        free = _subtract(spans, bars)
        fails = {"barred_stretches": sum(b - a for a, b in spans) * 1440}
        fails["barred_stretches"] -= sum(b - a for a, b in free) * 1440
        rows = []
        for a, b in free:
            num, nak, name, relax = next(
                (n, k, m, r) for x, y_, n, k, m, r in pieces if x <= a < y_
            )
            rows += [
                (x, y_, num, nak, name, relax, lagna)
                for x, y_, lagna in _lagna_windows(a, b, num, q, fails)
            ]
        # The day-yoga stretches go from every window; a day left with none is excluded
        # for them, with the windows they cover.
        rows, inside, yoga = _day_yogas(rows, vara, ay)
        if rows or not inside:
            yoga = {}
        else:
            rows = inside
        strict = [r for r in rows if not r[5]] if not (day_relax or yoga) else []
        if strict:
            if explain is not None:
                explain[date.isoformat()] = "listed"
            windows = _windows(strict, zone)
            nums = {w["_n"] for w in windows}
            masa = Mu.MASA.index(windows[0]["_m"])
            out_days.append(
                {
                    "date": date.isoformat(),
                    "vara": vara,
                    "lunarMonth": {
                        "amanta": MASA_IDS[masa],
                        "purnimanta": (
                            MASA_IDS[(masa + 1) % 12] if min(nums) > 15 else MASA_IDS[masa]
                        ),
                        "adhika": False,
                    },
                    "windows": _public(windows),
                    "cautions": ["krishna_last_three"] if 28 in nums else [],
                }
            )
        elif rows:
            rules = dict(day_relax) | yoga
            for r in rows:
                rules |= r[5]
            if explain is not None:
                explain[date.isoformat()] = "excluded:" + "+".join(sorted(rules))
            excluded.append(
                {
                    "date": date.isoformat(),
                    "vara": vara,
                    "windows": _public(_windows(rows, zone)),
                    "rules": sorted(rules),
                    **dict(zip(("reasons", "details"), _details(rules), strict=True)),
                }
            )
        else:
            ranked = sorted((k for k, m in fails.items() if m > 0.5), key=lambda k: -fails[k])
            near.append({"date": date.isoformat(), "vara": vara, "rules": ranked})
            if explain is not None:
                explain[date.isoformat()] = "lagna" if free else "window"
    return {
        "year": q.year,
        "days": out_days,
        "excluded": excluded,
        # An empty year names the days that failed only at the window (samskaras.md A5).
        "nearest": [] if out_days else near,
        "blocks": _blocks(y, q, frozenset(), barred_months={"Chaitra"}),  # MC 5.29
        "source": SOURCE,
        "alsoSource": {**DS, "page": "5, 137"},
        "engine": provenance(ay),
    }
