"""MongoDB connection + indexes for the News tool (synchronous PyMongo)."""
from __future__ import annotations

import logging
from threading import Lock

from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient
from pymongo.database import Database

from backend.news.config import get_settings

log = logging.getLogger(__name__)

ARTICLES = "news"  # the `news` collection from the spec

_client: MongoClient | None = None
_lock = Lock()


def get_client() -> MongoClient:
    global _client
    with _lock:
        if _client is None:
            _client = MongoClient(
                get_settings().mongo_uri,
                tz_aware=True,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                appname="casefile-news",
            )
        return _client


def get_db() -> Database:
    return get_client()[get_settings().mongo_db]


def close_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None


def ensure_indexes(db: Database | None = None) -> None:
    """Idempotent; safe on every startup."""
    db = db if db is not None else get_db()
    n = db[ARTICLES]

    n.create_index([("published_at", DESCENDING)], name="ix_published_at")
    n.create_index([("category", ASCENDING)], name="ix_category")
    n.create_index([("categories", ASCENDING)], name="ix_categories")
    n.create_index([("source.name", ASCENDING)], name="ix_source_name")
    n.create_index([("topics", ASCENDING)], name="ix_topics")
    n.create_index([("entities", ASCENDING)], name="ix_entities")
    n.create_index([("title", ASCENDING)], name="ix_title")
    n.create_index([("trending_score", DESCENDING)], name="ix_trending_score")
    n.create_index([("collected_at", DESCENDING)], name="ix_collected_at")
    n.create_index([("duplicate_group_id", ASCENDING)], name="ix_group")
    n.create_index([("title_tokens", ASCENDING), ("published_at", DESCENDING)], name="ix_cluster_candidates")
    n.create_index([("ai_status", ASCENDING), ("importance_score", DESCENDING)], name="ix_ai_queue")
    # Paginated feeds: one card per story (is_lead), newest activity first, optionally per category / source.
    n.create_index([("status", ASCENDING), ("is_lead", ASCENDING), ("last_activity_at", DESCENDING)], name="ix_feed")
    n.create_index([("status", ASCENDING), ("is_lead", ASCENDING), ("categories", ASCENDING), ("last_activity_at", DESCENDING)], name="ix_feed_category")
    n.create_index([("status", ASCENDING), ("is_lead", ASCENDING), ("trending_score", DESCENDING)], name="ix_feed_trending")
    n.create_index([("status", ASCENDING), ("source.name", ASCENDING), ("published_at", DESCENDING)], name="ix_feed_source")
    # Search. language_override is NOT "language": feeds carry codes like "hi" that Mongo can't stem.
    n.create_index(
        [("title", TEXT), ("entities", TEXT), ("topics", TEXT), ("categories", TEXT), ("summary", TEXT), ("source.name", TEXT), ("description", TEXT)],
        name="tx_news",
        weights={"title": 10, "entities": 6, "topics": 5, "categories": 3, "summary": 4, "source.name": 2, "description": 1},
        default_language="english",
        language_override="text_language",
    )

    db["stories"].create_index([("last_activity_at", DESCENDING)], name="ix_story_activity")
    db["stories"].create_index([("trending_score", DESCENDING)], name="ix_story_trending")
    db["stories"].create_index([("category", ASCENDING), ("trending_score", DESCENDING)], name="ix_story_category")
    db["news_categories"].create_index([("slug", ASCENDING)], unique=True, name="uq_category_slug")
    db["news_sources"].create_index([("enabled", ASCENDING), ("last_fetch_at", ASCENDING)], name="ix_source_due")
    db["news_runs"].create_index([("source_id", ASCENDING), ("started_at", DESCENDING)], name="ix_run_source")
    db["news_errors"].create_index([("created_at", DESCENDING)], name="ix_err_created")
    db["news_errors"].create_index([("source_id", ASCENDING), ("created_at", DESCENDING)], name="ix_err_source")
    log.info("News indexes ensured on %s", db.name)
