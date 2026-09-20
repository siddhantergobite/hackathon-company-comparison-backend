"""Test setup: uses a THROWAWAY database (never `event_data`) on the configured MongoDB."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Must run before any `app` import so settings pick these up.
os.environ["EVENT_MONGO_DB"] = "event_data_pytest"
os.environ["EVENT_ADMIN_API_KEY"] = "test-admin-key"
os.environ["EVENT_AI_ENABLED"] = "false"
os.environ["EVENT_INGEST_AUTO_APPROVE"] = "true"
os.environ.setdefault("EVENT_MONGO_URI", "mongodb://localhost:27017")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from backend.events.database import close_client, ensure_indexes, get_client, get_db  # noqa: E402

TEST_DB = "event_data_pytest"


@pytest.fixture(scope="session", autouse=True)
def _mongo():
    from backend.events.config import get_settings

    assert get_settings().event_mongo_db == TEST_DB, "tests must never run against a real database"
    try:
        get_client().admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB not available: {exc.__class__.__name__}", allow_module_level=True)
    yield
    get_client().drop_database(TEST_DB)
    close_client()


@pytest.fixture()
def db(_mongo):
    database = get_db()
    for name in database.list_collection_names():
        database.drop_collection(name)
    ensure_indexes(database)
    from backend.events.services.event_service import ensure_default_categories

    ensure_default_categories(database)
    return database


@pytest.fixture()
def client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.events.api import mount

    app = FastAPI()  # isolated app: only the Event Hub routers (lifespan/startup not run)
    mount(app)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def admin_headers():
    return {"X-Admin-Key": "test-admin-key"}


def days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def make_raw(**over):
    """A valid raw event dated in the future."""
    raw = {
        "title": "Test AI Summit 2026",
        "event_type": "summit",
        "description": "A summit about artificial intelligence and machine learning for developers and founders.",
        "start_date": days(30),
        "end_date": days(31),
        "location": {"venue": "Grand Hall", "city": "Berlin", "country": "Germany"},
        "organizer": {"name": "Acme Events"},
        "event_url": "https://example.com/e/ai-summit",
        "source": {"name": "TestSource", "source_event_id": "t-1"},
    }
    raw.update(over)
    return raw
