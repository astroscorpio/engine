"""Nativities and their dated events.

Events are the only thing that can falsify anything else in this package, so
they live in source control next to the birth data.  ``confidence`` records
how well the date itself is known -- a technique cannot be scored more
precisely than the event it is tested against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chart import Chart
from .context import ObserverContext
from .ephemeris import TimeZone, jd


@dataclass
class Event:
    date: str  # YYYY-MM-DD, or YYYY-MM for month-level events
    label: str
    domains: tuple[str, ...]  # see DOMAINS below
    polarity: int  # +1 gain / -1 loss / 0 neutral-but-marked
    confidence: str = "day"  # day | week | month | quarter
    end: str | None = None  # set for sustained states rather than moments
    note: str = ""
    time: str | None = None  # HH:MM local, when the moment is known
    time_uncertainty_hours: float | None = None
    kind: str = "event"  # event | notification | marker
    of: str | None = None  # for a notification: the date of the event itself
    magnitude: int = 3  # 1 trivial .. 5 life-changing
    tz: TimeZone | None = None  # local zone at the time, if not the birth zone
    lat: float | None = None
    lon: float | None = None
    place: str = ""
    contaminated: str = ""  # why this event cannot be scored, if it cannot

    def __post_init__(self) -> None:
        if self.confidence not in {"day", "week", "month", "quarter"}:
            raise ValueError(f"invalid event confidence {self.confidence!r}")
        if self.polarity not in {-1, 0, 1}:
            raise ValueError("event polarity must be -1, 0, or 1")
        if self.kind not in {"event", "notification", "marker"}:
            raise ValueError(f"invalid event kind {self.kind!r}")
        if self.magnitude not in range(1, 6):
            raise ValueError("event magnitude must be 1..5")
        if self.time_uncertainty_hours is not None:
            if not self.time:
                raise ValueError("time uncertainty requires an event time")
            if self.time_uncertainty_hours <= 0:
                raise ValueError("time uncertainty must be positive")
        if (self.lat is None) != (self.lon is None):
            raise ValueError("event latitude and longitude must be supplied together")
        if self.lat is not None and not -90 <= self.lat <= 90:
            raise ValueError("event latitude must be in [-90, 90]")
        if self.lon is not None and not -180 <= self.lon <= 180:
            raise ValueError("event longitude must be in [-180, 180]")

    @property
    def is_interval(self) -> bool:
        return self.end is not None


# Houses conventionally signifying each domain, used by the backtester to turn
# a technique's output into a testable prediction.
DOMAINS = {
    "career": (10, 6, 2),
    "education": (4, 5, 9),
    "relationship": (7, 5, 2),
    "money": (2, 11, 6),
    "home": (4, 2),
    "conflict": (6, 3, 8),
    "travel": (3, 9, 12),
    "health": (1, 6, 8),
    "loss": (12, 8, 6),
    "recognition": (10, 11, 1),
}


@dataclass
class Subject:
    name: str
    year: int
    month: int
    day: int
    hour: float
    lat: float
    lon: float
    tz: TimeZone
    place: str = ""
    events: list[Event] = field(default_factory=list)
    birth_time_confidence: str = "unverified"
    birth_timezone: TimeZone | None = None
    observer: ObserverContext | None = None

    @property
    def birth_zone(self) -> TimeZone:
        return self.tz if self.birth_timezone is None else self.birth_timezone

    @property
    def birth_context(self) -> ObserverContext:
        return ObserverContext(self.lat, self.lon, self.birth_zone, self.place)

    @property
    def observer_context(self) -> ObserverContext:
        return self.observer or self.birth_context

    @property
    def jd(self) -> float:
        return jd(self.year, self.month, self.day, self.hour, self.birth_zone)

    def chart(self, ayanamsa: str = "lahiri", node: str = "true") -> Chart:
        return Chart(
            jd=self.jd,
            lat=self.lat,
            lon=self.lon,
            tz=self.birth_zone,
            ayanamsa=ayanamsa,
            node=node,
            label=self.name,
        )

    def shifted(self, minutes: float) -> Subject:
        """Same nativity with the birth time moved -- for rectification runs."""
        out = Subject(**{**self.__dict__, "hour": self.hour + minutes / 60.0})
        return out


# An invented nativity, used as the CLI default and by the test suite.  It
# describes no real person; the events exist to exercise each kind of record
# (moment, notification, marker, contaminated date, sustained state).
EXAMPLE = Subject(
    name="Example",
    year=2001,
    month=1,
    day=19,
    hour=14 + 5 / 60,  # 14:05 IST
    lat=28.6139,
    lon=77.2090,
    tz=5.5,
    birth_timezone="Asia/Kolkata",
    place="New Delhi, India",
    observer=ObserverContext(lat=48.8566, lon=2.3522, timezone="Europe/Paris", place="Paris"),
    birth_time_confidence="invented example",
    events=[
        Event("2019-04", "completed a training course", ("education",), 1, "quarter"),
        Event("2020-10", "first full-time contract", ("career", "money"), 1, "quarter"),
        Event(
            "2021-03-15",
            "relocated for work",
            ("travel", "home", "career"),
            1,
            "day",
            tz="Europe/Paris",
            lat=48.8566,
            lon=2.3522,
            place="Paris",
        ),
        Event(
            "2022-05-10",
            "professional certificate awarded",
            ("education", "recognition"),
            1,
            "day",
            magnitude=4,
            tz="Europe/Paris",
        ),
        Event(
            "2022-05-16",
            "certificate letter received",
            ("education", "recognition"),
            1,
            "day",
            kind="notification",
            of="2022-05-10",
        ),
        Event("2023-01-09", "joined a new team", ("career",), 1, "day", tz="Europe/Paris"),
        Event(
            "2024-03",
            "started a side project",
            ("career",),
            1,
            "month",
            contaminated="the start was gradual; the month is inferred from other records",
        ),
        Event(
            "2024-03-18",
            "moved flat",
            ("home",),
            1,
            "day",
            magnitude=2,
            tz="Europe/Paris",
            lat=48.8566,
            lon=2.3522,
            place="Paris",
        ),
        Event(
            "2024-03-25",
            "noisy week at home",
            ("home",),
            0,
            "day",
            kind="marker",
            magnitude=1,
            note="behavioural, not an outcome; scored polarity 0",
        ),
        Event(
            "2024-04-09",
            "minor water leak",
            ("home",),
            -1,
            "day",
            time="10:00",
            time_uncertainty_hours=1.0,
            tz="Europe/Paris",
            magnitude=1,
        ),
        Event(
            "2024-04-11",
            "invited to speak on a panel",
            ("career", "recognition"),
            1,
            "day",
            time="16:30",
            kind="notification",
            magnitude=2,
            tz="Europe/Paris",
            note="the decision time is unknown, so the notification is not scoreable as an "
            "event moment",
        ),
        # Sustained state.  Scored as a mean over the interval against random
        # intervals of the same length, not as a moment.
        Event("2019-10", "evening classes", ("education",), 1, "month", end="2020-12"),
    ],
)


SUBJECTS = {"example": EXAMPLE}
