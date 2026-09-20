"""News ingestion pipeline.

    Source -> Collect -> Normalize/Validate -> Duplicate detection -> Category -> Topics/Entities
           -> Extractive summary -> MongoDB  ... then, asynchronously, AI enrichment.

Ingestion is fast and never depends on the LLM: every article is stored immediately with
rule-based fields. `enrich_pending` later upgrades the most important ones with AI summaries, key
points and richer entities, a bounded number per cycle. One failing source never stops the others.
"""
from __future__ import annotations

import logging
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from backend.news import cache as news_cache
from backend.news.collectors.base import CollectorError
from backend.news.collectors.registry import make_collector
from backend.news.config import Settings, get_settings
from backend.news.processing import ai, classify, cluster, entities
from backend.news.processing.normalize import InvalidArticle, TooOld, normalize_article

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestResult:
    action: str  # created | clustered | updated | unchanged | skipped | invalid
    article_id: str | None = None
    group_id: str | None = None
    errors: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------- one article
def ingest_item(db: Database, raw: dict, source: dict, *, index: classify.CategoryIndex, settings: Settings | None = None,
                now: datetime | None = None, dry_run: bool = False) -> IngestResult:
    settings = settings or get_settings()
    now = now or utcnow()
    try:
        art = normalize_article(raw, source, now=now, max_age_days=settings.max_article_age_days)
    except TooOld:
        return IngestResult("skipped")
    except InvalidArticle as exc:
        return IngestResult("invalid", errors=exc.errors)

    news = db["news"]
    existing = news.find_one({"_id": art["_id"]}, {"title": 1, "description": 1, "image_url": 1, "duplicate_group_id": 1})
    if existing:
        changes = {k: art[k] for k in ("title", "description", "image_url") if art.get(k) and art[k] != existing.get(k)}
        if changes and not dry_run:
            news.update_one({"_id": art["_id"]}, {"$set": {**changes, "last_seen_at": now}})
            return IngestResult("updated", art["_id"], existing.get("duplicate_group_id"))
        if not dry_run:
            news.update_one({"_id": art["_id"]}, {"$set": {"last_seen_at": now}})
        return IngestResult("unchanged", art["_id"], existing.get("duplicate_group_id"))

    title, desc = art["title"], art.get("description")
    ent = entities.extract(title, desc)
    primary, cats = classify.classify(index, title, desc, hint=source.get("category"), feed_tags=art.get("feed_tags"))
    summary = ai.extractive_summary(desc)
    doc: dict[str, Any] = {
        **art,
        "summary": summary,
        "summary_source": "extractive" if summary else None,
        "key_points": ai.extractive_key_points(desc),
        "event": None,
        "category": primary,
        "categories": cats,
        "topics": classify.detect_topics(title, desc),
        "entities": ent["entities"],
        "entities_detail": {"people": ent["people"], "organizations": ent["organizations"], "products": ent["products"], "locations": ent["locations"]},
        "location": ent["location"],
        "title_tokens": cluster.distinctive_tokens(title)[:15],
        "is_breaking": classify.is_breaking_title(title),
        "is_lead": True,
        "importance_score": 0.0,
        "trending_score": 0.0,
        "duplicate_group_id": None,
        "related_articles": [],
        "coverage": {"count": 1, "sources": [art["source"]["name"]]},
        "last_activity_at": art["published_at"],
        "status": "published",
        "ai_status": "pending" if len(desc or "") >= ai.MIN_TEXT_FOR_AI else "skipped",
        "ai_attempts": 0,
    }
    gid, matched, _score = cluster.find_story(db, doc, window_hours=settings.cluster_window_hours)
    doc["duplicate_group_id"] = gid or cluster.group_id_for(doc["_id"])
    if dry_run:
        return IngestResult("clustered" if matched else "created", doc["_id"], doc["duplicate_group_id"])
    try:
        news.insert_one(doc)
    except DuplicateKeyError:   # lost a race with another worker: it is stored, that is what matters
        return IngestResult("unchanged", doc["_id"], doc["duplicate_group_id"])
    cluster.recompute_story(db, doc["duplicate_group_id"], now=now)
    return IngestResult("clustered" if matched else "created", doc["_id"], doc["duplicate_group_id"])


# ------------------------------------------------------------------------------- one source
def _log_error(db: Database, source: dict, run_id: Any, kind: str, message: str, record: str | None = None) -> None:
    db["news_errors"].insert_one(
        {"source_id": source.get("_id"), "source_name": source.get("name"), "run_id": run_id, "type": kind,
         "message": str(message)[:600], "record": (record or "")[:300] or None, "created_at": utcnow()}
    )


