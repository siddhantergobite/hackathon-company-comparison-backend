"""Public event API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from backend.events.database import get_db
from backend.events.errors import EventHubRoute
from backend.events.models import EventOut, EventPage
from backend.events.services import event_service as svc
from backend.events.services.event_service import ApiError, ListParams

router = APIRouter(prefix="/api/events", tags=["events"], route_class=EventHubRoute)


def _params(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    search: str | None = Query(None, max_length=200),
    event_type: str | None = Query(None, description="One or more (comma-separated), e.g. conference,meetup"),
    country: str | None = None,
    state: str | None = None,
    city: str | None = None,
    category: str | None = Query(None, description="One or more (comma-separated)"),
    start_date: str | None = Query(None, description="Range start (YYYY-MM-DD); returns events overlapping the range"),
    end_date: str | None = Query(None, description="Range end (YYYY-MM-DD)"),
    is_online: bool | None = None,
    format: str | None = Query(None, description="online | offline | hybrid (comma-separated)"),
    price_type: str | None = Query(None, description="free | paid"),
    sort: str = Query("soonest", description="soonest | latest | recently_added | recently_updated"),
    status: str | None = Query(None, description="Comma-separated. Default: upcoming,ongoing"),
) -> ListParams:
    return ListParams(
        page=page, limit=limit, search=search, event_type=event_type, country=country, state=state,
        city=city, category=category, start_date=start_date, end_date=end_date, is_online=is_online,
        format=format, price_type=price_type, sort=sort, status=status,
    )


@router.get("", response_model=EventPage)
def list_events(params: ListParams = Depends(_params), db: Database = Depends(get_db)):
    return svc.list_events(db, params, public=True)


# NOTE: fixed paths must be declared before "/{event_id}".
@router.get("/types")
def event_types(db: Database = Depends(get_db)):
    return svc.list_event_types(db)


@router.get("/categories")
def categories(include_empty: bool = False, db: Database = Depends(get_db)):
    return svc.list_categories(db, include_empty=include_empty)


@router.get("/locations")
def locations(country: str | None = None, state: str | None = None, db: Database = Depends(get_db)):
    return svc.list_locations(db, country=country, state=state)


@router.get("/slug/{slug}", response_model=EventOut)
def event_by_slug(slug: str, db: Database = Depends(get_db)):
    doc = svc.get_event_by_slug(db, slug)
    if not doc:
        raise ApiError(404, "Event not found")
    return doc


@router.get("/{event_id}", response_model=EventOut)
def event_by_id(event_id: str, db: Database = Depends(get_db)):
    doc = svc.get_event(db, event_id)
    if not doc:
        raise ApiError(404, "Event not found")
    return doc
