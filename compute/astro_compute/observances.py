"""GET /v1/observances/ekadashi: each Ekadashi of a year at a place, with the
Smarta and Vaishnava fast days.

Rules from docs/sources/observances.md: Kamalakara Bhatta, Nirnaya-sindhu
(1612), 1898 printing with Jvalaprasada Misra's Hindi tika, Ekadashi-nirnaya,
pp. 49-63 ("NS").

Smarta (Daśamī at sunrise is the test; NS pp. 58-63):
  - the day with Ekadashi at sunrise;
  - Ekadashi long (still current at the second day's sunrise): householders the
    first day, ascetics the second (Skanda, p. 59); with Dvadashi long too (still
    current at the third day's sunrise), everyone the second (Narada, Madhava,
    pp. 59-60);
  - only Dvadashi long: the first day (Madhava, p. 60);
  - Ekadashi at no sunrise, pierced by Dashami at the first (Hemadri's
    viddha-nyuna), keyed on the Dvadashi:
      no Dvadashi at the next sunrise: everyone the pierced day (Skanda,
        Rsyasrnga, pp. 60, 62);
      Dvadashi over before the sunrise after that: householders the pierced day,
        ascetics and those seeking liberation the next (Madana-ratna; Madhava
        "grhinah purva, yater uttara", p. 62);
      Dvadashi still current at that sunrise: everyone the next day (p. 60).
    NS's "sama" Dvadashi (ending exactly at that sunrise) has no width in
    continuous time and is not computed.
Vaishnava (NS, after Madhava; not the Gaudiya Hari-bhakti-vilasa rules):
  - Dashami at any moment of the 96 minutes before sunrise pierces the day:
    the next day (Garuda; Skanda via Madhava, p. 53);
  - Ekadashi or Dvadashi long: the later day (Madhava, p. 59).
"Long" is measured from the first Ekadashi day (pure, or the pierced day when
Ekadashi touches no sunrise), as research reads NS pp. 59-62.
"""

from __future__ import annotations

import datetime as dt

from jyotisha import muhurta as Mu
from jyotisha import panchanga as P
from jyotisha.ephemeris import _rise_set, moon_rise_set, sunrise

from .errors import unsupported_location
from .fmt import provenance
from .ids import MASA_IDS, VARA_ID, tithi_id
from .models import EkadashiQuery
from .timeutil import aware, iso, local_jd

ARUNODAYA = 96 / 1440  # 4 ghatikas before sunrise, in days (NS p. 53)

