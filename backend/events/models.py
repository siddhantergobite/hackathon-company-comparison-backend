"""Pydantic models for events.

Write models (`EventCreate`, `EventUpdate`) validate admin input. Read models
(`EventOut`, `EventSummary`, ...) are deliberately lenient: every field is optional so a
partially-populated or older document can never make a read endpoint fail.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(str, Enum):
    conference = "conference"
    meetup = "meetup"
    industry_seminar = "industry_seminar"
    startup_event = "startup_event"
    business_networking = "business_networking"
    workshop = "workshop"
    summit = "summit"
    expo = "expo"
    trade_show = "trade_show"
    hackathon = "hackathon"
    webinar = "webinar"
    training = "training"
    other = "other"


EVENT_TYPE_LABELS: dict[str, str] = {
    "conference": "Conference",
    "meetup": "Meetup",
    "industry_seminar": "Industry Seminar",
    "startup_event": "Startup Event",
    "business_networking": "Business Networking",
    "workshop": "Workshop",
    "summit": "Summit",
    "expo": "Expo",
    "trade_show": "Trade Show",
    "hackathon": "Hackathon",
    "webinar": "Webinar",
    "training": "Training",
    "other": "Other",
}

# Friendly names used by filters / older clients -> canonical enum value.
EVENT_TYPE_ALIASES: dict[str, str] = {
    "startup": "startup_event", "startups": "startup_event", "startup event": "startup_event",
    "seminar": "industry_seminar", "industry seminar": "industry_seminar",
    "networking": "business_networking", "business networking": "business_networking",
    "trade show": "trade_show", "tradeshow": "trade_show", "exhibition": "expo",
    "conferences": "conference", "meetups": "meetup", "workshops": "workshop",
    "summits": "summit", "expos": "expo", "hackathons": "hackathon", "webinars": "webinar",
}


class EventStatus(str, Enum):
    upcoming = "upcoming"
    ongoing = "ongoing"
    completed = "completed"
    cancelled = "cancelled"
    postponed = "postponed"


class EventFormat(str, Enum):
    online = "online"
    offline = "offline"
    hybrid = "hybrid"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    duplicate = "duplicate"


class TicketType(str, Enum):
    free = "free"
    paid = "paid"


def _none_to_dict(v: Any) -> Any:
    return {} if v is None else v


class Location(BaseModel):
    model_config = ConfigDict(extra="ignore")
    venue: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class Organizer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    description: str | None = None
    website: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict)

    @field_validator("social_links", mode="before")
    @classmethod
    def _links(cls, v: Any) -> Any:
        return {} if v is None else v


class Registration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str | None = None
    price: float | None = None
    currency: str | None = None
    ticket_type: str | None = None
    ticket_info: str | None = None


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    url: str | None = None
    source_event_id: str | None = None


# ----------------------------------------------------------------------------- write models
class EventCreate(BaseModel):
    """Admin/manual input. Values are canonicalised by `processors.normalize`."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=300)
    slug: str | None = Field(default=None, max_length=120)
    event_type: EventType | None = None
    summary: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=20000)
    start_date: str
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    timezone: str | None = None
    location: Location | None = None
    is_online: bool | None = None
    format: EventFormat | None = None
    categories: list[str] = Field(default_factory=list, max_length=40)
    topics: list[str] = Field(default_factory=list, max_length=60)
    audience: list[str] = Field(default_factory=list, max_length=40)
    keywords: list[str] = Field(default_factory=list, max_length=60)
    organizer: Organizer | None = None
    registration: Registration | None = None
    image_url: str | None = None
    event_url: str | None = None
    source: SourceInfo | None = None
    status: EventStatus | None = None


class EventUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    slug: str | None = Field(default=None, max_length=120)
    event_type: EventType | None = None
    summary: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=20000)
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    timezone: str | None = None
    location: Location | None = None
    is_online: bool | None = None
    format: EventFormat | None = None
    categories: list[str] | None = None
    topics: list[str] | None = None
    audience: list[str] | None = None
    keywords: list[str] | None = None
    organizer: Organizer | None = None
    registration: Registration | None = None
    image_url: str | None = None
    event_url: str | None = None
    source: SourceInfo | None = None
    status: EventStatus | None = None


# ------------------------------------------------------------------------------ read models
class _Read(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @field_validator("location", "organizer", "registration", "source", mode="before", check_fields=False)
    @classmethod
    def _nested_none(cls, v: Any) -> Any:
        return _none_to_dict(v)

    @field_validator("categories", "topics", "audience", "keywords", "other_sources", mode="before", check_fields=False)
    @classmethod
    def _list_none(cls, v: Any) -> Any:
        return [] if v is None else v


class EventSummary(_Read):
    """What a listing card needs."""

    id: str
    slug: str | None = None
    title: str
    event_type: str | None = None
    summary: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    timezone: str | None = None
    location: Location = Field(default_factory=Location)
    is_online: bool = False
    format: str | None = None
    categories: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    organizer: Organizer = Field(default_factory=Organizer)
    registration: Registration = Field(default_factory=Registration)
    image_url: str | None = None
    status: str | None = None


class EventOut(EventSummary):
    """Full public event."""

    description: str | None = None
    audience: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    event_url: str | None = None
    source: SourceInfo = Field(default_factory=SourceInfo)
    other_sources: list[SourceInfo] = Field(default_factory=list)
    last_verified: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminEventSummary(EventSummary):
    review_status: str | None = None
    source: SourceInfo = Field(default_factory=SourceInfo)
    possible_duplicate_of: str | None = None
    duplicate_of: str | None = None
    manually_edited: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_verified: datetime | None = None


class AdminEventOut(EventOut):
    review_status: str | None = None
    possible_duplicate_of: str | None = None
    duplicate_of: str | None = None
    manually_edited: bool = False
    merged_from: list[dict[str, Any]] = Field(default_factory=list)


class EventPage(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    events: list[EventSummary]


class AdminEventPage(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    events: list[AdminEventSummary]
