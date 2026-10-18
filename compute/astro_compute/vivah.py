"""GET /v1/muhurat/vivah: the year's marriage days at a place (docs/sources/vivah.md,
phase 1, as the lead approved it on 15 Oct 2026).

A day (sunrise to sunrise) is listed when, at some moment of it:
  the amanta month is graded (MC 6.13 commentary, Narada; DS p. 181): best Magha,
    Phalguna, Vaishakha, Jyeshtha; middling Ashadha shukla 1-10, Kartika from
    shukla 11, Margashirsha; never an adhika or kshaya month (MC 1.47; DS p. 4);
  the Sun is not in Pisces, Sagittarius or Leo (Garga in MC p. 235);
  Jupiter is not in Leo or Capricorn (MC 1.48);
  one of the 11 nakshatras holds the Moon, free of vedha (MC 6.53-54), and the tithi
    is not rikta (4, 9, 14) or Amavasya;
and the day is not a Tuesday, nor within Jupiter's or Venus's setting or the 7 days
either side (DS p. 5; distances per Surya-siddhanta 9.6-7), nor an eclipse's barred
days (DS p. 181 note). From the window go Bhadra on earth, the bad yogas' opening
ghatis (Vyatipata and Vaidhriti whole), gandanta (MC 6.41), the Sun's sankranti
(MC 6.78), mahapata, and the day yogas the muhurta finder vetoes (MC 1.20-21, 1.30;
Narada's dagdha).
"""

from __future__ import annotations

import datetime as dt
import math
import re

import swisseph as swe
from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries, positions
from jyotisha.rare import (
    ABHIJIT,
    AMRITA_SIDDHI,
    AMRITA_VISHA_TITHI,
    DAGDHA,
    KANA,
    MARANA,
    RAVI_YOGA_COUNTS,
    SARVARTHA_SIDDHI,
    SIDDHI,
    UTPATA,
    nakshatra_28,
)

from . import vivah_lagna
from .errors import unsupported_location
from .fmt import provenance
from .ids import GRAHA_ID, MASA_IDS, NAKSHATRA_ID, NAKSHATRA_IDS, SIGN_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _edges, _rise_set, _sunset, _vara
from .timeutil import aware, iso, local_jd

GHATI = 24 / 1440
GRADE = {
    "Magha": "best", "Phalguna": "best", "Vaishakha": "best", "Jyeshtha": "best",
    "Ashadha": "middling", "Kartika": "middling", "Margashirsha": "middling",
}  # fmt: skip
BARRED_SUN = {4, 8, 11}  # Leo, Sagittarius, Pisces
BARRED_JUPITER = {4, 9}  # Leo, Capricorn
# MC 6.53: Mrgashira, Hasta, Mula, Anuradha, Magha, Rohini, Revati, U.Phalguni,
# U.Ashadha, U.Bhadrapada, Svati (0-based indexes).
NAKSHATRAS_OK = {4, 12, 18, 16, 9, 3, 26, 11, 20, 25, 14}
# MC 6.54: the paired stars, mutual (28-nakshatra names).
VEDHA_PAIRS = {
    "Rohini": "Abhijit", "Bharani": "Anuradha", "U.Ashadha": "Mrigashira",
    "Shravana": "Magha", "Hasta": "U.Bhadrapada", "Swati": "Shatabhisha",
    "Mula": "Punarvasu", "Revati": "U.Phalguni",
}  # fmt: skip
VEDHA_PAIRS |= {b: a for a, b in VEDHA_PAIRS.items()}
MALEFICS = ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
BENEFICS = ("Mercury", "Jupiter", "Venus")
PADA_PAIR = {1: 4, 4: 1, 2: 3, 3: 2}
RIKTA = {4, 9, 14, 19, 24, 29, 30}
WEAK_TITHI = {6, 8, 21, 23}
# MC 6.41: one ghatika either side of the junctions 5|6, 10|11, 15|1; two either
# side of Ashlesha|Magha, Jyeshtha|Mula, Revati|Ashvini.
TITHI_JUNCTIONS = {6, 11, 16, 21, 26, 1}
NAKSHATRA_JUNCTIONS = {9, 18, 0}
SANKRANTI_GHATIS = 16.5  # half of MC 6.78's 33 each side (research's reading)
# DS p. 181 note: days barred after and before an eclipse, by the fraction covered.
ECLIPSE_DAYS = ((1.0, 8, 4), (0.75, 6, 3), (0.5, 4, 2), (0.0, 3, 1.5))
SOURCE = {
    "text": "Muhūrta-cintāmaṇi",
    "verse": "1.46–48, 5.26, 6.13, 6.41, 6.53–54, 6.78, 6.97–99",
    "edition": (
        "Rāma Daivajña (1600 CE), with the Pīyūṣadhārā commentary of Govinda Daivajña (1603), "
        "1945 printing; "
        "the 1925 printing has the same page numbers (6.84–85 from the 1925 printing)"
    ),
    "page": "39–42, 186–187, 234–235, 265, 275–277, 293, 305–307",
}
DS = {
    "text": "Dharmasindhu",
    "edition": (
        "Kāśīnātha Upādhyāya (1790), edited by Kṛṣṇa Śāstrī Navare, First edition, "
        "Nirṇaya-sāgara Press, Bombay, 1888"
    ),
    "page": "4–5, 181–182",
}


