"""NewsAPI.org collector: the lawful route to Reuters / AP style headlines.

Reuters and AP no longer publish free RSS feeds. NewsAPI is a licensed aggregator that carries
their headlines and teasers. It needs NEWS_API_KEY; the free developer plan is for testing only,
so check newsapi.org's terms for production use.

Source `config` keys: mode ("top-headlines" | "everything"), sources ("reuters,associated-press"),
country, category, q, language, page_size.
"""
from __future__ import annotations

from backend.common.http import PoliteHttpClient
from backend.news.collectors.base import BaseNewsCollector, CollectorError, FetchResult
from backend.news.config import Settings, get_settings

API = "https://newsapi.org/v2"


class NewsApiCollector(BaseNewsCollector):
    type = "newsapi"

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.settings = settings or get_settings()
        self.client = client or PoliteHttpClient(self.settings.user_agent, min_interval=1.0, timeout=25.0, respect_robots=False)

    def is_available(self, source: dict) -> tuple[bool, str]:
        return (True, "") if self.settings.news_api_key else (False, "NEWS_API_KEY is not set")

    def fetch(self, source: dict) -> FetchResult:
        ok, why = self.is_available(source)
        if not ok:
            raise CollectorError(why)
        cfg = source.get("config") or {}
        mode = cfg.get("mode", "top-headlines")
        params: dict = {"pageSize": min(int(cfg.get("page_size", 100)), 100)}
        if mode == "everything":
            params.update({"sortBy": "publishedAt", "language": cfg.get("language", "en")})
        for k in ("sources", "country", "category", "q"):
            if cfg.get(k):
                params[k] = cfg[k]
        if mode == "everything" and not (params.get("q") or params.get("sources")):
            raise CollectorError("NewsAPI 'everything' mode needs q or sources")
        if mode == "top-headlines" and not any(params.get(k) for k in ("sources", "country", "category", "q")):
            raise CollectorError("NewsAPI 'top-headlines' needs sources, country, category or q")
        r = self.client.get(f"{API}/{mode}", params=params, headers={"X-Api-Key": self.settings.news_api_key}, api=True)
        data = r.json()
        if data.get("status") != "ok":
            raise CollectorError(f"NewsAPI error: {data.get('message') or data.get('code') or 'unknown'}")
        items = [
            {
                "title": a.get("title"), "link": a.get("url"), "description": a.get("description"),
                "published": a.get("publishedAt"), "image": a.get("urlToImage"), "author": a.get("author"),
                "source_name": (a.get("source") or {}).get("name"),
            }
            for a in data.get("articles") or []
            if a.get("title") and a.get("title") != "[Removed]"
        ]
        return FetchResult(items=items)
