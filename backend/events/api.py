"""Wiring for the Event Hub inside the Casefile FastAPI app.

`backend/main.py` calls `mount(app)` and passes `lifespan` to FastAPI. Everything here
is defensive: if MongoDB or EVENT_MONGO_URI is missing, the rest of Casefile keeps working
and Event Hub endpoints answer 503 instead of taking the server down.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.events.config import get_settings
from backend.events.database import close_client, ensure_indexes, get_db
from backend.events.errors import ApiError
from backend.events.routes import admin, events
from backend.events.services import event_service as svc

log = logging.getLogger("events")


def mount(app: FastAPI) -> None:
    app.include_router(events.router)
    app.include_router(admin.router)


def _startup_tasks() -> None:
    db = get_db()
    ensure_indexes(db)
    svc.ensure_default_categories(db)
    log.info("Event Hub ready (%s). Status refresh: %s", db.name, svc.refresh_statuses(db))


async def _status_refresher(minutes: int) -> None:
    while True:
        await asyncio.sleep(max(1, minutes) * 60)
        try:
            await asyncio.to_thread(lambda: svc.refresh_statuses(get_db()))
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("periodic event status refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    try:
        settings = get_settings()
        if not settings.admin_api_key:
            log.warning("EVENT_ADMIN_API_KEY is empty: /api/admin/* is disabled")
        await asyncio.to_thread(_startup_tasks)
        task = asyncio.create_task(_status_refresher(settings.status_refresh_minutes))
    except ApiError as exc:
        log.warning("Event Hub disabled: %s", exc.message)
    except Exception as exc:  # noqa: BLE001 - MongoDB down etc. must not stop Casefile
        log.error("Event Hub could not start (%s); the rest of Casefile is unaffected", exc.__class__.__name__)
    try:
        yield
    finally:
        if task:
            task.cancel()
        close_client()