def _spans(fn, t0: float, t1: float, step: float) -> list[tuple[float, float, object]]:
    """(start, end, value) runs of fn over [t0, t1]."""
    cuts = [t0, *(t for t, _ in Mu._scan(fn, t0, t1, step)), t1]
    return [(a, b, fn((a + b) / 2)) for a, b in zip(cuts, cuts[1:], strict=False) if b > a]


def _subtract(pieces: list[tuple[float, float]], bars: list[tuple[float, float]]):
    out = []
    for a, b in pieces:
        segs = [(a, b)]
        for x, y in bars:
            nxt = []
            for p, r in segs:
                if y <= p or x >= r:
                    nxt.append((p, r))
                    continue
                if x > p:
                    nxt.append((p, x))
                if y < r:
                    nxt.append((y, r))
            segs = nxt
        out += [s for s in segs if s[1] - s[0] > 1e-6]
    return out


STATE_DETAIL = re.compile(r"(\d+) days (?:before setting|after rising) in the (east|west)")
ECLIPSE_DETAIL = re.compile(r"(lunar|solar) eclipse, ([0-9.]+) of the disc")


def _star_id(name: str) -> str:
    return "abhijit" if name == "Abhijit" else NAKSHATRA_ID[name]


def _state_facts(planet: str, kind: str, detail: str | None) -> dict:
    """infancy_old's facts for excluded[].details: planet, state, side and day count."""
    facts = {"planet": GRAHA_ID[planet], "state": kind}
    m = STATE_DETAIL.match(detail or "")
    if m:
        facts |= {"side": m.group(2), "days": int(m.group(1))}
    return facts


def _venus_facts(sr: float, ss: float, q) -> dict:
    """venus_set's facts: Venus's distance from the Sun in time-degrees (SS 9.6-7)."""
    return {"planet": "venus", "distance": round(Mu.kalamsa("Venus", sr, ss, q.lat, q.lon)[0], 2)}


def _details(rules: dict) -> tuple[list[str], list[dict]]:
    """{rule: (reason, facts)} -> the excluded day's reasons and details, by rule id."""
    keys = sorted(rules)
    return [rules[k][0] for k in keys], [{"rule": k, **rules[k][1]} for k in keys]


def _month(jd: float, ay: str, cache: dict) -> tuple[str, bool, bool, float]:
    """(name, adhika, kshaya, month start) of the amanta month holding jd. A month with
    two solar ingresses is kshaya; MC and DS bar it and the adhika months around it,
    which are adhika anyway."""
    lm = Mu.lunar_month(jd, ay)
    key = round(lm.start, 4)
    if key not in cache:
        a = positions(lm.start, ay)["Sun"].sign
        b = positions(lm.end, ay)["Sun"].sign
        cache[key] = (lm.name, lm.adhika, (b - a) % 12 == 2, lm.start)
    return cache[key]


