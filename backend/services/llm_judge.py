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


def _field_val(x) -> str:
    if isinstance(x, dict):
        v = x.get("value")
        if isinstance(v, dict):
            return str(v.get("text") or v.get("label") or v.get("name") or "")[:240]
        return str(v or "")[:240]
    return str(x or "")[:240]


def judge_research_report(
    *,
    website_url: str,
    domain: str,
    brand_name: str,
    site_excerpt: str,
    offerings_hint: str,
    report: dict,
    wikidata_hint: Optional[dict] = None,
) -> dict:
    """
    Validate / sanitize the research JSON. Drop wrong competitors, wrong people,
    unit-less finance, and illogical fields. Prefer empty over a confident wrong fact.
    """
    wd = wikidata_hint or {}
    mkt = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    fin = report.get("financial_data") if isinstance(report.get("financial_data"), dict) else {}
    snap = {
        "company_profile": {
            "name": (report.get("company_profile") or {}).get("name"),
            "description": _field_val((report.get("company_profile") or {}).get("description")),
            "headquarters": _field_val((report.get("company_profile") or {}).get("headquarters")),
            "industry": _field_val((report.get("company_profile") or {}).get("industry")),
            "annual_revenue": _field_val((report.get("company_profile") or {}).get("annual_revenue")),
        },
        "products": [
            (o.get("item") if isinstance(o, dict) else str(o))
            for o in ((report.get("products_services") or {}).get("primary_offerings") or [])[:6]
        ],
        "market_analysis": {
            "industry": _field_val(mkt.get("industry")),
            "market_position": _field_val(mkt.get("market_position")),
            "geographic_reach": _field_val(mkt.get("geographic_reach")),
        },
        "revenue_estimate": _field_val(fin.get("revenue_estimate")),
        "competitors": [
            {"name": c.get("name"), "description": (c.get("description") or "")[:160]}
            for c in (report.get("competitors") or [])[:8]
            if isinstance(c, dict)
        ],
        "leadership_team": [
            {
                "name": l.get("name"),
                "role": l.get("role"),
                "source": l.get("source"),
                "status": l.get("status"),
            }
            for l in (report.get("leadership_team") or [])[:8]
            if isinstance(l, dict)
        ],
        "wikidata_verified": {
            "matched": bool(wd.get("matched")),
            "ceo": wd.get("ceo") or [],
            "chair": wd.get("chair") or [],
            "founders": wd.get("founders") or [],
            "hq": wd.get("headquarters") or "",
            "revenue": wd.get("revenue") or "",
        },
    }

    prompt = f"""You are the LLM-as-judge for a production B2B company-intelligence product sold to clients.
Your job is AUTHENTICITY, not completeness. A missing field is better than a wrong field.
Never invent a CEO, revenue figure, or job count. Apply the same rules to every company (startup or Fortune 500).

WEBSITE
- url: {website_url}
- domain: {domain}
- brand: {brand_name}
- site excerpt: {site_excerpt[:1000]}
- offerings hint: {offerings_hint[:400]}

REPORT SNAPSHOT
{json.dumps(snap)[:7500]}

RULES:
1. Competitors MUST be same industry / same work as THIS website. Drop the company itself and cross-domain peers.
2. Leadership:
   - Keep CURRENT operating executives (CEO, MD, President, Chair, CFO, CTO, COO) when Wikidata or a clear public source names them.
   - Historical founders/cofounders may be kept ONLY with status "historical". They are NOT the business point of contact unless they are still CEO/MD/President.
   - Drop people who are directors of unrelated subsidiaries, or names that look like page chrome.
   - If Wikidata lists a CEO, that person MUST appear as current CEO. Do not substitute a cofounder.
3. geographic_reach.value MUST be a short human string (e.g. "Global" or "India and Middle East"). Never an object.
4. Revenue: keep ONLY if it has a currency AND a scale (million/billion/crore) or a 9+ digit amount. Reject stock prices like "$507.29". Prefer Wikidata revenue when present. Otherwise "Not publicly available".
5. market_position must be a real business summary — never login pages, cookie banners, or unrelated SaaS.
6. quality_score is AUTHENTICITY 0-100, NOT completeness. Penalize missing current CEO, unit-less revenue, and weak sources. Typical honest range is 45-85. Never 100 unless Wikidata+official site agree on identity, CEO, and HQ.
7. Indian MCA / ZaubaCorp is disabled. Always drop_registry=true.
8. Return JSON ONLY:
{{
  "display_name": "...",
  "industry": {{"value":"...","confidence":"High|Medium|Low","source":"..."}},
  "competitors": [{{"name":"...","description":"...","strengths":"...","weaknesses":"...","threat_level":"High|Medium|Low","confidence":"Medium","source":"Judge-validated"}}],
  "leadership": [{{"name":"...","role":"...","status":"current|historical","keep":true}}],
  "drop_people": ["names to remove"],
  "poc_name": "current CEO/MD/President or empty",
  "poc_title": "...",
  "geographic_reach": {{"value":"short string","confidence":"Medium","source":"..."}},
  "revenue_estimate": {{"value":"Not publicly available or scaled amount","confidence":"Low|Medium|High","source":"..."}},
  "leadership_keep": true/false,
  "drop_registry": true,
  "market_position": {{"value":"...","confidence":"Medium","source":"Website"}},
  "rejected_reasons": ["..."],
  "quality_score": 0-100,
  "summary": "one sentence on data trust — mention what was removed"
}}
"""
    try:
        raw = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. You are a strict authenticity judge. "
                        "Never invent people or revenue. Prefer empty over wrong. "
                        "quality_score is authenticity, never completeness."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2000,
            json_mode=True,
            timeout=70.0,
        )
        data = _parse_json(raw)
        data["drop_registry"] = True
        try:
            q = int(data.get("quality_score") or 40)
        except (TypeError, ValueError):
            q = 40
        data["quality_score"] = max(10, min(92, q))
        return data
    except Exception as e:
        print(f"[Judge] report judge failed: {e}")
        return {
            "display_name": brand_name,
            "competitors": [],
            "leadership": [],
            "drop_people": [],
            "poc_name": "",
            "poc_title": "",
            "leadership_keep": False,
            "drop_registry": True,
            "market_position": {"value": "Not publicly available", "confidence": "Low", "source": "Judge"},
            "rejected_reasons": [f"Judge failed: {e}"],
            "quality_score": 25,
            "summary": "Judge unavailable — stripped unsafe fields.",
            "_error": str(e),
        }


