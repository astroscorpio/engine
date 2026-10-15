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
from jyotisha.ephemeris import ascendant, moon_rise_set

from .fmt import provenance
from .ids import tithi_id
from .models import EkadashiQuery
from .observances import (
    SOURCE,
    _collect,
    _lunar,
    _one,
    _overlap,
    _rise_set,
    _sankashti,
    _sunrises,
    _sunset,
    _vara,
)
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
    chaturdashi = _edge(start, q, False)  # its start; it ends where the Amavasya begins
    trayodashi = (_edge(chaturdashi, q, False), chaturdashi)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "lakshmiPuja": _span(_clip(start, end, days[chosen]["_w"]["pradosha"]), q),
        "nishithaCovered": days[chosen]["nishitha"]["covered"] > 0,
        "set": {
            "dhanteras": _dhanteras(*trayodashi, q),
            "narakaChaturdashi": _naraka(chaturdashi, start, q),
            "lakshmiPuja": {"date": days[chosen]["date"], "vara": days[chosen]["vara"]},
            "govardhan": _govardhan(end, _next, q),
            "bhaiDooj": _bhai_dooj(_next, _edge(_next, q, True), q),
        },
    }


# --- The other four days (festivals.md v4 s9-12, the lead's decisions of 15 Oct 2026) ---


ARUNODAYA = 4 * DANDA  # NS p. 297: "catur-ghatikatmako 'runodayah"


def _edge(t: float, q, forward: bool) -> float:
    """The next tithi change after t, or the last one before it."""
    fn = lambda x: Mu.tithi_at(x, q.ayanamsa)  # noqa: E731
    if forward:
        return Mu._scan(fn, t + 1e-5, t + 1.3, 1 / 24)[0][0]
    return Mu._scan(fn, t - 1.3, t - 1e-5, 1 / 24)[-1][0]


def _tithi(start: float, end: float, q) -> dict:
    return {"start": iso(start, q.tz), "end": iso(end, q.tz)}


def _dhanteras(start: float, end: float, q) -> dict:
    """s9: the Yama-dipa at nightfall (pradosha) on the dark Trayodashi current then
    (NS p. 294, DS p. 76); on both days or neither, the later (DS p. 20)."""
    _, days = _days(start, end, q, ("pradosha",))
    cov = [d["pradosha"]["covered"] > 0 for d in days]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "dhanteras_pradosha"
    else:
        chosen, rule = 1, "dhanteras_both_later" if cov[0] else "dhanteras_neither_later"
    w = days[chosen]["_w"]["pradosha"]
    return {
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "tithi": _tithi(start, end, q),
        "yamaDipa": _span(_clip(start, end, w) or w, q),
    }


def _moonrise(sunrise_jd: float, q) -> float | None:
    """The moonrise in the twelve hours before a sunrise."""
    return moon_rise_set(sunrise_jd - 0.5, sunrise_jd, q.lat, q.lon)[0]


def _naraka(start: float, end: float, q) -> dict:
    """s10, DS pp. 76-77 (NS pp. 295-296): the oil bath on the Caturdashi current at
    the pre-dawn moonrise; at both moonrises the earlier; at neither, the first dawn
    if the Caturdashi begins between its moonrise and sunrise, else the second day
    at moonrise. The bath runs from moonrise (or the tithi's start) to sunrise."""
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    m = [_moonrise(s[1], q), _moonrise(s[2], q)]
    at = [x is not None and start <= x < end for x in m]
    if at[0]:
        chosen, rule = 0, "naraka_moonrise_both_earlier" if at[1] else "naraka_moonrise"
        bath = (max(m[0], start), min(s[1], end))
    elif at[1]:
        chosen, rule = 1, "naraka_moonrise"
        bath = (m[1], min(s[2], end))
    elif m[0] is not None and m[0] < start <= s[1] - DANDA:
        # Begun under a ghatika before sunrise counts as at sunrise (DS's case-2
        # example starts one pala before; research's reading of 15 Oct 2026).
        chosen, rule = 0, "naraka_began_before_sunrise"
        bath = (start, s[1])
    else:
        chosen, rule = 1, "naraka_later_moonrise"
        bath = (m[1] if m[1] is not None else s[2] - ARUNODAYA, s[2])
    rise = s[1 + chosen]
    day = {"date": _date(rise, q), "vara": _vara(rise, q)}
    return {
        **day,
        "rule": rule,
        "tithi": _tithi(start, end, q),
        "moonrise": iso(m[chosen], q.tz) if m[chosen] is not None else None,
        "abhyangaSnana": _span(bath, q),
        "arunodaya": _span((rise - ARUNODAYA, rise), q),
        "lamps": _span(_windows(rise, q)["pradosha"], q),
    }


