"""
AEO / GEO Visibility Audit — Hackathon MVP (one-shot)
=====================================================
Flow:
  1. Crawl company site for AEO signals (headings, FAQ, schema, meta, about)
  2. Suggest topics / keywords (LLM) — or use user-provided list
  3. For each topic: find who's winning (DuckDuckGo free; SerpAPI optional)
  4. Gap analysis vs top pages
  5. Ready-to-use before/after fixes (headings, FAQs, schema)
  6. GEO readiness snapshot (external mentions — directories, reviews, press)

No DB, no scheduled monitoring — perfect for hackathon demos.
SerpAPI budget: at most `max_serp_searches` calls per run (default 3).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from backend.services import llm as llm_client

load_dotenv()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
MAX_TOPICS = 5
MAX_SERP_DEFAULT = 3  # SerpAPI free tier = 250/mo — keep demos cheap


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _fetch_html(url: str, timeout: int = 18) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text or ""
    except Exception as e:
        print(f"[AEO] fetch failed {url}: {e}")
        return ""


def _clean_text(soup: BeautifulSoup, limit: int = 4000) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:limit]


# ── Phase 1 — On-page AEO crawl ──────────────────────────────────────────────

def _extract_schema_types(soup: BeautifulSoup) -> list[dict]:
    found = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type") or item.get("type") or "Unknown"
            if isinstance(t, list):
                t = ", ".join(str(x) for x in t)
            found.append({
                "type": str(t),
                "name": str(item.get("name") or item.get("headline") or "")[:120],
                "has_faq": bool(
                    str(t).lower() == "faqpage"
                    or (isinstance(item.get("mainEntity"), list) and "Question" in str(item))
                ),
            })
    return found[:20]


def _extract_headings(soup: BeautifulSoup) -> dict:
    out = {"h1": [], "h2": [], "h3": []}
    for level in ("h1", "h2", "h3"):
        for tag in soup.find_all(level):
            text = tag.get_text(" ", strip=True)
            if text and len(text) < 200:
                out[level].append(text)
        out[level] = out[level][:15]
    return out


def _extract_faqs_from_dom(soup: BeautifulSoup) -> list[dict]:
    faqs = []
    # details/summary pattern
    for det in soup.find_all("details"):
        q = det.find("summary")
        if not q:
            continue
        question = q.get_text(" ", strip=True)
        answer = det.get_text(" ", strip=True).replace(question, "", 1).strip()
        if question and len(question) > 5:
            faqs.append({"question": question[:200], "answer": answer[:500], "source": "details"})

    # FAQPage JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("@type", "")).lower() != "faqpage":
                continue
            for ent in item.get("mainEntity") or []:
                if not isinstance(ent, dict):
                    continue
                q = ent.get("name") or ""
                ans = ""
                accepted = ent.get("acceptedAnswer") or {}
                if isinstance(accepted, dict):
                    ans = accepted.get("text") or ""
                if q:
                    faqs.append({"question": str(q)[:200], "answer": str(ans)[:500], "source": "schema"})

    # Heuristic: headings that look like questions
    if len(faqs) < 3:
        for tag in soup.find_all(["h2", "h3", "h4", "strong"]):
            text = tag.get_text(" ", strip=True)
            if "?" in text and 10 < len(text) < 160:
                nxt = tag.find_next(["p", "div", "li"])
                ans = nxt.get_text(" ", strip=True)[:500] if nxt else ""
                faqs.append({"question": text, "answer": ans, "source": "heading"})
    # dedupe
    seen = set()
    unique = []
    for f in faqs:
        key = f["question"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique[:12]


def _find_subpage(origin: str, paths: list[str]) -> tuple[str, str]:
    for path in paths:
        url = origin.rstrip("/") + path
        html = _fetch_html(url, timeout=12)
        if len(html) > 800:
            return url, html
        time.sleep(0.1)
    return "", ""


def crawl_aeo_signals(url: str) -> dict:
    """Crawl homepage + about/faq for AEO-relevant structure."""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    html = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")

    title = (soup.title.string or "").strip() if soup.title else ""
    meta_desc = ""
    meta_keywords = ""
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or "").lower()
        prop = (tag.get("property") or "").lower()
        content = tag.get("content") or ""
        if name == "description" or prop == "og:description":
            meta_desc = content[:600]
        if name == "keywords":
            meta_keywords = content[:300]

    homepage_text = _clean_text(BeautifulSoup(html, "html.parser"), 5000) if html else ""
    headings = _extract_headings(soup)
    schema = _extract_schema_types(soup)
    faqs = _extract_faqs_from_dom(soup)

    about_url, about_html = _find_subpage(
        origin,
        ["/about", "/about-us", "/company", "/who-we-are"],
    )
    about_text = ""
    about_headings = {"h1": [], "h2": [], "h3": []}
    if about_html:
        about_soup = BeautifulSoup(about_html, "html.parser")
        about_text = _clean_text(about_soup, 3500)
        about_headings = _extract_headings(about_soup)
        schema.extend(_extract_schema_types(about_soup))

    faq_url, faq_html = _find_subpage(
        origin,
        ["/faq", "/faqs", "/help", "/support", "/questions"],
    )
    if faq_html:
        faq_soup = BeautifulSoup(faq_html, "html.parser")
        faqs.extend(_extract_faqs_from_dom(faq_soup))
        schema.extend(_extract_schema_types(faq_soup))

    # dedupe faqs again
    seen = set()
    uniq_faqs = []
    for f in faqs:
        k = f["question"].lower().strip()
        if k in seen:
            continue
        seen.add(k)
        uniq_faqs.append(f)

    schema_types = sorted({s["type"] for s in schema if s.get("type")})
    has_faq_schema = any(
        "faq" in (s.get("type") or "").lower() or s.get("has_faq") for s in schema
    )
    has_org_schema = any("organization" in (s.get("type") or "").lower() for s in schema)

    return {
        "url": url,
        "origin": origin,
        "domain": parsed.netloc.replace("www.", ""),
        "title": title,
        "meta_description": meta_desc,
        "meta_keywords": meta_keywords,
        "homepage_text": homepage_text,
        "headings": headings,
        "about_url": about_url,
        "about_text": about_text,
        "about_headings": about_headings,
        "faq_url": faq_url,
        "faqs_found": uniq_faqs[:12],
        "schema_blocks": schema[:15],
        "schema_types": schema_types,
        "signals": {
            "has_h1": len(headings.get("h1") or []) > 0,
            "h1_count": len(headings.get("h1") or []),
            "h2_count": len(headings.get("h2") or []),
            "has_meta_description": bool(meta_desc),
            "has_about_page": bool(about_text),
            "faq_count": len(uniq_faqs),
            "has_faq_schema": has_faq_schema,
            "has_organization_schema": has_org_schema,
            "schema_types": schema_types,
        },
    }


# ── Phase 2 — Topic suggestions ──────────────────────────────────────────────

def suggest_topics(site: dict, user_keywords: Optional[list[str]] = None) -> list[str]:
    if user_keywords:
        cleaned = [k.strip() for k in user_keywords if k and str(k).strip()]
        if cleaned:
            return cleaned[:MAX_TOPICS]

    prompt = f"""You are an AEO/GEO strategist. Based on this website, suggest {MAX_TOPICS} search topics
