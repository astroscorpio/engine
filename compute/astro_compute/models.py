"""Request models. Responses are plain dicts shaped by docs/api-contract.md."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)

from .timeutil import check_zone

Ayanamsa = Literal[
    "lahiri", "raman", "krishnamurti", "true_citra", "true_revati", "yukteshwar",
    "suryasiddhanta", "fagan_bradley", "tropical",
]  # fmt: skip
Node = Literal["true", "mean"]

CLOCK = r"^\d{2}:\d{2}(:\d{2})?$"
OFFSET = r"^[+-]\d{2}:\d{2}$"


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class BundlePlace(Model):
    id: str = Field(pattern=r"^gn:\d{1,10}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str


class BundleRequest(Model):
    """POST /v1/bundle: one year-list route for several places (contract 7n)."""

    path: str = Field(pattern=r"^/v1/(observances|festivals|muhurat)/[a-z-]+$")
    query: dict[str, str] = Field(default_factory=dict)
    places: list[BundlePlace] = Field(min_length=1, max_length=40)


class PlaceIn(Model):
    """Coordinates are required here: the API gateway resolves {id} places
    before anything reaches compute."""

    id: str | None = None
    slug: str | None = None
    name: str | None = Field(default=None, max_length=200)
    admin1: str | None = None
    country: str | None = None
    countryCode: str | None = None
    population: int | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)

    def echo(self) -> dict:
        return self.model_dump(exclude_none=True)


class ChartIn(Model):
    name: str | None = Field(default=None, max_length=80)
    date: dt.date
    time: str | None = Field(default=None, pattern=CLOCK)
    timeUnknown: bool = False
    place: PlaceIn
    utcOffset: str | None = Field(default=None, pattern=OFFSET)
    ayanamsa: Ayanamsa = "lahiri"
    node: Node = "true"

    @model_validator(mode="after")
    def _time_needed(self) -> ChartIn:
        if not self.timeUnknown and not self.time:
            raise ValueError("time is required unless timeUnknown is true")
        return self

    def echo(self) -> dict:
        return {
            "name": self.name,
            "date": self.date.isoformat(),
            "time": None if self.timeUnknown else self.time,
            "timeUnknown": self.timeUnknown,
            "place": self.place.echo(),
            "utcOffset": self.utcOffset,
            "ayanamsa": self.ayanamsa,
            "node": self.node,
        }


Section = Literal["dasha", "yogas", "ashtakavarga", "strength", "states", "jaimini", "points"]


class ChartRequest(ChartIn):
    vargas: list[str] | Literal["all"] = Field(default_factory=lambda: ["D9"])
    include: list[Section] = Field(default_factory=lambda: ["dasha", "yogas", "ashtakavarga"])
    at: str | None = None


class DashaRequest(Model):
    chart: ChartIn
    system: Literal["vimshottari", "yogini", "ashtottari", "chara", "narayana"] = "vimshottari"
    path: list[str] = Field(default_factory=list, max_length=4)
    at: str | None = None


SignId = Literal[
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
]  # fmt: skip


class GocharaQuery(Model):
    moonSign: SignId
    start: dt.date
    end: dt.date
    tz: str = "Asia/Kolkata"
    ayanamsa: Ayanamsa = "lahiri"
    node: Node = "true"

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)

    @model_validator(mode="after")
    def _range(self) -> GocharaQuery:
        if not 0 <= (self.end - self.start).days <= 6:
            raise ValueError("until must be from date to 6 days after it")
        return self


class TransitRequest(Model):
    chart: ChartIn | None = None
    at: str | None = None
    days: int = Field(default=90, ge=0, le=730)
    ayanamsa: Ayanamsa = "lahiri"
    node: Node = "true"


class EventsQuery(Model):
    start: str
    end: str
    grahas: str = "sun,mars,mercury,jupiter,venus,saturn,rahu,ketu"
    kinds: str = "sign,nakshatra,station"
    ayanamsa: Ayanamsa = "lahiri"
    node: Node = "true"


class NakshatraIn(Model):
    """A partner known only by birth star, when the birth time is unknown."""

    name: str | None = Field(default=None, max_length=80)
    nakshatra: str
    pada: int = Field(ge=1, le=4)


class NameIn(Model):
    """A partner known only by name: the fallback when the birth star is not known (MM v.54)."""

    name: str = Field(min_length=1, max_length=80)
    basis: Literal["name"]


def _partner_kind(value: object) -> str:
    if isinstance(value, NakshatraIn):
        return "star"
    if isinstance(value, NameIn):
        return "name"
    if isinstance(value, dict) and "date" not in value:
        if "nakshatra" in value:
            return "star"
        if value.get("basis") == "name":
            return "name"
    return "chart"


Partner = Annotated[
    Annotated[ChartIn, Tag("chart")]
    | Annotated[NakshatraIn, Tag("star")]
    | Annotated[NameIn, Tag("name")],
    Discriminator(_partner_kind),
]


class MatchingRequest(Model):
    bride: Partner
    groom: Partner


class PanchangQuery(Model):
    date: dt.date
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    ayanamsa: Ayanamsa = "lahiri"
    hora: Literal["seasonal", "equal"] = "seasonal"

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)


class MonthQuery(Model):
    year: int = Field(ge=1800, le=2200)
    month: int = Field(ge=1, le=12)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    ayanamsa: Ayanamsa = "lahiri"

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)


class EkadashiQuery(Model):
    year: int = Field(ge=1800, le=2200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    ayanamsa: Ayanamsa = "lahiri"
    parana: bool = False  # Ekadashi fast-breaking times (observances.md s9, pending the lead)

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)


Act = Literal[
    "general", "education", "travel", "home", "mundan", "vehicle", "property",
    "annaprashan", "akshararambh",
]  # fmt: skip
Compass = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class MuhurtaRequest(Model):
    act: Act = "general"
    from_: dt.date = Field(alias="from")
    until: dt.date
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    hours: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}-\d{2}:\d{2}$")
    toward: Compass | None = None
    firstLeg: Compass | None = None
    door: Literal["N", "E", "S", "W"] | None = None  # home: the main door faces (MC 13.5)
    oldHouse: bool = False  # home: an old or rebuilt house (MC 13.2)
    eldest: bool = False  # mundan: an eldest child, so no Jyeshtha (MC 5.33 commentary)
    child: Literal["boy", "girl"] | None = None  # annaprashan: the month by sex (MC 5.17)
    top: int = Field(default=10, ge=1, le=50)
    chart: ChartIn | None = None
    ayanamsa: Ayanamsa = "lahiri"

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)


class MuhurtaCheck(Model):
    act: Act = "general"
    at: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str
    toward: Compass | None = None
    firstLeg: Compass | None = None
    door: Literal["N", "E", "S", "W"] | None = None  # home: the main door faces (MC 13.5)
    oldHouse: bool = False  # home: an old or rebuilt house (MC 13.2)
    eldest: bool = False  # mundan: an eldest child, so no Jyeshtha (MC 5.33 commentary)
    child: Literal["boy", "girl"] | None = None  # annaprashan: the month by sex (MC 5.17)
    chart: ChartIn | None = None
    ayanamsa: Ayanamsa = "lahiri"

    @field_validator("tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return check_zone(value)