# Names from the Ekadashi-mahatmya with bhasha-tika (Banaras, 1934), by folio,
# keyed by the purnimanta month and paksha as the text names them
# (docs/sources/ekadashi-names.md). (name, other names in the text, a name printed
# in Nirnaya-sindhu's 1898 commentary, the popular name where it differs, folio)
EM = {
    "text": "Ekadashi-mahatmya, bhasha-tika sahita",
    "edition": "Babu Baijnath Prasad, Banaras, 1934",
}
NS_P51 = "Nirnaya-sindhu, 1898, p. 51 (Hindi commentary)"
EKADASHI_NAMES = {
    "margashirsha_krishna": (None, (), None, "Utpannā", "f. 1, 11b"),
    "margashirsha_shukla": ("Mokṣā", (), None, "Mokṣadā", "f. 18"),
    "pausha_krishna": ("Saphalā", (), None, None, "f. 18b"),
    "pausha_shukla": ("Putradā", (), None, None, "f. 24b"),
    "magha_krishna": ("Ṣaṭtilā", (), None, None, "f. 36b"),
    "magha_shukla": ("Jayā", (), None, None, "f. 37"),
    "phalguna_krishna": ("Vijayā", (), None, None, "f. 43"),
    "phalguna_shukla": ("Āmalakī", (), None, None, "f. 47b"),
    "chaitra_krishna": ("Pāpamocanī", (), None, None, "f. 54"),
    "chaitra_shukla": ("Kāmadā", (), None, None, "f. 59b"),
    "vaishakha_krishna": ("Varūthinī", (), None, None, "f. 64"),
    "vaishakha_shukla": ("Mohinī", (), None, None, "f. 67b"),
    "jyeshtha_krishna": ("Aparā", (), None, None, "f. 71b"),
    "jyeshtha_shukla": ("Nirjalā", (), None, None, "f. 80"),
    "ashadha_krishna": ("Yoginī", (), None, None, "f. 80b"),
    "ashadha_shukla": ("Padmā", ("Śayanī",), "Devaśayanī", None, "f. 84b, 109"),
    "shravana_krishna": ("Kāmikā", (), None, None, "f. 109b"),
    "shravana_shukla": ("Putradā", (), None, None, "f. 116b"),
    "bhadrapada_krishna": ("Ajā", (), None, None, "f. 117b"),
    "bhadrapada_shukla": ("Parivartinī", ("Vāmanā", "Jayantī"), None, "Pārśva", "f. 120, 124"),
    "ashwin_krishna": ("Indirā", (), None, None, "f. 124b"),
    "ashwin_shukla": ("Pāśāṅkuśā", (), None, "Pāpāṅkuśā", "f. 128b"),
    "kartika_krishna": ("Ramā", (), None, None, "f. 131"),
    "kartika_shukla": ("Prabodhinī", ("Hari-bodhinī",), "Devotthāna", "Dev Uthānī", "f. 137"),
    "adhika_shukla": ("Padminī", (), None, None, "f. 146b"),
    "adhika_krishna": ("Paramā", (), None, None, "f. 155"),
}
NAME_NOTES = {
    "margashirsha_krishna": (
        "The text names none; its chapter tells the birth (utpatti) of Ekadashi."
    ),
}


def name_id(purnimanta: str, paksha: str, adhika: bool) -> str:
    return f"adhika_{paksha}" if adhika else f"{purnimanta}_{paksha}"


EKADASHI = {11: "shukla", 26: "krishna"}
SOURCE = {
    "text": "Nirnaya-sindhu",
    "verse": "Ekadashi-nirnaya, pariccheda 1",
    "edition": "Kamalakara Bhatta, with Jvalaprasada Misra's Hindi tika, 1898",
    "page": "49-63",
}


def _sunrises(first: float, lat: float, lon: float, n: int) -> list[float]:
    """The sunrise at or before `first`, then the next n - 1."""
    out = [sunrise(first, lat, lon)]
    while len(out) < n:
        out.append(_rise_set(out[-1] + 0.1, lat, lon, True))
    return out


