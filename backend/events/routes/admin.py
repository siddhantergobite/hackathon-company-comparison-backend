"""Admin API. Every route requires the `X-Admin-Key` header (EVENT_ADMIN_API_KEY)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from pymongo.database import Database

from backend.events.config import get_settings
from backend.events.database import get_db
from backend.events.errors import EventHubRoute
from backend.events.models import AdminEventOut, AdminEventPage, EventCreate, EventUpdate
from backend.events.services import admin_service as admin
from backend.events.services import event_service as svc
from backend.events.services.event_service import ApiError, ListParams


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        raise ApiError(503, "Admin API is disabled: set EVENT_ADMIN_API_KEY in .env")
    if not x_admin_key or not secrets.compare_digest(x_admin_key.encode(), expected.encode()):
        raise ApiError(401, "Invalid or missing admin key")


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)], route_class=EventHubRoute)


class DuplicateBody(BaseModel):
    duplicate_of: str = Field(min_length=1)


class MergeBody(BaseModel):
    master_id: str = Field(min_length=1)
    duplicate_ids: list[str] = Field(min_length=1, max_length=20)


class DismissBody(BaseModel):
    a_id: str
    b_id: str


class ReprocessBody(BaseModel):
    use_ai: bool | None = None
    force: bool = False


def _out(doc: dict) -> dict:
    return svc.doc_to_api(doc)


@router.get("/session")
def session():
    return {"ok": True}


@router.get("/stats")
def stats(db: Database = Depends(get_db)):
    return admin.stats(db)


@router.get("/events", response_model=AdminEventPage)
def list_events(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    review_status: str | None = None,
    status: str | None = None,
    source: str | None = None,
    event_type: str | None = None,
    needs_review: bool | None = None,
    sort: str = "recently_updated",
    db: Database = Depends(get_db),
):
    p = ListParams(
        page=page, limit=limit, search=search, review_status=review_status, status=status,
        source=source, event_type=event_type, needs_review=needs_review, sort=sort,
    )
    return svc.list_events(db, p, public=False)


@router.post("/events", response_model=AdminEventOut, status_code=201)
def create_event(body: EventCreate, use_ai: bool = False, db: Database = Depends(get_db)):
    doc, possible_dup = admin.create_event(db, body.model_dump(mode="python", exclude_none=True), use_ai=use_ai)
    out = _out(doc)
    out["possible_duplicate_of"] = possible_dup
    return out


@router.get("/events/{event_id}", response_model=AdminEventOut)
def get_event(event_id: str, db: Database = Depends(get_db)):
    doc = svc.get_event(db, event_id, public=False)
    if not doc:
        raise ApiError(404, "Event not found")
    return doc


@router.put("/events/{event_id}", response_model=AdminEventOut)
def update_event(event_id: str, body: EventUpdate, db: Database = Depends(get_db)):
    patch = body.model_dump(mode="python", exclude_unset=True)
    if not patch:
        raise ApiError(400, "No fields to update")
    return _out(admin.update_event(db, event_id, patch))


@router.delete("/events/{event_id}")
def delete_event(event_id: str, db: Database = Depends(get_db)):
    admin.delete_event(db, event_id)
    return {"deleted": True, "id": event_id}


@router.post("/events/{event_id}/approve", response_model=AdminEventOut)
def approve(event_id: str, db: Database = Depends(get_db)):
    return _out(admin.approve_event(db, event_id))


@router.post("/events/{event_id}/reject", response_model=AdminEventOut)
def reject(event_id: str, db: Database = Depends(get_db)):
    return _out(admin.reject_event(db, event_id))


@router.post("/events/{event_id}/duplicate", response_model=AdminEventOut)
def mark_duplicate(event_id: str, body: DuplicateBody, db: Database = Depends(get_db)):
    return _out(admin.mark_duplicate(db, event_id, body.duplicate_of))


@router.post("/events/{event_id}/reprocess", response_model=AdminEventOut)
def reprocess(event_id: str, body: ReprocessBody | None = None, db: Database = Depends(get_db)):
    body = body or ReprocessBody()
    return _out(admin.reprocess_event(db, event_id, use_ai=body.use_ai, force=body.force))


@router.post("/merge", response_model=AdminEventOut)
def merge(body: MergeBody, db: Database = Depends(get_db)):
    return _out(admin.merge_events(db, body.master_id, body.duplicate_ids))


@router.get("/duplicates")
def duplicates(limit: int = Query(50, ge=1, le=200), db: Database = Depends(get_db)):
    return admin.duplicate_suggestions(db, limit)


@router.post("/duplicates/dismiss")
def dismiss(body: DismissBody, db: Database = Depends(get_db)):
    admin.dismiss_duplicate(db, body.a_id, body.b_id)
    return {"dismissed": True}


@router.get("/sources")
def sources(db: Database = Depends(get_db)):
    return admin.sources_health(db)


@router.get("/ingestion/runs")
def runs(limit: int = Query(30, ge=1, le=200), source: str | None = None, db: Database = Depends(get_db)):
    return admin.list_runs(db, limit, source)


@router.get("/ingestion/errors")
def errors(limit: int = Query(100, ge=1, le=500), source: str | None = None, db: Database = Depends(get_db)):
    return admin.list_ingestion_errors(db, limit, source)
