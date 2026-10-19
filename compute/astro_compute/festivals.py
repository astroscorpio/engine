"""GET /v1/festivals/<id>: the festival days of a year at a place.

Rules from docs/sources/festivals.md: Nirnaya-sindhu (1918 Kalyan printing; "NS") and,
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

import copy
import datetime as dt
from functools import lru_cache

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import ascendant, luminaries, moon_rise_set, positions

from .fmt import provenance
from .ids import MASA_IDS, tithi_id
from .models import EkadashiQuery
from .observances import (
    NEAR_BOUNDARY,
    SOURCE,
    _collect,
    _full_or_new,
    _lunar,
    _one,
    _overlap,
    _rise_set,
    _sankashti,
    _sunrises,
    _sunset,
    _vara,
)
from .sankranti import _one as _sankranti_one
from .timeutil import aware, iso, local_jd

DANDA = 24 / 1440  # one ghatika (danda), in days
ROHINI, CHITRA, SHRAVANA = 3, 13, 21  # nakshatra indexes, Ashvini = 0
VAIDHRITI = 26  # yoga index, Vishkambha = 0
DS = {
    "text": "Dharmasindhu",
    "edition": (
        "Kāśīnātha Upādhyāya (1790), edited by Kṛṣṇa Śāstrī Navare, First edition, "
        "Nirṇaya-sāgara Press, Bombay, 1888"
    ),
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
    naraka = _naraka(chaturdashi, start, q)
    # Decision 42 (18 Oct 2026): the row on the eve of the Lakshmi Puja, the lamps evening or
    # the bath day, if either falls there.
    eve = (dt.date.fromisoformat(days[chosen]["date"]) - dt.timedelta(1)).isoformat()
    lamps = naraka["lampsVariant"]
    eve_row = (
        "lampsVariant"
        if lamps and lamps["date"] == eve
        else "narakaChaturdashi"
        if naraka["date"] == eve
        else None
    )
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "lakshmiPuja": _span(_clip(start, end, days[chosen]["_w"]["pradosha"]), q),
        "nishithaCovered": days[chosen]["nishitha"]["covered"] > 0,
        "eveRow": eve_row,
        "set": {
            "dhanteras": _dhanteras(*trayodashi, q),
            "narakaChaturdashi": naraka,
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
    if the Caturdashi begins between its moonrise and sunrise, the next dawn if it holds
    no sunrise at all (DS's second example of the case), else the second day at
    moonrise. The bath runs from moonrise (or the tithi's start) to sunrise."""
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
    elif end <= s[1]:
        # Holding no sunrise, it is over before that dawn's moonrise, and the bath is still
        # at that dawn: DS p. 77, "in both cases the bath is at the next moonrise" (research,
        # festivals.md, backend check on s10, 18 Oct 2026).
        chosen, rule = 0, "naraka_no_sunrise_next_dawn"
        bath = (m[0] if m[0] is not None else s[1] - ARUNODAYA, s[1])
    else:
        chosen, rule = 1, "naraka_later_moonrise"
        bath = (m[1] if m[1] is not None else s[2] - ARUNODAYA, s[2])
    rise = s[1 + chosen]
    day = {"date": _date(rise, q), "vara": _vara(rise, q)}
    # NS p. 297 (the Divodasiya): with the bath on the Caturdashi's second day, the lamps may be
    # given at the first day's pradosha while the Caturdashi is current then.
    early = _clip(start, end, _windows(s[0], q)["pradosha"]) if chosen == 0 else None
    lamps_variant = (
        {
            "date": _date(s[0], q),
            "vara": _vara(s[0], q),
            "rule": "naraka_lamps_divodasiya",
            "pradosha": _span(early, q),
        }
        if early
        else None
    )
    return {
        **day,
        "rule": rule,
        "tithi": _tithi(start, end, q),
        "moonrise": iso(m[chosen], q.tz) if m[chosen] is not None else None,
        "abhyangaSnana": _span(bath, q),
        "arunodaya": _span((rise - ARUNODAYA, rise), q),
        "lamps": _span(_windows(rise, q)["pradosha"], q),
        "lampsVariant": lamps_variant,
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


def _caturthi_choice(days: list[dict]) -> tuple[int, str, int]:
    """NS p. 47 (Brhaspati, "madhyahna-vyapini cet syat paratah, pare 'hani"): the next day
    if the Caturthi reaches its midday, else the earlier, Trtiya-joined day; with DS p. 9's
    stricter day, the later only when it fills the later day's whole midday alone (research,
    16 Oct 2026): (chosen, rule, DS's day)."""
    c0, c1 = (d["madhyahna"]["covered"] for d in days)
    chosen, rule = (1, "next_day_midday") if c1 > 0 else (0, "trtiya_joined_earlier")
    return chosen, rule, 1 if c1 >= 1 and c0 < 1 else 0


def _ganesha(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    base = _base(start, end, 4, q)
    if not _in_month(base, "bhadrapada"):
        return None
    _, days = _days(start, end, q, ("madhyahna",))
    chosen, rule, ds = _caturthi_choice(days)
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "dsEarlier": days[ds]["date"] if ds < chosen else None,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
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
        # DS p. 31: the Pratipada at sunrise; at sunrise on both days or neither, the earlier.
        cov = [start <= s[i] < end for i in range(3)]
        if cov[1]:
            ny, ny_rule, shown = 1, "both_earlier" if cov[2] else "sunrise_one_day", (1, 2)
        else:
            ny, ny_rule, shown = 0, "neither_earlier", (0, 1)
        out["newYearDate"] = _date(s[ny], q)
        out["newYear"] = {
            "date": _date(s[ny], q),
            "rule": ny_rule,
            "days": [
                {"date": _date(s[i], q), "sunrise": iso(s[i], q.tz), "covered": cov[i]}
                for i in shown
            ],
        }
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


# --- Karaka-caturthi, Karva Chauth (NS p. 293; DS pp. 9, 76; VR ff. 81-82) ---------


TITHI_TATTVA = {
    "text": "Tithi-tattva (Raghunandana), quoting the Saṃvatsara-pradīpa",
    "edition": (
        "Raghunandana Bhaṭṭācārya, edited by Jīvānanda Vidyāsāgara, 2nd edition, Nārāyaṇa Press, "
        "Calcutta, 1895"
    ),
    "page": "34",
}
VRATARAJA = {
    "text": "Vratarāja",
    "author": "Viśvanātha",
    "edition": (
        "Viśvanātha, Pothi edition, Bombay, "
        "undated (Internet Archive catalogues it as Khemrāj Śrīkṛṣṇadās, 1897)"
    ),
    "page": "ff. 81–82",
}


def _karva(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """The dark Caturthi ending amanta Ashvina (Kartika krishna purnimanta), current at
    moonrise: at both moonrises the earlier, at neither the later, as for Sankashti
    (NS p. 293; DS pp. 9, 76). VR f. 82 keeps it at nightfall, with the arghya after
    moonrise (f. 81): sunset and moonrise are the sourced times."""
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
    other = row["smarta"]["nearBoundaryDate"]
    near = (dt.date.fromisoformat(other) + dt.timedelta(1)).isoformat() if other else None
    return {
        "lunarMonth": month,
        "tithi": row["tithi"],
        "fastDate": row["smarta"]["date"],
        "date": dates[smarta],
        "vara": _vara(s[smarta], q),
        "rule": "parana_day_early_night",
        "variantDate": dates[vaishnava] if vaishnava != smarta else None,
        "window": _span(_windows(s[smarta], q)["pradosha"], q),
        "cautions": ["near_boundary"] if near else [],
        "nearBoundaryDate": near,
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
    share = [_share(start, end, w) for w in forenoon]
    cov = [x > 0 for x in share]
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
            {"date": _date(s[i], q), **_span(forenoon[i], q), "covered": round(share[i], 3)}
            for i in (0, 1)
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
    dawn_w = (rise - ARUNODAYA, rise)
    # The short Saptami is bathed for at its first arunodaya, in the Shashthi (NS p. 330).
    bath = dawn_w if rule == "shashthi_joined_first_day" else _clip(start, end, dawn_w) or dawn_w
    return {
        **base,
        "days": [
            {
                "date": _date(s[i], q),
                "vara": _vara(s[i], q),
                "arunodaya": {
                    **_span(dawn[i - 1], q),
                    "covered": round(_share(start, end, dawn[i - 1]), 3),
                },
            }
            for i in (1, 2)
        ],
        "date": _date(rise, q),
        "vara": _vara(rise, q),
        "rule": rule,
        "arunodaya": _span(bath, q),
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
        "tarpanaWindow": _span(_clip(start, end, w) or w, q),
    }


# --- Decision 21 (festivals.md s21, 15 Oct 2026) -----------------------------------


def _kalashtami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 84 (decision D4, 16 Oct 2026): NS p. 313's fast on the Ashtami covering
    midday (the 3rd fifth); covering it on both days, wholly or in part, the earlier.
    Covering neither, the day whose sunrise it holds (our reading). DS's own view: the
    earlier day holding it only at pradosha and the later only at midday, the pradosha
    day, with NS's day as variantDate. Otherwise variantDate is the Kaustubha's pradosha
    rule (both days: the later), which DS reports."""
    base = _base(start, end, 23, q)
    if not _in_month(base, "kartika"):
        return None
    _, days = _days(start, end, q, ("madhyahna", "pradosha"))
    chosen, rule, window, variant = _kala_choice(days)
    w = days[chosen]["_w"][window]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[variant]["date"] if variant != chosen else None,
        "popularName": "Kaal Bhairav Jayanti",
        "pujaWindow": _span(_clip(start, end, w) or w, q),
        "vigil": _vigil(start, end, days, q),
    }


def _kala_choice(days: list[dict]) -> tuple[int, str, str, int]:
    """D4's day on the two candidate days (DS pp. 10, 84): (chosen, rule, window, variant)."""
    mid = [d["madhyahna"]["covered"] > 0 for d in days]
    pr = [d["pradosha"]["covered"] > 0 for d in days]
    if pr[0] and not mid[0] and mid[1] and not pr[1]:
        return 0, "pradosha_only_earlier_ds", "pradosha", 1
    if mid[0] != mid[1]:
        chosen, rule = (0 if mid[0] else 1), "midday"
    elif mid[0]:
        chosen, rule = 0, "midday_both_earlier"
    else:
        chosen, rule = 1, "midday_neither_sunrise_day"
    return chosen, rule, "madhyahna", (0 if pr[0] else 1) if pr[0] != pr[1] else 1


def _vigil(start: float, end: float, days: list[dict], q) -> dict:
    """NS pp. 312-313, the night vigil alone: the Ashtami touching a night (sunset to
    sunrise); touching both in part, the later ("dina-dvaye 'mshato ratri-vyaptav
    uttaraiva"); one night wholly covered and the other only touched, the whole one
    (our reading)."""
    share = [_share(start, end, d["_w"]["night"]) for d in days]
    whole = [x >= 1 - 1e-9 for x in share]
    if share[0] > 0 and share[1] > 0:
        if whole[0] != whole[1]:
            k, rule = (0 if whole[0] else 1), "vigil_whole_night"
        else:
            k, rule = 1, "vigil_both_later"
    else:
        k, rule = (0 if share[0] > 0 else 1), "vigil_one_night"
    night = days[k]["_w"]["night"]
    return {
        "date": days[k]["date"],
        "vara": days[k]["vara"],
        "rule": rule,
        "window": _span(_clip(start, end, night), q),
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
    _, days = _days(start, end, q, ("madhyahna", "pradosha"))
    if days[1]["madhyahna"]["covered"] > 0:
        chosen, rule = 1, "next_day_midday"
    else:
        chosen, rule = 0, "trtiya_joined_earlier"
    # The Tila or Varada night vow takes the Caturthi covering pradosha (DS p. 89); on
    # both days the earlier, Trtiya-joined (DS p. 9), on neither the later (our reading).
    pr = [d["pradosha"]["covered"] > 0 for d in days]
    if pr[0] != pr[1]:
        v, v_rule = (0 if pr[0] else 1), "vow_pradosha"
    elif pr[0]:
        v, v_rule = 0, "vow_pradosha_both_earlier"
    else:
        v, v_rule = 1, "vow_pradosha_neither_later"
    w = days[v]["_w"]["pradosha"]
    mid = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "popularName": "Ganesh Jayanti",
        "pujaWindow": _span(_clip(start, end, mid) or mid, q),
        "vow": {
            "date": days[v]["date"],
            "vara": days[v]["vara"],
            "rule": v_rule,
            "window": _span(_clip(start, end, w) or w, q),
        },
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
    """DS p. 36 (decision D3, 15 Oct 2026): the Vaishakha shukla Tritiya covering the
    forenoon; on both days, the later only if the Tritiya lasts more than three
    day-muhurtas into it, else the earlier. variantDate is NS p. 134's day (VR f. 43):
    on both days, the later. Covering neither forenoon: the later (our reading)."""
    base = _base(start, end, 3, q)
    if not _in_month(base, "vaishakha"):
        return None
    s, days = _days(start, end, q, ())
    fore = [_forenoon(s[i], q) for i in (0, 1)]
    cov = [_share(start, end, w) > 0 for w in fore]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "forenoon"
    elif cov[0]:
        long = end - s[1] > 3 * _muhurta(s[1], q)
        chosen, rule = (1, "forenoon_both_three_muhurtas") if long else (0, "forenoon_both_earlier")
    else:
        chosen, rule = 1, "forenoon_neither_later"
    ns = 1 if all(cov) else chosen  # NS p. 134: on both days, the later
    strip = _strip(days)
    for d, w in zip(strip, fore, strict=True):
        d["forenoon"] = {**_span(w, q), "covered": round(_share(start, end, w), 3)}
    return {
        **base,
        "days": strip,
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[ns]["date"] if ns != chosen else None,
        "pujaWindow": _span(_clip(start, end, fore[chosen]) or fore[chosen], q),
    }


def _parashurama(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 37 (VR f. 43): the Tritiya covering the night's first watch (a quarter
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
    pr = days[chosen]["_w"]["pradosha"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "firstWatch": _span(_clip(start, end, watch[chosen]) or watch[chosen], q),
        "arghyaWindow": _span(_clip(start, end, pr) or pr, q),
    }


def _guru_purnima(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 160, DS p. 43: the Vyasa-puja of ascetics on the Ashadha Purnima, on the
    later day if the Purnima lasts three muhurtas or more after its sunrise, otherwise
    the earlier, Caturdashi-joined day (DS p. 20). The worship is in the morning (the
    1st fifth of the daytime, our reading of NS p. 28). Decision 29 (16 Oct 2026): when
    the Purnima holds the later sunrise for less than three muhurtas, that sunrise day is
    variantDate, as popular practice (caution popular_sunrise_day)."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "ashadha"):
        return None
    s, days = _days(start, end, q, ())
    muhurta = (_sunset(s[1], q) - s[1]) / 15
    held = start <= s[1] < end
    if held and end - s[1] >= 3 * muhurta:
        chosen, rule = 1, "three_muhurtas_later"
    else:
        chosen, rule = 0, "caturdashi_joined_earlier"
    popular = held and chosen == 0
    sr = s[chosen]
    morning = (sr, sr + (_sunset(sr, q) - sr) / 5)
    strip = _strip(days)
    for i, d in enumerate(strip):  # the first fifth: the three day-muhurtas the rule tests
        w = (s[i], s[i] + 3 * _muhurta(s[i], q))
        d["morning"] = {**_span(w, q), "covered": round(_share(start, end, w), 3)}
    return {
        **base,
        "days": strip,
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[1]["date"] if popular else None,
        "variantBasis": "popular_practice" if popular else None,
        "cautions": ["popular_sunrise_day"] if popular else [],
        "popularName": "Guru Purnima",
        "displayName": "Vyāsa-pūjā",
        "pujaWindow": _span(_clip(start, end, morning) or morning, q),
    }


# --- Decision 26: seo's April to September list (festivals.md s26, 15 Oct 2026) -------

PUSHYA, HASTA = 7, 12  # nakshatra indexes, Ashvini = 0
VYATIPATA = 16  # yoga index, the 17th
VRISHABHA, KANYA = 1, 5  # sign indexes, Mesha = 0
GANGA_YOGAS = (
    "jyeshtha", "shukla", "dashami", "wednesday", "hasta",
    "vyatipata", "gara", "ananda", "moon_kanya", "sun_vrishabha",
)  # fmt: skip
TEEJ = {  # kind: (popular name, the name in NS p. 197)
    "hariyali-teej": ("Hariyali Teej", "Madhuśrāvaṇikā"),
    "kajari-teej": ("Kajari Teej", "Kajjalī"),
    "hartalika-teej": ("Hartalika Teej", "Haritālikā"),
}


def _muhurta(sr: float, q) -> float:
    """A day-muhurta: a fifteenth of the daytime."""
    return (_sunset(sr, q) - sr) / 15


def _held(start: float, end: float, s: list[float]) -> list[int]:
    """The sunrises after s[0] that the tithi holds."""
    return [i for i in range(1, len(s)) if start <= s[i] < end]


def _vat_savitri(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS pp. 146-148, DS p. 41: the three-night Savitri vow on the Caturdashi-joined day,
    the exception to the later-day rule for a Purnima or Amavasya fast (NS p. 147), when
    the tithi runs more than three muhurtas before that day's sunset; with less, the later
    day (DS). The nights are that day and the two before it, the parana at the tithi's end
    (NS p. 148). The Amavasya form (the Nirnayamrta, NS p. 147) keeps the same rule on the
    new moon ending amanta Vaishakha, the dark fortnight of purnimanta Jyeshtha (our
    reading). Neither form in an adhika month (DS p. 4). The date is DS's puja-only day
    (decision D1, 15 Oct 2026): the later day when the Caturdashi lasts 18 nadis or more
    after the fast day's sunrise, else the fast day, which is then fastDate; the Amavasya
    form takes it through NS p. 148, "ayam nirnayo 'mayam api jneyah" (our reading)."""
    num = Mu.tithi_at((start + end) / 2, q.ayanamsa)
    base = _base(start, end, num, q)
    if not _in_month(base, "jyeshtha" if num == 15 else "vaishakha"):
        return None
    s = _sunrises(start, q.lat, q.lon, 2)  # s[0] <= start < s[1]
    before = max(0.0, _sunset(s[0], q) - start)
    mu = _muhurta(s[0], q)
    if before > 3 * mu:
        k, rule = 0, "caturdashi_joined"
    else:
        k, rule = 1, "under_three_muhurtas_later"
    puja = 1 if k == 0 and start - s[0] >= 18 * DANDA else k
    if puja != k:
        rule = "puja_only_later"
    fast = dt.date.fromisoformat(_date(s[k], q))
    return {
        **base,
        "form": "purnima" if num == 15 else "amavasya",
        "date": _date(s[puja], q),
        "vara": _vara(s[puja], q),
        "rule": rule,
        "fastDate": fast.isoformat() if puja != k else None,
        "muhurtasBeforeSunset": round(before / mu, 2),
        "caturdashiNadis": round((start - s[0]) / DANDA, 1),
        "nights": [(fast - dt.timedelta(days=i)).isoformat() for i in (2, 1, 0)],
        "paranaAfter": iso(end, q.tz),
    }


def _ganga_yogas(a: float, b: float, vara: str, q) -> list[str]:
    """The ten yogas (NS p. 144, DS p. 38) that meet the Dashami in [a, b], its part of a
    forenoon (our reading of DS's "the Dashami with some yogas, in the forenoon"). The
    month, the fortnight and the tithi hold throughout."""
    ay = q.ayanamsa

    def meets(fn, value) -> bool:
        return bool(_spans(fn, value, a, b, 1 / 24))

    hasta = meets(lambda t: Mu.nakshatra_at(t, ay), HASTA)
    wednesday = vara == "wednesday"
    found = {
        "jyeshtha": True,
        "shukla": True,
        "dashami": True,
        "wednesday": wednesday,
        "hasta": hasta,
        "vyatipata": meets(lambda t: Mu.yoga_at(t, ay), VYATIPATA),
        "gara": meets(lambda t: Mu.karana_at(t, ay), "Gara"),
        "ananda": wednesday and hasta,  # DS p. 38: Wednesday with Hasta is Ananda
        "moon_kanya": meets(lambda t: luminaries(t, ay)[1].sign, KANYA),
        "sun_vrishabha": meets(lambda t: luminaries(t, ay)[0].sign, VRISHABHA),
    }
    return [k for k in GANGA_YOGAS if found[k]]


def _ganga(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS pp. 143-146, DS pp. 38-39: the Jyeshtha shukla Dashami in the forenoon (sunrise
    to midday, DS); in both forenoons, the day with more of the ten yogas (NS p. 144), DS
    naming the Dashami and Vyatipata chief. A tie goes to the day with Vyatipata, else to
    the day with the Dashami at sunrise (our reading). An adhika Jyeshtha keeps it, and
    the pure month then does not (NS p. 144; DS p. 38)."""
    base = _base(start, end, 10, q)
    month = base["lunarMonth"]
    if month["amanta"] != "jyeshtha":
        return None
    prev = Mu.lunar_month(start - 29, q.ayanamsa)
    if not month["adhika"] and prev.adhika and prev.name == "Jyeshtha":
        return None
    s, days = _days(start, end, q, ())
    fore = [_forenoon(s[i], q) for i in (0, 1)]
    held = [_clip(start, end, w) for w in fore]
    yogas = [_ganga_yogas(*w, d["vara"], q) if w else [] for w, d in zip(held, days, strict=True)]
    if held[0] and held[1]:
        n = [len(y) for y in yogas]
        vy = ["vyatipata" in y for y in yogas]
        if n[0] != n[1]:
            chosen, rule = (0 if n[0] > n[1] else 1), "forenoon_both_more_yogas"
        elif vy[0] != vy[1]:
            chosen, rule = (0 if vy[0] else 1), "forenoon_both_tie_vyatipata"
        else:
            chosen, rule = 1, "forenoon_both_tie_sunrise"
    else:
        chosen, rule = (0 if held[0] else 1), "forenoon"
    return {
        **base,
        "days": [
            {
                "date": d["date"],
                "vara": d["vara"],
                "forenoon": {**_span(fore[i], q), "covered": round(_share(start, end, fore[i]), 3)},
                "yogas": yogas[i],
            }
            for i, d in enumerate(days)
        ],
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "yogas": yogas[chosen],
        "pujaWindow": _span(held[chosen], q),
    }


def _rath(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """NS p. 149, quoting the Skanda in the Tithi-tattva: the chariot festival on the
    Ashadha shukla Dvitiya joined with Pushya, or on the tithi alone. The day is the
    Dvitiya at sunrise, Trtiya-joined as the paired-tithi rule pairs them; at two sunrises
    the first (our reading, matched to prevailing practice: decision D2, 15 Oct 2026), at
    none the day it falls on (our reading)."""
    base = _base(start, end, 2, q)
    if not _in_month(base, "ashadha"):
        return None
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    held = _held(start, end, s)
    if not held:
        k, rule = 0, "no_sunrise_day_it_falls_on"
    else:
        k, rule = held[0], "two_sunrises_first" if len(held) == 2 else "sunrise_tritiya_joined"
    pushya = _spans(lambda t: Mu.nakshatra_at(t, q.ayanamsa), PUSHYA, start, end, 0.1)
    return {
        **base,
        "date": _date(s[k], q),
        "vara": _vara(s[k], q),
        "rule": rule,
        "pushya": _span(pushya[0], q) if pushya else None,
    }


def _sawan(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """DS p. 44: the Monday vow of Shravana, a fast for those able, otherwise one meal at
    night. A Monday counts when its sunrise falls in Shravana, purnimanta (North India,
    from the dark fortnight after the Ashadha Purnima) or amanta (from the day after the
    Ashadha Amavasya). Both lists, with each month's first and last day."""
    ay = q.ayanamsa
    sr = _rise_set(local_jd(dt.date(q.year, 6, 1), 0.0, q.tz, "year"), q.lat, q.lon, True)
    stop = local_jd(dt.date(q.year, 10, 31), 0.0, q.tz, "year")
    months: list = []
    dates: dict[str, list[str]] = {"purnimanta": [], "amanta": []}
    rows = []
    while sr < stop:
        month = next((m for m in months if m.start <= sr < m.end), None)
        if month is None:
            month = Mu.lunar_month(sr, ay)
            months.append(month)
        num = Mu.tithi_at(sr, ay)
        masa = Mu.MASA.index(month.name)
        names = {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if num > 15 else MASA_IDS[masa],
        }
        systems = [k for k in ("purnimanta", "amanta") if names[k] == "shravana"]
        date = _date(sr, q)
        for k in systems:
            dates[k].append(date)
        if systems and _vara(sr, q) == "monday":
            rows.append(
                {
                    "date": date,
                    "vara": "monday",
                    "rule": "shravana_monday",
                    "lunarMonth": {**names, "adhika": month.adhika},
                    "tithiAtSunrise": tithi_id(num),
                    "paksha": "shukla" if num <= 15 else "krishna",
                    "systems": systems,
                }
            )
        sr = _rise_set(sr + 0.1, q.lat, q.lon, True)
    return rows, {k: {"start": v[0], "end": v[-1]} if v else None for k, v in dates.items()}


def _teej(
    start: float, end: float, _next: float, q: EkadashiQuery, kind: str, month: str
) -> dict | None:
    """NS p. 197 (Divodasa): the women's Tritiyas, each kept Caturthi-joined, on the later
    day even with a muhurta or less of Tritiya (Madhava, NS p. 197; DS p. 55): the last day
    whose sunrise has it. A Tritiya touching no sunrise: the day it runs, Dvitiya-joined
    (DS p. 55). Kajari is the Bhadrapada dark Tritiya counted purnimanta (our reading)."""
    num = Mu.tithi_at((start + end) / 2, q.ayanamsa)
    base = _base(start, end, num, q)
    if not _in_month(base, month):
        return None
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    held = _held(start, end, s)
    if not held:
        k, rule = 0, "kshaya_dvitiya_joined"
    else:
        k, rule = held[-1], "two_sunrises_later" if len(held) == 2 else "sunrise_caturthi_joined"
    popular, textual = TEEJ[kind]
    return {
        **base,
        "date": _date(s[k], q),
        "vara": _vara(s[k], q),
        "rule": rule,
        "muhurtasAfterSunrise": round((end - s[k]) / _muhurta(s[k], q), 2) if held else None,
        "popularName": popular,
        "displayName": textual,
    }


def _naga(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 44 (NS p. 164: the later, Shashthi-joined Panchami). P is the Panchami's
    length after the later sunrise and C the Caturthi's after the earlier, in day-muhurtas:
    P of three or more, the later day; P under three with C up to three, the earlier; P of
    two to three with C over three, the later; P under two with C over three, the earlier
    (DS rejects one of a muhurta; under two is our reading). Touching no sunrise, the day
    it runs; two sunrises, the later (NS)."""
    base = _base(start, end, 5, q)
    if not _in_month(base, "shravana"):
        return None
    s = _sunrises(start, q.lat, q.lon, 3)  # s[0] <= start < s[1]
    held = _held(start, end, s)
    c = (start - s[0]) / _muhurta(s[0], q)
    p = (end - s[held[-1]]) / _muhurta(s[held[-1]], q) if held else None
    if p is None:
        k, rule = 0, "no_sunrise_day_it_runs"
    elif len(held) == 2:
        k, rule = 2, "two_sunrises_later"
    elif p >= 3:
        k, rule = 1, "three_muhurtas_later"
    elif c <= 3:
        k, rule = 0, "both_short_earlier"
    elif p >= 2:
        k, rule = 1, "long_caturthi_later"
    else:
        k, rule = 0, "under_two_muhurtas_earlier"
    return {
        **base,
        "date": _date(s[k], q),
        "vara": _vara(s[k], q),
        "rule": rule,
        "muhurtas": {"panchami": round(p, 2) if p is not None else None, "caturthi": round(c, 2)},
    }


def _rishi(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 55: the Bhadrapada shukla Panchami covering midday (the 3rd fifth); on both
    days or neither, the earlier."""
    base = _base(start, end, 5, q)
    if not _in_month(base, "bhadrapada"):
        return None
    _, days = _days(start, end, q, ("madhyahna",))
    cov = [d["madhyahna"]["covered"] > 0 for d in days]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "midday"
    else:
        chosen, rule = 0, "midday_both_earlier" if cov[0] else "midday_neither_earlier"
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


def _ananta(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """DS p. 58: the Bhadrapada shukla Caturdashi at sunrise lasting three muhurtas, failing
    that two; under two, the earlier day; at sunrise on both days, the earlier, as the
    complete one. Worship in the forenoon, else at midday. variantDate is NS p. 211's day,
    the Caturdashi covering midday (the 3rd fifth) on either day; on both, the day with
    more of it, the earlier when equal (our reading)."""
    base = _base(start, end, 14, q)
    if not _in_month(base, "bhadrapada"):
        return None
    s, days = _days(start, end, q, ("madhyahna",), 3)
    held = _held(start, end, s)
    after = (end - s[1]) / _muhurta(s[1], q) if held else None
    if not held:
        k, rule = 0, "no_sunrise_only_day"
    elif len(held) == 2:
        k, rule = 1, "sunrise_both_earlier"
    elif after >= 3:
        k, rule = 1, "sunrise_three_muhurtas"
    elif after >= 2:
        k, rule = 1, "sunrise_two_muhurtas"
    else:
        k, rule = 0, "under_two_muhurtas_earlier"
    mid = [d["madhyahna"]["covered"] for d in days]
    ns = max(range(len(days)), key=lambda i: (mid[i], -i))
    window = _clip(start, end, _forenoon(s[k], q)) or _clip(start, end, days[k]["_w"]["madhyahna"])
    return {
        **base,
        "days": _strip(days[: 3 if len(held) == 2 else 2]),
        "date": days[k]["date"],
        "vara": days[k]["vara"],
        "rule": rule,
        "variantDate": days[ns]["date"] if mid[ns] > 0 and ns != k else None,
        "muhurtasAfterSunrise": round(after, 2) if after is not None else None,
        "pujaWindow": _span(window, q),
    }


# --- Bengal Durga-puja by the Tithi-tattva (festivals.md s22) ------------------------

MOVABLE = {0, 3, 6, 9}  # Aries, Cancer, Libra, Capricorn


def _udaya(n: int, spans: dict, s: list[float], q) -> list[int]:
    """TT pp. 87-89: the sunrises a tithi holds for at least a day-muhurta after them
    ("ghatika" read as a muhurta, TT's own gloss)."""
    a, b = spans[n]
    return [k for k, sr in enumerate(s) if a <= sr and b - sr >= (_sunset(sr, q) - sr) / 15]


def _falls_in(t: float, s: list[float]) -> int:
    return max(k for k, sr in enumerate(s) if sr <= t)


def _movable(a: float, b: float, q) -> list[dict]:
    """Stretches of [a, b] with a movable lagna or a movable navamsa (TT p. 89)."""
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


# Research, 17 Oct 2026: Durga-puja's days are keyed to Kolkata for every city. The acts,
# NS/DS's Navami and the one-ghatika caution are Kolkata's; instants are shown in the
# city's own time; the forenoon and evening rites fall in the city's own forenoon and
# twilight on the Kolkata day; localRuleDate is the day the city's own sunrise would give.
KOLKATA = {"name": "Kolkata", "lat": 22.5726, "lon": 88.3639, "tz": "Asia/Kolkata"}
DURGA_ACT_TITHI = {"bodhana": 6, "amantrana": 7, "patrikaPravesha": 7, "mahashtami": 8,
                   "mahanavami": 9, "visarjana": 10}  # fmt: skip


def _durga_forenoon(sr: float, q) -> tuple[float, float]:
    return sr, (sr + _sunset(sr, q)) / 2


def _durga_twilight(sr: float, q) -> tuple[float, float]:
    """Bodhana's evening twilight: three ghatis after sunset (our reading of TT p. 75)."""
    ss = _sunset(sr, q)
    return ss, ss + 3 * DANDA


def _durga_acts(sp: dict, s: list[float], q) -> dict[str, tuple[int, str | None]]:
    """Each act's day (an index into the sunrises s at q's place) and rule, for the tithi
    spans sp. Every act on the tithi current at sunrise for a muhurta (TT pp. 87-89)."""
    # The leaf entry: the sunrise Saptami, in the forenoon; a lost Saptami goes to the
    # Shashthi-joined day it falls on (p. 89).
    held = _udaya(7, sp, s, q)
    leaf = (
        (held[0], "sunrise_saptami") if held else (_falls_in(sp[7][0], s), "kshaya_shashthi_joined")
    )
    # Mahashtami: the sunrise Ashtami; the complete first day when it holds two (p. 88).
    held = _udaya(8, sp, s, q)
    if len(held) >= 2:
        ashtami = (held[0], "complete_first_day")
    elif held:
        ashtami = (held[0], "sunrise_ashtami")
    else:
        ashtami = (_falls_in(sp[8][0], s), "kshaya_day_it_falls_on")
    held = _udaya(9, sp, s, q)
    navami = (
        (held[0], "sunrise_navami") if held else (_falls_in(sp[9][0], s), "kshaya_day_it_falls_on")
    )
    # The Dashami lasting under a muhurta after sunrise sends the immersion to the day
    # before (p. 89).
    held = _udaya(10, sp, s, q)
    dashami = (
        (held[0], "sunrise_dashami")
        if held
        else (_falls_in(sp[10][0], s), "short_dashami_day_before")
    )
    # Bodhana (p. 75): the Shashthi in the evening twilight; the evening before the leaf
    # entry holds both rites if it has it.
    eve = leaf[0] - 1
    covered = [k for k in range(0, leaf[0]) if _share(*sp[6], _durga_twilight(s[k], q)) > 0]
    if eve >= 0 and eve in covered:
        bodhana = (eve, "evening_before_leaf_entry")
    elif covered:
        bodhana = (covered[0], "shashthi_evening")
    else:  # the Shashthi touches neither evening: the later day's forenoon Shashthi
        bodhana = (1 if _clip(*sp[6], _durga_forenoon(s[1], q)) else 0, "neither_evening_forenoon")
    return {"bodhana": bodhana, "amantrana": (max(eve, 0), None), "patrikaPravesha": leaf,
            "mahashtami": ashtami, "mahanavami": navami, "visarjana": dashami}  # fmt: skip


@lru_cache(maxsize=32)
def _durga_kolkata(year: int, start: float, end: float, ayanamsa: str) -> dict:
    """The Kolkata reckoning of one Ashvina shukla Shashthi: the tithi spans, Kolkata's
    sunrises, each act's day and rule with its one-ghatika caution, and NS/DS's Navami."""
    kq = EkadashiQuery(year=year, lat=KOLKATA["lat"], lon=KOLKATA["lon"], tz=KOLKATA["tz"],
                       ayanamsa=ayanamsa)  # fmt: skip
    spans = {6: (start, end)}
    t = end
    for n in (7, 8, 9, 10):
        nxt = _edge(t, kq, True)
        spans[n] = (t, nxt)
        t = nxt
    s = _sunrises(start, kq.lat, kq.lon, 9)  # s[0] <= start
    own = _durga_acts(spans, s, kq)
    # The one-ghatika caution (as decision 28's): any act a 24-minute shift of a tithi
    # boundary, Shashthi to Dashami, would move carries the other day, and which boundary
    # moves it by how many minutes (research, 17 Oct 2026). edges[i] starts tithi 6 + i.
    edges = [spans[6][0], *(spans[n][1] for n in range(6, 11))]

    def acts_at(i: int, shift: float) -> dict[str, tuple[int, str | None]]:
        e = edges.copy()
        e[i] += shift
        return _durga_acts({n: (e[n - 6], e[n - 5]) for n in range(6, 11)}, s, kq)

    moved: dict[str, list[tuple[int, int]]] = {k: [] for k in own}  # (edge, direction)
    for i in range(len(edges)):
        for sign in (-1, 1):
            for k, (idx, _) in acts_at(i, sign * DANDA).items():
                if idx != own[k][0]:
                    moved[k].append((i, sign))

    def margin(k: str) -> dict:
        if not moved[k]:
            return {"cautions": [], "variantDate": None, "margin": None}
        best = None
        for i, sign in moved[k]:
            lo, hi = 0.0, DANDA  # the smallest shift that moves the act, to the second
            while hi - lo > 1 / 86400:
                mid = (lo + hi) / 2
                lo, hi = (lo, mid) if acts_at(i, sign * mid)[k][0] != own[k][0] else (mid, hi)
            if best is None or hi < best[0]:
                best = (hi, i, acts_at(i, sign * hi)[k][0])
        minutes, i, other = best
        n = DURGA_ACT_TITHI[k]
        tithi, boundary = (n, "end") if i == n - 5 else (6 + i, "start")
        return {
            "cautions": ["tithi_ghatika_margin"],
            "variantDate": _date(s[other], kq),
            "margin": {
                "tithi": tithi_id(tithi),
                "boundary": boundary,
                "minutes": round(minutes * 1440),
            },
        }

    navami = own["mahanavami"][0]
    _, ns_navami = _ashtami_navami({8: spans[8], 9: spans[9]}, kq)
    ns_date = ns_navami["date"] if ns_navami["date"] != _date(s[navami], kq) else None
    return {"kq": kq, "spans": spans, "s": s, "own": own, "ns_date": ns_date,
            "margins": {k: margin(k) for k in own}}  # fmt: skip


def _durga_puja(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """The Tithi-tattva's Durga-puja (pp. 73-92), keyed on the Ashvina shukla Shashthi and
    reckoned at Kolkata for every city (research, 17 Oct 2026). Every act on the tithi
    current at sunrise for a muhurta (pp. 87-89): the leaf entry on the Saptami's forenoon,
    Mahashtami (the complete first day when the Ashtami holds two sunrises), the sandhi of
    48 minutes, Mahanavami on the sunrise Navami and the immersion on the sunrise Dashami's
    forenoon, the last two in a movable lagna or navamsa (p. 89). Bodhana in the Shashthi's
    evening twilight (pp. 73-75). Each act carries the one-ghatika caution (the lead) and
    localRuleDate, the day the city's own sunrise would give (research)."""
    base = _base(start, end, 6, q)
    if not _in_month(base, "ashwin"):
        return None
    k = _durga_kolkata(q.year, start, end, q.ayanamsa)
    kq, spans, ks, own = k["kq"], k["spans"], k["s"], k["own"]
    home = abs(q.lat - KOLKATA["lat"]) < 0.05 and abs(q.lon - KOLKATA["lon"]) < 0.05
    ls = _sunrises(start, q.lat, q.lon, 9)
    local = _durga_acts(spans, ls, q)

    def day(key: str) -> dict:
        i = own[key][0]
        date = _date(ks[i], kq)
        mine = _date(ls[local[key][0]], q)
        return {
            "date": date,
            "vara": _vara(ks[i], kq),
            "localRuleDate": mine if mine != date else None,
        }

    def sunrise_on(key: str) -> float:
        """The requested city's sunrise on the act's Kolkata date."""
        d = dt.date.fromisoformat(_date(ks[own[key][0]], kq))
        return _sunrises(local_jd(d, 12.0, q.tz, "year"), q.lat, q.lon, 1)[0]

    def forenoon(key: str, *tithis: int) -> tuple[float, float] | None:
        w = _durga_forenoon(sunrise_on(key), q)
        if not home:  # the city's own forenoon on the Kolkata day, no tithi asserted
            return w
        return next((c for n in tithis if (c := _clip(*spans[n], w))), None)

    leaf_rule, a_rule = own["patrikaPravesha"][1], own["mahashtami"][1]
    leaf_w = forenoon("patrikaPravesha", 7)
    imm_w = forenoon("visarjana", 10, 9)
    shravana = bool(imm_w) and SHRAVANA in {Mu.nakshatra_at(x, q.ayanamsa) for x in imm_w}
    b_rule = own["bodhana"][1]
    if b_rule == "neither_evening_forenoon":
        b_w = forenoon("bodhana", 6)
    else:
        b_w = _durga_twilight(sunrise_on("bodhana"), q)
    junction = spans[8][1]
    ashtami = own["mahashtami"][0]
    m = copy.deepcopy(k["margins"])  # the cached reckoning is shared across calls
    return {
        **base,
        "date": _date(ks[ashtami], kq),
        "vara": _vara(ks[ashtami], kq),
        "rule": a_rule,
        "bodhana": {**day("bodhana"), "rule": b_rule, **(_span(b_w, q) or {}), **m["bodhana"]},
        "amantrana": {**day("amantrana"), **_span(_durga_twilight(sunrise_on("amantrana"), q), q),
                      **m["amantrana"]},
        "patrikaPravesha": {**day("patrikaPravesha"), "rule": leaf_rule,
                            "forenoon": _span(leaf_w, q),
                            "movableWindows": _movable(*leaf_w, q) if leaf_w else [],
                            **m["patrikaPravesha"]},
        "mahashtami": {**day("mahashtami"), "rule": a_rule, **m["mahashtami"]},
        "sandhiPuja": _span((junction - DANDA, junction + DANDA), q),
        "mahanavami": {**day("mahanavami"), "rule": own["mahanavami"][1], "nsDsDate": k["ns_date"],
                       **m["mahanavami"]},
        "visarjana": {**day("visarjana"), "rule": own["visarjana"][1], "forenoon": _span(imm_w, q),
                      "movableWindows": _movable(*imm_w, q) if imm_w else [], "shravana": shravana,
                      **m["visarjana"]},
    }  # fmt: skip


# --- Popular practice (festivals.md s27, decision 27, 15 Oct 2026) --------------------
# No text read gives these days: each rule is ours, stated from common practice, and
# every answer carries basis: "popular_practice".

ONAM_NADIKAS = 6 * DANDA  # 2 h 24 min of Shravana after sunrise
LEO = 4


def _chhath_day(start: float, end: float, s: list[float], sets: list[float]):
    """Decision 28: the first day whose sunrise holds the Shashthi; holding none, the day
    whose sunset falls in it (a tithi is never short enough to hold neither)."""
    inside = [i for i in range(3) if start <= sets[i] < end]
    held = [i for i in range(3) if start <= s[i] < end]
    if held:
        k = held[0]
        two = len(inside) > 1 and inside[-1] == k
        return k, "two_sunsets_later" if two else "sunrise_holds_shashthi"
    return (inside[0] if inside else 1), "sunset_in_shashthi"


def _chhath(
    start: float, end: float, _next: float, q: EkadashiQuery, month: str = "kartika"
) -> dict | None:
    """s27.1 as decision 28 (16 Oct 2026) corrected it: the evening arghya on the first
    day whose sunrise holds the Kartika shukla Shashthi, else the day whose sunset falls
    in it; two sunsets in it give the later, whose sunrise holds it. Where moving the
    Shashthi's start or end one ghatika either way changes the day, that other day is
    variantDate (caution ghatika_margin, the lead's wording of 16 Oct 2026). The morning arghya
    at the next sunrise; Kharna and nahay-khay the two days before. The spring Chhath
    takes the Caitra shukla Shashthi by the same rule."""
    base = _base(start, end, 6, q)
    if not _in_month(base, month):
        return None
    s = _sunrises(start, q.lat, q.lon, 4)  # s[0] <= start < s[1]
    sets = [_sunset(s[i], q) for i in range(3)]
    k, rule = _chhath_day(start, end, s, sets)
    moved = (
        (start - DANDA, end),
        (start + DANDA, end),
        (start, end - DANDA),
        (start, end + DANDA),
    )
    other = sorted({_chhath_day(a, b, s, sets)[0] for a, b in moved} - {k})
    day = lambda i: {"date": _date(s[i], q), "vara": _vara(s[i], q)}  # noqa: E731
    before = [
        _sunrises(s[k] - 1.5, q.lat, q.lon, 2)[0],  # two days before
        _sunrises(s[k] - 0.5, q.lat, q.lon, 2)[0],  # the day before
    ]
    return {
        **base,
        **day(k),
        "rule": rule,
        "variantDate": _date(s[other[0]], q) if other else None,
        "cautions": ["ghatika_margin"] if other else [],
        "set": {
            "nahayKhay": {"date": _date(before[0], q), "vara": _vara(before[0], q)},
            "kharna": {"date": _date(before[1], q), "vara": _vara(before[1], q)},
            "sandhyaArghya": {**day(k), "sunset": iso(sets[k], q.tz)},
            "ushaArghya": {**day(k + 1), "sunrise": iso(s[k + 1], q.tz)},
        },
    }


def _hanuman(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s27.2: the Caitra Purnima on the site's own Purnima-vrata day (observances s5)."""
    base = _base(start, end, 15, q)
    if not _in_month(base, "chaitra"):
        return None
    vrata = _full_or_new(start, end, _next, q)["vrata"]
    return {**base, "date": vrata["date"], "vara": vrata["vara"], "rule": "purnima_vrata_day"}


def _radhashtami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s27.3: the Bhadrapada shukla Ashtami covering midday (the 3rd fifth) on one day:
    that day; both or neither, the later, whose sunrise holds the Ashtami."""
    base = _base(start, end, 8, q)
    if not _in_month(base, "bhadrapada"):
        return None
    _, days = _days(start, end, q, ("madhyahna",))
    cov = [d["madhyahna"]["covered"] > 0 for d in days]
    if cov[0] != cov[1]:
        chosen, rule = (0 if cov[0] else 1), "midday_one_day"
    else:
        chosen, rule = 1, "midday_both_later" if cov[0] else "midday_neither_later"
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


def _star_day(a: float, b: float, rises: list[float]) -> tuple[float, str]:
    """The day a nakshatra span [a, b) is kept, by s27.4's test: the sunrise in it with 6
    nadikas of it left, the later when two qualify (research, 16 Oct 2026); else, if it
    holds a sunrise with less, the day before; holding none, the day it falls in (our
    reading)."""
    held = [sr for sr in rises if a <= sr < b]
    if ok := [sr for sr in held if b - sr >= ONAM_NADIKAS]:
        return ok[-1], "sunrise_six_nadikas"
    if held:
        return rises[rises.index(held[0]) - 1], "short_day_before"
    return max(x for x in rises if x <= a), "no_sunrise_day_it_falls_in"


def _onam(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s27.4: Chingam's days are those with the sidereal Sun in Simha at sunrise. Onam
    (Tiruvonam) is the Chingam day whose sunrise falls in Shravana with 6 nadikas of it
    left; with less, the day before; with no sunrise in it, the day it falls in (our
    reading). Two Tiruvonams in one Chingam are both shown, neither picked. Atham, the
    festival's opening, is the Hasta before each Tiruvonam by the same test, in Chingam or
    late Karkataka (our reading; popular practice: research's ruling of 16 Oct 2026)."""
    ay = q.ayanamsa
    t0 = local_jd(dt.date(q.year, 7, 15), 0.0, q.tz, "year")
    t1 = local_jd(dt.date(q.year, 10, 1), 0.0, q.tz, "year")
    rises = _sunrises(t0, q.lat, q.lon, int(t1 - t0) + 2)
    chingam = [sr for sr in rises if luminaries(sr, ay)[0].sign == LEO]
    if not chingam:
        return [], {"chingam": None}
    first, last = chingam[0], chingam[-1]
    nak = lambda t: Mu.nakshatra_at(t, ay)  # noqa: E731
    rows = []
    for a, b in _spans(nak, SHRAVANA, first - 1.2, last + 1.2, 0.1):
        sr, rule = _star_day(a, b, rises)
        if first <= sr <= last:
            ha, hb = _spans(nak, HASTA, a - 12, a, 0.1)[-1]  # the Hasta before (7.8-10.2 days)
            hr, h_rule = _star_day(ha, hb, rises)
            h_rule = "atham_" + h_rule
            rows.append(
                {
                    "date": _date(sr, q),
                    "vara": _vara(sr, q),
                    "rule": rule,
                    "shravana": _span((a, b), q),
                    "atham": {
                        "date": _date(hr, q),
                        "vara": _vara(hr, q),
                        "rule": h_rule,
                        "hasta": _span((ha, hb), q),
                    },
                }
            )
    if len(rows) > 1:
        for r in rows:
            r["twoTiruvonam"] = True
    span = {"start": _date(first, q), "end": _date(last, q)}
    return rows, {"chingam": span}


def _vishwakarma(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s27.5: the day of the Kanya sankranti's punyakala, as /observances/sankranti
    computes it (sankranti.md)."""
    from .sankranti import sankranti  # sankranti imports observances, as this does

    rows = []
    for r in sankranti(q)["sankrantis"]:
        if r["sign"] == "virgo":
            rows.append(
                {
                    "date": r["date"],
                    "vara": r["vara"],
                    "rule": "kanya_sankranti_punyakala",
                    "sankranti": {k: r[k] for k in ("at", "rule", "punyakala")},
                }
            )
    return rows, {}


# --- Karthigai Deepam (festivals.md s29, decision 32, 16 Oct 2026) ----------------------

TIRUVANNAMALAI = {"name": "Tiruvannamalai", "lat": 12.2253, "lon": 79.0747, "tz": "Asia/Kolkata"}
KRITTIKA, SCORPIO, SAGITTARIUS = 2, 7, 8  # nakshatra and sign indexes from 0


def _at(place: dict, q: EkadashiQuery) -> EkadashiQuery:
    """The query moved to a festival's one regional place, for every city (the lead)."""
    return EkadashiQuery(
        year=q.year, lat=place["lat"], lon=place["lon"], tz=place["tz"], ayanamsa=q.ayanamsa
    )


def _ingress(sign: int, t0: float, t1: float, q) -> float:
    """The moment in [t0, t1] that the sidereal Sun enters `sign`."""
    edges = Mu._scan(lambda t: luminaries(t, q.ayanamsa)[0].sign, t0, t1, 1.0)
    return next(t for t, s in edges if s == sign)


def _tamil_month_start(t: float, q) -> float:
    """The sunrise starting the solar month whose ingress is at t, by the Tamil Rule
    (Sewell and Dikshit, The Indian Calendar, Art. 28): an ingress before sunset starts
    it that day; after sunset, or before dawn, at the next sunrise."""
    s0, s1 = _sunrises(t, q.lat, q.lon, 2)
    return s0 if t < _sunset(s0, q) else s1


def _krittika_day(a: float, b: float, rises: list[float], sets: dict[float, float]):
    """Decision 32 on a Krittika span [a, b): (the day's sunrise, rule, variant's sunrise)."""
    at_set = [sr for sr in rises if a <= sets[sr] < b]
    if len(at_set) == 1:
        return at_set[0], "krittika_at_sunset", None
    if len(at_set) == 2:
        day = next((sr for sr in at_set if a <= sr < b), at_set[-1])
        return day, "two_sunsets_sunrise_day", next(sr for sr in at_set if sr != day)
    day = max(sr for sr in rises if sets[sr] <= a)
    return day, "no_sunset_evening_it_begins", rises[rises.index(day) + 1]


def _krittika_margin(a: float, b: float, rises: list[float], sets: dict, day: float) -> set:
    """The other days a one-ghatika shift of either end of Krittika gives: a changed day,
    or the next day when no sunset is left (research, 16 Oct 2026; as Chhath's caution)."""
    other = set()
    for x, y in ((a - DANDA, b), (a + DANDA, b), (a, b - DANDA), (a, b + DANDA)):
        d, rule, v = _krittika_day(x, y, rises, sets)
        if d != day:
            other.add(d)
        elif rule == "no_sunset_evening_it_begins":
            other.add(v)
    return other


def _karthigai(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s29 (decision 32): the day in solar Karttikai whose sunset falls in Krittika, at
    Tiruvannamalai for every city. No sunset in it: the evening it begins, the next day as
    variant. Two: the day also holding it at sunrise, the other as variant (our reading).
    Two Krittika days in one Karttikai are both shown, neither picked, as for Onam."""
    t = _at(TIRUVANNAMALAI, q)
    nak = lambda x: Mu.nakshatra_at(x, t.ayanamsa)  # noqa: E731
    t0 = local_jd(dt.date(t.year, 11, 1), 0.0, t.tz, "year")
    t1 = local_jd(dt.date(t.year, 12, 31), 0.0, t.tz, "year")
    first = _tamil_month_start(_ingress(SCORPIO, t0, t1, t), t)
    nxt = _tamil_month_start(_ingress(SAGITTARIUS, first, t1, t), t)
    rises = _sunrises(first - 3, t.lat, t.lon, int(nxt - first) + 7)
    sets = {sr: _sunset(sr, t) for sr in rises}
    tripura = {o["date"] for o in _year(t, 15, _tripura)}
    rows = []
    for a, b in _spans(nak, KRITTIKA, first - 2, nxt + 2, 0.1):
        day, rule, variant = _krittika_day(a, b, rises, sets)
        if not first <= day < nxt:
            continue
        cautions = []
        if rule == "no_sunset_evening_it_begins":
            cautions.append("no_krittika_sunset")
        elif other := _krittika_margin(a, b, rises, sets, day):
            cautions.append("krittika_margin")
            variant = variant if variant in other else max(other)
        date = _date(day, t)
        rows.append(
            {
                "date": date,
                "vara": _vara(day, t),
                "rule": rule,
                "variantDate": _date(variant, t) if variant is not None else None,
                "cautions": cautions,
                "krittika": _span((a, b), t),
                "sunset": iso(sets[day], t.tz),
                "tripurotsava": date in tripura,
            }
        )
    if len(rows) > 1:
        for r in rows:
            r["twoKrittika"] = True
    last = max(sr for sr in rises if sr < nxt)
    return rows, {
        "karttikai": {"start": _date(first, t), "end": _date(last, t)},
        "computedAt": TIRUVANNAMALAI,
    }


# --- Pongal and Lohri (festivals.md s28, decision 31, 16 Oct 2026) -----------------------

CHENNAI = {"name": "Chennai", "lat": 13.0827, "lon": 80.2707, "tz": "Asia/Kolkata"}
AMRITSAR = {"name": "Amritsar", "lat": 31.6340, "lon": 74.8723, "tz": "Asia/Kolkata"}
CAPRICORN = 9
PONGAL_MARGIN = 3 / 24  # a day ingress this close to sunset: the next day too (our reading)


def _makara(q) -> float:
    t0 = local_jd(dt.date(q.year, 1, 1), 12.0, q.tz, "year") - 0.5  # 1906 lost its midnight
    return _ingress(CAPRICORN, t0, t0 + 31, q)


def _tamil_day(t: float, q) -> tuple[float, bool, float]:
    """The Tamil Rule's first day for an ingress at t: (its sunrise, whether the ingress fell
    by day, the sunset of the day holding it)."""
    s0, s1 = _sunrises(t, q.lat, q.lon, 2)
    ss = _sunset(s0, q)
    return (s0, True, ss) if t < ss else (s1, False, ss)


def _pongal(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s28.1-28.2 (decision 31): Thai 1 by the Tamil Rule on our Makara ingress, at Chennai
    for every city. A day ingress less than three hours before sunset adds the next day
    as variantDate, popular practice (our reading of 2022 and 2026). Bhogi, Mattu Pongal
    and Kanum Pongal are the day before, after and two after, each with its variant."""
    c = _at(CHENNAI, q)
    t = _makara(c)
    first, by_day, ss = _tamil_day(t, c)
    margin = by_day and ss - t < PONGAL_MARGIN

    def day(n: int, basis: str, source: dict | None = None) -> dict:
        return {
            "date": _date(first + n, c),
            "vara": _vara(first + n, c),
            "basis": basis,
            "source": source,
            "variantDate": _date(first + n + 1, c) if margin else None,
        }

    row = {
        "date": _date(first, c),
        "vara": _vara(first, c),
        "rule": "tamil_rule_day_ingress" if by_day else "tamil_rule_night_ingress",
        "variantDate": _date(first + 1, c) if margin else None,
        "variantBasis": "popular_practice" if margin else None,
        "cautions": ["practice_margin_next_day"] if margin else [],
        "ingress": {"at": iso(t, c.tz), "sunset": iso(ss, c.tz)},
        "set": {
            "bhogi": day(-1, "popular_practice"),
            "mattuPongal": day(1, "text", KS_PONGAL),
            "kanumPongal": day(2, "popular_practice"),
        },
    }
    return [row], {"computedAt": CHENNAI}


def _lohri(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s28.3 (decision 31): the evening before the day, sunrise to sunrise at Amritsar,
    that holds the Makara ingress (Maghi), for every city; no time. Popular practice."""
    a = _at(AMRITSAR, q)
    t = _makara(a)
    (s0,) = _sunrises(t, a.lat, a.lon, 1)
    row = {
        "date": _date(s0 - 1, a),
        "vara": _vara(s0 - 1, a),
        "rule": "eve_of_ingress_day",
        "maghi": {"date": _date(s0, a), "vara": _vara(s0, a)},
        "ingress": {"at": iso(t, a.tz)},
    }
    return [row], {"computedAt": AMRITSAR}


# --- The Mesha new year and Gangaur (festivals.md s30-31, decisions 33-34, 16 Oct 2026) ---

KOCHI = {"name": "Kochi", "lat": 9.9312, "lon": 76.2673, "tz": "Asia/Kolkata"}
ARIES = 0


def _mesha(q) -> float:
    t0 = local_jd(dt.date(q.year, 3, 25), 0.0, q.tz, "year")
    return _ingress(ARIES, t0, t0 + 35, q)


def _vishu(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s30.1 (decision 33): the day whose sunrise is the first after our Mesha ingress, at
    Kochi for every city: our reading of the kept days and of the Kani, the new year's first
    sight (Logan 1887; Nagam Aiya 1906). Popular practice."""
    k = _at(KOCHI, q)
    t = _mesha(k)
    _, s1 = _sunrises(t, k.lat, k.lon, 2)
    row = {
        "date": _date(s1, k),
        "vara": _vara(s1, k),
        "rule": "first_sunrise_after_ingress",
        "ingress": {"at": iso(t, k.tz)},
    }
    return [row], {"computedAt": KOCHI}


def _tamil_new_year(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s30.2 (decision 33): Chittirai 1 by the Tamil Rule on our Mesha ingress, at Chennai for
    every city, as Pongal's Thai 1. Research re-checks 2027 against that year's holiday list;
    a labelled next-day variant is added only if it finds the 15th."""
    c = _at(CHENNAI, q)
    t = _mesha(c)
    first, by_day, ss = _tamil_day(t, c)
    row = {
        "date": _date(first, c),
        "vara": _vara(first, c),
        "rule": "tamil_rule_day_ingress" if by_day else "tamil_rule_night_ingress",
        "variantDate": None,
        "variantBasis": None,
        "cautions": [],
        "ingress": {"at": iso(t, c.tz), "sunset": iso(ss, c.tz)},
    }
    return [row], {"computedAt": CHENNAI}


def _baisakhi(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s30.3 (decision 33): the day, sunrise to sunrise at Amritsar, that holds our Mesha
    ingress, as Lohri's Maghi; for every city, with no time. Popular practice."""
    a = _at(AMRITSAR, q)
    t = _mesha(a)
    (s0,) = _sunrises(t, a.lat, a.lon, 1)
    row = {
        "date": _date(s0, a),
        "vara": _vara(s0, a),
        "rule": "day_holding_ingress",
        "ingress": {"at": iso(t, a.tz)},
    }
    return [row], {"computedAt": AMRITSAR}


def _gangaur(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s31 (decision 34): the Caitra shukla Tritiya by DS p. 9's Gauri-vrata rule: the day
    whose sunrise is the last the Tritiya holds, even by a trace (two: the later, Caturthi-
    joined); holding none, the Dvitiya-joined day it begins. NS's muhurta is a note."""
    base = _base(start, end, 3, q)
    if not _in_month(base, "chaitra"):
        return None
    s = _sunrises(start, q.lat, q.lon, 4)  # s[0] <= start < s[1]
    held = [sr for sr in s[1:] if sr < end]
    if held:
        day, rule = held[-1], "two_sunrises_later" if len(held) > 1 else "sunrise_tritiya"
    else:
        day, rule = s[0], "kshaya_dvitiya_joined"
    return {
        **base,
        "date": _date(day, q),
        "vara": _vara(day, q),
        "rule": rule,
        "popularName": "Gangaur",
        "displayName": "Gaurī-tṛtīyā",
    }


# --- Monthly vratas (festivals.md s32, decision 35, 16 Oct 2026) --------------------------


def _vinayaka(start: float, end: float, _next: float, q: EkadashiQuery) -> dict:
    """s32.1 (the lead's ruling): each shukla Caturthi by the live Ganesha Caturthi rule (NS
    p. 47), so the Bhadrapada row matches ganesha-chaturthi. dsEarlier is DS p. 9's stricter
    day where it is earlier: the later only when the Caturthi pervades the later day's whole
    midday alone. A note; it never moves the date."""
    base = _base(start, end, 4, q)
    _, days = _days(start, end, q, ("madhyahna",))
    chosen, rule, ds = _caturthi_choice(days)
    w = days[chosen]["_w"]["madhyahna"]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "dsEarlier": days[ds]["date"] if ds < chosen else None,
        "popularName": "Vinayaka Chaturthi",
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


def _skanda(start: float, end: float, _next: float, q: EkadashiQuery) -> dict:
    """s32.2: each shukla Shashthi joined to the Panchami (VR f. 108; NS p. 48; DS pp. 9-10):
    the day on which it begins between sunrise and sunset; begun at night, the first day
    whose sunrise it holds. The joining by day is our reading."""
    base = _base(start, end, 6, q)
    s = _sunrises(start, q.lat, q.lon, 2)  # s[0] <= start < s[1]
    if start < _sunset(s[0], q):
        day, rule = s[0], "panchami_joined_by_day"
    elif s[1] < end:
        day, rule = s[1], "first_sunrise_in_shashthi"
    else:  # wholly inside one night, only far north
        day, rule = s[0], "night_only_day_it_begins"
    return {**base, "date": _date(day, q), "vara": _vara(day, q), "rule": rule}


def _kalashtami_monthly(start: float, end: float, _next: float, q: EkadashiQuery) -> dict:
    """s32.3: each krishna Ashtami by the annual day's D4 rule (DS p. 10: some fast on every
    dark Ashtami for Kalabhairava, decided as the Bhairava-jayanti), without its vigil."""
    base = _base(start, end, 23, q)
    _, days = _days(start, end, q, ("madhyahna", "pradosha"))
    chosen, rule, window, variant = _kala_choice(days)
    w = days[chosen]["_w"][window]
    return {
        **base,
        "days": _strip(days),
        "date": days[chosen]["date"],
        "vara": days[chosen]["vara"],
        "rule": rule,
        "variantDate": days[variant]["date"] if variant != chosen else None,
        "pujaWindow": _span(_clip(start, end, w) or w, q),
    }


# --- Three spring days (festivals.md s33, decisions 36-38, 16 Oct 2026) -----------------
# Popular practice: no text read gives these days; each rule is ours, tested on kept days.

AHMEDABAD = {"name": "Ahmedabad", "lat": 23.0225, "lon": 72.5714, "tz": "Asia/Kolkata"}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
RAJASTHAN_AVOIDED = {"sunday", "tuesday", "saturday"}


def _sunrise_day(a: float, b: float, q) -> tuple[float, str]:
    """The first day whose sunrise the span [a, b) holds; holding none, the day it begins."""
    s = _sunrises(a, q.lat, q.lon, 3)  # s[0] <= a < s[1]
    held = [sr for sr in s[1:] if sr < b]
    if not held:
        return s[0], "no_sunrise_day_it_falls_on"
    return held[0], "two_sunrises_first" if len(held) > 1 else "sunrise"


def _sunset_day(a: float, b: float, q) -> tuple[float, str]:
    """The first day whose sunset the span [a, b) holds; holding none, the first day whose
    sunrise it holds."""
    held = [sr for sr in _sunrises(a - 1, q.lat, q.lon, 4) if a <= _sunset(sr, q) < b]
    if held:
        return held[0], "two_sunsets_first" if len(held) > 1 else "sunset"
    return _sunrise_day(a, b, q)[0], "no_sunset_sunrise_day"


def _margin(a: float, b: float, q, day_of) -> list[str]:
    """The other dates the rule gives when either end of [a, b) moves by one ghatika
    (24 minutes), as for Chhath (decision 28)."""
    own = _date(day_of(a, b, q)[0], q)
    moved = ((a - DANDA, b), (a + DANDA, b), (a, b - DANDA), (a, b + DANDA))
    return sorted({_date(day_of(x, y, q)[0], q) for x, y in moved} - {own})


def _entry(date: str, reason: str) -> dict:
    return {"date": date, "vara": WEEKDAYS[dt.date.fromisoformat(date).weekday()], "reason": reason}


def _with_variants(row: dict, variants: list[dict]) -> dict:
    """variants, with variantDate (the first) and cautions (their reasons) as elsewhere."""
    return {
        **row,
        "variants": variants,
        "variantDate": variants[0]["date"] if variants else None,
        "cautions": [v["reason"] for v in variants],
    }


def _rang_panchami(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s33.1 (decision 36): the dark Panchami after Holi (amanta Phalguna krishna) on the
    first day whose sunrise holds it; holding none, the day it begins."""
    base = _base(start, end, 20, q)
    if not _in_month(base, "phalguna"):
        return None
    day, rule = _sunrise_day(start, end, q)
    margin = [_entry(d, "tithi_ghatika_margin") for d in _margin(start, end, q, _sunrise_day)]
    return _with_variants(
        {**base, "date": _date(day, q), "vara": _vara(day, q), "rule": rule}, margin
    )


def _sheetala(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s33.3 (decision 38): the dark Ashtami after Holi on the first day whose sunrise holds
    it; holding none, the day it begins. Variants: the Saptami by the same rule, and
    Rajasthan's move off a Sunday, Tuesday or Saturday to the nearest earlier other day."""
    base = _base(start, end, 23, q)
    if not _in_month(base, "phalguna"):
        return None
    day, rule = _sunrise_day(start, end, q)
    edges = Mu._scan(lambda t: Mu.tithi_at(t, q.ayanamsa), start - 1.6, start - 1e-6, 0.25)
    saptami = max(t for t, n in edges if n == 22)
    variants = [_entry(_date(_sunrise_day(saptami, start, q)[0], q), "saptami")]
    d = dt.date.fromisoformat(_date(day, q))
    if WEEKDAYS[d.weekday()] in RAJASTHAN_AVOIDED:
        d -= dt.timedelta(1)
        while WEEKDAYS[d.weekday()] in RAJASTHAN_AVOIDED:
            d -= dt.timedelta(1)
        variants.append(_entry(d.isoformat(), "rajasthan_weekday"))
    variants += [_entry(x, "tithi_ghatika_margin") for x in _margin(start, end, q, _sunrise_day)]
    return _with_variants(
        {**base, "date": _date(day, q), "vara": _vara(day, q), "rule": rule}, variants
    )


# --- Kali Puja and Ahoi Ashtami (festivals.md s35-36, decisions 44-45, 18 Oct 2026) -----
# Popular practice: no text read gives either day. Each weighs one window on the day the
# tithi begins and the next, with decision 43's five-minute caution at the window's edges.


def _window_choice(cover: list[float], window: str) -> tuple[int, str]:
    """The day whose window the tithi covers; covering both, the day with more of it, the
    earlier if equal; covering neither, the later day (our reading)."""
    if cover[0] > 0 and cover[1] > 0:
        return (0 if cover[0] >= cover[1] else 1), f"{window}_both_more"
    if cover[0] > 0 or cover[1] > 0:
        return (0 if cover[0] > 0 else 1), window
    return 1, f"{window}_neither_later"


def _near_window(start: float, end: float, ws: list[tuple], window: str, k: int) -> int | None:
    """The other day the rule gives if the tithi's start or end moves by five minutes."""
    n = NEAR_BOUNDARY
    moved = ((start - n, end), (start + n, end), (start, end - n), (start, end + n))
    days = {_window_choice([_share(a, b, w) for w in ws], window)[0] for a, b in moved}
    return min(days - {k}, default=None)


def _two_days(start: float, end: float, q: EkadashiQuery, window: str) -> tuple:
    """The window on the two days, the rule's day and the caution: (sunrises, windows,
    the day, the row)."""
    s, days = _days(start, end, q, (window,))
    ws = [d["_w"][window] for d in days]
    k, rule = _window_choice([_share(start, end, w) for w in ws], window)
    other = _near_window(start, end, ws, window, k)
    row = {
        "days": _strip(days),
        "date": days[k]["date"],
        "vara": days[k]["vara"],
        "rule": rule,
        "cautions": ["near_boundary"] if other is not None else [],
        "nearBoundaryDate": days[other]["date"] if other is not None else None,
    }
    return s, ws, k, row


def _kali_puja(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s35 (decision 44): the Dipavali Amavasya, on the night whose nishitha it covers;
    covering both, the night with more of it, the earlier if equal; covering neither, the
    later night, which holds it at pradosha (our reading). pujaWindow is that nishitha
    within the Amavasya."""
    base = _base(start, end, 30, q)
    if not _in_month(base, "ashwin"):
        return None
    _, ws, k, row = _two_days(start, end, q, "nishitha")
    return {**base, **row, "pujaWindow": _span(_clip(start, end, ws[k]), q)}


def _ahoi(start: float, end: float, _next: float, q: EkadashiQuery) -> dict | None:
    """s36 (decision 45): the nija amanta Ashvina (purnimanta Kartika) krishna Ashtami, on
    the day whose pradosha it covers; covering both, the day with more of it, the earlier
    if equal; covering neither, the later day, whose sunrise holds it (our reading). That
    day's sunset, and its moonrise, the first after its sunrise and the visible rise as for
    Karva Chauth; no text read gives a star-sighting time."""
    base = _base(start, end, 23, q)
    if not _in_month(base, "ashwin"):
        return None
    s, ws, k, row = _two_days(start, end, q, "pradosha")
    rise, _ = moon_rise_set(s[k], s[k + 1], q.lat, q.lon, upper_limb=True)
    return {
        **base,
        **row,
        "sunset": iso(ws[k][0], q.tz),
        "moonrise": iso(rise, q.tz) if rise is not None else None,
    }


def _cheti_chand(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """s33.2 (decision 37): the nija Caitra shukla Dvitiya on the first day whose sunset it
    holds; holding none, the first day whose sunrise it holds; at Ahmedabad for every city.
    Variants: the earlier day when it begins inside that evening's pradosha, and in an
    adhika-Caitra year the adhika month's day by the same rule."""
    a = _at(AHMEDABAD, q)

    def build(start: float, end: float, _next: float, qq) -> dict | None:
        base = _base(start, end, 2, qq)
        if base["lunarMonth"]["amanta"] != "chaitra":
            return None
        day, rule = _sunset_day(start, end, qq)
        (s0,) = _sunrises(start, qq.lat, qq.lon, 1)  # the day the Dvitiya begins in
        variants = []
        late = _sunset(s0, qq) <= start < _windows(s0, qq)["pradosha"][1]
        if late and _date(s0, qq) != _date(day, qq):
            variants.append(_entry(_date(s0, qq), "pradosha_start"))
        variants += [
            _entry(x, "tithi_ghatika_margin") for x in _margin(start, end, qq, _sunset_day)
        ]
        return {
            **base,
            "date": _date(day, qq),
            "vara": _vara(day, qq),
            "rule": rule,
            "_variants": variants,
        }

    rows = _year(a, 2, build)
    adhika = [_entry(r["date"], "adhika_month") for r in rows if r["lunarMonth"]["adhika"]]
    out = []
    for r in rows:
        variants = r.pop("_variants")
        if not r["lunarMonth"]["adhika"]:
            out.append(_with_variants(r, variants + adhika))
    return out, {"computedAt": AHMEDABAD}


# --- Magh Mela: Magha-snana at Prayaga (contract 7t; research's magha-snana.md v3) ------

PRAYAGRAJ = {"name": "Prayagraj", "lat": 25.4358, "lon": 81.8463, "tz": "Asia/Kolkata"}
SAGITTARIUS, AQUARIUS = 8, 10
MAGHA_STAR = 9  # nakshatra index, Ashvini = 0
VYATIPATA = 16  # yoga index, Vishkambha = 0: the 17th


def _ns(verse: str, page: str) -> dict:
    return {**SOURCE, "verse": verse, "page": page}


def _ds(verse: str, page: str) -> dict:
    return {**DS, "verse": verse, "page": page}


def _amanta(t: float, edges: list[tuple[float, int]]) -> tuple[float, float]:
    """The amanta month, new moon to new moon, holding t."""
    starts = [jd for jd, num in edges if num == 1]
    return max(x for x in starts if x <= t), min(x for x in starts if x > t)


def _tithi_span(edges: list, month: tuple[float, float], num: int) -> tuple[float, float] | None:
    """Tithi `num` of the month: the span that begins inside it."""
    for (a, n), (b, _) in zip(edges, edges[1:], strict=False):
        if n == num and month[0] <= a < month[1]:
            return a, b
    return None


def _sunrise_bound(span: tuple[float, float], q, first: bool) -> tuple[float, str]:
    """The first or last sunrise the tithi holds; with none, the day it falls on."""
    a, b = span
    s = _sunrises(a, q.lat, q.lon, 4)
    held = [t for t in s if a <= t < b]
    if not held:
        return s[0], "only_day"
    return (held[0], "first_sunrise") if first else (held[-1], "last_sunrise")


def _bound(span: tuple[float, float], q, first: bool) -> dict:
    rise, rule = _sunrise_bound(span, q, first)
    return {"date": _date(rise, q), "vara": _vara(rise, q), "rule": rule, "tithi": _span(span, q)}


def _plus(date: str, n: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=n)).isoformat()


def _three(date: str) -> list[str]:
    return [date, _plus(date, 1), _plus(date, 2)]


def _meet(*spans: list[tuple[float, float]]) -> tuple[float, float] | None:
    """The first stretch where one span from each list overlaps."""
    lo, hi = max(s[0][0] for s in spans), min(s[0][1] for s in spans)
    if hi > lo:
        return lo, hi
    head = min(range(len(spans)), key=lambda i: spans[i][0][1])
    if len(spans[head]) == 1:
        return None
    return _meet(*(s[1:] if i == head else s for i, s in enumerate(spans)))


def _ardhodaya(span: tuple[float, float], q) -> dict | None:
    """v2 decision 3 (DS p. 87; NS p. 318): the Amavasya, a Sunday at Prayagraj (sunrise
    to sunrise), the Vyatipata yoga and Shravana at one instant."""
    a, b = span
    s = _sunrises(a, q.lat, q.lon, 4)
    sundays = [(x, y) for x, y in zip(s, s[1:], strict=False) if _vara(x, q) == "sunday"]
    yoga = _spans(lambda t: Mu.yoga_at(t, q.ayanamsa), VYATIPATA, a, b, 0.05)
    star = _spans(lambda t: Mu.nakshatra_at(t, q.ayanamsa), SHRAVANA, a, b, 0.05)
    if not (sundays and yoga and star):
        return None
    hit = _meet([span], sundays, yoga, star)
    if hit is None:
        return None
    rise = max(x for x, _ in sundays if x <= hit[0])
    day = (rise, _sunset(rise, q))  # sunrise to sunset, our reading of "by day"
    return {**_span(hit, q), "daylight": min(hit[1], day[1]) > max(hit[0], day[0])}


def _mahamaghi(span: tuple[float, float], q) -> dict | None:
    """v2 decision 4 (NS p. 333): Jupiter and the Moon in sidereal Magha at one instant
    within the Maghi Purnima."""
    a, b = span
    moon = _spans(lambda t: Mu.nakshatra_at(t, q.ayanamsa), MAGHA_STAR, a, b, 0.05)
    jupiter = _spans(lambda t: positions(t, q.ayanamsa)["Jupiter"].nakshatra, MAGHA_STAR, a, b, 0.5)
    hit = _meet(moon, jupiter) if moon and jupiter else None
    return _span(hit, q) if hit else None


def _month_rule(t_makara: float, t_kumbha: float, edges: list, q) -> str:
    """DS pp. 4, 87 (v3): which months the bathing runs through. The amanta month holding
    the Makara ingress is Pausha and the one holding the Kumbha ingress Magha."""
    pausha, magha = _amanta(t_makara, edges), _amanta(t_kumbha, edges)
    t_dhanu = _ingress(SAGITTARIUS, t_makara - 35, t_makara - 25, q)
    if pausha[0] <= t_dhanu:  # the month holding Makara holds Dhanu too
        return "month_kshaya"
    if magha[0] > pausha[1]:
        return "month_adhika_magha"  # a month with no ingress between them
    if t_dhanu < _amanta(pausha[0] - 1, edges)[0]:
        return "month_adhika_pausha"
    return "month_regular"


def _magha_snana(q: EkadashiQuery) -> tuple[list[dict], dict]:
    """Contract 7t: the bathing season whose Maghi Purnima falls in the year, at Prayagraj
    for every city (the lead, 17 Oct 2026)."""
    p = _at(PRAYAGRAJ, q)
    t_makara = _makara(p)
    t_kumbha = _ingress(AQUARIUS, t_makara + 25, t_makara + 35, p)
    edges = Mu._scan(lambda t: Mu.tithi_at(t, p.ayanamsa), t_makara - 75, t_kumbha + 45, 0.25)
    pausha, magha = _amanta(t_makara, edges), _amanta(t_kumbha, edges)
    # v4 (1983): one lost month holds both ingresses, so DS p. 4's two Purnimas are one full
    # moon and DS p. 86's Makara-to-Kumbha span is the month
    solar_only = pausha == magha
    rule = "month_kshaya_solar" if solar_only else _month_rule(t_makara, t_kumbha, edges, p)

    def full_or_new(month: tuple[float, float], num: int, held_rule: str) -> tuple[dict, tuple]:
        span = _tithi_span(edges, month, num)
        rise, how = _sunrise_bound(span, p, first=False)
        day = {
            "date": _date(rise, p),
            "vara": _vara(rise, p),
            "rule": held_rule if how == "last_sunrise" else "only_day",
            "tithi": _span(span, p),
        }
        return day, span

    pp, _ = full_or_new(pausha, 15, "pausha_later_day")
    mauni, mauni_span = full_or_new(pausha, 30, "amavasya_pratipad_pair")
    maghi, maghi_span = full_or_new(magha, 15, "maghi_later_day")
    sk = _sankranti_one(t_makara, CAPRICORN, p)
    month_cite = (_ns("the month of bathing", "319"), _ds("the month of bathing", "86"))

    days = [
        {"id": "pausha_purnima", **pp, "mark": "month_start"},
        {
            "id": "makara_sankranti",
            "date": sk["date"],
            "vara": sk["vara"],
            "rule": sk["rule"],
            "ruleKind": "sankranti",
            "mark": "solar_start",
            "source": _ds("the solar reckoning", "86"),
            "alsoSource": _ns("the Makara punyakala", "325"),
            "at": sk["at"],
        },
        {
            "id": "mauni_amavasya",
            **mauni,
            "mark": "texts_day_popular_name",
            "source": _ns("the Amavasya between the Pausha and Magha full moons", "318"),
            "alsoSource": _ds("ardhodaya", "87"),
            "popularName": "Mauni Amavasya",
        },
        {"id": "maghi_purnima", **maghi, "mark": "month_end"},
    ]
    for d in (days[0], days[3]):
        d["source"], d["alsoSource"] = month_cite
    if solar_only:  # v5: each tithi of the lost month is in both months (DS p. 3; NS p. 21)
        both = "a lost month's tithis in both months"
        days[3].update(mark="lost_month_purnima", source=_ds(both, "3"), alsoSource=_ns(both, "21"))
        days[2].update(
            mark="lost_month_amavasya",
            source=_ds(both, "3"),
            alsoSource=_ns("the Amavasya following the Pausha full moon", "318"),
        )
        del days[0]  # the one full moon shows once, as the Maghi Purnima
    span5, span7 = _tithi_span(edges, magha, 5), _tithi_span(edges, magha, 7)
    vasanta = _vasanta(*span5, span5[1], p) if span5 else None
    ratha = _ratha(*span7, span7[1], p) if span7 else None
    if vasanta:
        days.append(
            {
                "id": "vasanta_panchami",
                "date": vasanta["date"],
                "vara": vasanta["vara"],
                "rule": vasanta["rule"],
                "ruleKind": "vasanta-panchami",
                "mark": "inside_month_not_named",
                "source": month_cite[0],
                "alsoSource": month_cite[1],
            }
        )
    if ratha:
        days.append(
            {
                "id": "ratha_saptami",
                "date": ratha["date"],
                "vara": ratha["vara"],
                "rule": ratha["rule"],
                "ruleKind": "ratha-saptami",
                "mark": "texts_day",
                "source": _ns("Ratha-saptami at Prayaga", "330"),
                "alsoSource": None,
            }
        )
    days.sort(key=lambda d: d["date"])

    views = [{"id": "trayodashi", "dates": _three(_plus(maghi["date"], -2)), "headline": True}]
    if ratha:
        views.append(
            {
                "id": "makara_ratha_maghi",
                "dates": [sk["date"], ratha["date"], maghi["date"]],
                "headline": False,
            }
        )
    dashami = _bound(_tithi_span(edges, magha, 10), p, first=True)["date"]
    first_of_magha = _bound(_tithi_span(edges, magha, 1), p, first=True)["date"]
    views += [
        {"id": "from_dashami", "dates": _three(dashami), "headline": False},
        {"id": "makara_first_three", "dates": _three(sk["date"]), "headline": False},
        {"id": "magha_first_three", "dates": _three(first_of_magha), "headline": False},
    ]

    shivaratri = None
    span29 = _tithi_span(edges, magha, 29)
    sv = _shivaratri(*span29, span29[1], p, True) if span29 else None
    if sv:
        rise = _sunrises(local_jd(dt.date.fromisoformat(sv["date"]), 12.0, p.tz), p.lat, p.lon, 1)[
            0
        ]
        shivaratri = {
            "date": sv["date"],
            "vara": sv["vara"],
            "sunrise": iso(rise, p.tz),
            "kumbhaSankranti": iso(t_kumbha, p.tz),
            # v3: the vrata day's morning bath against the ingress
            "insideSolarSpan": rise < t_kumbha,
            # v4: the solar span is the month, so a vrata sunrise before Kumbha is inside it
            "mark": "inside_month_not_named" if solar_only and rise < t_kumbha else "outside_month",
        }

    lunar = None  # v4: DS p. 4's bounds collapse
    if not solar_only:
        lunar = {
            "start": {
                "ekadashi": _bound(_tithi_span(edges, pausha, 11), p, first=True),
                "purnima": pp["date"],
                "amavasya": mauni["date"],
            },
            "end": {
                "dvadashi": _bound(_tithi_span(edges, magha, 12), p, first=False),
                "purnima": maghi["date"],
            },
        }
    row = {
        "month": {
            "rule": rule,
            "lunar": lunar,
            "solar": {
                "start": {"at": iso(t_makara, p.tz), "date": _date(t_makara, p)},
                "end": {"at": iso(t_kumbha, p.tz), "date": _date(t_kumbha, p)},
            },
        },
        "bathDays": days,
        "threeDays": views,
        "ardhodaya": _ardhodaya(mauni_span, p),
        "mahamaghi": _mahamaghi(maghi_span, p),
        "shivaratri": shivaratri,
    }
    return [row], {"computedAt": PRAYAGRAJ}


def _year(q: EkadashiQuery, num: int | set[int], build) -> list[dict]:
    rows = _collect(
        q,
        num if isinstance(num, set) else {num},
        lambda a, b, c, qq: build(a, b, c, qq) or {"date": None},
        lambda r: (r["date"],),
    )
    return [r for r in rows if r.get("date")]


# kind: (tithi, builder, NS pages, DS pages or None)
FESTIVALS = {
    "dipavali": (30, _dipavali, "pp. 299–300", None),
    "mahashivaratri": (
        29,
        lambda a, b, c, q: _shivaratri(a, b, c, q, True),
        "pp. 334–337",
        None,
    ),
    "masik-shivaratri": (29, lambda a, b, c, q: _shivaratri(a, b, c, q, False), "p. 340", None),
    "ganesha-chaturthi": (4, _ganesha, "pp. 47, 198", None),
    "raksha-bandhan": (15, _raksha, "pp. 179–180", "p. 49"),
    "janmashtami": (23, _janmashtami, "pp. 183–192", "pp. 49–51"),
    "sharad-navaratri": (1, _navaratri, "pp. 240–241, 262–265, 272–273", "pp. 65–66, 68–69"),
    "chaitra-navaratri": (
        1,
        lambda a, b, c, q: _navaratri(a, b, c, q, "chaitra"),
        "pp. 113, 118, 240–241, 262–265, 272–273",
        "pp. 31, 33–34, 65–66, 69",
    ),
    "ramanavami": (9, _ramanavami, "pp. 118–120", "p. 33"),
    "vijayadashami": (10, _vijayadashami, "pp. 283–284", "p. 71"),
    "holika-dahana": (15, _holika, "pp. 342–345", "pp. 94–95"),
    "karva-chauth": (19, _karva, "p. 293", "pp. 9, 76"),
    "tulsi-vivah": (11, _tulsi, "p. 306", "pp. 81–82"),
    "tripurotsava": (15, _tripura, "pp. 311–312", "p. 84"),
    "vasanta-panchami": (5, _vasanta, "p. 329", "pp. 9, 89"),
    "ratha-saptami": (7, _ratha, "pp. 329–332", "p. 89"),
    "bhishma-ashtami": (8, _bhishma, "pp. 332–333, 718", "pp. 89–90"),
    "kalashtami": (23, _kalashtami, "pp. 312–313", "p. 84"),
    "dattatreya-jayanti": (15, _dattatreya, "p. 315", "p. 84"),
    "ganesha-jayanti": (4, _ganesha_jayanti, "p. 329", "p. 89"),
    "holashtak": (8, _holashtak, None, None),
    "akshaya-tritiya": (3, _akshaya, "pp. 134–135", "pp. 36–37"),
    "parashurama-jayanti": (3, _parashurama, "p. 134", "p. 37"),
    "guru-purnima": (15, _guru_purnima, "p. 160", "pp. 20, 43–44"),
    "durga-puja": (6, _durga_puja, "pp. 262–265, 272–273", "p. 69"),
    "vat-savitri": ({15, 30}, _vat_savitri, "pp. 146–148", "pp. 4, 41"),
    "ganga-dussehra": (10, _ganga, "pp. 143–146", "pp. 38–39"),
    "rath-yatra": (2, _rath, "p. 149", None),
    "sawan-somvar": (None, None, None, "p. 44"),
    "hariyali-teej": (
        3,
        lambda a, b, c, q: _teej(a, b, c, q, "hariyali-teej", "shravana"),
        "p. 197",
        None,
    ),
    "kajari-teej": (
        18,
        lambda a, b, c, q: _teej(a, b, c, q, "kajari-teej", "shravana"),
        "p. 197",
        None,
    ),
    "hartalika-teej": (
        3,
        lambda a, b, c, q: _teej(a, b, c, q, "hartalika-teej", "bhadrapada"),
        "p. 197",
        "p. 55",
    ),
    "nag-panchami": (5, _naga, "p. 164", "p. 44"),
    "rishi-panchami": (5, _rishi, None, "p. 55"),
    "anant-chaturdashi": (14, _ananta, "pp. 210–211", "p. 58"),
    # Popular practice (s27): no source; context, where a text touches the day, below.
    "chhath": (6, _chhath, None, None),
    "chaiti-chhath": (6, lambda a, b, c, q: _chhath(a, b, c, q, "chaitra"), None, None),
    "hanuman-jayanti": (15, _hanuman, None, None),
    "radhashtami": (8, _radhashtami, None, None),
    "onam": (None, None, None, None),
    "vishwakarma-puja": (None, None, None, None),
    "karthigai-deepam": (None, None, None, None),
    "lohri": (None, None, None, None),
    # Decision 31: Thai 1 by the Tamil Rule (SD p. 12), sourced; the set below.
    "pongal": (None, None, None, None),
    # Decision 33: the Mesha new year at one regional place each; Tamil New Year is sourced.
    "vishu": (None, None, None, None),
    "tamil-new-year": (None, None, None, None),
    "baisakhi": (None, None, None, None),
    # Decision 34: per city, as every tithi festival.
    "gangaur": (3, _gangaur, "p. 114", "pp. 9, 31–32"),
    # Decision 35: the monthly vratas, per city; Vinayaka Chaturthi monthly is popular practice.
    "vinayaka-chaturthi": (4, _vinayaka, None, None),
    "skanda-sashti": (6, _skanda, "p. 48", "pp. 9–10"),
    "kalashtami-monthly": (23, _kalashtami_monthly, None, "p. 10"),
    # Decisions 36-38: popular practice; cheti-chand at Ahmedabad for every city.
    "rang-panchami": (20, _rang_panchami, None, None),
    "cheti-chand": (None, None, None, None),
    "sheetala-ashtami": (23, _sheetala, None, None),
    "magha-snana": (None, None, "pp. 318–326, 330, 333", "pp. 4, 6, 86–88"),
    # Decisions 44-45 (s35-36): popular practice, per city.
    "kali-puja": (30, _kali_puja, None, None),
    "ahoi-ashtami": (23, _ahoi, None, None),
}
POPULAR = {
    "chhath",
    "chaiti-chhath",
    "hanuman-jayanti",
    "radhashtami",
    "onam",
    "vishwakarma-puja",
    "karthigai-deepam",
    "lohri",
    "vishu",
    "baisakhi",
    "vinayaka-chaturthi",
    "rang-panchami",
    "cheti-chand",
    "sheetala-ashtami",
    "kali-puja",
    "ahoi-ashtami",
}
# Computed at one regional place for every city (decisions 31-33): once per year and ayanamsa.
ONE_PLACE = {
    "karthigai-deepam",
    "pongal",
    "lohri",
    "vishu",
    "tamil-new-year",
    "baisakhi",
    "cheti-chand",
    "magha-snana",
}
YEARLY = {
    "onam": _onam,
    "vishwakarma-puja": _vishwakarma,
    "karthigai-deepam": _karthigai,
    "pongal": _pongal,
    "lohri": _lohri,
    "vishu": _vishu,
    "tamil-new-year": _tamil_new_year,
    "baisakhi": _baisakhi,
    "cheti-chand": _cheti_chand,
    "magha-snana": _magha_snana,
}
KALA_SANKALITA = {
    "text": "Kala Sankalita",
    "author": "John Warren",
    "edition": "John Warren, College Press, Madras, 1825",
}
KS_PONGAL = {
    **KALA_SANKALITA,
    "verse": "Uttarayana Punia Calum, the Pungol; Matoo Pungol",
    "page": "402",
}
SEWELL_DIKSHIT = {
    "text": "The Indian Calendar",
    "author": "Robert Sewell and Śaṅkara Bālkṛishṇa Dīkshit",
    "edition": "Robert Sewell and Śaṅkara Bālkṛishṇa Dīkshit, Swan Sonnenschein, London, 1896",
    "verse": "Art. 28, the Tamil Rule",
    "page": "12",
}
DS_MESHA = [  # research, 16 Oct 2026: the bath and gifts are p. 2; p. 31 is the punyakala
    {**DS, "verse": "the bath and gifts at an ingress", "page": "2"},
    {**DS, "verse": "the Mesha punyakala, ten nadis either side of the ingress", "page": "31"},
]
KRTYARATNAKARA = {
    "text": "Kṛtyaratnākara",
    "author": "Caṇḍeśvara Ṭhakkura",
    "edition": (
        "Caṇḍeśvara Ṭhakkura, edited by Kamala-kṛṣṇa Smṛtitīrtha, "
        "Asiatic Society of Bengal (Baptist Mission Press), Calcutta, 1925"
    ),
}
# Texts that touch the day without giving it (s27): shown as context, never as source.
CONTEXT = {
    "chhath": [
        {**DS, "verse": "Surya-shashthi of Bhadrapada", "page": "55"},
        {**KRTYARATNAKARA, "verse": "the dark-Shashthi Sun vow (Bhaviṣya)", "page": "447–448"},
        {**KRTYARATNAKARA, "verse": "the Kartika Shashthi, to Karttikeya", "page": "415"},
    ],
    "chaiti-chhath": [
        {**DS, "verse": "Surya-shashthi of Bhadrapada", "page": "55"},
        {**KRTYARATNAKARA, "verse": "the dark-Shashthi Sun vow (Bhaviṣya)", "page": "447–448"},
    ],
    "vishwakarma-puja": [{**DS, "verse": "sankranti punyakala", "page": "2"}],
    "karthigai-deepam": [
        {
            **KALA_SANKALITA,
            "verse": "Cartica Deepum and Survalaya Deepum (holy days 29–30)",
            "page": "401",
        },
        {**SOURCE, "verse": "Tripurotsava lamps on the Karttika Purnima", "page": "312"},
        {**DS, "verse": "Tripurotsava lamps on the Karttika Purnima", "page": "84"},
    ],
    "pongal": [
        {**DS, "verse": "the southern usage of a night Makara ingress", "page": "85"},
        KS_PONGAL,
        {
            **DS,
            "verse": "the Makara rites: the bath, sesame, the Sun bathed with milk",
            "page": "86",
        },
    ],
    "lohri": [
        {
            **SOURCE,
            "verse": "Baudhāyana: two holy days after a night Makara ingress, in the north",
            "page": "327",
        }
    ],
    "vishu": [
        {
            "text": "Malabar",
            "author": "William Logan",
            "edition": "William Logan, Vol. 1, Government Press, Madras, 1887",
            "verse": "Vishu, the astronomical new year day",
            "page": "160–161",
        },
        {
            "text": "The Travancore State Manual",
            "author": "V. Nagam Aiya",
            "edition": "V. Nagam Aiya, Vol. 2, Travancore Government Press, Trivandrum, 1906",
            "verse": "Vishu and the Kani",
            "page": "366–367",
        },
        {**SEWELL_DIKSHIT, "verse": "Art. 28, rule (b), the Malabar month's own rule"},
    ],
    "tamil-new-year": DS_MESHA,
    "vinayaka-chaturthi": [
        {
            **SOURCE,
            "verse": "Bṛhaspati: the Caturthi at midday, the next day if it reaches it",
            "page": "47",
        },
        {**DS, "verse": "the Vinayaka-vrata Caturthi at midday", "page": "9"},
        {**DS, "verse": "the Caitra shukla Caturthi, Ganesha at midday", "page": "32"},
        {**DS, "verse": "the Magha shukla Caturthi, decided as the Bhadrapada one", "page": "89"},
    ],
    "baisakhi": DS_MESHA,
    "rang-panchami": [
        {
            **DS,
            "verse": "ordinary people keep the colour festival up to the dark Panchami",
            "page": "95",
        },
        {
            "text": "An Indian Ephemeris, A.D. 700 to A.D. 1799",
            "author": "L. D. Swamikannu Pillai",
            "edition": "L. D. Swamikannu Pillai, Vol. 1, part 1, Government Press, Madras, 1922",
            "verse": "Rangapanchami, when colours are thrown about",
            "page": "65–66",
        },
        {
            "text": "Gazetteer of the Bombay Presidency, vol. XVIII, part 1: Poona",
            "author": "Edited by James M. Campbell",
            "edition": "Edited by James M. Campbell, Government Central Press, Bombay, 1885",
            "verse": "Rang-panchmi, where the Holi ends among the Kunbis",
            "page": "293",
        },
    ],
    "cheti-chand": [
        {
            **DS,
            "verse": "the young moon worshipped at nightfall on the Caitra shukla Dvitiya",
            "page": "31",
        },
        {
            "text": "Gazetteer of the Province of Sind",
            "author": "E. H. Aitken",
            "edition": (
                "E. H. Aitken, Printed for Government at the “Mercantile” Steam Press, Karachi, "
                "1907"
            ),
            "verse": "Cheti Chand, the first day of the first month of the Hindu year",
            "page": "206",
        },
        {
            "text": "The Imperial Gazetteer of India",
            "edition": (
                "Published under the authority of His Majesty’s Secretary of State for India in "
                "Council, New edition, vol. XXII (Samadhiala to Singhana), Clarendon Press, "
                "Oxford, 1908"
            ),
            "verse": "Chetichand, the Hindu New Year, observed on the river-side (Sind)",
            "page": "411",
        },
        {
            "text": "Folk Tales of Sind and Guzarat",
            "author": "C. A. Kincaid",
            "edition": "C. A. Kincaid, Daily Gazette Press, Karachi, 1925",
            "verse": "Udero Lal born on Cheti Chand",
            "page": "12",
        },
    ],
    "sheetala-ashtami": [
        {
            "text": "Census Report, Jaipur State",
            "author": "Munshi Govinda Sarana",
            "edition": "Munshi Govinda Sarana, Newul Kishore Press, Lucknow, 1903",
            "verse": "Sitla Ashtami among Jaipur's March festivals",
            "page": "356",
        },
        {
            **VRATARAJA,
            "verse": "the Shravana Shitala-saptami and the goddess's image, not this day",
            "page": "f. 110",
        },
        {
            **SOURCE,
            "verse": "the Bhadrapada (purnimanta) Shitala-vrata, not this day",
            "page": "183",
        },
    ],
    # s35: the texts give this night Lakshmi at pradosha and Alakshmi driven out, never Kali.
    "kali-puja": [
        {
            **TITHI_TATTVA,
            "text": "Tithi-tattva (Raghunandana)",
            "verse": "Lakshmi at pradosha on the Sukharatri, and torches for the ancestors",
            "page": "185–186",
        },
        {
            **SOURCE,
            "verse": "Lakshmi at pradosha; the Divodāsīya's Amavasya at pradosha and midnight",
            "page": "299–300",
        },
        {**DS, "verse": "Alakshmi driven out of the house-yards after midnight", "page": "77"},
    ],
    "ahoi-ashtami": [
        {
            **DS,
            "verse": "a bath in Radha-kunda on this Ashtami, for those who live near Mathura",
            "page": "76",
        },
    ],
}
RITE_SOURCES = {
    "karva-chauth": VRATARAJA,
    "akshaya-tritiya": {**VRATARAJA, "page": "ff. 43–44"},
    "parashurama-jayanti": {**VRATARAJA, "page": "f. 43"},
    "vasanta-panchami": {**VRATARAJA, "page": "f. 103"},
    "ratha-saptami": {**VRATARAJA, "page": "f. 115"},
    "sawan-somvar": {**VRATARAJA, "page": "ff. 347–354"},
    "hartalika-teej": {**VRATARAJA, "page": "ff. 48–52"},
    "gangaur": {**VRATARAJA, "page": "f. 38"},
    "skanda-sashti": {**VRATARAJA, "page": "f. 108"},
}
# NS p. 149 quotes the Skanda from the Tithi-tattva (part 1, p. 29).
TT_RATHA = {**TITHI_TATTVA, "text": "Tithi-tattva (Raghunandana), quoting the Skanda", "page": "29"}


MC_140 = {
    "text": "Muhūrta-cintāmaṇi",
    "verse": "1.40, with the Śīghrabodha in the commentary",
    "edition": (
        "Rāma Daivajña (1600), with the Pīyūṣadhārā commentary of Govinda Daivajña (1603), "
        "1945 printing; the 1925 printing has the same page numbers"
    ),
    "page": "33–34",
}


@lru_cache(maxsize=32)
def _one_place(kind: str, year: int, ayanamsa: str) -> tuple[list[dict], dict]:
    """A one-place kind's year, once per Lambda container: bundles ask for it city by city."""
    return YEARLY[kind](EkadashiQuery(year=year, lat=0, lon=0, tz="UTC", ayanamsa=ayanamsa))


def festival(kind: str, q: EkadashiQuery) -> dict:
    num, build, pages, ds_pages = FESTIVALS[kind]
    extra: dict = {}
    if kind == "sawan-somvar":
        rows, extra["shravana"] = _sawan(q)
    elif kind in ONE_PLACE:
        rows, extra = copy.deepcopy(_one_place(kind, q.year, q.ayanamsa))
    elif kind in YEARLY:
        rows, extra = YEARLY[kind](q)
    else:
        rows = _year(q, num, build)
    also = {**DS, "verse": kind, "page": ds_pages} if ds_pages else None
    if kind in POPULAR:
        source = None
        extra["context"] = CONTEXT.get(kind, [])
    elif kind == "pongal":
        source = SEWELL_DIKSHIT
        also = {**SOURCE, "verse": "the southern usage of a night Makara ingress", "page": "326"}
        extra["context"] = CONTEXT["pongal"]
    elif kind == "tamil-new-year":
        source = SEWELL_DIKSHIT
        also = {
            **KALA_SANKALITA,
            "verse": "Varsharumbum, the solar year's beginning",
            "page": "402",
        }
        extra["context"] = CONTEXT["tamil-new-year"]
    elif kind == "holashtak":
        source = MC_140
    elif kind == "durga-puja":
        source = {**TITHI_TATTVA, "text": "Tithi-tattva (Raghunandana)", "page": "73–92"}
        extra["computedAt"] = KOLKATA  # the days; instants and rites are local
    elif pages is None:  # Dharmasindhu alone
        source, also = also, None
    else:
        source = {**SOURCE, "verse": kind, "page": pages}
    if kind == "rath-yatra":
        also = TT_RATHA
    return {
        "year": q.year,
        "festival": kind,
        "basis": "popular_practice" if kind in POPULAR else "text",
        "occurrences": rows,
        **extra,
        "source": source,
        "alsoSource": also,
        **({"riteSource": RITE_SOURCES[kind]} if kind in RITE_SOURCES else {}),
        "engine": provenance(q.ayanamsa),
    }
