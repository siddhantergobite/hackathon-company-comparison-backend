"""News admin API: source management, categories, health. Requires the `X-Admin-Key` header.

Lives under /api/admin/news so the existing admin key handling in the frontend applies.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from pymongo.database import Database

from backend.common.errors import ApiError, HubRoute
from backend.news.config import get_settings
from backend.news.database import get_db
from backend.news.models import CategoryCreate, CategoryUpdate, SourceCreate, SourceUpdate
from backend.news.services import admin_service as admin


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise ApiError(503, "Admin API is disabled: set NEWS_ADMIN_API_KEY (or EVENT_ADMIN_API_KEY) in .env")
    if not x_admin_key or not secrets.compare_digest(x_admin_key.encode(), expected.encode()):
        raise ApiError(401, "Invalid or missing admin key")


router = APIRouter(prefix="/api/admin/news", tags=["news-admin"], dependencies=[Depends(require_admin)], route_class=HubRoute)


class EnabledBody(BaseModel):
    enabled: bool


@router.get("/session")
def session():
    return {"ok": True}


@router.get("/stats")
def stats(db: Database = Depends(get_db)):
    return admin.stats(db)


@router.get("/sources")
def list_sources(db: Database = Depends(get_db)):
    return admin.list_sources(db)


@router.post("/sources", status_code=201)
def create_source(body: SourceCreate, db: Database = Depends(get_db)):
    return admin.create_source(db, body.model_dump())


@router.put("/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, db: Database = Depends(get_db)):
    return admin.update_source(db, source_id, body.model_dump(exclude_unset=True))


@router.post("/sources/{source_id}/enabled")
def set_enabled(source_id: str, body: EnabledBody, db: Database = Depends(get_db)):
    return admin.set_enabled(db, source_id, body.enabled)


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, db: Database = Depends(get_db)):
    admin.delete_source(db, source_id)
    return {"deleted": True, "id": source_id}


@router.post("/sources/{source_id}/fetch")
def fetch_now(source_id: str, db: Database = Depends(get_db)):
    """Fetch one source right now (synchronously) and return what happened."""
    return admin.fetch_now(db, source_id)


@router.post("/enrich")
def enrich(limit: int = Query(10, ge=1, le=50), db: Database = Depends(get_db)):
    """Run AI enrichment on the most important pending articles right now."""
    return admin.enrich_now(db, limit)


@router.post("/recluster")
def recluster(hours: int = Query(72, ge=1, le=240), db: Database = Depends(get_db)):
    """Re-run duplicate detection across recent articles and merge fragmented stories."""
    return admin.recluster_now(db, hours)


@router.get("/categories")
def list_categories(db: Database = Depends(get_db)):
    return admin.list_categories(db)


@router.post("/categories", status_code=201)
def create_category(body: CategoryCreate, db: Database = Depends(get_db)):
    return admin.create_category(db, body.model_dump())


@router.put("/categories/{slug}")
def update_category(slug: str, body: CategoryUpdate, db: Database = Depends(get_db)):
    return admin.update_category(db, slug, body.model_dump(exclude_unset=True))


@router.get("/runs")
def runs(limit: int = Query(40, ge=1, le=200), source: str | None = None, db: Database = Depends(get_db)):
    return admin.list_runs(db, limit, source)


@router.get("/errors")
def errors(limit: int = Query(100, ge=1, le=500), source: str | None = None, db: Database = Depends(get_db)):
    return admin.list_errors(db, limit, source)
