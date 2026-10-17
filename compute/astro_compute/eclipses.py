"""Solar and lunar eclipses with the place's own circumstances and the vedha (contract 7r;
research's docs/sources/grahana.md, adopted by the lead on 17 Oct 2026).

Only an eclipse fit to be seen counts (DS p. 26; NS pp. 103-106): below the horizon
throughout it is astronomy only, and seen in part it counts for the visible part. A
penumbral eclipse has no shadow bite and is not reckoned (our reading). Solar contacts
are the place's own C1-C4; lunar ones the global umbral U1-U4, kept to the Moon above
the horizon. The vedha is whole praharas from the place's sunrise and sunset: four
before the eclipse's prahara for the Sun, three for the Moon (DS p. 28; NS p. 89).
"""

from __future__ import annotations

import swisseph as swe
from jyotisha.ephemeris import luminaries, moon_rise_set

from .fmt import provenance
from .ids import NAKSHATRA_IDS, SIGN_IDS
from .models import EkadashiQuery
from .observances import SOURCE as NS
from .observances import _sunrises, _sunset
from .timeutil import iso

FL = swe.FLG_SWIEPH
DS = {
    "text": "Dharmasindhu",
    "edition": "Kasinatha Upadhyaya, ed. Krsna Sastri Navare, Nirnaya-sagara Press, Bombay, 1888",
}
VEDHA_PRAHARAS = {"solar": 4, "lunar": 3}
POPULAR_HOURS = {"solar": 12, "lunar": 9}


def _type(flag: int, solar: bool) -> str:
    if flag & swe.ECL_TOTAL:
        return "total"
    if solar and flag & swe.ECL_ANNULAR_TOTAL:
        return "hybrid"
    if solar and flag & swe.ECL_ANNULAR:
        return "annular"
    if not solar and flag & swe.ECL_PENUMBRAL:
        return "penumbral"
    return "partial"


def _global(q: EkadashiQuery) -> list[tuple[str, int, tuple]]:
    """Every eclipse whose greatest phase falls in the year (UTC)."""
    t0, t1 = swe.julday(q.year, 1, 1, 0), swe.julday(q.year + 1, 1, 1, 0)
    out = []
    for body, find in (
        ("solar", lambda t: swe.sol_eclipse_when_glob(t, FL, 0, False)),
        ("lunar", lambda t: swe.lun_eclipse_when(t, FL, 0, False)),
    ):
        t = t0 - 1
        while True:
            flag, tret = find(t)
            if tret[0] >= t1:
                break
            if tret[0] >= t0:
                out.append((body, flag, tret))
            t = tret[0] + 20
    return sorted(out, key=lambda e: e[2][0])


def _praharas(t0: float, t1: float, q) -> list[tuple[float, float, str, int]]:
    """Whole praharas from the place's own sunrises and sunsets covering [t0, t1]: a quarter
    of the day (sunrise to sunset) or of the night (sunset to sunrise)."""
    s = _sunrises(t0 - 2, q.lat, q.lon, int(t1 - t0) + 6)
    out = []
    for a, b in zip(s, s[1:], strict=False):
        ss = _sunset(a, q)
        for part, x, y in (("day", a, ss), ("night", ss, b)):
            step = (y - x) / 4
            out += [(x + i * step, x + (i + 1) * step, part, i + 1) for i in range(4)]
    return out


def _moon_events(a: float, b: float, q) -> list[tuple[float, str]]:
    """The visible moonrises and moonsets (upper limb, as the panchang's) in [a, b)."""
    out, t = [], a
    while t < b:
        rise, set_ = moon_rise_set(t, b, q.lat, q.lon, upper_limb=True)
        found = [(x, k) for x, k in ((rise, "rise"), (set_, "set")) if x is not None]
        if not found:
            break
        out += found
        t = min(x for x, _ in found) + 1e-4
    return sorted(set(out))


