"""Event queries and write helpers shared by the API, admin, seed and ingestion code."""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from backend.events.errors import ApiError  # noqa: F401  (re-exported)
from backend.events.models import EVENT_TYPE_ALIASES, EVENT_TYPE_LABELS
from backend.events.taxonomy import CATEGORIES, canonical_category, slugify

PUBLIC_STATUSES_DEFAULT = ["upcoming", "ongoing"]
ALL_STATUSES = {"upcoming", "ongoing", "completed", "cancelled", "postponed"}
REVIEW_STATUSES = {"pending", "approved", "rejected", "duplicate"}
FORMATS = {"online", "offline", "hybrid"}

SEARCH_FIELDS = [
    "title", "summary", "description", "organizer.name", "location.city", "location.state",
    "location.country", "location.venue", "categories", "topics", "keywords", "audience",
]

SORTS: dict[str, list[tuple[str, int]]] = {
    "soonest": [("start_date", ASCENDING), ("start_time", ASCENDING), ("_id", ASCENDING)],
    "latest": [("start_date", DESCENDING), ("start_time", DESCENDING), ("_id", ASCENDING)],
    "recently_added": [("created_at", DESCENDING), ("_id", ASCENDING)],
    "recently_updated": [("updated_at", DESCENDING), ("_id", ASCENDING)],
}
SORT_ALIASES = {
    "soonest_first": "soonest", "date_asc": "soonest", "date": "soonest",
    "latest_first": "latest", "date_desc": "latest",
    "added": "recently_added", "new": "recently_added", "updated": "recently_updated",
}

# Fields never needed in a card/table row.
LIST_EXCLUDE = {"description": 0, "previous_slugs": 0, "merged_from": 0, "not_duplicates": 0, "keywords": 0, "audience": 0}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today_iso() -> str:
    return utcnow().date().isoformat()


