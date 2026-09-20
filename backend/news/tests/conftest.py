"""News test setup: a THROWAWAY database, no background worker, no real network or LLM calls."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["NEWS_MONGO_DB"] = "news_data_pytest"
os.environ["NEWS_ADMIN_API_KEY"] = "test-admin-key"
os.environ["NEWS_WORKER_ENABLED"] = "false"
os.environ["NEWS_AI_ENABLED"] = "false"
os.environ["NEWS_API_KEY"] = ""          # never let a real key in .env leak into tests
os.environ.setdefault("NEWS_MONGO_URI", os.environ.get("EVENT_MONGO_URI", "mongodb://localhost:27017"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from backend.news.database import close_client, ensure_indexes, get_client, get_db  # noqa: E402

TEST_DB = "news_data_pytest"


@pytest.fixture(scope="session", autouse=True)
def _mongo():
    from backend.news.config import get_settings

    assert get_settings().mongo_db == TEST_DB, "tests must never run against a real database"
    try:
        get_client().admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB not available: {exc.__class__.__name__}", allow_module_level=True)
    yield
    get_client().drop_database(TEST_DB)
    close_client()


@pytest.fixture()
def db(_mongo):
    from backend.news.cache import cache
    from backend.news.processing import classify
    from backend.news.sources import ensure_default_categories

    database = get_db()
    for name in database.list_collection_names():
        database.drop_collection(name)
    ensure_indexes(database)
    ensure_default_categories(database)
    cache.clear()
    classify.invalidate_cache()
    return database


@pytest.fixture()
def client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.news.api import mount

    app = FastAPI()
    mount(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_headers():
    return {"X-Admin-Key": "test-admin-key"}


def ago(minutes: float = 0, hours: float = 0, days: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes, hours=hours, days=days)


_n = 0


def make_source(db, **over):
    """Insert a source document and return it."""
    global _n
    _n += 1
    doc = {
        "_id": f"src-{_n}", "name": f"Source {_n}", "type": "rss", "url": f"https://feed{_n}.example.org/rss.xml",
        "homepage": f"https://feed{_n}.example.org", "category": "world", "language": "en", "enabled": True,
        "poll_minutes": 15, "priority": 3, "config": {}, "last_fetch_at": None, "last_success_at": None,
        "last_error": None, "consecutive_failures": 0, "articles_total": 0, "etag": None, "last_modified": None,
        "created_at": ago(), "updated_at": ago(),
    }
    doc.update(over)
    db["news_sources"].insert_one(doc)
    return doc


def make_raw(title="OpenAI announces new AI model for developers", **over):
    global _n
    _n += 1
    raw = {
        "title": title, "link": f"https://example.org/story-{_n}",
        "description": "OpenAI said on Tuesday it has released a new AI model aimed at developers, with faster responses and lower prices.",
        "published": ago(minutes=30), "image": "https://example.org/img.jpg", "author": "Staff", "tags": [],
    }
    raw.update(over)
    return raw


def ingest(db, raw, source=None, **kw):
    from backend.news.pipeline import ingest_item
    from backend.news.processing import classify

    source = source or make_source(db)
    return ingest_item(db, raw, source, index=classify.load_index(db, force=True), **kw), source
