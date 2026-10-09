"""
LLM-as-Judge — validate company-research facts before showing them.
Reject wrong legal entities, wrong directors, wrong-domain competitors,
and illogical scraped junk. Prefer silence over confident wrong answers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

from backend.services import llm as llm_client


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$", "", raw, flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in judge response")
    return json.loads(raw[start : end + 1])


def _phone_literal_in_text(phone: str, text: str) -> bool:
    """Require a complete phone-number token, not a digit substring match."""
    wanted = re.sub(r"\D", "", str(phone or ""))
    if len(wanted) < 7:
        return False
    for match in re.finditer(r"(?<!\d)\+?\d[\d\s()./-]{5,}\d(?!\d)", str(text or "")):
        if re.sub(r"\D", "", match.group(0)) == wanted:
            return True
    return False


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
            "_judge_available": False,
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
    public_evidence: Optional[list[dict]] = None,
    timeout: float = 70.0,
) -> dict:
    """
    Validate / sanitize the research JSON. Drop wrong competitors, wrong people,
    unit-less finance, and illogical fields. Prefer empty over a confident wrong fact.
    """
    wd = wikidata_hint or {}
    evidence_rows = []
    for row in (public_evidence or [])[:12]:
        if not isinstance(row, dict):
            continue
        source_url = str(row.get("url") or "").strip()
        if not source_url.startswith(("http://", "https://")):
            continue
        evidence_rows.append({
            "url": source_url,
            "title": str(row.get("title") or row.get("domain") or "Public source")[:160],
            "category": str(row.get("category") or "Public Web")[:60],
            "excerpt": str(row.get("text") or row.get("snippet") or row.get("excerpt") or "")[:700],
        })
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
        "financial_data": {
            key: _field_val(fin.get(key))
            for key in ("funding_status", "total_funding", "funding_stage", "profitability_status")
        },
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
        "swot_analysis": report.get("swot_analysis") or {},
        "risk_assessment": report.get("risk_assessment") or {},
        "recent_news": (report.get("recent_news") or [])[:6],
        "hiring_signals": [
            {"role": h.get("role"), "platform": h.get("platform"), "source_url": h.get("source_url")}
            for h in (report.get("hiring_signals") or [])[:8]
            if isinstance(h, dict)
        ],
        "contact_intelligence": {
            "emails": [
                {
                    "email": e.get("email"),
                    "person": e.get("person") or e.get("person_name") or e.get("name"),
                    "title": e.get("title") or e.get("role"),
                    "source": e.get("source"),
                }
                for e in ((report.get("contact_intelligence") or {}).get("emails") or [])[:8]
                if isinstance(e, dict)
            ],
            "phones": [
                {
                    "number": p.get("number"),
                    "person": p.get("person") or p.get("person_name") or p.get("name"),
                    "source": p.get("source"),
                }
                for p in ((report.get("contact_intelligence") or {}).get("phones") or [])[:8]
                if isinstance(p, dict)
            ],
            "public_point_of_contact": (report.get("contact_intelligence") or {}).get("public_point_of_contact") or {},
        },
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

PUBLIC WEB EVIDENCE (retrieved candidate sources; use URLs only from this list):
{json.dumps(evidence_rows, ensure_ascii=False)[:7000] or "[]"}

REPORT SNAPSHOT
{json.dumps(snap)[:7500]}

RULES:
1. Define the business domain from the website and retrieved public evidence. A competitor MUST sell a materially overlapping product or service to similar customers in an evidenced market. Drop the company itself, generic peer labels, and cross-domain peers. Return fewer than three if the evidence does not support three. Include an official domain only when a supplied source supports it, and include the supporting evidence URL.
2. Leadership:
   - Keep CURRENT operating executives (CEO, MD, President, Chair, CFO, CTO, COO) only when the same-company evidence or domain-matched Wikidata supports the person and role.
   - Treat CEO, Founder, Chairman, Chairperson, and board roles as separate claims. Never transfer a person from a similarly named company or a subsidiary.
   - Historical founders/cofounders may be kept ONLY with status "historical". They are NOT the business point of contact unless they are still CEO/MD/President.
   - Keep a Founder/cofounder claim only when the evidence identifies that person as a founder of THIS exact company; a person's fame or work in the same industry is not evidence.
   - Drop people who are directors of unrelated subsidiaries, or names that look like page chrome.
   - If Wikidata lists a CEO, that person MUST appear as current CEO. Do not substitute a cofounder.
   - If the evidence does not clearly identify a role, omit it. Do not fill a missing person from model memory.
3. geographic_reach.value MUST be a short human string (e.g. "Global" or "India and Middle East"). Never an object.
4. Revenue and funding: keep a value only when the exact company and value are supported by a supplied evidence excerpt/source URL. Revenue and funding totals also need a currency and scale (million/billion/crore) or a 9+ digit amount. Reject stock prices like "$507.29". Prefer domain-matched Wikidata revenue. Never infer funding stage or profitability. Otherwise use "Not publicly available".
5. market_position must be a real business summary — never login pages, cookie banners, or unrelated SaaS.
6. Review every supplied report section, including SWOT, risks, news, hiring, contacts, products, leadership, competitors, and finance. For SWOT and risk entries, retain only claims that point to a supplied source URL. Label strategic implications as analysis/inference, not fact. Do not create opportunities, threats, or a numeric overall risk level from generic industry assumptions.
7. Keep a news or event item only when a supplied public source clearly concerns this exact company and supports its date. A future date is valid only for a clearly identified event. Do not call an undated item “latest”; reject unrelated publication names and search-result noise.
8. quality_score is AUTHENTICITY 0-100, NOT completeness. Penalize missing current CEO, unit-less revenue, weak sources, and cross-domain people/competitors. Typical honest range is 45-85. Never 100 unless Wikidata+official site agree on identity, CEO, and HQ.
9. Indian MCA / ZaubaCorp is disabled. Always drop_registry=true.
10. Return JSON ONLY:
{{
  "display_name": "...",
  "industry": {{"value":"...","confidence":"High|Medium|Low","source":"..."}},
  "competitors": [{{"name":"...","description":"...","strengths":"...","weaknesses":"...","official_domain":"... or empty","market_location":"... or empty","overlap_reason":"...","evidence_url":"exact URL from PUBLIC WEB EVIDENCE","threat_level":"High|Medium|Low","confidence":"High|Medium|Low","source":"source domain/category"}}],
  "leadership": [{{"name":"...","role":"...","status":"current|historical","keep":true}}],
  "drop_people": ["names to remove"],
  "poc_name": "current CEO/MD/President or empty",
  "poc_title": "...",
  "geographic_reach": {{"value":"short string","confidence":"Medium","source":"..."}},
  "revenue_estimate": {{"value":"Not publicly available or scaled amount","confidence":"Low|Medium|High","source":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE or empty"}},
  "financial_intelligence": {{
    "funding_status": {{"value":"... or Not publicly available","source_url":"exact URL from PUBLIC WEB EVIDENCE or empty","confidence":"Low|Medium|High"}},
    "total_funding": {{"value":"scaled amount or Not publicly available","source_url":"exact URL from PUBLIC WEB EVIDENCE or empty","confidence":"Low|Medium|High"}},
    "funding_stage": {{"value":"... or Not publicly available","source_url":"exact URL from PUBLIC WEB EVIDENCE or empty","confidence":"Low|Medium|High"}},
    "profitability_status": {{"value":"... or Not publicly available","source_url":"exact URL from PUBLIC WEB EVIDENCE or empty","confidence":"Low|Medium|High"}}
  }},
  "leadership_keep": true/false,
  "drop_registry": true,
  "market_position": {{"value":"...","confidence":"Medium","source":"Website"}},
  "swot_analysis": {{
    "strengths": [{{"point":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}],
    "weaknesses": [{{"point":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}],
    "opportunities": [{{"point":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"analysis","confidence":"High|Medium|Low"}}],
    "threats": [{{"point":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}]
  }},
  "risk_assessment": {{
    "overall_risk_level":"Low|Medium|High|Undetermined",
    "regulatory_risks":[{{"risk":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}],
    "competitive_risks":[{{"risk":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}],
    "operational_risks":[{{"risk":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}],
    "reputational_risks":[{{"risk":"...","source_url":"exact URL from PUBLIC WEB EVIDENCE","basis":"fact|analysis","confidence":"High|Medium|Low"}}]
  }},
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
            max_tokens=3400,
            json_mode=True,
            timeout=timeout,
        )
        data = _parse_json(raw)
        data["drop_registry"] = True
        try:
            q = int(data.get("quality_score") or 40)
        except (TypeError, ValueError):
            q = 40
        data["quality_score"] = max(10, min(92, q))
        data["_judge_available"] = True
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
            "swot_analysis": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
            "risk_assessment": {"overall_risk_level": "Undetermined"},
            "leadership_keep": False,
            "drop_registry": True,
            "market_position": {"value": "Not publicly available", "confidence": "Low", "source": "Judge"},
            "rejected_reasons": [f"Judge failed: {e}"],
            "quality_score": 25,
            "summary": "Judge unavailable — stripped unsafe fields.",
            "_judge_available": False,
            "_error": str(e),
        }


def judge_ai_profile(
    *,
    website_url: str,
    domain: str,
    company_name: str,
    candidate: dict,
    evidence: list[dict],
    existing_leaders: Optional[list] = None,
    timeout: float = 90.0,
) -> dict:
    """Judge the dedicated AI knowledge fallback at fact level.

    The normal report judge is intentionally conservative and only sees the
    main report snapshot. This pass receives a candidate generated from model
    knowledge plus fetched pages and search snippets. It keeps those evidence
    levels distinct. Email and phone values remain literal-evidence-only.
    """
    candidate = candidate if isinstance(candidate, dict) else {}
    rows = []
    allowed_urls = set()
    for row in (evidence or [])[:36]:
        if not isinstance(row, dict):
            continue
        href = str(row.get("url") or "").strip()
        if not href.startswith(("http://", "https://")):
            continue
        low = href.lower()
        if any(x in low for x in ("chatgpt.com", "chat.openai.com", "openai.com/chat", "/login", "/signin")):
            continue
        allowed_urls.add(href)
        rows.append({
            "url": href,
            "title": str(row.get("title") or "")[:180],
            "source": str(row.get("source") or "Public web")[:100],
            "snippet": str(row.get("snippet") or row.get("text") or "")[:900],
            "retrieved": row.get("retrieved") is not False,
        })

    existing = [
        {"name": l.get("name"), "role": l.get("role"), "status": l.get("status")}
        for l in (existing_leaders or [])[:8]
        if isinstance(l, dict) and l.get("name")
    ]

    prompt = f"""You are a second-pass fact judge for a company-intelligence product.

