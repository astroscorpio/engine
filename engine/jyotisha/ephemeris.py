"""Ephemeris layer: the only module that talks to Swiss Ephemeris.

Everything above this line is pure arithmetic on longitudes, so the whole
system can be re-run under a different ayanamsa -- or tropically -- by
changing one argument.  That is deliberate: the sidereal assumption is the
single largest untested input to every downstream claim.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe

type TimeZone = float | str | dt.tzinfo

_EPHEMERIS_PATH = os.environ.get("SE_EPHE_PATH")
if _EPHEMERIS_PATH:
    path = Path(_EPHEMERIS_PATH).expanduser()
    if not path.is_dir():
        raise ValueError(f"SE_EPHE_PATH is not a directory: {path}")
    swe.set_ephe_path(str(path))

SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]
SIGN_ABBR = [s[:3] for s in SIGNS]

NAKSHATRAS = [
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "P.Phalguni",
    "U.Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "P.Ashadha",
    "U.Ashadha",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "P.Bhadrapada",
    "U.Bhadrapada",
    "Revati",
]

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
SEVEN = GRAHAS[:7]

_BODIES = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
}

AYANAMSAS = {
    "lahiri": swe.SIDM_LAHIRI,
    "raman": swe.SIDM_RAMAN,
    "krishnamurti": swe.SIDM_KRISHNAMURTI,
    "true_citra": swe.SIDM_TRUE_CITRA,
    "true_revati": swe.SIDM_TRUE_REVATI,
    "yukteshwar": swe.SIDM_YUKTESHWAR,
    "suryasiddhanta": swe.SIDM_SURYASIDDHANTA,
    "fagan_bradley": swe.SIDM_FAGAN_BRADLEY,
    "tropical": None,  # no ayanamsa at all -- the falsification case
}

SIDEREAL_YEAR = 365.256363
# Dasha years are reckoned here as 365.2425 days, the Gregorian mean year.
# Conventions differ (365.25 Julian, 365.2422 tropical, 360 savana), so any
# published method statement must quote this value.
DASHA_YEAR = 365.2425


@dataclass(frozen=True)
class Position:
    name: str
    longitude: float
    speed: float = 0.0
    latitude: float = 0.0

    # These are pure functions of the immutable fields and are read millions of
    # times per backtest, so they are memoised per instance. ``cached_property``
    # writes straight into ``__dict__``, which frozen dataclasses still have,
    # and subsequent reads resolve as plain attribute lookups.
    @cached_property
    def sign(self) -> int:
        return int(self.longitude // 30) % 12

    @cached_property
    def degree(self) -> float:
        return self.longitude % 30

    @cached_property
    def retrograde(self) -> bool:
        return self.speed < 0

    @cached_property
    def nakshatra(self) -> int:
        return int(self.longitude // (360 / 27)) % 27

    @cached_property
    def pada(self) -> int:
        return int((self.longitude % (360 / 27)) // (360 / 108)) + 1

    def __str__(self) -> str:
        d = self.degree
        m = (d % 1) * 60
        return f"{SIGN_ABBR[self.sign]} {int(d):2d}°{int(m):02d}'{'R' if self.retrograde else ' '}"


def set_ayanamsa(name: str) -> int | None:
    try:
        mode = AYANAMSAS[name]
    except KeyError as exc:
        valid = ", ".join(sorted(AYANAMSAS))
        raise ValueError(f"unknown ayanamsa {name!r}; choose one of: {valid}") from exc
    if mode is not None:
        swe.set_sid_mode(mode)
    return mode


def _flags(mode: int | None) -> int:
    base = swe.FLG_SWIEPH | swe.FLG_SPEED
    return base | (swe.FLG_SIDEREAL if mode is not None else 0)


def backend_info(jd_ut: float = 2451545.0) -> dict:
    """Report the backend Swiss Ephemeris actually selected."""
    _, returned = swe.calc_ut(jd_ut, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SPEED)
    if returned & swe.FLG_JPLEPH:
        backend = "jpl"
    elif returned & swe.FLG_SWIEPH:
        backend = "swiss-files"
    elif returned & swe.FLG_MOSEPH:
        backend = "moshier"
    else:
        backend = "unknown"
    return {
        "swisseph_version": swe.version,
        "python_extension": swe.get_library_path(),
        "ephemeris_path": _EPHEMERIS_PATH or "",
        "requested": "swiss-files",
        "actual": backend,
        "returned_flags": returned,
    }


def positions(jd_ut: float, ayanamsa: str = "lahiri", node: str = "true") -> dict[str, Position]:
    """Sidereal (or tropical) longitudes of the nine grahas at jd_ut."""
    if node not in {"true", "mean"}:
        raise ValueError("node must be 'true' or 'mean'")
    mode = set_ayanamsa(ayanamsa)
    flags = _flags(mode)
    out: dict[str, Position] = {}
    for name, body in _BODIES.items():
        v = swe.calc_ut(jd_ut, body, flags)[0]
        out[name] = Position(name, v[0] % 360, v[3], v[1])
    node_body = swe.TRUE_NODE if node == "true" else swe.MEAN_NODE
    v = swe.calc_ut(jd_ut, node_body, flags)[0]
    out["Rahu"] = Position("Rahu", v[0] % 360, v[3], v[1])
    out["Ketu"] = Position("Ketu", (v[0] + 180) % 360, v[3], -v[1])
    return out


def luminaries(jd_ut: float, ayanamsa: str = "lahiri") -> tuple[Position, Position]:
    """Sun and Moon only, computed exactly as positions() computes them.

    Tithi, nakshatra, yoga and karana read nothing else, and the panchanga
    scans call them a few hundred times a day; skipping the other seven
    bodies makes those scans about four times cheaper.
    """
    flags = _flags(set_ayanamsa(ayanamsa))
    s = swe.calc_ut(jd_ut, swe.SUN, flags)[0]
    m = swe.calc_ut(jd_ut, swe.MOON, flags)[0]
    return Position("Sun", s[0] % 360, s[3], s[1]), Position("Moon", m[0] % 360, m[3], m[1])


def ascendant(
    jd_ut: float, lat: float, lon_east: float, ayanamsa: str = "lahiri", system: bytes = b"W"
) -> tuple[Position, list[float]]:
    """Ascendant plus the cusp list for the requested house system.

    Whole-sign (``W``) is the Parashari default; Placidus (``P``) is offered
    only so bhava-chalita and Western comparisons remain possible.
    """
    if not -90 <= lat <= 90:
        raise ValueError("latitude must be in [-90, 90]")
    if not -180 <= lon_east <= 180:
        raise ValueError("longitude must be in [-180, 180]")
    mode = set_ayanamsa(ayanamsa)
    flags = swe.FLG_SIDEREAL if mode is not None else 0
    cusps, ascmc = swe.houses_ex(jd_ut, lat, lon_east, system, flags)
    return Position("Ascendant", ascmc[0] % 360), list(cusps)


def ayanamsa_value(jd_ut: float, name: str = "lahiri") -> float:
    mode = set_ayanamsa(name)
    return 0.0 if mode is None else swe.get_ayanamsa_ut(jd_ut)


# --- time -------------------------------------------------------------------


def _tzinfo(zone: TimeZone) -> dt.tzinfo:
    if isinstance(zone, dt.tzinfo):
        return zone
    if isinstance(zone, str):
        try:
            return ZoneInfo(zone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone {zone!r}") from exc
    return dt.timezone(dt.timedelta(hours=float(zone)))


def _localize(value: dt.datetime, zone: TimeZone) -> dt.datetime:
    """Attach a zone while rejecting ambiguous or nonexistent wall times."""
    timezone = _tzinfo(zone)
    if not isinstance(timezone, ZoneInfo):
        return value.replace(tzinfo=timezone)
    candidates = []
    for fold in (0, 1):
        candidate = value.replace(tzinfo=timezone, fold=fold)
        round_trip = candidate.astimezone(dt.UTC).astimezone(timezone)
        if round_trip.replace(tzinfo=None) == value and all(
            existing.astimezone(dt.UTC) != candidate.astimezone(dt.UTC) for existing in candidates
        ):
            candidates.append(candidate)
    if not candidates:
        raise ValueError(f"nonexistent local time {value.isoformat(sep=' ')} in {timezone.key}")
    if len(candidates) > 1:
        raise ValueError(
            f"ambiguous local time {value.isoformat(sep=' ')} in {timezone.key}; "
            "supply an explicit UTC offset"
        )
    return candidates[0]


def now(zone: TimeZone = 0.0) -> dt.datetime:
    """Current aware civil datetime in ``zone``."""
    return dt.datetime.now(tz=_tzinfo(zone))


def jd(year: int, month: int, day: int, hour: float = 0.0, tz_offset: TimeZone = 0.0) -> float:
    """Julian Day (UT) from a local civil datetime."""
    naive = dt.datetime(year, month, day) + dt.timedelta(hours=hour)
    local = _localize(naive, tz_offset)
    utc = local.astimezone(dt.UTC)
    utc_hour = utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3_600_000_000
    return swe.julday(utc.year, utc.month, utc.day, utc_hour)


def parse(stamp: str, tz_offset: TimeZone = 0.0, *, date_hour: float = 12.0) -> float:
    """Civil timestamp to JD(UT).

    Naive timestamps are interpreted in ``tz_offset``. ISO timestamps carrying
    ``Z`` or a numeric UTC offset use that explicit offset. Date-only values
    use ``date_hour`` (noon by default).
    """
    stamp = stamp.strip()
    date_only = len(stamp) == 10 and stamp[4] == "-" and stamp[7] == "-"
    if date_only:
        t = dt.date.fromisoformat(stamp)
        return jd(t.year, t.month, t.day, date_hour, tz_offset)
    iso = stamp.replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(iso)
    except ValueError as exc:
        raise ValueError(
            f"invalid timestamp {stamp!r}; use YYYY-MM-DD, YYYY-MM-DD HH:MM[:SS], or ISO-8601"
        ) from exc
    if t.tzinfo is None:
        t = _localize(t, tz_offset)
    utc = t.astimezone(dt.UTC)
    hour = utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3_600_000_000
    return swe.julday(utc.year, utc.month, utc.day, hour)


def to_datetime(jd_ut: float, tz_offset: TimeZone = 0.0) -> dt.datetime:
    y, m, d, h = swe.revjul(jd_ut)
    # revjul carries floating noise near exact minute/day boundaries.
    utc = dt.datetime(y, m, d, tzinfo=dt.UTC) + dt.timedelta(milliseconds=round(h * 3_600_000))
    return utc.astimezone(_tzinfo(tz_offset))


def fmt(jd_ut: float, tz_offset: TimeZone = 0.0, with_time: bool = False) -> str:
    t = to_datetime(jd_ut, tz_offset)
    return t.strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y")


def _rise_set(jd_ut: float, lat: float, lon_east: float, rising: bool):
    rsmi = (swe.CALC_RISE if rising else swe.CALC_SET) | swe.BIT_DISC_CENTER
    res, tret = swe.rise_trans(jd_ut, swe.SUN, rsmi, (lon_east, lat, 0.0))
    if res != 0:
        event = "sunrise" if rising else "sunset"
        raise RuntimeError(f"Swiss Ephemeris found no {event} after JD {jd_ut:.5f}")
    return tret[0]


def sunrise(jd_ut: float, lat: float, lon_east: float) -> float:
    """JD(UT) of the sunrise at or before jd_ut -- the Vedic day boundary."""
    # Searching from exactly one day back overshoots to the coming sunrise
    # when jd_ut sits in the minute or two before sunrise and sunrise is
    # drifting later day by day; start further back and walk forward instead.
    t = _rise_set(jd_ut - 1.5, lat, lon_east, True)
    while (nxt := _rise_set(t + 0.1, lat, lon_east, True)) <= jd_ut:
        t = nxt
    return t


def next_sunrise(jd_ut: float, lat: float, lon_east: float) -> float:
    return _rise_set(sunrise(jd_ut, lat, lon_east) + 0.1, lat, lon_east, True)


def moon_rise_set(
    start_jd: float, end_jd: float, lat: float, lon_east: float
) -> tuple[float | None, float | None]:
    """First moonrise and first moonset inside [start_jd, end_jd), or None.

    Disc centre with refraction, the same convention as the sunrise above.
    The Moon skips one rising (and one setting) roughly every month, so a
    civil day without either is normal, not an error.
    """
    out = []
    for flag in (swe.CALC_RISE, swe.CALC_SET):
        res, tret = swe.rise_trans(
            start_jd, swe.MOON, flag | swe.BIT_DISC_CENTER, (lon_east, lat, 0.0)
        )
        t = tret[0]
        out.append(t if res == 0 and start_jd <= t < end_jd else None)
    return out[0], out[1]


def station_dates(
    body: str, start_jd: float, end_jd: float, ayanamsa: str = "lahiri", step: float = 0.5
) -> list[dict]:
    """Retrograde/direct stations by sign change of daily speed."""
    if end_jd <= start_jd:
        raise ValueError("station search end must follow start")
    if step <= 0:
        raise ValueError("station search step must be positive")
    mode = set_ayanamsa(ayanamsa)
    flags = _flags(mode)
    code = _BODIES.get(body)
    if code is None:
        raise ValueError(f"stations are unsupported for {body!r}")
    out, t, prev = [], start_jd, None
    while t <= end_jd:
        v = swe.calc_ut(t, code, flags)[0]
        speed = v[3]
        if prev is not None and (prev[1] > 0) != (speed > 0):
            lo, hi = prev[0], t
            for _ in range(40):
                mid = (lo + hi) / 2
                s = swe.calc_ut(mid, code, flags)[0][3]
                if (s > 0) == (prev[1] > 0):
                    lo = mid
                else:
                    hi = mid
            v_mid = swe.calc_ut((lo + hi) / 2, code, flags)[0]
            out.append(
                {
                    "jd": (lo + hi) / 2,
                    "longitude": v_mid[0] % 360,
                    "direction": "retrograde" if speed < 0 else "direct",
                }
            )
        prev = (t, speed)
        t += step
    return out


def ingress_dates(
    body: str,
    start_jd: float,
    end_jd: float,
    ayanamsa: str = "lahiri",
    step: float = 1.0,
    *,
    node: str = "true",
) -> list[dict]:
    """Sign-ingress moments, bisected to about a minute."""
    if end_jd <= start_jd:
        raise ValueError("ingress search end must follow start")
    if step <= 0:
        raise ValueError("ingress search step must be positive")
    if node not in {"true", "mean"}:
        raise ValueError("node must be 'true' or 'mean'")
    mode = set_ayanamsa(ayanamsa)
    flags = _flags(mode)
    code = _BODIES.get(body)
    if body in ("Rahu", "Ketu"):
        code = swe.TRUE_NODE if node == "true" else swe.MEAN_NODE
    if code is None:
        raise ValueError(f"ingresses are unsupported for {body!r}")
    shift = 180 if body == "Ketu" else 0

    def lon(t: float) -> float:
        return (swe.calc_ut(t, code, flags)[0][0] + shift) % 360

    out, t, prev_sign = [], start_jd, int(lon(start_jd) // 30)
    while t <= end_jd:
        s = int(lon(t) // 30)
        if s != prev_sign:
            lo, hi = t - step, t
            for _ in range(40):
                mid = (lo + hi) / 2
                if int(lon(mid) // 30) == prev_sign:
                    lo = mid
                else:
                    hi = mid
            out.append({"jd": hi, "sign": s, "from_sign": prev_sign})
            prev_sign = s
        t += step
    return out


def crossings(
    body: str,
    start_jd: float,
    end_jd: float,
    width: float,
    ayanamsa: str = "lahiri",
    step: float = 1.0,
    *,
    node: str = "true",
) -> list[dict]:
    """Moments a body crosses a multiple of ``width`` degrees, bisected to well
    under a second: width 30 gives sign ingresses (as ingress_dates), 360/27
    nakshatra ingresses.  ``step`` must be shorter than the time the body
    takes to cross one division.  Each crossing carries the division entered,
    the one left, the boundary longitude and the speed there (negative for a
    retrograde re-entry)."""
    if end_jd <= start_jd:
        raise ValueError("crossing search end must follow start")
    if step <= 0 or width <= 0:
        raise ValueError("crossing step and width must be positive")
    if node not in {"true", "mean"}:
        raise ValueError("node must be 'true' or 'mean'")
    flags = _flags(set_ayanamsa(ayanamsa))
    code = _BODIES.get(body)
    if body in ("Rahu", "Ketu"):
        code = swe.TRUE_NODE if node == "true" else swe.MEAN_NODE
    if code is None:
        raise ValueError(f"crossings are unsupported for {body!r}")
    shift = 180 if body == "Ketu" else 0
    count = round(360 / width)

    def part(t: float) -> int:
        return int(((swe.calc_ut(t, code, flags)[0][0] + shift) % 360) // width) % count

    out, t, prev = [], start_jd, part(start_jd)
    while t < end_jd:
        nxt = min(t + step, end_jd)
        now = part(nxt)
        if now != prev:
            lo, hi = t, nxt
            for _ in range(40):
                mid = (lo + hi) / 2
                if part(mid) == prev:
                    lo = mid
                else:
                    hi = mid
            v = swe.calc_ut(hi, code, flags)[0]
            entered = part(hi)
            forward = (entered - prev) % count == 1
            out.append(
                {
                    "jd": hi,
                    "index": entered,
                    "from_index": prev,
                    "longitude": (entered if forward else prev) * width % 360,
                    "speed": v[3],
                }
            )
            prev = entered
        t = nxt
    return out


def solar_return(
    natal_jd: float, natal_sun: float, year_index: int, ayanamsa: str = "lahiri"
) -> float:
    """JD when the transiting Sun regains its natal longitude, year_index
    years after birth -- the varshaphala moment."""
    if year_index < 0:
        raise ValueError("year_index must be nonnegative")
    mode = set_ayanamsa(ayanamsa)
    flags = _flags(mode)
    guess = natal_jd + year_index * SIDEREAL_YEAR
    for _ in range(60):
        lon = swe.calc_ut(guess, swe.SUN, flags)[0]
        diff = (lon[0] - natal_sun + 180) % 360 - 180
        if abs(diff) < 1e-7:
            break
        guess -= diff / max(lon[3], 1e-6)
    return guess


def eclipses(start_jd: float, end_jd: float) -> list[dict]:
    """Solar and lunar eclipse maxima in a span."""
    out, t = [], start_jd
    while t < end_jd:
        try:
            _, tret = swe.sol_eclipse_when_glob(t, swe.FLG_SWIEPH, 0, False)
        except Exception:
            break
        if tret[0] > end_jd:
            break
        out.append({"jd": tret[0], "kind": "solar"})
        t = tret[0] + 20
    t = start_jd
    while t < end_jd:
        try:
            _, tret = swe.lun_eclipse_when(t, swe.FLG_SWIEPH, 0, False)
        except Exception:
            break
        if tret[0] > end_jd:
            break
        out.append({"jd": tret[0], "kind": "lunar"})
        t = tret[0] + 20
    return sorted(out, key=lambda e: e["jd"])


def equatorial(jd_ut: float) -> dict[str, tuple]:
    """Tropical right ascension and declination."""
    flags = swe.FLG_SWIEPH | swe.FLG_EQUATORIAL
    out = {}
    for name, body in _BODIES.items():
        v = swe.calc_ut(jd_ut, body, flags)[0]
        out[name] = (v[0] % 360, v[1])
    v = swe.calc_ut(jd_ut, swe.TRUE_NODE, flags)[0]
    out["Rahu"] = (v[0] % 360, v[1])
    out["Ketu"] = ((v[0] + 180) % 360, -v[1])
    return out


def obliquity(jd_ut: float) -> float:
    return swe.calc_ut(jd_ut, swe.ECL_NUT, 0)[0][0]


def sunset(jd_ut: float, lat: float, lon_east: float) -> float:
    """First sunset after the governing sunrise."""
    return _rise_set(sunrise(jd_ut, lat, lon_east) + 0.05, lat, lon_east, False)


def mean_longitude(jd_ut: float, body: str) -> float:
    """Mean heliocentric-equivalent longitude, used for the chesta kendra.

    Swiss Ephemeris has no 'mean planet', so this uses the classical mean
    motion from a J2000 epoch position -- adequate for a strength measure
    that is then divided into 60 virupas.
    """
    epoch = 2451545.0
    period = {
        "Sun": 365.2564,
        "Moon": 27.32158,
        "Mars": 686.98,
        "Mercury": 87.969,
        "Jupiter": 4332.59,
        "Venus": 224.701,
        "Saturn": 10759.22,
    }[body]
    start = {
        "Sun": 280.46,
        "Moon": 218.32,
        "Mars": 355.43,
        "Mercury": 252.25,
        "Jupiter": 34.35,
        "Venus": 181.98,
        "Saturn": 50.08,
    }[body]
    return (start + 360.0 * (jd_ut - epoch) / period) % 360
