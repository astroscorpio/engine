"""POST /v1/muhurat/vivah/personal (contract 7q): the public vivah list's days inside a
span, judged for one couple by docs/sources/vivah.md section 5 and "Phase 3" (P1-P8, as
the lead approved them on 16 Oct 2026).

  P1 Jupiter from the bride's Moon sign (MC's table, p. 233): information only.
  P2 the Sun for the groom, P3 the Moon for both: the site's gochara (PD 26, with vedha).
  P4 tara for both: the 3rd, 5th and 7th are bad (MC 4.18 commentary), lifted by MC 5.32.
  P5 the first-born's birth month, star, tithi and muhurta (MC 6.14), P6 the three
     jyeshthas (MC 6.15; DS p. 181): only for a partner marked eldest.
  P7 the 8th lagna (MC 6.44-45, Guru's remedy), P8 the rising sign (Kashyapa, Narada).

The couple's birth data stays in the request: nothing here is stored or cached.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import swisseph as swe
from jyotisha import muhurta as Mu
from jyotisha.chart import EXALTATION, NATURAL_FRIENDS, OWN_SIGNS, SIGN_LORDS
from jyotisha.ephemeris import positions, sunrise, sunset

from .errors import ApiError, invalid
from .fmt import provenance
from .ids import MASA_IDS, NAKSHATRA_IDS, SIGN_IDS, tithi_id
from .matching import moon_of
from .models import VIVAH_SPAN_DAYS, ChartIn, EkadashiQuery, VivahPersonalRequest
from .timeutil import iso
from .transit_service import _gochara_from
from .vivah import vivah
from .vivah_lagna import NAV, _sees

JUPITER_BRIDE = {
    **dict.fromkeys((2, 5, 7, 9, 11), "best"),
    **dict.fromkeys((1, 3, 6, 10), "worship"),
    **dict.fromkeys((4, 8, 12), "condemned"),
}
BAD_TARA = {3, 5, 7}  # vipat, pratyari, vadha (MC 4.18 commentary, p. 157)
# MC 6.45: these 8th signs cause no fault, so only a birth sign whose 8th is not among
# them gives the bar: Taurus, Cancer, Virgo, Scorpio, Capricorn, Pisces.
EXEMPT_EIGHTH = {11, 1, 3, 7, 9, 5}
UPACAYA = {3, 6, 10, 11}
BENEFICS = ("Mercury", "Jupiter", "Venus")
SIDES = ("bride", "groom")


@dataclass
class Partner:
    side: str
    basis: str
    time_known: bool
    uncertain: bool
    moon_sign: int
    star: int
    pada: int
    eldest: bool
    lagna: int | None = None
    month: str | None = None  # amanta month id
    tithi: int | None = None  # 1-30
    muhurta: tuple[bool, int] | None = None  # (by day, 1-15)
    skipped: list[str] = field(default_factory=list)


def _partner(raw, side: str, eldest: bool) -> Partner:
    moon = moon_of(raw, side)
    p = Partner(
        side, moon.basis, bool(moon.time_known), moon.uncertain, moon.sign, moon.nakshatra,
        moon.pada, eldest,
    )  # fmt: skip
    if isinstance(raw, ChartIn) and moon.chart is not None:
        c = moon.chart
        name = Mu.lunar_month(c.jd, c.ayanamsa).name
        p.month = MASA_IDS[Mu.MASA.index(name)]
        p.tithi = Mu.tithi_at(c.jd, c.ayanamsa)
        if moon.time_known:
            p.lagna = c.asc.sign
            p.muhurta = _muhurta_of(c.jd, c.lat, c.lon)
    if p.lagna is None:
        p.skipped.append("eighth_lagna_from_lagna")
    if eldest:
        p.skipped += [
            r for r, v in (("birth_month", p.month), ("birth_tithi", p.tithi)) if v is None
        ]
        if p.muhurta is None:
            p.skipped.append("birth_muhurta")
    return p


def _muhurta_of(jd: float, lat: float, lon: float) -> tuple[bool, int]:
    """Which of the fifteen muhurtas of the day or of the night holds jd."""
    sr = sunrise(jd, lat, lon)
    ss = sunset(jd, lat, lon)
    if jd < ss:
        return True, min(15, int((jd - sr) / ((ss - sr) / 15)) + 1)
    nxt = sunrise(sr + 1.2, lat, lon)
    return False, min(15, int((jd - ss) / ((nxt - ss) / 15)) + 1)


def _jd(text: str) -> float:
    t = dt.datetime.fromisoformat(text).astimezone(dt.UTC)
    return swe.julday(t.year, t.month, t.day, t.hour + t.minute / 60 + t.second / 3600)


def _tara(birth_star: int, star: int) -> int:
    return ((star - birth_star) % 27 + 1) % 9 or 9


def _mark(rule: str, sides: list[str]) -> dict:
    return {"rule": rule, "side": "both" if len(sides) == 2 else sides[0]}


def _moment(t: float, couple: list[Partner], bright: bool) -> tuple[list, list, list, list]:
    """P2-P5 at one moment: (bars, faults, supports, lifted) as marks."""
    p = positions(t)
    moon = p["Moon"]
    star = int(moon.longitude // (360 / 27)) % 27
    tithi = Mu.tithi_at(t)
    bars, faults, supports, lifted = [], [], [], []
    lord = SIGN_LORDS[moon.sign]
    benefic_sign = lord in BENEFICS or (moon.sign == 3 and bright)
    weak_moon, bad_tara, fav = [], [], []
    for x in couple:
        goch = _gochara_from(x.moon_sign, p)
        moon_good = goch["Moon"][0] == "good"
        if moon_good:
            supports.append(_mark("moon_good", [x.side]))
        else:
            weak_moon.append(x.side)
        if _tara(x.star, star) in BAD_TARA:
            if benefic_sign and moon_good:
                lifted.append({**_mark("tara_bad", [x.side]), "by": "mc_5_32"})
            else:
                bad_tara.append(x.side)
        if x.side == "groom":
            if goch["Sun"][0] == "good":
                supports.append(_mark("sun_groom", ["groom"]))
            else:
                faults.append(_mark("sun_groom_weak", ["groom"]))
        if x.eldest:
            if star == x.star:
                bars.append(_mark("birth_star", [x.side]))
            if x.tithi is not None and tithi == x.tithi:
                bars.append(_mark("birth_tithi", [x.side]))
        elif star == x.star or (x.tithi is not None and tithi == x.tithi):
            fav.append(x.side)
    if len(weak_moon) == 2:
        bars.append(_mark("moon_weak_both", weak_moon))
    elif weak_moon:
        faults.append(_mark("moon_weak", weak_moon))
    if len(bad_tara) == 2:
        bars.append(_mark("tara_bad_both", bad_tara))
    elif bad_tara:
        faults.append(_mark("tara_bad", bad_tara))
    if fav:
        supports.append(_mark("birth_day_favourable", fav))
    return bars, faults, supports, lifted


def _guru_remedy(sign: int, t: float) -> str | None:
    """MC p. 272 (Guru): which condition lifts the 8th lagna, if any: the rising sign's
    lord in a kendra with a benefic's aspect, in its own or a benefic's navamsa, exalted,
    or in its own or a friend's sign (BPHS)."""
    p = positions(t)
    lord = SIGN_LORDS[sign]
    at = p[lord].sign
    if (at - sign) % 12 + 1 in (1, 4, 7, 10) and any(
        _sees(p, b, at, occupy=False) for b in BENEFICS if b != lord
    ):
        return "guru_kendra_aspect"
    nav = int(p[lord].longitude // NAV) % 12
    if nav in OWN_SIGNS[lord] or SIGN_LORDS[nav] in BENEFICS:
        return "guru_navamsa"
    if at == EXALTATION[lord][0]:
        return "guru_exalted"
    if at in OWN_SIGNS[lord] or SIGN_LORDS[at] in NATURAL_FRIENDS[lord][0]:
        return "guru_own_friend"
    return None


def _lagna_marks(sign: int, t: float, couple: list[Partner]) -> tuple[list, list, list, list]:
    """P7 and P8 for the sign rising at t: (bars, faults, supports, lifted)."""
    bars, faults, supports, lifted = [], [], [], []
    eighth, rashi, good = [], [], []
    for x in couple:
        births = [x.moon_sign] + ([x.lagna] if x.lagna is not None else [])
        if any((b + 7) % 12 == sign and (b + 7) % 12 not in EXEMPT_EIGHTH for b in births):
            eighth.append(x.side)
        if sign == x.moon_sign:
            rashi.append(x.side)
        if sign == x.lagna or any((sign - b) % 12 + 1 in UPACAYA for b in births):
            good.append(x.side)
    if eighth:
        remedy = _guru_remedy(sign, t)
        if remedy:
            lifted.append({**_mark("eighth_lagna", eighth), "by": remedy})
        else:
            bars.append(_mark("eighth_lagna", eighth))
    if rashi:
        faults.append(_mark("janma_rashi_rising", rashi))
    if good:
        supports.append(_mark("janma_lagna_rising", good))
    return bars, faults, supports, lifted


def _muhurta_bars(day: dict, couple: list[Partner], q) -> list[tuple[float, float, str]]:
    """P5 (Vasishtha): the eldest partner's birth muhurta on the wedding day, by number."""
    out = []
    first = _jd(day["windows"][0]["start"])
    sr = sunrise(first, q.lat, q.lon)
    ss = sunset(first, q.lat, q.lon)
    nxt = sunrise(sr + 1.2, q.lat, q.lon)
    for x in couple:
        if not (x.eldest and x.muhurta):
            continue
        by_day, k = x.muhurta
        a, length = (sr, (ss - sr) / 15) if by_day else (ss, (nxt - ss) / 15)
        out.append((a + (k - 1) * length, a + k * length, x.side))
    return out


def _cut(a: float, b: float, bars: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    pieces = [(a, b)]
    for x, y, _ in bars:
        pieces = [
            part
            for lo, hi in pieces
            for part in ((lo, min(hi, x)), (max(lo, y), hi))
            if part[1] - part[0] > 1e-9
        ]
    return pieces


def _judge_day(day: dict, couple: list[Partner], q) -> tuple[dict | None, list[str], dict]:
    """The day with the couple's marks, or None with the rules that removed it and, for
    no_lagna, the minutes each bar took and what removed godhuli (null: there was none)."""
    month = day["lunarMonth"]["amanta"]
    eldest = [x for x in couple if x.eldest]
    day_bars, day_faults, day_supports = [], [], []
    for x in couple:
        if x.month == month:
            if x.eldest:
                day_bars.append("birth_month")
            else:
                day_supports.append(_mark("birth_day_favourable", [x.side]))
    if month == "jyeshtha":
        if len(eldest) == 2:
            day_bars.append("three_jyeshtha")
        elif eldest:
            day_faults.append(_mark("eldest_jyeshtha", [eldest[0].side]))
    if day_bars:
        return None, sorted(set(day_bars)), {}
    cuts = _muhurta_bars(day, couple, q)
    windows = []
    for w in day["windows"]:
        bright = w["paksha"] == "shukla"
        bars_min = dict(w["lagnaBars"])
        lagnas = []
        for lg in w["lagnas"]:
            a, b = _jd(lg["start"]), _jd(lg["end"])
            pieces = _cut(a, b, cuts)
            gone = (b - a - sum(y - x for x, y in pieces)) * 1440
            if gone > 0.01:
                bars_min["birth_muhurta"] = bars_min.get("birth_muhurta", 0) + gone
            for x, y in pieces:
                mid = (x + y) / 2
                bars, faults, supports, lifted = _moment(mid, couple, bright)
                lb, lf, ls, ll = _lagna_marks(SIGN_IDS.index(lg["sign"]), mid, couple)
                bars += lb
                if bars:
                    for m in bars:
                        bars_min[m["rule"]] = bars_min.get(m["rule"], 0) + (y - x) * 1440
                    continue
                marks = {"faults": faults + lf, "supports": supports + ls, "lifted": lifted + ll}
                row = {**lg, "start": iso(x, q.tz), "end": iso(y, q.tz), "personal": marks}
                row["clean"] = lg["clean"] and not marks["faults"]
                lagnas.append(row)
        bars_min = {k: round(v) for k, v in sorted(bars_min.items())}
        windows.append({**w, "lagnas": lagnas, "lagnaBars": bars_min})
    godhuli, godhuli_bars = day["godhuli"], None
    if godhuli:
        a, b = _jd(godhuli["start"]), _jd(godhuli["end"])
        bright = day["windows"][0]["paksha"] == "shukla"
        pieces = _cut(a, b, cuts)
        bars, faults, supports, lifted = _moment((a + b) / 2, couple, bright)
        godhuli_bars = [m["rule"] for m in bars] + ([] if pieces else ["birth_muhurta"])
        if godhuli_bars:
            godhuli = None
        else:
            x, y = max(pieces, key=lambda r: r[1] - r[0])
            godhuli = {
                "start": iso(x, q.tz),
                "end": iso(y, q.tz),
                "personal": {"faults": faults, "supports": supports, "lifted": lifted},
            }
    rows = [lg for w in windows for lg in w["lagnas"]]
    if not rows and not godhuli:
        barred: dict[str, int] = {}
        for w in windows:
            for rule, m in w["lagnaBars"].items():
                barred[rule] = barred.get(rule, 0) + m
        why = {"barred": dict(sorted(barred.items())), "godhuliBars": godhuli_bars}
        return None, ["no_lagna"], why
    status = "clean" if any(lg["clean"] for lg in rows) else "faulted" if rows else "godhuli"
    cautions = [c for c in day["cautions"] if c != "no_clean_lagna"]
    if status != "clean":
        cautions.append("no_clean_lagna")
    bride = next(x for x in couple if x.side == "bride")
    pj = positions(_jd(day["windows"][0]["start"]))["Jupiter"]
    jupiter = JUPITER_BRIDE[(pj.sign - bride.moon_sign) % 12 + 1]
    return (
        {
            **day,
            "windows": windows,
            "cautions": cautions,
            "lagnaStatus": status,
            "godhuli": godhuli,
            "personal": {
                "faults": day_faults,
                "supports": day_supports,
                "lifted": [],
                "jupiterBride": jupiter,
            },
        },
        [],
        {},
    )


def _span_days(req: VivahPersonalRequest) -> list[dict]:
    days = (req.until - req.from_).days + 1
    if days < 1:
        raise invalid("until must not be before from", "until")
    if days > VIVAH_SPAN_DAYS:
        raise ApiError(
            "span_too_long", f"the search span is limited to {VIVAH_SPAN_DAYS} days", 422, "until"
        )
    lo, hi = req.from_.isoformat(), req.until.isoformat()
    out = []
    for year in range(req.from_.year, req.until.year + 1):
        q = EkadashiQuery(year=year, lat=req.lat, lon=req.lon, tz=req.tz)
        out += [d for d in vivah(q)["days"] if lo <= d["date"] <= hi]
    return out


def personal(req: VivahPersonalRequest) -> dict:
    couple = [
        _partner(req.bride, "bride", req.brideEldest),
        _partner(req.groom, "groom", req.groomEldest),
    ]
    q = EkadashiQuery(year=req.from_.year, lat=req.lat, lon=req.lon, tz=req.tz)
    days, removed = [], []
    for d in _span_days(req):
        judged, rules, why = _judge_day(d, couple, q)
        if judged is None:
            removed.append({"date": d["date"], "vara": d["vara"], "rules": rules, **why})
        else:
            days.append(judged)
    return {
        "from": req.from_.isoformat(),
        "until": req.until.isoformat(),
        "partners": {x.side: _facts(x) for x in couple},
        "coupleNotes": ["both_eldest"] if all(x.eldest for x in couple) else [],
        "days": days,
        "removed": removed,
        "engine": provenance("lahiri"),
    }


def _facts(x: Partner) -> dict:
    return {
        "basis": "chart" if x.basis == "chart" else "nakshatra",
        "timeKnown": x.time_known,
        "moonUncertain": x.uncertain,
        "moonSign": SIGN_IDS[x.moon_sign],
        "star": NAKSHATRA_IDS[x.star],
        "pada": x.pada,
        "lagna": SIGN_IDS[x.lagna] if x.lagna is not None else None,
        "birthMonth": x.month,
        "birthTithi": tithi_id(x.tithi) if x.tithi else None,
        "eldest": x.eldest,
        "skipped": x.skipped,
    }
