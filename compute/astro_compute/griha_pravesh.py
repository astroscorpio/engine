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
(the commentary on 13.1, p. 439).
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, positions

from .fmt import provenance
from .ids import MASA_IDS, NAKSHATRA_IDS, SIGN_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _vara
from .timeutil import aware, iso
from .vivah import DS, _spans, _subtract, _Year

# Vasishtha in MC 13.1's commentary: Citra, the three Uttaras, Rohini, Mrgashira,
# Anuradha, Dhanishtha, Revati, Shatabhisha (0-based indexes).
STARS = {13, 11, 20, 25, 3, 4, 16, 22, 26, 23}
MONTHS = {"Magha", "Phalguna", "Vaishakha", "Jyeshtha"}
UTTARAYANA = {9, 10, 11, 0, 1, 2}  # the Sun in Capricorn to Gemini
BARRED_SUN = {3, 5, 10}  # Cancer, Virgo, Aquarius (Guru)
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
    out_days = []
    for i, (sr, _ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        why = None
        if vara in ("sunday", "tuesday"):
            why = vara
        else:
            hit = next((p for p in y.states if i in y.states[p]), None)
            if hit:
                why = f"{hit.lower()}_{y.states[hit][i][0]}"
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
            if name not in MONTHS or adhika or kshaya:
                reasons.append("month")
            elif sun.sign not in UTTARAYANA or sun.sign in BARRED_SUN:
                reasons.append("sun_sign")
            elif positions(mid, ay)["Jupiter"].sign in BARRED_JUPITER:
                reasons.append("jupiter_sign")
            elif moon.nakshatra not in STARS:
                reasons.append("nakshatra")
            elif not _pot_chakra(sun.nakshatra, moon.nakshatra):
                reasons.append("pot_chakra")
            elif num in RIKTA:
                reasons.append("tithi")
            else:
                pieces.append((a, b, num, moon.nakshatra, name))
        if not pieces:
            if explain is not None:
                explain[date.isoformat()] = _first_gp(reasons)
            continue
        free = _subtract([(a, b) for a, b, *_ in pieces], [(x, y_) for x, y_, _ in y.bars])
        windows: list[dict] = []
        for a, b in free:
            num, nak, name = next((n, k, m) for x, y_, n, k, m in pieces if x <= a < y_)
            for x, y_, lagna in _lagna_windows(a, b, q):
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
                last = windows[-1] if windows else None
                if (
                    last
                    and last["end"] == row["start"]
                    and all(last[k] == row[k] for k in ("lagna", "nakshatra", "tithi"))
                ):
                    last["end"] = row["end"]
                else:
                    windows.append(row)
        if not windows:
            if explain is not None:
                explain[date.isoformat()] = "lagna" if free else "window"
            continue
        if explain is not None:
            explain[date.isoformat()] = "listed"
        nums = {w["_n"] for w in windows}
        cautions = []
        if nums & {26, 27, 28}:
            cautions.append("krishna_after_dashami")
        if vara == "saturday":
            cautions.append("saturday")
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
                "windows": [{k: v for k, v in w.items() if not k.startswith("_")} for w in windows],
                "cautions": cautions,
            }
        )
    return {
        "year": q.year,
        "days": out_days,
        "blocks": _blocks(y, q),
        "source": SOURCE,
        "alsoSource": DS,
        "engine": provenance(ay),
    }


def _first_gp(reasons: list[str]) -> str:
    """The test the day's best piece failed: a piece stops at its first failure, so a
    later test means the earlier ones passed somewhere in the day."""
    order = ("tithi", "pot_chakra", "nakshatra", "jupiter_sign", "sun_sign", "month")
    return next((r for r in order if r in reasons), "none")


def _blocks(y: _Year, q) -> list[dict]:
    """The year's day-level bars, merged into runs: Jupiter's and Venus's states, the
    Sun's southern course and its barred signs, and Jupiter in Leo or Capricorn."""
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
                "dakshinayana" if s not in UTTARAYANA else "sun_sign" if s in BARRED_SUN else None
            ),
        ),
        (y.jupiter, lambda s: "jupiter_sign" if s in BARRED_JUPITER else None),
    ):
        for a, b, sign in spans:
            rule = rule_of(sign)
            if rule is None:
                continue
            if rows and rows[-1][0] == rule and rows[-1][2] == a:
                rows[-1] = (rule, rows[-1][1], b, None)
            else:
                rows.append((rule, a, b, None))
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    out = [
        {"rule": rule, "start": iso(a, zone), "end": iso(b, zone), "detail": detail}
        for rule, a, b, detail in rows
    ]
    out = [r for r in out if r["end"] >= y0 and r["start"] < y1]
    return sorted(out, key=lambda r: r["start"])