def _govardhan(start: float, end: float, q) -> dict:
    """s11, DS p. 78: the Pratipada at sunrise lasting nine day-muhurtas or more
    after it (ten in the text; nine to ten our reading): every rite on that day.
    Otherwise Bali's worship, the cow play, the Govardhana-puja and the margapali
    on the Amavasya-joined day before, and the bath, new clothes and nirajana on the
    sunrise day. NS pp. 301-302 (variantDate): the later day only if the Pratipada
    reaches that day's sayahna, the 5th fifth of the daytime."""
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    if end > s[1]:  # the Pratipada is current at the later sunrise
        muhurta = (_sunset(s[1], q) - s[1]) / 15
        later = end - s[1] >= 9 * muhurta
        ns_later = end > s[1] + 12 * muhurta
        rule = "govardhan_nine_muhurtas" if later else "govardhan_earlier"
        bath = s[1]
    else:  # it touches no sunrise
        later = ns_later = False
        rule, bath = "govardhan_no_sunrise_earlier", s[0]
    rise = s[1] if later else s[0]
    morning = (rise, rise + (_sunset(rise, q) - rise) / 5)
    return {
        "date": _date(rise, q),
        "vara": _vara(rise, q),
        "rule": rule,
        "variantDate": _date(s[1] if ns_later else s[0], q) if ns_later != later else None,
        "tithi": _tithi(start, end, q),
        "govardhanPuja": _span(_clip(start, end, morning), q),
        "baliPuja": _span(_night(rise, q), q),
        "bathDate": _date(bath, q) if bath != rise else None,
    }