def new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def doc_to_api(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = d.pop("_id")
    return d


# ---------------------------------------------------------------------------- query building
@dataclass
class ListParams:
    page: int = 1
    limit: int = 20
    search: str | None = None
    event_type: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_online: bool | None = None
    format: str | None = None
    price_type: str | None = None
    sort: str = "soonest"
    status: str | None = None
    # admin only
    review_status: str | None = None
    source: str | None = None
    needs_review: bool | None = None


def csv_values(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _ci_exact(value: str) -> dict:
    return {"$regex": f"^{re.escape(value.strip())}$", "$options": "i"}


def parse_iso_date(value: str | None, name: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ApiError(400, f"Invalid {name}: expected YYYY-MM-DD") from None


def resolve_event_types(value: str | None) -> list[str]:
    out = []
    for v in csv_values(value):
        key = v.lower().replace("_", " ").strip()
        canonical = key.replace(" ", "_")
        if canonical in EVENT_TYPE_LABELS:
            out.append(canonical)
        elif key in EVENT_TYPE_ALIASES:
            out.append(EVENT_TYPE_ALIASES[key])
        else:
            raise ApiError(400, f"Invalid event_type '{v}'")
    return out


def search_clause(text: str) -> list[dict]:
    """Every whitespace-separated token must match the START of a word in some field.

    Word-start matching keeps "AI" from matching "Spain" or "training" while still
    letting "mach" find "Machine Learning".
    """
    clauses = []
    for token in text.split()[:8]:
        token = token.strip()
        if not token:
            continue
        rx = {"$regex": rf"(?<![A-Za-z0-9]){re.escape(token)}", "$options": "i"}
        clauses.append({"$or": [{f: rx} for f in SEARCH_FIELDS]})
    return clauses


def build_query(p: ListParams, *, public: bool = True) -> dict:
    today = today_iso()
    clauses: list[dict] = []

    if public:
        clauses.append({"review_status": "approved"})
    elif p.review_status:
        rs = [v for v in csv_values(p.review_status)]
        bad = [v for v in rs if v not in REVIEW_STATUSES]
        if bad:
            raise ApiError(400, f"Invalid review_status '{bad[0]}'")
        clauses.append({"review_status": {"$in": rs}})

    statuses = csv_values(p.status) or (PUBLIC_STATUSES_DEFAULT if public else [])
    bad = [s for s in statuses if s not in ALL_STATUSES]
    if bad:
        raise ApiError(400, f"Invalid status '{bad[0]}'")
    if statuses:
        clauses.append({"status": {"$in": statuses}})
        # Don't trust a stale stored status: an event that already ended is never "upcoming".
        if set(statuses) <= {"upcoming", "ongoing"}:
            clauses.append({"end_date": {"$gte": today}})

    types = resolve_event_types(p.event_type)
    if types:
        clauses.append({"event_type": {"$in": types}})
    if p.country:
        clauses.append({"location.country": _ci_exact(p.country)})
    if p.state:
        clauses.append({"location.state": _ci_exact(p.state)})
    if p.city:
        clauses.append({"location.city": _ci_exact(p.city)})

    cats = [canonical_category(c) for c in csv_values(p.category)]
    if cats:
        clauses.append({"categories": {"$in": [re.compile(f"^{re.escape(c)}$", re.I) for c in cats]}})

    if p.is_online is not None:
        clauses.append({"is_online": p.is_online})
    fmts = [f.lower() for f in csv_values(p.format)]
    if fmts:
        bad = [f for f in fmts if f not in FORMATS]
        if bad:
            raise ApiError(400, f"Invalid format '{bad[0]}'")
        clauses.append({"format": {"$in": fmts}})
    if p.price_type:
        pt = p.price_type.lower()
        if pt not in ("free", "paid"):
            raise ApiError(400, "Invalid price_type: expected 'free' or 'paid'")
        clauses.append({"registration.ticket_type": pt})

    # Date filters select events that OVERLAP the requested range.
    lo, hi = parse_iso_date(p.start_date, "start_date"), parse_iso_date(p.end_date, "end_date")
    if lo and hi and hi < lo:
        raise ApiError(400, "end_date must not be before start_date")
    if hi:
        clauses.append({"start_date": {"$lte": hi}})
    if lo:
        clauses.append({"end_date": {"$gte": lo}})

    if p.source:
        clauses.append({"source.name": _ci_exact(p.source)})
    if p.needs_review:
        clauses.append({"$or": [{"review_status": "pending"}, {"possible_duplicate_of": {"$type": "string"}}]})
    if p.search and p.search.strip():
        clauses.extend(search_clause(p.search.strip()))

    return {"$and": clauses} if clauses else {}


def paginate(total: int, page: int, limit: int) -> dict:
    return {"page": page, "limit": limit, "total": total, "total_pages": math.ceil(total / limit) if limit else 0}


def list_events(db: Database, p: ListParams, *, public: bool = True) -> dict:
    sort_key = SORT_ALIASES.get(p.sort, p.sort)
    if sort_key not in SORTS:
        raise ApiError(400, f"Invalid sort '{p.sort}'. Use one of: {', '.join(SORTS)}")
    query = build_query(p, public=public)
    coll = db["events"]
    total = coll.count_documents(query)
    cursor = (
        coll.find(query, LIST_EXCLUDE)
        .sort(SORTS[sort_key])
        .skip((p.page - 1) * p.limit)
        .limit(p.limit)
    )
    return {**paginate(total, p.page, p.limit), "events": [doc_to_api(d) for d in cursor]}


def get_event(db: Database, event_id: str, *, public: bool = True) -> dict | None:
    q: dict[str, Any] = {"_id": event_id}
    if public:
        q["review_status"] = "approved"
    doc = db["events"].find_one(q)
    return doc_to_api(doc) if doc else None


def get_event_by_slug(db: Database, slug: str, *, public: bool = True) -> dict | None:
    q: dict[str, Any] = {"$or": [{"slug": slug}, {"previous_slugs": slug}]}
    if public:
        q = {"$and": [q, {"review_status": "approved"}]}
    doc = db["events"].find_one(q)
    return doc_to_api(doc) if doc else None


# ----------------------------------------------------------------------------------- facets
def _public_base() -> dict:
    return {"review_status": "approved", "status": {"$in": PUBLIC_STATUSES_DEFAULT}, "end_date": {"$gte": today_iso()}}


def list_event_types(db: Database) -> list[dict]:
    counts = {
        r["_id"]: r["count"]
        for r in db["events"].aggregate([{"$match": _public_base()}, {"$group": {"_id": "$event_type", "count": {"$sum": 1}}}])
    }
    return [{"value": v, "label": label, "count": counts.get(v, 0)} for v, label in EVENT_TYPE_LABELS.items()]


def list_categories(db: Database, *, include_empty: bool = False) -> list[dict]:
    counts = {
        r["_id"]: r["count"]
        for r in db["events"].aggregate(
            [{"$match": _public_base()}, {"$unwind": "$categories"}, {"$group": {"_id": "$categories", "count": {"$sum": 1}}}]
        )
    }
    known = {c["name"]: c for c in db["categories"].find({}, {"_id": 0})}
    names = set(counts) | (set(known) if include_empty else set())
    out = [
        {"name": n, "slug": known.get(n, {}).get("slug") or slugify(n), "count": counts.get(n, 0)}
        for n in names
    ]
    out.sort(key=lambda c: (-c["count"], c["name"].lower()))
    return out


def list_locations(db: Database, country: str | None = None, state: str | None = None) -> dict:
    """Distinct countries; states for a country; cities for a country/state (with counts)."""
    base = _public_base()

    def distinct(field: str, extra: dict | None = None) -> list[dict]:
        match = {**base, **(extra or {}), field: {"$type": "string", "$ne": ""}}
        rows = db["events"].aggregate(
            [{"$match": match}, {"$group": {"_id": f"${field}", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
        )
        return [{"name": r["_id"], "count": r["count"]} for r in rows]

    out: dict[str, list[dict]] = {"countries": distinct("location.country"), "states": [], "cities": []}
    if country:
        c = {"location.country": _ci_exact(country)}
        out["states"] = distinct("location.state", c)
        if state:
            c["location.state"] = _ci_exact(state)
        out["cities"] = distinct("location.city", c)
    return out


# -------------------------------------------------------------------------------- writes
def unique_slug(db: Database, title: str, start_date: str | None, city: str | None = None, exclude_id: str | None = None) -> str:
    base = slugify(title) or "event"
    year = (start_date or "")[:4]
    if year and year not in base:
        base = f"{base}-{year}"

    def taken(s: str) -> bool:
        q: dict[str, Any] = {"$or": [{"slug": s}, {"previous_slugs": s}]}
        if exclude_id:
            q = {"$and": [q, {"_id": {"$ne": exclude_id}}]}
        return db["events"].count_documents(q, limit=1) > 0

    if not taken(base):
        return base
    city_slug = slugify(city or "")
    if city_slug and not taken(f"{base}-{city_slug}"):
        return f"{base}-{city_slug}"
    n = 2
    while taken(f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def register_categories(db: Database, names: list[str]) -> None:
    """Make sure every category used by an event exists in the `categories` collection."""
    for name in names:
        s = slugify(name)
        if s:
            db["categories"].update_one({"slug": s}, {"$setOnInsert": {"name": name, "slug": s, "created_at": utcnow()}}, upsert=True)


def ensure_default_categories(db: Database) -> None:
    register_categories(db, CATEGORIES)


def insert_event(db: Database, event: dict, *, review_status: str = "approved", extra: dict | None = None) -> dict:
    """Insert a normalised event (adds id, slug, timestamps). Returns the stored document."""
    now = utcnow()
    doc = {**event, **(extra or {})}
    doc.setdefault("last_verified", now)
    doc["created_at"] = doc["updated_at"] = now
    doc["review_status"] = review_status
    loc = doc.get("location") or {}
    requested_slug = doc.pop("slug", None)
    for _ in range(6):
        doc["_id"] = doc.get("_id") or new_event_id()
        doc["slug"] = (
            unique_slug(db, requested_slug, doc.get("start_date"), loc.get("city")) if requested_slug
            else unique_slug(db, doc["title"], doc.get("start_date"), loc.get("city"))
        )
        try:
            db["events"].insert_one(doc)
            break
        except DuplicateKeyError as exc:
            msg = str(exc)
            if "uq_slug" in msg:
                continue  # lost a slug race; recompute
            if "_id_" in msg or "index: _id" in msg:
                doc["_id"] = None
                continue
            raise
    else:  # pragma: no cover - extremely unlikely
        raise RuntimeError("Could not allocate a unique slug")
    register_categories(db, doc.get("categories") or [])
    return doc


def update_event(db: Database, event_id: str, changes: dict, *, unset: list[str] | None = None) -> dict | None:
    changes = {**changes, "updated_at": utcnow()}
    op: dict[str, Any] = {"$set": changes}
    if unset:
        op["$unset"] = {k: "" for k in unset}
    doc = db["events"].find_one_and_update({"_id": event_id}, op, return_document=True)
    if doc and changes.get("categories"):
        register_categories(db, changes["categories"])
    return doc


def _blank(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def fill_missing(target: dict, donor: dict) -> dict:
    """`$set` payload (dotted paths) that fills empty fields of `target` from `donor`."""
    updates: dict[str, Any] = {}
    for f in ("summary", "description", "start_time", "end_time", "timezone", "image_url", "event_url"):
        if _blank(target.get(f)) and not _blank(donor.get(f)):
            updates[f] = donor[f]
    for group in ("location", "organizer", "registration"):
        t, d = target.get(group) or {}, donor.get(group) or {}
        for k, v in d.items():
            if _blank(t.get(k)) and not _blank(v):
                updates[f"{group}.{k}"] = v
    for f in ("categories", "topics", "audience", "keywords"):
        merged = list(target.get(f) or [])
        seen = {x.casefold() for x in merged}
        for x in donor.get(f) or []:
            if x.casefold() not in seen:
                merged.append(x)
                seen.add(x.casefold())
        if merged != (target.get(f) or []):
            updates[f] = merged
    return updates


def refresh_statuses(db: Database) -> dict[str, int]:
    """Move events through upcoming -> ongoing -> completed based on their dates.

    cancelled/postponed are human decisions and are never touched. Uses the UTC date.
    """
    coll = db["events"]
    today = today_iso()
    live = {"$in": ["upcoming", "ongoing"]}
    now = utcnow()
    completed = coll.update_many(
        {"status": live, "end_date": {"$lt": today}}, {"$set": {"status": "completed", "updated_at": now}}
    ).modified_count
    ongoing = coll.update_many(
        {"status": "upcoming", "start_date": {"$lte": today}, "end_date": {"$gte": today}},
        {"$set": {"status": "ongoing", "updated_at": now}},
    ).modified_count
    reverted = coll.update_many(
        {"status": "ongoing", "start_date": {"$gt": today}}, {"$set": {"status": "upcoming", "updated_at": now}}
    ).modified_count
    return {"completed": completed, "ongoing": ongoing, "reverted_to_upcoming": reverted}
