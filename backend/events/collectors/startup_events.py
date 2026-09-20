"""Startup-event sources: feeds in sources.json with `"group": "startup"`.

Add only feeds whose publishers permit this use (public calendars, organizer-provided
iCal/JSON, partner feeds). Nothing here scrapes HTML.
"""
from __future__ import annotations

from backend.events.config import Settings
from backend.events.collectors.feed import FeedCollector, load_feeds


def build(settings: Settings | None = None) -> list[FeedCollector]:
    return load_feeds(settings, group="startup")
