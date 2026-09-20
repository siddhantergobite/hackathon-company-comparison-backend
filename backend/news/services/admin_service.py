"""Admin operations: source management, categories, ingestion health, manual runs."""
from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from pymongo.database import Database

from backend.common.errors import ApiError
from backend.news import cache as news_cache
from backend.news.pipeline import enrich_pending, is_due, next_due, run_source
from backend.news.processing import classify
from backend.news.sources import source_id
from backend.news.taxonomy import slugify


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def validate_feed_url(url: str | None, *, allow_private: bool = False) -> str:
    """http(s) only, and never a private/loopback/link-local host (the server will fetch this URL)."""
    u = (url or "").strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ApiError(400, "Feed URL must be a valid http(s) URL")
    if allow_private:
        return u
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ApiError(400, f"Cannot resolve host '{p.hostname}'") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ApiError(400, "Feed URL points to a private or internal address, which is not allowed")
    return u


# ---------------------------------------------------------------------------------- sources
def health(source: dict, now: datetime | None = None) -> str:
    now = now or utcnow()
    if not source.get("enabled", True):
        return "disabled"
    if not source.get("last_fetch_at"):
        return "never"
    if (source.get("consecutive_failures") or 0) > 0:
        return "failed"
    ok = source.get("last_success_at")
    if ok:
        ok = ok if ok.tzinfo else ok.replace(tzinfo=timezone.utc)
        if now - ok > timedelta(minutes=max(60, 4 * int(source.get("poll_minutes") or 15))):
            return "stale"
    return "active"


def source_out(s: dict) -> dict:
    d = dict(s)
    d["id"] = d.pop("_id")
    d["health"] = health(s)
    nd = next_due(s)
    d["next_fetch_at"] = nd if s.get("enabled", True) else None
    d["due"] = is_due(s)
    return d


def list_sources(db: Database) -> list[dict]:
    return [source_out(s) for s in db["news_sources"].find({}).sort([("name", 1)])]


def _get_source(db: Database, sid: str) -> dict:
    s = db["news_sources"].find_one({"_id": sid})
    if not s:
        raise ApiError(404, "Source not found")
    return s


def _check_type_requirements(doc: dict) -> None:
    if doc["type"] == "rss":
        doc["url"] = validate_feed_url(doc.get("url"))
    elif doc["type"] == "newsapi":
        cfg = doc.get("config") or {}
        if not any(cfg.get(k) for k in ("sources", "q", "country", "category")):
            raise ApiError(400, "NewsAPI sources need config with at least one of: sources, q, country, category")


def create_source(db: Database, payload: dict) -> dict:
    sid = source_id(payload["name"])
    if not sid:
        raise ApiError(400, "Source name must contain letters or numbers")
    if db["news_sources"].find_one({"_id": sid}):
        raise ApiError(409, f"A source named '{payload['name']}' already exists")
    cat = (payload.get("category") or "").strip() or None
    if cat and not classify.load_index(db).resolve(cat):
        raise ApiError(400, f"Unknown category '{cat}'")
    now = utcnow()
    doc = {
        "_id": sid, **payload, "category": cat, "created_at": now, "updated_at": now, "last_fetch_at": None, "last_success_at": None,
        "last_error": None, "last_error_at": None, "consecutive_failures": 0, "articles_total": 0, "etag": None, "last_modified": None, "seeded": False,
    }
    _check_type_requirements(doc)
    db["news_sources"].insert_one(doc)
    return source_out(doc)


def update_source(db: Database, sid: str, patch: dict) -> dict:
    src = _get_source(db, sid)
    changes = {k: v for k, v in patch.items() if v is not None or k in ("category", "homepage", "country")}
    if not changes:
        raise ApiError(400, "No fields to update")
    if "category" in changes and changes["category"]:
        if not classify.load_index(db).resolve(changes["category"]):
            raise ApiError(400, f"Unknown category '{changes['category']}'")
    merged = {**src, **changes}
    if "url" in changes or "config" in changes:
        _check_type_requirements(merged)
    if "url" in changes:   # a different feed: forget the cached validators
        changes.update({"etag": None, "last_modified": None})
    changes["updated_at"] = utcnow()
    db["news_sources"].update_one({"_id": sid}, {"$set": changes})
    return source_out(_get_source(db, sid))


def set_enabled(db: Database, sid: str, enabled: bool) -> dict:
    _get_source(db, sid)
    upd: dict[str, Any] = {"enabled": enabled, "updated_at": utcnow()}
    if enabled:   # re-enabling should fetch soon and clear any failure back-off
        upd["consecutive_failures"] = 0
        upd["last_fetch_at"] = None
    db["news_sources"].update_one({"_id": sid}, {"$set": upd})
    return source_out(_get_source(db, sid))