The first model produced a candidate profile using public web evidence and its
general knowledge.  Judge each claim for THIS exact company, not a similarly
named company or a subsidiary.  You may keep a well-known public executive from
model knowledge when the identity and role are strongly consistent, but label it
model-knowledge-reviewed rather than verified.  A model answer is never a source.

COMPANY
- name: {company_name}
- website: {website_url}
- domain: {domain}

EXISTING EVIDENCE
{json.dumps(rows, ensure_ascii=False)[:12000] or "[]"}

EXISTING LEADERS (context)
{json.dumps(existing, ensure_ascii=False)[:1800]}

CANDIDATE PROFILE
{json.dumps(candidate, ensure_ascii=False)[:7000]}

RULES
1. Keep current CEO, CTO, COO, CFO, President, Chair, Founder/Co-founder,
   Managing Director, or another named senior leader only for this exact company.
2. Founders may be historical; do not turn a historical founder into a current
   operating executive or point of contact.
3. A name/title not literally present in the evidence may still be retained only
   as model-knowledge-reviewed when it is a well-known public fact and the
   company identity is unambiguous. Use Medium confidence at most in that case.
   If a name appears only in an unfetched search snippet, label it
   search-snippet-supported; do not call the linked page fetched or verified.
4. Keep email or phone ONLY when the exact value appears in the evidence. Never
   infer an address pattern, guess a number, or reveal private contact details.