a potential customer would type into Google or ask an AI assistant.

Return JSON only:
{{"topics": ["topic1", "topic2", ...]}}

Rules:
- Topics should be natural search queries / questions (not just brand name)
- Mix: 2 commercial intent ("best X for Y"), 2 problem/question, 1 category
- Keep each under 8 words
- English only

Website title: {site.get('title')}
Domain: {site.get('domain')}
Meta: {site.get('meta_description')}
H1s: {site.get('headings', {}).get('h1')}
H2s: {site.get('headings', {}).get('h2')[:8]}
About (excerpt): {(site.get('about_text') or site.get('homepage_text') or '')[:1800]}
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=600,
            json_mode=True,
        )
        data = json.loads(raw)
        topics = data.get("topics") or []
        return [str(t).strip() for t in topics if str(t).strip()][:MAX_TOPICS]
    except Exception as e:
        print(f"[AEO] topic suggest failed: {e}")
        name = site.get("domain", "company").split(".")[0]
        return [
            f"best {name} alternative",
            f"what is {name}",
            f"{name} pricing",
        ]


# ── Phase 3 — Who's winning (DDG free / SerpAPI optional) ────────────────────

def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    rows = []
    # Prefer new package name `ddgs` (duckduckgo_search is deprecated / flaky)
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            rows = list(ddgs.text(query, max_results=max_results))
    except Exception as e1:
        print(f"[AEO] ddgs failed '{query}': {e1}")
        try:
            from duckduckgo_search import DDGS as LegacyDDGS
            with LegacyDDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=max_results))
        except Exception as e2:
            print(f"[AEO] legacy DDG failed '{query}': {e2}")
            return []
    out = []
    for r in rows:
        url = r.get("href") or r.get("link") or r.get("url") or ""
        if not url:
            continue
        out.append({
            "title": r.get("title") or "",
            "url": url,
            "snippet": r.get("body") or r.get("snippet") or "",
            "source": "duckduckgo",
        })
    return out


