"""GET /v1/festivals/<id>: the festival days of a year at a place.

Rules from docs/sources/festivals.md, all from Nirnaya-sindhu (1898 printing;
"NS"). Windows:
  pratah     the 1st fifth of the daytime (NS p. 28 divides the day in five;
             "morning" read as its first part, our reading);
  madhyahna  the 3rd fifth of the daytime (NS p. 28);
  aparahna   the last third of the daytime (NS p. 81 defines it so for
             shraddha; used for the festivals too, our reading);
  pradosha   three muhurtas after sunset, a muhurta a fifteenth of the night;
  nishitha   two ghatikas around the middle of the night (Madhava, NS p. 335),
             taken as a fifteenth of the night centred on its midpoint (our
             reading of the ghatika's length).
Bhadra is the Vishti karana: in a Purnima, its first half.
NS names a new moon (and the dark fortnight before it) by the amanta month it
ends, so month tests below use the amanta month.
"""

from __future__ import annotations

from jyotisha import muhurta as Mu

from .fmt import provenance
from .models import EkadashiQuery
from .observances import SOURCE, _collect, _lunar, _overlap, _rise_set, _sunrises, _sunset, _vara
from .timeutil import aware, iso

DANDA = 24 / 1440  # one ghatika (danda), in days
ROHINI, SHRAVANA = 3, 21  # nakshatra indexes, Ashvini = 0


def _night(sunrise_jd: float, q) -> tuple[float, float]:
    ss = _sunset(sunrise_jd, q)
    return ss, _rise_set(ss + 0.01, q.lat, q.lon, True)


def _windows(sunrise_jd: float, q) -> dict[str, tuple[float, float]]:
    ss, nr = _night(sunrise_jd, q)
    night, day = nr - ss, ss - sunrise_jd
    mid = ss + night / 2
    return {
        "pratah": (sunrise_jd, sunrise_jd + day / 5),
        "madhyahna": (sunrise_jd + 2 * day / 5, sunrise_jd + 3 * day / 5),
        "aparahna": (sunrise_jd + 2 * day / 3, ss),
        "pradosha": (ss, ss + 3 * night / 15),
        "nishitha": (mid - night / 30, mid + night / 30),
        "night": (ss, nr),
    }


def _share(start: float, end: float, w: tuple[float, float]) -> float:
    return _overlap(start, end, w[0], w[1]) / (w[1] - w[0])


def _clip(start: float, end: float, w: tuple[float, float]) -> tuple[float, float] | None:
    """The part of window w inside [start, end]."""
    a, b = max(start, w[0]), min(end, w[1])
    return (a, b) if b > a else None


def _span(w: tuple[float, float] | None, q) -> dict | None:
    return {"start": iso(w[0], q.tz), "end": iso(w[1], q.tz)} if w else None


def _date(jd: float, q) -> str:
    return aware(jd, q.tz).date().isoformat()


def _days(start: float, end: float, q, names: tuple[str, ...], n: int = 2):
    """The day the tithi begins and the next n - 1: dates, windows and coverage."""
    s = _sunrises(start, q.lat, q.lon, n + 1)
    out = []
    for i in range(n):
        w = _windows(s[i], q)
        out.append(
            {
                "date": _date(s[i], q),
                "vara": _vara(s[i], q),
                **{
                    nm: {**_span(w[nm], q), "covered": round(_share(start, end, w[nm]), 3)}
                    for nm in names
                },
                "_w": w,
            }
        )
    return s, out


def _strip(days: list[dict]) -> list[dict]:
    return [{k: v for k, v in d.items() if k != "_w"} for d in days]


def _base(start: float, end: float, num: int, q) -> dict:
    # The tithi's midpoint names its month; the next sunrise can fall in the next
    # month when an Amavasya touches no sunrise.
    return {
        "lunarMonth": _lunar((start + end) / 2, num, q),
        "tithi": {"start": iso(start, q.tz), "end": iso(end, q.tz)},
    }


def _in_month(base: dict, amanta: str) -> bool:
    return base["lunarMonth"]["amanta"] == amanta and not base["lunarMonth"]["adhika"]


def _spans(fn, value, t0: float, t1: float, step: float) -> list[tuple[float, float]]:
    """The stretches of [t0, t1] where fn(t) == value."""
    cuts = [t0, *(t for t, _ in Mu._scan(fn, t0, t1, step)), t1]
    return [(a, b) for a, b in zip(cuts, cuts[1:], strict=False) if fn((a + b) / 2) == value]