def judge_hiring_signals(
    *,
    company_name: str,
    domain: str,
    signals: list,
) -> dict:
    """Keep only openings where THIS company is the employer."""
    compact = []
    for h in (signals or [])[:12]:
        if not isinstance(h, dict):
            continue
        compact.append({
            "role": h.get("role"),
            "url": h.get("source_url"),
            "title": h.get("source_title"),
            "platform": h.get("platform"),
            "count": h.get("count"),
        })
    if not compact:
        return {"keep_urls": [], "drop_reasons": ["no signals"]}

    prompt = f"""You judge hiring signals for a company-intelligence product.
KEEP a row if the employer is exactly "{company_name}" (domain {domain}).
KEEP official careers pages, jobs.{{domain}}, LinkedIn /company/.../jobs, Naukri company job pages,
Indeed /cmp/ employer pages, Glassdoor employer job pages, and the company's own ATS.
DROP:
- keyword searches (product name + "jobs", e.g. "Microsoft 365 jobs in Pune")
- consultant / partner / reseller jobs at OTHER companies
- job-board homepages, ads, or "N job openings" SERP titles with no employer page
- LinkedIn keyword-search URLs (jobs/search?keywords=) that are not the company's page

SIGNALS
{json.dumps(compact)[:4000]}

Return JSON ONLY:
{{
  "keep_urls": ["https://..."],
  "drop_reasons": ["short reason for each drop"]
}}
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Keep this employer's LinkedIn, Naukri, Indeed, Glassdoor, and official careers pages. Drop other employers and keyword searches."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=700,
            json_mode=True,
            timeout=45.0,
        )
        data = _parse_json(raw)
        urls = data.get("keep_urls") or []
        data["keep_urls"] = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        return data
    except Exception as e:
        print(f"[Judge] hiring judge failed: {e}")
        return {"keep_urls": [], "drop_reasons": [f"judge failed: {e}"], "_error": str(e)}


def is_junk_page_text(text: str, url: str = "") -> bool:
    """Heuristic filter for login walls / unrelated HR portals etc."""
    blob = f"{url} {text[:800]}".lower()
    junk_markers = [
        "login to keka", "continue with google", "continue with microsoft",
        "forgot password", "sign in to continue", "captcha",
        "academy.keka", "app.keka.com", "/login", "cookie consent",
    ]
    return any(m in blob for m in junk_markers)
