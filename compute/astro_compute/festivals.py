"""GET /v1/festivals/<id>: the festival days of a year at a place.

Rules from docs/sources/festivals.md: Nirnaya-sindhu (1898 printing; "NS") and,
where research recommends it, the Dharmasindhu (1888 printing; "DS"), with NS's
own day kept as variantDate where the two differ. Windows:
  madhyahna  the 3rd fifth of the daytime (NS p. 28);
  aparahna   the 4th fifth of the daytime (our reading of NS p. 28's five-part
             day; DS p. 32 uses it too). NS's monthly shraddha keeps its own
             last third (observances.py);
  abhijit    the 8th of the 15 day muhurtas;
  pradosha   three muhurtas after sunset, a muhurta a fifteenth of the night;
  nishitha   two ghatikas around the middle of the night (Madhava, NS p. 335),
             taken as a fifteenth of the night centred on its midpoint (our
             reading of the ghatika's length).
A ghatika is 24 minutes and a yama a quarter of the daytime (NS p. 82). Bhadra
is the Vishti karana: in a Purnima, its first half, with its tail the last 3
ghatikas of the tithi's 3rd prahara (an eighth) and its face the first 5 of the
4th (DS pp. 94-95, MC 1.44).
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
ROHINI, CHITRA, SHRAVANA = 3, 13, 21  # nakshatra indexes, Ashvini = 0
VAIDHRITI = 26  # yoga index, Vishkambha = 0
DS = {
    "text": "Dharmasindhu",
    "edition": "Kasinatha Upadhyaya, ed. Krsna Sastri Navare, Nirnaya-sagara Press, Bombay, 1888",
}


def _night(sunrise_jd: float, q) -> tuple[float, float]:
    ss = _sunset(sunrise_jd, q)
    return ss, _rise_set(ss + 0.01, q.lat, q.lon, True)


def _windows(sunrise_jd: float, q) -> dict[str, tuple[float, float]]:
    ss, nr = _night(sunrise_jd, q)
    night, day = nr - ss, ss - sunrise_jd
    mid = ss + night / 2
    return {
        "madhyahna": (sunrise_jd + 2 * day / 5, sunrise_jd + 3 * day / 5),
        "aparahna": (sunrise_jd + 3 * day / 5, sunrise_jd + 4 * day / 5),
        "abhijit": (sunrise_jd + 7 * day / 15, sunrise_jd + 8 * day / 15),
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


# --- Raksha Bandhan (NS pp. 179-180; DS p. 49) -------------------------------------


def _after(t: float, w: tuple[float, float]) -> tuple[float, float] | None:
    """The part of window w after moment t."""
    return (max(t, w[0]), w[1]) if t < w[1] else None


def _raksha_ns(start: float, end: float, s: list[float], days: list[dict], free: float) -> int:
    """NS p. 180: the earlier day's afternoon, even when the Upakarma is on the
    next day; after Bhadra, even at night; never the Purnima joined with Pratipada."""
    if start < days[0]["_w"]["aparahna"][1] and free < s[1]:
        return 0
    return 1


def _raksha(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 49: the Purnima current at sunrise and lasting more than three
    muhurtas after it: that day, in the afternoon or at pradosha, free of Bhadra.
    Otherwise the earlier day, at pradosha or about then, free of Bhadra."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "shravana"):
        return None
    s, days = _days(start, end, q, ("aparahna", "pradosha"))
    bhadra = _bhadra(start, end, q)
    free = bhadra[1] if bhadra else start  # the Purnima after Bhadra
    w0, w1 = days[0]["_w"], days[1]["_w"]
    muhurta = (w1["night"][0] - s[1]) / 15
    if start <= s[1] < end and end - s[1] > 3 * muhurta:
        chosen, rule = 1, "udaya_three_muhurtas"
        tie = _after(free, w1["aparahna"]) or _after(free, w1["pradosha"])
    else:
        chosen, rule = 0, "earlier_pradosha"
        tie = _after(free, w0["pradosha"]) or (free, min(end, s[1]))
    ns = _raksha_ns(start, end, s, days, free)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[ns]["date"] if ns != chosen else None,
        "tieWindow": _span(tie, q),
        "bhadra": _span(bhadra, q),
    }


# --- Janmashtami and Jayanti (NS pp. 183-192; DS pp. 49-51) --------------------------


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
    variant = None
    # The split year: one observance on the Rohini day (Madhava, DS pp. 50-51),
    # if that day's Ashtami lasts a muhurta after sunrise (DS); NS p. 192 keeps
    # two fasts, the first day being its Janmashtami.
    muhurta = (days[1]["_w"]["night"][0] - s[1]) / 15
    if jay and jay[1] == "split_later" and start <= s[1] and end - s[1] >= muhurta:
        variant, chosen, rule = chosen, 1, "split_rohini_day"
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
        "variantDate": days[variant]["date"] if variant is not None else None,
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


# --- Sharad Navaratri and Vijayadashami (NS pp. 240-241, 283-284; DS pp. 65, 71) ---------


def _navaratri(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 65 (NS pp. 240-241): the Pratipada current at sunrise, best lasting
    three muhurtas after it, then two, by some texts one; never the day joined with
    Amavasya, unless the Pratipada lasts under a muhurta after sunrise or touches
    none. Filling a whole day and more, it is kept on the first. Begun within ten
    ghatikas of sunrise, failing that at the Abhijit muhurta; never in the
    afternoon or at night."""
    base = _base(start, end, 1, q)
    if not _in_month(base, "ashwin"):
        return None
    s, days = _days(start, end, q, (), 3)
    held = [i for i in (1, 2) if start <= s[i] < end]
    muhurta = [(d["_w"]["night"][0] - s[i]) / 15 for i, d in enumerate(days)]
    if not held:
        chosen, rule = 0, "no_sunrise_amavasya_joined"
    elif len(held) == 2:
        chosen, rule = 1, "full_day_first"
    elif end - s[1] < muhurta[1]:
        chosen, rule = 0, "under_one_muhurta_amavasya_joined"
    else:
        chosen, rule = 1, "pratipada_at_sunrise"
    sr, w = s[chosen], days[chosen]["_w"]
    window = _clip(start, end, (sr, sr + 10 * DANDA)) or _clip(start, end, w["abhijit"])
    cautions = []
    if window:
        ay = q.ayanamsa
        if window[0] < start + 16 * DANDA:
            cautions.append("first_16_nadis")
        if CHITRA in {Mu.nakshatra_at(t, ay) for t in window}:
            cautions.append("chitra")
        if VAIDHRITI in {Mu.yoga_at(t, ay) for t in window}:
            cautions.append("vaidhriti")
    return {
        **base,
        "days": _strip(days[: 3 if held == [1, 2] and chosen == 2 else 2]),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "muhurtasAfterSunrise": round((end - sr) / muhurta[chosen], 2) if chosen else None,
        "sthapanaWindow": _span(window, q),
        "cautions": cautions,
    }