def _serpapi_search(query: str, max_results: int = 5) -> list[dict]:
    if not SERPAPI_KEY:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "api_key": SERPAPI_KEY,
                "num": max_results,
            },
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic_results") or []
        return [
            {
                "title": r.get("title") or "",
                "url": r.get("link") or "",
                "snippet": r.get("snippet") or "",
                "source": "serpapi",
            }
            for r in organic[:max_results]
            if r.get("link")
        ]
    except Exception as e:
        print(f"[AEO] SerpAPI failed '{query}': {e}")
        return []


def search_competitors(
    query: str,
    *,
    use_serpapi: bool,
    serp_budget_left: list[int],
) -> list[dict]:
    """Prefer SerpAPI only while budget remains; else DuckDuckGo (free)."""
    if use_serpapi and SERPAPI_KEY and serp_budget_left[0] > 0:
        rows = _serpapi_search(query)
        if rows:
            serp_budget_left[0] -= 1
            return rows
    return _ddg_search(query)


def _light_page_signals(url: str) -> dict:
    html = _fetch_html(url, timeout=12)
    if not html:
        return {"url": url, "ok": False}
    soup = BeautifulSoup(html, "html.parser")
    headings = _extract_headings(soup)
    schema = _extract_schema_types(soup)
    faqs = _extract_faqs_from_dom(soup)
    title = (soup.title.string or "").strip() if soup.title else ""
    meta = ""
    for tag in soup.find_all("meta"):
        if (tag.get("name") or "").lower() == "description":
            meta = (tag.get("content") or "")[:300]
            break
    text = _clean_text(BeautifulSoup(html, "html.parser"), 2000)
    return {
        "url": url,
        "ok": True,
        "title": title,
        "meta_description": meta,
        "headings": headings,
        "faq_count": len(faqs),
        "schema_types": sorted({s["type"] for s in schema}),
        "text_excerpt": text[:1500],
        "has_faq_schema": any("faq" in (s.get("type") or "").lower() for s in schema),
    }


# ── Phase 4+5 — Gaps + before/after recommendations ─────────────────────────

