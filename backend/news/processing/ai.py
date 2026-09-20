"""AI enrichment: summary, key points, event, category, topics, entities.

Design rules:
  * Input is ONLY the headline + the publisher's short teaser. Full articles are never fetched.
  * The model may not add facts. Entities it returns are kept only if the name literally appears
    in the input text (`ground_entities`), which removes hallucinated names.
  * Teasers that are too thin to summarise are skipped (ai_status="skipped"): a headline alone is
    not enough to write a faithful summary, so no summary is invented.
  * Every failure falls back to the rule-based / extractive result; nothing here can block ingestion.
  * The LLM is Casefile's shared client (Azure OpenAI primary), so no extra key is needed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.news.config import get_settings
from backend.news.processing.classify import CategoryIndex

log = logging.getLogger(__name__)

MIN_TEXT_FOR_AI = 60   # characters of teaser needed before the model is asked to summarise

_SYSTEM = (
    "You are a careful news analyst. You receive ONLY a headline and a short teaser from a publisher's feed. "
    "Reply with ONE JSON object and nothing else.\n"
    "Hard rules: use only information present in the provided text. Never add facts, numbers, names, quotes or dates "
    "that are not in it. Do not add titles or status words such as former, current, late, acting, alleged or convicted, "
    "and do not add first names, ages, places or background from your own knowledge. "
    "If the text is thin, write a shorter summary rather than guessing.\n"
    "Keys:\n"
    '  "summary": 2-4 sentences (1-2 if the text is thin), neutral tone, no hype.\n'
    '  "key_points": 3-5 short bullet strings, each supported by the text (fewer if the text supports fewer).\n'
    '  "event": ONE sentence stating what actually happened.\n'
    '  "category": exactly one of: {categories}\n'
    '  "categories": up to 3 of the same list, primary first.\n'
    '  "topics": up to 6 short topic labels (e.g. "AI Agents", "Semiconductors").\n'
    '  "entities": {{"people": [], "organizations": [], "countries": [], "locations": [], "products": [], "technologies": []}} '
    "- only names that appear in the text."
)


def ai_available() -> bool:
    if not get_settings().ai_enabled:
        return False
    try:
        from backend.services import llm

        return bool(llm.azure_configured() or llm.groq_configured())
    except Exception:  # noqa: BLE001
        return False


def _llm_chat(messages: list[dict]) -> str:
    """Single seam for the LLM call (Casefile's shared client)."""
    from backend.services import llm

    return llm.chat(messages, json_mode=True, max_tokens=900, reasoning_effort="low", timeout=60.0, retry_empty=False)


# ------------------------------------------------------------------ extractive fallback
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘'])")


def sentences(text: str | None) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if len(s.strip()) > 15]


def extractive_summary(description: str | None, max_len: int = 320) -> str | None:
    """First sentences of the publisher's own teaser (no generation involved)."""
    out = ""
    for s in sentences(description):
        if out and len(out) + len(s) + 1 > max_len:
            break
        out = f"{out} {s}".strip()
        if len(out) >= 160:
            break
    if not out and description:
        out = description if len(description) <= max_len else description[: max_len - 1].rstrip() + "…"
    return out or None


def extractive_key_points(description: str | None) -> list[str]:
    s = sentences(description)
    return [x[:180] for x in s[:4]] if len(s) >= 3 else []


