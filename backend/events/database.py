"""MongoDB connection + index management (synchronous PyMongo).

The same code path is used by the API (FastAPI runs `def` routes in a thread pool),
the seed script, and the ingestion pipeline.
"""
from __future__ import annotations

import logging
from threading import Lock

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from backend.events.config import get_settings

log = logging.getLogger(__name__)

_client: MongoClient | None = None
_lock = Lock()


def get_client() -> MongoClient:
    global _client
    with _lock:
        if _client is None:
            settings = get_settings()
            _client = MongoClient(
                settings.event_mongo_uri,
                tz_aware=True,  # datetimes come back as UTC-aware
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                appname="global-event-aggregator",
            )
        return _client


def get_db() -> Database:
    return get_client()[get_settings().event_mongo_db]


def close_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:  # noqa: BLE001 - health probe: any failure means "down"
        return False


def ensure_indexes(db: Database | None = None) -> None:
    """Create all indexes. Idempotent; safe to run on every startup."""
    db = db if db is not None else get_db()
    ev = db["events"]

    ev.create_index([("slug", ASCENDING)], unique=True, name="uq_slug")
    ev.create_index([("start_date", ASCENDING)], name="ix_start_date")
    ev.create_index([("event_type", ASCENDING)], name="ix_event_type")
    ev.create_index([("location.country", ASCENDING)], name="ix_country")
    ev.create_index([("location.state", ASCENDING)], name="ix_state")
    ev.create_index([("location.city", ASCENDING)], name="ix_city")
    ev.create_index([("categories", ASCENDING)], name="ix_categories")
    ev.create_index([("status", ASCENDING)], name="ix_status")
    ev.create_index([("source.name", ASCENDING)], name="ix_source_name")
    ev.create_index([("created_at", DESCENDING)], name="ix_created_at")
    ev.create_index([("updated_at", DESCENDING)], name="ix_updated_at")
    ev.create_index([("previous_slugs", ASCENDING)], sparse=True, name="ix_previous_slugs")
    # Main public listing: approved + status + soonest first.
    ev.create_index(
        [("review_status", ASCENDING), ("status", ASCENDING), ("start_date", ASCENDING)],
        name="ix_listing",
    )
    # Event identity: one record per (source, source event id). Only enforced when an id exists.
    ev.create_index(
        [("source.name", ASCENDING), ("source.source_event_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"source.source_event_id": {"$type": "string"}},
        name="uq_source_event",
    )

    db["categories"].create_index([("slug", ASCENDING)], unique=True, name="uq_category_slug")
    db["ingestion_runs"].create_index([("source", ASCENDING), ("started_at", DESCENDING)], name="ix_run_source")
    db["ingestion_errors"].create_index([("created_at", DESCENDING)], name="ix_err_created")
    db["ingestion_errors"].create_index([("source", ASCENDING)], name="ix_err_source")
    log.info("MongoDB indexes ensured on %s", db.name)