def _up(t: float, events: list[tuple[float, str]]) -> bool:
    before = [k for x, k in events if x <= t]
    if before:
        return before[-1] == "rise"
    after = [k for x, k in events if x > t]
    return bool(after) and after[0] == "set"


def _when(jd: float | None, q) -> str | None:
    return iso(jd, q.tz) if jd else None


def _vedha(body: str, kind: str, first: float, last: float, rose: float | None,
           sets_eclipsed: float | None, q) -> tuple[dict, dict | None]:  # fmt: skip
    """The vedha from the first contact seen at the place to its end, with DS's variant."""
    span = _praharas(first - 2, last + 1, q)
    i = next(k for k, (a, b, _, _) in enumerate(span) if a <= first < b)
    a, b, part, num = span[i]
    variant = None
    if body == "lunar" and rose is not None:
        # DS p. 28; NS p. 89 (Vrddha-Vasistha): the Moon rising eclipsed, no food through
        # the day before it rises.
        start, rule = _sunrises(rose, q.lat, q.lon, 1)[0], "moon_rises_eclipsed_from_sunrise"
    else:
        start = span[i - VEDHA_PRAHARAS[body]][0]
        rule = "four_praharas_solar" if body == "solar" else "three_praharas_lunar"
        if body == "lunar" and kind == "total":  # DS p. 28, "kecit"
            variant = {"start": iso(span[i - 4][0], q.tz), "rule": "four_praharas_total_lunar"}
    if sets_eclipsed is None:
        end, end_rule = last, "last_contact"
    elif body == "solar":
        end, end_rule = _sunrises(sets_eclipsed + 0.5, q.lat, q.lon, 1)[0], "next_clear_sunrise"
        if end <= sets_eclipsed:
            end = _sunrises(sets_eclipsed, q.lat, q.lon, 2)[1]
    else:
        rises = [x for x, k in _moon_events(last, last + 2, q) if k == "rise"]
        end, end_rule = rises[0], "next_clear_moonrise"
    return {
        "start": iso(start, q.tz),
        "end": iso(end, q.tz),
        "rule": rule,
        "endRule": end_rule,
        "prahara": {"start": iso(a, q.tz), "end": iso(b, q.tz), "part": part, "num": num},
    }, variant


def _solar(flag: int, g: tuple, q) -> dict:
    jmax = g[0]
    lflag, lt, attr = swe.sol_eclipse_when_loc(jmax - 1, (q.lon, q.lat, 0), FL, False)
    here = abs(lt[0] - jmax) < 0.5 and lflag & swe.ECL_VISIBLE
    local: dict = {"visible": bool(here), "type": None, "contacts": None, "magnitude": None,
                   "obscuration": None, "visibleFrom": None, "visibleUntil": None,
                   "maximumVisible": False, "risesEclipsed": False, "setsEclipsed": False,
                   "rise": None, "set": None}  # fmt: skip
    if not here:
        return {"local": local, "first": None}
    c1, c4 = lt[1], lt[4]
    sr = _sunrises(c1, q.lat, q.lon, 2)
    rise = next((x for x in sr if c1 < x < c4), None)
    set_ = next((x for x in (_sunset(y, q) for y in sr) if c1 < x < c4), None)
    first, last = (rise or c1), (set_ or c4)
    local.update(
        type=_type(lflag, True),
        contacts={
            "c1": _when(c1, q),
            "c2": _when(lt[2], q),
            "maximum": _when(lt[0], q),
            "c3": _when(lt[3], q),
            "c4": _when(c4, q),
        },  # fmt: skip
        magnitude=round(attr[0], 3),
        obscuration=round(attr[2], 3),
        visibleFrom=iso(first, q.tz),
        visibleUntil=iso(last, q.tz),
        maximumVisible=bool(lflag & swe.ECL_MAX_VISIBLE),
        risesEclipsed=rise is not None,
        setsEclipsed=set_ is not None,
        rise=_when(rise, q),
        set=_when(set_, q),
    )
    return {"local": local, "first": first, "last": last, "rose": rise, "set": set_}


