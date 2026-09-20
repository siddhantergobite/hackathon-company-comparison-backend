"""Category, topic and breaking-news detection (rule-based, DB-extensible).

Categories come from the `news_categories` collection, so an admin can add a category with its
keywords and it takes part in classification immediately (after the short cache expires).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from pymongo.database import Database

from backend.news.taxonomy import DEFAULT_CATEGORIES, TOPICS, slugify

_BREAKING = re.compile(r"^\s*(breaking( news)?|just in|developing|urgent|news alert|live)\b\s*[:\-–—|]?|\b(breaking news)\b", re.I)


def _kw_regex(words: list[str]) -> re.Pattern | None:
    ws = sorted({w.strip().lower() for w in words if w and w.strip()}, key=len, reverse=True)
    if not ws:
        return None
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in ws) + r")(?![\w])", re.I)


@dataclass
class CategoryIndex:
    categories: list[dict] = field(default_factory=list)
    _rx: dict[str, re.Pattern | None] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.categories = [c for c in self.categories if c.get("enabled", True) and not c.get("virtual")]
        self._rx = {c["slug"]: _kw_regex(c.get("keywords") or []) for c in self.categories}
        self.by_slug = {c["slug"]: c for c in self.categories}
        self.by_name = {c["name"].lower(): c for c in self.categories}

    def resolve(self, value: str | None) -> dict | None:
        """Map a slug or display name (case-insensitive) to a category document."""
        if not value:
            return None
        v = value.strip().lower()
        return self.by_slug.get(v) or self.by_slug.get(slugify(v)) or self.by_name.get(v)

    def scores(self, title: str | None, description: str | None) -> dict[str, float]:
        out: dict[str, float] = {}
        for slug, rx in self._rx.items():
            if rx is None:
                continue
            t = len({m.lower() for m in rx.findall(title or "")})
            d = len({m.lower() for m in rx.findall(description or "")})
            s = 3.0 * t + 1.0 * min(d, 3)
            if s:
                out[slug] = s
        return out


_cache: tuple[float, CategoryIndex] | None = None
_CACHE_TTL = 60.0


def default_index() -> CategoryIndex:
    return CategoryIndex([dict(c) for c in DEFAULT_CATEGORIES])


def load_index(db: Database | None, *, force: bool = False) -> CategoryIndex:
    global _cache
    if db is None:
        return default_index()
    if not force and _cache and time.monotonic() - _cache[0] < _CACHE_TTL:
        return _cache[1]
    docs = list(db["news_categories"].find({}, {"_id": 0}))
    idx = CategoryIndex(docs) if docs else default_index()
    _cache = (time.monotonic(), idx)
    return idx


def invalidate_cache() -> None:
    global _cache
    _cache = None


def classify(index: CategoryIndex, title: str | None, description: str | None, *, hint: str | None = None, feed_tags=()) -> tuple[str, list[str]]:
    """Return (primary_slug, [all slugs]). The source's default category nudges ties."""
    scores = index.scores(title, description)
    hint_cat = index.resolve(hint)
    if hint_cat:
        scores[hint_cat["slug"]] = scores.get(hint_cat["slug"], 0) + 2.5
    for tag in feed_tags or []:
        c = index.resolve(tag)
        if c:
            scores[c["slug"]] = scores.get(c["slug"], 0) + 2.0
    if not scores:
        fallback = hint_cat["slug"] if hint_cat else ("world" if "world" in index.by_slug else next(iter(index.by_slug), "world"))
        return fallback, [fallback]
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[0][1]
    primary = ranked[0][0]
    extra = [s for s, v in ranked[1:] if v >= max(3.0, 0.5 * top)][:2]
    return primary, [primary, *extra]


_TOPIC_RX = {name: _kw_regex(words) for name, words in TOPICS.items()}


def detect_topics(title: str | None, description: str | None, limit: int = 6) -> list[str]:
    scored: list[tuple[float, str]] = []
    for name, rx in _TOPIC_RX.items():
        if rx is None:
            continue
        t = len({m.lower() for m in rx.findall(title or "")})
        d = len({m.lower() for m in rx.findall(description or "")})
        s = 3.0 * t + 1.0 * d
        if t >= 1 or d >= 2 or (d == 1 and any(" " in m for m in rx.findall(description or ""))):
            scored.append((s, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _, n in scored[:limit]]


def is_breaking_title(title: str | None) -> bool:
    return bool(title and _BREAKING.search(title))