# ------------------------------------------------------------------------- validation
def ground_entities(candidates: Any, source_text: str, limit: int = 12) -> list[str]:
    """Keep only names that literally occur in the source text (case-insensitive)."""
    hay = re.sub(r"\s+", " ", source_text or "").lower()
    out: list[str] = []
    seen: set[str] = set()
    for c in candidates or []:
        name = re.sub(r"\s+", " ", str(c or "")).strip(" .,;:")
        if 2 <= len(name) <= 60 and name.lower() in hay and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _strs(value: Any, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        s = re.sub(r"\s+", " ", str(v or "")).strip(" -••")
        if s and len(s) <= max_len and s not in out:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def parse_response(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("model did not return JSON")
    data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("model JSON is not an object")
    return data


def build_updates(data: dict, article: dict, index: CategoryIndex) -> dict:
    source_text = f"{article.get('title') or ''}. {article.get('description') or ''}"
    summary = re.sub(r"\s+", " ", str(data.get("summary") or "")).strip()
    if len(summary) < 20:
        raise ValueError("summary missing")
    detail_in = data.get("entities") if isinstance(data.get("entities"), dict) else {}
    detail = {k: ground_entities(detail_in.get(k), source_text) for k in ("people", "organizations", "countries", "locations", "products", "technologies")}
    flat = list(dict.fromkeys(detail["people"] + detail["organizations"] + detail["products"] + detail["technologies"]))[:12]
    locations = list(dict.fromkeys(detail["countries"] + detail["locations"]))[:6]

    updates: dict[str, Any] = {
        "summary": summary[:700],
        "key_points": _strs(data.get("key_points"), 5, 220),
        "event": (re.sub(r"\s+", " ", str(data.get("event") or "")).strip()[:300] or None),
        "topics": _strs(data.get("topics"), 6, 40) or article.get("topics") or [],
        "entities_detail": detail,
        "summary_source": "ai",
        "ai_status": "done",
    }
    if flat:
        updates["entities"] = list(dict.fromkeys(flat + (article.get("entities") or [])))[:12]
    if locations:
        updates["location"] = list(dict.fromkeys(locations + (article.get("location") or [])))[:6]

    primary = index.resolve(data.get("category"))
    if primary:
        cats = [primary["slug"]]
        for c in data.get("categories") or []:
            r = index.resolve(c)
            if r and r["slug"] not in cats:
                cats.append(r["slug"])
        updates["category"] = primary["slug"]
        updates["categories"] = cats[:3]
    return updates


# ------------------------------------------------------------------ unsupported-claim guard
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_NUM = re.compile(r"\d[\d,.]*\d|\d")
_RISKY = {
    "former", "late", "acting", "interim", "alleged", "allegedly", "convicted", "dead", "died", "killed", "arrested", "resigned",
    "fired", "sacked", "jailed", "charged", "sentenced", "impeached", "ousted", "current", "incumbent", "outgoing",
}
_CALENDAR = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "january", "february", "march", "april",
             "may", "june", "july", "august", "september", "october", "november", "december"}
_ALLOWED_CAPS = {"ai", "us", "uk", "eu", "un"}


def _norm(w: str) -> str:
    w = w.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def unsupported_terms(outputs: list[str], source_text: str, allowed: set[str] | None = None) -> list[str]:
    """Numbers, proper nouns and status words in the generated text that are NOT in the source text.

    Prompts alone do not stop a model from "helpfully" adding what it knows ("former president ...").
    This is the hard check: anything flagged means the text asserts something the publisher's
    headline/teaser did not say.
    """
    src_words = {_norm(w) for w in _WORD.findall(source_text or "")}
    src_nums = {n.replace(",", "") for n in _NUM.findall(source_text or "")}
    ok = {_norm(a) for a in (allowed or set())} | _ALLOWED_CAPS
    bad: list[str] = []
    for text in outputs:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
            words = _WORD.findall(sentence)
            for i, w in enumerate(words):
                n, lw = _norm(w), w.lower()
                if lw in _RISKY and n not in src_words and lw not in src_words:
                    bad.append(lw)
                elif i > 0 and w[0].isupper() and n not in src_words and n not in ok and lw not in _CALENDAR:
                    bad.append(w)
        for num in _NUM.findall(text or ""):
            if num.replace(",", "") not in src_nums:
                bad.append(num)
    return list(dict.fromkeys(bad))


def enrich_article(article: dict, index: CategoryIndex) -> dict | None:
    """Return the field updates for one article, or None when it should not / could not be enriched.

    One corrective retry if the text asserts something the source does not; if it still does,
    the result is rejected (the article keeps its extractive summary).
    """
    if not ai_available():
        return None
    system = _SYSTEM.format(categories=", ".join(sorted(index.by_slug)))
    payload = {
        "headline": article.get("title"),
        "teaser": article.get("description"),
        "publisher": (article.get("source") or {}).get("name"),
        "published": article["published_at"].isoformat() if article.get("published_at") else None,
    }
    source_text = f"{article.get('title') or ''}. {article.get('description') or ''}"
    allowed = set(_WORD.findall(payload["publisher"] or ""))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    text = _llm_chat(messages)
    for attempt in (1, 2):
        updates = build_updates(parse_response(text), article, index)   # raises on bad output; caller records it
        bad = unsupported_terms([updates["summary"], updates.get("event") or "", *updates["key_points"]], source_text, allowed)
        if not bad:
            return updates
        if attempt == 2:
            raise ValueError(f"unsupported claims not present in the source text: {bad[:6]}")
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": f"These terms are NOT in the headline or teaser: {bad[:8]}. Rewrite the JSON using ONLY information in the headline and teaser."},
        ]
        text = _llm_chat(messages)
    return None  # pragma: no cover
