"""Duplicate detection across sources.

Signals: source event id (exact), normalised title, start date, city/venue, organizer.
Fuzzy matching uses difflib + token containment (no external dependency).

Confidence levels:
  exact    same (source, source_event_id)
  high     safe to auto-merge into the existing event
  possible looks related; keep both but flag for a human to review
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any, Iterable

from pymongo.collection import Collection

HIGH_THRESHOLD = 0.90
POSSIBLE_THRESHOLD = 0.75

_STOP = {"the", "a", "an", "of", "and", "for", "in", "at", "on", "by", "with", "to"}
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_ORG_NOISE = re.compile(r"\b(inc|llc|ltd|limited|gmbh|corp|corporation|co|company|pvt|private|the)\b", re.I)


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def normalize_title(title: str | None) -> str:
    s = _ascii((title or "").lower()).replace("&", " and ")
    s = _YEAR.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(t for t in s.split() if t not in _STOP)


def _tokens(norm: str) -> set[str]:
    return {t for t in norm.split() if t}


def _numbers(tokens: set[str]) -> set[str]:
    """Edition / session numbers ("Meetup 7", "Day 2", "12th"), ignoring years (already stripped)."""
    return {m.group(0) for tok in tokens if (m := re.match(r"\d+", tok))}


def _title_signals(a: str | None, b: str | None) -> tuple[float, float]:
    """(strict, loose) similarity. `loose` adds token containment ("AI Summit" inside "Global AI Summit")."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0, 0.0
    if na == nb:
        return 1.0, 1.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _tokens(na), _tokens(nb)
    jacc = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    strict = max(seq, jacc)
    na_nums, nb_nums = _numbers(ta), _numbers(tb)
    if na_nums and nb_nums and na_nums != nb_nums:
        return min(strict, 0.5), min(strict, 0.5)  # "Meetup #7" vs "Meetup #8": different events
    contain = len(ta & tb) / min(len(ta), len(tb)) if min(len(ta), len(tb)) >= 2 else 0.0
    return strict, max(strict, 0.9 * contain)


def title_similarity(a: str | None, b: str | None) -> float:
    return _title_signals(a, b)[1]


def _norm_name(s: str | None) -> str:
    s = _ORG_NOISE.sub(" ", _ascii((s or "").lower()))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def _name_similarity(a: str | None, b: str | None) -> float | None:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return None
    return SequenceMatcher(None, na, nb).ratio()


def _days_apart(a: str | None, b: str | None) -> int | None:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class DuplicateMatch:
    event: dict
    score: float
    confidence: str  # exact | high | possible
    reasons: list[str] = field(default_factory=list)


def score_pair(a: dict, b: dict) -> tuple[float, list[str]]:
    """Similarity of two event dicts in [0, 1] plus human-readable reasons."""
    sa, sb = a.get("source") or {}, b.get("source") or {}
    if sa.get("name") and sa.get("name") == sb.get("name") and sa.get("source_event_id") and sa.get("source_event_id") == sb.get("source_event_id"):
        return 1.0, ["same source event id"]

    reasons: list[str] = []
    days = _days_apart(a.get("start_date"), b.get("start_date"))
    if days is None or days > 1:
        return 0.0, []

    strict, t = _title_signals(a.get("title"), b.get("title"))
    if t < 0.6:
        return 0.0, []
    reasons.append(f"title similarity {t:.0%}")
    reasons.append("same start date" if days == 0 else "start dates 1 day apart")

    la, lb = a.get("location") or {}, b.get("location") or {}
    on_a, on_b = bool(a.get("is_online")), bool(b.get("is_online"))
    city_a, city_b = _norm_name(la.get("city")), _norm_name(lb.get("city"))
    if on_a and on_b:
        loc = 1.0
        reasons.append("both online")
    elif city_a and city_b:
        if city_a == city_b:
            loc = 1.0
            reasons.append("same city")
        else:
            loc = 0.0  # different cities: almost certainly different events
    else:
        loc = 0.5

    org = _name_similarity((a.get("organizer") or {}).get("name"), (b.get("organizer") or {}).get("name"))
    ven = _name_similarity(la.get("venue"), lb.get("venue"))
    if org is not None and org >= 0.8:
        reasons.append("same organizer")
    if ven is not None and ven >= 0.8:
        reasons.append("same venue")

    score = 0.55 * t + 0.20 * loc + 0.15 * (0.5 if org is None else org) + 0.10 * (0.5 if ven is None else ven)
    if days == 1:
        score -= 0.05
    if loc == 0.0:
        score = min(score, 0.5)
    if t > strict:  # matched only by containment: suggestive, never enough to auto-merge
        score = min(score, HIGH_THRESHOLD - 0.01)
    return round(max(0.0, min(score, 1.0)), 4), reasons


def _confidence(score: float, reasons: list[str]) -> str | None:
    if score >= 1.0 and "same source event id" in reasons:
        return "exact"
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= POSSIBLE_THRESHOLD:
        return "possible"
    return None


def _candidates(coll: Collection, event: dict, exclude_id: str | None) -> Iterable[dict]:
    sd = event.get("start_date")
    try:
        d = date.fromisoformat(sd)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return []
    q: dict[str, Any] = {
        "start_date": {"$gte": (d - timedelta(days=1)).isoformat(), "$lte": (d + timedelta(days=1)).isoformat()},
        "review_status": {"$ne": "duplicate"},
    }
    if exclude_id:
        q["_id"] = {"$ne": exclude_id}
    return coll.find(q).limit(500)


def find_duplicate(coll: Collection, event: dict, *, exclude_id: str | None = None) -> DuplicateMatch | None:
    """Best existing match for `event`, or None."""
    best: DuplicateMatch | None = None
    for cand in _candidates(coll, event, exclude_id):
        if event.get("_id") and cand.get("_id") == event["_id"]:
            continue
        if cand.get("_id") in (event.get("not_duplicates") or []):
            continue
        score, reasons = score_pair(event, cand)
        conf = _confidence(score, reasons)
        if conf and (best is None or score > best.score):
            best = DuplicateMatch(cand, score, conf, reasons)
    return best


def suggest_duplicates(coll: Collection, *, limit: int = 50, min_score: float = POSSIBLE_THRESHOLD) -> list[dict]:
    """Scan stored events for likely duplicate pairs (for the admin review queue)."""
    docs = list(
        coll.find(
            {"review_status": {"$ne": "duplicate"}, "status": {"$in": ["upcoming", "ongoing", "postponed"]}},
        ).sort("start_date", 1).limit(5000)
    )
    by_date: dict[str, list[dict]] = {}
    for d in docs:
        by_date.setdefault(d.get("start_date") or "", []).append(d)

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for sd, group in by_date.items():
        try:
            nxt = (date.fromisoformat(sd) + timedelta(days=1)).isoformat()
        except ValueError:
            continue
        pool = group + by_date.get(nxt, [])
        for i, a in enumerate(group):
            for b in pool:
                if a["_id"] == b["_id"]:
                    continue
                key = tuple(sorted((a["_id"], b["_id"])))
                if key in seen:
                    continue
                seen.add(key)  # type: ignore[arg-type]
                if b["_id"] in (a.get("not_duplicates") or []) or a["_id"] in (b.get("not_duplicates") or []):
                    continue
                score, reasons = score_pair(a, b)
                conf = _confidence(score, reasons)
                if conf and score >= min_score:
                    out.append({"a": a, "b": b, "score": score, "confidence": conf, "reasons": reasons})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]
