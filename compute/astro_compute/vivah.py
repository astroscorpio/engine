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
(MC 6.78) and mahapata.
"""

from __future__ import annotations

import datetime as dt
import math

import swisseph as swe
from jyotisha import muhurta as Mu
from jyotisha.ephemeris import luminaries, positions
from jyotisha.rare import ABHIJIT, nakshatra_28

from .errors import unsupported_location
from .fmt import provenance
from .ids import MASA_IDS, NAKSHATRA_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _edges, _rise_set, _sunset, _vara
from .timeutil import aware, iso, local_jd

GHATI = 24 / 1440
SIDEREAL_DAY = 360.9856  # time-degrees per solar day
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
SET_DISTANCE = {"Jupiter": 11.0}  # Venus: 8 retrograde, 10 direct (SS 9.6-7)
# MC 5.27 (the lead's choice; DS p. 5's 7 days and MC 5.28's 10, 7 or 3 are notes):
# (days old before setting, days infant after rising) by the side of the sky.
OLD_INFANT_DAYS = {
    "Venus": ({"east": 15, "west": 5}, {"east": 3, "west": 10}),
    "Jupiter": ({"east": 15, "west": 15}, {"east": 15, "west": 15}),
}
# DS p. 181 note: days barred after and before an eclipse, by the fraction covered.
ECLIPSE_DAYS = ((1.0, 8, 4), (0.75, 6, 3), (0.5, 4, 2), (0.0, 3, 1.5))
SOURCE = {
    "text": "Muhurta-cintamani",
    "verse": "1.46-48, 5.26, 6.13, 6.41, 6.53-54, 6.78, 6.97-99",
    "edition": "with Govinda's Piyushadhara, 1945 (6.84-85 from the 1925 printing)",
    "page": "39-42, 186-187, 234-235, 265, 275-277, 293, 305-307",
}
DS = {
    "text": "Dharmasindhu",
    "edition": "Kasinatha Upadhyaya, ed. Krsna Sastri Navare, Nirnaya-sagara Press, Bombay, 1888",
    "page": "4-5, 181-182",
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


def _kalamsa(name: str, sr: float, ss: float, q) -> tuple[float, bool]:
    """Distance from the Sun in time-degrees, and whether the planet is east of the
    Sun (an evening planet): the gap between its setting and the Sun's, or for a
    morning planet between their risings, at the place."""
    body = swe.JUPITER if name == "Jupiter" else swe.VENUS
    sun, planet = (swe.calc_ut(sr, b, swe.FLG_SWIEPH)[0][0] for b in (swe.SUN, body))
    east = (planet - sun) % 360 < 180
    if min((planet - sun) % 360, (sun - planet) % 360) > 30:
        return 999.0, east  # far from the Sun; near opposition the nearest setting is ambiguous
    geo = (q.lon, q.lat, 0.0)
    flag = swe.CALC_SET if east else swe.CALC_RISE
    res, tret = swe.rise_trans((ss if east else sr) - 0.5, body, flag | swe.BIT_DISC_CENTER, geo)
    if res != 0:
        return 0.0, east
    gap = (tret[0] - ss) if east else (sr - tret[0])
    return gap * SIDEREAL_DAY, east


def _bad_set_days(days: list[tuple[float, float]], q) -> dict[str, dict[int, tuple[str, str]]]:
    """Per planet, day index -> (set | old | infant, detail). MC 5.27: Venus is an
    infant 3 days after rising in the east and 10 after rising in the west, old 15
    days before setting in the east and 5 before setting in the west; Jupiter 15
    and 15 (it always sets in the west and rises in the east)."""
    out = {}
    for name in ("Jupiter", "Venus"):
        flags, sides = [], []
        for sr, ss in days:
            limit = SET_DISTANCE.get(name)
            if limit is None:
                speed = swe.calc_ut(sr, swe.VENUS, swe.FLG_SWIEPH | swe.FLG_SPEED)[0][3]
                limit = 8.0 if speed < 0 else 10.0
            gap, east = _kalamsa(name, sr, ss, q)
            flags.append(gap < limit)
            sides.append(east)
        state: dict[int, tuple[str, str]] = {}
        i = 0
        while i < len(flags):
            if not flags[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            # An evening planet (east of the Sun) sets in the west; a morning one
            # rises in the east.
            setting = "west" if i > 0 and sides[i - 1] else "east"
            rising = "west" if j + 1 < len(flags) and sides[j + 1] else "east"
            old_days, infant_days = OLD_INFANT_DAYS[name]
            before, after = old_days[setting], infant_days[rising]
            for k in range(max(0, i - before), i):
                state.setdefault(k, ("old", f"{before} days before setting in the {setting}"))
            for k in range(i, j + 1):
                state[k] = ("set", None)
            for k in range(j + 1, min(len(flags), j + 1 + after)):
                state.setdefault(k, ("infant", f"{after} days after rising in the {rising}"))
            i = j + 1
        out[name] = state
    return out


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


def vivah(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the first rule that rejected it."""
    ay, zone = q.ayanamsa, q.tz
    t0 = local_jd(dt.date(q.year, 1, 1), 0.0, zone, "year")
    t1 = local_jd(dt.date(q.year, 12, 31), 23.99, zone, "year")
    pad = 40
    try:
        # Every sunrise from 40 days before the year to 40 after it: the setting runs
        # of Jupiter and Venus reach across the year's ends.
        days = []
        sr = _rise_set(t0 - pad - 1, q.lat, q.lon, True)
        while sr < t1 + pad:
            nr = _rise_set(sr + 0.1, q.lat, q.lon, True)
            days.append((sr, _sunset(sr, q), nr))
            sr = nr
    except RuntimeError as exc:
        raise unsupported_location(
            "the Sun does not rise on a day needed here; marriage days cannot be formed"
        ) from exc
    set_state = _bad_set_days([(s, e) for s, e, _ in days], q)
    eclipse_bars = _eclipses(t0, t1, q)

    lo, hi = days[0][0], days[-1][2]
    edges = _edges(q)
    tithis = [(a, b, n) for (a, n), (b, _) in zip(edges, edges[1:], strict=False)]
    y0, y1 = tithis[0][0], tithis[-1][1]  # the year and a few days either side
    moon_pada = _spans(lambda t: int(luminaries(t, ay)[1].longitude // (360 / 108)), y0, y1, 1 / 12)
    sun_sign = _spans(lambda t: luminaries(t, ay)[0].sign, lo, hi, 1.0)
    jupiter = _spans(lambda t: positions(t, ay)["Jupiter"].sign, lo, hi, 2.0)
    yogas = Mu._yoga_spans(y0, y1, ay)

    bars: list[tuple[float, float, str]] = []
    for name, (a, b) in yogas:
        n = Mu.BAD_YOGA_GHATIS.get(name, 0)
        if name in Mu.BAD_YOGA_GHATIS:
            end = b if n is None else a + (b - a) / 2 if n == "half" else min(b, a + n * GHATI)
            bars.append((a, end, "bad_yoga"))
    for a, b, n in tithis:
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
    for a, _, v in moon_pada:
        nak = int(v) // 4
        if prev is not None and nak != prev and nak in NAKSHATRA_JUNCTIONS:
            bars.append((a - 2 * GHATI, a + 2 * GHATI, "gandanta_nakshatra"))
        prev = nak
    for b, _, _ in sun_sign[1:]:  # each sign change
        bars.append((b - SANKRANTI_GHATIS * GHATI, b + SANKRANTI_GHATIS * GHATI, "sankranti"))
    bars += [(a, b, "mahapata") for _, _, a, b in Mu.mahapatas(y0, y1)]

    months: dict = {}
    tithi_month = {a: _month((a + b) / 2, ay, months) for a, b, _ in tithis}
    out_days = []
    for i, (sr, ss, nr) in enumerate(days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        why = None
        if vara == "tuesday":
            why = "tuesday"
        elif any(i in set_state[p] for p in set_state):
            why = next(f"{p.lower()}_{set_state[p][i][0]}" for p in set_state if i in set_state[p])
        elif any(a <= sr + 0.5 <= b for a, b, _ in eclipse_bars):
            why = "eclipse"
        if why:
            if explain is not None:
                explain[date.isoformat()] = why
            continue
        reasons: list[str] = []
        cuts = {sr, nr}
        for spans in (tithis, moon_pada, sun_sign, jupiter):
            cuts |= {x for a, b, _ in spans for x in (a, b) if sr < x < nr}
        cuts = sorted(cuts)
        pieces = []
        for a, b in zip(cuts, cuts[1:], strict=False):
            mid = (a + b) / 2
            start, num = next((x, n) for x, y, n in tithis if x <= mid < y)
            name, adhika, kshaya, _ = tithi_month[start]
            grade = GRADE.get(name)
            if grade is None or adhika or kshaya:
                reasons.append("adhika_month" if adhika or kshaya else "month")
                continue
            if (name == "Ashadha" and num > 10) or (name == "Kartika" and num < 11):
                reasons.append("chaturmas")
                continue
            sun, moon = luminaries(mid, ay)
            if sun.sign in BARRED_SUN:
                reasons.append("sun_sign")
                continue
            p = positions(mid, ay)
            if p["Jupiter"].sign in BARRED_JUPITER:
                reasons.append("jupiter_sign")
                continue
            nak = moon.nakshatra
            if nak not in NAKSHATRAS_OK:
                reasons.append("nakshatra")
                continue
            if num in RIKTA:
                reasons.append("tithi")
                continue
            if _pierced(nak, moon.longitude, p):
                reasons.append("vedha")
                continue
            pieces.append((a, b, num, nak, grade, name))
        if not pieces:
            if explain is not None:
                explain[date.isoformat()] = _first(reasons)
            continue
        free = _subtract([(a, b) for a, b, *_ in pieces], [(x, y) for x, y, _ in bars])
        if not free and explain is not None:
            hit = [k for x, y, k in bars if any(x < b and y > a for a, b, *_ in pieces)]
            explain[date.isoformat()] = "window:" + "+".join(sorted(set(hit)))
        windows = []
        for a, b in free:
            num, nak, grade, name = next((n, k, g, m) for x, y, n, k, g, m in pieces if x <= a < y)
            row = {
                "start": iso(a, zone),
                "end": iso(b, zone),
                "nakshatra": NAKSHATRA_IDS[nak],
                "tithi": tithi_id(num),
                "paksha": "shukla" if num <= 15 else "krishna",
                "_n": num,
                "_g": grade,
                "_m": name,
            }
            if windows and windows[-1]["end"] == row["start"] and windows[-1]["_n"] == num:
                windows[-1]["end"] = row["end"]
            else:
                windows.append(row)
        if not windows:
            continue
        if explain is not None:
            explain[date.isoformat()] = "listed"
        nums = {w["_n"] for w in windows}
        cautions = []
        if nums & WEAK_TITHI:
            cautions.append("weak_tithi")
        if vara in ("sunday", "saturday"):
            bad = nums & {12, 13, 27, 28}
            cautions.append("middling_weekday_dvadashi_trayodashi" if bad else "middling_weekday")
        if any(n > 15 for n in nums):
            cautions.append("krishna_paksha")
        grade = "best" if any(w["_g"] == "best" for w in windows) else "middling"
        month = next(w["_m"] for w in windows)
        masa = Mu.MASA.index(month)
        out_days.append(
            {
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
                "godhuli": _godhuli(ss, vara, q),
            }
        )
    return {
        "year": q.year,
        "days": out_days,
        "blocks": _blocks(days, set_state, eclipse_bars, sun_sign, jupiter, q),
        "source": SOURCE,
        "alsoSource": DS,
        "engine": provenance(ay),
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


def _pierced(nak: int, moon_lon: float, p: dict) -> bool:
    """MC 6.54: a malefic anywhere in the paired star pierces the whole star; a
    benefic only the Moon's quarter that pairs with its own (1-4, 2-3)."""
    pair = VEDHA_PAIRS.get(Mu.NAKSHATRAS[nak])
    if pair is None:
        return False
    moon_pada = int((moon_lon % (360 / 27)) // (360 / 108)) + 1
    for g in MALEFICS + BENEFICS:
        lon = p[g].longitude
        if nakshatra_28(lon) != pair:
            continue
        if g in MALEFICS:
            return True
        if pair == "Abhijit":
            pada = int((lon - ABHIJIT[0]) // ((ABHIJIT[1] - ABHIJIT[0]) / 4)) + 1
        else:
            pada = int((lon % (360 / 27)) // (360 / 108)) + 1
        if PADA_PAIR[pada] == moon_pada:
            return True
    return False


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
                {"rule": "sun_sign", "start": iso(a, zone), "end": iso(b, zone), "detail": None}
            )
    for a, b, sign in jupiter:
        if sign in BARRED_JUPITER:
            rows.append(
                {"rule": "jupiter_sign", "start": iso(a, zone), "end": iso(b, zone), "detail": None}
            )
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    rows = [r for r in rows if r["end"] >= y0 and r["start"] < y1]
    return sorted(rows, key=lambda r: r["start"])
