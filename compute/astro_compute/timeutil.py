"""Civil time <-> Julian day, and the ISO strings the contract promises."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jyotisha import ephemeris as E

from .errors import ApiError, invalid

type Zone = str | float

MIN_DATE = dt.date(1800, 1, 1)
MAX_DATE = dt.date(2200, 12, 31)


def tzinfo(zone: Zone) -> dt.tzinfo:
    if isinstance(zone, str):
        try:
            return ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise invalid(f"unknown IANA timezone {zone!r}", "tz") from exc
    return dt.timezone(dt.timedelta(hours=zone))


def check_zone(name: str) -> str:
    tzinfo(name)
    return name


def parse_offset(text: str) -> float:
    sign = -1 if text.startswith("-") else 1
    hours, minutes = text[1:].split(":")
    value = int(hours) + int(minutes) / 60
    if value > 14:
        raise invalid("utcOffset must be within +/-14:00", "utcOffset")
    return sign * value


def parse_clock(text: str, field: str = "time") -> float:
    """'HH:MM' or 'HH:MM:SS' -> hours."""
    try:
        parts = [int(p) for p in text.split(":")]
    except ValueError as exc:
        raise invalid(f"{field} must be HH:MM or HH:MM:SS", field) from exc
    if len(parts) not in (2, 3):
        raise invalid(f"{field} must be HH:MM or HH:MM:SS", field)
    h, m, s = (parts + [0])[:3]
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise invalid(f"{field} is out of range", field)
    return h + m / 60 + s / 3600


def check_date(day: dt.date, field: str = "date") -> dt.date:
    if not MIN_DATE <= day <= MAX_DATE:
        raise invalid(f"{field} must fall between {MIN_DATE} and {MAX_DATE}", field)
    return day


def local_jd(day: dt.date, hour: float, zone: Zone, field: str = "time") -> float:
    """JD(UT) of a local civil moment, with DST gaps and overlaps made explicit."""
    try:
        return E.jd(day.year, day.month, day.day, hour, zone)
    except ValueError as exc:
        text = str(exc)
        if "ambiguous" in text:
            raise ApiError(
                "ambiguous_time",
                "this local time occurs twice (clocks went back); resend with utcOffset",
                422,
                field,
            ) from exc
        if "nonexistent" in text:
            raise invalid("this local time never occurred (clocks went forward)", field) from exc
        raise


def _utc(jd: float) -> dt.datetime:
    t = E.to_datetime(jd, 0.0)
    # Round to the nearest second in UTC, where arithmetic is not wall-clock.
    return (t + dt.timedelta(microseconds=500_000)).replace(microsecond=0)


def _minute_offset(t: dt.datetime) -> dt.datetime:
    """LMT offsets carry seconds (+05:53:28), which JavaScript dates reject.
    Re-express the same instant at the offset rounded to the minute."""
    off = t.utcoffset()
    if off is None or off.seconds % 60 == 0:
        return t
    minutes = round(off.total_seconds() / 60)
    return t.astimezone(dt.timezone(dt.timedelta(minutes=minutes)))


def aware(jd: float, zone: Zone) -> dt.datetime:
    return _minute_offset(_utc(jd).astimezone(tzinfo(zone)))


def iso(jd: float, zone: Zone) -> str:
    return aware(jd, zone).isoformat()


def iso_utc(jd: float) -> str:
    return _utc(jd).isoformat().replace("+00:00", "Z")


def offset_text(t: dt.datetime) -> str:
    """'+05:30'; local mean time keeps its seconds ('+05:53:28') because this is
    shown to people, while the ISO timestamps carry the minute-rounded offset."""
    total = int(t.utcoffset().total_seconds())
    sign = "+" if total >= 0 else "-"
    hours, rem = divmod(abs(total), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{sign}{hours:02d}:{minutes:02d}" + (f":{seconds:02d}" if seconds else "")


def parse_instant(text: str, zone: Zone, field: str = "at") -> float:
    """ISO instant (offset or Z) -> JD; naive values are read in `zone`."""
    try:
        return E.parse(text, zone)
    except ValueError as exc:
        raise invalid(f"{field} must be an ISO 8601 timestamp", field) from exc


@dataclass(frozen=True)
class Birth:
    jd: float
    zone: Zone  # what the birth moment was resolved in (place tz or explicit offset)
    display: str  # the place's IANA zone, used for every other time we print
    local: dt.datetime
    utc_offset: str


def resolve_birth(day: dt.date, time: str | None, unknown: bool, tz: str, utc_offset: str | None):
    check_date(day)
    hour = 12.0 if unknown else parse_clock(time or "", "time")
    zone: Zone = parse_offset(utc_offset) if utc_offset else check_zone(tz)
    jd = local_jd(day, hour, zone)
    exact = _utc(jd).astimezone(tzinfo(zone))
    return Birth(jd, zone, tz, _minute_offset(exact), offset_text(exact))
