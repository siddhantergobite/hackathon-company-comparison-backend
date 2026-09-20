"""Conference / industry-event sources: feeds in sources.json with `"group": "conference"`
(and any feed without a group is treated as "general" and picked up by `general`).
"""
from __future__ import annotations

from backend.events.config import Settings
from backend.events.collectors.feed import FeedCollector, load_feeds


def build(settings: Settings | None = None) -> list[FeedCollector]:
    return load_feeds(settings, group="conference") + load_feeds(settings, group="general")
