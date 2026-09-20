"""Read side of the News tool: feeds, search, stories, trending, facets."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import DESCENDING
from pymongo.database import Database

from backend.common.errors import ApiError
from backend.news.cache import cache
from backend.news.config import get_settings
from backend.news.taxonomy import VIRTUAL_CATEGORIES, WHATS_HAPPENING_GROUPS

SORTS = {"latest", "trending", "importance"}
BREAKING_WINDOW_HOURS = 12


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def doc_to_api(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = d.pop("_id")
    return d


def parse_dt(value: str | None, name: str, *, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # An unencoded "+00:00" offset arrives as " 00:00" (the + becomes a space in a query string)
    value = re.sub(r"(T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) (\d{2}:\d{2})$", r"\1+\2", value)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, f"Invalid {name}: expected an ISO date or datetime") from None
    if len(value) <= 10:   # a bare date
        dt = dt.replace(hour=23, minute=59, second=59) if end_of_day else dt
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class ListParams:
    page: int = 1
    limit: int = 20
    category: str | None = None
    source: str | None = None
    topic: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    sort: str = "latest"
    group: bool = True          # one card per story (default) vs every individual article
    q: str | None = None


def _ci(value: str) -> dict:
    return {"$regex": f"^{re.escape(value.strip())}$", "$options": "i"}


def _category_slugs(db: Database) -> dict[str, dict]:
    return cache.get_or_set(("category-map",), get_settings().cache_ttl_long,
                            lambda: {c["slug"]: c for c in db["news_categories"].find({"enabled": True}, {"_id": 0})})


def resolve_category(db: Database, value: str) -> str:
    v = value.strip().lower()
    if v in ("all", "breaking"):
        return v
    cats = _category_slugs(db)
    if v in cats:
        return v
    for slug, c in cats.items():
        if c["name"].lower() == v:
            return slug
    raise ApiError(404, f"Unknown category '{value}'")


def build_query(db: Database, p: ListParams) -> dict:
    clauses: list[dict] = [{"status": "published"}]
    grouped = p.group and not p.source
    if grouped:
        clauses.append({"is_lead": True})
    time_field = "last_activity_at" if grouped else "published_at"

    if p.category:
        cat = resolve_category(db, p.category)
        if cat == "breaking":
            clauses.append({"is_breaking": True})
            clauses.append({time_field: {"$gte": utcnow() - timedelta(hours=BREAKING_WINDOW_HOURS)}})
        elif cat != "all":
            clauses.append({"categories": cat})
    if p.source:
        clauses.append({"source.name": _ci(p.source)})
    if p.topic:
        clauses.append({"topics": _ci(p.topic)})
    lo, hi = parse_dt(p.date_from, "from"), parse_dt(p.date_to, "to", end_of_day=True)
    if lo and hi and hi < lo:
        raise ApiError(400, "'to' must not be before 'from'")
    if lo:
        clauses.append({time_field: {"$gte": lo}})
    if hi:
        clauses.append({time_field: {"$lte": hi}})
    return {"$and": clauses}


def _sort_spec(p: ListParams, grouped: bool) -> list[tuple[str, int]]:
    if p.sort not in SORTS:
        raise ApiError(400, f"Invalid sort '{p.sort}'. Use one of: {', '.join(sorted(SORTS))}")
    if p.sort == "trending":
        return [("trending_score", DESCENDING), ("_id", DESCENDING)]
    if p.sort == "importance":
        return [("importance_score", DESCENDING), ("published_at", DESCENDING), ("_id", DESCENDING)]
    return [("last_activity_at" if grouped else "published_at", DESCENDING), ("_id", DESCENDING)]


def _page(total: int, page: int, limit: int, docs: list[dict]) -> dict:
    return {"page": page, "limit": limit, "total": total, "total_pages": math.ceil(total / limit) if limit else 0,
            "has_more": page * limit < total, "articles": [doc_to_api(d) for d in docs]}


_LIST_EXCLUDE = {"title_tokens": 0, "entities_detail": 0, "feed_tags": 0, "key_points": 0, "content": 0, "related_articles": 0}


def list_articles(db: Database, p: ListParams) -> dict:
    if p.q and p.q.strip():
        return search_articles(db, p)
    q = build_query(db, p)
    grouped = p.group and not p.source
    total = db["news"].count_documents(q)
    if grouped and p.sort == "latest" and not p.source:
        return _page(total, p.page, p.limit, _diverse_latest(db, q, p))
    cursor = db["news"].find(q, _LIST_EXCLUDE).sort(_sort_spec(p, grouped)).skip((p.page - 1) * p.limit).limit(p.limit)
    return _page(total, p.page, p.limit, list(cursor))


# A publisher that releases dozens of items at once (a sports desk, a wire) would otherwise fill the
# whole "Latest" page. Each source's n-th newest story is treated as this many minutes older, so
# sources interleave while the feed still reads newest-first. Explicit source filters are unaffected.
DIVERSITY_PENALTY_MINUTES = 20


def _diverse_latest(db: Database, query: dict, p: ListParams) -> list[dict]:
    penalty_ms = DIVERSITY_PENALTY_MINUTES * 60 * 1000
    pipeline = [
        {"$match": query},
        {"$setWindowFields": {"partitionBy": "$source.name", "sortBy": {"last_activity_at": -1},
                              "output": {"_rank": {"$documentNumber": {}}}}},
        {"$addFields": {"_eff": {"$subtract": ["$last_activity_at", {"$multiply": [{"$subtract": ["$_rank", 1]}, penalty_ms]}]}}},
        {"$sort": {"_eff": -1, "_id": -1}},
        {"$skip": (p.page - 1) * p.limit},
        {"$limit": p.limit},
        {"$project": {**_LIST_EXCLUDE, "_rank": 0, "_eff": 0}},
    ]
    return list(db["news"].aggregate(pipeline))


def search_articles(db: Database, p: ListParams) -> dict:
    """Full-text search over title, summary, topics, entities, source and category; one hit per story."""
    text = (p.q or "").strip()
    if len(text) < 2:
        raise ApiError(400, "Search text must be at least 2 characters")
    base = build_query(db, ListParams(**{**p.__dict__, "group": False, "q": None}))
    match: dict[str, Any] = {"$and": [{"$text": {"$search": text}}, *base["$and"]]}
    pipeline = [
        {"$match": match},
        {"$addFields": {"_score": {"$meta": "textScore"}}},
        {"$sort": {"_score": -1, "published_at": -1}},
        {"$group": {"_id": "$duplicate_group_id", "doc": {"$first": "$$ROOT"}, "best": {"$max": "$_score"}}},
        {"$sort": {"best": -1, "doc.published_at": -1}},
        {"$facet": {"count": [{"$count": "n"}], "rows": [{"$skip": (p.page - 1) * p.limit}, {"$limit": p.limit}]}},
    ]
    res = next(db["news"].aggregate(pipeline), {"count": [], "rows": []})
    total = res["count"][0]["n"] if res["count"] else 0
    docs = []
    for r in res["rows"]:
        d = r["doc"]
        for k in list(_LIST_EXCLUDE) + ["_score"]:
            d.pop(k, None)
        docs.append(d)
    if not docs and total == 0 and len(text) >= 3 and " " not in text:
        return _prefix_fallback(db, p, text, base)
    return _page(total, p.page, p.limit, docs)


def _prefix_fallback(db: Database, p: ListParams, text: str, base: dict) -> dict:
    """Text search matches whole words; this catches partial input like "nvid" or "ind econ"."""
    rx = {"$regex": r"(?<![A-Za-z0-9])" + re.escape(text), "$options": "i"}
    q = {"$and": [*base["$and"], {"$or": [{"title": rx}, {"entities": rx}, {"topics": rx}, {"source.name": rx}]}]}
    total = db["news"].count_documents(q)
    docs = list(db["news"].find(q, _LIST_EXCLUDE).sort([("published_at", DESCENDING)]).skip((p.page - 1) * p.limit).limit(p.limit))
    return _page(total, p.page, p.limit, docs)


# --------------------------------------------------------------------------------- details
def get_article(db: Database, article_id: str) -> dict | None:
    doc = db["news"].find_one({"_id": article_id, "status": "published"}, {"title_tokens": 0, "feed_tags": 0})
    return doc_to_api(doc) if doc else None


def get_story(db: Database, story_id: str) -> dict | None:
    story = db["stories"].find_one({"_id": story_id})
    if not story:
        return None
    members = list(db["news"].find({"duplicate_group_id": story_id, "status": "published"}, _LIST_EXCLUDE).sort([("published_at", DESCENDING)]))
    lead = db["news"].find_one({"_id": story.get("lead_article_id")}, {"title_tokens": 0, "feed_tags": 0})
    return {"story": doc_to_api(story), "lead": doc_to_api(lead) if lead else None, "articles": [doc_to_api(m) for m in members]}


def related_articles(db: Database, article_id: str, limit: int = 8) -> list[dict]:
    """Other coverage of the same story first; then topically similar recent articles."""
    art = db["news"].find_one({"_id": article_id, "status": "published"}, {"duplicate_group_id": 1, "topics": 1, "entities": 1, "published_at": 1, "category": 1})
    if not art:
        raise ApiError(404, "Article not found")
    same = list(db["news"].find({"duplicate_group_id": art.get("duplicate_group_id"), "_id": {"$ne": article_id}, "status": "published"}, _LIST_EXCLUDE).sort([("published_at", DESCENDING)]).limit(limit))
    out = same
    if len(out) < limit:
        seen = {d["_id"] for d in out} | {article_id}
        anchors = [*(art.get("entities") or [])[:4], *(art.get("topics") or [])[:3]]
        if anchors:
            since = (art.get("published_at") or utcnow()) - timedelta(days=5)
            more = db["news"].find(
                {"status": "published", "is_lead": True, "_id": {"$nin": list(seen)}, "duplicate_group_id": {"$ne": art.get("duplicate_group_id")},
                 "published_at": {"$gte": since}, "$or": [{"entities": {"$in": anchors}}, {"topics": {"$in": anchors}}]},
                _LIST_EXCLUDE,
            ).sort([("importance_score", DESCENDING)]).limit(limit - len(out))
            out = out + list(more)
    return [doc_to_api(d) for d in out]


# ---------------------------------------------------------------------- top / trending / now
def _leads_for_stories(db: Database, stories: list[dict]) -> list[dict]:
    ids = [s["lead_article_id"] for s in stories if s.get("lead_article_id")]
    by_id = {d["_id"]: d for d in db["news"].find({"_id": {"$in": ids}, "status": "published"}, _LIST_EXCLUDE)}
    return [doc_to_api(by_id[i]) for i in ids if i in by_id]


def _recent_stories(db: Database, *, hours: int, sort_field: str, limit: int, categories: list[str] | None = None) -> list[dict]:
    q: dict[str, Any] = {"last_activity_at": {"$gte": utcnow() - timedelta(hours=hours)}}
    if categories:
        q["category"] = {"$in": categories}
    return list(db["stories"].find(q).sort([(sort_field, DESCENDING)]).limit(limit))


def top_stories(db: Database, limit: int = 5) -> list[dict]:
    """Most important stories of the last 24h, with an illustrated one first (it becomes the hero)."""
    stories = _recent_stories(db, hours=24, sort_field="trending_score", limit=max(limit * 3, 12))
    stories.sort(key=lambda s: (-(s.get("trending_score") or 0)))
    hero = next((s for s in stories[:8] if s.get("image_url")), None)
    if hero:
        stories.remove(hero)
        stories.insert(0, hero)
    return _leads_for_stories(db, stories[:limit])


def trending(db: Database, limit: int = 10) -> list[dict]:
    return _leads_for_stories(db, _recent_stories(db, hours=48, sort_field="trending_score", limit=limit))


def whats_happening(db: Database, per_group: int = 3) -> list[dict]:
    groups = []
    for g in WHATS_HAPPENING_GROUPS:
        candidates = _recent_stories(db, hours=36, sort_field="trending_score", limit=per_group * 5, categories=g["categories"])
        # Stories covered by several outlets are the real "events": rank them first, then by trend.
        candidates.sort(key=lambda s: ((s.get("source_count") or 1) < 2, -(s.get("trending_score") or 0)))
        arts = _leads_for_stories(db, candidates[:per_group])
        if arts:
            groups.append({"key": g["key"], "label": g["label"], "icon": g["icon"], "articles": arts})
    return groups


# -------------------------------------------------------------------------------- facets
def list_categories(db: Database) -> list[dict]:
    since = utcnow() - timedelta(hours=48)
    counts = {r["_id"]: r["n"] for r in db["news"].aggregate([
        {"$match": {"status": "published", "is_lead": True, "last_activity_at": {"$gte": since}}},
        {"$unwind": "$categories"}, {"$group": {"_id": "$categories", "n": {"$sum": 1}}}])}
    breaking = db["news"].count_documents({"status": "published", "is_lead": True, "is_breaking": True, "last_activity_at": {"$gte": utcnow() - timedelta(hours=BREAKING_WINDOW_HOURS)}})
    total = db["news"].count_documents({"status": "published", "is_lead": True, "last_activity_at": {"$gte": since}})
    out = [{**c, "count": total if c["slug"] == "all" else breaking} for c in VIRTUAL_CATEGORIES]
    rows = sorted(db["news_categories"].find({"enabled": True}, {"_id": 0}), key=lambda c: (c.get("order", 500), c["name"]))
    out += [{"slug": c["slug"], "name": c["name"], "icon": c.get("icon"), "order": c.get("order", 500), "virtual": False, "count": counts.get(c["slug"], 0)} for c in rows]
    return out


def list_sources(db: Database) -> list[dict]:
    since = utcnow() - timedelta(hours=48)
    counts = {r["_id"]: r["n"] for r in db["news"].aggregate([
        {"$match": {"status": "published", "published_at": {"$gte": since}}}, {"$group": {"_id": "$source.name", "n": {"$sum": 1}}}])}
    homepages = {s["name"]: s.get("homepage") for s in db["news_sources"].find({}, {"name": 1, "homepage": 1})}
    rows = [{"name": n, "url": homepages.get(n), "count": c} for n, c in counts.items() if n]
    rows.sort(key=lambda r: (-r["count"], r["name"].lower()))
    return rows


def list_topics(db: Database, limit: int = 24) -> list[dict]:
    since = utcnow() - timedelta(hours=72)
    rows = db["news"].aggregate([
        {"$match": {"status": "published", "is_lead": True, "last_activity_at": {"$gte": since}}},
        {"$unwind": "$topics"}, {"$group": {"_id": "$topics", "n": {"$sum": 1}}}, {"$sort": {"n": -1, "_id": 1}}, {"$limit": limit}])
    return [{"name": r["_id"], "count": r["n"]} for r in rows]