def _heuristic_recommendations(site: dict, topics: list[str], company_name: str) -> dict:
    """Always-usable before/after fixes when LLM is down — keeps hackathon demos alive."""
    signals = site.get("signals") or {}
    h1s = (site.get("headings") or {}).get("h1") or []
    meta = site.get("meta_description") or ""
    domain = site.get("domain") or "example.com"
    topic0 = topics[0] if topics else f"what is {company_name}"
    topic1 = topics[1] if len(topics) > 1 else f"best {company_name} alternative"

    aeo = 20
    if signals.get("has_h1"):
        aeo += 15
    if signals.get("has_meta_description"):
        aeo += 10
    if signals.get("has_about_page"):
        aeo += 15
    if signals.get("faq_count", 0) >= 3:
        aeo += 15
    elif signals.get("faq_count", 0) >= 1:
        aeo += 5
    if signals.get("has_faq_schema"):
        aeo += 15
    if signals.get("has_organization_schema"):
        aeo += 10
    aeo = min(100, aeo)

    faqs = [
        {
            "question": f"What is {company_name}?",
            "answer": (
                f"{company_name} helps customers with products and services described on {domain}. "
                f"Replace this with a plain, one-sentence description of what you sell and who you serve."
            ),
        },
        {
            "question": f"Who is {company_name} for?",
            "answer": f"{company_name} is built for [target customer]. Fill in the exact audience (e.g. startups, SMBs, enterprises).",
        },
        {
            "question": f"How is {company_name} different?",
            "answer": f"Unlike alternatives, {company_name} [unique value]. Keep this factual and consistent everywhere.",
        },
        {
            "question": topic0 if "?" in topic0 else f"How does {company_name} help with {topic0}?",
            "answer": f"{company_name} addresses this by [how product solves it]. Lead with the direct answer in the first sentence.",
        },
        {
            "question": topic1 if "?" in topic1 else f"Is {company_name} a good option for {topic1}?",
            "answer": f"Yes — {company_name} is relevant when you need [use case]. Add proof points (customers, features) here.",
        },
    ]

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["question"],
                "acceptedAnswer": {"@type": "Answer", "text": f["answer"]},
            }
            for f in faqs[:5]
        ],
    }
    org_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": company_name,
        "url": site.get("url") or f"https://{domain}",
        "description": meta or f"{company_name} — add a consistent 1-2 sentence description.",
    }

    recs = []
    before_h1 = h1s[0] if h1s else "(missing)"
    recs.append({
        "id": "rec_h1",
        "type": "heading",
        "priority": "High",
        "page": "homepage",
        "title": "Answer-first H1",
        "why": "Answer engines prefer a clear, direct heading that states what you do.",
        "before": before_h1,
        "after": f"{company_name}: [what you do] for [who you serve]",
        "aeo_impact": "Strong",
        "geo_impact": "Moderate",
    })
    recs.append({
        "id": "rec_meta",
        "type": "meta",
        "priority": "High",
        "page": "homepage",
        "title": "Tighten meta description",
        "why": "A consistent short description helps both snippets and AI systems identify the brand.",
        "before": meta or "(missing)",
        "after": f"{company_name} helps [audience] [outcome]. Start free / book a demo.",
        "aeo_impact": "Strong",
        "geo_impact": "Moderate",
    })
    recs.append({
        "id": "rec_faq",
        "type": "faq",
        "priority": "High",
        "page": "faq" if site.get("faq_url") else "new",
        "title": "Add customer-question FAQs",
        "why": "FAQs mirror how people ask AI assistants and Google answer boxes.",
        "before": f"{signals.get('faq_count', 0)} FAQ(s) found on site",
        "after": "\n".join(f"Q: {f['question']}\nA: {f['answer']}" for f in faqs[:3]),
        "aeo_impact": "Strong",
        "geo_impact": "Moderate",
    })
    recs.append({
        "id": "rec_faq_schema",
        "type": "schema",
        "priority": "High",
        "page": "faq" if site.get("faq_url") else "new",
        "title": "Add FAQPage schema",
        "why": "FAQ schema helps search/answer engines reuse your Q&A as direct answers.",
        "before": "FAQPage schema: " + ("present" if signals.get("has_faq_schema") else "(missing)"),
        "after": json.dumps(faq_schema, indent=2),
        "aeo_impact": "Strong",
        "geo_impact": "Light",
    })
    recs.append({
        "id": "rec_org_schema",
        "type": "schema",
        "priority": "Medium",
        "page": "homepage",
        "title": "Add Organization schema",
        "why": "Helps AI systems treat your brand as a real entity with consistent facts.",
        "before": "Organization schema: " + ("present" if signals.get("has_organization_schema") else "(missing)"),
        "after": json.dumps(org_schema, indent=2),
        "aeo_impact": "Moderate",
        "geo_impact": "Strong",
    })
    if not signals.get("has_about_page"):
        recs.append({
            "id": "rec_about",
            "type": "about",
            "priority": "High",
            "page": "about",
            "title": "Create a plain-language About page",
            "why": "New companies need a clear About page so search and AI can explain who you are.",
            "before": "(missing)",
            "after": (
                f"{company_name} is a [industry] company that helps [audience] [outcome]. "
                f"Founded in [year], we focus on [differentiation]."
            ),
            "aeo_impact": "Strong",
            "geo_impact": "Strong",
        })

    gaps = []
    if not signals.get("has_faq_schema") or signals.get("faq_count", 0) < 3:
        gaps.append({
            "area": "FAQ",
            "severity": "High",
            "finding": "Weak or missing FAQ + FAQ schema coverage.",
            "why_it_matters": "Direct-answer boxes and AI replies prefer structured Q&A.",
        })
    if not signals.get("has_organization_schema"):
        gaps.append({
            "area": "Schema",
            "severity": "Medium",
            "finding": "No Organization schema detected.",
            "why_it_matters": "Entity clarity improves GEO mention confidence.",
        })
    if not signals.get("has_about_page"):
        gaps.append({
            "area": "About",
            "severity": "High",
            "finding": "No About page content found.",
            "why_it_matters": "Brand understanding starts with a clear About story.",
        })
    if not gaps:
        gaps.append({
            "area": "Content",
            "severity": "Medium",
            "finding": "Core structure exists; deepen answer-first content for target topics.",
            "why_it_matters": "Competitors often win by answering the query in the first lines.",
        })

    return {
        "visibility_summary": (
            f"{company_name} was crawled for AEO structure (headings, FAQ, schema, About). "
            f"Scores reflect on-page readiness; apply the before/after fixes below, then distribute "
            f"consistent facts on directories, reviews, and comparison pages for GEO."
        ),
        "aeo_score": aeo,
        "geo_score": 35,
        "gaps": gaps,
        "recommendations": recs,
        "suggested_faqs": faqs,
        "suggested_schema": {
            "faq_page_jsonld": json.dumps(faq_schema),
            "organization_jsonld": json.dumps(org_schema),
        },
        "distribution_checklist": [
            {"action": "Publish clear About + FAQ on your site", "helps": "Both", "done_hint": "Open /about and /faq"},
            {"action": "Add FAQPage + Organization schema", "helps": "AEO", "done_hint": "View source for JSON-LD"},
            {"action": "Create listings on 3 relevant directories/review sites", "helps": "GEO", "done_hint": "Search brand on G2/Trustpilot/Google"},
            {"action": "Keep name + 1-line description identical everywhere", "helps": "Both", "done_hint": "Compare homepage vs listings"},
            {"action": "Ask early customers for honest reviews", "helps": "GEO", "done_hint": "Check review platforms weekly"},
        ],
    }


