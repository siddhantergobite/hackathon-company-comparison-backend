"""Duplicate detection + story clustering.

The same event is reported by many outlets under different headlines. Every article belongs to a
*story* (`duplicate_group_id`); a story with several articles is shown once, with
"Covered by N sources", and each source article stays reachable.

Signals: canonical URL (handled by the article id), normalised-title similarity with synonym
folding ("announces" = "launches"), shared named entities, topic overlap and publication-time
proximity. Semantic/embedding similarity is an intentional extension point (`semantic_score`);
without an embeddings deployment the rule-based signals are used.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from pymongo.database import Database

from backend.news.processing import scoring

JOIN_SCORE = 0.66        # combined score needed to join an existing story
NEAR_IDENTICAL = 0.85    # titles this similar join on their own (within the time window)
STRONG_SHARED_TOKENS = 4  # with 2 shared entities: same event despite different wording
MAX_STORY_SIZE = 40      # never let chaining glue unrelated stories into one mega-story

_STOP = set("""a an the of and or for in on at by with to from as is are was were be been it its this that these those
into over after before amid about than then not no nor but so if we you they he she his her our their who whom which what when
where why how will would could should may might can has have had do does did up down out off per via vs new says say said
report reports reported reportedly update updates latest news live video watch photos photo pictures exclusive analysis
opinion week year years day days first second third one two three four five more most amid finally just now today yesterday
""".split())
# verbs that different outlets use for the same act: fold them together, then drop them
_LAUNCH = set("announce announces announced announcing launch launches launched launching introduce introduces introduced unveil unveils unveiled reveal reveals revealed debut debuts debuted release releases released rolls roll rolled unveiling".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]")


def _stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def distinctive_tokens(title: str | None) -> list[str]:
    out: list[str] = []
    for raw in _TOKEN.findall((title or "").lower().replace("’", "'").replace("'s", "")):
        t = raw.strip(".-")
        if not t or t in _STOP or t in _LAUNCH:
            continue
        t = _stem(t)
        if t and t not in out:
            out.append(t)
    return out


def normalized_title(title: str | None) -> str:
    return " ".join(distinctive_tokens(title))


def _numbers(tokens: set[str]) -> set[str]:
    return {t for t in tokens if any(ch.isdigit() for ch in t) and not re.fullmatch(r"20\d\d", t)}


def title_similarity(a_tokens: list[str], b_tokens: list[str]) -> float:
    A, B = set(a_tokens), set(b_tokens)
    if not A or not B:
        return 0.0
    inter = A & B
    jacc = len(inter) / len(A | B)
    contain = len(inter) / min(len(A), len(B)) if min(len(A), len(B)) >= 3 else 0.0
    seq = SequenceMatcher(None, " ".join(a_tokens), " ".join(b_tokens)).ratio()
    sim = max(jacc, 0.9 * contain, 0.7 * seq)
    na, nb = _numbers(A), _numbers(B)
    if na and nb and not (na & nb):   # "rates up 25bp" vs "rates up 50bp": different events
        sim = min(sim, 0.4)
    return sim


def _jacc(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def semantic_score(a: dict, b: dict) -> float | None:
    """Hook for embedding similarity. Returns None when no embeddings are configured."""
    return None


def score_pair(a: dict, b: dict) -> tuple[float, dict[str, Any]]:
    """Similarity of two articles in [0, 1] (`a`/`b` need title_tokens, entities, topics, published_at)."""
    at, bt = a.get("title_tokens") or distinctive_tokens(a.get("title")), b.get("title_tokens") or distinctive_tokens(b.get("title"))
    t = title_similarity(at, bt)
    ea = {e.lower() for e in a.get("entities") or []}
    eb = {e.lower() for e in b.get("entities") or []}
    ent = _jacc(ea, eb)
    topic = _jacc({x.lower() for x in a.get("topics") or []}, {x.lower() for x in b.get("topics") or []})
    pa, pb = a.get("published_at"), b.get("published_at")
    hours = abs((pa - pb).total_seconds()) / 3600.0 if isinstance(pa, datetime) and isinstance(pb, datetime) else 48.0
    prox = math.exp(-hours / 30.0)

    shared = set(at) & set(bt)
    detail = {"title": round(t, 3), "entities": round(ent, 3), "topics": round(topic, 3), "time": round(prox, 3), "shared_tokens": sorted(shared)}
    # Never join on a single generic shared word
    if len(shared) < 2 and not (shared and (ea & eb)):
        return 0.0, detail
    if ea and eb:
        base = 0.6 * t + 0.2 * ent + 0.1 * topic + 0.1 * prox
    else:
        # One side names no known entity: the entity signal is missing, not negative evidence.
        base = (0.6 * t + 0.1 * topic + 0.1 * prox) / 0.8
    sem = semantic_score(a, b)
    if sem is not None:
        base = 0.7 * base + 0.3 * sem
    # Outlets paraphrase headlines heavily. Four shared distinctive words AND two shared named
    # entities, close in time, is the same event even when the wording differs.
    if len(shared) >= STRONG_SHARED_TOKENS and len(ea & eb) >= 2 and prox >= 0.4:
        detail["strong_overlap"] = True
        base = max(base, JOIN_SCORE + 0.01)
    return round(base, 4), detail


def group_id_for(article_id: str) -> str:
    return "st_" + hashlib.sha1(article_id.encode()).hexdigest()[:12]


def find_story(db: Database, article: dict, *, window_hours: int = 72) -> tuple[str | None, dict | None, float]:
    """Best existing article this one duplicates: (group_id, matched article, score)."""
    tokens = article.get("title_tokens") or []
    pub = article.get("published_at")
    if not tokens or not isinstance(pub, datetime):
        return None, None, 0.0
    w = timedelta(hours=window_hours)
    cursor = db["news"].find(
        {
            "status": "published",
            "published_at": {"$gte": pub - w, "$lte": pub + w},
            "title_tokens": {"$in": tokens[:14]},
            "_id": {"$ne": article.get("_id")},
        },
        {"title": 1, "title_tokens": 1, "entities": 1, "topics": 1, "published_at": 1, "duplicate_group_id": 1},
    ).limit(400)
    best: dict | None = None
    best_score = 0.0
    for cand in cursor:
        s, detail = score_pair(article, cand)
        strong = detail["title"] >= NEAR_IDENTICAL and len(detail["shared_tokens"]) >= 2
        if (s >= JOIN_SCORE or strong) and s + (0.5 if strong else 0) > best_score:
            best, best_score = cand, s + (0.5 if strong else 0)
    if not best:
        return None, None, 0.0
    return best.get("duplicate_group_id") or group_id_for(best["_id"]), best, min(1.0, best_score)


def _lead_key(m: dict, priority_of: dict[str, int]) -> tuple:
    pri = priority_of.get((m.get("source") or {}).get("id") or "", 3)
    quality = (
        pri * 10
        + (5 if m.get("image_url") else 0)
        + (3 if m.get("ai_status") == "done" else 0)
        + min(len(m.get("description") or ""), 400) / 100.0
    )
    pub = m.get("published_at")
    return (quality, -(pub.timestamp() if isinstance(pub, datetime) else 0))


def recompute_story(db: Database, group_id: str, *, now: datetime | None = None) -> dict | None:
    """(Re)build the story: choose the lead article, coverage list, scores and breaking flag."""
    now = now or datetime.now(timezone.utc)
    news = db["news"]
    members = list(news.find({"duplicate_group_id": group_id, "status": "published"}))
    if not members:
        db["stories"].delete_one({"_id": group_id})
        return None

    src_ids = {(m.get("source") or {}).get("id") for m in members if (m.get("source") or {}).get("id")}
    priority_of = {s["_id"]: s.get("priority", 3) for s in db["news_sources"].find({"_id": {"$in": list(src_ids)}}, {"priority": 1})}
    lead = max(members, key=lambda m: _lead_key(m, priority_of))
    members.sort(key=lambda m: m.get("published_at") or now)
    sources: list[str] = []
    for m in members:
        n = (m.get("source") or {}).get("name")
        if n and n not in sources:
            sources.append(n)
    count = len(members)
    source_count = len(sources)
    first, last = members[0].get("published_at"), max((m.get("published_at") or now) for m in members)
    category = lead.get("category")
    categories = list(dict.fromkeys(c for m in [lead, *members] for c in (m.get("categories") or [])))[:4]
    breaking = any(m.get("is_breaking") for m in members) or (
        source_count >= 3 and isinstance(first, datetime) and (now - first) <= timedelta(minutes=90)
    )
    imp = scoring.importance(
        source_priority=max(priority_of.values(), default=3), category=category, source_count=source_count, breaking=breaking,
    )
    trend = scoring.trending(importance_score=imp, source_count=source_count, last_activity=last, now=now)
    coverage = {"count": count, "sources": sources}

    news.update_many({"duplicate_group_id": group_id}, {"$set": {"is_lead": False, "coverage": coverage, "importance_score": imp, "trending_score": trend, "is_breaking": breaking, "last_activity_at": last}})
    news.update_one({"_id": lead["_id"]}, {"$set": {"is_lead": True}})
    ids = [m["_id"] for m in members]
    from pymongo import UpdateOne

    news.bulk_write(
        [UpdateOne({"_id": m["_id"]}, {"$set": {"related_articles": [x for x in ids if x != m["_id"]][:10]}}) for m in members],
        ordered=False,
    )

    story = {
        "_id": group_id,
        "title": lead.get("title"),
        "summary": lead.get("summary") or lead.get("description"),
        "category": category,
        "categories": categories,
        "image_url": lead.get("image_url") or next((m.get("image_url") for m in members if m.get("image_url")), None),
        "topics": list(dict.fromkeys(t for m in [lead, *members] for t in (m.get("topics") or [])))[:8],
        "entities": list(dict.fromkeys(e for m in [lead, *members] for e in (m.get("entities") or [])))[:10],
        "article_count": count,
        "source_count": source_count,
        "sources": sources,
        "lead_article_id": lead["_id"],
        "first_published_at": first,
        "last_activity_at": last,
        "importance_score": imp,
        "trending_score": trend,
        "is_breaking": breaking,
        "updated_at": now,
    }
    db["stories"].replace_one({"_id": group_id}, story, upsert=True)
    return story


def rescore_recent(db: Database, *, hours: int = 96, now: datetime | None = None) -> int:
    """Re-apply time decay to recently active stories (called every cycle)."""
    from pymongo import UpdateMany

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    ops = []
    story_updates = []
    for s in db["stories"].find({"last_activity_at": {"$gte": cutoff}}, {"importance_score": 1, "source_count": 1, "last_activity_at": 1}):
        t = scoring.trending(importance_score=s.get("importance_score", 0), source_count=s.get("source_count", 1), last_activity=s.get("last_activity_at"), now=now)
        ops.append(UpdateMany({"duplicate_group_id": s["_id"]}, {"$set": {"trending_score": t}}))
        story_updates.append((s["_id"], t))
    if ops:
        db["news"].bulk_write(ops, ordered=False)
        from pymongo import UpdateOne

        db["stories"].bulk_write([UpdateOne({"_id": sid}, {"$set": {"trending_score": t}}) for sid, t in story_updates], ordered=False)
    return len(ops)


# ---------------------------------------------------------------------------- recluster
def recluster(db: Database, *, hours: int = 48, now: datetime | None = None) -> dict:
    """Merge fragmented stories among recent articles (union-find over pairwise similarity).

    Ingest-time clustering only sees what exists at that moment, so an event reported over several
    hours can end up as several stories. This pass unites them. Story ids stay stable: a merged
    story keeps the id of its largest existing group. Chaining is capped (MAX_STORY_SIZE).
    """
    from collections import Counter, defaultdict

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    docs = list(db["news"].find(
        {"status": "published", "published_at": {"$gte": since}},
        {"title": 1, "title_tokens": 1, "entities": 1, "topics": 1, "published_at": 1, "duplicate_group_id": 1},
    ))
    if len(docs) < 2:
        return {"articles": len(docs), "merged_groups": 0, "moved": 0}
    by_id = {d["_id"]: d for d in docs}
    parent = {i: i for i in by_id}
    size = {i: 1 for i in by_id}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if size[ra] + size[rb] > MAX_STORY_SIZE:
            return False
        parent[rb] = ra
        size[ra] += size[rb]
        return True

    first_of_group: dict[str, str] = {}
    for d in docs:                                           # what is already grouped stays grouped
        g = d.get("duplicate_group_id")
        if g in first_of_group:
            union(first_of_group[g], d["_id"])
        else:
            first_of_group[g] = d["_id"]

    postings: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        for tok in (d.get("title_tokens") or [])[:14]:
            postings[tok].append(d["_id"])
    pair_hits: Counter = Counter()
    for tok, ids in postings.items():
        if 2 <= len(ids) <= 60:                              # very common tokens carry no signal
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pair_hits[(ids[i], ids[j]) if ids[i] < ids[j] else (ids[j], ids[i])] += 1

    scored = []
    for (a, b), hits in pair_hits.items():
        if hits < 2 or find(a) == find(b):
            continue
        s, detail = score_pair(by_id[a], by_id[b])
        strong = detail["title"] >= NEAR_IDENTICAL and len(detail["shared_tokens"]) >= 2
        if s >= JOIN_SCORE or strong:
            scored.append((s + (0.5 if strong else 0), a, b))
    for _s, a, b in sorted(scored, reverse=True):            # strongest evidence first
        union(a, b)

    comps: dict[str, list[str]] = defaultdict(list)
    for i in by_id:
        comps[find(i)].append(i)
    changed_groups: set[str] = set()
    moved = merged = 0
    for members in comps.values():
        existing = Counter(by_id[m].get("duplicate_group_id") for m in members)
        if len(existing) <= 1:
            continue
        target = max(existing.items(), key=lambda kv: (kv[1], str(kv[0])))[0] or group_id_for(min(members))
        merged += len(existing) - 1
        changed_groups.add(target)
        for m in members:
            old = by_id[m].get("duplicate_group_id")
            if old != target:
                db["news"].update_one({"_id": m}, {"$set": {"duplicate_group_id": target}})
                moved += 1
                changed_groups.add(old)
    for g in changed_groups:
        if g:
            recompute_story(db, g, now=now)
    return {"articles": len(docs), "merged_groups": merged, "moved": moved}