def _vijayadashami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 284 (DS p. 71): the afternoon is the main time, pradosha the
    secondary. The afternoon on both days (covered or touched): the earlier, but
    the later if Shravana is current in the later day's afternoon (pp. 283-284);
    pradosha on both days with the afternoon only on the later: the later."""
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


# --- Holika-dahana (NS pp. 342-344; DS pp. 94-95) ------------------------------------


def _holika_ns(start: float, end: float, s: list[float], w: list, free: float) -> int:
    """NS: the Purnima at pradosha, on both days the later; with Bhadra over the
    first pradosha, lit at night once Bhadra ends; reaching neither pradosha, or
    Bhadra past the night, the next day in Pratipada (p. 343)."""
    p = [_share(start, end, x) for x in w]
    if p[1] > 0:
        return 1
    return 0 if p[0] > 0 and (_clip(free, end, w[0]) or free < s[1]) else 1


def _clear_of(w: tuple[float, float] | None, face: tuple[float, float]):
    """Window w with the face cut out: the part before it, else the part after."""
    if not w or _overlap(*w, *face) == 0:
        return w
    return _clip(w[0], w[1], (w[0], face[0])) or _clip(w[0], w[1], (face[1], w[1]))


def _holika(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 94. The Purnima at pradosha, free of Bhadra. Pradosha on both days,
    or partly on the second: the second, Bhadra being on the first. The first
    day's pradosha in Bhadra and none on the second: if the Purnima lasts 3 1/2
    yamas into the second day and the Pratipada grows, the second day's pradosha
    in Pratipada; if the Pratipada shrinks, the first night, in Bhadra's tail or
    avoiding its face; otherwise after Bhadra if it ends before midnight, else in
    Bhadra avoiding its face. Pradosha on neither day: the first night, in
    Bhadra's tail, else in Bhadra after pradosha. Never by day; not in an
    adhika month."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "phalguna"):
        return None
    s, days = _days(start, end, q, ("pradosha",))
    bhadra = _bhadra(start, end, q)
    free = bhadra[1] if bhadra else start
    face, tail = Mu.bhadra_face_tail(15, start, end)
    w = [d["_w"]["pradosha"] for d in days]
    p = [_share(start, end, x) for x in w]
    night = days[0]["_w"]["night"]
    midnight = (night[0] + night[1]) / 2
    pr = _clip(start, end, w[0])
    tail_at_night = tail[0] >= max(night[0], start) and tail[1] <= night[1]
    if p[1] > 0:
        chosen, rule, fire = 1, "pradosha_later", _clip(start, end, w[1])
    elif pr and _clip(free, end, w[0]):
        chosen, rule, fire = 0, "pradosha", _clip(free, end, w[0])
    elif pr:  # the first pradosha in Bhadra, none on the second day
        yama = (days[1]["_w"]["night"][0] - s[1]) / 4
        long = start <= s[1] < end and end - s[1] >= 3.5 * yama
        if long and _next - end > end - start:
            chosen, rule, fire = 1, "sardha_triyama_later", w[1]
        elif long:
            chosen, rule = 0, "shrinking_pratipada_tail"
            fire = tail if tail_at_night else _clear_of(pr, face)
        elif free <= midnight:
            chosen, rule, fire = 0, "after_bhadra_before_midnight", (free, midnight)
        else:
            chosen, rule, fire = 0, "bhadra_avoiding_face", _clear_of(pr, face)
    else:  # pradosha on neither day
        chosen = 0
        after = _clip(max(start, w[0][1]), min(free, night[1]), night)
        if tail_at_night and tail[0] >= w[0][1]:
            rule, fire = "neither_tail", tail
        else:
            rule, fire = "neither_after_pradosha", _clear_of(after, face)
    ns = _holika_ns(start, end, s, w, free)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[ns]["date"] if ns != chosen else None,
        "dahanWindow": _span(fire, q),
        "bhadra": _span(bhadra, q),
        "bhadraTail": _span(tail, q),
        "bhadraFace": _span(face, q),
    }


def _year(q: EkadashiQuery, num: int, build) -> list[dict]:
    rows = _collect(
        q, {num}, lambda a, b, c, qq: build(a, b, c, qq) or {"date": None}, lambda r: (r["date"],)
    )
    return [r for r in rows if r.get("date")]


# kind: (tithi, builder, NS pages, DS pages or None)
FESTIVALS = {
    "dipavali": (30, _dipavali, "pp. 299-300", None),
    "mahashivaratri": (
        29,
        lambda a, b, c, q: _shivaratri(a, b, c, q, True),
        "pp. 334-337",
        None,
    ),
    "masik-shivaratri": (29, lambda a, b, c, q: _shivaratri(a, b, c, q, False), "p. 340", None),
    "ganesha-chaturthi": (4, _ganesha, "pp. 47, 198", None),
    "raksha-bandhan": (15, _raksha, "pp. 179-180", "p. 49"),
    "janmashtami": (23, _janmashtami, "pp. 183-192", "pp. 49-51"),
    "sharad-navaratri": (1, _navaratri, "pp. 240-241", "pp. 65-66"),
    "vijayadashami": (10, _vijayadashami, "pp. 283-284", "p. 71"),
    "holika-dahana": (15, _holika, "pp. 342-344", "pp. 94-95"),
}


def festival(kind: str, q: EkadashiQuery) -> dict:
    num, build, pages, ds_pages = FESTIVALS[kind]
    rows = _year(q, num, build)
    source = {**SOURCE, "verse": kind, "page": pages}
    return {
        "year": q.year,
        "festival": kind,
        "occurrences": rows,
        "source": source,
        "alsoSource": {**DS, "verse": kind, "page": ds_pages} if ds_pages else None,
        "engine": provenance(q.ayanamsa),
    }