def next_due(source: dict) -> datetime | None:
    """When a source should next be polled. Repeated failures back off exponentially (max 6h)."""
    last = source.get("last_fetch_at")
    if not last:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    failures = int(source.get("consecutive_failures") or 0)
    minutes = min(int(source.get("poll_minutes") or 15) * (2 ** min(failures, 5)), 360)
    return last + timedelta(minutes=minutes)


def is_due(source: dict, now: datetime | None = None) -> bool:
    if not source.get("enabled", True):
        return False
    nd = next_due(source)
    return nd is None or (now or utcnow()) >= nd


def run_source(db: Database, source: dict, *, settings: Settings | None = None, client=None, collector=None,
               index: classify.CategoryIndex | None = None) -> dict:
    """Fetch + process one source. Never raises: failures are recorded and returned."""
    settings = settings or get_settings()
    index = index or classify.load_index(db)
    started = utcnow()
    counts = {"fetched": 0, "created": 0, "clustered": 0, "updated": 0, "unchanged": 0, "skipped": 0, "invalid": 0, "errors": 0}
    run_id = db["news_runs"].insert_one(
        {"source_id": source["_id"], "source_name": source.get("name"), "status": "running", "started_at": started}
    ).inserted_id
    status, fatal, etag, last_mod = "success", None, source.get("etag"), source.get("last_modified")

    try:
        collector = collector or make_collector(source, settings, client)
        ok, why = collector.is_available(source)
        if not ok:
            raise CollectorError(why)
        result = collector.fetch(source)
        etag, last_mod = result.etag, result.last_modified
        items = result.items[: settings.max_items_per_fetch]
        counts["fetched"] = len(items)
        logged = 0
        for raw in items:
            try:
                res = ingest_item(db, raw, source, index=index, settings=settings)
                counts[res.action] = counts.get(res.action, 0) + 1
                if res.action == "invalid" and logged < 20:
                    logged += 1
                    _log_error(db, source, run_id, "validation", "; ".join(res.errors), raw.get("title") or raw.get("link"))
            except Exception as exc:  # noqa: BLE001 - one bad item must not stop the rest
                counts["errors"] += 1
                log.exception("item failed in %s", source.get("name"))
                if logged < 20:
                    logged += 1
                    _log_error(db, source, run_id, exc.__class__.__name__, str(exc), raw.get("title") or raw.get("link"))
        good = counts["created"] + counts["clustered"] + counts["updated"] + counts["unchanged"] + counts["skipped"]
        if counts["errors"] and not good:
            status = "failed"
        elif counts["errors"] or counts["invalid"]:
            status = "partial"
    except Exception as exc:  # noqa: BLE001 - network / auth / parse failure of the whole source
        status, fatal = "failed", f"{exc.__class__.__name__}: {exc}"
        _log_error(db, source, run_id, exc.__class__.__name__, str(exc))
        log.warning("source %s failed: %s", source.get("name"), fatal)

    finished = utcnow()
    db["news_runs"].update_one({"_id": run_id}, {"$set": {"status": status, "counts": counts, "error": fatal, "finished_at": finished}})
    upd: dict[str, Any] = {"last_fetch_at": started, "updated_at": finished, "etag": etag, "last_modified": last_mod}
    if status == "failed":
        upd["last_error"], upd["last_error_at"] = fatal or "all items failed", finished
    else:
        upd["last_success_at"], upd["last_error"] = finished, None
    inc: dict[str, int] = {"articles_total": counts["created"] + counts["clustered"]}
    ops: dict[str, Any] = {"$set": upd, "$inc": inc}
    if status == "failed":
        inc["consecutive_failures"] = 1
    else:
        upd["consecutive_failures"] = 0
    db["news_sources"].update_one({"_id": source["_id"]}, ops)
    news_cache.cache.clear()
    return {"source_id": source["_id"], "source": source.get("name"), "status": status, "counts": counts, "error": fatal}


# ------------------------------------------------------------------------------ AI enrichment
def enrich_pending(db: Database, *, limit: int | None = None, settings: Settings | None = None,
                   index: classify.CategoryIndex | None = None) -> dict:
    """Upgrade the most important not-yet-enriched articles with AI summaries. Bounded per call."""
    settings = settings or get_settings()
    limit = settings.ai_max_per_cycle if limit is None else limit
    if limit <= 0 or not ai.ai_available():
        return {"enriched": 0, "failed": 0, "skipped": "ai_unavailable" if limit > 0 else "limit_zero"}
    index = index or classify.load_index(db)
    docs = list(db["news"].find({"status": "published", "ai_status": "pending"}).sort([("importance_score", -1), ("published_at", -1)]).limit(limit))

    def work(doc: dict):
        try:
            return doc, ai.enrich_article(doc, index), None
        except Exception as exc:  # noqa: BLE001 - recorded below; the article keeps its rule-based fields
            return doc, None, exc

    done = failed = 0
    groups: set[str] = set()
    with ThreadPoolExecutor(max_workers=max(1, settings.ai_concurrency)) as pool:
        for doc, updates, exc in pool.map(work, docs):
            if updates:
                db["news"].update_one({"_id": doc["_id"]}, {"$set": updates})
                done += 1
                if doc.get("duplicate_group_id"):
                    groups.add(doc["duplicate_group_id"])
            else:
                failed += 1
                attempts = int(doc.get("ai_attempts") or 0) + 1
                db["news"].update_one({"_id": doc["_id"]}, {"$set": {"ai_attempts": attempts, "ai_status": "failed" if attempts >= 3 else "pending"}})
                _log_error(db, doc.get("source") or {}, None, "ai", f"{exc.__class__.__name__}: {exc}" if exc else "no result", doc.get("title"))
    for gid in groups:
        cluster.recompute_story(db, gid)
    if done:
        news_cache.cache.clear()
    return {"enriched": done, "failed": failed}


