"""Event classification: summary, type, categories, topics, audience, keywords.

Two layers, both optional and both non-fatal:
  1. A deterministic rule-based classifier (always available, no network).
  2. An optional LLM classifier that reuses Casefile's shared client (Azure OpenAI primary),
     enabled with EVENT_AI_ENABLED=true. If it errors or returns junk, the rule-based
     result is used and the event is still stored.

Classification only FILLS MISSING fields by default, so source-provided and
admin-edited values are never overwritten unless `force=True`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.events.config import get_settings
from backend.events.models import EVENT_TYPE_LABELS
from backend.events.taxonomy import AUDIENCES, CATEGORIES, canonical_category
from backend.events.processors.normalize import clean_list, clean_text, map_event_type

log = logging.getLogger(__name__)

# category -> keywords (matched on word boundaries)
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Artificial Intelligence": ["artificial intelligence", "ai", "genai", "generative ai", "llm", "llms", "large language model", "chatgpt", "ai agents", "agentic", "computer vision", "nlp", "neural"],
    "Machine Learning": ["machine learning", "ml", "deep learning", "mlops", "reinforcement learning", "neural network"],
    "Technology": ["technology", "tech", "innovation", "digital transformation", "iot", "5g", "robotics", "quantum"],
    "Software": ["software", "developer", "developers", "programming", "open source", "api", "apis", "devops", "engineering"],
    "SaaS": ["saas", "b2b software", "subscription software"],
    "Startups": ["startup", "startups", "founder", "founders", "pitch", "demo day", "accelerator", "incubator", "seed stage"],
    "Finance": ["finance", "financial", "banking", "accounting", "treasury", "wealth"],
    "FinTech": ["fintech", "payments", "open banking", "neobank", "insurtech", "regtech"],
    "Healthcare": ["healthcare", "health care", "clinical", "hospital", "medical", "patient", "pharma", "biotech"],
    "HealthTech": ["healthtech", "digital health", "telehealth", "medtech", "health tech"],
    "Travel": ["travel", "tourism", "hospitality", "airline", "hotel"],
    "TravelTech": ["traveltech", "travel tech", "booking", "online travel"],
    "E-commerce": ["e-commerce", "ecommerce", "online retail", "marketplace", "d2c", "shopify"],
    "Marketing": ["marketing", "seo", "content marketing", "branding", "advertising", "growth marketing", "social media"],
    "Sales": ["sales", "revenue", "crm", "business development", "account executive", "go-to-market", "gtm"],
    "Cybersecurity": ["cybersecurity", "cyber security", "infosec", "security", "zero trust", "ransomware", "soc", "threat"],
    "Cloud": ["cloud", "aws", "azure", "gcp", "kubernetes", "serverless", "infrastructure"],
    "Data Science": ["data science", "data scientist", "analytics", "big data", "data engineering", "business intelligence", "bi"],
    "Blockchain": ["blockchain", "crypto", "cryptocurrency", "web3", "defi", "nft", "bitcoin", "ethereum"],
    "Education": ["education", "edtech", "learning", "university", "teachers", "students", "curriculum"],
    "Manufacturing": ["manufacturing", "industry 4.0", "factory", "industrial", "automation", "additive manufacturing"],
    "Automotive": ["automotive", "electric vehicle", "ev", "mobility", "autonomous vehicles", "car"],
    "Real Estate": ["real estate", "proptech", "property", "construction", "housing"],
    "Logistics": ["logistics", "supply chain", "freight", "warehouse", "shipping", "fulfillment"],
    "Energy": ["energy", "renewable", "solar", "wind power", "oil and gas", "cleantech", "hydrogen", "sustainability"],
    "Retail": ["retail", "consumer goods", "store", "merchandising", "omnichannel"],
    "Human Resources": ["human resources", "hr", "talent", "recruiting", "recruitment", "people ops", "workforce", "hiring"],
    "Product Management": ["product management", "product manager", "product managers", "product-led", "roadmap", "ux", "product design"],
    "Business": ["business", "leadership", "strategy", "management", "executive", "enterprise"],
    "Entrepreneurship": ["entrepreneur", "entrepreneurs", "entrepreneurship", "small business", "founder"],
    "Investment": ["investment", "investor", "investors", "venture capital", "vc", "private equity", "funding", "angel"],
}

AUDIENCE_KEYWORDS: dict[str, list[str]] = {
    "Founders": ["founder", "founders", "co-founder", "cofounders"],
    "Entrepreneurs": ["entrepreneur", "entrepreneurs", "small business owners"],
    "Investors": ["investor", "investors", "vc", "venture capital", "angel investors", "limited partners"],
    "Developers": ["developer", "developers", "software engineers", "programmers", "devs"],
    "CTOs": ["cto", "ctos", "vp engineering", "engineering leaders", "tech leaders"],
    "Product Managers": ["product manager", "product managers", "product leaders", "pms"],
    "Business Leaders": ["business leaders", "executives", "c-suite", "ceo", "ceos", "decision makers", "leaders"],
    "Researchers": ["researcher", "researchers", "scientists", "academics", "phd"],
    "Designers": ["designer", "designers", "ux designers", "ui designers"],
    "Marketers": ["marketer", "marketers", "marketing leaders", "cmo"],
    "Sales Professionals": ["sales professionals", "sales leaders", "sales teams", "account executives"],
    "Data Scientists": ["data scientist", "data scientists", "data engineers", "analysts"],
    "Engineers": ["engineer", "engineers", "engineering teams"],
    "Students": ["students", "graduates", "early-career", "university students"],
    "HR Professionals": ["hr professionals", "hr leaders", "recruiters", "talent acquisition", "chros"],
    "Executives": ["executives", "c-level", "senior leaders", "vps"],
}

_TYPE_TITLE_RULES: list[tuple[str, str]] = [
    (r"\bhackathon\b", "hackathon"), (r"\bwebinar\b", "webinar"), (r"\bworkshop\b", "workshop"),
    (r"\bmeet[- ]?up\b", "meetup"), (r"\btrade ?show\b", "trade_show"), (r"\bexpo\b|\bexhibition\b", "expo"),
    (r"\bsummit\b", "summit"), (r"\bnetworking\b|\bmixer\b", "business_networking"),
    (r"\bseminar\b", "industry_seminar"), (r"\btraining\b|\bbootcamp\b|\bmasterclass\b", "training"),
    (r"\bdemo day\b|\bpitch\b|\bstartup\b", "startup_event"),
    (r"\bconference\b|\bcongress\b|\bsymposium\b|\bconvention\b|\bforum\b", "conference"),
]


@dataclass
class Classification:
    event_type: str | None = None
    summary: str | None = None
    categories: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    method: str = "rules"


def _count(pattern_words: list[str], text: str) -> int:
    n = 0
    for w in pattern_words:
        n += len(re.findall(rf"(?<![\w]){re.escape(w)}(?![\w])", text))
    return n


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")) if s.strip()]


def make_summary(event: dict, max_len: int = 220) -> str | None:
    desc = clean_text(event.get("description"), multiline=False)
    if desc:
        out = ""
        for s in _sentences(desc):
            if out and len(out) + len(s) + 1 > max_len:
                break
            out = f"{out} {s}".strip()
            if len(out) >= 90:
                break
        if len(out) > max_len:
            out = out[: max_len - 1].rstrip(" ,;:") + "…"
        if out:
            return out
    etype = EVENT_TYPE_LABELS.get(event.get("event_type") or "", "Event")
    loc = event.get("location") or {}
    where = ", ".join(x for x in (loc.get("city"), loc.get("country")) if x) or ("online" if event.get("is_online") else "")
    parts = [f"{etype}"]
    if where:
        parts.append(f"in {where}" if where != "online" else "held online")
    if event.get("start_date"):
        parts.append(f"on {event['start_date']}")
    title = event.get("title")
    return f"{title}: {' '.join(parts)}." if title else None


def classify_rules(event: dict) -> Classification:
    title = (event.get("title") or "").lower()
    body = " ".join(
        [
            (event.get("summary") or ""),
            (event.get("description") or ""),
            " ".join(event.get("categories") or []),
            " ".join(event.get("topics") or []),
            (event.get("organizer") or {}).get("name") or "",
        ]
    ).lower()

    # --- type: title wins, then body, then source-provided hint
    etype: str | None = None
    for pat, val in _TYPE_TITLE_RULES:
        if re.search(pat, title):
            etype = val
            break
    if etype is None:
        etype = map_event_type(body[:400]) if body else None

    # --- categories: weighted keyword hits (title counts triple)
    scored: list[tuple[int, str, list[str]]] = []
    for cat, words in CATEGORY_KEYWORDS.items():
        t = _count(words, title)
        b = _count(words, body)
        score = t * 3 + b
        if score >= 2 or t >= 1:
            hits = [w for w in words if re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", title + " " + body)]
            scored.append((score, cat, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))
    categories = [c for _, c, _ in scored[:4]]

    topics: list[str] = []
    for _, _, hits in scored[:4]:
        for h in hits:
            label = h.upper() if len(h) <= 3 else h.title()
            if label not in topics:
                topics.append(label)
    topics = topics[:8]

    audience = [a for a, words in AUDIENCE_KEYWORDS.items() if _count(words, title + " " + body) >= 1][:6]
    keywords = clean_list(topics + categories, max_items=12)

    return Classification(
        event_type=etype,
        summary=make_summary(event),
        categories=categories,
        topics=topics,
        audience=audience,
        keywords=keywords,
        method="rules",
    )


# ------------------------------------------------------------------------------------ LLM
_LLM_SYSTEM = (
    "You classify professional events. Reply with ONE JSON object and nothing else, with keys: "
    '"summary" (max 240 chars, factual, no hype), "event_type" (one of: {types}), '
    '"categories" (0-4 items, prefer from: {cats}), "topics" (0-8 short tags), '
    '"audience" (0-6 items, prefer from: {aud}), "keywords" (0-10). '
    "Use only information present in the event; do not invent facts."
)


def ai_available() -> bool:
    """AI classification needs EVENT_AI_ENABLED=true AND a configured Casefile LLM (Azure/Groq)."""
    if not get_settings().ai_enabled:
        return False
    try:
        from backend.services import llm

        return bool(llm.azure_configured() or llm.groq_configured())
    except Exception:  # noqa: BLE001
        return False


def _llm_chat(messages: list[dict]) -> str:
    """Single seam for the LLM call (Casefile's shared client: Azure OpenAI primary)."""
    from backend.services import llm

    return llm.chat(messages, json_mode=True, max_tokens=700, reasoning_effort="low", timeout=45.0, retry_empty=False)


def classify_llm(event: dict) -> Classification | None:
    """Returns None on any failure (no key, network, parse, validation)."""
    if not ai_available():
        return None
    loc = event.get("location") or {}
    payload = {
        "title": event.get("title"),
        "description": (event.get("description") or event.get("summary") or "")[:3500],
        "organizer": (event.get("organizer") or {}).get("name"),
        "location": ", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
        "format": event.get("format"),
        "existing_categories": event.get("categories"),
    }
    system = _LLM_SYSTEM.format(
        types=", ".join(EVENT_TYPE_LABELS), cats=", ".join(CATEGORIES), aud=", ".join(AUDIENCES)
    )
    try:
        text = _llm_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
        )
        m = re.search(r"\{.*\}", text or "", re.S)
        data = json.loads(m.group(0)) if m else None
        if not isinstance(data, dict):
            raise ValueError("model did not return a JSON object")
        return Classification(
            event_type=map_event_type(data.get("event_type")),
            summary=clean_text(data.get("summary"), max_len=300),
            categories=clean_list(data.get("categories"), max_items=4, canonical=canonical_category),
            topics=clean_list(data.get("topics"), max_items=8),
            audience=clean_list(data.get("audience"), max_items=6),
            keywords=clean_list(data.get("keywords"), max_items=10),
            method="llm",
        )
    except Exception as exc:  # noqa: BLE001 - AI must never break ingestion
        log.warning("AI classification failed (%s); using rule-based result", exc.__class__.__name__)
        return None


# ------------------------------------------------------------------------------ public API
def classify_event(event: dict, *, use_ai: bool | None = None, force: bool = False) -> dict:
    """Return the fields to set on `event` (does not mutate it).

    force=False fills only missing/weak fields. force=True replaces classification fields.
    """
    rules = classify_rules(event)
    ai = classify_llm(event) if (use_ai if use_ai is not None else ai_available()) else None

    def pick(field_name: str):
        a = getattr(ai, field_name, None) if ai else None
        return a if a else getattr(rules, field_name)

    updates: dict[str, Any] = {}
    current_type = event.get("event_type")
    new_type = pick("event_type")
    if new_type and (force or not current_type or current_type == "other"):
        if new_type != current_type:
            updates["event_type"] = new_type
    elif not current_type:
        updates["event_type"] = "other"

    for f in ("summary", "categories", "topics", "audience", "keywords"):
        new = pick(f)
        if new and (force or not event.get(f)):
            updates[f] = new

    if ai and ai.method == "llm":
        updates["classified_by"] = "llm"
    elif updates:
        updates["classified_by"] = "rules"
    return updates