5. A point of contact must be a current operating executive or an explicitly
   public business contact. Prefer a current leader over a historical founder.
6. Headquarters and founding year may use model knowledge only when the company
   identity is unambiguous; mark those facts model-knowledge-reviewed.
7. Drop unsupported, low-confidence, wrong-company, duplicate, and page-chrome
   claims. Prefer an empty value to a confident error.
8. Products/services, market position, and geographic reach may be retained from
   model knowledge only as Medium-confidence suggestions. They are not verified
   claims unless a supplied evidence record supports them.
9. Competitor candidates must overlap in business domain and operating market.
   Keep a candidate without evidence only as a model-knowledge suggestion; do
   not present it as a verified competitor. Never guess an official domain.
10. Do not infer recent news, current hiring, revenue/funding, emails, or phone
    numbers from model memory. Those require literal current public evidence.

Return ONLY JSON:
{{
  "overall_score": 0,
  "summary": "one short sentence explaining what was kept and what remains unverified",
  "leadership": [{{
    "name": "Full Name",
    "role": "CEO",
    "status": "current|historical",
    "keep": true,
    "confidence": "High|Medium|Low",
    "verification_status": "evidence-verified|search-snippet-supported|model-knowledge-reviewed",
    "source_urls": ["exact URLs from EXISTING EVIDENCE"],
    "reason": "short reason"
  }}],
  "point_of_contact": {{
    "keep": true,
    "name": "",
    "title": "",
    "email": "",
    "phone": "",
    "confidence": "High|Medium|Low",
    "verification_status": "evidence-verified|search-snippet-supported|model-knowledge-reviewed",
    "source_urls": [],
    "reason": "short reason"
  }},
  "headquarters": {{
    "keep": true,
    "value": "city, country",
    "confidence": "High|Medium|Low",
    "verification_status": "evidence-verified|search-snippet-supported|model-knowledge-reviewed",
    "source_urls": [],
    "reason": "short reason"
  }},
  "founded": {{"keep":true,"value":"YYYY","confidence":"High|Medium|Low","verification_status":"evidence-verified|search-snippet-supported|model-knowledge-reviewed","source_urls":[],"reason":"short reason"}},
  "business_profile": {{
    "products_services": [{{"item":"...","keep":true,"confidence":"High|Medium|Low","verification_status":"evidence-verified|search-snippet-supported|model-knowledge-reviewed","source_urls":[],"reason":"..."}}],
    "market_position": {{"keep":true,"value":"...","confidence":"High|Medium|Low","verification_status":"evidence-verified|search-snippet-supported|model-knowledge-reviewed","source_urls":[],"reason":"..."}},
    "geographic_reach": {{"keep":true,"value":"...","confidence":"High|Medium|Low","verification_status":"evidence-verified|search-snippet-supported|model-knowledge-reviewed","source_urls":[],"reason":"..."}},
    "competitor_candidates": [{{"name":"...","official_domain":"... or empty","market_location":"... or empty","overlap_reason":"...","keep":true,"confidence":"High|Medium|Low","verification_status":"evidence-verified|search-snippet-supported|model-knowledge-reviewed","source_urls":[],"reason":"..."}}]
  }}
}}
"""

    try:
        raw = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Be strict about company identity. "
                        "Never invent emails or phones. Separate evidence from model knowledge."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=2600,
            json_mode=True,
            timeout=timeout,
            reasoning_effort="low",
        )
        data = _parse_json(raw)
    except Exception as e:
        print(f"[Judge] AI profile judge failed: {e}")
        return {
            "overall_score": 0,
            "summary": "AI profile judge unavailable; no fallback facts were promoted.",
            "leadership": [],
            "point_of_contact": {},
            "headquarters": {},
            "founded": {},
            "_judge_available": False,
            "_error": str(e),
        }

    def _score(value, default=0):
        try:
            n = float(value)
        except (TypeError, ValueError):
            return default
        if 0 < n <= 1:
            n *= 100
        return max(0, min(100, int(round(n))))

    def _confidence(value):
        value = str(value or "Medium").strip().title()
        return value if value in {"High", "Medium", "Low"} else "Medium"

    def _urls(value):
        return [u for u in (value or []) if isinstance(u, str) and u in allowed_urls][:4]

    def _keep(value) -> bool:
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "reject", "drop"}
        return bool(value)

    def _matching_evidence_rows(name):
        needle = str(name or "").strip().lower()
        if not needle:
            return []
        return [r for r in rows if needle in f"{r['title']} {r['snippet']}".lower()]

    def _evidence_urls_for(name):
        return [r["url"] for r in _matching_evidence_rows(name)][:3]

    def _evidence_status(matches):
        if any(row.get("retrieved") for row in matches):
            return "evidence-verified"
        if matches:
            return "search-snippet-supported"
        return "model-knowledge-reviewed"

    leaders = []
    for row in data.get("leadership") or []:
        if not isinstance(row, dict) or not _keep(row.get("keep")):
            continue
        name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip(" ,;.")
        role = re.sub(r"\s+", " ", str(row.get("role") or "Leadership")).strip(" ,;.")
        if not name or len(name.split()) < 2 or len(name) > 90 or len(role) > 90:
            continue
        confidence = _confidence(row.get("confidence"))
        score = _score(row.get("score"), 65 if confidence != "Low" else 35)
        if confidence == "Low" or score < 55:
            continue
        name_matches = _matching_evidence_rows(name)
        evidence_hit = bool(name_matches)
        matching_urls = {match["url"] for match in name_matches}
        urls = [u for u in _urls(row.get("source_urls")) if u in matching_urls]
        status = str(row.get("verification_status") or "").strip().lower()
        if evidence_hit:
            status = _evidence_status(name_matches)
            urls = urls or _evidence_urls_for(name)
        else:
            status = "model-knowledge-reviewed"
            confidence = "Medium" if confidence == "High" else confidence
        if status != "evidence-verified":
            confidence = "Medium" if confidence == "High" else confidence
        leaders.append({
            "name": name,
            "role": role,
            "status": "historical" if str(row.get("status") or "").lower() == "historical" else "current",
            "confidence": confidence,
            "verification_status": status,
            "verification_score": score,
            "source_urls": urls,
            "reason": str(row.get("reason") or "Reviewed by the AI profile judge")[:260],
        })

    poc = data.get("point_of_contact") or data.get("poc") or {}
    if not isinstance(poc, dict) or not _keep(poc.get("keep")):
        poc = {}
    else:
        name = re.sub(r"\s+", " ", str(poc.get("name") or "")).strip(" ,;.")
        title = re.sub(r"\s+", " ", str(poc.get("title") or "")).strip(" ,;.")
        email = str(poc.get("email") or "").strip().lower()
        phone = str(poc.get("phone") or "").strip()
        name_matches = _matching_evidence_rows(name)
        email_matches = [
            row for row in rows
            if email and email in f"{row['title']} {row['snippet']}".lower()
        ]
        phone_matches = [
            row for row in rows
            if phone and _phone_literal_in_text(phone, f"{row['title']} {row['snippet']}")
        ]
        if not email_matches:
            email = ""
        if not phone_matches:
            phone = ""
        # Do not tie a model-known executive to a generic public mailbox or
        # phone. Retain a contact name only when that name itself is in source
        # text; otherwise keep any literal contact detail anonymous.
        if not name_matches:
            name, title = "", ""
        relevant_rows = name_matches if name else (email_matches + phone_matches)
        matching_urls = {row["url"] for row in relevant_rows}
        matching_rows = relevant_rows
        if not matching_rows:
            poc = {}
        else:
            conf = _confidence(poc.get("confidence"))
            score = _score(poc.get("score"), 65 if conf != "Low" else 35)
            if conf == "Low" or score < 55 or not (name or email or phone):
                poc = {}
            else:
                status = _evidence_status(matching_rows)
                if status != "evidence-verified":
                    conf = "Medium" if conf == "High" else conf
                urls = [u for u in _urls(poc.get("source_urls")) if u in matching_urls]
                urls = urls or list(matching_urls)[:4]
                poc = {
                    "name": name,
                    "title": title,
                    "email": email,
                    "phone": phone,
                    "confidence": conf,
                    "verification_status": status,
                    "verification_score": score,
                    "source_urls": urls,
                    "reason": str(poc.get("reason") or "Reviewed by the AI profile judge")[:260],
                }

    def _fact(value):
        if not isinstance(value, dict) or not _keep(value.get("keep")):
            return {}
        text = re.sub(r"\s+", " ", str(value.get("value") or "")).strip(" ,;")
        if not text or len(text) > 180:
            return {}
        conf = _confidence(value.get("confidence"))
        score = _score(value.get("score"), 65 if conf != "Low" else 35)
        if conf == "Low" or score < 55:
            return {}
        fact_matches = _matching_evidence_rows(text) if len(text) >= 5 else []
        matching_urls = {match["url"] for match in fact_matches}
        urls = [u for u in _urls(value.get("source_urls")) if u in matching_urls]
        urls = urls or _evidence_urls_for(text)
        evidence_hit = bool(fact_matches and urls)
        status = _evidence_status(fact_matches) if evidence_hit else "model-knowledge-reviewed"
        if status != "evidence-verified":
            conf = "Medium" if conf == "High" else conf
        return {
            "value": text,
            "confidence": conf,
            "verification_status": status,
            "verification_score": score,
            "source_urls": urls,
            "reason": str(value.get("reason") or "Reviewed by the AI profile judge")[:260],
        }

    business = data.get("business_profile") if isinstance(data.get("business_profile"), dict) else {}
    products = []
    seen_products = set()
    for row in business.get("products_services") or []:
        if not isinstance(row, dict) or not _keep(row.get("keep")):
            continue
        item = re.sub(r"\s+", " ", str(row.get("item") or row.get("value") or "")).strip(" ,;.")
        if not item or len(item) > 120 or item.lower() in seen_products:
            continue
        conf = _confidence(row.get("confidence"))
        if conf == "Low":
            continue
        item_matches = _matching_evidence_rows(item) if len(item) >= 5 else []
        matching_urls = {match["url"] for match in item_matches}
        urls = [u for u in _urls(row.get("source_urls")) if u in matching_urls]
        urls = urls or _evidence_urls_for(item)
        evidence_hit = bool(item_matches and urls)
        status = _evidence_status(item_matches) if evidence_hit else "model-knowledge-reviewed"
        if status != "evidence-verified":
            conf = "Medium"
        products.append({
            "item": item,
            "confidence": conf,
            "verification_status": status,
            "source_urls": urls,
            "reason": str(row.get("reason") or "Reviewed by the AI profile judge")[:220],
        })
        seen_products.add(item.lower())

    competitor_candidates = []
    seen_competitors = set()
    for row in business.get("competitor_candidates") or []:
        if not isinstance(row, dict) or not _keep(row.get("keep")):
            continue
        name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip(" ,;.")
        if not name or len(name) > 90 or name.lower() in seen_competitors:
            continue
        conf = _confidence(row.get("confidence"))
        if conf == "Low":
            continue
        name_matches = _matching_evidence_rows(name)
        matching_urls = {match["url"] for match in name_matches}
        urls = [u for u in _urls(row.get("source_urls")) if u in matching_urls]
        urls = urls or _evidence_urls_for(name)
        evidence_hit = bool(name_matches and urls)
        status = _evidence_status(name_matches) if evidence_hit else "model-knowledge-reviewed"
        if status != "evidence-verified":
            conf = "Medium"
        official_domain = re.sub(r"^https?://|^www\.", "", str(row.get("official_domain") or "").strip(), flags=re.I).strip("/ ").lower()
        evidence_hosts = {
            urlparse(source_url).netloc.lower().removeprefix("www.")
            for source_url in urls if urlparse(source_url).netloc
        }
        if official_domain and not any(
            official_domain == host or host.endswith("." + official_domain) or official_domain.endswith("." + host)
            for host in evidence_hosts
        ):
            official_domain = ""
        competitor_candidates.append({
            "name": name,
            "official_domain": official_domain,
            "market_location": str(row.get("market_location") or "")[:100],
            "overlap_reason": str(row.get("overlap_reason") or "")[:220],
            "confidence": conf,
            "verification_status": status,
            "source_urls": urls,
            "reason": str(row.get("reason") or "Reviewed by the AI profile judge")[:220],
        })
        seen_competitors.add(name.lower())

    business_profile = {
        "products_services": products[:8],
        "market_position": _fact(business.get("market_position")),
        "geographic_reach": _fact(business.get("geographic_reach")),
        "competitor_candidates": competitor_candidates[:4],
    }

    score = _score(data.get("overall_score") or data.get("quality_score"), 0)
    return {
        "overall_score": score,
        "summary": str(data.get("summary") or "AI profile facts were reviewed for company identity and evidence.")[:500],
        "leadership": leaders[:10],
        "point_of_contact": poc,
        "headquarters": _fact(data.get("headquarters")),
        "founded": _fact(data.get("founded")),
        "business_profile": business_profile,
        "_judge_available": True,
    }


def judge_hiring_signals(
    *,
    company_name: str,
    domain: str,
    signals: list,
    timeout: float = 45.0,
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
            timeout=timeout,
        )
        data = _parse_json(raw)
        urls = data.get("keep_urls") or []
        data["keep_urls"] = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        return data
    except Exception as e:
        print(f"[Judge] hiring judge failed: {e}")
        return {"keep_urls": [], "drop_reasons": [f"judge failed: {e}"], "_error": str(e)}


def judge_public_point_of_contact(
    *,
    website_url: str,
    domain: str,
    company_name: str,
    candidate: dict,
    evidence: list[dict],
    existing_leaders: Optional[list] = None,
    timeout: float = 50.0,
) -> dict:
    """Verify a public business contact before it is added to a report.

    The candidate is deliberately treated as untrusted model output.  The
    judge may keep a name/title only when the supplied public evidence supports
    the exact company and role.  Email addresses and phone numbers must be
    explicitly present in that evidence; they are never generated from a name
    or a domain pattern.
    """
    candidate = candidate if isinstance(candidate, dict) else {}
    rows = []
    allowed_urls = set()
    for row in (evidence or [])[:16]:
        if not isinstance(row, dict):
            continue
        href = str(row.get("url") or "").strip()
        if not href.startswith(("http://", "https://")):
            continue
        low = href.lower()
        if any(x in low for x in ("chatgpt.com", "chat.openai.com", "openai.com/chat")):
            continue
        allowed_urls.add(href)
        rows.append({
            "url": href,
            "title": str(row.get("title") or "")[:180],
            "source": str(row.get("source") or "Public web")[:80],
            "snippet": str(row.get("snippet") or row.get("text") or "")[:700],
            "retrieved": row.get("retrieved") is not False,
        })

    leaders = [
        {"name": l.get("name"), "role": l.get("role"), "source": l.get("source")}
        for l in (existing_leaders or [])[:8]
        if isinstance(l, dict) and l.get("name")
    ]
    prompt = f"""You are the final public-contact authenticity judge for a company-intelligence product.

