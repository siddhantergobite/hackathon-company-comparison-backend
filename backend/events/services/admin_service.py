"""Admin operations: CRUD, moderation, duplicates/merge, reprocess, ingestion health."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymongo.database import Database

from backend.events.services import event_service as svc
from backend.events.services.event_service import ApiError
from backend.events.processors.classify import classify_event
from backend.events.processors.deduplicate import find_duplicate, suggest_duplicates
from backend.events.processors.normalize import ValidationFailure, normalize_event

SYSTEM_FIELDS = {
    "_id", "slug", "created_at", "updated_at", "review_status", "other_sources", "previous_slugs",
    "merged_from", "possible_duplicate_of", "duplicate_of", "manually_edited", "not_duplicates", "classified_by",
}


def _get(db: Database, event_id: str) -> dict:
    doc = db["events"].find_one({"_id": event_id})
    if not doc:
        raise ApiError(404, "Event not found")
    return doc


def _normalize_or_400(raw: dict) -> dict:
    try:
        event, _warnings = normalize_event(raw)
    except ValidationFailure as exc:
        raise ApiError(400, "; ".join(exc.errors)) from None
    return event


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------------------------ CRUD
def create_event(db: Database, payload: dict, *, use_ai: bool = False) -> tuple[dict, str | None]:
    """Manual/organizer-submitted event. Published immediately (admin action)."""
    event = _normalize_or_400(payload)
    event["source"]["name"] = event["source"].get("name") or "manual"
    event.update(classify_event(event, use_ai=use_ai))
    match = find_duplicate(db["events"], event)
    stored = svc.insert_event(db, event, review_status="approved", extra={"manually_edited": True})
    return stored, (match.event["_id"] if match else None)


def update_event(db: Database, event_id: str, patch: dict) -> dict:
    existing = _get(db, event_id)
    base = {k: v for k, v in existing.items() if k not in SYSTEM_FIELDS and k != "last_verified"}
    normalized = _normalize_or_400(_deep_merge(base, patch))

    changes = {k: v for k, v in normalized.items() if k != "slug"}
    changes["event_type"] = changes.get("event_type") or existing.get("event_type") or "other"
    changes["manually_edited"] = True

    new_slug = normalized.get("slug")
    if new_slug and new_slug != existing.get("slug"):
        loc = changes.get("location") or {}
        slug = svc.unique_slug(db, new_slug, None, loc.get("city"), exclude_id=event_id)
        if slug != new_slug:
            raise ApiError(400, f"Slug '{new_slug}' is already in use")
        changes["slug"] = slug
        changes["previous_slugs"] = sorted(set((existing.get("previous_slugs") or []) + [existing["slug"]]))
    doc = svc.update_event(db, event_id, changes)
    return doc  # type: ignore[return-value]


def delete_event(db: Database, event_id: str) -> None:
    _get(db, event_id)
    db["events"].delete_one({"_id": event_id})
    db["events"].update_many({"possible_duplicate_of": event_id}, {"$unset": {"possible_duplicate_of": ""}})
    db["events"].update_many({"duplicate_of": event_id}, {"$unset": {"duplicate_of": ""}, "$set": {"review_status": "pending"}})


# ------------------------------------------------------------------------------ moderation
def approve_event(db: Database, event_id: str) -> dict:
    doc = _get(db, event_id)
    changes: dict[str, Any] = {"review_status": "approved"}
    unset = ["duplicate_of"] if doc.get("duplicate_of") else []
    other = doc.get("possible_duplicate_of")
    if other:
        # approving a flagged event = "this is a different event"
        unset.append("possible_duplicate_of")
        db["events"].update_one({"_id": other}, {"$addToSet": {"not_duplicates": event_id}})
        changes["not_duplicates"] = sorted(set((doc.get("not_duplicates") or []) + [other]))
    return svc.update_event(db, event_id, changes, unset=unset)  # type: ignore[return-value]


def reject_event(db: Database, event_id: str) -> dict:
    _get(db, event_id)
    return svc.update_event(db, event_id, {"review_status": "rejected"}, unset=["possible_duplicate_of"])  # type: ignore[return-value]


def mark_duplicate(db: Database, event_id: str, master_id: str) -> dict:
    if event_id == master_id:
        raise ApiError(400, "An event cannot be a duplicate of itself")
    dup, master = _get(db, event_id), _get(db, master_id)
    if master.get("review_status") == "duplicate":
        raise ApiError(400, "The chosen original is itself marked as a duplicate")
    _register_alt_source(db, master, dup)
    return svc.update_event(  # type: ignore[return-value]
        db, event_id, {"review_status": "duplicate", "duplicate_of": master_id}, unset=["possible_duplicate_of"]
    )


def _register_alt_source(db: Database, master: dict, dup: dict) -> None:
    """Remember the duplicate's source identity on the master so re-ingesting it can't recreate it."""
    others = list(master.get("other_sources") or [])
    src = dup.get("source") or {}
    key = (src.get("name"), src.get("source_event_id"))
    own = ((master.get("source") or {}).get("name"), (master.get("source") or {}).get("source_event_id"))
    if src.get("source_event_id") and key != own and key not in {(o.get("name"), o.get("source_event_id")) for o in others}:
        others.append(src)
        svc.update_event(db, master["_id"], {"other_sources": others})


def merge_events(db: Database, master_id: str, duplicate_ids: list[str]) -> dict:
    master = _get(db, master_id)
    ids = [d for d in dict.fromkeys(duplicate_ids) if d != master_id]
    if not ids:
        raise ApiError(400, "Choose at least one other event to merge")
    dups = [_get(db, d) for d in ids]

    merged_from = list(master.get("merged_from") or [])
    other_sources = list(master.get("other_sources") or [])
    prev_slugs = set(master.get("previous_slugs") or [])
    known = {(o.get("name"), o.get("source_event_id")) for o in other_sources}
    known.add(((master.get("source") or {}).get("name"), (master.get("source") or {}).get("source_event_id")))
    working = dict(master)
    all_updates: dict[str, Any] = {}

    for d in dups:
        ups = svc.fill_missing(working, d)
        for k, v in ups.items():
            all_updates[k] = v
            # keep `working` current so later donors only fill what is still blank
            if "." in k:
                grp, sub = k.split(".", 1)
                working[grp] = {**(working.get(grp) or {}), sub: v}
            else:
                working[k] = v
        for s in [d.get("source") or {}, *(d.get("other_sources") or [])]:
            key = (s.get("name"), s.get("source_event_id"))
            if s.get("name") and key not in known:
                other_sources.append(s)
                known.add(key)
        if d.get("slug"):
            prev_slugs.add(d["slug"])
        prev_slugs.update(d.get("previous_slugs") or [])
        merged_from.append({"id": d["_id"], "title": d.get("title"), "source": (d.get("source") or {}).get("name"), "merged_at": svc.utcnow()})

    all_updates["other_sources"] = other_sources
    all_updates["previous_slugs"] = sorted(prev_slugs - {master.get("slug")})
    all_updates["merged_from"] = merged_from
    db["events"].delete_many({"_id": {"$in": ids}})
    db["events"].update_many({"possible_duplicate_of": {"$in": ids}}, {"$unset": {"possible_duplicate_of": ""}})
    doc = svc.update_event(db, master_id, all_updates, unset=["possible_duplicate_of"])
    return doc  # type: ignore[return-value]


def dismiss_duplicate(db: Database, a_id: str, b_id: str) -> None:
    _get(db, a_id), _get(db, b_id)
    for x, y in ((a_id, b_id), (b_id, a_id)):
        db["events"].update_one({"_id": x}, {"$addToSet": {"not_duplicates": y}})
        db["events"].update_one({"_id": x, "possible_duplicate_of": y}, {"$unset": {"possible_duplicate_of": ""}})


def duplicate_suggestions(db: Database, limit: int = 50) -> list[dict]:
    return [
        {"score": s["score"], "confidence": s["confidence"], "reasons": s["reasons"], "a": svc.doc_to_api(s["a"]), "b": svc.doc_to_api(s["b"])}
        for s in suggest_duplicates(db["events"], limit=limit)
    ]


def reprocess_event(db: Database, event_id: str, *, use_ai: bool | None = None, force: bool = False) -> dict:
    doc = _get(db, event_id)
    base = {k: v for k, v in doc.items() if k not in SYSTEM_FIELDS and k != "last_verified"}
    event = _normalize_or_400(base)
    event.pop("slug", None)
    updates = classify_event(event, use_ai=use_ai, force=force)
    event.update(updates)
    event["reprocessed_at"] = svc.utcnow()
    return svc.update_event(db, event_id, event)  # type: ignore[return-value]


# ---------------------------------------------------------------------------------- stats
def stats(db: Database) -> dict:
    ev = db["events"]

    def group(field: str) -> dict[str, int]:
        return {str(r["_id"]): r["count"] for r in ev.aggregate([{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}])}

    since = svc.utcnow() - timedelta(hours=24)
    return {
        "total": ev.estimated_document_count(),
        "by_review_status": group("review_status"),
        "by_status": group("status"),
        "by_source": group("source.name"),
        "needs_review": ev.count_documents({"$or": [{"review_status": "pending"}, {"possible_duplicate_of": {"$type": "string"}}]}),
        "ingestion_errors_24h": db["ingestion_errors"].count_documents({"created_at": {"$gte": since}}),
    }


# -------------------------------------------------------------------------- ingestion health
def _run_to_api(run: dict) -> dict:
    d = dict(run)
    d["id"] = str(d.pop("_id"))
    if d.get("run_id") is not None:
        d["run_id"] = str(d["run_id"])
    return d


def list_runs(db: Database, limit: int = 30, source: str | None = None) -> list[dict]:
    q = {"source": source} if source else {}
    return [_run_to_api(r) for r in db["ingestion_runs"].find(q).sort("started_at", -1).limit(limit)]


def list_ingestion_errors(db: Database, limit: int = 100, source: str | None = None) -> list[dict]:
    q = {"source": source} if source else {}
    return [_run_to_api(r) for r in db["ingestion_errors"].find(q).sort("created_at", -1).limit(limit)]


def sources_health(db: Database) -> list[dict]:
    from backend.events.collectors.registry import list_collectors

    counts = {r["_id"]: r["count"] for r in db["events"].aggregate([{"$group": {"_id": "$source.name", "count": {"$sum": 1}}}])}
    now = svc.utcnow()
    rows: list[dict] = []
    covered: set[str] = set()

    for c in list_collectors():
        last = db["ingestion_runs"].find_one({"source": c.name, "status": {"$ne": "running"}}, sort=[("started_at", -1)])
        errors_24h = db["ingestion_errors"].count_documents({"source": c.name, "created_at": {"$gte": now - timedelta(hours=24)}})
        configured = c.is_configured()
        if not configured:
            health = "not_configured"
        elif not last:
            health = "never_run"
        elif last["status"] == "failed":
            health = "failing"
        elif last["status"] == "partial" or errors_24h:
            health = "degraded"
        elif now - last["started_at"] > timedelta(hours=48):
            health = "stale"
        else:
            health = "healthy"
        covered.add(c.source_name)
        rows.append(
            {
                "name": c.name, "label": c.label, "description": c.description, "configured": configured,
                "health": health, "events": counts.get(c.source_name, 0), "errors_24h": errors_24h,
                "last_run": _run_to_api(last) if last else None,
            }
        )
    for name, n in counts.items():
        if name and name not in covered:
            rows.append(
                {"name": name, "label": name, "description": "Manual / seeded events (no automated collector)",
                 "configured": True, "health": "manual", "events": n, "errors_24h": 0, "last_run": None}
            )
    return rows