# ------------------------------------------------------------------------------------ lease
def acquire_lease(db: Database, name: str, ttl_seconds: int) -> bool:
    """Cross-process lock so two server workers never run the same cycle."""
    now = utcnow()
    owner = f"{socket.gethostname()}:{os.getpid()}"
    try:
        db["news_locks"].update_one(
            {"_id": name, "$or": [{"expires_at": {"$lt": now}}, {"owner": owner}]},
            {"$set": {"owner": owner, "expires_at": now + timedelta(seconds=ttl_seconds), "acquired_at": now}},
            upsert=True,
        )
        return True
    except DuplicateKeyError:
        return False


def release_lease(db: Database, name: str) -> None:
    db["news_locks"].delete_one({"_id": name, "owner": f"{socket.gethostname()}:{os.getpid()}"})


# ------------------------------------------------------------------------------------ cycle
def cleanup(db: Database, settings: Settings | None = None, *, force: bool = False) -> dict:
    """Delete articles older than the retention window (at most every 12 hours)."""
    settings = settings or get_settings()
    now = utcnow()
    state = db["news_locks"].find_one({"_id": "cleanup"}) or {}
    last = state.get("last_at")
    if not force and last and now - last.replace(tzinfo=last.tzinfo or timezone.utc) < timedelta(hours=12):
        return {"skipped": True}
    cutoff = now - timedelta(days=settings.retention_days)
    a = db["news"].delete_many({"published_at": {"$lt": cutoff}}).deleted_count
    s = db["stories"].delete_many({"last_activity_at": {"$lt": cutoff}}).deleted_count
    keep = now - timedelta(days=14)
    db["news_runs"].delete_many({"started_at": {"$lt": keep}})
    db["news_errors"].delete_many({"created_at": {"$lt": keep}})
    db["news_locks"].update_one({"_id": "cleanup"}, {"$set": {"last_at": now}}, upsert=True)
    return {"articles": a, "stories": s}


def run_due_sources(db: Database, settings: Settings | None = None, *, only: list[str] | None = None, client=None,
                    max_workers: int = 4, with_ai: bool = True) -> dict:
    """One worker cycle: poll due sources, enrich, rescore, clean up. Returns a summary."""
    settings = settings or get_settings()
    if not acquire_lease(db, "cycle", ttl_seconds=20 * 60):
        return {"skipped": "another worker holds the lease"}
    try:
        now = utcnow()
        q: dict[str, Any] = {"enabled": True}
        if only:
            q = {"_id": {"$in": only}}
        sources = [s for s in db["news_sources"].find(q) if only or is_due(s, now)]
        index = classify.load_index(db, force=True)

        # One thread per host: hosts run in parallel, feeds on the same host are fetched politely in turn.
        by_host: dict[str, list[dict]] = {}
        for s in sources:
            by_host.setdefault(urlparse(s.get("url") or "").netloc or s["_id"], []).append(s)

        def run_host(group: list[dict]) -> list[dict]:
            return [run_source(db, s, settings=settings, client=client, index=index) for s in group]

        results: list[dict] = []
        if by_host:
            with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(by_host)))) as pool:
                for r in pool.map(run_host, by_host.values()):
                    results.extend(r)
        enrich = enrich_pending(db, settings=settings, index=index) if with_ai else {"skipped": "disabled"}
        stored = sum(r["counts"]["created"] + r["counts"]["clustered"] for r in results)
        merged = cluster.recluster(db, hours=max(24, min(96, settings.cluster_window_hours))) if stored else {"merged_groups": 0}
        rescored = cluster.rescore_recent(db)
        clean = cleanup(db, settings)
        news_cache.cache.clear()
        return {"sources": len(results), "results": results, "enrichment": enrich, "recluster": merged, "rescored": rescored, "cleanup": clean}
    finally:
        release_lease(db, "cycle")
