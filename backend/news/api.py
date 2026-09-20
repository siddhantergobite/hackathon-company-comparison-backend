"""Wiring for the News tool inside the Casefile FastAPI app.

`backend/main.py` calls `mount(app)` and composes `lifespan` with the Event Hub's. Everything is
defensive: if MongoDB or the settings are missing, Casefile keeps running and only the News
endpoints answer 503.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.common.errors import ApiError
from backend.news.config import get_settings
from backend.news.database import close_client, ensure_indexes, get_db
from backend.news.pipeline import run_due_sources
from backend.news.routes import admin, news
from backend.news.sources import ensure_default_categories, ensure_default_sources

log = logging.getLogger("news")


def mount(app: FastAPI) -> None:
    # The admin router is registered first so /api/admin/news/... can never be shadowed.
    app.include_router(admin.router)
    app.include_router(news.router)


def _startup_tasks() -> None:
    db = get_db()
    ensure_indexes(db)
    cats = ensure_default_categories(db)
    srcs = ensure_default_sources(db, get_settings())
    log.info("News ready (%s): +%d categories, +%d sources", db.name, cats, srcs)


def cycle() -> dict:
    """One collection cycle (also used by the CLI and the admin 'run now')."""
    return run_due_sources(get_db(), get_settings())


async def _worker() -> None:
    settings = get_settings()
    await asyncio.sleep(max(0, settings.startup_delay_seconds))
    while True:
        try:
            summary = await asyncio.to_thread(cycle)
            if summary.get("sources"):
                log.info("news cycle: %d source(s), enrichment=%s", summary["sources"], summary.get("enrichment"))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the loop must survive any single failure
            log.exception("news cycle failed")
        await asyncio.sleep(max(30, settings.poll_interval_seconds))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    try:
        settings = get_settings()
        if not settings.admin_api_key:
            log.warning("News admin key not set: /api/admin/news/* is disabled")
        await asyncio.to_thread(_startup_tasks)
        if settings.worker_enabled:
            task = asyncio.create_task(_worker())
        else:
            log.info("News background worker is disabled (NEWS_WORKER_ENABLED=false)")
    except ApiError as exc:
        log.warning("News disabled: %s", exc.message)
    except Exception as exc:  # noqa: BLE001 - MongoDB down etc. must not stop Casefile
        log.error("News could not start (%s); the rest of Casefile is unaffected", exc.__class__.__name__)
    try:
        yield
    finally:
        if task:
            task.cancel()
        close_client()
