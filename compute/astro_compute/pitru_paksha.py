"""GET /v1/observances/pitru-paksha: the shraddha day of each tithi of the Mahalaya
fortnight at a place (docs/sources/observances.md s8; provisional until the lead
rules on decision 8).

Nirnaya-sindhu, 1918 Kalyan printing ("NS"). The fortnight is the dark half ending amanta
Bhadrapada (p. 215). Mahalaya shraddha is parvana, kept on the day whose
afternoon the tithi holds (p. 718):
  one day only: that day;
  both days, fully or equally in part: the earlier;
  both, unequally: the day with more (Marici);
  neither: the earlier if the tithi was current three muhurtas before the first
    day's sunset (Sumantu), otherwise the later (Gobhila; p. 719).
Windows count day muhurtas (dm, a fifteenth of sunrise to sunset), our reading
of the five-part day: the afternoon is [9, 12] dm. The Chaturdashi is only for
violent deaths and is an ekoddishta (pp. 235-236), so it takes the midday from
the kutapa to the rauhina, [7, 9] dm, where neither day goes to the earlier
(p. 718). The maternal grandfather's Ashvina shukla Pratipada takes sangava,
[3, 6] dm (p. 239).
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries

from .errors import unsupported_location
from .festivals import _date, _spans
from .fmt import provenance
from .ids import tithi_id
from .models import EkadashiQuery
from .observances import (
    SOURCE,
    _edges,
    _lunar,
    _near_call,
    _overlap,
    _shraddha,
    _sunrises,
    _sunset,
    _vara,
)
from .timeutil import iso

WINDOWS = {"aparahna": (9, 12), "kutapaRauhina": (7, 9), "sangava": (3, 6)}
BHARANI, MAGHA, HASTA = 1, 9, 12  # nakshatra indexes, Ashvini = 0
PAGES = {**SOURCE, "verse": "Mahalaya (pitr-paksha) shraddha", "page": "215–239, 717–720"}
DS_P61 = {
    "text": "Dharmasindhu",
    "edition": (
        "Kāśīnātha Upādhyāya (1790), edited by Kṛṣṇa Śāstrī Navare, First edition, "
        "Nirṇaya-sāgara Press, Bombay, 1888"
    ),
    "page": "61",
}


def _window(sunrise_jd: float, q, name: str) -> tuple[float, float]:
    a, b = WINDOWS[name]
    dm = (_sunset(sunrise_jd, q) - sunrise_jd) / 15
    return sunrise_jd + a * dm, sunrise_jd + b * dm


def _parvana_neither(start: float, s: list[float], q) -> tuple[int, str]:
    ss = _sunset(s[0], q)
    if start <= ss - 3 * (ss - s[0]) / 15:
        return 0, "neither_three_muhurtas_earlier"
    return 1, "neither_later"


def _pick(start: float, end: float, s: list[float], q, name: str, neither) -> dict:
    """The day of the two the tithi touches whose window it holds, by NS p. 718."""
    w = [_window(s[i], q, name) for i in (0, 1)]
    cov = [_overlap(start, end, *x) / (x[1] - x[0]) for x in w]
    if (cov[0] > 0) != (cov[1] > 0):
        chosen, rule = (0 if cov[0] > 0 else 1), "one_day"
    elif cov[0] > 0:
        if abs(cov[0] - cov[1]) < 1e-9:
            chosen, rule = 0, "both_earlier"
        else:
            chosen, rule = (0 if cov[0] > cov[1] else 1), "more"
    else:
        chosen, rule = neither(start, s, q)
    return {
        "date": _date(s[chosen], q),
        "vara": _vara(s[chosen], q),
        "rule": rule,
        name: [
            {
                "date": _date(s[i], q),
                "start": iso(w[i][0], q.tz),
                "end": iso(w[i][1], q.tz),
                "covered": round(cov[i], 3),
            }
            for i in (0, 1)
        ],
        "_chosen": (s[chosen], w[chosen]),
    }


def _star_day(star: int, days: list[float], q) -> dict | None:
    """The day of the fortnight whose afternoon holds the Moon's star longest."""
    nak = lambda t: Mu.nakshatra_at(t, q.ayanamsa)  # noqa: E731
    spans = _spans(nak, star, days[0], days[-1], 0.1)
    best = None
    for sr in days[:-1]:
        w = _window(sr, q, "aparahna")
        held = sum(_overlap(a, b, *w) for a, b in spans)
        if held > 0 and (best is None or held > best[0]):
            best = (held, sr)
    if best is None:
        return None
    return {"date": _date(best[1], q), "vara": _vara(best[1], q)}