The candidate below may be an answer produced from model knowledge. It is NOT evidence.
Keep it only when the supplied public evidence supports the same company at {domain}.
This product may show public business contacts only; never reveal confidential, private,
non-public, or inferred personal contact information.

COMPANY
- name: {company_name}
- official website: {website_url}
- domain: {domain}

CANDIDATE (untrusted)
{json.dumps(candidate, ensure_ascii=False)[:1800]}

EXISTING LEADERS (context only)
{json.dumps(leaders, ensure_ascii=False)[:1600]}

PUBLIC EVIDENCE
{json.dumps(rows, ensure_ascii=False)[:8500] or "[]"}

STRICT RULES
1. The evidence must refer to this exact company, not a similarly named company, customer,
   subsidiary, recruiter, or unrelated person.
2. A name/title is acceptable only when the evidence supports that person as a current
   CEO, Managing Director, President, Chair, Founder/Owner, or official business contact.
   Historical founders are not current contacts unless the evidence says they still run it.
3. Keep an email or phone number only if that exact value appears in the public evidence.
   Never infer an email pattern, guess a phone number, or turn a private personal detail
   into a contact. Prefer an official company-domain or official company-page contact.
4. A model answer alone is not a source. An unfetched search snippet can locate a
   candidate, but cannot verify a point of contact. Require a fetched public page.
