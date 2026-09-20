"""Eventbrite collector (official API v3).

Eventbrite removed public event *search* in 2020, so this reads the events of the
organizations you have API access to (EVENTBRITE_ORGANIZATION_IDS) using your private
token (EVENTBRITE_TOKEN). Disabled until both are configured.

NOTE: written against the documented v3 response shape; not exercised against the live
API in this repository's tests (it needs your credentials).
"""
from __future__ import annotations

from typing import Iterator

from backend.events.config import Settings, get_settings
from backend.events.collectors.base import BaseCollector, CollectorError, PoliteHttpClient

API = "https://www.eventbriteapi.com/v3"


def _text(node) -> str | None:
    if isinstance(node, dict):
        return node.get("text") or node.get("html")
    return node


class EventbriteCollector(BaseCollector):
    name = "eventbrite"
    label = "Eventbrite"
    description = "Official Eventbrite API v3 (organizations you have access to)"
    source_name = "Eventbrite"
    source_url = "https://www.eventbrite.com"

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or PoliteHttpClient(self.settings.ingest_user_agent, min_interval=0.5)

    @property
    def org_ids(self) -> list[str]:
        return [o.strip() for o in self.settings.eventbrite_organization_ids.split(",") if o.strip()]

    def is_configured(self) -> bool:
        return bool(self.settings.eventbrite_token and self.org_ids)

    def collect(self) -> Iterator[dict]:
        if not self.is_configured():
            raise CollectorError("Eventbrite is not configured (EVENTBRITE_TOKEN / EVENTBRITE_ORGANIZATION_IDS)")
        headers = {"Authorization": f"Bearer {self.settings.eventbrite_token}"}
        for org in self.org_ids:
            continuation = None
            while True:
                params = {"status": "live", "order_by": "start_asc", "page_size": 50, "expand": "venue,organizer,ticket_availability,category"}
                if continuation:
                    params["continuation"] = continuation
                data = self.client.get(f"{API}/organizations/{org}/events/", params=params, headers=headers, api=True).json()
                for ev in data.get("events", []):
                    yield self.to_raw(ev)
                pg = data.get("pagination") or {}
                continuation = pg.get("continuation") if pg.get("has_more_items") else None
                if not continuation:
                    break

    @staticmethod
    def to_raw(ev: dict) -> dict:
        start, end = ev.get("start") or {}, ev.get("end") or {}
        venue = ev.get("venue") or {}
        addr = venue.get("address") or {}
        org = ev.get("organizer") or {}
        price = ((ev.get("ticket_availability") or {}).get("minimum_ticket_price") or {})
        raw = {
            "title": _text(ev.get("name")),
            "summary": ev.get("summary"),
            "description": _text(ev.get("description")),
            "start": start.get("local"),
            "end": end.get("local"),
            "timezone": start.get("timezone"),
            "event_url": ev.get("url"),
            "image_url": (ev.get("logo") or {}).get("url"),
            "source_event_id": ev.get("id"),
            "is_online": bool(ev.get("online_event")),
            "venue": venue.get("name"),
            "address": addr.get("address_1") or addr.get("localized_address_display"),
            "city": addr.get("city"),
            "state": addr.get("region"),
            "country": addr.get("country"),
            "latitude": addr.get("latitude"),
            "longitude": addr.get("longitude"),
            "organizer": {"name": org.get("name"), "description": _text(org.get("description")), "website": org.get("url")},
            "categories": [(ev.get("category") or {}).get("name")] if ev.get("category") else [],
            "status": "cancelled" if ev.get("status") == "canceled" else None,
        }
        if ev.get("is_free"):
            raw["ticket_type"] = "free"
        elif price.get("major_value") is not None:
            raw["price"] = price.get("major_value")
            raw["currency"] = price.get("currency")
        raw["registration_url"] = ev.get("url")
        return raw
