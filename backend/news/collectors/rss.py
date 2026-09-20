"""RSS / Atom collector (feedparser). Uses conditional GET so unchanged feeds cost one 304.

Feeds are published for machine consumption, so robots.txt is not applied to the feed URL itself;
we still identify ourselves honestly, rate-limit per host and back off on errors.
"""
from __future__ import annotations

import re
from typing import Any

import feedparser

from backend.common.http import PoliteHttpClient
from backend.news.collectors.base import BaseNewsCollector, CollectorError, FetchResult
from backend.news.config import Settings, get_settings

_IMG_TAG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
_IMG_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif)(\?|$)", re.I)


def _entry_image(e: Any) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key) or []:
            url = m.get("url")
            if url and (m.get("medium") == "image" or str(m.get("type", "")).startswith("image") or _IMG_EXT.search(url) or key == "media_thumbnail"):
                return url
    for link in e.get("links") or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    img = e.get("image")
    if isinstance(img, dict) and img.get("href"):
        return img["href"]
    body = (e.get("summary") or "") + " " + " ".join(c.get("value", "") for c in e.get("content") or [])
    m = _IMG_TAG.search(body)
    return m.group(1) if m else None


def entry_to_raw(e: Any) -> dict:
    description = e.get("summary")
    if not description and e.get("content"):
        description = e["content"][0].get("value")
    return {
        "title": e.get("title"),
        "link": e.get("link"),
        "description": description,
        "published": e.get("published_parsed") or e.get("updated_parsed") or e.get("published") or e.get("updated"),
        "image": _entry_image(e),
        "author": e.get("author"),
        "tags": [t.get("term") for t in e.get("tags") or [] if t.get("term")],
    }


class RssCollector(BaseNewsCollector):
    type = "rss"

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or PoliteHttpClient(self.settings.user_agent, min_interval=1.0, timeout=25.0, respect_robots=False)

    def is_available(self, source: dict) -> tuple[bool, str]:
        return (True, "") if source.get("url") else (False, "no feed URL")

    def fetch(self, source: dict) -> FetchResult:
        headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"}
        if source.get("etag"):
            headers["If-None-Match"] = source["etag"]
        if source.get("last_modified"):
            headers["If-Modified-Since"] = source["last_modified"]
        r = self.client.get(source["url"], headers=headers)
        if r.status_code == 304:
            return FetchResult(not_modified=True, etag=source.get("etag"), last_modified=source.get("last_modified"))
        parsed = feedparser.parse(r.content)
        if not getattr(parsed, "version", ""):   # empty for anything that is not RSS/Atom (HTML pages, JSON, junk)
            raise CollectorError("not a valid RSS/Atom feed (the URL returned something else, e.g. an HTML page)")
        if not parsed.entries:
            return FetchResult(etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"))
        return FetchResult(
            items=[entry_to_raw(e) for e in parsed.entries],
            etag=r.headers.get("ETag"),
            last_modified=r.headers.get("Last-Modified"),
        )
