"""GET /v1/observances/ekadashi: each Ekadashi of a year at a place, with the
Smarta and Vaishnava fast days.

Rules from docs/sources/observances.md: Kamalakara Bhatta, Nirnaya-sindhu
(1612), 1898 printing with Jvalaprasada Misra's Hindi tika, Ekadashi-nirnaya,
pp. 49-63 ("NS").

Smarta (Daśamī at sunrise is the test; NS pp. 58-63):
  - the day with Ekadashi at sunrise;
  - Ekadashi at two sunrises: householders the first day, ascetics the second
    (Skanda, p. 59); with Dvadashi also at two sunrises, everyone the second
    (Narada, Madhava, pp. 59-60);
  - only Dvadashi at two sunrises: the first day (Madhava, p. 60);
  - Ekadashi at no sunrise (pierced by Dashami): the next day, unless the next
    day has no Dvadashi at all, then the pierced day (Skanda, Rsyasrnga, pp. 60, 62).
Vaishnava (NS, after Madhava; not the Gaudiya Hari-bhakti-vilasa rules):
  - Dashami at any moment of the 96 minutes before sunrise pierces the day:
    the next day (Garuda; Skanda via Madhava, p. 53);
  - Ekadashi or Dvadashi at two sunrises: the later day (Madhava, p. 59).
Our reading: a tithi "increases" when it is current at two consecutive sunrises.
"""

from __future__ import annotations

import datetime as dt

from jyotisha import muhurta as Mu
from jyotisha.ephemeris import _rise_set, sunrise

from .errors import unsupported_location
from .fmt import provenance
from .ids import MASA_IDS, tithi_id
from .models import EkadashiQuery
from .timeutil import aware, iso, local_jd

ARUNODAYA = 96 / 1440  # 4 ghatikas before sunrise, in days (NS p. 53)
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
    e_inc, dv_inc = len(ek) >= 2, len(dv) >= 2

    ascetic = None
    if e is None:
        if dv:
            smarta, s_rule = 1, "pierced_next_day"
        else:
            smarta, s_rule = 0, "no_dvadashi_next_day"
    elif e_inc and dv_inc:
        smarta, s_rule = e + 1, "both_increase"
    elif e_inc:
        smarta, s_rule, ascetic = e, "ekadashi_increases", e + 1
    elif dv_inc:
        smarta, s_rule = e, "dvadashi_increases"
    else:
        smarta, s_rule = e, "sunrise"

    dawn = s[e] - ARUNODAYA if e is not None else None
    pierced = dawn is not None and start > dawn
    if e is None:
        vaishnava, v_rule = 1, "pierced_next_day"
    elif pierced:
        vaishnava, v_rule = e + 1, "arunodaya_pierced"
    elif e_inc or dv_inc:
        vaishnava, v_rule = e + 1, "increase"
    else:
        vaishnava, v_rule = e, "pure"

    lunar = Mu.lunar_month(s[1], q.ayanamsa)
    masa = Mu.MASA.index(lunar.name)
    num = Mu.tithi_at(start + 1e-6, q.ayanamsa)
    last = max(smarta, vaishnava, ascetic or 0) + 1
    return {
        "paksha": EKADASHI[num],
        "lunarMonth": {
            "amanta": MASA_IDS[masa],
            "purnimanta": MASA_IDS[(masa + 1) % 12] if num > 15 else MASA_IDS[masa],
            "adhika": lunar.adhika,
        },
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


def ekadashi(q: EkadashiQuery) -> dict:
    zone, ay = q.tz, q.ayanamsa
    first = local_jd(dt.date(q.year, 1, 1), 0.0, zone, "year")
    last = local_jd(dt.date(q.year, 12, 31), 23.99, zone, "year")
    # Every tithi change from a little before the year to a little after it.
    edges = Mu._scan(lambda t: Mu.tithi_at(t, ay), first - 4, last + 4, 0.25)
    out = []
    try:
        for i, (jd, num) in enumerate(edges):
            if num not in EKADASHI or i + 2 >= len(edges):
                continue
            row = _one(jd, edges[i + 1][0], edges[i + 2][0], q)
            dates = (row["smarta"]["date"], row["vaishnava"]["date"])
            if any(d[:4] == str(q.year) for d in dates):
                out.append(row)
    except RuntimeError as exc:
        raise unsupported_location(
            "the Sun does not rise on a day needed here; Ekadashi days cannot be formed"
        ) from exc
    return {"year": q.year, "ekadashis": out, "source": SOURCE, "engine": provenance(ay)}
