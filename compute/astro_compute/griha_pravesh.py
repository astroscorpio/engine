"""GET /v1/muhurat/griha-pravesh: the year's days for entering a new house at a place
(docs/sources/griha-pravesh.md, as the lead approved it on 15 Oct 2026).

A day is listed when, at some moment of it, the amanta month is Magha, Phalguna,
Vaishakha or Jyeshtha with the Sun in its northern course and not in Cancer, Virgo
or Aquarius (MC 13.1); Jupiter and Venus are clear (MC 1.46-48, 5.27) and Jupiter
is not in Leo or Capricorn (1.48); the Moon is in one of Vasishtha's ten stars and
passes the pot chakra (13.6; DS p. 242); the tithi is not 4, 9, 14 or Amavasya; and
the day is not a Sunday or Tuesday (13.4). Its windows add a fixed or dual lagna
whose navamsa is not movable, the 4th and 8th empty, and the Moon not in the 1st,
6th, 8th or 12th (13.4; Vasishtha), less the marriage chapter's barred stretches
(the commentary on 13.1, p. 439) and the day yogas the muhurta finder vetoes.

excluded[] holds the days that pass every rule except ones almanacs relax (the
lead's list, 15 Oct 2026): Narada's middling months Kartika and Margashirsha, Guru's
bar on the Sun in Aquarius, infancy and old age beyond 3 days, Venus set at 10
time-degrees but not 8, Jupiter in Leo or Capricorn, and a day yoga that covers
every window.
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, positions

from .fmt import provenance
from .ids import MASA_IDS, NAKSHATRA_IDS, SIGN_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _vara
from .timeutil import aware, iso
from .vivah import (
    DS,
    _day_yogas,
    _details,
    _lagna_gandanta,
    _month_runs,
    _spans,
    _state_facts,
    _subtract,
    _venus_facts,
    _Year,
)

# Vasishtha in MC 13.1's commentary: Citra, the three Uttaras, Rohini, Mrgashira,
# Anuradha, Dhanishtha, Revati, Shatabhisha (0-based indexes).
STARS = {13, 11, 20, 25, 3, 4, 16, 22, 26, 23}
MONTHS = {"Magha", "Phalguna", "Vaishakha", "Jyeshtha"}
MIDDLING = {"Kartika", "Margashirsha"}  # Narada, MC 13.1 commentary: for excluded[] only
UTTARAYANA = {9, 10, 11, 0, 1, 2}  # the Sun in Capricorn to Gemini
BARRED_SUN = {3, 5, 10}  # Cancer, Virgo, Aquarius (Guru)
AQUARIUS = 10
BARRED_JUPITER = {4, 9}
MOVABLE = {0, 3, 6, 9}
RIKTA = {4, 9, 14, 19, 24, 29, 30}
SOURCE = {
    "text": "Muhurta-cintamani",
    "verse": "13.1, 13.3-6; 1.46-48, 5.27",
    "edition": "with Govinda's Piyushadhara, 1945 (13.2-3a from the 1925 printing)",
    "page": "437-447",
}


def _pot_chakra(sun_nak: int, moon_nak: int) -> bool:
    """MC 13.6, DS p. 242: the Moon's star counted from the Sun's (the 1st); 1-5 and
    14-21 are bad."""
    count = (moon_nak - sun_nak) % 27 + 1
    return not (count <= 5 or 14 <= count <= 21)


def _lagna_windows(a: float, b: float, q) -> list[tuple[float, float, int]]:
    """Stretches of [a, b] with a fixed or dual lagna, a navamsa that is not movable,
    the 4th and 8th empty, and the Moon not in the 1st, 6th, 8th or 12th."""
    ay = q.ayanamsa

    def asc(t: float) -> float:
        return ascendant(t, q.lat, q.lon, ay)[0].longitude

    out = []
    for x0, y0, lagna in _spans(lambda t: int(asc(t) // 30), a, b, 1 / 96):
        if lagna in MOVABLE:
            continue
        for x, y, idx in _spans(lambda t: int(asc(t) // (30 / 9)), x0, y0, 1 / 288):
            if idx % 12 in MOVABLE:
                continue
            p = positions((x + y) / 2, ay)
            house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
            if any(h in (4, 8) for h in house.values()) or house["Moon"] in (1, 6, 8, 12):
                continue
            out.append((x, y, lagna))
    return out


def griha_pravesh(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the rule that rejected it."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    out_days, excluded = [], []
    for i, (sr, _ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        # Rules the almanacs relax (the lead's list, 15 Oct 2026) give reasons for
        # excluded[]; the rest reject the day outright.
        day_relax: dict[str, tuple[str, dict]] = {}
        why = vara if vara in ("sunday", "tuesday") else None
        for planet, state in y.states.items():
            if i not in state:
                continue
            kind, detail = state[i]
            if i in y.relaxed[planet]:
                why = why or f"{planet.lower()}_{kind}"
            elif kind == "set":
                day_relax["venus_set"] = (
                    "Venus is within the Surya-siddhanta's 10 time-degrees of the Sun (9.6-7)",
                    _venus_facts(*y.days[i][:2], q),
                )
            else:
                day_relax["infancy_old"] = (
                    f"{planet} is in its {'infancy' if kind == 'infant' else 'old age'}, "
                    f"{detail} (Muhurta Chintamani 5.27)",
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
            if adhika or kshaya:
                reasons.append("month")
                continue
            if name in MIDDLING:
                relax["middling_month"] = (
                    f"The lunar month is {name}, which Narada counts middling for house entry; "
                    "Muhurta Chintamani 13.1 asks for the Sun's northern course",
                    {"month": MASA_IDS[Mu.MASA.index(name)]},
                )
            elif name not in MONTHS or sun.sign not in UTTARAYANA:
                reasons.append("month")
                continue
            if sun.sign in BARRED_SUN:
                if sun.sign != AQUARIUS:
                    reasons.append("sun_sign")
                    continue
                relax["sun_sign"] = (
                    "The Sun is in Aquarius, where Guru bars house entry "
                    "(Muhurta Chintamani 13.1 commentary)",
                    {"sign": SIGN_IDS[sun.sign]},
                )
            jupiter = positions(mid, ay)["Jupiter"].sign
            if jupiter in BARRED_JUPITER:
                relax["jupiter_sign"] = (
                    f"Jupiter is in {Mu.SIGNS[jupiter]}; Muhurta Chintamani 1.48 bars the "
                    "whole of its stay",
                    {"sign": SIGN_IDS[jupiter]},
                )
            if moon.nakshatra not in STARS:
                reasons.append("nakshatra")
                continue
            if not _pot_chakra(sun.nakshatra, moon.nakshatra):
                reasons.append("pot_chakra")
                continue
            if num in RIKTA:
                reasons.append("tithi")
                continue
            pieces.append((a, b, num, moon.nakshatra, name, relax))
        if not pieces:
            if explain is not None:
                explain[date.isoformat()] = _first_gp(reasons)
            continue
        bars = [(x, y_) for x, y_, _ in y.bars] + _lagna_gandanta(sr, nr, q)
        free = _subtract([(a, b) for a, b, *_ in pieces], bars)
        rows = []
        for a, b in free:
            num, nak, name, relax = next(
                (n, k, m, r) for x, y_, n, k, m, r in pieces if x <= a < y_
            )
            rows += [
                (x, y_, num, nak, name, relax, lagna) for x, y_, lagna in _lagna_windows(a, b, q)
            ]
        # The day-yoga stretches go from every window; a day left with none is
        # excluded for them, with the windows they cover.
        rows, inside, yoga = _day_yogas(rows, vara, ay)
        if rows or not inside:
            yoga = {}
        else:
            rows = inside
        strict = [r for r in rows if not r[5]] if not (day_relax or yoga) else []
        if strict:
            if explain is not None:
                explain[date.isoformat()] = "listed"
            out_days.append(_listed(date, vara, strict, zone, ay))
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
                    "windows": _public(_windows(rows, zone, ay)),
                    "rules": sorted(rules),
                    **dict(zip(("reasons", "details"), _details(rules), strict=True)),
                }
            )
        elif explain is not None:
            explain[date.isoformat()] = "lagna" if free else "window"
    return {
        "year": q.year,
        "days": out_days,
        "excluded": excluded,
        # Outside MC 13.1's four months and Narada's middling two: barred outright.
        "blocks": _blocks(y, q, barred_months=set(Mu.MASA) - MONTHS - MIDDLING),
        "source": SOURCE,
        "alsoSource": DS,
        "engine": provenance(ay),
    }


def _doors(x: float, y_: float, num: int, lagna: int, ay: str) -> list[str]:
    """The doors for which a window also passes MC 13.5, as the finder's door= applies
    it: the tithi's class for that door and the Sun on the left (13.4-5)."""
    sun = (luminaries((x + y_) / 2, ay)[0].sign - lagna) % 12 + 1
    n = (num - 1) % 15 + 1
    return [d for d in "NESW" if n in Mu.DOOR_TITHIS[d] and sun in Mu.DOOR_SUN[d]]