def _bhadra(start: float, end: float, q) -> tuple[float, float] | None:
    found = _spans(lambda t: Mu.karana_at(t, q.ayanamsa), "Vishti", start, end, 0.05)
    return found[0] if found else None


# --- Dipavali (NS pp. 299-300) --------------------------------------------------------


def _dipavali(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    base = _base(start, end, 30, q)
    if not _in_month(base, "ashwin"):
        return None
    _, days = _days(start, end, q, ("pradosha", "nishitha"))
    # "If the Amavasya touches even one danda of the next night, leave the first
    # day" (Tithi-tattva, NS p. 300); otherwise the Amavasya current at pradosha.
    next_night = days[1]["_w"]["night"][0]
    touches_next = end - next_night >= DANDA
    in_pradosha = [d["pradosha"]["covered"] > 0 for d in days]
    if touches_next:
        chosen, rule = 1, "danda_next_night_later"
    elif in_pradosha[0]:
        chosen, rule = 0, "pradosha"
    else:
        chosen, rule = 1, "neither_later"
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "lakshmiPuja": _span(_clip(start, end, days[chosen]["_w"]["pradosha"]), q),
        "nishithaCovered": days[chosen]["nishitha"]["covered"] > 0,
    }


# --- Shivaratri (NS pp. 334-337, 340) ----------------------------------------------


def _shivaratri_day(days: list[dict]) -> tuple[int, str, int | None]:
    """NS pp. 335-337. Midnight wholly on both days: pradosha decides (only the
    later day has it: the later day, Madhava, endorsed by NS; Hemadri the first).
    Otherwise midnight decides: the day with (more of) it, so the first day when
    it has all of midnight and the later day only part (Isana-samhita). With no
    midnight on either day, the day with pradosha (the later day when it alone
    has one of the two, p. 337). Returns (day, rule, Hemadri's variant or None)."""
    n = [d["nishitha"]["covered"] for d in days]
    p = [d["pradosha"]["covered"] > 0 for d in days]
    if n[0] >= 1 and n[1] >= 1:
        if p[1] and not p[0]:
            return 1, "midnight_both_pradosha_later", 0
        if p[0] and not p[1]:
            return 0, "midnight_both_pradosha", None
        return 0, "midnight_both_first", None
    if n[0] > 0 or n[1] > 0:
        return (0 if n[0] >= n[1] else 1), "by_midnight", None
    if p[0] != p[1]:
        return p.index(True), "by_pradosha", None
    return 1, "neither_later", None


def _shivaratri(
    start: float, end: float, _next: float, q: EkadashiQuery, maha: bool
) -> dict | None:
    base = _base(start, end, 29, q)
    if maha and not _in_month(base, "magha"):
        return None
    _, days = _days(start, end, q, ("pradosha", "nishitha"))
    chosen, rule, variant = _shivaratri_day(days)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[variant]["date"] if variant is not None else None,
        "nishitha": days[chosen]["nishitha"],
    }


# --- Ganesha Chaturthi (NS pp. 47, 198) -------------------------------------------


def _ganesha(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    base = _base(start, end, 4, q)
    if not _in_month(base, "bhadrapada"):
        return None
    _, days = _days(start, end, q, ("madhyahna",))
    # "madhyahna-vyapini cet syat paratah, pare 'hani": the next day if the
    # Chaturthi reaches its midday; otherwise the earlier day, joined with Trtiya.
    if days[1]["madhyahna"]["covered"] > 0:
        chosen, rule = 1, "next_day_midday"
    else:
        chosen, rule = 0, "trtiya_joined_earlier"
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "pujaWindow": {k: days[chosen]["madhyahna"][k] for k in ("start", "end")},
        "moonAvoid": {"start": iso(start, q.tz), "end": iso(end, q.tz)},
    }


# --- Raksha Bandhan (NS p. 180) ----------------------------------------------------