def _eclipses(t0: float, t1: float, q) -> list[tuple[float, float, str]]:
    """(barred from, barred to, detail) for eclipses visible at the place."""
    geo = (q.lon, q.lat, 0.0)
    out = []
    for finder, kind in ((swe.lun_eclipse_when_loc, "lunar"), (swe.sol_eclipse_when_loc, "solar")):
        t = t0 - 12
        while t < t1 + 6:
            try:
                ret, tret, attr = finder(t, geo, swe.FLG_SWIEPH)
            except swe.Error:
                break
            peak = tret[0]
            if peak <= t or peak > t1 + 6:
                break
            covered = attr[0]
            if covered > 0:
                after, before = next((a, b) for m, a, b in ECLIPSE_DAYS if covered >= m)
                out.append(
                    (
                        peak - math.ceil(before),
                        peak + after,
                        f"{kind} eclipse, {min(covered, 1.0):.2f} of the disc",
                    )
                )
            t = peak + 10
    return out


class _Year:
    """What a year's dates list needs at a place: the Vedic days (40 either side, so
    Jupiter's and Venus's runs reach across the year's ends), Jupiter's and Venus's
    states, the tithi, Moon-quarter, Sun-sign and Jupiter-sign spans, the amanta
    month of each tithi, and the barred stretches (Bhadra on earth, the bad yogas,
    gandanta, the Sun's sankranti and mahapata)."""

    def __init__(self, q: EkadashiQuery, pad: int = 40):
        self.q, self.ay, self.zone = q, q.ayanamsa, q.tz
        ay = q.ayanamsa
        self.t0 = local_jd(dt.date(q.year, 1, 1), 0.0, q.tz, "year")
        self.t1 = local_jd(dt.date(q.year, 12, 31), 23.99, q.tz, "year")
        try:
            days = []
            sr = _rise_set(self.t0 - pad - 1, q.lat, q.lon, True)
            while sr < self.t1 + pad:
                nr = _rise_set(sr + 0.1, q.lat, q.lon, True)
                days.append((sr, _sunset(sr, q), nr))
                sr = nr
        except RuntimeError as exc:
            raise unsupported_location(
                "the Sun does not rise on a day needed here; the dates cannot be formed"
            ) from exc
        self.days = days
        pairs = [(s, e) for s, e, _ in days]
        self.states = Mu.jupiter_venus_states(pairs, q.lat, q.lon)
        # The almanac count, for excluded[]: Venus at 8 time-degrees either way and
        # three days of infancy and old age (MC 5.28's shortest).
        three = {"east": 3, "west": 3}
        self.relaxed = Mu.jupiter_venus_states(
            pairs, q.lat, q.lon, {"Venus": (three, three), "Jupiter": (three, three)}, 8.0
        )
        lo, hi = days[0][0], days[-1][2]
        edges = _edges(q)
        self.tithis = [(a, b, n) for (a, n), (b, _) in zip(edges, edges[1:], strict=False)]
        y0, y1 = self.tithis[0][0], self.tithis[-1][1]
        self.moon_pada = _spans(
            lambda t: int(luminaries(t, ay)[1].longitude // (360 / 108)), y0, y1, 1 / 12
        )
        self.sun_sign = _spans(lambda t: luminaries(t, ay)[0].sign, lo, hi, 1.0)
        self.jupiter = _spans(lambda t: positions(t, ay)["Jupiter"].sign, lo, hi, 2.0)
        months: dict = {}
        self.tithi_month = {a: _month((a + b) / 2, ay, months) for a, b, _ in self.tithis}
        bars: list[tuple[float, float, str]] = []
        for name, (a, b) in Mu._yoga_spans(y0, y1, ay):
            if name in Mu.BAD_YOGA_GHATIS:
                n = Mu.BAD_YOGA_GHATIS[name]
                end = b if n is None else a + (b - a) / 2 if n == "half" else min(b, a + n * GHATI)
                bars.append((a, end, "bad_yoga"))
        for a, b, n in self.tithis:
            if n in TITHI_JUNCTIONS:
                bars.append((a - GHATI, a + GHATI, "gandanta_tithi"))
            if n in (4, 8, 11, 15, 18, 22, 25, 29):
                for x, y, v in _spans(lambda t: Mu.karana_at(t, ay), a, b, 0.05):
                    if v != "Vishti":
                        continue
                    for u, w, sign in _spans(lambda t: luminaries(t, ay)[1].sign, x, y, 1 / 24):
                        if Mu.bhadra_residence(sign) == "earth":
                            bars.append((u, w, "bhadra"))
        prev = None
        for a, _, v in self.moon_pada:
            nak = int(v) // 4
            if prev is not None and nak != prev and nak in NAKSHATRA_JUNCTIONS:
                bars.append((a - 2 * GHATI, a + 2 * GHATI, "gandanta_nakshatra"))
            prev = nak
        for b, _, _ in self.sun_sign[1:]:  # each sign change
            bars.append((b - SANKRANTI_GHATIS * GHATI, b + SANKRANTI_GHATIS * GHATI, "sankranti"))
        bars += [(a, b, "mahapata") for _, _, a, b in Mu.mahapatas(y0, y1)]
        self.bars = bars

    def cuts(self, sr: float, nr: float) -> list[float]:
        out = {sr, nr}
        for spans in (self.tithis, self.moon_pada, self.sun_sign, self.jupiter):
            out |= {x for a, b, _ in spans for x in (a, b) if sr < x < nr}
        return sorted(out)

    def tithi(self, t: float) -> tuple[int, tuple]:
        start, num = next((x, n) for x, y, n in self.tithis if x <= t < y)
        return num, self.tithi_month[start]


WEEKDAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")


def _lagna_gandanta(sr: float, nr: float, q) -> list[tuple[float, float]]:
    """MC 6.41: half a ghatika either side of the lagna's Cancer-Leo, Scorpio-Sagittarius
    and Pisces-Aries boundaries, left out of every window (the lead's decision of 15 Oct
    2026)."""
    fn = lambda t: Mu.lagna_at(t, q.lat, q.lon, q.ayanamsa)  # noqa: E731
    edges = Mu._scan(fn, sr - GHATI, nr + GHATI, 1 / 96)
    return [(t - GHATI / 2, t + GHATI / 2) for t, sign in edges if sign in Mu.JUNCTION_LAGNAS]


def _day_yogas(rows: list[tuple], vara: str, ay: str):
    """Split rows (start, end, ...) at the weekday-nakshatra stretches the muhurta
    finder vetoes: MC 1.30's utpata, mrtyu and kana (28 nakshatras), Narada's dagdha
    (MC 1.5 commentary) and a siddhi pair on its visha tithi (MC 1.20-21). A Ravi or
    siddhi yoga at the same moment lifts them (MC 1.27, 1.42); only a Ravi yoga lifts
    the visha. Returns the rows outside them, the rows inside, and {rule id: (reason,
    facts)} for those inside (the lead's decisions of 15 Oct 2026)."""
    w = WEEKDAYS.index(vara)
    day = vara.capitalize()

    def fn(t: float) -> frozenset:
        sun, moon = luminaries(t, ay)
        lon = moon.longitude
        n28, n27 = nakshatra_28(lon), Mu.NAKSHATRAS[int(lon // (360 / 27)) % 27]
        if (moon.nakshatra - sun.nakshatra) % 27 + 1 in RAVI_YOGA_COUNTS:
            return frozenset()
        visha_day = (Mu.tithi_at(t, ay) - 1) % 15 + 1 == AMRITA_VISHA_TITHI[w]
        siddhi = (
            (AMRITA_SIDDHI.get(w) == n27 and not visha_day)
            or n27 in SARVARTHA_SIDDHI.get(w, set())
            or SIDDHI.get(w) == n28
        )
        out = set()
        for rid, name, table in (
            ("utpata", "Utpata", UTPATA),
            ("marana", "Mrtyu", MARANA),
            ("kana", "Kana", KANA),
        ):
            if table.get(w) == n28:
                text = f"{n28} on a {day} is {name} yoga (Muhūrta-cintāmaṇi 1.30)"
                out.add((rid, text, (("weekday", vara), ("star", _star_id(n28)))))
        if DAGDHA.get(w) == n27:
            text = f"{n27} on a {day} is Dagdha yoga (Nārada in Muhūrta-cintāmaṇi 1.5)"
            out.add(("dagdha", text, (("weekday", vara), ("star", _star_id(n27)))))
        if siddhi:
            out.clear()
        if AMRITA_SIDDHI.get(w) == n27 and visha_day:
            tithi = Mu.TITHI_NAMES[AMRITA_VISHA_TITHI[w] - 1]
            text = (
                f"{n27} on a {day} is a siddhi pair, turned to visha on {tithi} "
                "(Muhūrta-cintāmaṇi 1.20–21)"
            )
            facts = (("weekday", vara), ("star", _star_id(n27)))
            out.add(("visha", text, (*facts, ("tithi", tithi_id(AMRITA_VISHA_TITHI[w])))))
        return frozenset(out)

    free, inside, why = [], [], {}
    for r in rows:
        for a, b, hits in _spans(fn, r[0], r[1], 1 / 48):
            if hits:
                inside.append((a, b, *r[2:]))
                why |= {rid: (text, dict(facts)) for rid, text, facts in hits}
            else:
                free.append((a, b, *r[2:]))
    return free, inside, why


ALLOWED_SOLAR = {0, 1, 2, 7, 9, 10}  # MC 6.13's first half: Sun in these signs
SLOW = {"Jupiter", "Saturn", "Rahu", "Ketu"}
TITHI_NAME = {4: "Chaturthi", 9: "Navami", 14: "Chaturdashi"}


def vivah(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the first rule that rejected it."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    eclipse_bars = _eclipses(y.t0, y.t1, q)
    out_days, excluded = [], []
    for i, (sr, ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        # Rules the almanacs relax (the lead's list, 15 Oct 2026) give reasons; the
        # rest exclude the day outright.
        day_relax: dict[str, tuple[str, dict]] = {}
        strict_why = None
        if vara == "tuesday":
            day_relax["tuesday"] = (
                "Tuesday, which Vasiṣṭha avoids always (Muhūrta-cintāmaṇi 6.53)",
                {"weekday": vara},
            )
        for planet, state in y.states.items():
            if i not in state:
                continue
            kind, detail = state[i]
            if i in y.relaxed[planet]:
                strict_why = strict_why or f"{planet.lower()}_{kind}"
            elif kind == "set":
                day_relax["venus_set"] = (
                    "Venus is within the Sūrya-siddhānta's 10 time-degrees of the Sun (9.6–7)",
                    _venus_facts(sr, ss, q),
                )
            else:
                day_relax["infancy_old"] = (
                    f"{planet} is in its {'infancy' if kind == 'infant' else 'old age'}, "
                    f"{detail} (Muhūrta-cintāmaṇi 5.27)",
                    _state_facts(planet, kind, detail),
                )
        hit = next((d for a, b, d in eclipse_bars if a <= sr + 0.5 <= b), None)
        if hit:
            m = ECLIPSE_DETAIL.match(hit)
            day_relax["eclipse"] = (
                f"Within the days barred around a {hit} (Dharmasindhu p. 181)",
                {"kind": m.group(1), "magnitude": float(m.group(2))} if m else {},
            )
        if strict_why:
            if explain is not None:
                explain[date.isoformat()] = strict_why
            continue
        reasons: list[str] = []
        pieces = []
        cuts = y.cuts(sr, nr)
        for a, b in zip(cuts, cuts[1:], strict=False):
            mid = (a + b) / 2
            num, (name, adhika, kshaya, _) = y.tithi(mid)
            relax: dict[str, tuple[str, dict]] = {}
            grade = GRADE.get(name)
            if adhika or kshaya:
                reasons.append("adhika_month")
                continue
            sun, moon = luminaries(mid, ay)
            if (name == "Ashadha" and num > 10) or (name == "Kartika" and num < 11):
                reasons.append("chaturmas")
                continue
            if grade is None:
                if name in ("Shravana", "Bhadrapada", "Ashwin") or sun.sign not in ALLOWED_SOLAR:
                    reasons.append("month")
                    continue
                relax["solar_month"] = (
                    f"The lunar month is {name}; Muhūrta-cintāmaṇi's commentary sets aside "
                    "counting by the solar month",
                    {"month": MASA_IDS[Mu.MASA.index(name)], "sunSign": SIGN_IDS[sun.sign]},
                )
            if sun.sign in BARRED_SUN:
                reasons.append("sun_sign")
                continue
            p = positions(mid, ay)
            if p["Jupiter"].sign in BARRED_JUPITER:
                relax["jupiter_sign"] = (
                    f"Jupiter is in {Mu.SIGNS[p['Jupiter'].sign]}; Muhūrta-cintāmaṇi 1.48 "
                    "bars marriage for its whole stay",
                    {"sign": SIGN_IDS[p["Jupiter"].sign]},
                )
            nak = moon.nakshatra
            if nak not in NAKSHATRAS_OK:
                reasons.append("nakshatra")
                continue
            base = (num - 1) % 15 + 1
            if num == 30:
                reasons.append("tithi")
                continue
            if base in TITHI_NAME:
                relax["rikta"] = (
                    f"{TITHI_NAME[base]} is a rikta tithi, barred by Muhūrta-cintāmaṇi 6.53",
                    {"tithi": tithi_id(num)},
                )
            piercers = _pierced(nak, moon.longitude, p)
            if piercers and not set(piercers) <= SLOW:
                reasons.append("vedha")
                continue
            if piercers:
                star = Mu.NAKSHATRAS[nak]
                relax["vedha_slow"] = (
                    f"{', '.join(piercers)} in {VEDHA_PAIRS[star]} pierces {star} "
                    "(Muhūrta-cintāmaṇi 6.54)",
                    {
                        "planets": [GRAHA_ID[g] for g in piercers],
                        "star": _star_id(VEDHA_PAIRS[star]),
                        "pierces": NAKSHATRA_IDS[nak],
                    },
                )
            pieces.append((a, b, num, nak, grade or "middling", name, relax))
        if not pieces:
            if explain is not None:
                explain[date.isoformat()] = _first(reasons)
            continue
        bars = [(x, y_) for x, y_, _ in y.bars] + _lagna_gandanta(sr, nr, q)
        free = _subtract([(a, b) for a, b, *_ in pieces], bars)
        rows = []
        for a, b in free:
            num, nak, grade, name, relax = next(
                (n, k, g, m, r) for x, y_, n, k, g, m, r in pieces if x <= a < y_
            )
            rows.append((a, b, num, nak, grade, name, relax))
        # The day-yoga stretches go from every window; a day left with none is
        # excluded for them, with the windows they cover.
        rows, inside, yoga = _day_yogas(rows, vara, ay)
        if rows or not inside:
            yoga = {}
        else:
            rows = inside
        strict = [r for r in rows if not r[6]] if not (day_relax or yoga) else []
        if strict:
            day = _listed(date, vara, sr, ss, strict, q)
            # The lead's decision (16 Oct 2026): a day left with no lagna and no godhuli
            # offers no time, so it moves to excluded[] as no_lagna.
            if day["lagnaStatus"] == "none":
                excluded.append(_no_lagna(day))
            else:
                out_days.append(day)
            if explain is not None:
                explain[date.isoformat()] = (
                    "excluded:no_lagna" if day["lagnaStatus"] == "none" else "listed"
                )
            continue
        if rows:
            rules = dict(day_relax) | yoga
            for r in rows:
                rules |= r[6]
            if explain is not None:
                explain[date.isoformat()] = "excluded:" + "+".join(sorted(rules))
            excluded.append(
                {
                    "date": date.isoformat(),
                    "vara": vara,
                    "windows": [
                        {k: v for k, v in w.items() if not k.startswith("_")}
                        for w in _windows(rows, q)
                    ],
                    "rules": sorted(rules),
                    **dict(zip(("reasons", "details"), _details(rules), strict=True)),
                }
            )
        elif explain is not None:
            hit = [k for x, y_, k in y.bars if any(x < b and y_ > a for a, b, *_ in pieces)]
            explain[date.isoformat()] = "window:" + "+".join(sorted(set(hit)))
    return {
        "year": q.year,
        "days": out_days,
        "excluded": excluded,
        "blocks": _blocks(y.days, y.states, eclipse_bars, y.sun_sign, y.jupiter, q)
        + _season_blocks(y, q),
        "source": SOURCE,
        "alsoSource": DS,
        "engine": provenance(ay),
    }


def _windows(rows: list[tuple], q) -> list[dict]:
    """Window rows, joining neighbours that share a tithi."""
    out: list[dict] = []
    for a, b, num, nak, *_ in rows:
        row = {
            "start": iso(a, q.tz),
            "end": iso(b, q.tz),
            "nakshatra": NAKSHATRA_IDS[nak],
            "tithi": tithi_id(num),
            "paksha": "shukla" if num <= 15 else "krishna",
            "_n": num,
            "_a": a,
            "_b": b,
        }
        if out and out[-1]["end"] == row["start"] and out[-1]["_n"] == num:
            out[-1]["end"], out[-1]["_b"] = row["end"], b
        else:
            out.append(row)
    return out


def _listed(date: dt.date, vara: str, sr: float, ss: float, rows: list[tuple], q) -> dict:
    windows = _windows(rows, q)
    # Phase 2 (V1-V10): the lagnas in each window; the dark fortnight's Moon is malefic.
    for w in windows:
        w.update(vivah_lagna.window(w["_a"], w["_b"], q, w["_n"] <= 15, sr, ss))
    nums = {w["_n"] for w in windows}
    godhuli = _godhuli(ss, vara, q)
    lagnas = [lg for w in windows for lg in w["lagnas"]]
    if any(lg["clean"] for lg in lagnas):
        status = "clean"
    else:
        status = "faulted" if lagnas else "godhuli" if godhuli else "none"
    cautions = []
    if status != "clean":
        cautions.append("no_clean_lagna")  # V9: godhuli remains the texts' alternative
    if nums & WEAK_TITHI:
        cautions.append("weak_tithi")
    if vara in ("sunday", "saturday"):
        bad = nums & {12, 13, 27, 28}
        cautions.append("middling_weekday_dvadashi_trayodashi" if bad else "middling_weekday")
    if any(n > 15 for n in nums):
        cautions.append("krishna_paksha")
    grade = "best" if any(r[4] == "best" for r in rows) else "middling"
    masa = Mu.MASA.index(rows[0][5])
    return {
        "date": date.isoformat(),
        "vara": vara,
        "grade": grade,
        "lunarMonth": {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if min(nums) > 15 else MASA_IDS[masa],
            "adhika": False,
        },
        "windows": [{k: v for k, v in w.items() if not k.startswith("_")} for w in windows],
        "cautions": cautions,
        "lagnaStatus": status,
        "godhuli": godhuli,
    }


def _no_lagna(day: dict) -> dict:
    """A listed day with neither a lagna nor godhuli, as an excluded day: its barred
    minutes by rule, summed over the windows."""
    barred: dict[str, int] = {}
    for w in day["windows"]:
        for rule, m in w["lagnaBars"].items():
            barred[rule] = barred.get(rule, 0) + m
    rules = {
        "no_lagna": (
            "No lagna in the windows clears Muhūrta-cintāmaṇi's lagna rules (ch. 6), and "
            "godhuli is excluded (6.99)",
            {"barred": dict(sorted(barred.items()))},
        )
    }
    reasons, details = _details(rules)
    return {
        "date": day["date"],
        "vara": day["vara"],
        "windows": [
            {k: v for k, v in w.items() if k not in ("lagnas", "lagnaBars")} for w in day["windows"]
        ],
        "rules": ["no_lagna"],
        "reasons": reasons,
        "details": details,
    }


def _first(reasons: list[str]) -> str:
    """The broadest reason a day failed: season rules before the day's own."""
    # A piece fails at its first test, so tithi and vedha imply an allowed nakshatra.
    order = (
        "adhika_month",
        "month",
        "chaturmas",
        "sun_sign",
        "jupiter_sign",
        "vedha",
        "tithi",
        "nakshatra",
    )
    return next((r for r in order if r in reasons), "none")


def _pierced(nak: int, moon_lon: float, p: dict) -> list[str]:
    """MC 6.54: the planets piercing the Moon's star. A malefic anywhere in the
    paired star pierces the whole star; a benefic only the Moon's quarter that pairs
    with its own (1-4, 2-3)."""
    pair = VEDHA_PAIRS.get(Mu.NAKSHATRAS[nak])
    if pair is None:
        return []
    moon_pada = int((moon_lon % (360 / 27)) // (360 / 108)) + 1
    out = []
    for g in MALEFICS + BENEFICS:
        lon = p[g].longitude
        if nakshatra_28(lon) != pair:
            continue
        if g in MALEFICS:
            out.append(g)
            continue
        if pair == "Abhijit":
            pada = int((lon - ABHIJIT[0]) // ((ABHIJIT[1] - ABHIJIT[0]) / 4)) + 1
        else:
            pada = int((lon % (360 / 27)) // (360 / 108)) + 1
        if PADA_PAIR[pada] == moon_pada:
            out.append(g)
    return out


def _godhuli(ss: float, vara: str, q) -> dict | None:
    """MC 6.97-99: half a ghatika either side of sunset; Thursday only before it,
    Saturday only after; none with the Moon 1st, 6th or 8th from the lagna or
    Mars 1st, 7th or 8th."""
    a, b = ss - GHATI / 2, ss + GHATI / 2
    if vara == "thursday":
        b = ss
    elif vara == "saturday":
        a = ss
    lagna = Mu.lagna_at(ss, q.lat, q.lon, q.ayanamsa)
    p = positions(ss, q.ayanamsa)
    house = {g: (p[g].sign - lagna) % 12 + 1 for g in ("Moon", "Mars")}
    if house["Moon"] in (1, 6, 8) or house["Mars"] in (1, 7, 8):
        return None
    return {"start": iso(a, q.tz), "end": iso(b, q.tz)}


def _blocks(days, set_state, eclipse_bars, sun_sign, jupiter, q) -> list[dict]:
    """The year's day-level bars, merged into runs, for display."""
    zone = q.tz
    out = []
    for planet, state in set_state.items():
        run = None
        for i in sorted(state):
            kind, detail = state[i]
            if run and run[0] == kind and run[2] == i - 1:
                run[2] = i
                continue
            if run:
                out.append((planet, *run))
            run = [kind, i, i, detail]
        if run:
            out.append((planet, *run))
    rows = []
    for planet, kind, i, j, detail in out:
        a, b = days[i][0], days[j][2]
        rows.append(
            {
                "rule": f"{planet.lower()}_{kind}",
                "start": iso(a, zone),
                "end": iso(b, zone),
                "detail": detail,
            }
        )
    for a, b, detail in eclipse_bars:
        rows.append(
            {"rule": "eclipse", "start": iso(a, zone), "end": iso(b, zone), "detail": detail}
        )
    for a, b, sign in sun_sign:
        if sign in BARRED_SUN:
            rows.append(
                {
                    "rule": "sun_sign",
                    "start": iso(a, zone),
                    "end": iso(b, zone),
                    "detail": SIGN_IDS[sign],
                }
            )
    for a, b, sign in jupiter:
        if sign in BARRED_JUPITER:
            rows.append(
                {
                    "rule": "jupiter_sign",
                    "start": iso(a, zone),
                    "end": iso(b, zone),
                    "detail": SIGN_IDS[sign],
                }
            )
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    rows = [r for r in rows if r["end"] >= y0 and r["start"] < y1]
    return sorted(rows, key=lambda r: r["start"])


def _month_runs(y: _Year, barred) -> list[tuple[float, float, str, str]]:
    """(start, end, rule, month id) for each adhika or kshaya month (adhika_month) and
    each pure amanta month named in barred (off_season), from new moon to new moon,
    at the instants the day tests use."""
    months: dict[float, list] = {}
    for a, b, _ in y.tithis:
        name, adhika, kshaya, start = y.tithi_month[a]
        m = months.setdefault(start, [name, adhika, kshaya, a, b])
        m[3], m[4] = min(m[3], a), max(m[4], b)
    runs = []
    for start, (name, adhika, kshaya, a, b) in months.items():
        rule = "adhika_month" if adhika or kshaya else "off_season" if name in barred else None
        if rule:
            # The month's own new moons, not the edges of the year's tithi list.
            end = Mu.lunar_month((a + b) / 2, y.ay).end
            runs.append((start, end, rule, MASA_IDS[Mu.MASA.index(name)]))
    return runs


def _season_blocks(y: _Year, q) -> list[dict]:
    """The season as runs, at the instants the day test uses: chaturmas from the Ashadha
    shukla Ekadashi to the Kartika shukla Ekadashi, each amanta month outside MC's season
    (off_season, its month id in detail), and the adhika or kshaya months."""
    outside = {m for m in Mu.MASA if m not in GRADE}
    runs = [(rule, a, b, mid) for a, b, rule, mid in _month_runs(y, outside)]

    def ekadashis(month: str) -> list[float]:
        return [
            a
            for a, _, n in y.tithis
            if n == 11 and y.tithi_month[a][0] == month and not y.tithi_month[a][1]
        ]

    ends = ekadashis("Kartika")
    for start in ekadashis("Ashadha"):
        end = next((x for x in ends if x > start), None)
        if end is not None:
            runs.append(("chaturmas", start, end, None))
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    rows = [
        {"rule": rule, "start": iso(a, q.tz), "end": iso(b, q.tz), "detail": detail}
        for rule, a, b, detail in runs
    ]
    return [r for r in rows if r["end"] >= y0 and r["start"] < y1]