def _bhai_dooj(start: float, end: float, q) -> dict:
    """s12, DS p. 79: the earlier day only when the Dvitiya covers the afternoon
    (the 4th fifth of the daytime) on that day alone; otherwise the later day. Yama
    is worshipped in that afternoon."""
    _, days = _days(start, end, q, ("aparahna",))
    cov = [d["aparahna"]["covered"] > 0 for d in days]
    if cov[0] and not cov[1]:
        chosen, rule = 0, "bhai_dooj_earlier_alone"
    else:
        chosen, rule = 1, "bhai_dooj_later"
    w = days[chosen]["_w"]["aparahna"]
    return {
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "cover": "both" if all(cov) else "earlier" if cov[0] else "later" if cov[1] else "neither",
        "tithi": _tithi(start, end, q),
        "yamaPuja": _span(_clip(start, end, w) or w, q),
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


def _navaratri(
    start: float, end: float, _next: float, q: EkadashiQuery, month: str = "ashwin"
) -> dict | None:
    """DS p. 65 (NS pp. 240-241): the Pratipada current at sunrise, best lasting
    three muhurtas after it, then two, by some texts one; never the day joined with
    Amavasya, unless the Pratipada lasts under a muhurta after sunrise or touches
    none. Filling a whole day and more, it is kept on the first. Begun within ten
    ghatikas of sunrise, failing that at the Abhijit muhurta; never in the
    afternoon or at night. The Caitra Navaratri follows the same rule (NS p. 113,
    DS p. 31)."""
    base = _base(start, end, 1, q)
    if not _in_month(base, month):
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
    spans = _tithi_spans(start, q)
    ashtami, navami = _ashtami_navami(spans, q)
    out = {
        **base,
        "days": _strip(days[: 3 if held == [1, 2] and chosen == 2 else 2]),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "muhurtasAfterSunrise": round((end - sr) / muhurta[chosen], 2) if chosen else None,
        "sthapanaWindow": _span(window, q),
        "cautions": cautions,
        "navaratriDays": _navaratri_days(sr, spans, q),
        "ashtami": ashtami,
        "navami": navami,
    }
    if month == "ashwin":
        junction = spans[8][1]  # the Ashtami's end, the Navami's start
        out["sandhiPuja"] = _span((junction - DANDA, junction + DANDA), q)
    else:
        out["newYearDate"] = _date(s[1] if end > s[1] else s[0], q)
    return out


def _tithi_spans(start: float, q) -> dict[int, tuple[float, float]]:
    """The bright fortnight's tithis 1-10 from a Pratipada beginning at start."""
    edges = [
        (start, 1),
        *Mu._scan(lambda t: Mu.tithi_at(t, q.ayanamsa), start + 1e-5, start + 11.5, 0.25),
    ]
    return {n: (a, b) for (a, n), (b, _) in zip(edges, edges[1:], strict=False) if 1 <= n <= 10}


def _navaratri_days(first_rise: float, spans: dict, q) -> list[dict]:
    """DS p. 66: each day's worship goes with the tithi at its sunrise (our reading);
    a tithi touching two sunrises is worshipped on both days, and one touching none
    on the day it falls in, beside that day's own tithi. The first day is the
    kalasha-sthapana day, which carries the Pratipada however it falls."""
    out, sr = [], first_rise
    for _ in range(12):
        nr = _rise_set(sr + 0.1, q.lat, q.lon, True)
        nums = [
            n
            for n, (a, b) in spans.items()
            if n <= 9 and (a <= sr < b or (sr < a and b <= nr) or (not out and n == 1 and a < nr))
        ]
        if not nums:
            break
        out.append(
            {"date": _date(sr, q), "vara": _vara(sr, q), "tithis": [tithi_id(n) for n in nums]}
        )
        sr = nr
    return out


def _ashtami_navami(spans: dict, q) -> tuple[dict, dict]:
    """Durgashtami (NS pp. 262-264, DS p. 69): the Ashtami current at sunrise, even
    for a ghatika, joined to the Navami; never Saptami-touched. The earlier day when
    the Ashtami lasts under a ghatika after that sunrise, when the Navami touches no
    sunrise, or when the Ashtami fills the whole first day and only about a muhurta
    of the next. Mahanavami (NS pp. 272-273, DS p. 69): the day the Navami begins if
    it covers three muhurtas before that day's sunset, otherwise the next day."""
    a0, a1 = spans[8]
    n1 = spans[9][1]
    s = _sunrises(a0, q.lat, q.lon, 4)  # s[0] <= a0 < s[1]
    held = [i for i in (1, 2) if a0 <= s[i] < a1]
    if not held:
        k, rule = 0, "ashtami_no_sunrise_earlier"
    else:
        k = held[-1]
        muhurta = (_sunset(s[k], q) - s[k]) / 15
        if a1 - s[k] < DANDA:
            k, rule = k - 1, "under_one_ghatika_earlier"
        elif n1 <= s[k + 1]:
            k, rule = k - 1, "navami_no_sunrise_earlier"
        elif len(held) == 2 and a1 - s[k] <= muhurta:
            k, rule = k - 1, "full_first_day"
        else:
            rule = "sunrise_navami_joined"
    ashtami = {
        "date": _date(s[k], q),
        "vara": _vara(s[k], q),
        "rule": rule,
        "tithi": _tithi(a0, a1, q),
    }
    x = max(i for i in range(4) if s[i] <= a1)  # the day the Navami begins
    sunset = _sunset(s[x], q)
    if sunset - a1 >= 3 * (sunset - s[x]) / 15:
        y, rule = x, "navami_three_muhurtas_evening"
    else:
        y, rule = x + 1, "navami_later"
    navami = {
        "date": _date(s[y], q),
        "vara": _vara(s[y], q),
        "rule": rule,
        "tithi": _tithi(a1, n1, q),
    }
    return ashtami, navami


def _ramanavami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS pp. 118-120, DS p. 33: the Navami covering midday on the earlier day only:
    that day. Otherwise the later day, unless its Navami lasts under three muhurtas
    after sunrise or touches no sunrise: then the earlier. When the later day holds
    but the Dashami touches no sunrise, Smartas keep the earlier day and Vaishnavas
    the later. The arghya is given at midday."""
    base = _base(start, end, 9, q)
    if not _in_month(base, "chaitra"):
        return None
    s, days = _days(start, end, q, ("madhyahna",), 3)
    cov = [d["madhyahna"]["covered"] > 0 for d in days[:2]]
    smarta = vaishnava = None
    if cov[0] and not cov[1]:
        chosen, rule = 0, "midday_earlier_only"
    elif not (start <= s[1] < end) or end - s[1] < 3 * (days[1]["_w"]["night"][0] - s[1]) / 15:
        chosen, rule = 0, "short_later_earlier"
    elif _next <= next(x for x in s if x > end):  # the Dashami touches no sunrise
        chosen, rule = 0, "smarta_vaishnava_split"
        smarta, vaishnava = days[0]["date"], days[1]["date"]
    else:
        chosen, rule = 1, "later_day"
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days[:2]),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "smartaDate": smarta,
        "vaishnavaDate": vaishnava,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
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
    # Vasantotsava (NS p. 345, DS p. 95): the dark Pratipada at sunrise after the
    # Purnima, the earlier when at sunrise on both days; touching none, the day it
    # falls on (our reading, as DS p. 31 rules for the new year).
    p = _sunrises(end, q.lat, q.lon, 2)  # p[0] <= end < p[1]
    at_sunrise = _next > p[1]
    colours = p[1] if at_sunrise else p[0]
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
        "vasantotsava": {
            "date": _date(colours, q),
            "vara": _vara(colours, q),
            "rule": "vasantotsava_sunrise" if at_sunrise else "vasantotsava_no_sunrise",
            "tithi": _tithi(end, _next, q),
        },
        # The morning after the fire: the bath and the salutation of the Holika ash
        # (DS p. 95, "evam ratrau holikotsavam krtva pratah"; tying the colour day to
        # it is our reading, the lead's decision of 15 Oct 2026).
        "colours": {
            "date": _date(s[chosen + 1], q),
            "vara": _vara(s[chosen + 1], q),
            "popularName": "Rangwali Holi",
            "aliases": ["Dhulandi", "Dhuleti"],
        },
    }


# --- Karaka-caturthi, Karva Chauth (NS p. 293; DS pp. 9, 76; VR ff. 80-82) ---------


TITHI_TATTVA = {
    "text": "Tithi-tattva (Raghunandana), quoting the Samvatsara-pradipa",
    "edition": "Smrti-tattva, part 1, Calcutta, 1895",
    "page": "24",
}
VRATARAJA = {
    "text": "Vratraja",
    "author": "Vishvanatha",
    "edition": "Bombay pothi, Khemraj Shrikrishnadas (Internet Archive dates the copy to 1897)",
    "page": "ff. 80-82",
}


def _karva(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """The dark Caturthi ending amanta Ashvina (Kartika krishna purnimanta), current at
    moonrise: at both moonrises the earlier, at neither the later, as for Sankashti
    (NS p. 293; DS pp. 9, 76). VR f. 82 keeps it at nightfall, with the arghya after
    moonrise (f. 80): sunset and moonrise are the sourced times."""
    row = _sankashti(start, end, _next, q)
    if row["lunarMonth"]["amanta"] != "ashwin" or row["lunarMonth"]["adhika"]:
        return None
    s = _sunrises(start, q.lat, q.lon, 2)
    rise = s[0] if row["date"] == _date(s[0], q) else s[1]
    out = {k: v for k, v in row.items() if k not in ("angaraki", "paksha")}
    out["sunset"] = iso(_sunset(rise, q), q.tz)
    return out


# --- Tulsi-vivaha and Tripurotsava (festivals.md s17; the lead's decision of 15 Oct 2026)


def _tulsi(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS pp. 81-82: joined everywhere to the Prabodhotsava, on the parana day of the
    Prabodhini (Kartika shukla) Ekadashi, in the early night (pradosha, our reading).
    The day after the Smarta fast; the Vaishnava parana day is variantDate."""
    row = _one(start, end, _next, q)
    month = row["lunarMonth"]
    if month["amanta"] != "kartika" or month["adhika"] or row["paksha"] != "shukla":
        return None
    s = _sunrises(start, q.lat, q.lon, 6)
    dates = [_date(t, q) for t in s]
    smarta = dates.index(row["smarta"]["date"]) + 1
    vaishnava = dates.index(row["vaishnava"]["date"]) + 1
    return {
        "lunarMonth": month,
        "tithi": row["tithi"],
        "fastDate": row["smarta"]["date"],
        "date": dates[smarta],
        "vara": _vara(s[smarta], q),
        "rule": "parana_day_early_night",
        "variantDate": dates[vaishnava] if vaishnava != smarta else None,
        "window": _span(_windows(s[smarta], q)["pradosha"], q),
    }


def _tripura(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 312 (Bhargavarcana-dipika), DS p. 84: the Tripurotsava and its lamps at
    dusk on the Kartika Purnima. The Purnima current at pradosha on one day: that day;
    on both or neither: the later (NS p. 311, "kartiki paurnamasi para grahya")."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "kartika"):
        return None
    _, days = _days(start, end, q, ("pradosha",))
    cov = [d["pradosha"]["covered"] > 0 for d in days]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "tripura_pradosha"
    else:
        chosen, rule = 1, "tripura_both_later" if cov[0] else "tripura_neither_later"
    w = days[chosen]["_w"]["pradosha"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "popularName": "Dev Deepawali",
        "window": _span(_clip(start, end, w) or w, q),
    }


# --- Magha shukla: Vasanta Panchami, Ratha-saptami, Bhishmashtami (festivals.md s18-20) --


def _vasanta(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 89: the later day only when the Panchami covers the forenoon on the later
    day alone; otherwise the earlier (DS p. 9: a Panchami is taken Caturthi-joined).
    The forenoon is sunrise to midday, our reading."""
    base = _base(start, end, 5, q)
    if not _in_month(base, "magha"):
        return None
    s, _ = _days(start, end, q, ())
    forenoon = [(s[i], (s[i] + _sunset(s[i], q)) / 2) for i in (0, 1)]
    cov = [_share(start, end, w) > 0 for w in forenoon]
    if cov[1] and not cov[0]:
        chosen, rule = 1, "forenoon_later_alone"
    else:
        chosen, rule = 0, "both_earlier" if all(cov) else "earlier"
    return {
        **base,
        "date": _date(s[chosen], q),
        "vara": _vara(s[chosen], q),
        "rule": rule,
        "popularName": "Basant Panchami",
        # Decision 18a (15 Oct 2026): Sarasvati's worship in the forenoon of the
        # Caturthi-joined Panchami, the Samvatsara-pradipa in the Tithi-tattva.
        "alsoNamed": [{"name": "Saraswati Puja", "source": TITHI_TATTVA}],
        "forenoon": [
            {"date": _date(s[i], q), **_span(forenoon[i], q), "covered": cov[i]} for i in (0, 1)
        ],
        "pujaWindow": _span(_clip(start, end, forenoon[chosen]), q),
    }


def _ratha(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 329, DS p. 89: the Saptami covering arunodaya, the four ghatikas before
    sunrise; at both, the earlier. A short Saptami ending before the next arunodaya
    goes to the first day, bathed at its arunodaya in the Shashthi (NS p. 330); one
    touching neither arunodaya is taken on that day too (our reading)."""
    base = _base(start, end, 7, q)
    if not _in_month(base, "magha"):
        return None
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    dawn = [(s[i] - ARUNODAYA, s[i]) for i in (1, 2)]
    cov = [_share(start, end, w) > 0 for w in dawn]
    if cov[0]:
        rise, rule = s[1], "arunodaya_both_earlier" if cov[1] else "arunodaya"
    elif cov[1]:
        rise, rule = s[2], "arunodaya"
    else:
        rise, rule = s[0], "shashthi_joined_first_day"
    return {
        **base,
        "date": _date(rise, q),
        "vara": _vara(rise, q),
        "rule": rule,
        "arunodaya": _span((rise - ARUNODAYA, rise), q),
    }


def _bhishma(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 90: the Ashtami covering midday, the shraddha being ekoddishta, decided as
    for every ekoddishta (NS p. 718): one day only, that day; both, the earlier if
    equal, else the day with more; neither, the earlier. Midday is the 8th and 9th
    day-muhurtas, from the kutapa to the rauhina."""
    from .pitru_paksha import _pick  # pitru_paksha imports this module

    base = _base(start, end, 8, q)
    if not _in_month(base, "magha"):
        return None
    s = _sunrises(start, q.lat, q.lon, 3)
    pick = _pick(start, end, s, q, "kutapaRauhina", lambda *_: (0, "neither_earlier"))
    _, w = pick.pop("_chosen")
    return {
        **base,
        **pick,
        "tarpanaWindow": _span(w, q),
    }


# --- Decision 21 (festivals.md s21, 15 Oct 2026) -----------------------------------


def _kalashtami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 313: the fast on the Ashtami covering midday (the 3rd fifth); covering it on
    both days, wholly or in part, the earlier. Covering neither, the day whose sunrise
    it holds (our reading). variantDate is the Kaustubha's pradosha rule (both days:
    the later), which DS p. 84 reports."""
    base = _base(start, end, 23, q)
    if not _in_month(base, "kartika"):
        return None
    s, days = _days(start, end, q, ("madhyahna", "pradosha"))
    mid = [d["madhyahna"]["covered"] > 0 for d in days]
    if mid[0] != mid[1]:
        chosen, rule = (0 if mid[0] else 1), "midday"
    elif mid[0]:
        chosen, rule = 0, "midday_both_earlier"
    else:
        chosen, rule = 1, "midday_neither_sunrise_day"
    pr = [d["pradosha"]["covered"] > 0 for d in days]
    kaustubha = (0 if pr[0] else 1) if pr[0] != pr[1] else 1
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[kaustubha]["date"] if kaustubha != chosen else None,
        "popularName": "Kaal Bhairav Jayanti",
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


def _dattatreya(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 315, DS p. 84: the Margashirsha Purnima covering pradosha; at both pradoshas
    or neither, the later day (our reading, by the general Purnima rule, NS p. 73)."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "margashirsha"):
        return None
    _, days = _days(start, end, q, ("pradosha",))
    cov = [d["pradosha"]["covered"] > 0 for d in days]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "pradosha"
    else:
        chosen, rule = 1, "pradosha_both_later" if cov[0] else "pradosha_neither_later"
    w = days[chosen]["_w"]["pradosha"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


def _ganesha_jayanti(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 89: the Vinayaka-vrata of Magha shukla Caturthi follows the Bhadrapada rule
    (s4: the next day if the Caturthi reaches its midday, else the Trtiya-joined
    earlier day). The Tila or Varada night vow takes pradosha (a note)."""
    base = _base(start, end, 4, q)
    if not _in_month(base, "magha"):
        return None
    _, days = _days(start, end, q, ("madhyahna",))
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
        "popularName": "Ganesh Jayanti",
        "pujaWindow": {k: days[chosen]["madhyahna"][k] for k in ("start", "end")},
    }


def _holashtak(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """MC 1.40 with the Shighrabodha in its commentary: the eight days from the Phalguna
    shukla Ashtami to the Purnima, avoided for marriage and auspicious acts only on the
    Beas, Ravi and Sutlej and at Pushkar; elsewhere auspicious."""
    base = _base(start, end, 8, q)
    if not _in_month(base, "phalguna"):
        return None
    t = start
    for _ in range(8):  # the Ashtami to the Purnima
        t = _edge(t, q, True)
    return {
        **base,
        "date": _date(start, q),
        "endDate": _date(t, q),
        "rule": "holashtak_period",
        "period": _tithi(start, t, q),
        "regions": ["beas", "ravi", "sutlej", "pushkar"],
    }


# --- Akshaya Tritiya, Parashurama Jayanti, Guru Purnima (festivals.md s24-25) -------


def _forenoon(sr: float, q) -> tuple[float, float]:
    """Sunrise to midday: DS p. 36's own gloss of the forenoon."""
    return sr, (sr + _sunset(sr, q)) / 2


def _akshaya(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 134 (VR f. 43): the Vaishakha shukla Tritiya covering the forenoon; on
    both days, the later. variantDate is DS p. 36's rule for both days: the later
    only if the Tritiya lasts more than three muhurtas into it, else the earlier."""
    base = _base(start, end, 3, q)
    if not _in_month(base, "vaishakha"):
        return None
    s, days = _days(start, end, q, ())
    fore = [_forenoon(s[i], q) for i in (0, 1)]
    cov = [_share(start, end, w) > 0 for w in fore]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "forenoon"
    elif cov[0]:
        chosen, rule = 1, "forenoon_both_later"
    else:
        chosen, rule = 1, "forenoon_neither_later"
    ds = chosen
    if all(cov):
        ds = 1 if end - s[1] > 3 * (_sunset(s[1], q) - s[1]) / 15 else 0
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[ds]["date"] if ds != chosen else None,
        "pujaWindow": _span(_clip(start, end, fore[chosen]) or fore[chosen], q),
    }


def _parashurama(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 37 (VR ff. 42-43): the Tritiya covering the night's first watch (a quarter
    of the night, our reading); the earlier day only if its first watch alone is
    covered; both, wholly or in part, the later. Arghya at pradosha."""
    base = _base(start, end, 3, q)
    if not _in_month(base, "vaishakha"):
        return None
    _, days = _days(start, end, q, ("pradosha",))
    watch = []
    for d in days:
        a, b = d["_w"]["night"]
        watch.append((a, a + (b - a) / 4))
    cov = [_share(start, end, w) > 0 for w in watch]
    if cov[0] and not cov[1]:
        chosen, rule = 0, "first_watch_earlier_only"
    else:
        chosen, rule = 1, "first_watch_later"
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "firstWatch": _span(watch[chosen], q),
        "arghyaWindow": {k: days[chosen]["pradosha"][k] for k in ("start", "end")},
    }


def _guru_purnima(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 160, DS p. 43: the Vyasa-puja of ascetics on the Ashadha Purnima, on the
    later day if the Purnima lasts three muhurtas or more after its sunrise, otherwise
    the earlier, Caturdashi-joined day (DS p. 20). The worship is in the morning (the
    1st fifth of the daytime, our reading of NS p. 28)."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "ashadha"):
        return None
    s, days = _days(start, end, q, ())
    muhurta = (_sunset(s[1], q) - s[1]) / 15
    if start <= s[1] < end and end - s[1] >= 3 * muhurta:
        chosen, rule = 1, "three_muhurtas_later"
    else:
        chosen, rule = 0, "caturdashi_joined_earlier"
    sr = s[chosen]
    morning = (sr, sr + (_sunset(sr, q) - sr) / 5)
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "popularName": "Guru Purnima",
        "displayName": "Vyāsa-pūjā",
        "pujaWindow": _span(_clip(start, end, morning) or morning, q),
    }


# --- Bengal Durga-puja by the Tithi-tattva (festivals.md s22) ------------------------

MOVABLE = {0, 3, 6, 9}  # Aries, Cancer, Libra, Capricorn


def _udaya(n: int, spans: dict, s: list[float], q) -> list[int]:
    """TT pp. 77-79: the sunrises a tithi holds for at least a day-muhurta after them
    ("ghatika" read as a muhurta, TT's own gloss)."""
    a, b = spans[n]
    return [k for k, sr in enumerate(s) if a <= sr and b - sr >= (_sunset(sr, q) - sr) / 15]


def _falls_in(t: float, s: list[float]) -> int:
    return max(k for k, sr in enumerate(s) if sr <= t)


def _movable(a: float, b: float, q) -> list[dict]:
    """Stretches of [a, b] with a movable lagna or a movable navamsa (TT p. 79)."""
    ay = q.ayanamsa
    out: list[tuple[float, float]] = []
    for x, y, idx in _vspans(
        lambda t: int(ascendant(t, q.lat, q.lon, ay)[0].longitude // (30 / 9)), a, b
    ):
        if idx // 9 in MOVABLE or idx % 12 in MOVABLE:
            if out and abs(out[-1][1] - x) < 1e-9:
                out[-1] = (out[-1][0], y)
            else:
                out.append((x, y))
    return [_span(w, q) for w in out]


def _vspans(fn, t0: float, t1: float) -> list[tuple[float, float, int]]:
    cuts = [t0, *(t for t, _ in Mu._scan(fn, t0, t1, 1 / 288)), t1]
    return [(a, b, fn((a + b) / 2)) for a, b in zip(cuts, cuts[1:], strict=False) if b > a]


def _durga_puja(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """The Tithi-tattva's Durga-puja (pp. 63-82), keyed on the Ashvina shukla Shashthi.
    Every act on the tithi current at sunrise for a muhurta (pp. 77-79): the leaf entry
    on the Saptami's forenoon, Mahashtami (the complete first day when the Ashtami holds
    two sunrises), the sandhi of 48 minutes, Mahanavami on the sunrise Navami and the
    immersion on the sunrise Dashami's forenoon, the last two in a movable lagna or
    navamsa (p. 79). Bodhana in the Shashthi's evening twilight (pp. 63-65)."""
    base = _base(start, end, 6, q)
    if not _in_month(base, "ashwin"):
        return None
    spans = {6: (start, end)}
    t = end
    for n in (7, 8, 9, 10):
        nxt = _edge(t, q, True)
        spans[n] = (t, nxt)
        t = nxt
    s = _sunrises(start, q.lat, q.lon, 9)  # s[0] <= start
    day = lambda k: {"date": _date(s[k], q), "vara": _vara(s[k], q)}  # noqa: E731

    def forenoon(k: int, n: int) -> tuple[float, float] | None:
        return _clip(*spans[n], (s[k], (s[k] + _sunset(s[k], q)) / 2))

    # The leaf entry: the sunrise Saptami, in the forenoon; a lost Saptami goes to the
    # Shashthi-joined day it falls on (p. 79).
    held = _udaya(7, spans, s, q)
    leaf, leaf_rule = (
        (held[0], "sunrise_saptami")
        if held
        else (_falls_in(spans[7][0], s), "kshaya_shashthi_joined")
    )
    leaf_w = forenoon(leaf, 7)
    # Mahashtami: the sunrise Ashtami; the complete first day when it holds two (p. 78).
    held = _udaya(8, spans, s, q)
    if len(held) >= 2:
        ashtami, a_rule = held[0], "complete_first_day"
    elif held:
        ashtami, a_rule = held[0], "sunrise_ashtami"
    else:
        ashtami, a_rule = _falls_in(spans[8][0], s), "kshaya_day_it_falls_on"
    junction = spans[8][1]
    held = _udaya(9, spans, s, q)
    navami, n_rule = (
        (held[0], "sunrise_navami")
        if held
        else (_falls_in(spans[9][0], s), "kshaya_day_it_falls_on")
    )
    # The Dashami lasting under a muhurta after sunrise sends the immersion to the day
    # before (p. 79).
    held = _udaya(10, spans, s, q)
    if held:
        dashami, d_rule = held[0], "sunrise_dashami"
    else:
        dashami, d_rule = _falls_in(spans[10][0], s), "short_dashami_day_before"
    imm_w = forenoon(dashami, 10) or forenoon(dashami, 9)
    shravana = bool(imm_w) and SHRAVANA in {Mu.nakshatra_at(x, q.ayanamsa) for x in imm_w}

    # Bodhana (p. 65): the Shashthi in the evening twilight (three ghatis after sunset,
    # our reading); the evening before the leaf entry holds both rites if it has it.
    def twilight(k: int) -> tuple[float, float]:
        ss = _sunset(s[k], q)
        return ss, ss + 3 * DANDA

    eve = leaf - 1
    covered = [k for k in range(0, leaf) if _share(*spans[6], twilight(k)) > 0]
    if eve >= 0 and eve in covered:
        bodhana = {**day(eve), "rule": "evening_before_leaf_entry", **_span(twilight(eve), q)}
    elif covered:
        k = covered[0]
        bodhana = {**day(k), "rule": "shashthi_evening", **_span(twilight(k), q)}
    else:  # the Shashthi touches neither evening: the later day's forenoon Shashthi
        w = forenoon(1, 6)
        bodhana = {**day(1 if w else 0), "rule": "neither_evening_forenoon", **(_span(w, q) or {})}
    amantrana = {**day(max(eve, 0)), **_span(twilight(max(eve, 0)), q)}
    _, ns_navami = _ashtami_navami({8: spans[8], 9: spans[9]}, q)
    ns_date = ns_navami["date"] if ns_navami["date"] != _date(s[navami], q) else None
    return {
        **base,
        "date": _date(s[ashtami], q),
        "vara": _vara(s[ashtami], q),
        "rule": a_rule,
        "bodhana": bodhana,
        "amantrana": amantrana,
        "patrikaPravesha": {**day(leaf), "rule": leaf_rule, "forenoon": _span(leaf_w, q),
                            "movableWindows": _movable(*leaf_w, q) if leaf_w else []},
        "mahashtami": {**day(ashtami), "rule": a_rule},
        "sandhiPuja": _span((junction - DANDA, junction + DANDA), q),
        "mahanavami": {**day(navami), "rule": n_rule, "nsDsDate": ns_date},
        "visarjana": {**day(dashami), "rule": d_rule, "forenoon": _span(imm_w, q),
                      "movableWindows": _movable(*imm_w, q) if imm_w else [], "shravana": shravana},
    }  # fmt: skip


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
    "sharad-navaratri": (1, _navaratri, "pp. 240-241, 262-265, 272-273", "pp. 65-66, 68-69"),
    "chaitra-navaratri": (
        1,
        lambda a, b, c, q: _navaratri(a, b, c, q, "chaitra"),
        "pp. 113, 118, 240-241, 262-265, 272-273",
        "pp. 31, 33-34, 65-66, 69",
    ),
    "ramanavami": (9, _ramanavami, "pp. 118-120", "p. 33"),
    "vijayadashami": (10, _vijayadashami, "pp. 283-284", "p. 71"),
    "holika-dahana": (15, _holika, "pp. 342-345", "pp. 94-95"),
    "karva-chauth": (19, _karva, "p. 293", "pp. 9, 76"),
    "tulsi-vivah": (11, _tulsi, "p. 306", "pp. 81-82"),
    "tripurotsava": (15, _tripura, "pp. 311-312", "p. 84"),
    "vasanta-panchami": (5, _vasanta, "p. 329", "pp. 9, 89"),
    "ratha-saptami": (7, _ratha, "pp. 329-332", "p. 89"),
    "bhishma-ashtami": (8, _bhishma, "pp. 332-333, 718", "pp. 89-90"),
    "kalashtami": (23, _kalashtami, "pp. 312-313", "p. 84"),
    "dattatreya-jayanti": (15, _dattatreya, "p. 315", "p. 84"),
    "ganesha-jayanti": (4, _ganesha_jayanti, "p. 329", "p. 89"),
    "holashtak": (8, _holashtak, None, None),
    "akshaya-tritiya": (3, _akshaya, "pp. 134-135", "pp. 36-37"),
    "parashurama-jayanti": (3, _parashurama, "p. 134", "p. 37"),
    "guru-purnima": (15, _guru_purnima, "p. 160", "pp. 20, 43-44"),
    "durga-puja": (6, _durga_puja, "pp. 262-265, 272-273", "p. 69"),
}
RITE_SOURCES = {
    "karva-chauth": VRATARAJA,
    "akshaya-tritiya": {**VRATARAJA, "page": "ff. 43-44"},
    "parashurama-jayanti": {**VRATARAJA, "page": "ff. 42-43"},
    "vasanta-panchami": {**VRATARAJA, "page": "f. 103"},
    "ratha-saptami": {**VRATARAJA, "page": "f. 115"},
}


MC_140 = {
    "text": "Muhurta-cintamani",
    "verse": "1.40, with the Shighrabodha in the commentary",
    "edition": "with Govinda's Piyushadhara, 1945",
    "page": "33-34",
}


def festival(kind: str, q: EkadashiQuery) -> dict:
    num, build, pages, ds_pages = FESTIVALS[kind]
    rows = _year(q, num, build)
    if kind == "holashtak":
        source = MC_140
    elif kind == "durga-puja":
        source = {**TITHI_TATTVA, "text": "Tithi-tattva (Raghunandana)", "page": "63-82"}
    else:
        source = {**SOURCE, "verse": kind, "page": pages}
    return {
        "year": q.year,
        "festival": kind,
        "occurrences": rows,
        "source": source,
        "alsoSource": {**DS, "verse": kind, "page": ds_pages} if ds_pages else None,
        **({"riteSource": RITE_SOURCES[kind]} if kind in RITE_SOURCES else {}),
        "engine": provenance(q.ayanamsa),
    }