def _raksha(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """In the earlier day's afternoon, even when the Upakarma falls on the next
    day; never in Bhadra (if Bhadra is there, at its end, even at night:
    Nirnayamrta); never on the Purnima joined with Pratipada."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "shravana"):
        return None
    s, days = _days(start, end, q, ("aparahna",))
    bhadra = _bhadra(start, end, q)
    free = bhadra[1] if bhadra else start  # the Purnima after Bhadra
    a0, a1 = days[0]["_w"]["aparahna"], days[1]["_w"]["aparahna"]
    if start < a0[1]:  # it reaches the earlier day's afternoon
        tie = _clip(free, end, a0)
        if tie:
            chosen, rule = 0, "aparahna"
        elif free < s[1]:
            chosen, rule, tie = 0, "after_bhadra_night", (free, min(end, s[1]))
        else:
            chosen, rule, tie = 1, "bhadra_past_sunrise", _clip(free, end, a1) or (free, end)
    else:  # it begins after the earlier day's sunset
        tie = _clip(free, end, a1)
        chosen, rule = 1, ("later_aparahna" if tie else "no_aparahna")
        tie = tie or (free, end)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "tieWindow": _span(tie, q),
        "bhadra": _span(bhadra, q),
    }


# --- Janmashtami and Jayanti (NS pp. 183-191) ---------------------------------------


def _by_midnight(n: list[float]) -> tuple[int, str]:
    """NS pp. 189-190, the Ashtami alone: the day whose midnight it holds; on both
    days or neither, the second; partly on both, unequally, the day with more."""
    if n[0] > 0 and n[1] == 0:
        return 0, "first_only"
    if n[0] == 0 and n[1] > 0:
        return 1, "second_only"
    if n[0] == 0:
        return 1, "neither_later"
    if abs(n[0] - n[1]) < 1e-9:
        return 1, "both_later"
    return (0 if n[0] > n[1] else 1), "more"


def _jayanti(
    j: list[bool], n: list[float], r: list[bool], joined: bool
) -> tuple[int, str, int | None] | None:
    """NS pp. 190-191, the Ashtami joined with Rohini at midnight (j). The Ashtami
    at the first midnight (n) and Rohini at the second (r), joined in between:
    the second (Madhava), Hemadri the first. Returns (day, rule, Hemadri's day)."""
    if j[0] and not j[1]:
        return 0, "first", None
    if j[1] and not j[0]:
        return 1, "second", None
    if j[0] and j[1]:
        return 1, "both_later", None
    if n[0] > 0 and n[1] == 0 and r[1] and not r[0] and joined:
        return 1, "split_later", 0
    return None


def _janmashtami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    base = _base(start, end, 23, q)
    if not _in_month(base, "shravana"):
        return None
    s, days = _days(start, end, q, ("nishitha",))
    nak = lambda t: Mu.nakshatra_at(t, q.ayanamsa)  # noqa: E731
    rohini = _spans(nak, ROHINI, s[0] - 1, s[2] + 1, 0.1)
    nish = [d["_w"]["nishitha"] for d in days]
    n = [_share(start, end, w) for w in nish]
    r = [any(_overlap(a, b, *w) > 0 for a, b in rohini) for w in nish]
    both = [(max(a, start), min(b, end)) for a, b in rohini if min(b, end) > max(a, start)]
    j = [any(_overlap(a, b, *w) > 0 for a, b in both) for w in nish]
    chosen, rule = _by_midnight(n)
    jay = _jayanti(j, n, r, bool(both))
    # The sunrise view NS sets aside (p. 191): the Ashtami at the later sunrise.
    at_sunrise = [i for i in (1, 2) if start <= s[i] < end]
    out = _strip(days)
    for d, flag in zip(out, r, strict=True):
        d["rohiniAtMidnight"] = flag
    near = next(((a, b) for a, b in rohini if _overlap(a, b, s[0], s[2]) > 0), None)
    return {
        **base,
        "days": out,
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "nishitha": days[chosen]["nishitha"],
        "rohini": _span(near, q),
        "jayanti": {
            "date": days[jay[0]]["date"],
            "vara": days[jay[0]]["vara"],
            "rule": jay[1],
            "variantDate": days[jay[2]]["date"] if jay[2] is not None else None,
        }
        if jay
        else None,
        "udayaDate": _date(s[at_sunrise[-1]], q) if at_sunrise else days[0]["date"],
    }


# --- Sharad Navaratri and Vijayadashami (NS pp. 240-241, 283-284) ----------------------


def _navaratri(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """Kalasha-sthapana on the Pratipada current at sunrise, "even for two
    muhurtas"; never the one joined with Amavasya (the day it begins on); in
    the morning (Devi Purana via Tithi-tattva)."""
    base = _base(start, end, 1, q)
    if not _in_month(base, "ashwin"):
        return None
    s, days = _days(start, end, q, ("pratah",), 3)
    held = [i for i in (1, 2) if start <= s[i] < end]
    variant = None
    if len(held) == 1:
        chosen, rule = held[0], "pratipada_at_sunrise"
    elif held:
        chosen, rule, variant = held[0], "vrddhi_first", held[1]
    else:
        chosen, rule = 0, "no_sunrise"
    w = days[chosen]["_w"]
    muhurta = (w["night"][0] - s[chosen]) / 15
    return {
        **base,
        "days": _strip(days[: 3 if variant == 2 else 2]),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[variant]["date"] if variant is not None else None,
        "sthapanaWindow": _span(_clip(start, end, w["pratah"]), q),
        "twoMuhurtas": end - s[chosen] >= 2 * muhurta if held else None,
    }


def _vijayadashami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 284: the afternoon is the main time, pradosha the secondary. The
    afternoon on both days (covered or touched): the earlier, but the later if
    Shravana is current in the later day's afternoon (pp. 283-284); pradosha on
    both days with the afternoon only on the later: the later."""
    base = _base(start, end, 10, q)
    if not _in_month(base, "ashwin"):
        return None
    _, days = _days(start, end, q, ("aparahna", "pradosha"))
    a = [_share(start, end, d["_w"]["aparahna"]) for d in days]
    p = [_share(start, end, d["_w"]["pradosha"]) for d in days]
    later = _clip(start, end, days[1]["_w"]["aparahna"])
    # Shravana lasts far longer than an afternoon: its two ends are enough.
    shravana = bool(later) and SHRAVANA in {Mu.nakshatra_at(t, q.ayanamsa) for t in later}
    if a[0] > 0 and a[1] > 0:
        chosen, rule = (1, "shravana_later") if shravana else (0, "aparahna_both_earlier")
    elif a[0] > 0 or a[1] > 0:
        chosen = 0 if a[0] > 0 else 1
        rule = "pradosha_both_later" if chosen and p[0] > 0 and p[1] > 0 else "aparahna"
    elif p[0] > 0 or p[1] > 0:
        chosen, rule = (0 if p[0] > 0 else 1), "pradosha"
    else:
        chosen, rule = 1, "neither_later"
    w = days[chosen]["_w"]["pradosha" if rule == "pradosha" else "aparahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "pujaWindow": _span(_clip(start, end, w), q),
        "shravanaInLaterAparahna": shravana,
    }


# --- Holika-dahana (NS pp. 342-344) -------------------------------------------------


def _holika(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """The Phalguna Purnima at pradosha, lit at nightfall (Narada). On both days
    the later, since Bhadra is on the first. Never in Bhadra: with Bhadra over
    the pradosha, lit at night once it ends. Reaching neither pradosha, or Bhadra
    past the night: the next day's pradosha, in Pratipada (Bhavishya via
    Nirnayamrta). Not in an adhika month."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "phalguna"):
        return None
    s, days = _days(start, end, q, ("pradosha",))
    bhadra = _bhadra(start, end, q)
    free = bhadra[1] if bhadra else start
    w = [d["_w"]["pradosha"] for d in days]
    p = [_share(start, end, x) for x in w]
    first = _clip(free, end, w[0])
    if p[1] > 0:
        chosen, fire = 1, _clip(free, end, w[1])
        rule = "pradosha_both_later" if p[0] > 0 else "pradosha"
    elif first:
        chosen, rule, fire = 0, "pradosha", first
    elif p[0] > 0 and free < s[1]:
        chosen, rule, fire = 0, "after_bhadra_night", (free, min(end, s[1]))
    else:
        chosen, rule, fire = 1, "shrinking_later", w[1]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "dahanWindow": _span(fire, q),
        "bhadra": _span(bhadra, q),
    }


def _year(q: EkadashiQuery, num: int, build) -> list[dict]:
    rows = _collect(
        q, {num}, lambda a, b, c, qq: build(a, b, c, qq) or {"date": None}, lambda r: (r["date"],)
    )
    return [r for r in rows if r.get("date")]


FESTIVALS = {
    "dipavali": (30, _dipavali, "pp. 299-300"),
    "mahashivaratri": (29, lambda a, b, c, q: _shivaratri(a, b, c, q, True), "pp. 334-337"),
    "masik-shivaratri": (29, lambda a, b, c, q: _shivaratri(a, b, c, q, False), "p. 340"),
    "ganesha-chaturthi": (4, _ganesha, "pp. 47, 198"),
    "raksha-bandhan": (15, _raksha, "p. 180"),
    "janmashtami": (23, _janmashtami, "pp. 183-191"),
    "sharad-navaratri": (1, _navaratri, "pp. 240-241"),
    "vijayadashami": (10, _vijayadashami, "pp. 283-284"),
    "holika-dahana": (15, _holika, "pp. 342-344"),
}


def festival(kind: str, q: EkadashiQuery) -> dict:
    num, build, pages = FESTIVALS[kind]
    rows = _year(q, num, build)
    source = {**SOURCE, "verse": kind, "page": pages}
    return {
        "year": q.year,
        "festival": kind,
        "occurrences": rows,
        "source": source,
        "engine": provenance(q.ayanamsa),
    }
