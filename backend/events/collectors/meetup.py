"""Meetup collector (official GraphQL API).

Reads upcoming events for the groups listed in MEETUP_GROUP_URLNAMES using an OAuth
access token (MEETUP_ACCESS_TOKEN). Disabled until both are configured.

NOTE: written against Meetup's documented GraphQL schema; not exercised against the live
API in this repository's tests (it needs your credentials and API access level). If Meetup
changes a field, only `QUERY` / `to_raw` need adjusting.
"""
from __future__ import annotations

from typing import Iterator

from backend.events.config import Settings, get_settings
from backend.events.collectors.base import BaseCollector, CollectorError, PoliteHttpClient

ENDPOINT = "https://api.meetup.com/gql-ext"

QUERY = """
query GroupEvents($urlname: String!) {
  groupByUrlname(urlname: $urlname) {
    name
    link
    description
    upcomingEvents(input: {first: 50}) {
      edges { node {
        id title description dateTime endTime eventUrl eventType
        venue { name address city state country lat lon }
        featuredEventPhoto { highResUrl }
        feeSettings { amount currency }
      } }
    }
  }
}
"""


class MeetupCollector(BaseCollector):
    name = "meetup"
    label = "Meetup"
    description = "Official Meetup GraphQL API (groups you configure)"
    source_name = "Meetup"
    source_url = "https://www.meetup.com"

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or PoliteHttpClient(self.settings.ingest_user_agent, min_interval=1.0)

    @property
    def groups(self) -> list[str]:
        return [g.strip() for g in self.settings.meetup_group_urlnames.split(",") if g.strip()]

    def is_configured(self) -> bool:
        return bool(self.settings.meetup_access_token and self.groups)

    def collect(self) -> Iterator[dict]:
        if not self.is_configured():
            raise CollectorError("Meetup is not configured (MEETUP_ACCESS_TOKEN / MEETUP_GROUP_URLNAMES)")
        headers = {"Authorization": f"Bearer {self.settings.meetup_access_token}"}
        for urlname in self.groups:
            payload = self.client.post_json(ENDPOINT, json={"query": QUERY, "variables": {"urlname": urlname}}, headers=headers).json()
            if payload.get("errors"):
                raise CollectorError(f"Meetup API error for '{urlname}': {payload['errors'][0].get('message', 'unknown')}")
            group = (payload.get("data") or {}).get("groupByUrlname")
            if not group:
                continue
            for edge in (group.get("upcomingEvents") or {}).get("edges") or []:
                yield self.to_raw(edge["node"], group)

    @staticmethod
    def to_raw(node: dict, group: dict) -> dict:
        venue = node.get("venue") or {}
        fee = node.get("feeSettings") or {}
        etype = (node.get("eventType") or "").upper()
        raw = {
            "title": node.get("title"),
            "description": node.get("description"),
            "start": node.get("dateTime"),
            "end": node.get("endTime"),
            "event_url": node.get("eventUrl"),
            "source_event_id": node.get("id"),
            "event_type": "meetup",
            "format": {"ONLINE": "online", "HYBRID": "hybrid", "PHYSICAL": "offline"}.get(etype),
            "venue": venue.get("name"),
            "address": venue.get("address"),
            "city": venue.get("city"),
            "state": venue.get("state"),
            "country": venue.get("country"),
            "latitude": venue.get("lat"),
            "longitude": venue.get("lon"),
            "image_url": (node.get("featuredEventPhoto") or {}).get("highResUrl"),
            "organizer": {"name": group.get("name"), "website": group.get("link"), "description": group.get("description")},
            "registration_url": node.get("eventUrl"),
        }
        if fee.get("amount") is not None:
            raw["price"] = fee.get("amount")
            raw["currency"] = fee.get("currency")
        else:
            raw["ticket_type"] = "free"
        return raw