def _one(start: float, end: float, dv_end: float, q: EkadashiQuery) -> dict:
    zone = q.tz
    s = _sunrises(start, q.lat, q.lon, 5)  # s[0] <= start < s[1]
    day = [aware(t, zone).date().isoformat() for t in s]

    def at_sunrise(t0: float, t1: float) -> list[int]:
        return [i for i, t in enumerate(s) if t0 <= t < t1]

    ek, dv = at_sunrise(start, end), at_sunrise(end, dv_end)
    e = ek[0] if ek else None  # always s[1] when it exists
    # The first Ekadashi day: pure (Ekadashi at its sunrise) or, at no sunrise,
    # the pierced day. A tithi runs long when it is still current at the sunrise
    # after its own day: Ekadashi at the second day's, Dvadashi at the third's.
    first = e if e is not None else 0
    e_inc = len(ek) >= 2
    dv_long = dv_end > s[first + 2]

    ascetic = None
    if e is None:  # over before s[1]: pierced at s[0] and short
        if not dv:
            smarta, s_rule = 0, "no_dvadashi_next_day"
        elif not dv_long:
            smarta, s_rule, ascetic = 0, "viddha_nyuna_householders_first", 1
        else:
            smarta, s_rule = 1, "viddha_nyuna_dvadashi_long"
    elif e_inc and dv_long:
        smarta, s_rule = e + 1, "both_increase"
    elif e_inc:
        smarta, s_rule, ascetic = e, "ekadashi_increases", e + 1
    elif dv_long:
        smarta, s_rule = e, "dvadashi_increases"
    else:
        smarta, s_rule = e, "sunrise"

    dawn = s[e] - ARUNODAYA if e is not None else None
    pierced = dawn is not None and start > dawn
    if e is None:
        vaishnava, v_rule = 1, "pierced_next_day"
    elif pierced:
        vaishnava, v_rule = e + 1, "arunodaya_pierced"
    elif e_inc or dv_long:
        vaishnava, v_rule = e + 1, "increase"
    else:
        vaishnava, v_rule = e, "pure"

    lunar = Mu.lunar_month(s[1], q.ayanamsa)
    masa = Mu.MASA.index(lunar.name)
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    last = max(smarta, vaishnava, ascetic or 0) + 1
    purnimanta = MASA_IDS[(masa + 1) % 12] if num > 15 else MASA_IDS[masa]
    nid = name_id(purnimanta, EKADASHI[num], lunar.adhika)
    name, others, printed, popular, folio = EKADASHI_NAMES[nid]
    return {
        "paksha": EKADASHI[num],
        "lunarMonth": {"amanta": MASA_IDS[masa], "purnimanta": purnimanta, "adhika": lunar.adhika},
        "nameId": nid,
        "name": name,
        "otherNames": list(others),
        "alsoPrinted": {"name": printed, "source": NS_P51} if printed else None,
        "popularName": popular,
        "nameSource": {**EM, "verse": None, "page": folio},
        "nameNote": NAME_NOTES.get(nid),
        "tithi": {"start": iso(start, zone), "end": iso(end, zone)},
        "dvadashiEnd": iso(dv_end, zone),
        "days": [
            {
                "date": day[i],
                "sunrise": iso(s[i], zone),
                "tithiAtSunrise": tithi_id(Mu.tithi_at(s[i], q.ayanamsa)),
            }
            for i in range(last + 1)
        ],
        "smarta": {
            "date": day[smarta],
            "asceticDate": day[ascetic] if ascetic is not None else None,
            "rule": s_rule,
        },
        "vaishnava": {
            "date": day[vaishnava],
            "rule": v_rule,
            "arunodaya": iso(dawn, zone) if dawn is not None else None,
            "dashamiAtArunodaya": pierced,
        },
        "differs": day[smarta] != day[vaishnava],
    }


def _edges(q: EkadashiQuery) -> list[tuple[float, int]]:
    """Every tithi change from a little before the year to a little after it."""
    first = local_jd(dt.date(q.year, 1, 1), 0.0, q.tz, "year")
    last = local_jd(dt.date(q.year, 12, 31), 23.99, q.tz, "year")
    return Mu._scan(lambda t: Mu.tithi_at(t, q.ayanamsa), first - 4, last + 4, 0.25)


def _collect(q: EkadashiQuery, targets, build, dates_of) -> list[dict]:
    edges = _edges(q)
    out = []
    try:
        for i, (jd, num) in enumerate(edges):
            if num in targets and i + 2 < len(edges):
                row = build(jd, edges[i + 1][0], edges[i + 2][0], q)
                if any(d and d[:4] == str(q.year) for d in dates_of(row)):
                    out.append(row)
    except RuntimeError as exc:
        raise unsupported_location(
            "the Sun does not rise on a day needed here; the observance days cannot be formed"
        ) from exc
    return out


def ekadashi(q: EkadashiQuery) -> dict:
    rows = _collect(q, EKADASHI, _one, lambda r: (r["smarta"]["date"], r["vaishnava"]["date"]))
    return {"year": q.year, "ekadashis": rows, "source": SOURCE, "engine": provenance(q.ayanamsa)}


# --- Purnima, Amavasya, Pradosha (docs/sources/observances.md s5, pradosha.md) -------

