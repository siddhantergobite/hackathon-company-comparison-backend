"""
LLM-as-Judge (Groq) — validate company-research facts before showing them.
Reject wrong legal entities, wrong directors, wrong-domain competitors,
and illogical scraped junk. Prefer silence over confident wrong answers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from backend.services import llm as llm_client


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in judge response")
    return json.loads(raw[start : end + 1])


def judge_entity_match(
    *,
    website_url: str,
    domain: str,
    brand_name: str,
    site_title: str,
    site_description: str,
    site_about_excerpt: str,
    candidate: dict,
) -> dict:
    """
    Decide if an MCA/Zauba candidate is the SAME operating company as the website.
    Reject subsidiaries / sister entities (e.g. TCS E-Serve for tcs.com).
    """
    legal = (candidate.get("legal_name") or candidate.get("Company Name") or "").strip()
    cin = (candidate.get("cin") or candidate.get("CIN") or "").strip()
    reason = candidate.get("reason") or candidate.get("match_reason") or ""
    score = candidate.get("score") or candidate.get("match_score") or 0

    prompt = f"""You are a strict corporate-entity judge for a company intelligence product.
Your job: decide if the MCA registry candidate is the SAME company that owns/operates the website.

WEBSITE
- url: {website_url}
- domain: {domain}
- brand/name guess: {brand_name}
- title: {site_title}
- description: {site_description[:400]}
- about excerpt: {site_about_excerpt[:700]}

MCA CANDIDATE
- legal_name: {legal}
- CIN: {cin}
- heuristic_score: {score}
- heuristic_reason: {reason}

RULES (critical):
1. Accept ONLY if the candidate is the primary operating legal entity for this website brand.
2. REJECT subsidiaries, service arms, foundations, employee trusts, SPVs, and sister companies
   even if they share the brand token (example: reject "TCS E-SERVE LIMITED" for tcs.com;
   prefer "Tata Consultancy Services Limited" / main listed entity if that is what the site represents).
3. If domain is a well-known parent brand site, require the legal name to be the parent / main company.
4. If unsure, REJECT. Never invent a better CIN — just reject.
5. Return JSON only:
{{
  "accept": true/false,
  "confidence": "High"|"Medium"|"Low",
  "preferred_display_name": "best public brand name for the website",
  "reason": "one short sentence",
  "is_subsidiary_or_sister": true/false
}}
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Be strict. Prefer reject over wrong accept."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=400,
            json_mode=True,
            timeout=45.0,
        )
        data = _parse_json(raw)
        data["accept"] = bool(data.get("accept"))
        conf = data.get("confidence") or "Low"
        # normalize numeric confidences from some models
        if isinstance(conf, (int, float)):
            conf = "High" if float(conf) >= 0.75 else ("Medium" if float(conf) >= 0.5 else "Low")
        data["confidence"] = str(conf)
        return data
    except Exception as e:
        print(f"[Judge] entity match failed: {e}")
        return {
            "accept": False,
            "confidence": "Low",
            "preferred_display_name": brand_name,
            "reason": f"Judge unavailable — refusing unsafe MCA match ({e})",
            "is_subsidiary_or_sister": True,
            "_error": str(e),
        }


def judge_research_report(
    *,
    website_url: str,
    domain: str,
    brand_name: str,
    site_excerpt: str,
    offerings_hint: str,
    report: dict,
) -> dict:
    """
    Validate / sanitize the research JSON. Drop wrong competitors, wrong people,
    and illogical fields. Only keep High/Medium confidence facts that fit the domain.
    """
    # Compact snapshot for judge (keep tokens low / fast)
    snap = {
        "company_profile": report.get("company_profile") or {},
        "products_services": report.get("products_services") or {},
        "market_analysis": {
            "industry": (report.get("market_analysis") or {}).get("industry"),
            "market_position": (report.get("market_analysis") or {}).get("market_position"),
        },
        "competitors": (report.get("competitors") or [])[:8],
        "leadership_team": (report.get("leadership_team") or [])[:8],
        "registry_intelligence": {
            "legal_name": (report.get("registry_intelligence") or {}).get("legal_name"),
            "cin": (report.get("registry_intelligence") or {}).get("cin"),
            "confidence": (report.get("registry_intelligence") or {}).get("confidence"),
            "directors": ((report.get("registry_intelligence") or {}).get("directors") or [])[:6],
        },
    }

    prompt = f"""You are an LLM-as-judge for B2B company intelligence.
Validate this research report against the website. REMOVE anything wrong, outdated-sounding without proof,
wrong-domain, or low-confidence garbage. Prefer empty / "Not publicly available" over wrong facts.

WEBSITE
- url: {website_url}
- domain: {domain}
- brand: {brand_name}
- site excerpt: {site_excerpt[:1200]}
- offerings hint: {offerings_hint[:500]}

REPORT SNAPSHOT
{json.dumps(snap)[:7000]}

RULES:
1. Competitors MUST be same industry / same work domain as the website. Drop cross-domain peers.
2. Do NOT include the company itself as a competitor.
3. Leadership/founders: keep ONLY if named on the company website or clear public sources in the report. Else clear the list.
4. market_position must be a real business summary — NEVER login-page text, cookie banners, or unrelated SaaS pages.
5. If a field is uncertain, set value to "Not publicly available" with confidence Low OR remove it.
6. Propose 3-6 REAL domain-specific competitors with short specific strengths/weaknesses (not generic filler).
7. Indian MCA / ZaubaCorp registry is disabled for this product. Always set drop_registry=true. Do not treat CIN/directors as required.
8. Return JSON ONLY:
{{
  "display_name": "...",
  "industry": {{"value":"...","confidence":"High|Medium|Low","source":"..."}},
  "competitors": [{{"name":"...","description":"...","strengths":"...","weaknesses":"...","threat_level":"High|Medium|Low","confidence":"Medium","source":"Judge-validated"}}],
  "leadership_keep": true/false,
  "drop_registry": true/false,
  "market_position": {{"value":"...","confidence":"Medium","source":"Website"}},
  "rejected_reasons": ["..."],
  "quality_score": 0-100,
  "summary": "one sentence on data trust"
}}
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Strict accuracy. Never invent people or revenue."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1600,
            json_mode=True,
            timeout=60.0,
        )
        return _parse_json(raw)
    except Exception as e:
        print(f"[Judge] report judge failed: {e}")
        return {
            "display_name": brand_name,
            "competitors": [],
            "leadership_keep": False,
            "drop_registry": True,
            "market_position": {"value": "Not publicly available", "confidence": "Low", "source": "Judge"},
            "rejected_reasons": [f"Judge failed: {e}"],
            "quality_score": 25,
            "summary": "Judge unavailable — stripped unsafe fields.",
            "_error": str(e),
        }


def is_junk_page_text(text: str, url: str = "") -> bool:
    """Heuristic filter for login walls / unrelated HR portals etc."""
    blob = f"{url} {text[:800]}".lower()
    junk_markers = [
        "login to keka", "continue with google", "continue with microsoft",
        "forgot password", "sign in to continue", "captcha",
        "academy.keka", "app.keka.com", "/login", "cookie consent",
    ]
    return any(m in blob for m in junk_markers)