def _parse_json_loose(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def generate_recommendations(
    site: dict,
    topics: list[str],
    topic_research: list[dict],
    company_name: str,
) -> dict:
    fallback = _heuristic_recommendations(site, topics, company_name)

    competitor_digest = []
    for tr in topic_research:
        for c in (tr.get("top_results") or [])[:3]:
            competitor_digest.append({
                "topic": tr.get("topic"),
                "title": c.get("title"),
                "url": c.get("url"),
                "snippet": c.get("snippet"),
                "page": {
                    "title": (c.get("page_signals") or {}).get("title"),
                    "h1": ((c.get("page_signals") or {}).get("headings") or {}).get("h1"),
                    "faq_count": (c.get("page_signals") or {}).get("faq_count"),
                    "schema_types": (c.get("page_signals") or {}).get("schema_types"),
                },
            })

    prompt = f"""You are an AEO and GEO expert. Compare USER site vs competitors.
Return JSON ONLY:
{{"visibility_summary":"...","aeo_score":0,"geo_score":0,
"gaps":[{{"area":"FAQ","severity":"High","finding":"...","why_it_matters":"..."}}],
"recommendations":[{{"id":"rec1","type":"heading","priority":"High","page":"homepage","title":"...","why":"...","before":"...","after":"...","aeo_impact":"Strong","geo_impact":"Moderate"}}],
"suggested_faqs":[{{"question":"...","answer":"..."}}],
"suggested_schema":{{"faq_page_jsonld":"...","organization_jsonld":"..."}},
"distribution_checklist":[{{"action":"...","helps":"Both","done_hint":"..."}}]}}

Give 5-8 specific before/after recommendations. Schema fields are JSON strings.

USER: name={company_name} domain={site.get('domain')} title={site.get('title')}
meta={site.get('meta_description')}
signals={json.dumps(site.get('signals'))}
h1={site.get('headings', {}).get('h1')} h2={(site.get('headings') or {}).get('h2', [])[:8]}
faqs={json.dumps((site.get('faqs_found') or [])[:4])}
about={(site.get('about_text') or '')[:900]}
home={(site.get('homepage_text') or '')[:900]}
TOPICS={topics}
COMPETITORS={json.dumps(competitor_digest)[:4500]}
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Be specific and actionable."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=3000,
            json_mode=True,
            timeout=120.0,
        )
        data = _parse_json_loose(raw)
        # Ensure critical keys exist; fill from fallback if LLM omitted them
        for key in ("recommendations", "suggested_faqs", "gaps", "distribution_checklist"):
            if not data.get(key):
                data[key] = fallback.get(key)
        if not data.get("suggested_schema"):
            data["suggested_schema"] = fallback.get("suggested_schema")
        if data.get("aeo_score") is None:
            data["aeo_score"] = fallback.get("aeo_score")
        if data.get("geo_score") is None:
            data["geo_score"] = fallback.get("geo_score")
        if not data.get("visibility_summary"):
            data["visibility_summary"] = fallback.get("visibility_summary")
        data["_source"] = "llm"
        return data
    except Exception as e:
        print(f"[AEO] recommendation LLM failed: {e}")
        fallback["_source"] = "heuristic_fallback"
        fallback["_error"] = str(e)
        return fallback


# ── Phase 6 — GEO snapshot (one-shot, no monitoring) ─────────────────────────

def geo_mention_snapshot(company_name: str, domain: str, topics: list[str]) -> dict:
    """
    Hackathon GEO check without polling ChatGPT forever:
    look for third-party mentions (reviews, directories, comparisons, press).
    """
    queries = [
        f'"{company_name}" review OR reviews',
        f'"{company_name}" vs OR alternative OR comparison',
        f'"{company_name}" site:g2.com OR site:capterra.com OR site:trustpilot.com',
        f'"{domain}" (news OR interview OR "best of")',
    ]
    if topics:
        queries.append(f'best {topics[0]}')

    mentions = []
    for q in queries[:4]:
        for r in _ddg_search(q, max_results=4):
            url = (r.get("url") or "").lower()
            if domain.lower() in url:
                continue  # skip own site
            mentions.append({
                "query": q,
                "title": r.get("title"),
                "url": r.get("url"),
                "snippet": r.get("snippet"),
                "kind": _classify_mention(url),
            })
        time.sleep(0.15)

    # dedupe by url
    seen = set()
    unique = []
    for m in mentions:
        u = m.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        unique.append(m)

    kinds = {m["kind"] for m in unique}
    score = min(100, 15 * len(unique) + 10 * len(kinds))
    return {
        "company_name": company_name,
        "external_mentions": unique[:15],
        "mention_count": len(unique),
        "mention_kinds": sorted(kinds),
        "geo_readiness_score": score,
        "note": (
            "One-shot GEO snapshot from public web mentions (reviews, comparisons, press). "
            "Hackathon mode does not continuously poll ChatGPT/Claude."
        ),
    }


def _classify_mention(url: str) -> str:
    u = url.lower()
    if any(x in u for x in ("g2.com", "capterra", "trustpilot", "clutch.co", "producthunt")):
        return "reviews"
    if any(x in u for x in ("linkedin.com", "crunchbase", "wikidata", "wikipedia")):
        return "knowledge"
    if any(x in u for x in ("reddit.com", "quora.com", "forum")):
        return "forum"
    if any(x in u for x in ("vs", "alternative", "best-", "compare")):
        return "comparison"
    if any(x in u for x in ("news", "press", "medium.com", "blog")):
        return "press"
    return "other"


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run(
    url: str,
    keywords: Optional[list[str]] = None,
    *,
    use_serpapi: bool = False,
    max_topics: int = 3,
    max_serp_searches: int = MAX_SERP_DEFAULT,
) -> dict:
    """
    One-shot AEO/GEO audit.

    use_serpapi: if True and SERPAPI_KEY set, spend up to max_serp_searches calls.
    Everything else uses free DuckDuckGo.
    """
    started = time.time()
    print(f"[AEO] Starting audit for {url}")

    site = crawl_aeo_signals(url)
    brand_guess = (site.get("domain") or "company").split(".")[0].replace("-", " ").title()
    title_bit = (site.get("title") or "").split("|")[0].split("-")[0].strip()
    # Prefer short brand-like titles; otherwise use domain brand
    if title_bit and len(title_bit.split()) <= 4 and "workspace" not in title_bit.lower():
        company_name = title_bit
    else:
        company_name = brand_guess or "Company"

    topics = suggest_topics(site, keywords)[: max(1, min(max_topics, MAX_TOPICS))]
    print(f"[AEO] Topics: {topics}")

    serp_budget = [max_serp_searches if (use_serpapi and SERPAPI_KEY) else 0]
    search_engine = "serpapi+duckduckgo" if serp_budget[0] else "duckduckgo"

    topic_research = []
    for topic in topics:
        results = search_competitors(
            topic,
            use_serpapi=use_serpapi,
            serp_budget_left=serp_budget,
        )
        # enrich top 2 non-own results with light page signals
        enriched = []
        page_enriched = 0
        for r in results[:5]:
            item = dict(r)
            rurl = r.get("url") or ""
            if (
                rurl
                and site.get("domain")
                and site.get("domain") not in rurl.lower()
                and page_enriched < 2
            ):
                item["page_signals"] = _light_page_signals(rurl)
                page_enriched += 1
                time.sleep(0.15)
            enriched.append(item)
        topic_research.append({
            "topic": topic,
            "top_results": enriched,
            "winner_domains": [
                urlparse(r["url"]).netloc.replace("www.", "")
                for r in enriched if r.get("url")
            ][:5],
        })
        time.sleep(0.2)

    recs = generate_recommendations(site, topics, topic_research, company_name)
    geo = geo_mention_snapshot(company_name, site.get("domain") or "", topics)

    # blend GEO score into response
    if isinstance(recs.get("geo_score"), (int, float)):
        blended = int(round(0.5 * float(recs["geo_score"]) + 0.5 * geo["geo_readiness_score"]))
        recs["geo_score_blended"] = blended

    elapsed = round(time.time() - started, 1)
    return {
        "company_name": company_name,
        "url": site.get("url"),
        "domain": site.get("domain"),
        "on_page": {
            "title": site.get("title"),
            "meta_description": site.get("meta_description"),
            "headings": site.get("headings"),
            "about_url": site.get("about_url"),
            "faq_url": site.get("faq_url"),
            "faqs_found": site.get("faqs_found"),
            "schema_types": site.get("schema_types"),
            "signals": site.get("signals"),
        },
        "topics": topics,
        "topic_research": topic_research,
        "analysis": {
            "visibility_summary": recs.get("visibility_summary"),
            "aeo_score": recs.get("aeo_score"),
            "geo_score": recs.get("geo_score"),
            "geo_score_blended": recs.get("geo_score_blended"),
            "gaps": recs.get("gaps") or [],
            "recommendations": recs.get("recommendations") or [],
            "suggested_faqs": recs.get("suggested_faqs") or [],
            "suggested_schema": recs.get("suggested_schema") or {},
            "distribution_checklist": recs.get("distribution_checklist") or [],
            "recommendation_source": recs.get("_source") or "unknown",
        },
        "geo_snapshot": geo,
        "_meta": {
            "mode": "hackathon_one_shot",
            "search_engine": search_engine,
            "serpapi_configured": bool(SERPAPI_KEY),
            "serpapi_used": max_serp_searches - serp_budget[0] if use_serpapi else 0,
            "serpapi_budget_remaining_this_run": serp_budget[0],
            "model_used": llm_client.ACTIVE_MODEL_LABEL,
            "elapsed_seconds": elapsed,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "monitoring": "disabled (hackathon — run again manually to re-check)",
        },
    }
