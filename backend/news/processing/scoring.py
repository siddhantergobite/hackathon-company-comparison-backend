"""Importance and trending scores.

importance (0-100): how much a story matters, independent of time
    source editorial weight + category weight + how many outlets cover it (+ breaking bonus)
trending: importance amplified by coverage, decayed by age (half-life ~8h), boosted when fresh
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from backend.news.taxonomy import CATEGORY_WEIGHT

TREND_HALF_LIFE_HOURS = 8.0


def _age_hours(when: datetime | None, now: datetime) -> float:
    if when is None:
        return 999.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (now - when).total_seconds() / 3600.0)


def importance(*, source_priority: int = 3, category: str | None = None, source_count: int = 1, breaking: bool = False) -> float:
    base = max(1, min(5, source_priority)) * 7                       # 7-35
    cat = CATEGORY_WEIGHT.get(category or "", 5)                      # 3-12
    cover = min(35.0, 14.0 * math.log(max(1, source_count)) + (source_count > 1) * 6)  # 0-35
    bonus = 15.0 if breaking else 0.0
    return round(max(0.0, min(100.0, base + cat + cover + bonus)), 2)


def trending(*, importance_score: float, source_count: int, last_activity: datetime | None, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    age = _age_hours(last_activity, now)
    decay = math.exp(-math.log(2) * age / TREND_HALF_LIFE_HOURS)
    coverage = 1.0 + 1.2 * math.log(max(1, source_count))
    fresh = 1.25 if age <= 1 else 1.0
    return round(coverage * (0.4 + importance_score / 100.0) * 100.0 * decay * fresh, 2)
