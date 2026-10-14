"""Explicit civil-time and observer-location context."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .ephemeris import TimeZone


@dataclass(frozen=True)
class ObserverContext:
    lat: float
    lon: float
    timezone: TimeZone
    place: str = ""

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude must be in [-90, 90]")
        if not -180 <= self.lon <= 180:
            raise ValueError("longitude must be in [-180, 180]")

    def overridden(
        self,
        *,
        lat: float | None = None,
        lon: float | None = None,
        timezone: TimeZone | None = None,
        place: str | None = None,
    ) -> ObserverContext:
        return replace(
            self,
            lat=self.lat if lat is None else lat,
            lon=self.lon if lon is None else lon,
            timezone=self.timezone if timezone is None else timezone,
            place=self.place if place is None else place,
        )
