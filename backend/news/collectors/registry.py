"""Source types -> collectors. To support a new kind of source, add a collector and register it here."""
from __future__ import annotations

from backend.common.http import PoliteHttpClient
from backend.news.collectors.base import BaseNewsCollector
from backend.news.collectors.newsapi import NewsApiCollector
from backend.news.collectors.rss import RssCollector
from backend.news.config import Settings, get_settings

COLLECTOR_TYPES: dict[str, type[BaseNewsCollector]] = {
    "rss": RssCollector,
    "newsapi": NewsApiCollector,
}


def make_collector(source: dict, settings: Settings | None = None, client: PoliteHttpClient | None = None) -> BaseNewsCollector:
    settings = settings or get_settings()
    cls = COLLECTOR_TYPES.get(source.get("type") or "rss")
    if cls is None:
        raise ValueError(f"unsupported source type '{source.get('type')}'")
    return cls(settings, client)
