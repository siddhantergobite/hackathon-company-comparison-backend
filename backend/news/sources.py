"""Default news sources + seeding.

Every default below was fetched and parsed successfully when this list was written. Sources
live in the `news_sources` collection: admins can add, edit, disable or delete them, and seeding
NEVER overwrites an existing document, so edits survive restarts.

Reuters and AP have no free public RSS feed any more; they are available through the optional
NewsAPI source (needs NEWS_API_KEY). Anthropic publishes no official feed, and VentureBeat blocks
automated feed requests (HTTP 429), so neither is listed.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from backend.news.config import Settings
from backend.news.taxonomy import DEFAULT_CATEGORIES, slugify

# name, feed url, homepage, category hint, priority (1-5), country
_RSS = [
    # --- world / general
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "https://www.bbc.com/news", "world", 5, "GB"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "https://www.bbc.com/news/world", "world", 5, "GB"),
    ("The Guardian World", "https://www.theguardian.com/world/rss", "https://www.theguardian.com/world", "world", 4, "GB"),
    ("The Guardian Politics", "https://www.theguardian.com/politics/rss", "https://www.theguardian.com/politics", "politics", 4, "GB"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml", "https://www.npr.org", "world", 4, "US"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "https://www.aljazeera.com", "world", 4, "QA"),
    # --- AI
    ("OpenAI", "https://openai.com/news/rss.xml", "https://openai.com/news", "ai", 5, "US"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml", "https://deepmind.google/blog", "ai", 5, "GB"),
    ("Google AI Blog", "https://blog.google/technology/ai/rss/", "https://blog.google/technology/ai", "ai", 4, "US"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "https://techcrunch.com/category/artificial-intelligence", "ai", 4, "US"),
    ("The Guardian AI", "https://www.theguardian.com/technology/artificialintelligenceai/rss", "https://www.theguardian.com/technology/artificialintelligenceai", "ai", 4, "GB"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "https://www.technologyreview.com", "technology", 5, "US"),
    # --- technology
    ("TechCrunch", "https://techcrunch.com/feed/", "https://techcrunch.com", "technology", 4, "US"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "https://www.theverge.com", "technology", 4, "US"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "https://arstechnica.com", "technology", 4, "US"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "https://spectrum.ieee.org", "technology", 4, "US"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "https://www.bbc.com/news/technology", "technology", 4, "GB"),
    ("The Guardian Technology", "https://www.theguardian.com/uk/technology/rss", "https://www.theguardian.com/technology", "technology", 4, "GB"),
    ("Microsoft Official Blog", "https://blogs.microsoft.com/feed/", "https://blogs.microsoft.com", "technology", 3, "US"),
    ("Google Research", "https://research.google/blog/rss/", "https://research.google/blog", "ai", 3, "US"),
    # --- startups
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/", "https://techcrunch.com/category/startups", "startups", 4, "US"),
    ("YourStory", "https://yourstory.com/feed", "https://yourstory.com", "startups", 3, "IN"),
    # --- business / finance / economy
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "https://www.bbc.com/news/business", "business", 4, "GB"),
    ("The Guardian Business", "https://www.theguardian.com/uk/business/rss", "https://www.theguardian.com/business", "business", 4, "GB"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "https://www.cnbc.com", "finance", 4, "US"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "https://economictimes.indiatimes.com/markets", "finance", 4, "IN"),
    # --- India
    ("BBC India", "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml", "https://www.bbc.com/news/world/asia/india", "india", 4, "GB"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "https://www.thehindu.com", "india", 4, "IN"),
    ("Indian Express", "https://indianexpress.com/feed/", "https://indianexpress.com", "india", 4, "IN"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "https://timesofindia.indiatimes.com", "india", 3, "IN"),
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories", "https://www.ndtv.com", "india", 3, "IN"),
    # --- science / space / climate / health
    ("Nature", "https://www.nature.com/nature.rss", "https://www.nature.com", "science", 5, "GB"),
    ("ScienceDaily", "https://www.sciencedaily.com/rss/all.xml", "https://www.sciencedaily.com", "science", 3, "US"),
    ("BBC Science & Environment", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "https://www.bbc.com/news/science_and_environment", "science", 4, "GB"),
    ("The Guardian Science", "https://www.theguardian.com/science/rss", "https://www.theguardian.com/science", "science", 4, "GB"),
    ("Ars Technica Science", "https://feeds.arstechnica.com/arstechnica/science", "https://arstechnica.com/science", "science", 3, "US"),
    ("NASA", "https://www.nasa.gov/feed/", "https://www.nasa.gov", "space", 5, "US"),
    ("SpaceNews", "https://spacenews.com/feed/", "https://spacenews.com", "space", 4, "US"),
    ("The Guardian Climate", "https://www.theguardian.com/environment/climate-crisis/rss", "https://www.theguardian.com/environment/climate-crisis", "climate", 4, "GB"),
    ("BBC Health", "https://feeds.bbci.co.uk/news/health/rss.xml", "https://www.bbc.com/news/health", "health", 4, "GB"),
    # --- cybersecurity
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "https://krebsonsecurity.com", "cybersecurity", 4, "US"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "https://www.bleepingcomputer.com", "cybersecurity", 4, "US"),
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews", "https://thehackernews.com", "cybersecurity", 3, "US"),
    # --- sports / entertainment / education / travel
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "https://www.bbc.com/sport", "sports", 3, "GB"),
    ("ESPN", "https://www.espn.com/espn/rss/news", "https://www.espn.com", "sports", 3, "US"),
    ("BBC Entertainment & Arts", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "https://www.bbc.com/news/entertainment_and_arts", "entertainment", 3, "GB"),
    ("BBC Education", "https://feeds.bbci.co.uk/news/education/rss.xml", "https://www.bbc.com/news/education", "education", 3, "GB"),
    ("The Guardian Travel", "https://www.theguardian.com/travel/rss", "https://www.theguardian.com/travel", "travel", 3, "GB"),
]

_NEWSAPI = {
    "name": "Reuters & AP (via NewsAPI)",
    "type": "newsapi",
    "url": None,
    "homepage": "https://newsapi.org",
    "category": "world",
    "priority": 5,
    "country": None,
    "config": {"mode": "top-headlines", "sources": "reuters,associated-press"},
}


def source_id(name: str) -> str:
    return slugify(name)


def _base(settings: Settings, **kw) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "type": "rss", "language": "en", "enabled": True, "poll_minutes": settings.default_poll_minutes,
        "priority": 3, "config": {}, "created_at": now, "updated_at": now,
        "last_fetch_at": None, "last_success_at": None, "last_error": None, "last_error_at": None,
        "consecutive_failures": 0, "articles_total": 0, "etag": None, "last_modified": None, "seeded": True, **kw,
    }


def ensure_default_sources(db: Database, settings: Settings) -> int:
    """Insert missing default sources. Never touches sources that already exist."""
    inserted = 0
    docs = [
        _base(settings, _id=source_id(n), name=n, url=u, homepage=h, category=c, priority=p, country=cty)
        for n, u, h, c, p, cty in _RSS
    ]
    docs.append(_base(settings, _id=source_id(_NEWSAPI["name"]), enabled=settings.newsapi_configured, **_NEWSAPI))
    for d in docs:
        res = db["news_sources"].update_one({"_id": d["_id"]}, {"$setOnInsert": d}, upsert=True)
        inserted += 1 if res.upserted_id is not None else 0
    return inserted


def ensure_default_categories(db: Database) -> int:
    inserted = 0
    for c in DEFAULT_CATEGORIES:
        res = db["news_categories"].update_one({"slug": c["slug"]}, {"$setOnInsert": {**c, "created_at": datetime.now(timezone.utc)}}, upsert=True)
        inserted += 1 if res.upserted_id is not None else 0
    return inserted