def delete_source(db: Database, sid: str) -> None:
    _get_source(db, sid)
    db["news_sources"].delete_one({"_id": sid})   # articles already collected are kept


def fetch_now(db: Database, sid: str, *, settings=None, client=None) -> dict:
    src = _get_source(db, sid)
    res = run_source(db, src, settings=settings, client=client)
    return {**res, "source": source_out(_get_source(db, sid))}


def enrich_now(db: Database, limit: int, *, settings=None) -> dict:
    return enrich_pending(db, limit=limit, settings=settings)


def recluster_now(db: Database, hours: int) -> dict:
    from backend.news.processing.cluster import recluster

    out = recluster(db, hours=hours)
    news_cache.cache.clear()
    return out


# ----------------------------------------------------------------------------- categories
def _cat_out(c: dict) -> dict:
    d = dict(c)
    d.pop("_id", None)
    return d


def list_categories(db: Database) -> list[dict]:
    return [_cat_out(c) for c in db["news_categories"].find({}).sort([("order", 1), ("name", 1)])]


def create_category(db: Database, payload: dict) -> dict:
    slug = slugify(payload["name"])
    if not slug or slug in ("all", "breaking"):
        raise ApiError(400, "That category name is reserved or invalid")
    if db["news_categories"].find_one({"slug": slug}):
        raise ApiError(409, f"Category '{payload['name']}' already exists")
    kws = sorted({k.strip().lower() for k in payload.get("keywords") or [] if k.strip()})
    doc = {"slug": slug, "name": payload["name"].strip(), "icon": payload.get("icon"), "order": payload.get("order", 500), "keywords": kws,
           "enabled": payload.get("enabled", True), "virtual": False, "created_at": utcnow()}
    db["news_categories"].insert_one(doc)
    classify.invalidate_cache()
    news_cache.cache.clear()
    return _cat_out(doc)


def update_category(db: Database, slug: str, patch: dict) -> dict:
    cat = db["news_categories"].find_one({"slug": slug})
    if not cat:
        raise ApiError(404, "Category not found")
    changes = {k: v for k, v in patch.items() if v is not None}
    if "keywords" in changes:
        changes["keywords"] = sorted({k.strip().lower() for k in changes["keywords"] if k.strip()})
    if not changes:
        raise ApiError(400, "No fields to update")
    db["news_categories"].update_one({"slug": slug}, {"$set": changes})
    classify.invalidate_cache()
    news_cache.cache.clear()
    return _cat_out(db["news_categories"].find_one({"slug": slug}))


# ---------------------------------------------------------------------------- health / logs
def list_errors(db: Database, limit: int = 100, source_id_: str | None = None) -> list[dict]:
    q = {"source_id": source_id_} if source_id_ else {}
    out = []
    for e in db["news_errors"].find(q).sort([("created_at", -1)]).limit(limit):
        d = dict(e)
        d["id"] = str(d.pop("_id"))
        d["run_id"] = str(d["run_id"]) if d.get("run_id") else None
        out.append(d)
    return out


def list_runs(db: Database, limit: int = 40, source_id_: str | None = None) -> list[dict]:
    q = {"source_id": source_id_} if source_id_ else {}
    out = []
    for r in db["news_runs"].find(q).sort([("started_at", -1)]).limit(limit):
        d = dict(r)
        d["id"] = str(d.pop("_id"))
        out.append(d)
    return out


def stats(db: Database) -> dict:
    now = utcnow()
    srcs = list(db["news_sources"].find({}, {"enabled": 1, "last_fetch_at": 1, "last_success_at": 1, "consecutive_failures": 1, "poll_minutes": 1}))
    by_health: dict[str, int] = {}
    for s in srcs:
        h = health(s, now)
        by_health[h] = by_health.get(h, 0) + 1
    return {
        "articles": db["news"].estimated_document_count(),
        "stories": db["stories"].estimated_document_count(),
        "articles_24h": db["news"].count_documents({"collected_at": {"$gte": now - timedelta(hours=24)}}),
        "multi_source_stories": db["stories"].count_documents({"source_count": {"$gte": 2}}),
        "ai_enriched": db["news"].count_documents({"ai_status": "done"}),
        "ai_pending": db["news"].count_documents({"ai_status": "pending"}),
        "sources": len(srcs),
        "sources_by_health": by_health,
        "errors_24h": db["news_errors"].count_documents({"created_at": {"$gte": now - timedelta(hours=24)}}),
    }