def _windows(rows: list[tuple], zone, ay: str | None = None) -> list[dict]:
    """Window rows, joining neighbours that share the lagna, nakshatra and tithi. With
    ay, each carries doors (pages' ask, 15 Oct 2026)."""
    out: list[dict] = []
    for x, y_, num, nak, name, _relax, lagna in rows:
        row = {
            "start": iso(x, zone),
            "end": iso(y_, zone),
            "lagna": SIGN_IDS[lagna],
            "nakshatra": NAKSHATRA_IDS[nak],
            "tithi": tithi_id(num),
            "paksha": "shukla" if num <= 15 else "krishna",
            "_n": num,
            "_m": name,
        }
        if ay is not None:
            row["doors"] = _doors(x, y_, num, lagna, ay)
        last = out[-1] if out else None
        if (
            last
            and last["end"] == row["start"]
            and all(last.get(k) == row.get(k) for k in ("lagna", "nakshatra", "tithi", "doors"))
        ):
            last["end"] = row["end"]
        else:
            out.append(row)
    return out


def _public(windows: list[dict]) -> list[dict]:
    return [{k: v for k, v in w.items() if not k.startswith("_")} for w in windows]


def _listed(date, vara: str, rows: list[tuple], zone, ay: str) -> dict:
    windows = _windows(rows, zone, ay)
    nums = {w["_n"] for w in windows}
    cautions = []
    if nums & {26, 27, 28}:
        cautions.append("krishna_after_dashami")
    if vara == "saturday":
        cautions.append("saturday")
    masa = Mu.MASA.index(windows[0]["_m"])
    return {
        "date": date.isoformat(),
        "vara": vara,
        "lunarMonth": {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if min(nums) > 15 else MASA_IDS[masa],
            "adhika": False,
        },
        "windows": _public(windows),
        "cautions": cautions,
    }


