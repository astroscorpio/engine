"""GET /v1/muhurat/annaprashan and /v1/muhurat/akshararambh: the year's days for a child's
first rice and first letters at a place (docs/sources/samskaras.md, as the lead approved
it on 15 Oct 2026).

Annaprashana (MC 5.17-18; DS pp. 4-5, 135): the bright fortnight; tithi 2, 3, 5, 7, 10 or
13; Monday, Wednesday, Thursday or Friday; DS's sixteen stars; no adhika or kshaya month;
Jupiter and Venus clear. Its windows are the forenoon with the lagna not Aries, Scorpio
or Pisces, the 10th empty, no malefic in the 1st, 4th or 7th and the Moon not in the 6th
or 8th, less the whole spans of Vishti and seven bad yogas (DS p. 135; the whole Vishti is
our reading) and the barred stretches the other date lists remove.

Akshararambha (MC 5.37; DS p. 138), what both texts allow: the Sun's northern course but
not in Aquarius, and not from the Devashayani Ekadashi to the Karka sankranti; tithi 2, 3,
5, 10, 11 or 12, the dark fortnight's last three days excepted; Monday, Wednesday,
Thursday or Friday; MC's ten stars. Its windows have Taurus, Gemini, Virgo, Sagittarius
or Pisces rising with the 8th empty. What one text alone allows goes to excluded[]
(ds_only, mc_only).
"""

from __future__ import annotations

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, positions

from .festivals import festival
from .fmt import provenance
from .griha_pravesh import UTTARAYANA, _public, _windows
from .ids import MASA_IDS, NAKSHATRA_IDS, SIGN_IDS, tithi_id
from .models import EkadashiQuery
from .observances import _vara
from .timeutil import aware, iso
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

MALEFICS = ("Sun", "Mars", "Saturn", "Rahu", "Ketu")
BENEFIC_VARAS = {"monday", "wednesday", "thursday", "friday"}

# DS p. 135 (Vasishtha in MC's commentary, p. 179): Ashvini, Rohini, Mrgashira, Punarvasu,
# Pushya, the three Uttaras, Hasta, Citra, Svati, Anuradha, Shravana, Dhanishtha,
# Shatabhisha and Revati (0-based indexes).
ANNA_STARS = {0, 3, 4, 6, 7, 11, 12, 13, 14, 16, 20, 21, 22, 23, 25, 26}
ANNA_TITHIS = {2, 3, 5, 7, 10, 13}  # bright fortnight only
ANNA_BAD_LAGNAS = {0, 7, 11}  # Aries, Scorpio, Pisces (MC 5.17)
# DS p. 135, MC's commentary p. 179: barred for their own spans.
ANNA_YOGAS = {"Vaidhriti", "Vyatipata", "Ganda", "Atiganda", "Vajra", "Shula", "Parigha"}
ANNA_SOURCE = {
    "text": "Muhurta-cintamani",
    "verse": "5.17-18",
    "edition": "with Govinda's Piyushadhara, 1945",
    "page": "178-181",
}

# MC 5.37: Hasta, Ashvini, Pushya, Shravana, Svati, Revati, Punarvasu, Ardra, Citra and
# Anuradha. DS p. 138 adds Mrgashira, Dhanishtha and Shatabhisha.
AKSHARA_STARS = {12, 0, 7, 21, 14, 26, 6, 5, 13, 16}
DS_STARS = {4, 22, 23}
AKSHARA_TITHIS = {2, 3, 5, 10, 11, 12}  # both texts; DS adds 13, MC 6
AKSHARA_LAGNAS = {1, 2, 5, 8, 11}  # Taurus, Gemini, Virgo, Sagittarius, Pisces
AQUARIUS, GEMINI = 10, 2
AKSHARA_SOURCE = {
    "text": "Muhurta-cintamani",
    "verse": "5.37",
    "edition": "with Govinda's Piyushadhara, 1945",
    "page": "197-198",
}
DS_ONLY = "allowed by DS only"
MC_ONLY = "allowed by MC only"


def _merge(into: dict, extra: dict) -> None:
    """Add {rule: (reason, facts)}, joining the reasons and facts of a repeated rule."""
    for k, (text, facts) in extra.items():
        if k in into:
            old, f0 = into[k]
            into[k] = (old if text in old else f"{old}; {text}", {**f0, **facts})
        else:
            into[k] = (text, facts)


