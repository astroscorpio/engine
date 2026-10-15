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
from jyotisha.ephemeris import _rise_set, sunrise

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

NS_73 = {**SOURCE, "verse": "Purnima-nirnaya; Darsha-shraddha-kala", "page": "72-73, 81-82"}
YAMAS = 3  # NS p. 82: "three yamas or more on the next day"


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
    row = {
        "paksha": "shukla" if num <= 15 else "krishna",
        "lunarMonth": _lunar(s[1], num, q),
        "tithi": {"start": iso(start, zone), "end": iso(end, zone)},
        "vrata": {
            "date": day[vrata],
            "rule": rule,
            "earlierDate": day[earlier] if earlier is not None and earlier != vrata else None,
        },
    }
    if num == 30:
        # NS p. 81: the Amavasya covering the aparahna, the last third of the daytime.
        candidates = range(0, (held[-1] if held else 0) + 1)
        aparahna = []
        for i in candidates:
            sr, ss = s[i], _sunset(s[i], q)
            a0, a1 = sr + 2 * (ss - sr) / 3, ss
            aparahna.append((i, a0, a1, _overlap(start, end, a0, a1) / (a1 - a0), ss - sr))
        full = [i for i, _, _, c, _ in aparahna if c >= 1 - 1e-9]
        later, daylen = aparahna[-1][0], aparahna[-1][4]
        if full:
            shraddha, s_rule = full[0], "full_aparahna"
        elif end >= s[later] + YAMAS * daylen / 4 and later > 0:
            shraddha, s_rule = later, "growing_three_yamas"
        else:
            shraddha, s_rule = max(later - 1, 0), "shrinking_earlier"
        last = max(last, later)
        row["shraddha"] = {
            "date": day[shraddha],
            "rule": s_rule,
            "aparahna": [
                {
                    "date": day[i],
                    "start": iso(a0, zone),
                    "end": iso(a1, zone),
                    "covered": round(c, 3),
                }
                for i, a0, a1, c, _ in aparahna
            ],
        }
        row["differs"] = row["shraddha"]["date"] != row["vrata"]["date"]
    row["days"] = [
        {
            "date": day[i],
            "sunrise": iso(s[i], zone),
            "tithiAtSunrise": tithi_id(Mu.tithi_at(s[i], q.ayanamsa)),
        }
        for i in range(last + 1)
    ]
    return row


def _pradosha_window(sunrise_jd: float, q: EkadashiQuery) -> tuple[float, float]:
    """Three muhurtas after sunset, a muhurta being a fifteenth of the night."""
    ss = _sunset(sunrise_jd, q)
    nr = _rise_set(ss + 0.01, q.lat, q.lon, True)
    return ss, ss + 3 * (nr - ss) / 15


def _pradosha(start: float, end: float, _next_end: float, q: EkadashiQuery) -> dict:
    """NS p. 72 footnote: the Trayodashi covering pradosha. Both or neither: the
    later day, with Mayukha's earlier day (after Sumantu) as a variant."""
    zone = q.tz
    s = _sunrises(start, q.lat, q.lon, 3)  # the day it begins and the next
    day = [aware(t, zone).date().isoformat() for t in s]
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    rows, covers = [], []
    for i in (0, 1):
        p0, p1 = _pradosha_window(s[i], q)
        covered = _overlap(start, end, p0, p1) / (p1 - p0)
        covers.append(covered >= 1 - 1e-9)
        rows.append(
            {
                "date": day[i],
                "vara": VARA_ID[P.VARA_LORDS[P.vara_index(s[i], q.lon, q.tz)]],
                "pradosha": {"start": iso(p0, zone), "end": iso(p1, zone)},
                "covered": round(covered, 3),
            }
        )
    if covers == [True, False]:
        chosen, rule, variant = 0, "covers_pradosha", None
    elif covers == [False, True]:
        chosen, rule, variant = 1, "covers_pradosha", None
    else:
        chosen, variant = 1, 0
        rule = "both_covered_later" if all(covers) else "neither_covered_later"
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