NS_73 = {**SOURCE, "verse": "Purnima-nirnaya; Darsha-shraddha-kala", "page": "72-73, 81-87"}
# observances.md s6: names a given Amavasya can carry (meta.amavasyaNames).
MAHALAYA_AMANTA = "bhadrapada"  # the dark fortnight after the Bhadrapada full moon (NS p. 215)
# NS p. 341 names a new moon by the amanta month it ends: its yugadi "Magha
# Amavasya" ends amanta Magha. The popular Mauni Amavasya is the one inside
# purnimanta Magha (amanta Pausha), a different new moon.
MAGHA = "magha"
WEEKDAY_NAMES = {"monday": "somavati", "tuesday": "bhauma", "saturday": "shani"}


def _vara(sunrise_jd: float, q) -> str:
    return VARA_ID[P.VARA_LORDS[P.vara_index(sunrise_jd, q.lon, q.tz)]]


def _lunar(jd: float, num: int, q: EkadashiQuery) -> dict:
    lunar = Mu.lunar_month(jd, q.ayanamsa)
    masa = Mu.MASA.index(lunar.name)
    return {
        "amanta": MASA_IDS[masa],
        "purnimanta": MASA_IDS[(masa + 1) % 12] if num > 15 else MASA_IDS[masa],
        "adhika": lunar.adhika,
    }


def _sunset(sunrise_jd: float, q: EkadashiQuery) -> float:
    return _rise_set(sunrise_jd + 0.05, q.lat, q.lon, False)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _full_or_new(start: float, end: float, _next_end: float, q: EkadashiQuery) -> dict:
    """NS p. 73: the vrata is kept on the later day, joined to the next Pratipada,
    never on the day joined to Chaturdashi, except the Savitri vrata."""
    zone = q.tz
    s = _sunrises(start, q.lat, q.lon, 4)  # s[0] <= start < s[1]
    day = [aware(t, zone).date().isoformat() for t in s]
    held = [i for i, t in enumerate(s) if start <= t < end]
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    if held:
        vrata, rule, earlier = held[-1], "later_day", 0
    else:
        vrata, rule, earlier = 0, "only_day", None
    last = vrata
    lunar = _lunar(s[1], num, q)
    vara = _vara(s[vrata], q)
    row = {
        "paksha": "shukla" if num <= 15 else "krishna",
        "lunarMonth": lunar,
        "tithi": {"start": iso(start, zone), "end": iso(end, zone)},
        "vrata": {
            "date": day[vrata],
            "vara": vara,
            "rule": rule,
            "earlierDate": day[earlier] if earlier is not None and earlier != vrata else None,
        },
    }
    if num == 30:
        names = []
        if lunar["amanta"] == MAHALAYA_AMANTA and not lunar["adhika"]:
            names.append("mahalaya")
        if lunar["amanta"] == MAGHA and not lunar["adhika"]:
            names.append("magha")
        if lunar["purnimanta"] == MAGHA and not lunar["adhika"]:
            names.append("mauni")
        if vara in WEEKDAY_NAMES:
            names.append(WEEKDAY_NAMES[vara])
        row["names"] = names
        last = max(last, _shraddha(row, start, end, s, len(held), q))
    row["days"] = [
        {
            "date": day[i],
            "sunrise": iso(s[i], zone),
            "tithiAtSunrise": tithi_id(Mu.tithi_at(s[i], q.ayanamsa)),
        }
        for i in range(last + 1)
    ]
    return row