def _planet_relax(y: _Year, i: int, q) -> tuple[str | None, dict]:
    """Jupiter's and Venus's states on day i: (the strict rule that bars it, or None,
    and the relaxable rules), as in the other lists."""
    sr, ss, _ = y.days[i]
    relax: dict = {}
    for planet, state in y.states.items():
        if i not in state:
            continue
        kind, detail = state[i]
        if i in y.relaxed[planet]:
            return f"{planet.lower()}_{kind}", relax
        if kind == "set":
            relax["venus_set"] = (
                "Venus is within the Surya-siddhanta's 10 time-degrees of the Sun (9.6-7)",
                _venus_facts(sr, ss, q),
            )
        else:
            relax["infancy_old"] = (
                f"{planet} is in its {'infancy' if kind == 'infant' else 'old age'}, "
                f"{detail} (Muhurta Chintamani 5.27)",
                _state_facts(planet, kind, detail),
            )
    return None, relax


def _house_windows(a: float, b: float, q, ok) -> list[tuple[float, float, int]]:
    """Stretches of [a, b] whose lagna and the houses at its middle pass ok(lagna, house)."""
    ay = q.ayanamsa
    out = []
    for x, y_, lagna in _spans(
        lambda t: int(ascendant(t, q.lat, q.lon, ay)[0].longitude // 30), a, b, 1 / 96
    ):
        p = positions((x + y_) / 2, ay)
        house = {g: (p[g].sign - lagna) % 12 + 1 for g in p}
        if ok(lagna, house):
            out.append((x, y_, lagna))
    return out


def _whole_spans(y: _Year, ay: str) -> list[tuple[float, float]]:
    """The whole spans of Vishti and of annaprashana's seven yogas (DS p. 135)."""
    y0, y1 = y.tithis[0][0], y.tithis[-1][1]
    bars = [(a, b) for name, (a, b) in Mu._yoga_spans(y0, y1, ay) if name in ANNA_YOGAS]
    bars += [
        (a, b)
        for a, b, vishti in _spans(lambda t: Mu.karana_at(t, ay) == "Vishti", y0, y1, 0.05)
        if vishti
    ]
    return bars


def _day(y: _Year, date, vara: str, rows: list[tuple], zone, extra: dict | None = None) -> dict:
    windows = _windows(rows, zone)
    nums = {w["_n"] for w in windows}
    masa = Mu.MASA.index(windows[0]["_m"])
    adhika = y.tithi((rows[0][0] + rows[0][1]) / 2)[1][1]
    return {
        "date": date.isoformat(),
        "vara": vara,
        "lunarMonth": {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if min(nums) > 15 else MASA_IDS[masa],
            "adhika": adhika,
        },
        "windows": _public(windows),
        **(extra or {}),
    }


def _settle(y: _Year, date, vara, rows, day_relax, zone, out_days, excluded, explain, extra=None):
    """The shared tail of both lists: day yogas, then listed, excluded or dropped."""
    rows, inside, yoga = _day_yogas(rows, vara, y.ay)
    if rows or not inside:
        yoga = {}
    else:
        rows = inside
    strict = [r for r in rows if not r[5]] if not (day_relax or yoga) else []
    if strict:
        if explain is not None:
            explain[date.isoformat()] = "listed"
        out_days.append(_day(y, date, vara, strict, zone, extra))
    elif rows:
        rules = dict(day_relax)
        _merge(rules, yoga)
        for r in rows:
            _merge(rules, r[5])
        if explain is not None:
            explain[date.isoformat()] = "excluded:" + "+".join(sorted(rules))
        reasons, details = _details(rules)
        excluded.append(
            {
                "date": date.isoformat(),
                "vara": vara,
                "windows": _public(_windows(rows, zone)),
                "rules": sorted(rules),
                "reasons": reasons,
                "details": details,
            }
        )
    elif explain is not None:
        explain[date.isoformat()] = "window"


def _state_blocks(y: _Year, q) -> list[dict]:
    """Jupiter's and Venus's states, merged into runs."""
    rows = []
    for planet, state in y.states.items():
        run = None
        for i in sorted(state):
            kind, detail = state[i]
            if run and run[0] == kind and run[2] == i - 1:
                run[2] = i
                continue
            if run:
                rows.append((planet, *run))
            run = [kind, i, i, detail]
        if run:
            rows.append((planet, *run))
    return [
        {
            "rule": f"{planet.lower()}_{kind}",
            "start": iso(y.days[i][0], q.tz),
            "end": iso(y.days[j][2], q.tz),
            "detail": detail,
        }
        for planet, kind, i, j, detail in rows
    ]


def _in_year(rows: list[dict], q) -> list[dict]:
    y0, y1 = f"{q.year}-01-01", f"{q.year + 1}-01-01"
    return sorted((r for r in rows if r["end"] >= y0 and r["start"] < y1), key=lambda r: r["start"])


def annaprashan(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the rule that rejected it."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    whole = _whole_spans(y, ay)
    out_days, excluded = [], []
    for i, (sr, ss, nr) in enumerate(y.days):
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        why, day_relax = _planet_relax(y, i, q)
        if vara == "sunday":
            day_relax["sunday"] = (
                "Sunday, which some allow (Dharmasindhu p. 135)",
                {"weekday": vara},
            )
        elif vara not in BENEFIC_VARAS:
            why = why or "weekday"
        if why:
            if explain is not None:
                explain[date.isoformat()] = why
            continue
        midday = (sr + ss) / 2
        cuts = sorted({c for c in y.cuts(sr, nr) if c < midday} | {midday})
        reasons: list[str] = []
        pieces = []
        for a, b in zip(cuts, cuts[1:], strict=False):
            mid = (a + b) / 2
            num, (name, adhika, kshaya, _) = y.tithi(mid)
            moon = luminaries(mid, ay)[1]
            if adhika or kshaya:
                reasons.append("month")
            elif num > 15 or num not in ANNA_TITHIS:
                reasons.append("tithi")
            elif moon.nakshatra not in ANNA_STARS:
                reasons.append("nakshatra")
            else:
                pieces.append((a, b, num, moon.nakshatra, name, {}))
        if not pieces:
            if explain is not None:
                order = ("weekday", "month", "tithi", "nakshatra")
                explain[date.isoformat()] = next((r for r in order if r in reasons), "none")
            continue
        bars = [(x, y_) for x, y_, _ in y.bars] + _lagna_gandanta(sr, nr, q) + whole
        rows = []
        for a, b in _subtract([(a, b) for a, b, *_ in pieces], bars):
            num, nak, name, relax = next(
                (n, k, m, r) for x, y_, n, k, m, r in pieces if x <= a < y_
            )

            def ok(lagna, house) -> bool:
                return (
                    lagna not in ANNA_BAD_LAGNAS
                    and 10 not in house.values()
                    and all(house[g] not in (1, 4, 7) for g in MALEFICS)
                    and house["Moon"] not in (6, 8)
                )

            rows += [
                (x, y_, num, nak, name, relax, lagna)
                for x, y_, lagna in _house_windows(a, b, q, ok)
            ]
        _settle(y, date, vara, rows, day_relax, zone, out_days, excluded, explain)
    blocks = _state_blocks(y, q)
    for a, b, _ in y.tithis:
        name, adhika, kshaya, _start = y.tithi_month[a]
        if adhika or kshaya:
            run = {"rule": "adhika_month", "start": iso(a, zone), "end": iso(b, zone),
                   "detail": MASA_IDS[Mu.MASA.index(name)]}  # fmt: skip
            if (
                blocks
                and blocks[-1]["rule"] == "adhika_month"
                and blocks[-1]["end"] == run["start"]
            ):
                blocks[-1]["end"] = run["end"]
            else:
                blocks.append(run)
    return {
        "year": q.year,
        "days": out_days,
        "excluded": excluded,
        "blocks": _in_year(blocks, q),
        "source": ANNA_SOURCE,
        "alsoSource": {**DS, "page": "4-5, 135"},
        "engine": provenance(ay),
    }


def _devashayani(y: _Year) -> list[float]:
    """The starts of the pure Ashadha shukla Ekadashi in the year's tithi list."""
    return [
        a
        for a, _, n in y.tithis
        if n == 11 and y.tithi_month[a][0] == "Ashadha" and not y.tithi_month[a][1]
    ]


def akshararambh(q: EkadashiQuery, explain: dict | None = None) -> dict:
    """explain, if given, is filled with date -> the rule that rejected it."""
    y = _Year(q)
    ay, zone = y.ay, y.zone
    sleeps = _devashayani(y)
    out_days, excluded = [], []
    vasanta = {o["date"] for o in festival("vasanta-panchami", q)["occurrences"]}
    for sr, _ss, nr in y.days:
        date = aware(sr, zone).date()
        if date.year != q.year:
            continue
        vara = _vara(sr, q)
        day_relax: dict = {}
        if vara == "sunday":
            day_relax["ds_only"] = (f"Sunday, {DS_ONLY} (Dharmasindhu p. 138)", {"weekday": vara})
        elif vara not in BENEFIC_VARAS:
            if explain is not None:
                explain[date.isoformat()] = "weekday"
            continue
        reasons: list[str] = []
        pieces = []
        cuts = y.cuts(sr, nr)
        for a, b in zip(cuts, cuts[1:], strict=False):
            mid = (a + b) / 2
            num, (name, _adhika, _kshaya, _) = y.tithi(mid)
            sun, moon = luminaries(mid, ay)
            base = (num - 1) % 15 + 1
            relax: dict = {}
            if sun.sign not in UTTARAYANA or sun.sign == AQUARIUS:
                reasons.append("season")
                continue
            if sun.sign == GEMINI and any(s <= mid for s in sleeps):
                reasons.append("hari_sleeps")
                continue
            if num in (28, 29, 30):
                reasons.append("tithi")  # the dark fortnight's last three days (DS)
                continue
            if base == 13 and num <= 15:
                relax["ds_only"] = (
                    f"Trayodashi, {DS_ONLY} (Dharmasindhu p. 138)",
                    {"tithi": tithi_id(num)},
                )
            elif base == 6:
                relax["mc_only"] = (
                    f"Shashthi, {MC_ONLY} (Muhurta Chintamani 5.37)",
                    {"tithi": tithi_id(num)},
                )
            elif base not in AKSHARA_TITHIS:
                reasons.append("tithi")
                continue
            if moon.nakshatra in DS_STARS:
                star = NAKSHATRA_IDS[moon.nakshatra]
                _merge(relax, {"ds_only": (f"{Mu.NAKSHATRAS[moon.nakshatra]}, {DS_ONLY} "
                                           "(Dharmasindhu p. 138)", {"star": star})})  # fmt: skip
            elif moon.nakshatra not in AKSHARA_STARS:
                reasons.append("nakshatra")
                continue
            # A piece one text allows and the other text's own extra also touches is
            # allowed by neither (MC's 6th is not in DS; DS's stars and Sunday not in MC).
            if "mc_only" in relax and ("ds_only" in relax or "ds_only" in day_relax):
                reasons.append("tithi")
                continue
            pieces.append((a, b, num, moon.nakshatra, name, relax))
        if not pieces:
            if explain is not None:
                order = ("weekday", "season", "hari_sleeps", "tithi", "nakshatra")
                explain[date.isoformat()] = next((r for r in order if r in reasons), "none")
            continue
        bars = [(x, y_) for x, y_, _ in y.bars] + _lagna_gandanta(sr, nr, q)
        rows = []
        for a, b in _subtract([(a, b) for a, b, *_ in pieces], bars):
            num, nak, name, relax = next(
                (n, k, m, r) for x, y_, n, k, m, r in pieces if x <= a < y_
            )

            def ok(lagna, house) -> bool:
                return lagna in AKSHARA_LAGNAS and 8 not in house.values()

            rows += [
                (x, y_, num, nak, name, relax, lagna)
                for x, y_, lagna in _house_windows(a, b, q, ok)
            ]
        extra = {"vasantaPanchami": True} if date.isoformat() in vasanta else None
        _settle(y, date, vara, rows, day_relax, zone, out_days, excluded, explain, extra)
    vijaya = festival("vijayadashami", q)["occurrences"]
    blocks = []
    for a, b, sign in y.sun_sign:
        rule = (
            "dakshinayana" if sign not in UTTARAYANA else "sun_sign" if sign == AQUARIUS else None
        )
        if rule is None:
            continue
        detail = SIGN_IDS[sign] if rule == "sun_sign" else None
        if blocks and blocks[-1]["rule"] == rule and blocks[-1]["end"] == iso(a, zone):
            blocks[-1]["end"] = iso(b, zone)
        else:
            blocks.append(
                {"rule": rule, "start": iso(a, zone), "end": iso(b, zone), "detail": detail}
            )
    for s in sleeps:
        karka = next((a for a, _, sign in y.sun_sign if a > s and sign == 3), None)
        if karka is not None and karka > s:
            blocks.append({"rule": "hari_sleeps", "start": iso(s, zone), "end": iso(karka, zone),
                           "detail": None})  # fmt: skip
    return {
        "year": q.year,
        "days": out_days,
        "excluded": excluded,
        "vijayadashami": {
            "date": vijaya[0]["date"],
            "note": "Kerala practice (Vidyarambham), not a muhurta: MC 5.37 and Dharmasindhu "
            "p. 138 ask for the Sun's northern course",
        }
        if vijaya
        else None,
        "blocks": _in_year(blocks, q),
        "source": AKSHARA_SOURCE,
        "alsoSource": {**DS, "page": "4, 138"},
        "engine": provenance(ay),
    }
