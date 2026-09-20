"""developers.events collector: an open, community-maintained list of developer conferences.

LICENSE: the data is CC BY-NC 4.0 (Attribution-NonCommercial). It may only be used for
NON-COMMERCIAL purposes and must be credited. Because of that this collector is OPT-IN:
it stays disabled until you set EVENT_DEVELOPERS_EVENTS_ENABLED=true, which records that
you have decided your use is non-commercial. Every imported event carries an attribution
line in its description and a link back to the source.

Source: https://github.com/scraly/developers-conferences-agenda  (data: developers.events)
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterator

from backend.events.collectors.base import BaseCollector, CollectorError, PoliteHttpClient
from backend.events.config import Settings, get_settings
from backend.events.processors.normalize import map_event_type, slugify
from backend.events.taxonomy import CATEGORIES, canonical_category

DATA_URL = "https://developers.events/all-events.json"
ATTRIBUTION = (
    "Listing data from developers.events, an open list of developer conferences "
    "(CC BY-NC 4.0, https://github.com/scraly/developers-conferences-agenda)."
)


def _utc_date(ms) -> str | None:
    try:
        return datetime.fromtimestamp(float(ms) / 1000, timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _tags(item: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for t in item.get("tags") or []:
        if isinstance(t, dict) and t.get("key") and t.get("value"):
            out.setdefault(str(t["key"]).lower(), []).append(str(t["value"]).strip())
    return out


class DevelopersEventsCollector(BaseCollector):
    name = "developers-events"
    label = "developers.events"
    description = "Open list of developer conferences (CC BY-NC 4.0: non-commercial use, attribution required)"
    source_name = "developers.events"
    source_url = "https://developers.events"

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or PoliteHttpClient(self.settings.ingest_user_agent, min_interval=1.0, timeout=60.0)

    def is_configured(self) -> bool:
        return bool(self.settings.developers_events_enabled)

    def collect(self) -> Iterator[dict]:
        if not self.is_configured():
            raise CollectorError("developers.events is disabled: set EVENT_DEVELOPERS_EVENTS_ENABLED=true (CC BY-NC data, non-commercial use only)")
        try:
            items = self.client.get(DATA_URL).json()
        except ValueError as exc:
            raise CollectorError("developers.events returned invalid JSON") from exc
        if not isinstance(items, list):
            raise CollectorError("developers.events: unexpected payload (expected a list)")
        today = datetime.now(timezone.utc).date().isoformat()
        for item in items:
            raw = self.to_raw(item)
            # the file also holds years of past events; only bring in what hasn't ended
            if raw and (raw["end"] or raw["start"]) >= today:
                yield raw

    @staticmethod
    def to_raw(item: dict) -> dict | None:
        dates = item.get("date") or []
        start = _utc_date(dates[0]) if dates else None
        end = _utc_date(dates[-1]) if dates else None
        name = (item.get("name") or "").strip()
        if not name or not start:
            return None

        city, country = (item.get("city") or "").strip(), (item.get("country") or "").strip()
        online = city.lower() == "online" or country.lower() == "online"
        hybrid = not online and "online" in (item.get("location") or "").lower()
        fmt = "online" if online else "hybrid" if hybrid else "offline"

        tags = _tags(item)
        categories = ["Technology", "Software"]
        topics: list[str] = []
        for value in tags.get("tech", []) + tags.get("topic", []):
            canon = canonical_category(value)
            if canon in CATEGORIES:
                if canon not in categories:
                    categories.append(canon)
            elif value.title() not in topics:
                topics.append(value.title())

        where = "online" if online else ", ".join(x for x in (city, country) if x) + (" and online" if hybrid else "")
        parts = [f"{name} is a developer event {'held ' + where if online else 'in ' + where}."]
        if tags.get("language"):
            parts.append(f"Language: {', '.join(tags['language'])}.")
        cfp = item.get("cfp") or {}
        until = cfp.get("untilDate")
        if cfp.get("link") and until and datetime.fromtimestamp(float(until) / 1000, timezone.utc) > datetime.now(timezone.utc):
            parts.append(f"Call for papers is open until {cfp.get('until')}: {cfp['link']}")
        parts.append(ATTRIBUTION)

        sid = hashlib.sha1(f"{slugify(name)}|{slugify(city)}|{start[:4]}".encode()).hexdigest()[:16]
        return {
            "title": name,
            "event_type": map_event_type(name) or "conference",
            "description": " ".join(parts),
            "start": start,
            "end": end,
            "event_url": item.get("hyperlink"),
            "source_event_id": sid,
            "city": None if online else city or None,
            "country": None if online else country or None,
            "format": fmt,
            "categories": categories,
            "topics": topics[:8],
            "audience": ["Developers"],
        }
