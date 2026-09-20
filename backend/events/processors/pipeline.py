"""Ingestion pipeline: Source -> Validate -> Normalize -> Dedupe -> Classify -> MongoDB.

`ingest_event` handles one raw record; `run_collector` drives a whole collector,
isolating per-record failures and logging the run + errors for the admin dashboard.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pymongo.database import Database

from backend.events.config import get_settings
from backend.events.services import event_service as svc
from backend.events.processors.classify import classify_event
from backend.events.processors.deduplicate import DuplicateMatch, find_duplicate
from backend.events.processors.normalize import ValidationFailure, normalize_event

log = logging.getLogger(__name__)

# Fields where a non-empty value from the source replaces what we have.
_SOURCE_AUTHORITATIVE = (
    "title", "description", "start_date", "end_date", "start_time", "end_time", "timezone",
    "is_online", "format", "image_url", "event_url", "status",
)


@dataclass
class IngestResult:
    action: str  # created | updated | unchanged | merged | flagged | skipped | invalid
    event_id: str | None = None
    slug: str | None = None
    duplicate_of: str | None = None
    confidence: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def find_by_identity(db: Database, source_name: str | None, source_event_id: str | None) -> dict | None:
    """Existing event for a (source, source event id) - also matches ids folded in by a merge."""
    if not source_name or not source_event_id:
        return None
    return db["events"].find_one(
        {
            "$or": [
                {"source.name": source_name, "source.source_event_id": source_event_id},
                {"other_sources": {"$elemMatch": {"name": source_name, "source_event_id": source_event_id}}},
            ]
        }
    )


def _blank(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _merge_into_master(db: Database, master: dict, event: dict, dry_run: bool) -> None:
    src = event.get("source") or {}
    others = list(master.get("other_sources") or [])
    known = {(o.get("name"), o.get("source_event_id")) for o in others}
    known.add(((master.get("source") or {}).get("name"), (master.get("source") or {}).get("source_event_id")))
    if (src.get("name"), src.get("source_event_id")) not in known:
        others.append(src)
    changes = svc.fill_missing(master, event)
    changes["other_sources"] = others
    changes["last_verified"] = svc.utcnow()
    if not dry_run:
        svc.update_event(db, master["_id"], changes)


def _update_existing(db: Database, existing: dict, event: dict, *, use_ai: bool | None, dry_run: bool) -> IngestResult:
    res = IngestResult("unchanged", existing["_id"], existing.get("slug"))
    if existing.get("manually_edited"):
        # An admin owns this record: only record that the source still lists it.
        if not dry_run:
            svc.update_event(db, existing["_id"], {"last_verified": svc.utcnow()})
        return res

    changes: dict[str, Any] = {}
    for f in _SOURCE_AUTHORITATIVE:
        if not _blank(event.get(f)) and event[f] != existing.get(f):
            changes[f] = event[f]
    for group in ("location", "organizer", "registration"):
        merged = {**(existing.get(group) or {})}
        for k, v in (event.get(group) or {}).items():
            if not _blank(v):
                merged[k] = v
        if merged != (existing.get(group) or {}):
            changes[group] = merged
    if (event.get("source") or {}).get("url") and (event["source"]["url"] != (existing.get("source") or {}).get("url")):
        changes["source"] = {**(existing.get("source") or {}), **{k: v for k, v in event["source"].items() if not _blank(v)}}
    for f in ("event_type", "summary", "categories", "topics", "audience", "keywords"):
        if not _blank(event.get(f)) and event[f] != existing.get(f):
            changes[f] = event[f]

    # fill anything still missing from classification (never overwrites)
    merged_view = {**existing, **changes}
    for k, v in classify_event(merged_view, use_ai=use_ai).items():
        if k not in changes and (k == "classified_by" or _blank(existing.get(k)) or existing.get(k) == "other"):
            changes[k] = v

    if changes:
        res.action = "updated"
    changes["last_verified"] = svc.utcnow()
    if not dry_run:
        svc.update_event(db, existing["_id"], changes)
    return res


def ingest_event(
    db: Database,
    raw: dict,
    *,
    source_name: str | None = None,
    source_url: str | None = None,
    auto_approve: bool | None = None,
    use_ai: bool | None = None,
    dry_run: bool = False,
    extra: dict | None = None,
) -> IngestResult:
    settings = get_settings()
    auto_approve = settings.ingest_auto_approve if auto_approve is None else auto_approve

    raw = dict(raw)
    src = dict(raw.get("source") or {}) if isinstance(raw.get("source"), dict) else {}
    if source_name and not src.get("name"):
        src["name"] = source_name
    if source_url and not src.get("url"):
        src["url"] = source_url
    raw["source"] = src

    try:
        event, warnings = normalize_event(raw)
    except ValidationFailure as exc:
        return IngestResult("invalid", errors=exc.errors)

    # 1) same source + same source event id -> refresh that record
    source = event["source"]
    existing = find_by_identity(db, source.get("name"), source.get("source_event_id"))
    if existing:
        res = _update_existing(db, existing, event, use_ai=use_ai, dry_run=dry_run)
        res.warnings = warnings
        return res

    # feeds often include past events; don't create records for things that already ended
    if event["status"] == "completed":
        return IngestResult("skipped", warnings=warnings + ["event already ended"])

    # 2) same event from another source (or a near-copy)
    match: DuplicateMatch | None = find_duplicate(db["events"], event)
    if match and match.confidence in ("exact", "high"):
        _merge_into_master(db, match.event, event, dry_run)
        return IngestResult(
            "merged", match.event["_id"], match.event.get("slug"), match.event["_id"], match.confidence, warnings
        )

    # 3) classification fills gaps; failures here never block storage
    try:
        event.update(classify_event(event, use_ai=use_ai))
    except Exception as exc:  # noqa: BLE001
        log.warning("classification failed for %r: %s", event.get("title"), exc)
        warnings.append("classification failed; stored without it")
        event.setdefault("event_type", "other")

    fields = {"manually_edited": False, **(extra or {})}
    if match:  # "possible": store, but queue for a human
        fields["possible_duplicate_of"] = match.event["_id"]
        review = "pending"
    else:
        review = "approved" if (auto_approve and event.get("event_url")) else "pending"

    if dry_run:
        return IngestResult("flagged" if match else "created", None, None, match.event["_id"] if match else None,
                            match.confidence if match else None, warnings)

    stored = svc.insert_event(db, event, review_status=review, extra=fields)
    return IngestResult(
        "flagged" if match else "created", stored["_id"], stored["slug"],
        match.event["_id"] if match else None, match.confidence if match else None, warnings,
    )


# ------------------------------------------------------------------------------- runs
def _hint(raw: dict) -> str:
    return str(raw.get("title") or raw.get("name") or raw.get("source_event_id") or raw.get("uid") or "?")[:200]


def _log_error(db: Database, run_id: Any, source: str, message: str, error_type: str, raw: dict | None) -> None:
    try:
        raw_text = json.dumps(raw, default=str, ensure_ascii=False)[:2000] if raw is not None else None
    except Exception:  # noqa: BLE001
        raw_text = None
    db["ingestion_errors"].insert_one(
        {
            "run_id": run_id, "source": source, "error_type": error_type, "message": message[:1000],
            "record": _hint(raw) if raw else None, "raw": raw_text, "created_at": svc.utcnow(),
        }
    )


def run_collector(
    db: Database,
    collector: Any,
    *,
    dry_run: bool = False,
    use_ai: bool | None = None,
    limit: int | None = None,
) -> dict:
    """Run one collector end to end. Never raises; returns the run summary."""
    name = collector.name
    counts = {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "merged": 0, "flagged": 0, "skipped": 0, "invalid": 0, "errors": 0}
    run_id = None
    if not dry_run:
        run_id = db["ingestion_runs"].insert_one(
            {"source": name, "label": getattr(collector, "label", name), "status": "running", "started_at": svc.utcnow(), "dry_run": False}
        ).inserted_id

    fatal: str | None = None
    try:
        for raw in collector.collect():
            counts["fetched"] += 1
            try:
                res = ingest_event(
                    db, raw, source_name=collector.source_name, source_url=getattr(collector, "source_url", None),
                    use_ai=use_ai, dry_run=dry_run,
                )
                counts[res.action] = counts.get(res.action, 0) + 1
                if res.action == "invalid" and not dry_run:
                    _log_error(db, run_id, name, "; ".join(res.errors), "validation", raw)
            except Exception as exc:  # noqa: BLE001 - one bad record must not stop the run
                counts["errors"] += 1
                log.exception("record failed in %s", name)
                if not dry_run:
                    _log_error(db, run_id, name, str(exc), exc.__class__.__name__, raw)
            if limit and counts["fetched"] >= limit:
                break
    except Exception as exc:  # noqa: BLE001 - collector-level failure (network, auth, parse)
        fatal = f"{exc.__class__.__name__}: {exc}"
        log.exception("collector %s failed", name)
        if not dry_run:
            _log_error(db, run_id, name, fatal, exc.__class__.__name__, None)

    ok_records = counts["created"] + counts["updated"] + counts["unchanged"] + counts["merged"] + counts["flagged"] + counts["skipped"]
    bad_records = counts["errors"] + counts["invalid"]
    if fatal and ok_records == 0:
        status = "failed"
    elif fatal or bad_records:
        status = "partial" if ok_records else "failed"
    else:
        status = "success"

    summary = {"source": name, "status": status, "counts": counts, "error": fatal, "dry_run": dry_run}
    if run_id is not None:
        db["ingestion_runs"].update_one(
            {"_id": run_id}, {"$set": {"status": status, "counts": counts, "error": fatal, "finished_at": svc.utcnow()}}
        )
        svc.refresh_statuses(db)
    return summary