def _first_gp(reasons: list[str]) -> str:
    """The test the day's best piece failed: a piece stops at its first failure, so a
    later test means the earlier ones passed somewhere in the day."""
    order = ("tithi", "pot_chakra", "nakshatra", "jupiter_sign", "sun_sign", "month")
    return next((r for r in order if r in reasons), "none")


def _blocks(
    y: _Year, q, barred_sun: frozenset | set = BARRED_SUN, barred_months: frozenset | set = ()
) -> list[dict]:
    """The year's day-level bars, merged into runs: Jupiter's and Venus's states, the
    Sun's southern course and its barred signs, Jupiter in Leo or Capricorn, and the
    adhika months and barred lunar months (off_season, the month id in detail)."""
    zone = q.tz
    rows = []
    for planet, state in y.states.items():
        run = None
        for i in sorted(state):
            kind, detail = state[i]
            if run and run[0] == kind and run[2] == i - 1:
                run[2] = i
                continue
            if run:
                rows.append(
                    (f"{planet.lower()}_{run[0]}", y.days[run[1]][0], y.days[run[2]][2], run[3])
                )
            run = [kind, i, i, detail]
        if run:
            rows.append(
                (f"{planet.lower()}_{run[0]}", y.days[run[1]][0], y.days[run[2]][2], run[3])
            )
    for spans, rule_of in (
        (
            y.sun_sign,
            lambda s: (
                "dakshinayana" if s not in UTTARAYANA else "sun_sign" if s in barred_sun else None
            ),
        ),
        (y.jupiter, lambda s: "jupiter_sign" if s in BARRED_JUPITER else None),
    ):
        for a, b, sign in spans:
            rule = rule_of(sign)
            if rule is None:
                continue
            detail = SIGN_IDS[sign] if rule in ("jupiter_sign", "sun_sign") else None
            if rows and rows[-1][0] == rule and rows[-1][2] == a and rows[-1][3] == detail:
                rows[-1] = (rule, rows[-1][1], b, detail)
            else:
                rows.append((rule, a, b, detail))
    rows += [(rule, a, b, mid) for a, b, rule, mid in _month_runs(y, barred_months)]
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    out = [
        {"rule": rule, "start": iso(a, zone), "end": iso(b, zone), "detail": detail}
        for rule, a, b, detail in rows
    ]
    out = [r for r in out if r["end"] >= y0 and r["start"] < y1]
    return sorted(out, key=lambda r: r["start"])
