"""All available collectors. Add a new source by appending it here."""
from __future__ import annotations

from backend.events.config import Settings, get_settings
from backend.events.collectors import conference_sources, startup_events
from backend.events.collectors.base import BaseCollector
from backend.events.collectors.developers_events import DevelopersEventsCollector
from backend.events.collectors.eventbrite import EventbriteCollector
from backend.events.collectors.meetup import MeetupCollector


def list_collectors(settings: Settings | None = None) -> list[BaseCollector]:
    settings = settings or get_settings()
    return [
        EventbriteCollector(settings),
        MeetupCollector(settings),
        DevelopersEventsCollector(settings),
        *startup_events.build(settings),
        *conference_sources.build(settings),
    ]


def get_collector(name: str, settings: Settings | None = None) -> BaseCollector | None:
    return next((c for c in list_collectors(settings) if c.name == name), None)