5. Return only URLs present in PUBLIC EVIDENCE. Never return ChatGPT/OpenAI/login URLs.

Return JSON only:
{{
  "accept": true,
  "name": "current public contact name or empty",
  "title": "current role or empty",
  "email": "exact public business email or empty",
  "phone": "exact public business phone or empty",
  "source_urls": ["https://..."],
  "confidence": "High|Medium|Low",
  "reason": "one short evidence-based sentence"
}}
"""
    try:
        raw = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Reject unsupported or private contact data. "
                        "Public evidence beats model memory."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=700,
            json_mode=True,
            timeout=timeout,
            reasoning_effort="low",
        )
        data = _parse_json(raw)
        data["accept"] = bool(data.get("accept"))
        data["source_urls"] = [
            u for u in (data.get("source_urls") or [])
            if isinstance(u, str) and u in allowed_urls
        ]
        conf = data.get("confidence") or "Low"
        if isinstance(conf, (int, float)):
            conf = "High" if float(conf) >= 0.75 else ("Medium" if float(conf) >= 0.5 else "Low")
        data["confidence"] = str(conf)

        fetched_rows = [row for row in rows if row.get("retrieved")]
        evidence_text = "\n".join(
            f"{r.get('title', '')} {r.get('snippet', '')}" for r in fetched_rows
        ).lower()
        # A strict deterministic backstop for the fields most likely to be
        # hallucinated by a model.  The judge cannot approve values that were
        # not literally present in the evidence sent to it.
        email = str(data.get("email") or "").strip().lower()
        if email and email not in evidence_text:
            data["email"] = ""
        phone = str(data.get("phone") or "").strip()
        if phone and not _phone_literal_in_text(phone, evidence_text):
            data["phone"] = ""
        name = str(data.get("name") or "").strip()
        if name and name.lower() not in evidence_text:
            data["name"] = ""
            data["title"] = ""
            name = ""
        if name:
            if data.get("email") and not any(
                name.lower() in f"{row.get('title', '')} {row.get('snippet', '')}".lower()
                and str(data["email"]).lower() in f"{row.get('title', '')} {row.get('snippet', '')}".lower()
                for row in fetched_rows
            ):
                data["email"] = ""
            if data.get("phone") and not any(
                name.lower() in f"{row.get('title', '')} {row.get('snippet', '')}".lower()
                and _phone_literal_in_text(data["phone"], f"{row.get('title', '')} {row.get('snippet', '')}")
                for row in fetched_rows
            ):
                data["phone"] = ""
        retained_fields = [str(data.get(k) or "").strip().lower() for k in ("name", "email")]
        relevant_urls = {
            row["url"] for row in fetched_rows
            if any(
                field and field in f"{row.get('title', '')} {row.get('snippet', '')}".lower()
                for field in retained_fields
            ) or (
                data.get("phone")
                and _phone_literal_in_text(data.get("phone"), f"{row.get('title', '')} {row.get('snippet', '')}")
            )
        }
        data["source_urls"] = [u for u in data.get("source_urls") or [] if u in relevant_urls]
        if not data["source_urls"] and relevant_urls:
            data["source_urls"] = list(relevant_urls)[:4]
        if data["accept"] and not data["source_urls"]:
            data["accept"] = False
            data["reason"] = "No usable public source was returned by the judge"
        if data["accept"] and not any(
            str(data.get(k) or "").strip() for k in ("name", "email", "phone")
        ):
            data["accept"] = False
            data["reason"] = "The public evidence did not contain a usable contact"
        data["_judge_available"] = True
        return data
    except Exception as e:
        print(f"[Judge] public contact judge failed: {e}")
        return {
            "accept": False,
            "source_urls": [],
            "confidence": "Low",
            "reason": f"Contact judge unavailable — refusing unsafe contact ({e})",
            "_judge_available": False,
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