def _kutapa_choice(spans: list[tuple], kshaya: bool) -> tuple[int, str]:
    """NS pp. 86-87, the kutapa (8th of the 15 day muhurtas, Matsya): the day it
    covers; partly on both, the day with more; equal, a shrinking Amavasya takes
    the earlier day and otherwise the later (Pracetas); covered on both, the later."""
    covered = [(i, c) for i, c in spans if c > 0]
    if not covered:
        return spans[-1][0], "kutapa_none_later"
    if len(covered) == 1:
        return covered[0][0], "kutapa_one_day"
    (i0, c0), (i1, c1) = covered[-2], covered[-1]
    if c0 >= 1 - 1e-9 and c1 >= 1 - 1e-9:
        return i1, "kutapa_tie_later"
    if abs(c0 - c1) > 1e-9:
        return (i0, "kutapa_more") if c0 > c1 else (i1, "kutapa_more")
    return (i0, "kutapa_tie_kshaya_earlier") if kshaya else (i1, "kutapa_tie_later")


def _shraddha(row: dict, start: float, end: float, s: list[float], held: int, q) -> int:
    """NS pp. 81-87: the Amavasya touching the aparahna (last third of the daytime)
    of one day; both, or neither, go to the kutapa. Returns the last day index used."""
    zone = q.tz
    day = [aware(t, zone).date().isoformat() for t in s]
    rows = []
    for i in range(held + 1):
        sr, ss = s[i], _sunset(s[i], q)
        span = ss - sr
        a0, k0 = sr + 2 * span / 3, sr + 7 * span / 15
        rows.append(
            (i, (a0, ss, _overlap(start, end, a0, ss) / (ss - a0)),
             (k0, k0 + span / 15, _overlap(start, end, k0, k0 + span / 15) / (span / 15)))
        )  # fmt: skip
    touched = [i for i, (_, _, c), _ in rows if c > 0]
    kutapa = [(i, k[2]) for i, _, k in rows]
    if len(touched) == 1:
        chosen, rule = touched[0], "aparahna"
    elif touched:
        chosen, _ = _kutapa_choice([(i, c) for i, c in kutapa if i in touched], held == 0)
        rule = "aparahna_both_kutapa"
    else:
        chosen, rule = _kutapa_choice(kutapa, held == 0)
    row["shraddha"] = {
        "date": day[chosen],
        "rule": rule,
        "aparahna": [
            {
                "date": day[i],
                "start": iso(a[0], zone),
                "end": iso(a[1], zone),
                "covered": round(a[2], 3),
            }
            for i, a, _ in rows
        ],
        "kutapa": [
            {
                "date": day[i],
                "start": iso(k[0], zone),
                "end": iso(k[1], zone),
                "covered": round(k[2], 3),
            }
            for i, _, k in rows
        ],
    }
    row["differs"] = row["shraddha"]["date"] != row["vrata"]["date"]
    return held


def _pradosha_window(sunrise_jd: float, q: EkadashiQuery) -> tuple[float, float]:
    """Three muhurtas after sunset, a muhurta being a fifteenth of the night."""
    ss = _sunset(sunrise_jd, q)
    nr = _rise_set(ss + 0.01, q.lat, q.lon, True)
    return ss, ss + 3 * (nr - ss) / 15


def _pradosha(start: float, end: float, _next_end: float, q: EkadashiQuery) -> dict:
    """NS p. 72 footnote: the Trayodashi covering pradosha. Covering both days or
    reaching neither, or touching both equally: the later day, with Mayukha's
    earlier day (after Sumantu) as a variant. Partly on both, unequally: the day
    with more of it (the other opinion NS records there)."""
    zone = q.tz
    s = _sunrises(start, q.lat, q.lon, 3)  # the day it begins and the next
    day = [aware(t, zone).date().isoformat() for t in s]
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    rows, covers = [], []
    for i in (0, 1):
        p0, p1 = _pradosha_window(s[i], q)
        covers.append(_overlap(start, end, p0, p1) / (p1 - p0))
        rows.append(
            {
                "date": day[i],
                "vara": VARA_ID[P.VARA_LORDS[P.vara_index(s[i], q.lon, q.tz)]],
                "pradosha": {"start": iso(p0, zone), "end": iso(p1, zone)},
                "covered": round(covers[-1], 3),
            }
        )
    full = [c >= 1 - 1e-9 for c in covers]
    variant = None
    if full[0] != full[1]:
        chosen, rule = full.index(True), "covers_pradosha"
    elif all(full):
        chosen, rule, variant = 1, "both_covered_later", 0
    elif covers == [0, 0]:
        chosen, rule, variant = 1, "neither_covered_later", 0
    elif abs(covers[0] - covers[1]) < 1e-9:
        chosen, rule, variant = 1, "equal_touch_later", 0
    else:
        chosen, rule = (0 if covers[0] > covers[1] else 1), "more_pradosha"
    return {
        "paksha": "shukla" if num <= 15 else "krishna",
        "lunarMonth": _lunar(s[0] if num <= 15 else s[1], num, q),
        "tithi": {"start": iso(start, zone), "end": iso(end, zone)},
        "days": rows,
        "date": day[chosen],
        "vara": rows[chosen]["vara"],
        "rule": rule,
        "variantDate": day[variant] if variant is not None else None,
    }


