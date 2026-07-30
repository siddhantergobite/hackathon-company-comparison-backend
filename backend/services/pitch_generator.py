"""
Compare pitching company vs target company and generate outreach pitch.
"""
from __future__ import annotations

import json
import re
from typing import Any

from backend.services import llm as llm_client

MODEL = llm_client.AZURE_MODEL


def _val(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("value", "") or "")
    return str(field or "")


def _compact_target(target: dict) -> dict:
    co = target.get("company_profile") or {}
    meta = target.get("_meta") or {}
    contacts = target.get("contact_intelligence") or {}
    leadership = target.get("leadership_team") or []
    hiring = target.get("hiring_signals") or []
    prod = target.get("products_services") or {}
    sc = target.get("intelligence_score") or {}
    services = []
    for item in prod.get("primary_offerings") or []:
        if isinstance(item, dict):
            services.append(item.get("item") or item.get("value") or "")
        elif isinstance(item, str):
            services.append(item)
    return {
        "company_name": meta.get("company_name") or co.get("name") or "",
        "industry": _val(co.get("industry")),
        "description": _val(co.get("description")),
        "headquarters": _val(co.get("headquarters")),
        "employees": _val((target.get("employee_insights") or {}).get("total_employees")),
        "target_services": [s for s in services if s],
        "market_position": _val((target.get("market_analysis") or {}).get("market_position")),
        "leadership": leadership[:5],
        "contacts": (contacts.get("emails") or [])[:5],
        "phones": (contacts.get("phones") or [])[:5],
        "hiring_signals": hiring,
        "swot": target.get("swot_analysis") or {},
        "competitors": (target.get("competitors") or [])[:4],
        "content_gaps": _val((target.get("content_strategy") or {}).get("content_gap_opportunity")),
        "intelligence_summary": sc.get("summary", ""),
        "ai_conclusion": target.get("ai_conclusion", ""),
        "citations": (meta.get("citations") or [])[:10],
    }


def run(brochure: dict, target: dict) -> dict:
    pitcher = {
        "company_name": brochure.get("company_name", ""),
        "summary": brochure.get("summary", ""),
        "services": brochure.get("services") or [],
        "industries": brochure.get("industries") or [],
        "case_studies": brochure.get("case_studies", ""),
        "contacts": brochure.get("contacts") or [],
    }
    tgt = _compact_target(target)

    prompt = f"""You are a senior B2B sales strategist. Compare what the pitching company offers against what the target company likely needs (based on hiring signals, profile, and public intelligence).

PITCHING COMPANY:
{json.dumps(pitcher, indent=2)}

TARGET COMPANY:
{json.dumps(tgt, indent=2)}

Return ONLY valid JSON:
{{
  "match_score": 75,
  "ai_conclusion": "One compelling sentence on what the target is likely building and why now is the right time to pitch",
  "signals_used": ["signal tag 1", "signal tag 2"],
  "matches": [
    {{
      "pitcher_offers": "service from pitching company",
      "target_needs": "inferred need with hiring evidence",
      "fit": "Strong match|Partial match|Unconfirmed",
      "citation_url": "url from hiring_signals or citations if relevant, else empty string"
    }}
  ],
  "email_draft": {{
    "to_name": "best POC name",
    "to_email": "email if known else empty",
    "to_title": "title",
    "from_name": "pitching company contact name",
    "from_email": "pitching company email if known",
    "subject": "concise subject line",
    "body_html": "email body with <p> tags, reference specific hiring signals and case studies, 150-250 words"
  }},
  "talking_points": ["bullet 1", "bullet 2", "bullet 3"]
}}

Rules:
- match_score 0-100 based on real overlap between pitcher services and target needs
- Use target_services, swot weaknesses/opportunities, and hiring_signals to infer needs
- Reference SPECIFIC hiring roles, SWOT gaps, and content_gaps where relevant
- Email must name the POC from contacts or phones if available; reference their industry and HQ
- Include POC phone in talking_points if available from phones[]
- Email must feel personal and cite 1-2 concrete facts (hiring count, project type, case study)
- Use authentic data only — do not invent client names beyond case_studies provided"""

    raw = llm_client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.35,
        max_tokens=3500,
        json_mode=True,
    )
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise RuntimeError("Failed to parse pitch generation response")
        result = json.loads(m.group())

    result["_meta"] = {
        "pitcher_company": pitcher.get("company_name"),
        "target_company": tgt.get("company_name"),
        "model_used": MODEL,
    }
    return result