def _lunar(flag: int, g: tuple, q) -> dict:
    p1, p4, u1, u4 = g[6], g[7], g[2], g[3]
    _, attr = swe.lun_eclipse_how(g[0], (q.lon, q.lat, 0), FL)
    events = _moon_events(p1 - 1, p4 + 1, q)
    inside = [(x, k) for x, k in events if p1 < x < p4]
    seen = _up(p1, events) or bool(inside)
    umbral = bool(u1) and (_up(u1, events) or any(u1 < x < u4 for x, _ in events))
    rise = next((x for x, k in events if k == "rise" and u1 and u1 < x < u4), None)
    set_ = next((x for x, k in events if k == "set" and u1 and u1 < x < u4), None)
    local = {
        "visible": seen,
        "type": _type(flag, False) if seen else None,
        "magnitude": round(attr[0], 3),
        "penumbralMagnitude": round(attr[1], 3),
        "visibleFrom": None,
        "visibleUntil": None,
        "maximumVisible": _up(g[0], events),
        "risesEclipsed": rise is not None,
        "setsEclipsed": set_ is not None,
        "rise": _when(rise, q),
        "set": _when(set_, q),
    }
    if not umbral:  # no shadow bite above the horizon: nothing is reckoned here
        a = next((x for x, k in inside if k == "rise"), p1) if seen else None
        b = next((x for x, k in inside if k == "set"), p4) if seen else None
        local.update(visibleFrom=_when(a, q), visibleUntil=_when(b, q))
        return {"local": local, "first": None, "seen": seen}
    first, last = (rise or u1), (set_ or u4)
    local.update(visibleFrom=iso(first, q.tz), visibleUntil=iso(last, q.tz))
    return {"local": local, "first": first, "last": last, "rose": rise, "set": set_}


def eclipses(q: EkadashiQuery) -> dict:
    rows = []
    for body, flag, g in _global(q):
        kind = _type(flag, body == "solar")
        got = _solar(flag, g, q) if body == "solar" else _lunar(flag, g, q)
        row = {
            "id": f"{iso(g[0], 'UTC')[:10]}-{body}",
            "body": body,
            "type": kind,
            "greatest": iso(g[0], q.tz),
        }
        if body == "lunar":
            row["contacts"] = {k: _when(g[i], q) for k, i in
                               (("p1", 6), ("u1", 2), ("u2", 4), ("greatest", 0), ("u3", 5),
                                ("u4", 3), ("p4", 7))}  # fmt: skip
        # The eclipsed body at greatest eclipse: DS p. 28 reckons the signs from it.
        pos = luminaries(g[0], q.ayanamsa)[0 if body == "solar" else 1]
        row["atMaximum"] = {
            "body": "sun" if body == "solar" else "moon",
            "sign": SIGN_IDS[pos.sign],
            "nakshatra": NAKSHATRA_IDS[pos.nakshatra],
        }
        row["local"] = got["local"]
        if kind == "penumbral":
            reason = "penumbral_no_bite"
        elif got["first"] is None:
            reason = "umbral_not_visible" if got.get("seen") else "not_visible"
        else:
            reason = None
        vedha = variant = None
        if reason is None:
            vedha, variant = _vedha(
                body, kind, got["first"], got["last"], got["rose"], got["set"], q
            )
            # Practice, not the texts: 12 or 9 hours before the first contact seen here.
            hours = POPULAR_HOURS[body]
            vedha |= {"popularStart": iso(got["first"] - hours / 24, q.tz), "popularHours": hours}
        rows.append(
            {
                **row,
                "reckoned": reason is None,
                "notReckoned": reason,
                "vedha": vedha,
                "vedhaVariant": variant,
            }
        )
    return {
        "year": q.year,
        "eclipses": rows,
        "source": {**DS, "verse": "grahana-nirnaya", "page": "26-29"},
        "alsoSource": {**NS, "verse": "grahana-nirnaya", "page": "89-107"},
        "engine": provenance(q.ayanamsa),
    }