def _sankashti(start: float, end: float, _next_end: float, q: EkadashiQuery) -> dict:
    """NS p. 47, VM p. 38: the Chaturthi current at moonrise. At both moonrises:
    the earlier day (joined with Trtiya), others the later; at neither: the
    later day. Moonrise is the visible rise, upper limb with refraction (our
    convention: the texts do not say)."""
    zone = q.tz
    s = _sunrises(start, q.lat, q.lon, 3)
    day = [aware(t, zone).date().isoformat() for t in s]
    rows, current = [], []
    for i in (0, 1):
        rise, _ = moon_rise_set(s[i], s[i + 1], q.lat, q.lon, upper_limb=True)
        current.append(rise is not None and start <= rise < end)
        rows.append(
            {
                "date": day[i],
                "vara": _vara(s[i], q),
                "moonrise": iso(rise, zone) if rise is not None else None,
                "current": current[-1],
            }
        )
    variant = None
    if current == [True, False]:
        chosen, rule = 0, "moonrise"
    elif current == [False, True]:
        chosen, rule = 1, "moonrise"
    elif all(current):
        chosen, rule, variant = 0, "both_earlier", 1
    else:
        chosen, rule = 1, "neither_later"
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    return {
        "paksha": "krishna",
        "lunarMonth": _lunar(s[1], num, q),
        "tithi": {"start": iso(start, zone), "end": iso(end, zone)},
        "days": rows,
        "date": day[chosen],
        "vara": rows[chosen]["vara"],
        "moonrise": rows[chosen]["moonrise"],
        "rule": rule,
        "variantDate": day[variant] if variant is not None else None,
        "angaraki": rows[chosen]["vara"] == "tuesday",
    }


def sankashti(q: EkadashiQuery) -> dict:
    rows = _collect(q, {19}, _sankashti, lambda r: (r["date"],))
    source = {**SOURCE, "verse": "Sankashta-chaturthi", "page": "47"}
    return {"year": q.year, "occurrences": rows, "source": source, "engine": provenance(q.ayanamsa)}


def purnima(q: EkadashiQuery) -> dict:
    rows = _collect(q, {15}, _full_or_new, lambda r: (r["vrata"]["date"],))
    return {"year": q.year, "occurrences": rows, "source": NS_73, "engine": provenance(q.ayanamsa)}


def amavasya(q: EkadashiQuery) -> dict:
    rows = _collect(q, {30}, _full_or_new, lambda r: (r["vrata"]["date"], r["shraddha"]["date"]))
    return {"year": q.year, "occurrences": rows, "source": NS_73, "engine": provenance(q.ayanamsa)}


def pradosha(q: EkadashiQuery) -> dict:
    rows = _collect(q, {13, 28}, _pradosha, lambda r: (r["date"],))
    source = {**SOURCE, "verse": "Pradosha-vrata (footnote, Brahmottara-khanda)", "page": "72"}
    return {"year": q.year, "occurrences": rows, "source": source, "engine": provenance(q.ayanamsa)}
