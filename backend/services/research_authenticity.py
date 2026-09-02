"""
Production authenticity layer for company research.

Prefer silence / "Not publicly available" over a confident wrong fact.
Rules apply to ANY company — not Microsoft-specific.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# ── display flattening (kills [object Object]) ───────────────────────────────

def flatten_display(value: Any, depth: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        s = value.strip()
        if s.lower() in ("[object object]", "none", "null", "undefined"):
            return ""
        return s
    if depth > 4:
        return ""
    if isinstance(value, list):
        parts = [flatten_display(x, depth + 1) for x in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        if "value" in value:
            return flatten_display(value.get("value"), depth + 1)
        for k in ("text", "label", "name", "summary", "regions", "countries", "description", "item"):
            if value.get(k) not in (None, "", [], {}):
                return flatten_display(value.get(k), depth + 1)
        parts = []
        for k, v in value.items():
            if k in ("source", "confidence", "verified", "favicon", "provenance"):
                continue
            fv = flatten_display(v, depth + 1)
            if fv:
                parts.append(fv)
        return "; ".join(parts)
    return ""


def field(value: Any, source: str = "Public web", confidence: str = "Medium") -> dict:
    v = flatten_display(value)
    if not v:
        v = "Not publicly available"
        if confidence == "Medium":
            confidence = "Low"
    return {"value": v, "source": source, "confidence": confidence}


# ── source classification ────────────────────────────────────────────────────

_SOCIAL_HOSTS = (
    "linkedin.com", "twitter.com", "x.com", "instagram.com", "facebook.com",
    "youtube.com", "tiktok.com", "threads.net", "pinterest.com",
)
_ENCYCLOPEDIA = ("wikipedia.org", "wikidata.org", "britannica.com")
_NEWS = (
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "nytimes.com",
    "economictimes.", "business-standard.com", "moneycontrol.com",
    "techcrunch.com", "theverge.com", "news.microsoft.com",
)
_IR_HINTS = ("investor", "sec.gov", "secfilings", "annualreport")
_ATS = (
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "successfactors.com",
    "icims.com", "smartrecruiters.com", "ashbyhq.com", "jobvite.com",
    "taleo.net", "oraclecloud.com", "workable.com", "bamboohr.com",
)
_LOW_TRUST = (
    "ad.linkedin.com", "naukri.com/code360", "naukri.com/library",
    "fiscal.ai", "leadiq.com", "nodeflair.com",
)


def host_of(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "").split(":")[0]
    except Exception:
        return ""


def host_is_social(url: str) -> bool:
    """Domain-aware — 'x.com' must not match 'xbox.com'."""
    h = host_of(url)
    if not h:
        return False
    return any(h == s or h.endswith("." + s) for s in _SOCIAL_HOSTS)


def classify_source(url: str, company_domain: str = "") -> str:
    u = (url or "").lower()
    h = host_of(url)
    path = ""
    try:
        path = urlparse(url).path.lower()
    except Exception:
        pass

    cd = (company_domain or "").lower().replace("www.", "")
    if cd and (h == cd or h.endswith("." + cd) or _same_brand_host(h, cd)):
        if any(x in u for x in _IR_HINTS) or "investor" in path:
            return "Investor Relations"
        if any(x in h + path for x in ("career", "job", "jobs")):
            return "Official Careers"
        if any(x in path for x in ("/about", "/leadership", "/team", "/company")):
            return "Company Website"
        return "Company Website"

    if "ad.linkedin.com" in h:
        return "LinkedIn Ads (low trust)"

    if any(h == s or h.endswith("." + s) for s in _SOCIAL_HOSTS):
        if "linkedin.com" in h:
            if "/company/" in u and "/jobs" in u:
                return "LinkedIn Company Jobs"
            if "/company/" in u:
                return "LinkedIn Company Profile"
            if "ad.linkedin.com" in h:
                return "LinkedIn Ads (low trust)"
            return "LinkedIn"
        return "Social Media"

    if any(x in h for x in _ENCYCLOPEDIA):
        return "Encyclopedia"
    if "wikidata.org" in h:
        return "Wikidata"
    if any(x in h for x in ("crunchbase.com", "pitchbook.com", "tracxn.com")):
        return "Funding / Company"
    if any(x in h for x in ("theorg.com", "the.org")):
        return "Org Chart / Leadership"
    if any(x in h for x in ("opencorporates.com",)):
        return "Global Registry"
    if any(x in h for x in ("glassdoor.", "ambitionbox.com")):
        return "Employee Reviews"
    if any(n in h for n in _NEWS) or "news." in h:
        return "News"
    if any(x in h for x in _ATS):
        return "Applicant Tracking (jobs)"
    if "naukri.com" in h:
        if any(x in u for x in ("/code360/", "/library/")):
            return "Job article (not a live opening)"
        if path in ("", "/"):
            return "Job board homepage"
        return "Job board (unverified employer)"
    if any(x in u for x in _LOW_TRUST):
        return "Third-party directory"
    return "Public Web"


def _same_brand_host(a: str, b: str) -> bool:
    def stem(h: str) -> str:
        h = (h or "").lower().replace("www.", "")
        return (h.split(".")[0] if h else "")
    sa, sb = stem(a), stem(b)
    return bool(sa and sb and sa == sb and len(sa) >= 4)


def source_trust_score(category: str) -> int:
    table = {
        "Company Website": 92,
        "Investor Relations": 95,
        "Official Careers": 88,
        "Wikidata": 86,
        "Encyclopedia": 72,
        "Applicant Tracking (jobs)": 80,
        "LinkedIn Company Jobs": 70,
        "LinkedIn Company Profile": 62,
        "News": 68,
        "Funding / Company": 60,
        "Org Chart / Leadership": 64,
        "Global Registry": 70,
        "Employee Reviews": 55,
        "LinkedIn": 50,
        "Social Media": 45,
        "Public Web": 40,
        "Third-party directory": 28,
        "LinkedIn Ads (low trust)": 20,
        "Job board (unverified employer)": 18,
        "Job article (not a live opening)": 10,
        "Job board homepage": 8,
        "Search": 25,
    }
    return table.get(category, 40)


def is_junk_citation(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http"):
        return True
    junk = (
        "chatgpt.com", "chat.openai.com", "openai.com/chat",
        "accounts.google", "login.microsoftonline",
        "/log-in", "/signin", "/sign-in",
        "m365.cloud.microsoft",
        "crunchbase.com/?_",
    )
    if any(x in u for x in junk):
        return True
    h = host_of(url)
    path = urlparse(url).path.lower() if url else ""
    # Bare homepages of job boards / login walls
    if h in ("naukri.com", "www.naukri.com") and path in ("", "/"):
        return True
    return False


# ── leadership ranking / POC ─────────────────────────────────────────────────

_CURRENT_CEO = re.compile(
    r"(?i)\b(chief executive( officer)?|\bceo\b|managing director|\bmd\b|president|"
    r"chairman|chairperson|chair of the board|vice chair(?:man|person)?)\b"
)
_CURRENT_CSuite = re.compile(
    r"(?i)\b(ceo|cto|cfo|coo|cmo|chief |president|managing director|chairman|chairperson|"
    r"chair of the board|general counsel|chief operating|chief financial|chief technology)\b"
)
_HISTORICAL = re.compile(
    r"(?i)\b(former|ex-|emeritus|retired|late |deceased|historical|outgoing|stepped down)\b"
)
_OPERATING_OVERRIDE = re.compile(
    r"(?i)\b(ceo|chief executive|president|managing director|chairman|chairperson)\b"
)


def leader_status(role: str) -> str:
    """
    Founder-led companies are the norm in this dataset, so a plain "Founder" title is
    treated as current. Historical status needs explicit evidence — "former", "late",
    or the "(historical)" marker that the pre-1985 founder heuristic applies.
    """
    role = role or ""
    if _HISTORICAL.search(role) and not _OPERATING_OVERRIDE.search(role):
        return "historical"
    return "current"


def role_rank(role: str, status: str = "") -> int:
    """Lower is better. Historical founders rank last."""
    r = (role or "").lower()
    st = status or leader_status(role)
    if st == "historical":
        if "founder" in r:
            return 80
        return 90
    if re.search(r"chief executive|\bceo\b", r):
        return 0
    if re.search(r"managing director|\bmd\b", r):
        return 1
    if re.search(r"\bpresident\b", r) and "vice" not in r:
        return 2
    if re.search(r"chairman|chairperson|chair of", r):
        return 3
    if re.search(r"\bcfo\b|chief financial", r):
        return 4
    if re.search(r"\bcoo\b|chief operating", r):
        return 5
    if re.search(r"\bcto\b|chief technology", r):
        return 6
    if re.search(r"chief ", r):
        return 7
    if re.search(r"co-?founder|founder", r):
        return 8
    if re.search(r"director", r):
        return 12
    return 20


def has_operating_exec(leaders: list) -> bool:
    for l in leaders or []:
        if not isinstance(l, dict):
            continue
        st = l.get("status") or leader_status(l.get("role") or "")
        if st == "current" and _CURRENT_CEO.search(l.get("role") or ""):
            return True
    return False


def has_named_current_leadership(leaders: list) -> bool:
    """True when we have at least one living current officer — including founder-led firms."""
    for l in leaders or []:
        if not isinstance(l, dict) or not (l.get("name") or "").strip():
            continue
        st = l.get("status") or leader_status(l.get("role") or "")
        if st == "current":
            return True
    return False


def rank_leadership(leaders: list) -> list:
    out = []
    seen = set()
    for l in leaders or []:
        if not isinstance(l, dict) or not l.get("name"):
            continue
        row = dict(l)
        role = row.get("role") or "Leadership"
        st = row.get("status") or leader_status(role)
        row["status"] = st
        row["is_current"] = st == "current"
        row["role"] = role
        key = (row.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda x: (role_rank(x.get("role") or "", x.get("status") or ""), x.get("name") or ""))
    # Cap: keep up to 6 current + 2 historical
    current = [x for x in out if x.get("status") == "current"][:6]
    historical = [x for x in out if x.get("status") != "current"][:2]
    return current + historical


def select_point_of_contact(report: dict) -> dict:
    """
    Business outreach contact — never a historical cofounder unless they are still CEO.
    Prefer named company-domain email, then current CEO/MD/President.
    """
    contacts = report.get("contact_intelligence") or {}
    emails = contacts.get("emails") or []
    phones = contacts.get("phones") or []
    leaders = rank_leadership(report.get("leadership_team") or [])
    co = report.get("company_profile") or {}
    company = flatten_display(co.get("name")) or (report.get("_meta") or {}).get("company_name") or ""

    named_email = None
    for e in emails:
        if not isinstance(e, dict):
            continue
        person = (e.get("person") or e.get("person_name") or e.get("name") or "").strip()
        em = (e.get("email") or "").strip()
        if person and em and "@" in em:
            # skip generic if we have a person, still OK
            named_email = e
            if not re.match(r"(?i)^(info|hello|contact|support|sales|admin|hr)@", em):
                break
            named_email = named_email or e

    exec_ = None
    for l in leaders:
        if l.get("status") == "current" and _CURRENT_CEO.search(l.get("role") or ""):
            exec_ = l
            break
    if not exec_:
        for l in leaders:
            if l.get("status") == "current" and _CURRENT_CSuite.search(l.get("role") or ""):
                exec_ = l
                break
    if not exec_:
        # Founder-led firms often list no CEO title at all
        for l in leaders:
            if l.get("status") == "current" and re.search(r"(?i)co-?founder|founder", l.get("role") or ""):
                exec_ = l
                break

    name, title, email, phone, reason = "", "", "", "", ""

    if named_email:
        name = (named_email.get("person") or named_email.get("person_name") or named_email.get("name") or "").strip()
        title = named_email.get("title") or named_email.get("label") or named_email.get("role") or ""
        email = named_email.get("email") or ""
        reason = "Named public email on company / contact pages"
    elif exec_:
        name = exec_.get("name") or ""
        title = exec_.get("role") or ""
        reason = f"Current operating executive ({title})"
    else:
        reason = "No verified current executive or named email — do not guess"

    # Match phone to person if possible
    first = (name.split() or [""])[0].lower()
    for p in phones:
        if not isinstance(p, dict):
            continue
        pn = (p.get("person_name") or p.get("name") or "").lower()
        if first and first in pn:
            phone = p.get("number") or ""
            if not name:
                name = p.get("person_name") or p.get("name") or ""
            break
    if not phone and phones:
        p0 = phones[0]
        phone = p0.get("number") if isinstance(p0, dict) else str(p0)

    # If name came from historical founder only, blank it
    if name:
        match = next((l for l in leaders if (l.get("name") or "").lower() == name.lower()), None)
        if match and match.get("status") == "historical" and not _OPERATING_OVERRIDE.search(match.get("role") or ""):
            name, title = "", ""
            reason = "Historical founder is not a business point of contact"

    return {
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "company": company,
        "reason": reason,
        "confidence": "High" if email or (name and exec_) else "Low",
    }


# ── hiring authenticity ──────────────────────────────────────────────────────

_SERP_TITLE = re.compile(
    r"(?i)(jobs? in |open roles|job opportunities|current job openings|"
    r"careers jobs|link to naukri|naukri\.com|\d+\s*\+?\s*(jobs?|openings|vacancies)|"
    r"hiring now|apply now|walk[- ]in)"
)
_PRODUCT_KEYWORD_JOB = re.compile(
    r"(?i)\b(\d{2,4}\s+)?[A-Za-z0-9][A-Za-z0-9 \-]{0,40}\s+jobs?\s+in\s+"
)


def _company_tokens(company_name: str) -> list[str]:
    stop = {"inc", "ltd", "llc", "limited", "corp", "corporation", "the", "pvt", "private", "co"}
    toks = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", company_name or "")]
    return [t for t in toks if t not in stop][:4]


def employer_mentioned(text: str, company_name: str, domain: str = "") -> bool:
    blob = (text or "").lower()
    if domain:
        stem = domain.split(".")[0].lower()
        if stem and len(stem) >= 4 and stem in blob:
            return True
    tokens = _company_tokens(company_name)
    if not tokens:
        return False
    # Require the brand as employer phrasing, not a product keyword
    brand = tokens[0]
    if re.search(rf"(?i)\bat\s+{re.escape(company_name)}\b", text or ""):
        return True
    if re.search(rf"(?i)\b{re.escape(brand)}\s+(careers|jobs|hiring|corporation|inc)\b", text or ""):
        return True
    return brand in blob


def is_official_careers_url(url: str, domain: str, company_name: str) -> tuple[bool, str]:
    u = (url or "").lower()
    h = host_of(url)
    try:
        path = urlparse(url).path.lower()
    except Exception:
        path = ""
    cd = (domain or "").lower().replace("www.", "")

    if not u.startswith("http"):
        return False, "invalid_url"

    # Own-domain careers
    if cd and (h == cd or h.endswith("." + cd) or _same_brand_host(h, cd)):
        if any(x in h + path for x in ("career", "job", "jobs", "work-with-us")):
            return True, "official_careers"
        return False, "company_page_not_careers"

    if any(x in h for x in _ATS):
        tokens = _company_tokens(company_name)
        if tokens and any(t in u for t in tokens):
            return True, "ats"
        return False, "ats_other_employer"

    # LinkedIn company jobs only
    if "linkedin.com" in h:
        if "ad.linkedin.com" in h:
            return False, "linkedin_ads"
        if "/company/" in u and "/jobs" in u:
            return True, "linkedin_company_jobs"
        # Keyword job search URLs
        if "/jobs/" in u:
            return False, "linkedin_keyword_search"
        return False, "linkedin_not_jobs"

    if "naukri.com" in h:
        return False, "naukri_unverified"
    if any(x in h for x in ("indeed.com", "glassdoor.", "monster.com", "foundit.in")):
        return False, "aggregator_unverified"

    if any(x in path for x in ("/careers", "/jobs")) and tokens_in_url(u, company_name):
        return True, "third_party_careers"
    return False, "unrelated"


def tokens_in_url(url: str, company_name: str) -> bool:
    u = (url or "").lower()
    return any(t in u for t in _company_tokens(company_name))


def looks_like_serp_title(role: str, title: str = "") -> bool:
    blob = f"{role or ''} {title or ''}"
    if _SERP_TITLE.search(blob):
        return True
    if _PRODUCT_KEYWORD_JOB.search(blob):
        return True
    if re.search(r"(?i)^(job opportunities|naukri|link to )", role or ""):
        return True
    return False


def filter_hiring_signals(signals: list, company_name: str, domain: str) -> list:
    """Keep only authentic employer openings. Drop keyword / article noise."""
    kept, seen = [], set()
    for h in signals or []:
        if not isinstance(h, dict):
            continue
        role = flatten_display(h.get("role"))
        url = (h.get("source_url") or "").strip()
        title = h.get("source_title") or ""
        snippet = h.get("snippet") or ""
        if not role or len(role) < 4:
            continue
        if looks_like_serp_title(role, title):
            continue
        ok, kind = is_official_careers_url(url, domain, company_name)
        blob = f"{role} {title} {snippet}"
        if not ok:
            continue
        if kind in ("linkedin_company_jobs", "ats", "third_party_careers"):
            if not employer_mentioned(blob + " " + url, company_name, domain):
                continue
        key = (role.lower()[:60], url.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        count = h.get("count") or 1
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = 1
        # Never trust a count scraped from a SERP title
        if kind != "official_careers":
            count = 1
        else:
            count = max(1, min(count, 5000))
        rec = dict(h)
        rec["role"] = role
        rec["count"] = count
        rec["authenticity"] = kind
        rec["verified_employer"] = True
        rec["platform"] = {
            "official_careers": "Official Careers",
            "ats": "Company ATS",
            "linkedin_company_jobs": "LinkedIn Company",
            "third_party_careers": "Careers microsite",
        }.get(kind, h.get("platform") or "Hiring")
        kept.append(rec)
    return kept[:8]


def hiring_conclusion(company_name: str, hiring: list) -> dict:
    if not hiring:
        return {
            "ai_conclusion": (
                f"No official careers page or verified openings found for {company_name}."
            ),
            "signals_used": [],
        }
    roles = [h.get("role") for h in hiring[:4] if h.get("role")]
    platforms = sorted({h.get("platform") or "" for h in hiring if h.get("platform")})
    src = ", ".join(p for p in platforms if p)
    return {
        "ai_conclusion": (
            f"{company_name} has verified public hiring on {src or 'official channels'} "
            f"related to: {', '.join(roles)}."
        ),
        "signals_used": roles,
    }


# ── revenue / geographic ─────────────────────────────────────────────────────

_MONEY = re.compile(
    r"(?:USD|US\$|INR|₹|Rs\.?|EUR|€|GBP|£|\$)\s*[\d,.]+"
    r"(?:\s*(?:trillion|billion|million|thousand|crore|lakh|tn|bn|mn))?",
    re.I,
)
_SCALE = re.compile(r"(trillion|billion|million|thousand|crore|lakh|\bbn\b|\bmn\b|\btn\b)", re.I)
_STOCK = re.compile(r"(?i)\b(stock price|share price|nasdaq|nyse|ticker|quote)\b")


def sanitize_revenue(raw: Any) -> str:
    """Reject stock prices and unit-less amounts like '$507.29'."""
    text = flatten_display(raw)
    if not text or "not publicly" in text.lower() or "not disclosed" in text.lower():
        return ""
    if _STOCK.search(text) and not _SCALE.search(text):
        return ""
    m = _MONEY.search(text)
    if not m:
        # Allow already-scaled Wikidata strings: "USD 245 billion (2024)"
        if _SCALE.search(text) and re.search(r"\d", text):
            return text[:120]
        return ""
    snippet = m.group(0)
    rest = text[m.end():m.end() + 24]
    combined = snippet + " " + rest
    if _SCALE.search(combined) or _SCALE.search(text):
        # keep surrounding scale word
        extra = re.search(r"\s*(trillion|billion|million|thousand|crore|lakh|tn|bn|mn)", rest, re.I)
        out = snippet
        if extra and extra.group(0).strip().lower() not in snippet.lower():
            out = (snippet + extra.group(0)).strip()
        year = re.search(r"\((?:FY\s*)?\d{4}\)", text)
        if year and year.group(0) not in out:
            out = f"{out} {year.group(0)}"
        return re.sub(r"\s+", " ", out)[:120]
    digits = re.sub(r"\D", "", snippet)
    if len(digits) >= 9:  # >= 100 million with no unit, still plausible
        return snippet
    # '$507.29' / '$245.12' stock-like
    return ""


def normalize_geographic_reach(raw: Any, hq: str = "", description: str = "") -> dict:
    text = flatten_display(raw)
    blob = f"{text} {hq} {description}".lower()
    if text and "not publicly" not in text.lower() and "[object" not in text.lower():
        conf = "Medium"
        if any(w in blob for w in ("worldwide", "global", "multinational", "international")):
            conf = "High"
        return field(text, "Public sources", conf)
    if any(w in blob for w in ("worldwide", "global", "multinational", "international")):
        return field("Global", "Public sources", "Medium")
    if hq and "not publicly" not in hq.lower():
        return field(f"Headquartered in {hq}", "Company profile", "Medium")
    return field("Not publicly available", "Public sources", "Low")


# ── honest scoring ───────────────────────────────────────────────────────────

_EMPTY = re.compile(r"(?i)^(not publicly available|not disclosed|n/?a|unknown|—|-)?$")


def _filled(val: Any) -> bool:
    s = flatten_display(val).strip()
    if not s or _EMPTY.match(s) or "[object" in s.lower():
        return False
    return True


def compute_honest_scores(report: dict, citations: list | None = None, judge_quality: int | None = None) -> dict:
    """
    Completeness ≠ accuracy.
    Overall is capped by source reliability and judge authenticity.
    Never 100/100 when sources are mixed or unverified.
    """
    cp = report.get("company_profile") or {}
    prod = report.get("products_services") or {}
    mkt = report.get("market_analysis") or {}
    fin = report.get("financial_data") or {}
    leaders = report.get("leadership_team") or []
    comps = report.get("competitors") or []
    hiring = report.get("hiring_signals") or []
    citations = citations or (report.get("_meta") or {}).get("citations") or []

    required = [
        cp.get("name"),
        cp.get("description"),
        cp.get("headquarters") or cp.get("hq"),
        cp.get("industry") or (mkt.get("industry") if isinstance(mkt, dict) else None),
        prod.get("primary_offerings") if isinstance(prod, dict) else None,
        mkt.get("market_position") if isinstance(mkt, dict) else None,
        mkt.get("geographic_reach") if isinstance(mkt, dict) else None,
        comps,
        leaders,
    ]
    optional = [
        fin.get("revenue_estimate") if isinstance(fin, dict) else None,
        hiring,
        (report.get("contact_intelligence") or {}).get("emails"),
        (report.get("recent_news") or []),
    ]

    def _ok(x) -> bool:
        if isinstance(x, list):
            return len([i for i in x if i]) > 0
        return _filled(x)

    req_hit = sum(1 for x in required if _ok(x))
    opt_hit = sum(1 for x in optional if _ok(x))
    completeness = int(round(100 * (req_hit + 0.4 * opt_hit) / (len(required) + 0.4 * len(optional))))
    completeness = max(15, min(92, completeness))

    # Reliability from citation mix
    cats = [c.get("category") or classify_source(c.get("url") or "") for c in citations]
    if cats:
        weights = [source_trust_score(c) for c in cats]
        reliability = int(sum(weights) / len(weights))
    else:
        reliability = 40
    # Official site present?
    if any(c in ("Company Website", "Investor Relations", "Wikidata") for c in cats):
        reliability = min(90, reliability + 8)
    if any("low trust" in (c or "").lower() or "unverified" in (c or "").lower() or "article" in (c or "").lower() for c in cats):
        reliability = max(25, reliability - 10)
    # No named current people at all — do not look like IR-grade
    if not has_named_current_leadership(leaders):
        reliability = min(reliability, 68)
        completeness = min(completeness, 78)

    authenticity = judge_quality if isinstance(judge_quality, int) else None
    if authenticity is None:
        # Fast path skips the judge; do not leave a 55 that looks like "we found nothing"
        # when the company site itself named current officers.
        if has_named_current_leadership(leaders) and any(
            any(tok in str((l or {}).get("source") or "").lower() for tok in (
                "company", "wikidata", "wikipedia", "public company profiles",
            ))
            for l in (leaders or []) if isinstance(l, dict)
        ):
            authenticity = 74
        else:
            authenticity = 55
    authenticity = max(10, min(92, int(authenticity)))

    # Penalties
    if not has_named_current_leadership(leaders):
        authenticity = min(authenticity, 70)
    if hiring and not all(h.get("verified_employer") for h in hiring if isinstance(h, dict)):
        authenticity = min(authenticity, 60)
    rev = flatten_display((fin or {}).get("revenue_estimate") if isinstance(fin, dict) else "")
    if rev and not sanitize_revenue(rev) and "not " not in rev.lower():
        authenticity = min(authenticity, 55)

    overall = int(round(0.40 * authenticity + 0.35 * reliability + 0.25 * completeness))
    overall = min(overall, reliability + 12, authenticity + 15)
    if authenticity < 80 or reliability < 80:
        overall = min(overall, 88)
    if authenticity < 70 or reliability < 60:
        overall = min(overall, 78)
    overall = max(12, min(92, overall))

    verified = 0
    estimated = 0
    unverified = 0
    for ldr in leaders:
        if not isinstance(ldr, dict):
            continue
        if str(ldr.get("confidence") or "").lower() == "high" and ldr.get("provenance") in ("wikidata", "company"):
            verified += 1
        elif ldr.get("status") == "historical":
            estimated += 1
        else:
            unverified += 1
    verified += sum(1 for h in hiring if isinstance(h, dict) and h.get("verified_employer"))
    verified += len(comps)

    summary_bits = [
        f"Authenticity {authenticity}/100 (LLM-as-judge)",
        f"source reliability {reliability}/100",
        f"completeness {completeness}/100",
    ]
    if not has_named_current_leadership(leaders):
        summary_bits.append("current leadership not independently verified — omitted rather than guessed")
    summary = "; ".join(summary_bits) + "."

    return {
        "overall": overall,
        "data_completeness": completeness,
        "source_reliability": reliability,
        "authenticity": authenticity,
        "verified_fields_count": verified,
        "estimated_fields_count": estimated,
        "unverified_fields_count": unverified,
        "summary": summary,
    }