def _gajacchaya(start: float, end: float, chosen: tuple, moon_star: int, q) -> bool:
    """The Moon in moon_star and the Sun in Hasta while the tithi holds the
    afternoon of its day (NS pp. 233, 238)."""
    a, b = max(start, chosen[1][0]), min(end, chosen[1][1])
    if b <= a:
        return False
    ay = q.ayanamsa
    moon = _spans(lambda t: luminaries(t, ay)[1].nakshatra, moon_star, a, b, 0.02)
    sun = _spans(lambda t: luminaries(t, ay)[0].nakshatra, HASTA, a, b, 0.02)
    return any(_overlap(m0, m1, s0, s1) > 0 for m0, m1 in moon for s0, s1 in sun)


def _row(start: float, end: float, num: int, q) -> dict:
    s = _sunrises(start, q.lat, q.lon, 3)
    row = {"tithi": tithi_id(num), "start": iso(start, q.tz), "end": iso(end, q.tz)}
    if num == 29:  # violent deaths only, an ekoddishta: the midday window
        mid = _pick(start, end, s, q, "kutapaRauhina", lambda *_: (0, "neither_earlier"))
        aft = _pick(start, end, s, q, "aparahna", _parvana_neither)
        row |= {k: v for k, v in mid.items() if k != "_chosen"}
        row["aparahna"] = aft["aparahna"]
        row["variantDate"] = aft["date"] if aft["date"] != mid["date"] else None
        return row
    if num == 30:  # the darsha rule sets the Mahalaya Amavasya too (Dharmasindhu p. 61)
        return row | _amavasya(start, end, q)
    pick = _pick(start, end, s, q, "aparahna", _parvana_neither)
    row |= {k: v for k, v in pick.items() if k != "_chosen"}
    if num == 28:
        row["gajacchaya"] = _gajacchaya(start, end, pick["_chosen"], MAGHA, q)
    return row


def _amavasya(start: float, end: float, q) -> dict:
    """NS pp. 81-87, as for every darsha shraddha (observances.md s5): the
    Amavasya touching one day's aparahna (the last third of the daytime); both or
    neither go to the kutapa tie-breaks."""
    s = _sunrises(start, q.lat, q.lon, 4)
    held = [t for t in s if start <= t < end]
    darsha: dict = {"vrata": {"date": None}}
    _shraddha(darsha, start, end, s, len(held), q)
    sh = darsha["shraddha"]
    day = next(t for t in s if _date(t, q) == sh["date"])
    dm = (_sunset(day, q) - day) / 15
    afternoon = (day, (day + 10 * dm, day + 15 * dm))
    return {
        "date": sh["date"],
        "vara": _vara(day, q),
        "rule": sh["rule"],
        "ruleGroup": "shraddha",
        "aparahna": sh["aparahna"],
        "kutapa": sh["kutapa"],
        "source": {**DS_P61, "verse": "Mahalaya and darsha shraddha on one day"},
        "gajacchaya": _gajacchaya(start, end, afternoon, HASTA, q),
    }


def pitru_paksha(q: EkadashiQuery) -> dict:
    edges = _edges(q)
    try:
        for i, (jd, num) in enumerate(edges):
            if num != 16 or i + 17 > len(edges):
                continue
            month = _lunar((jd + edges[i + 1][0]) / 2, num, q)
            if month["amanta"] == "bhadrapada" and not month["adhika"]:
                break
        else:
            raise unsupported_location("no Mahalaya fortnight in this year's range")
        rows = [
            _near_call(
                lambda a, b, qq, n=edges[k][1]: _row(a, b, n, qq), edges[k][0], edges[k + 1][0], q
            )
            for k in range(i, i + 15)
        ]
        first, last = edges[i][0], edges[i + 15][0]
        span = _sunrises(first, q.lat, q.lon, 18)
        days = [t for t in span if t < last] + [next(t for t in span if t >= last)]
        p0, p1 = edges[i + 15][0], edges[i + 16][0]  # Ashvina shukla Pratipada
        matamaha = None
        if not _lunar((p0 + p1) / 2, 1, q)["adhika"]:
            s = _sunrises(p0, q.lat, q.lon, 3)
            pick = _pick(p0, p1, s, q, "sangava", lambda *_: (1, "neither_later"))
            matamaha = {k: v for k, v in pick.items() if k != "_chosen"}
            matamaha |= {"start": iso(p0, q.tz), "end": iso(p1, q.tz)}
        bharani, magha = _star_day(BHARANI, days, q), _star_day(MAGHA, days, q)
    except RuntimeError as exc:
        raise unsupported_location(
            "the Sun does not rise on a day needed here; the shraddha days cannot be formed"
        ) from exc
    return {
        "year": q.year,
        "lunarMonth": month,
        "start": iso(first, q.tz),
        "end": iso(last, q.tz),
        "tithis": rows,
        "bharani": bharani,
        "magha": magha,
        "matamaha": matamaha,
        "source": PAGES,
        "engine": provenance(q.ayanamsa),
    }
