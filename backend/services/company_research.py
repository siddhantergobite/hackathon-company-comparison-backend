"""
Company Intelligence Research Engine  v2
==========================================
Phase 1 — SCRAPE    : Homepage + /about + /team + /products + /pricing + /careers + Wikipedia
Phase 2 — SEARCH    : 20+ DuckDuckGo targeted queries across every intelligence dimension
Phase 3 — SCRAPE+   : Fetch & read top news article content directly
Phase 4 — ANALYZE   : Azure OpenAI (primary) via shared LLM client
Phase 5 — REPORT    : Structured deep intelligence JSON
"""

import os, re, json, time, ipaddress, socket
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import BoundedSemaphore, Lock
from typing import Any
from urllib.parse import urlparse, urljoin
import requests
from dotenv import load_dotenv
load_dotenv()

from backend.services import llm as llm_client
from backend.services import research_authenticity as auth
from backend.services import wikidata as wikidata_client

MODEL = (
    llm_client.AZURE_MODEL
    if llm_client.azure_configured()
    else (
        llm_client.GROQ_MODEL
        if getattr(llm_client, "RESEARCH_USE_GROQ", False) and llm_client.groq_configured()
        else (llm_client.AZURE_MODEL if llm_client.azure_configured() else "gpt-5-mini")
    )
)

# The bounded research path is the default for interactive use. Deep mode can
# still be enabled explicitly for a broader public-web sweep.
def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off", "")


RESEARCH_DEEP = _env_flag("RESEARCH_DEEP", False)
RESEARCH_FAST = not RESEARCH_DEEP
# The report judge remains enabled by default. Set the skip flag only when a
# deliberately faster, less-validated response is needed.
RESEARCH_SKIP_JUDGE = _env_flag("RESEARCH_SKIP_JUDGE", False)
# Interactive mode limits hiring discovery to the core public sources; the
# broader eight-query sweep remains available with RESEARCH_DEEP=1.
RESEARCH_SKIP_HIRING_SEARCH = _env_flag("RESEARCH_SKIP_HIRING_SEARCH", RESEARCH_FAST)
# Model-assisted gap-fill for leadership, company identity, and contacts when
# the site scrape finds nothing. Every retained fact gets a visible status.
RESEARCH_LLM_ENRICH = _env_flag("RESEARCH_LLM_ENRICH", True)
RESEARCH_AI_PROFILE_FALLBACK = _env_flag("RESEARCH_AI_PROFILE_FALLBACK", True)

# Bound the sequential model stages in the interactive path. The independent
# report and fact judges remain enabled; timeouts only return the sourced
# fallback fields when a provider is slow or unavailable.
REPORT_LLM_TIMEOUT = 30.0 if RESEARCH_FAST else 50.0
REPORT_JUDGE_TIMEOUT = 30.0 if RESEARCH_FAST else 70.0
PROFILE_LLM_TIMEOUT = 30.0 if RESEARCH_FAST else 90.0
PROFILE_JUDGE_TIMEOUT = 30.0 if RESEARCH_FAST else 90.0
HIRING_LLM_TIMEOUT = 20.0 if RESEARCH_FAST else 50.0
HIRING_JUDGE_TIMEOUT = 20.0 if RESEARCH_FAST else 45.0
CONCLUSION_LLM_TIMEOUT = 10.0 if RESEARCH_FAST else 35.0
# Keep free public search within a modest concurrency budget. A burst of many
# simultaneous DuckDuckGo requests is more likely to be throttled than faster.
_DDG_SEARCH_SEMAPHORE = BoundedSemaphore(3)

# ZaubaCorp / Indian MCA / CIN — fully OFF (user requested remove CIN completely).
# Research uses website + global public web only (pre-CIN behavior).
ENABLE_ZAUBACORP = False
ENABLE_CIN_LOOKUP = False

# Domain-stem → public brand name (used when scrape is blocked / title is garbage)
KNOWN_BRANDS = {
    "microsoft": "Microsoft",
    "buffer": "Buffer",
    "google": "Google",
    "apple": "Apple",
    "amazon": "Amazon",
    "meta": "Meta",
    "facebook": "Meta",
    "linkedin": "LinkedIn",
    "salesforce": "Salesforce",
    "oracle": "Oracle",
    "ibm": "IBM",
    "adobe": "Adobe",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
    "notion": "Notion",
    "slack": "Slack",
    "atlassian": "Atlassian",
    "hubspot": "HubSpot",
    "shopify": "Shopify",
    "stripe": "Stripe",
    "tcs": "Tata Consultancy Services",
    "infosys": "Infosys",
    "wipro": "Wipro",
    "ergobite": "Ergobite",
    "accenture": "Accenture",
    "deloitte": "Deloitte",
}

KNOWN_TICKERS = {
    "microsoft": "MSFT",
    "google": "GOOGL",
    "apple": "AAPL",
    "amazon": "AMZN",
    "salesforce": "CRM",
}

# Many companies publish their corporate pages on descriptive subdomains
# (about.google, careers.microsoft.com, jobs.amazon.com). The subdomain is a
# page type, not the company identity.
GENERIC_SITE_SUBDOMAINS = {
    "about", "careers", "career", "jobs", "job", "investor", "investors",
    "ir", "support", "help", "news", "blog", "blogs", "corporate", "company",
}
PUBLIC_SUFFIX_PARTS = {"co", "com", "org", "net", "gov", "ac"}


def _domain_parts(domain: str) -> list[str]:
    d = (domain or "").lower().split(":", 1)[0].strip(".")
    parts = [p for p in d.split(".") if p]
    if parts and parts[0] == "www":
        parts = parts[1:]
    return parts


def _domain_stem(domain: str) -> str:
    parts = _domain_parts(domain)
    if not parts:
        return ""
    if parts[0] in GENERIC_SITE_SUBDOMAINS and len(parts) >= 2:
        # Handle both about.google and careers.example.co.uk.
        if len(parts) == 2:
            return parts[1]
        if len(parts) >= 3 and parts[-2] in PUBLIC_SUFFIX_PARTS:
            return parts[-3]
        return parts[-2]
    return parts[0]


def _brand_from_domain(domain: str) -> str:
    stem = _domain_stem(domain)
    if not stem:
        return "Company"
    return KNOWN_BRANDS.get(stem) or stem.replace("-", " ").title()


def _is_blocked_page_text(title: str = "", text: str = "") -> bool:
    blob = f"{title or ''} {text or ''}".lower()
    markers = (
        "request has been blocked",
        "access denied",
        "attention required",
        "cf-browser-verification",
        "captcha",
        "bot detection",
        "unusual traffic",
        "automated process",
        "your current user-agent string appears to be from an automated",
        "enable javascript and cookies",
        "sorry, you have been blocked",
    )
    return any(m in blob for m in markers)


def _is_parked_page_text(title: str = "", text: str = "") -> bool:
    """Detect a parked/for-sale domain, which is not company evidence."""
    blob = f"{title or ''} {text or ''}".lower()
    markers = (
        "huge domains",
        "this domain is for sale",
        "domain name is for sale",
        "buy this domain",
        "make an offer for this domain",
        "domain parking",
        "parked domain",
        "this website is for sale",
        "domain has been registered",
    )
    return any(marker in blob for marker in markers)


def _name_matches_domain(name: str, domain: str) -> bool:
    """True if candidate company name is plausibly the website brand."""
    if isinstance(name, dict):
        name = name.get("value") or name.get("name") or ""
    name = str(name or "")
    stem = _domain_stem(domain)
    if not stem:
        return True
    n = re.sub(r"[^a-z0-9]", "", name.lower())
    s = re.sub(r"[^a-z0-9]", "", stem)
    if not n or len(n) < 2:
        return False
    if s in n or n in s:
        return True
    brand = KNOWN_BRANDS.get(stem, "")
    b = re.sub(r"[^a-z0-9]", "", brand.lower())
    if b and (b in n or n in b):
        return True
    # reject obvious block-page titles used as names
    if _is_blocked_page_text(name, ""):
        return False
    junk_starts = ("your request", "access denied", "attention required", "just a moment")
    if any(name.lower().startswith(j) for j in junk_starts):
        return False
    return False


def _anchor_company_name(candidate: str, domain: str, scraped: dict | None = None) -> str:
    """Never let a blocked/WAF page or unrelated LLM name replace the domain brand."""
    scraped = scraped or {}
    if isinstance(candidate, dict):
        candidate = candidate.get("value") or candidate.get("name") or ""
    candidate = str(candidate or "").strip()
    brand = _brand_from_domain(domain)
    blocked = bool(scraped.get("_scrape_blocked")) or _is_blocked_page_text(
        scraped.get("title") or "", scraped.get("homepage_text") or ""
    )
    if blocked:
        return brand
    site_title = re.split(r"[|\-:]", str(scraped.get("title") or ""))[0].strip()
    if _name_matches_domain(site_title, domain):
        return site_title
    if _name_matches_domain(candidate, domain):
        return candidate or brand
    return brand


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─────────────────────────────────────────────────────────────────────────────
# ZAUBACORP — Indian MCA Official Registry Scraper
# ─────────────────────────────────────────────────────────────────────────────

def _is_zaubacorp_company_url(href: str) -> bool:
    """Match ZaubaCorp company pages (slug or /company/ paths)."""
    if not href or "zaubacorp.com" not in href.lower():
        return False
    lower = href.lower()
    skip = (
        "/company-list/", "/companysearch", "/login", "/about", "/contact",
        "/director/", "/company-list", "/privacy", "/terms", "/blog",
    )
    if any(s in lower for s in skip):
        return False
    # Slug: .../NAME-PRIVATE-LIMITED-U52520PN2019PTC185480
    if re.search(r"zaubacorp\.com/[A-Z0-9][A-Z0-9\-]*(PTC|PLC|LLP|OPC|FLC)\d", href, re.I):
        return True
    if re.search(r"zaubacorp\.com/company/[A-Z0-9]", href, re.I):
        return True
    return False


def _parse_zaubacorp_jsonld(soup) -> dict:
    """Extract Organization fields from JSON-LD (high-confidence MCA data)."""
    out = {}
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
            if item.get("@type") not in ("Organization", "Corporation"):
                continue
            if item.get("legalName"):
                out["Company Name"] = item["legalName"]
            ident = item.get("identifier") or {}
            if isinstance(ident, dict) and ident.get("propertyID") == "CIN":
                out["CIN"] = ident.get("value", "")
            if item.get("email"):
                out["Email Address"] = item["email"]
            if item.get("address"):
                addr = item["address"]
                if isinstance(addr, dict):
                    addr = ", ".join(str(v) for v in addr.values() if v)
                out["Registered Address"] = str(addr).strip()
            if item.get("foundingDate"):
                out["Date of Incorporation"] = item["foundingDate"]
    return out


def _parse_zaubacorp_prose(text: str) -> dict:
    """Parse narrative MCA block on ZaubaCorp company pages."""
    out = {}
    if not text:
        return out
    patterns = {
        "CIN": r"(?:CIN(?:\s*(?:Number|No\.?))?\s*(?:is|:)?\s*)([A-Z]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})",
        "Date of Incorporation": r"incorporated on\s+([^\.]+?)(?:\.|\s+It is)",
        "Authorized Capital": r"authorized share capital is\s+(Rs\.?\s*[\d,\.]+\.?\d*)",
        "Paid Up Capital": r"paid up capital is\s+(Rs\.?\s*[\d,\.]+\.?\d*)",
        "Status": r"(?:current status is|status is)\s+([A-Za-z]+)",
        "Email Address": r"[Ee]mail address\s*(?:is|-)\s*([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
        "Registered Address": r"[Rr]egistered address of .+? is\s+([^\.]+(?:\.|$))",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            out[key] = m.group(1).strip().rstrip(".")
    dm = re.search(r"Directors? of .+? are\s+(.+?)(?:\.|\s+(?:Its|ERGOBITE|[A-Z]{3,}))", text, re.I)
    if dm:
        names = []
        for n in re.split(r",|\band\b", dm.group(1)):
            n = re.sub(r"\s+", " ", n.strip().strip("."))
            if len(n) > 3 and n.lower() not in ("the", "and"):
                names.append({"name": n, "din": "", "designation": "Director"})
        if names:
            out["Directors"] = names
    return out


_ZAUBA_STOPWORDS = {
    "private", "limited", "ltd", "pvt", "company", "india", "the", "and", "llp", "opc",
    "solutions", "technologies", "technology", "services", "tech", "systems", "industries",
    "international", "global", "enterprises", "corporation", "corp", "inc", "co",
}


def _meaningful_tokens(text: str) -> list:
    return [
        t for t in re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()
        if len(t) > 2 and t not in _ZAUBA_STOPWORDS
    ]


def _normalize_zauba_href(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("/www."):
        href = "https://" + href.lstrip("/")
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        href = "https://www.zaubacorp.com" + href
    return href


def _zauba_match_score(query: str, url: str, structured: dict = None) -> int:
    """Score how well a ZaubaCorp hit matches the search query."""
    legal = ((structured or {}).get("Company Name") or "").upper().strip()
    q = re.sub(r"\s+", " ", (query or "").upper()).strip()
    slug = (url or "").upper()
    if not legal:
        legal = slug

    if q and (q in legal or legal in q):
        return 100

    q_tokens = [t for t in q.split() if len(t) > 2]
    if not q_tokens:
        return 0

    matches = sum(1 for t in q_tokens if t in legal or t in slug)
    score = matches * 20
    if matches == len(q_tokens):
        score += 50
    # Penalize wrong sibling companies sharing one token (e.g. ERGOBITE INFOSYSTEMS vs ERGOBITE TECH)
    meaningful = _meaningful_tokens(query)
    if meaningful:
        primary = meaningful[0].upper()
        if primary in legal and len(q_tokens) > 2 and matches < len(q_tokens):
            score = max(score - 10, 20)
    return score


_CIN_RE = re.compile(r"[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}")
_CIN_VALID_TYPES = {
    "PTC", "PLC", "FTC", "GAP", "NPL", "OPC", "FLP", "SGC", "ULL", "ULT",
    "GOI", "GAT", "NPL",
}


def _safe_print(msg: str) -> None:
    """Print without crashing on Windows cp1252 consoles."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _is_valid_cin(cin: str) -> bool:
    """Strict Indian MCA CIN format check (21 chars)."""
    c = re.sub(r"[\s\-]", "", (cin or "").upper())
    if not _CIN_RE.fullmatch(c):
        return False
    # Year of incorporation embedded in CIN
    try:
        year = int(c[8:12])
        if year < 1947 or year > time.gmtime().tm_year + 1:
            return False
    except Exception:
        return False
    ctype = c[12:15]
    if ctype not in _CIN_VALID_TYPES and not re.fullmatch(r"[A-Z]{3}", ctype):
        return False
    return True


def _normalize_cin(cin: str) -> str:
    return re.sub(r"[\s\-]", "", (cin or "").upper())


def _legal_matches_brand(legal_name: str, brand: str, domain: str) -> bool:
    legal = re.sub(r"[^a-z0-9]", "", (legal_name or "").lower())
    brand_l = re.sub(r"[^a-z0-9]", "", (brand or "").lower())
    stem = re.sub(r"[^a-z0-9]", "", _domain_stem(domain))
    if not legal:
        return False
    if brand_l and len(brand_l) >= 3 and brand_l in legal:
        return True
    if stem and len(stem) >= 3 and stem in legal:
        return True
    # Known brand expansions
    known = KNOWN_BRANDS.get(stem, "")
    known_l = re.sub(r"[^a-z0-9]", "", known.lower())
    if known_l and known_l in legal:
        return True
    return False


def _discover_cin_candidates(company_name: str, domain: str, scraped: dict, raw_html: str = "") -> list[dict]:
    """
    Collect possible CINs from website, public search, and LLM.
    Does NOT invent — only extracts patterns that already look like CINs.
    """
    found = []
    seen = set()

    def _add(cin: str, source: str, evidence: str = ""):
        c = _normalize_cin(cin)
        if not _is_valid_cin(c) or c in seen:
            return
        seen.add(c)
        found.append({"cin": c, "source": source, "evidence": (evidence or "")[:200]})

    # 1) Website / HTML
    signals = _extract_entity_signals(scraped, f"https://{domain}", raw_html=raw_html)
    for c in signals.get("cins") or []:
        _add(c, "website", "Found on company website HTML/text")
    if signals.get("cin"):
        _add(signals["cin"], "website", "Primary CIN extracted from website")

    # 2) Public web search (Tofler / Zauba / MCA mentions) — extract CIN patterns only
    queries = [
        f'"{company_name}" CIN',
        f"{company_name} {domain} CIN Private Limited",
        f'site:zaubacorp.com "{company_name}"',
        f'site:tofler.in "{company_name}" CIN',
    ]
    for q in queries[:3]:
        for r in _ddg_search(q, max_results=5):
            blob = f"{r.get('title','')} {r.get('body','')} {r.get('href','')}"
            for m in _CIN_RE.findall(blob.upper()):
                _add(m, "public_search", q)

    # 3) LLM (Groq/Gemini via shared client) — may only return an existing CIN, never invent
    try:
        prompt = f"""You must find the official Indian MCA Corporate Identification Number (CIN) for this company IF it is an Indian registered company.

Company brand: {company_name}
Website domain: {domain}
Site title: {(scraped.get('title') or '')[:120]}
About excerpt: {(scraped.get('about_text') or scraped.get('homepage_text') or '')[:500]}

Rules:
1. Return ONLY valid JSON.
2. CIN must be exactly 21 chars matching Indian MCA format (starts with L or U).
3. If you are NOT highly certain, return empty cin.
4. NEVER invent / guess a CIN.
5. Global non-India companies (e.g. google.com, microsoft.com, buffer.com) usually have NO Indian parent CIN for the global site — return empty unless this website is clearly an Indian legal entity.

JSON schema:
{{"cin":"","confidence":"High|Medium|Low","legal_name":"","reason":"short"}}
"""
        raw = llm_client.chat_groq(
            [
                {"role": "system", "content": "Return valid JSON only. Prefer empty CIN over a wrong CIN."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=250,
            json_mode=True,
            timeout=25.0,
        )
        raw = re.sub(r"^```(?:json)?", "", (raw or "").strip(), flags=re.I).strip()
        raw = re.sub(r"```$", "", raw).strip()
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        cin = _normalize_cin(data.get("cin") or "")
        conf = str(data.get("confidence") or "Low").lower()
        if cin and conf in ("high", "medium") and _is_valid_cin(cin):
            _add(cin, "llm", data.get("reason") or data.get("legal_name") or "LLM")
    except Exception as e:
        print(f"[CIN] LLM discover failed: {e}")

    print(f"[CIN] Candidates: {[f.get('cin') for f in found]}")
    return found


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _find_emails(text: str) -> list:
    """All e-mail addresses in `text`, first-seen order, no duplicates.

    Scanning a large page (minified JS, inline base64) with the bare pattern is quadratic: one
    2.6 MB homepage took ~9 s. Anchoring on each '@' and looking only at its neighbourhood finds
    the same addresses in milliseconds (a local part is at most 64 chars, a domain at most 255).
    """
    out: dict = {}
    for m in re.finditer("@", text or ""):
        seg = text[max(0, m.start() - 64): m.end() + 255]
        for e in _EMAIL_RE.findall(seg):
            out.setdefault(e, None)
    return list(out)


def _verify_cin(cin: str, company_name: str, domain: str) -> dict:
    """
    Verify CIN against MCA mirror (Zauba). Accept only if page CIN matches
    and legal name matches the website brand/domain.
    """
    cin = _normalize_cin(cin)
    out = {
        "ok": False,
        "cin": cin,
        "url": "",
        "structured": {},
        "text": "",
        "reason": "not verified",
        "match_confidence": "Low",
    }
    if not _is_valid_cin(cin):
        out["reason"] = "invalid CIN format"
        return out

    urls = _lookup_zauba_by_cin(cin)
    # Direct known URL pattern fallback
    urls = list(dict.fromkeys(urls + [
        f"https://www.zaubacorp.com/companysearchresults/{cin}",
    ]))

    best = None
    for u in urls[:5]:
        page = _fetch_zaubacorp_page(u) if "companysearchresults" not in u else {"structured": {}, "url": u, "text": ""}
        # If searchresults page, try to extract company link first
        if "companysearchresults" in (u or ""):
            try:
                resp = requests.get(u, headers=HEADERS, timeout=12)
                if resp.status_code == 200:
                    for m in re.finditer(
                        rf"zaubacorp\.com/([A-Z0-9\-]*{re.escape(cin)}[A-Z0-9\-]*)",
                        resp.text, re.I,
                    ):
                        page = _fetch_zaubacorp_page(f"https://www.zaubacorp.com/{m.group(1)}")
                        if page.get("structured"):
                            break
            except Exception:
                continue

        zs = page.get("structured") or {}
        page_cin = _normalize_cin(zs.get("CIN") or "")
        # Sometimes CIN only in URL/text
        if not page_cin:
            blob = f"{page.get('url','')} {page.get('text','')}"
            m = _CIN_RE.search(blob.upper())
            page_cin = m.group(0) if m else ""
        if page_cin != cin:
            # still accept if URL contains CIN and company name present
            if cin not in (page.get("url") or "").upper():
                continue
        legal = zs.get("Company Name") or ""
        if not legal:
            continue
        if not _legal_matches_brand(legal, company_name, domain):
            _safe_print(f"[CIN] Reject {cin} - legal '{legal}' does not match brand '{company_name}' / {domain}")
            continue
        # Reject obvious sister/subsidiary for global brand sites
        if _is_india_subsidiary_for_global_site(legal, domain, company_name):
            _safe_print(f"[CIN] Reject {cin} - India subsidiary of global site ({legal})")
            continue
        best = page
        break

    if not best:
        out["reason"] = "CIN not found on MCA mirror or name mismatch"
        return out

    zs = best.get("structured") or {}
    zs["CIN"] = cin
    out.update({
        "ok": True,
        "url": best.get("url") or "",
        "structured": zs,
        "text": best.get("text") or "",
        "reason": f"CIN verified on MCA mirror for {zs.get('Company Name')}",
        "match_confidence": "High",
        "legal_name": zs.get("Company Name") or "",
    })
    return out


def _cin_name_fit_score(legal_name: str, brand: str, domain: str) -> int:
    """Higher = better match of MCA legal name to website brand."""
    if not _legal_matches_brand(legal_name, brand, domain):
        return -999
    legal_u = (legal_name or "").upper()
    brand_u = (brand or "").upper()
    stem = _domain_stem(domain).upper()
    score = 50
    # Prefer names that start with brand/stem
    if legal_u.startswith(brand_u) or (stem and legal_u.startswith(stem)):
        score += 40
    # Penalize sister/subsidiary tokens
    for tok in _SUBSIDIARY_TOKENS:
        if tok.upper().replace(" ", "") in re.sub(r"[^A-Z0-9]", "", legal_u):
            score -= 80
    for tok in ("INFOSYSTEMS", "INFOTECH", "TECHNOLOGIES", "SOLUTIONS", "SERVICES", "CONSULTING"):
        # soft penalty only when brand itself doesn't include that token
        if tok in legal_u and tok not in brand_u and tok not in stem:
            score -= 5
    # Prefer shorter legal names (less likely sister entity stuffing)
    score -= max(0, len(legal_u.split()) - 4) * 3
    return score


def _cin_year(cin: str) -> int:
    try:
        return int(_normalize_cin(cin)[8:12])
    except Exception:
        return 9999


def _resolve_verified_cin(scraped: dict, url: str, company_name: str, raw_html: str = "") -> dict:
    """
    CIN-first resolver:
    - Find valid CIN candidates
    - Verify against MCA mirror
    - Stick to best brand-matching verified CIN
    - If none, return empty (caller continues previous global flow)
    """
    domain = urlparse(url).netloc.replace("www.", "")
    brand = company_name or _brand_from_domain(domain)
    empty = {
        "cin_verified": False,
        "cin": "",
        "match_confidence": "Low",
        "match_reason": "No verified CIN",
        "url": "",
        "structured": {},
        "text": "",
        "preferred_display_name": brand,
        "entity_signals": _extract_entity_signals(scraped, url, raw_html),
        "candidates": [],
    }
    if not ENABLE_CIN_LOOKUP:
        empty["match_reason"] = "CIN lookup disabled"
        return empty

    # Skip CIN chase for obvious global consumer domains when brand is known global
    stem = _domain_stem(domain)
    global_no_cin = {
        "google", "microsoft", "apple", "amazon", "meta", "facebook", "buffer",
        "notion", "slack", "openai", "nvidia", "oracle", "salesforce", "adobe",
    }
    # Still allow if website itself embeds a CIN (Indian entity page)
    signals = empty["entity_signals"]
    if stem in global_no_cin and not (signals.get("cins") or signals.get("cin")):
        empty["match_reason"] = "Global brand site - CIN lookup skipped unless present on website"
        _safe_print(f"[CIN] Skip lookup for global brand domain {domain}")
        return empty

    candidates = _discover_cin_candidates(brand, domain, scraped, raw_html=raw_html)
    # Prefer website CINs, then LLM, then public search
    src_rank = {"website": 0, "llm": 1, "public_search": 2}
    candidates = sorted(candidates, key=lambda c: src_rank.get(c.get("source"), 9))[:5]
    empty["candidates"] = candidates

    verified = []
    for cand in candidates:
        try:
            ver = _verify_cin(cand["cin"], brand, domain)
        except Exception as e:
            _safe_print(f"[CIN] verify error for {cand.get('cin')}: {e}")
            continue
        if not ver.get("ok"):
            _safe_print(f"[CIN] candidate {cand['cin']} failed: {ver.get('reason')}")
            continue
        fit = _cin_name_fit_score(ver.get("legal_name") or "", brand, domain)
        verified.append({**ver, "cin_source": cand.get("source") or "", "fit": fit})
        _safe_print(
            f"[CIN] ok {ver['cin']} -> {ver.get('legal_name')} "
            f"(source={cand.get('source')}, fit={fit})"
        )

    if not verified:
        _safe_print("[CIN] No verified CIN - falling back to global research path")
        return empty

    verified.sort(
        key=lambda v: (
            -(int(v.get("fit") or 0) // 10),  # coarse fit band
            _cin_year(v.get("cin") or ""),     # older CIN preferred inside same band
            -int(v.get("fit") or 0),
            src_rank.get(v.get("cin_source"), 9),
        )
    )
    best = verified[0]
    _safe_print(
        f"[CIN] LOCKED {best['cin']} -> {best.get('legal_name')} "
        f"(source={best.get('cin_source')}, fit={best.get('fit')})"
    )
    return {
        "cin_verified": True,
        "cin": best["cin"],
        "match_confidence": "High",
        "match_reason": best.get("reason") or "CIN verified",
        "match_score": 1000,
        "url": best.get("url") or "",
        "structured": best.get("structured") or {},
        "text": best.get("text") or "",
        "preferred_display_name": best.get("legal_name") or brand,
        "entity_signals": signals,
        "candidates": candidates,
        "cin_source": best.get("cin_source") or "",
    }


_GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "rediffmail.com", "hotmail.com", "outlook.com",
    "ymail.com", "live.com", "protonmail.com",
}
_INDIAN_CITIES = (
    "mumbai", "delhi", "kolkata", "chennai", "bangalore", "bengaluru", "pune",
    "hyderabad", "bhilwara", "jaipur", "noida", "gurgaon", "gurugram", "ahmedabad",
    "kochi", "cochin", "lucknow", "indore", "nagpur", "surat", "vadodara",
)
_MCA_CONF_HIGH = 140
_MCA_CONF_MED = 100

# Tokens that usually mean subsidiary / sister / non-parent entity
_SUBSIDIARY_TOKENS = {
    "eserve", "e-serve", "e serve", "foundation", "trust", "welfare",
    "employee", "employees", "benefit", "pension", "holdings", "investment",
    "ventures", "incubator", "academy", "foundation", "charitable",
}


def _normalize_legal_name(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip())
    n = re.sub(r"\bPvt\.?\s*Ltd\.?\b", "Private Limited", n, flags=re.I)
    n = re.sub(r"\bLtd\.?\b", "Limited", n, flags=re.I)
    return n.strip()


def _extract_entity_signals(scraped: dict, url: str, raw_html: str = "") -> dict:
    """Pull CIN, legal names, emails, and location hints from the company website."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").lower()
    stem = domain.split(".")[0] if domain else ""

    blobs = [
        raw_html or "",
        scraped.get("homepage_text") or "",
        scraped.get("about_text") or "",
        scraped.get("leadership_text") or "",
        scraped.get("description") or "",
    ]
    combined = "\n".join(blobs)
    cins = list(dict.fromkeys(_CIN_RE.findall(combined.upper())))

    legal_names = []
    legal_patterns = [
        r"([A-Za-z0-9][\w\s&.'\-]{2,80}?\bPrivate\s+Limited)",
        r"([A-Za-z0-9][\w\s&.'\-]{2,80}?\bIndia\s+Limited)",
        r"([A-Za-z0-9][\w\s&.'\-]{2,80}?\bLtd\.?)",
    ]
    for pat in legal_patterns:
        for m in re.finditer(pat, combined, re.I):
            name = _normalize_legal_name(m.group(1).rstrip(".,;"))
            if stem and stem.lower() in name.lower() and len(name) >= len(stem) + 3:
                legal_names.append(name)

    if stem:
        title_stem = stem.replace("-", " ").title()
        if title_stem not in legal_names:
            legal_names.append(title_stem)

    email_pat = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    emails = _find_emails(combined)[:12]
    corporate_emails = [
        e.lower() for e in emails
        if stem and (stem in e.lower() or e.lower().endswith("@" + domain))
    ]

    cd = scraped.get("contact_data") or {}
    address_bits = [cd.get("address") or ""] + list(cd.get("addresses") or [])
    address_text = " ".join(str(a) for a in address_bits if a)

    return {
        "domain": domain,
        "domain_stem": stem,
        "cin": cins[0] if cins else "",
        "cins": cins,
        "legal_names": list(dict.fromkeys(legal_names))[:8],
        "emails": [e.lower() for e in emails],
        "corporate_emails": corporate_emails,
        "address_text": address_text,
        "website_keywords": _meaningful_tokens(combined[:4000])[:24],
    }


def _entity_match_score(signals: dict, structured: dict, url: str) -> tuple[int, str]:
    """Score MCA registry candidate against website entity signals."""
    legal = ((structured or {}).get("Company Name") or "").upper().strip()
    if not legal:
        legal = (url or "").upper()
    reasons = []
    score = 0

    site_cin = (signals.get("cin") or "").upper()
    reg_cin = ((structured or {}).get("CIN") or "").upper()
    if site_cin and reg_cin and site_cin == reg_cin:
        return 1000, "CIN verified on website"

    for raw_name in signals.get("legal_names") or []:
        norm = _normalize_legal_name(raw_name).upper()
        if norm == legal:
            score += 200
            reasons.append(f"Exact legal name: {raw_name}")
            break
        if norm.replace(" LIMITED", "") in legal or legal in norm:
            score += 130
            reasons.append(f"Legal name overlap: {raw_name}")
            break

    stem = (signals.get("domain_stem") or "").lower()
    if stem and stem in legal.lower():
        score += 40
        reasons.append("Brand token in legal name")

    # Heavy penalty for subsidiary / sister entities when website is the brand domain
    legal_l = legal.lower()
    site_blob_l = " ".join(signals.get("legal_names") or []).lower() + " " + stem
    for bad in _SUBSIDIARY_TOKENS:
        if bad in legal_l and bad not in site_blob_l and bad not in (signals.get("domain") or "").lower():
            score -= 140
            reasons.append(f"Subsidiary/sister token: {bad}")

    # Prefer "LIMITED" / "INDIA LIMITED" parents over long multi-token service arms
    if re.search(r"\bE[\s\-]?SERVE\b", legal, re.I):
        score -= 180
        reasons.append("E-Serve style entity — unlikely primary brand site")

    site_blob = " ".join(signals.get("legal_names") or []).lower()
    site_blob += " " + stem + " " + (signals.get("domain") or "")
    site_tokens = set(_meaningful_tokens(site_blob) + (signals.get("website_keywords") or []))
    for tok in set(_meaningful_tokens(legal)) - site_tokens:
        if len(tok) >= 4 and tok != stem:
            score -= 85
            reasons.append(f"Unrelated token: {tok}")

    reg_email = ((structured or {}).get("Email Address") or "").lower()
    domain = signals.get("domain") or ""
    if reg_email and domain:
        email_dom = reg_email.split("@")[-1]
        if domain in email_dom or email_dom.endswith("." + domain):
            score += 100
            reasons.append("MCA email matches website domain")
        elif email_dom in _GENERIC_EMAIL_DOMAINS:
            score -= 45
            reasons.append(f"Generic MCA email ({email_dom})")
        elif stem and stem not in email_dom:
            score -= 30

    reg_addr = ((structured or {}).get("Registered Address") or "").lower()
    addr_text = (signals.get("address_text") or "").lower()
    site_cities = [c for c in _INDIAN_CITIES if c in addr_text]
    if reg_addr and site_cities:
        if any(c in reg_addr for c in site_cities):
            score += 50
            reasons.append("City matches website")
        else:
            score -= 90
            reasons.append("City mismatch vs website")

    if "PRIVATE" in legal and any("india limited" in n.lower() for n in (signals.get("legal_names") or [])):
        score -= 65
        reasons.append("Private Ltd entity vs India Ltd on website")

    if "PLC" in reg_cin and any("india" in n.lower() for n in (signals.get("legal_names") or [])):
        score += 45
        reasons.append("Listed PLC matches India Ltd")

    if (structured.get("Directors") or []) and score >= 45:
        score += 25
        reasons.append(f"{len(structured['Directors'])} MCA directors")

    return score, "; ".join(reasons[:6]) or "Weak match"


def _build_zauba_queries(signals: dict, scraped: dict) -> list[str]:
    """Build MCA search queries from website signals — avoid blind PRIVATE LIMITED guess."""
    queries = []
    for name in signals.get("legal_names") or []:
        queries.append(_normalize_legal_name(name))

    stem = signals.get("domain_stem") or ""
    for q in [
        f"{stem} india limited",
        f"{stem} limited",
        stem,
    ]:
        if stem:
            queries.append(q)

    # Famous brand expansions — helps avoid matching sister/subsidiary entities
    _BRAND_EXPANSIONS = {
        "tcs": ["Tata Consultancy Services Limited", "Tata Consultancy Services"],
        "infosys": ["Infosys Limited"],
        "wipro": ["Wipro Limited"],
        "hcl": ["HCL Technologies Limited"],
        "accenture": ["Accenture Solutions Private Limited"],
        "microsoft": ["Microsoft Corporation"],
        "google": ["Google LLC"],
        "amazon": ["Amazon.com, Inc."],
    }
    for extra in _BRAND_EXPANSIONS.get(stem.lower(), []):
        queries.insert(0, extra)

    title = re.split(r"[|\-—–]", scraped.get("title") or "")[0].strip()
    generic_title = bool(re.search(
        r"\b(best|leading|top|#1|official|home|welcome|download|buy|book)\b",
        title, re.I,
    )) or len(title.split()) > 6
    if title and not generic_title:
        queries.append(title)

    return list(dict.fromkeys(q for q in queries if q and len(q.strip()) >= 3))[:6]


def _collect_zauba_candidate_urls(search_name: str) -> list[str]:
    """Collect ZaubaCorp company page URLs for a search term (no page fetch yet)."""
    candidate_urls = []

    def _collect_url(href: str):
        href = _normalize_zauba_href(href)
        if _is_zaubacorp_company_url(href) and href not in candidate_urls:
            candidate_urls.append(href)

    # Reduce ZaubaCorp HTML search fan-out for speed
    for q in [
        f"site:zaubacorp.com {search_name}",
        f"zaubacorp {search_name}",
    ]:
        for r in _ddg_search(q, max_results=5):
            _collect_url(r.get("href", ""))

    from bs4 import BeautifulSoup
    for token in _meaningful_tokens(search_name)[:2]:
        try:
            sr = requests.get(
                f"https://www.zaubacorp.com/companysearchresults/{token.upper()}",
                headers=HEADERS, timeout=10,
            )
            if sr.status_code != 200:
                continue
            for a in BeautifulSoup(sr.text, "html.parser").find_all("a", href=True):
                _collect_url(a["href"])
                if len(candidate_urls) >= 8:
                    break
        except Exception:
            continue
        if len(candidate_urls) >= 8:
            break

    return candidate_urls[:8]


def _lookup_zauba_by_cin(cin: str) -> list[str]:
    """Find ZaubaCorp page URLs for a known CIN."""
    cin = (cin or "").upper().strip()
    if not cin:
        return []
    urls = []
    for r in _ddg_search(f"site:zaubacorp.com {cin}", max_results=6):
        href = _normalize_zauba_href(r.get("href", ""))
        if cin in href.upper() and _is_zaubacorp_company_url(href):
            urls.append(href)
    try:
        sr = requests.get(
            f"https://www.zaubacorp.com/companysearchresults/{cin}",
            headers=HEADERS, timeout=15,
        )
        if sr.status_code == 200:
            for m in re.finditer(
                rf"zaubacorp\.com/([A-Z0-9\-]*{re.escape(cin)}[A-Z0-9\-]*)",
                sr.text, re.I,
            ):
                urls.append(f"https://www.zaubacorp.com/{m.group(1)}")
    except Exception:
        pass
    return list(dict.fromkeys(urls))[:4]


def _fetch_zaubacorp_page(zauba_url: str) -> dict:
    """Fetch and parse one ZaubaCorp company page."""
    from bs4 import BeautifulSoup

    result = {"text": "", "url": zauba_url, "structured": {}}
    if not zauba_url:
        return result

    try:
        resp = requests.get(zauba_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        structured = _parse_zaubacorp_jsonld(soup)

        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(strip=True)
                if key and value and len(key) < 60 and "paid company" not in value.lower():
                    if key not in structured or len(value) > len(str(structured.get(key, ""))):
                        structured[key] = value

        field_map = {
            "CIN": ["cin", "CIN"],
            "Company Name": ["company-name", "company_name"],
            "Status": ["company-status"],
            "Date of Incorporation": ["date-of-incorporation"],
            "Registered Address": ["registered-address"],
            "Authorized Capital": ["authorized-capital"],
            "Paid Up Capital": ["paid-up-capital"],
            "RoC": ["roc"],
        }
        for label, ids in field_map.items():
            for id_ in ids:
                el = soup.find(id=id_) or soup.find(class_=id_)
                if el and not structured.get(label):
                    structured[label] = el.get_text(strip=True)
                    break

        if not structured.get("Company Name"):
            h1 = soup.find("h1")
            if h1:
                structured["Company Name"] = h1.get_text(strip=True)

        directors = list(structured.get("Directors") or [])
        for table in soup.find_all("table"):
            header = table.find("tr")
            if not header or not re.search(r"director|din|designation", header.get_text(), re.I):
                continue
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    rec = _normalize_director_row(
                        cols[0].get_text(strip=True),
                        cols[1].get_text(strip=True) if len(cols) > 1 else "",
                        cols[2].get_text(strip=True) if len(cols) > 2 else "Director",
                    )
                    if rec:
                        directors.append(rec)
            if directors:
                break

        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        full_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:8000]

        prose = _parse_zaubacorp_prose(full_text)
        for k, v in prose.items():
            if k == "Directors":
                if not directors:
                    directors = v
            elif not structured.get(k) or "not publicly" in str(structured.get(k, "")).lower():
                structured[k] = v

        if directors:
            seen_names = set()
            deduped = []
            for d in directors:
                n = re.sub(r"\s+", " ", d.get("name", "").strip())
                if n and n.lower() not in seen_names:
                    seen_names.add(n.lower())
                    deduped.append({**d, "name": n, "source": "ZaubaCorp MCA", "confidence": "High"})
            structured["Directors"] = deduped

        result["structured"] = structured
        result["text"] = full_text
    except Exception as e:
        print(f"[ZaubaCorp] Page fetch error ({zauba_url}): {e}")

    return result


def _resolve_mca_entity(scraped: dict, url: str, raw_html: str = "") -> dict:
    """
    Resolve the correct MCA legal entity for a website URL.
    Uses CIN (if on site), legal name, email domain, city, and penalties for sibling companies.
    """
    signals = _extract_entity_signals(scraped, url, raw_html)
    empty = {
        "text": "", "url": "", "structured": {},
        "match_score": 0, "match_confidence": "Low",
        "match_reason": "No confident MCA match",
        "alternatives": [], "entity_signals": signals,
    }

    seen_urls = set()
    candidates = []

    def _evaluate(page: dict):
        u = page.get("url") or ""
        if not u or u in seen_urls:
            return
        seen_urls.add(u)
        struct = page.get("structured") or {}
        if not struct.get("Company Name") and not struct.get("CIN"):
            return
        score, reason = _entity_match_score(signals, struct, u)
        candidates.append({
            "url": u,
            "text": page.get("text") or "",
            "structured": struct,
            "score": score,
            "reason": reason,
            "legal_name": struct.get("Company Name") or "",
        })

    if signals.get("cin"):
        print(f"[MCA] CIN on website: {signals['cin']}")
        for u in _lookup_zauba_by_cin(signals["cin"]):
            _evaluate(_fetch_zaubacorp_page(u))

    for q in _build_zauba_queries(signals, scraped)[:4]:
        for u in _collect_zauba_candidate_urls(q)[:4]:
            _evaluate(_fetch_zaubacorp_page(u))

    # Direct MCA name search for brand expansions (find parent, not sister cos)
    from bs4 import BeautifulSoup
    for q in _build_zauba_queries(signals, scraped)[:3]:
        try:
            token = requests.utils.quote(q.upper())
            sr = requests.get(
                f"https://www.zaubacorp.com/companysearchresults/{token}",
                headers=HEADERS, timeout=12,
            )
            if sr.status_code != 200:
                continue
            soup = BeautifulSoup(sr.text, "html.parser")
            for a in soup.find_all("a", href=True)[:12]:
                href = _normalize_zauba_href(a["href"])
                if _is_zaubacorp_company_url(href):
                    _evaluate(_fetch_zaubacorp_page(href))
        except Exception as e:
            print(f"[MCA] direct search fail for '{q}': {e}")

    if not candidates:
        print(f"[MCA] No ZaubaCorp candidates for '{signals.get('domain_stem')}'")
        return empty

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Auto-reject obvious subsidiaries before spending LLM calls
    filtered = []
    for cand in candidates:
        legal_l = (cand.get("legal_name") or "").lower()
        if re.search(r"\be[\s\-]?serve\b", legal_l) or any(t in legal_l for t in ("agro", "foundation", "trust", "welfare")):
            # keep only if website itself is that niche
            site_l = ((scraped.get("title") or "") + " " + (scraped.get("description") or "")).lower()
            if not any(t in site_l for t in ("e-serve", "eserve", "agro", "foundation")):
                print(f"[MCA] auto-skip subsidiary-like '{cand['legal_name']}'")
                continue
        filtered.append(cand)
    if filtered:
        candidates = filtered

    # LLM-as-judge: never accept a registry entity the judge rejects
    from backend.services import llm_judge
    brand = (signals.get("domain_stem") or "Company").replace("-", " ").title()
    accepted = None
    for cand in candidates[:4]:
        if cand["score"] < (_MCA_CONF_MED - 50):
            continue
        legal_l = (cand.get("legal_name") or "").lower()
        stem = (signals.get("domain_stem") or "").lower()
        # Fast path: strong brand match, no subsidiary tokens → accept without LLM
        strong = (
            cand["score"] >= _MCA_CONF_HIGH
            and stem
            and stem in legal_l
            and not re.search(r"\be[\s\-]?serve\b", legal_l)
            and not any(t in legal_l for t in ("foundation", "trust", "welfare", "agro"))
        )
        if strong:
            accepted = cand
            accepted["judge"] = {
                "accept": True,
                "confidence": "High",
                "preferred_display_name": brand,
                "reason": "Strong heuristic brand/legal match (LLM skipped for speed)",
                "is_subsidiary_or_sister": False,
            }
            print(f"[MCA] strong-match accept '{cand['legal_name']}' score={cand['score']}")
            break
        if "Subsidiary/sister token" in (cand.get("reason") or "") and cand["score"] < _MCA_CONF_MED:
            continue
        verdict = llm_judge.judge_entity_match(
            website_url=url,
            domain=signals.get("domain") or "",
            brand_name=brand,
            site_title=scraped.get("title") or "",
            site_description=scraped.get("description") or "",
            site_about_excerpt=(scraped.get("about_text") or scraped.get("homepage_text") or "")[:900],
            candidate={
                "legal_name": cand["legal_name"],
                "cin": (cand.get("structured") or {}).get("CIN") or "",
                "score": cand["score"],
                "reason": cand["reason"],
            },
        )
        print(f"[MCA Judge] '{cand['legal_name']}' accept={verdict.get('accept')} — {verdict.get('reason')}")
        if verdict.get("accept") and str(verdict.get("confidence", "")).lower() in ("high", "medium"):
            accepted = cand
            accepted["judge"] = verdict
            break

    alts = [
        {"legal_name": c["legal_name"], "score": c["score"], "url": c["url"]}
        for c in candidates[:4]
        if not accepted or c["url"] != accepted["url"]
    ]

    if not accepted:
        best = candidates[0] if candidates else {"legal_name": "", "score": 0, "reason": "none"}
        print(
            f"[MCA] Judge rejected all candidates (best was '{best.get('legal_name')}' "
            f"score {best.get('score')}) — hiding directors/registry"
        )
        return {
            **empty,
            "alternatives": alts,
            "match_reason": f"No judge-approved MCA match (best: {best.get('reason')})",
            "match_score": best.get("score") or 0,
            "preferred_display_name": brand,
        }

    best = accepted
    conf = "High" if best["score"] >= _MCA_CONF_HIGH and str((best.get("judge") or {}).get("confidence")).lower() == "high" else "Medium"
    print(
        f"[MCA] Matched '{best['legal_name']}' "
        f"(score {best['score']}, {conf}) — {best['reason']}"
    )
    return {
        "text": best["text"],
        "url": best["url"],
        "structured": best["structured"],
        "match_score": best["score"],
        "match_confidence": conf,
        "match_reason": best["reason"] + " | judge: " + ((best.get("judge") or {}).get("reason") or ""),
        "alternatives": alts,
        "entity_signals": signals,
        "preferred_display_name": ((best.get("judge") or {}).get("preferred_display_name") or brand),
    }


def _normalize_director_row(name: str, din: str, designation: str) -> dict | None:
    name = re.sub(r"\s+", " ", (name or "").strip())
    din = re.sub(r"\s+", " ", (din or "").strip())
    designation = (designation or "Director").strip() or "Director"
    # DIN column often appears first (5-8 digits)
    if re.match(r"^\d{5,8}$", name) and din and not re.match(r"^\d{5,8}$", din):
        name, din = din, name
    if not name or len(name) < 3 or "paid company" in name.lower():
        return None
    if re.match(r"^\d{5,8}$", name):
        return None
    return {"name": name, "din": din, "designation": designation}


def _scrape_zaubacorp(company_name_or_domain: str) -> dict:
    """
    Search ZaubaCorp for the company and scrape official MCA data:
    CIN, incorporation date, registered address, directors, capital, status.
    Returns {"text": str, "url": str, "structured": dict}
    """
    from bs4 import BeautifulSoup

    result = {"text": "", "url": "", "structured": {}}
    search_name = company_name_or_domain.replace("-", " ").replace("_", " ").strip()
    if not search_name or len(search_name) < 2:
        return result

    zauba_url = None
    candidate_urls = []

    def _collect_url(href: str):
        href = _normalize_zauba_href(href)
        if _is_zaubacorp_company_url(href) and href not in candidate_urls:
            candidate_urls.append(href)

    # Step 1: DuckDuckGo — accept modern slug URLs (not just /company/)
    for q in [
        f"site:zaubacorp.com {search_name}",
        f"site:zaubacorp.com {search_name} CIN",
        f"zaubacorp {search_name} private limited",
    ]:
        for r in _ddg_search(q, max_results=8):
            _collect_url(r.get("href", ""))

    # Step 2: ZaubaCorp companysearchresults (reliable for Indian companies)
    from bs4 import BeautifulSoup
    for token in _meaningful_tokens(search_name)[:3]:
        try:
            sr = requests.get(
                f"https://www.zaubacorp.com/companysearchresults/{token.upper()}",
                headers=HEADERS, timeout=15,
            )
            if sr.status_code != 200:
                continue
            for a in BeautifulSoup(sr.text, "html.parser").find_all("a", href=True):
                _collect_url(a["href"])
        except Exception as e:
            print(f"[ZaubaCorp] companysearchresults/{token} failed: {e}")

    # Step 3: company-list fallback
    try:
        search_url = (
            f"https://www.zaubacorp.com/company-list/p-1/q-"
            f"{requests.utils.quote(search_name)}"
        )
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        qtokens = _meaningful_tokens(search_name)
        ranked = []
        for a in soup.find_all("a", href=True):
            full = _normalize_zauba_href(a["href"])
            if not _is_zaubacorp_company_url(full):
                continue
            link_text = a.get_text(" ", strip=True).lower()
            score = sum(25 for t in qtokens if t in link_text) + sum(15 for t in qtokens if t in full.lower())
            ranked.append((score, full))
        ranked.sort(key=lambda x: x[0], reverse=True)
        for score, href in ranked[:8]:
            if score >= 25:
                _collect_url(href)
        if not candidate_urls and qtokens:
            for m in re.finditer(
                rf"zaubacorp\.com/([A-Z0-9\-]*{re.escape(qtokens[0].upper())}[A-Z0-9\-]*PTC\d+)",
                resp.text, re.I,
            ):
                _collect_url(f"https://www.zaubacorp.com/{m.group(1)}")
    except Exception as e:
        print(f"[ZaubaCorp] Direct search failed: {e}")

    # Step 4: Pick best candidate by fetching lightweight CIN/name check
    best = {"score": 0, "url": "", "data": None}
    for url in candidate_urls[:8]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            quick_soup = BeautifulSoup(resp.text, "html.parser")
            quick_struct = _parse_zaubacorp_jsonld(quick_soup)
            if not quick_struct.get("Company Name"):
                h1 = quick_soup.find("h1")
                if h1:
                    quick_struct["Company Name"] = h1.get_text(strip=True)
            score = _zauba_match_score(search_name, url, quick_struct)
            if score > best["score"]:
                best = {"score": score, "url": url, "data": (resp, quick_soup, quick_struct)}
        except Exception:
            continue

    if best["score"] >= 25:
        zauba_url = best["url"]
        cached = best["data"]
    elif candidate_urls and _meaningful_tokens(search_name):
        # Last resort: first slug hit containing primary token
        primary = _meaningful_tokens(search_name)[0]
        zauba_url = next((u for u in candidate_urls if primary in u.lower()), "")
        cached = None
    else:
        zauba_url = ""
        cached = None

    if not zauba_url:
        print(f"[ZaubaCorp] No page found for '{search_name}'")
        return result

    result["url"] = zauba_url
    print(f"[ZaubaCorp] Scraping: {zauba_url} (match score {best['score']})")

    try:
        if cached:
            resp, soup, structured = cached[0], cached[1], dict(cached[2])
        else:
            resp = requests.get(zauba_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            structured = _parse_zaubacorp_jsonld(soup)

        # Table-based MCA fields
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                value = cells[1].get_text(strip=True)
                if key and value and len(key) < 60 and "paid company" not in value.lower():
                    if key not in structured or len(value) > len(str(structured.get(key, ""))):
                        structured[key] = value

        field_map = {
            "CIN": ["cin", "CIN"],
            "Company Name": ["company-name", "company_name"],
            "Status": ["company-status"],
            "Date of Incorporation": ["date-of-incorporation"],
            "Registered Address": ["registered-address"],
            "Authorized Capital": ["authorized-capital"],
            "Paid Up Capital": ["paid-up-capital"],
            "RoC": ["roc"],
        }
        for label, ids in field_map.items():
            for id_ in ids:
                el = soup.find(id=id_) or soup.find(class_=id_)
                if el and not structured.get(label):
                    structured[label] = el.get_text(strip=True)
                    break

        # Directors from tables
        directors = list(structured.get("Directors") or [])
        for table in soup.find_all("table"):
            header = table.find("tr")
            if not header or not re.search(r"director|din|designation", header.get_text(), re.I):
                continue
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    rec = _normalize_director_row(
                        cols[0].get_text(strip=True),
                        cols[1].get_text(strip=True) if len(cols) > 1 else "",
                        cols[2].get_text(strip=True) if len(cols) > 2 else "Director",
                    )
                    if rec:
                        directors.append(rec)
            if directors:
                break

        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        full_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:8000]

        # Prose + director regex (fills gaps when tables are paywalled)
        prose = _parse_zaubacorp_prose(full_text)
        for k, v in prose.items():
            if k == "Directors":
                if not directors:
                    directors = v
            elif not structured.get(k) or "not publicly" in str(structured.get(k, "")).lower():
                structured[k] = v

        if directors:
            seen_names = set()
            deduped = []
            for d in directors:
                n = re.sub(r"\s+", " ", d.get("name", "").strip())
                if n and n.lower() not in seen_names:
                    seen_names.add(n.lower())
                    deduped.append({**d, "name": n, "source": "ZaubaCorp MCA", "confidence": "High"})
            structured["Directors"] = deduped

        result["structured"] = structured
        result["text"] = full_text
        print(f"[ZaubaCorp] Got {len(structured)} fields, {len(structured.get('Directors') or [])} directors")

    except Exception as e:
        print(f"[ZaubaCorp] Scrape error: {e}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# POSTAL ADDRESS EXTRACTION — pattern based, no hard-coded city list
# ─────────────────────────────────────────────────────────────────────────────

# A postal address almost always ends in a recognisable postcode token.
_ADDR_TAIL = re.compile(
    r"(?:"
    r"\b\d{6}\b"                                         # India PIN
    r"|\b(?:[A-Z]{2}|[A-Z][a-z]{2,})\s+\d{5}(?:-\d{4})?\b"  # "CA 94105", "California 94105"
    r"|\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b"            # UK postcode
    r"|\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b"                     # Canada postcode
    r"|\b\d{5}\s+[A-Z][a-zA-Z]{2,}\b"                    # "10115 Berlin"
    r")"
)
_ADDR_STREET = re.compile(
    r"(?i)\b(?:road|rd\.?|street|st\.?|floor|flr|suite|avenue|ave\.?|lane|marg|nagar|"
    r"sector|block|tower|plaza|park|chambers|building|bldg|complex|estate|highway|"
    r"drive|boulevard|blvd|circle|court|plot|survey|phase|wing|premises|house|centre|center)\b"
)
_ADDR_HINT = re.compile(
    r"(?i)\b(?:head\s*office|headquarters?|hq|registered\s*office|corporate\s*office|"
    r"global\s*(?:hq|headquarters)|main\s*office|principal\s*place)\b"
)
# Lines that look like postal addresses but are navigation, legal or marketing noise
_ADDR_REJECT = re.compile(
    r"(?i)(copyright|\u00a9|all rights reserved|privacy policy|terms of|cookie|"
    r"@[a-z0-9.-]+\.[a-z]{2,}|https?://|\bgst\b|\bcin\b|\bpan\b|"
    r"\b(?:port|version|build|error|sku|invoice|order|ticket|revision)\b\s*[:#]|"
    r"\be\.?g\.?\b|\bport\s+(?:number|is|used)\b|"
    # Registration, patent and certificate numbers look exactly like postcodes
    r"\bpatent\b|\biso\s*\d|\bno\.\s*\d|\b(?:reg|registration|licen[cs]e|cert)\w*\.?\s*(?:no|number)\b)"
)


def _extract_addresses(text: str, max_out: int = 8) -> list:
    """
    Pull postal addresses from line-structured page text.

    Anchors on a postcode, then walks backwards over continuation lines so that
    addresses broken across several DOM nodes are rejoined, and keeps a short
    preceding header line (``MUMBAI``, ``Head Office``) as a location label.
    """
    if not text:
        return []
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    out, seen = [], set()

    for i, line in enumerate(lines):
        if len(line) > 260 or not _ADDR_TAIL.search(line):
            continue
        if _ADDR_REJECT.search(line):
            continue

        chunk = [line]
        j = i - 1
        while j >= 0 and len(chunk) < 4:
            prev = lines[j]
            if len(prev) > 120 or _ADDR_REJECT.search(prev):
                break
            if ("," in prev) or _ADDR_STREET.search(prev) or re.match(r"^\d+[\w\-/]*\s", prev):
                chunk.insert(0, prev)
                j -= 1
                continue
            break

        body = re.sub(r"\s+", " ", " ".join(chunk)).strip(" ,;|")
        # Require street-level evidence: a street word, or enough comma-separated
        # parts to be an address. Otherwise headlines and footers with a stray
        # number ("© 2026 Postman, Inc.") get read as offices.
        if len(body) < 18 or not re.search(r"\d", body):
            continue
        if not _ADDR_STREET.search(body) and body.count(",") < 2:
            continue

        header = ""
        if j >= 0:
            prev = lines[j].strip(" :–—-")
            is_label = 2 < len(prev) <= 40 and not re.search(r"\d{4}", prev)
            if is_label and (prev.isupper() or _ADDR_HINT.search(prev)):
                header = prev

        addr = f"{header} — {body}" if header else body
        key = re.sub(r"[^a-z0-9]", "", addr.lower())[:60]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(addr[:220])
        if len(out) >= max_out:
            break
    return out


def _addresses_from_jsonld(raw_html: str) -> list:
    """Read schema.org PostalAddress blocks, which many CMS themes emit on contact pages."""
    if not raw_html:
        return []
    out = []

    def _walk(node):
        if isinstance(node, list):
            for n in node:
                _walk(n)
            return
        if not isinstance(node, dict):
            return
        addr = node.get("address")
        for cand in (addr if isinstance(addr, list) else [addr]):
            if isinstance(cand, str) and len(cand) > 18:
                out.append(re.sub(r"\s+", " ", cand).strip()[:220])
            elif isinstance(cand, dict):
                parts = [
                    cand.get("streetAddress"), cand.get("addressLocality"),
                    cand.get("addressRegion"), cand.get("postalCode"),
                    cand.get("addressCountry") if isinstance(cand.get("addressCountry"), str) else "",
                ]
                joined = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
                if len(joined) > 18:
                    out.append(re.sub(r"\s+", " ", joined)[:220])
        for v in node.values():
            if isinstance(v, (dict, list)):
                _walk(v)

    for m in re.finditer(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', raw_html):
        try:
            _walk(json.loads(m.group(1).strip()))
        except Exception:
            continue
    return list(dict.fromkeys(out))[:6]


def _pick_headquarters(addresses: list) -> str:
    """Choose the HQ from a list of office addresses: explicit HQ label wins, else the first."""
    for a in addresses or []:
        if _ADDR_HINT.search(a or ""):
            return a
    return (addresses or [""])[0]


# ─────────────────────────────────────────────────────────────────────────────
# CONTACT INTELLIGENCE — extract emails, phones with person names
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_contact_page(origin: str, raw_html: str = "", homepage_soup=None,
                         discovered: list | None = None,
                         extra_texts: list | None = None) -> dict:
    """
    Scrape homepage HTML + contact pages for phones/emails/addresses WITH person names.
    Uses raw HTML first (footer is often where contacts live), then any contact URLs
    discovered from the site's own navigation before falling back to guessed paths.
    """
    from bs4 import BeautifulSoup

    contact = {
        "phones": [],
        "emails": [],
        "address": "",
        "addresses": [],
        "whatsapp": "",
        "toll_free": "",
        "source_pages": [],
    }

    email_pat = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    # Indian + international: +91 98672 00065, 9867200065, (022) 1234 5678
    phone_pat = re.compile(
        r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{3,5}(?:[\s\-]?\d{2,5})?"
    )
    # "Suresh Shriyan: +91 98672 00065" or "Suresh Shriyan +91 ..."
    name_phone_pat = re.compile(
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z\.]+){0,3})\s*[:\-]?\s*"
        r"((?:\+?\d[\d\s\-().]{8,}\d))"
    )
    # email local-part often has name: suresh.shriyan@...
    name_from_email = re.compile(r"^([a-zA-Z]+(?:[._\-][a-zA-Z]+)+)@")

    def _is_valid_phone(num: str) -> bool:
        raw = (num or "").strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10 or len(digits) > 15:
            return False
        if re.search(r"\d+\.\d+\s*-\d+", raw):
            return False
        if re.search(r"\.\d{2}", raw) and ("-" in raw or "(" in raw):
            return False
        if digits.startswith("20") and len(digits) <= 8:
            return False
        if not (raw.startswith("+") or digits.startswith(("91", "0", "6", "7", "8", "9"))):
            return False
        return True

    def _dept_label(txt: str, fallback="General") -> str:
        t = (txt or "").lower()
        if any(w in t for w in ["career", "hr", "recruit", "hiring", "job"]):
            return "HR / Careers"
        if any(w in t for w in ["enquir", "inquiry", "sales", "business", "purchase"]):
            return "Business Enquiries"
        if any(w in t for w in ["support", "help", "service", "assist"]):
            return "Support"
        if any(w in t for w in ["export", "international", "overseas"]):
            return "Export / International"
        if any(w in t for w in ["media", "press", "pr "]):
            return "Media / PR"
        if any(w in t for w in ["finance", "account", "billing"]):
            return "Finance / Accounts"
        if any(w in t for w in ["get in touch", "contact", "reach"]):
            return "Get In Touch"
        return fallback

    def _person_near_phone(block: str, phone: str) -> str:
        """Find a person name next to this phone in the text block."""
        # Direct pattern Name: phone
        for m in name_phone_pat.finditer(block):
            if re.sub(r"\D", "", m.group(2)) == re.sub(r"\D", "", phone):
                name = m.group(1).strip()
                # reject department words as names
                if name.lower() not in ("office", "mumbai", "contact", "phone", "mobile",
                                        "call", "whatsapp", "india", "address", "email"):
                    return name
        # Look at text immediately before the phone
        idx = block.find(phone)
        if idx > 0:
            before = block[max(0, idx - 60):idx].strip()
            m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z\.]+){1,3})\s*[:\-]?\s*$", before)
            if m:
                return m.group(1).strip()
        return ""

    seen_addr = set()

    def _parse_html(html: str, page_label: str):
        if not html:
            return
        soup = BeautifulSoup(html, "html.parser")
        # Keep footer/header — that is where contacts usually live
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        found_e, found_p = set(), set()

        # mailto:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if email and email not in found_e and "example" not in email:
                    found_e.add(email)
                    parent_txt = a.parent.get_text(" ", strip=True)[:200] if a.parent else ""
                    label = _dept_label(parent_txt + " " + a.get_text())
                    # Derive person from email local part
                    person = ""
                    m = name_from_email.match(email)
                    if m:
                        person = m.group(1).replace(".", " ").replace("_", " ").replace("-", " ").title()
                    contact["emails"].append({
                        "email": email,
                        "label": f"{person} ({label})" if person else label,
                        "person": person,
                        "source": page_label,
                        "confidence": "High",
                        "verified": True,
                    })

        # tel:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("tel:"):
                num = href.replace("tel:", "").strip()
                if _is_valid_phone(num):
                    key = re.sub(r"\D", "", num)
                    if key not in found_p:
                        found_p.add(key)
                        parent_txt = a.parent.get_text(" ", strip=True)[:200] if a.parent else ""
                        person = _person_near_phone(parent_txt, num)
                        label = person if person else _dept_label(parent_txt)
                        contact["phones"].append({
                            "number": num,
                            "label": label,
                            "person": person,
                            "source": page_label,
                            "confidence": "High",
                            "verified": True,
                        })

        # Full page text patterns (footer "Get In Touch" blocks)
        page_text = soup.get_text("\n", strip=True)

        # Name: phone pairs
        for m in name_phone_pat.finditer(page_text):
            name, num = m.group(1).strip(), m.group(2).strip()
            if not _is_valid_phone(num):
                continue
            key = re.sub(r"\D", "", num)
            if key in found_p:
                # upgrade label with person name if missing
                for p in contact["phones"]:
                    if re.sub(r"\D", "", p["number"]) == key and not p.get("person"):
                        p["person"] = name
                        p["label"] = name
                continue
            found_p.add(key)
            if name.lower() in ("office", "mumbai", "contact", "phone", "mobile", "india"):
                continue
            contact["phones"].append({
                "number": num,
                "label": name,
                "person": name,
                "source": page_label,
                "confidence": "High",
                "verified": True,
            })

        # Plain emails in text
        for email in _find_emails(page_text):
            email = email.lower()
            if email in found_e or "example" in email or "domain.com" in email:
                continue
            if email.endswith((".png", ".jpg", ".css", ".js")):
                continue
            found_e.add(email)
            person = ""
            m = name_from_email.match(email)
            if m:
                person = m.group(1).replace(".", " ").replace("_", " ").replace("-", " ").title()
            # Find surrounding context for department
            idx = page_text.lower().find(email)
            ctx = page_text[max(0, idx - 80):idx + len(email) + 40] if idx >= 0 else ""
            label = _dept_label(ctx)
            contact["emails"].append({
                "email": email,
                "label": f"{person} ({label})" if person else label,
                "person": person,
                "source": page_label,
                "confidence": "High",
                "verified": True,
            })

        # Plain phones not yet captured
        for m in phone_pat.finditer(page_text):
            num = m.group(0).strip()
            if not _is_valid_phone(num):
                continue
            key = re.sub(r"\D", "", num)
            if key in found_p:
                continue
            # Must look like a phone (has + or starts with 0/9/8/7 for India mobiles)
            digits = key
            if not (num.strip().startswith("+") or digits.startswith(("91", "0", "6", "7", "8", "9"))):
                continue
            if len(digits) < 10:
                continue
            found_p.add(key)
            ctx = page_text[max(0, m.start() - 60):m.end() + 20]
            person = _person_near_phone(ctx, num)
            contact["phones"].append({
                "number": num,
                "label": person if person else _dept_label(ctx),
                "person": person,
                "source": page_label,
                "confidence": "Medium",
                "verified": True,
            })

        # Addresses — postcode-anchored patterns + schema.org, not a city whitelist
        for addr in _extract_addresses(page_text) + _addresses_from_jsonld(html):
            key = re.sub(r"[^a-z0-9]", "", addr.lower())[:60]
            if key and key not in seen_addr:
                seen_addr.add(key)
                contact["addresses"].append(addr)

        # WhatsApp / toll-free
        wp = re.search(r"whatsapp[^\d]*(\+?[\d\s\-]{8,})", page_text, re.I)
        if wp and not contact["whatsapp"]:
            contact["whatsapp"] = wp.group(1).strip()
        tf = re.search(r"(?:toll.?free|1800)[^\d]*(\+?[\d\s\-]{6,})", page_text, re.I)
        if tf and not contact["toll_free"]:
            contact["toll_free"] = tf.group(0).strip()

    # 1) Parse RAW homepage HTML (footer intact)
    if raw_html:
        _parse_html(raw_html, "Homepage / Footer")
        contact["source_pages"].append(origin)

    # 2) Contact pages — links found in the nav/footer first, then conventional paths
    guesses = (
        ["/contact", "/contact-us"]
        if not RESEARCH_DEEP
        else ["/contact", "/contact-us", "/contactus", "/reach-us",
              "/get-in-touch", "/about/contact", "/connect"]
    )
    contact_urls = list(dict.fromkeys(
        list(discovered or []) + [origin + p for p in guesses]
    ))[:6]

    def _fetch_contact(target: str):
        try:
            fetched = _fetch_public_profile_page(target, timeout=5)
            html = str(fetched.get("html") or "")
            final_url = str(fetched.get("url") or target)
            if len(html) <= 500:
                return target, None
            # /contact often 302s to an unrelated marketing page — drop those
            if not _redirect_ok(target, final_url, "contact_text"):
                print(f"[Contact] Ignored off-target redirect {target} -> {final_url}")
                return target, None
            return final_url, html
        except Exception:
            pass
        return target, None

    if not contact["addresses"] or not (contact["emails"] or contact["phones"]):
        with ThreadPoolExecutor(max_workers=min(6, len(contact_urls))) as pool:
            for final_url, html in pool.map(_fetch_contact, contact_urls):
                if html:
                    _parse_html(html, "Contact page")
                    contact["source_pages"].append(final_url)
                    print(f"[Contact] Scraped {final_url}")
                    if not RESEARCH_DEEP and contact["addresses"] and (contact["emails"] or contact["phones"]):
                        break

    # 3) Fallback soup if provided
    if homepage_soup and not contact["emails"] and not contact["phones"]:
        _parse_html(str(homepage_soup), "Homepage soup")

    # 4) Last resort — some sites only print the address on the about page
    if not contact["addresses"]:
        for txt in extra_texts or []:
            for addr in _extract_addresses(txt):
                key = re.sub(r"[^a-z0-9]", "", addr.lower())[:60]
                if key not in seen_addr:
                    seen_addr.add(key)
                    contact["addresses"].append(addr)

    contact["address"] = _pick_headquarters(contact["addresses"])

    # Dedup
    seen_e, seen_p = set(), set()
    contact["emails"] = [
        e for e in contact["emails"]
        if e["email"] not in seen_e and not seen_e.add(e["email"])
    ][:20]
    contact["phones"] = [
        p for p in contact["phones"]
        if re.sub(r"\D", "", p["number"]) not in seen_p
        and not seen_p.add(re.sub(r"\D", "", p["number"]))
    ][:20]

    print(f"[Contact] Found {len(contact['emails'])} emails, {len(contact['phones'])} phones")
    return contact


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Deep Website Scraper (homepage + sub-pages)
# ─────────────────────────────────────────────────────────────────────────────

# Path/anchor tokens that identify a content bucket, with a specificity weight.
# Used both to discover real URLs from site navigation and to detect off-target redirects.
_PAGE_INTENT_TOKENS = {
    "about_text": (("about", 10), ("who-we-are", 10), ("our-story", 9), ("company-profile", 9),
                   ("overview", 6), ("company", 3), ("who we are", 9), ("our story", 9)),
    "leadership_text": (("leadership", 10), ("management-team", 10), ("our-team", 9),
                        ("board-of-directors", 10), ("investor-relations", 8), ("investors", 6),
                        ("executive", 9), ("founders", 9), ("management", 8), ("team", 7),
                        ("people", 6), ("board", 6), ("leadership team", 10), ("our team", 9),
                        ("about", 2)),
    "contact_text": (("contact", 10), ("get-in-touch", 9), ("reach-us", 9), ("locations", 7),
                     ("offices", 7), ("get in touch", 9), ("contact us", 10), ("office", 5),
                     ("support", 4), ("help", 3)),
    "products_text": (("products", 9), ("services", 9), ("solutions", 8), ("platform", 7),
                      ("offerings", 7), ("what-we-do", 8), ("what we do", 8)),
    "careers_text": (("careers", 10), ("jobs", 9), ("join-us", 8), ("work-with-us", 8),
                     ("openings", 7), ("join us", 8)),
    "pricing_text": (("pricing", 10), ("plans", 7), ("price", 6)),
    "blog_text": (("blog", 9), ("news", 8), ("insights", 7), ("press", 7)),
}
# Content hubs whose deep URLs (case studies, webinars, solution pages) routinely
# contain words like "management" or "team" without being company pages.
_NOISE_SECTIONS = {
    "solutions", "solution", "resources", "resource", "blog", "blogs", "news",
    "case-studies", "case-study", "webinars", "webinar", "industry", "industries",
    "function", "functions", "events", "press", "insights", "whitepapers", "ebooks",
}


def _fetch_page_full(url: str, timeout: int = 15) -> dict:
    """Fetch a URL once and return flat text, line-structured text, final URL and status."""
    out = {"text": "", "lines": "", "final_url": url, "status": 0, "html": ""}
    try:
        from bs4 import BeautifulSoup
        fetched = _fetch_public_profile_page(url, timeout=min(max(int(timeout), 2), 16))
        html = str(fetched.get("html") or "")
        if not html:
            return out
        out["status"] = 200
        out["final_url"] = str(fetched.get("url") or url)
        out["html"] = html
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        # Keep block boundaries: team cards render as "Name\nRole" with no separator char
        lines = soup.get_text(separator="\n", strip=True)
        lines = re.sub(r"[ \t\xa0]+", " ", lines)
        out["lines"] = re.sub(r"\n\s*\n+", "\n", lines).strip()[:14000]
        out["text"] = re.sub(r"\s+", " ", out["lines"])[:5000]
    except Exception:
        pass
    return out


def _fetch_page(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return cleaned single-line text."""
    return _fetch_page_full(url, timeout).get("text") or ""


def _redirect_ok(requested: str, final_url: str, intent_key: str) -> bool:
    """
    Reject silent redirects that land somewhere unrelated.

    Plenty of sites 302 an unknown path like /contact onto a marketing page, which
    then gets scraped as if it were the contact page.
    """
    try:
        req_path = urlparse(requested).path.strip("/").lower()
        fin_path = urlparse(final_url).path.strip("/").lower()
    except Exception:
        return True
    if not fin_path or fin_path == req_path or (req_path and req_path in fin_path):
        return True
    return any(tok in fin_path for tok, _ in _PAGE_INTENT_TOKENS.get(intent_key, ()))


def _discover_site_pages(homepage_html: str, origin: str) -> dict:
    """
    Map the site's own nav/footer links onto content buckets.

    Guessing paths misses anything nested (``/company/about-us``), which is where a
    lot of mid-market sites keep their about, leadership and contact pages.
    """
    found = {key: [] for key in _PAGE_INTENT_TOKENS}
    if not homepage_html:
        return found
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(homepage_html, "html.parser")
    except Exception:
        return found

    host = urlparse(origin).netloc.replace("www.", "").lower()
    scored = {key: {} for key in _PAGE_INTENT_TOKENS}
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        try:
            p = urlparse(urljoin(origin + "/", href))
        except Exception:
            continue
        if p.scheme not in ("http", "https"):
            continue
        if p.netloc.replace("www.", "").lower() != host:
            continue
        path = (p.path or "/").rstrip("/").lower()
        segments = [s for s in path.split("/") if s]
        if not segments or len(segments) > 3:
            continue
        if re.search(r"\.(pdf|jpe?g|png|webp|gif|zip|mp4|docx?|pptx?)$", path):
            continue
        anchor = " ".join((a.get_text(" ", strip=True) or "").lower().split())[:60]
        clean_url = f"{p.scheme}://{p.netloc}{p.path}"
        last = segments[-1]
        for key, tokens in _PAGE_INTENT_TOKENS.items():
            best = 0
            for tok, weight in tokens:
                slug = tok.replace(" ", "-")
                if last == slug or last.replace("-", "") == slug.replace("-", ""):
                    best = max(best, weight + 4)
                elif slug in last and len(slug) / len(last) >= 0.5:
                    # "about-us", "our-team" — the token still dominates the slug
                    best = max(best, weight)
                elif slug in segments[:-1]:
                    best = max(best, weight - 1)
                elif tok in anchor:
                    best = max(best, weight - 3)
            # A marketing/content section rarely holds the company's own about or team page
            if best and segments[0] in _NOISE_SECTIONS and key not in ("products_text", "blog_text"):
                best -= 6
            if best > 0:
                # Shallow hub pages beat deep ones at the same token strength
                score = best * 10 - len(segments)
                if score > scored[key].get(clean_url, 0):
                    scored[key][clean_url] = score

    for key, urls in scored.items():
        found[key] = [u for u, _ in sorted(urls.items(), key=lambda kv: -kv[1])][:4]
    return found


def _scrape_one_subpage(origin: str, key: str, candidates: list, timeout: int = 6) -> tuple:
    """Try candidate URLs for one content bucket; return (key, flat_text, lines_text, url)."""
    limit = 2 if not RESEARCH_DEEP else 4
    for cand in candidates[:limit]:
        target = cand if cand.startswith("http") else origin + cand
        page = _fetch_page_full(target, timeout=timeout)
        if page["status"] != 200 or len(page["text"]) <= 300:
            continue
        if not _redirect_ok(target, page["final_url"], key):
            print(f"[Research] Ignored off-target redirect {target} -> {page['final_url']}")
            continue
        return key, page["text"], page["lines"], page["final_url"]
    return key, "", "", ""


def _scrape_website(url: str, include_wiki: bool = False) -> dict:
    """Scrape homepage + key sub-pages for maximum context."""
    from bs4 import BeautifulSoup

    result = {
        "url": url, "title": "", "description": "", "keywords": "",
        "homepage_text": "", "about_text": "", "products_text": "",
        "pricing_text": "", "careers_text": "", "blog_text": "",
        "leadership_text": "", "nav_links": [], "social_links": [],
        "emails": [], "phones": [], "tech_hints": [],
        "_homepage_reachable": False, "_homepage_status": None,
        "_site_parked": False,
        "_structured": {}, "_page_urls": {},
    }

    base = url.rstrip("/")
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    _homepage_raw = ""   # keep raw HTML for contact scraper (footer intact)

    # ── Homepage ──────────────────────────────────────────────────────
    try:
        home_timeout = 8
        resp = _fetch_public_profile_page(url, timeout=home_timeout)
        homepage_html = str(resp.get("html") or "")
        if not homepage_html:
            raise ValueError("The public homepage could not be fetched")
        result["_homepage_reachable"] = True
        result["_homepage_status"] = 200
        result["_homepage_final_url"] = str(resp.get("url") or url)
        _homepage_raw = homepage_html
        soup = BeautifulSoup(homepage_html, "html.parser")

        result["title"] = (soup.title.string or "").strip()
        for tag in soup.find_all("meta"):
            name = tag.get("name","").lower()
            prop = tag.get("property","").lower()
            content = tag.get("content","")
            if name in ("description",) or prop in ("og:description",):
                result["description"] = content[:600]
            if name == "keywords":
                result["keywords"] = content[:300]
            if prop == "og:site_name" and content:
                result["og_site_name"] = content.strip()[:120]

        # Tech stack hints from scripts/links
        tech_hints = set()
        for s in soup.find_all("script", src=True):
            src = s["src"]
            for tech in ["react","angular","vue","gatsby","next","wordpress",
                         "shopify","hubspot","salesforce","marketo","segment",
                         "google-analytics","gtag","intercom","zendesk"]:
                if tech in src.lower():
                    tech_hints.add(tech.title())
        result["tech_hints"] = list(tech_hints)

        # Social links
        result["social_links"] = list({
            a["href"] for a in soup.find_all("a", href=True)
            if a.get("href") and auth.host_is_social(a["href"])
        })[:12]

        # Nav links
        result["nav_links"] = list({
            a.get_text(strip=True)
            for a in soup.find_all("a", href=True)
            if a.get_text(strip=True) and len(a.get_text(strip=True)) < 40
        })[:40]

        # Emails & phones (quick pass from raw HTML before footer is removed)
        email_pat = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        result["emails"] = _find_emails(homepage_html)[:10]

        # Clean homepage body text for LLM (footer removed here only for body_text)
        soup_body = BeautifulSoup(homepage_html, "html.parser")
        for tag in soup_body(["script","style","nav","footer","header","noscript"]):
            tag.decompose()
        home_lines = re.sub(r"[ \t\xa0]+", " ", soup_body.get_text(separator="\n", strip=True))
        home_lines = re.sub(r"\n\s*\n+", "\n", home_lines).strip()
        result["_structured"]["homepage_text"] = home_lines[:14000]
        result["homepage_text"] = re.sub(r"\s+", " ", home_lines)[:6000]

    except Exception as e:
        print(f"[Research] Homepage scrape failed: {e}")

    # Detect WAF / bot-block pages — these poison brand naming if used as title
    result["_scrape_blocked"] = _is_blocked_page_text(
        result.get("title") or "", result.get("homepage_text") or ""
    )
    result["_site_parked"] = _is_parked_page_text(
        result.get("title") or "", result.get("homepage_text") or ""
    )
    if result["_site_parked"]:
        # Do not let a domain marketplace title become the company identity or
        # allow its generic contact details into the report.
        brand = _brand_from_domain(parsed.netloc.replace("www.", ""))
        print(f"[Research] Parked domain detected — refusing synthetic report for '{brand}'")
        result["title"] = brand
        result["description"] = f"{brand} public website is unavailable (parked domain)"
        result["homepage_text"] = ""
        result["about_text"] = ""
        result["products_text"] = ""
        result["careers_text"] = ""
        result["leadership_text"] = ""
        result["contact_data"] = {"phones": [], "emails": [], "address": "", "addresses": [], "source_pages": []}
    if result["_scrape_blocked"]:
        brand = _brand_from_domain(parsed.netloc.replace("www.", ""))
        print(f"[Research] Homepage looks blocked/WAF — anchoring brand to '{brand}'")
        result["title"] = brand
        if not result.get("description"):
            result["description"] = f"{brand} corporate website ({parsed.netloc})"
        # Prefer og:site_name when present and not blocked
        og = (result.get("og_site_name") or "").strip()
        if og and not _is_blocked_page_text(og, "") and _name_matches_domain(og, parsed.netloc):
            result["title"] = og

    # ── Sub-pages: site's own nav links first, then conventional guesses ──
    discovered = _discover_site_pages(_homepage_raw, origin)
    if any(discovered.values()):
        print("[Research] Discovered nav pages: " + ", ".join(
            f"{k.replace('_text','')}={len(v)}" for k, v in discovered.items() if v
        ))

    guesses = {
        "about_text":     ["/about", "/about-us", "/company/about-us", "/corporate"],
        "products_text":  ["/products", "/services"],
        "careers_text":   ["/careers", "/jobs", "/work-with-us"],
        "leadership_text": ["/leadership", "/team", "/board-of-directors",
                            "/investor-relations", "/investors"],
    }
    if RESEARCH_DEEP:
        guesses = {
            "about_text":     ["/about", "/about-us", "/company", "/who-we-are",
                               "/investor-relations", "/investors"],
            "products_text":  ["/products", "/services", "/solutions", "/platform"],
            "pricing_text":   ["/pricing", "/plans"],
            "careers_text":   ["/careers", "/jobs", "/work-with-us"],
            "leadership_text": ["/leadership", "/team", "/management", "/executive-team"],
            "blog_text":      ["/blog", "/news"],
        }
    def _bucket_limit(key: str) -> int:
        if RESEARCH_DEEP:
            return 4
        # Listed firms bury MD/board on IR pages — keep extra leadership/about/careers slots.
        if key in ("leadership_text", "about_text", "careers_text"):
            return 4
        return 2
    sub_pages = {
        key: list(dict.fromkeys(discovered.get(key, []) + [origin + p for p in paths]))[:_bucket_limit(key)]
        for key, paths in guesses.items()
    }
    # Corporate about pages are frequently 1-2 MB; a short timeout silently loses them
    sub_timeout = 12 if not RESEARCH_DEEP else 16

    # Buckets overlap (about and leadership often resolve to the same page), so fetch
    # the deduplicated union once and let each bucket pick from the shared results.
    targets = list(dict.fromkeys(u for cands in sub_pages.values() for u in cands))
    pages = {}
    if targets:
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
            for url_, page in zip(targets, pool.map(lambda u: _fetch_page_full(u, sub_timeout), targets)):
                pages[url_] = page

    for key, cands in sub_pages.items():
        for target in cands:
            page = pages.get(target) or {}
            if page.get("status") != 200 or len(page.get("text") or "") <= 300:
                continue
            if not _redirect_ok(target, page.get("final_url") or target, key):
                print(f"[Research] Ignored off-target redirect {target} -> {page.get('final_url')}")
                continue
            result[key] = page["text"]
            result["_structured"][key] = page["lines"]
            result["_page_urls"][key] = page["final_url"]
            print(f"[Research] Scraped sub-page: {page['final_url']} ({len(page['text'])} chars) -> {key}")
            break

    # ── Contact page — deep extraction from RAW HTML (footer intact) ──
    result["contact_data"] = _scrape_contact_page(
        origin,
        raw_html=_homepage_raw,
        discovered=discovered.get("contact_text") or [],
        extra_texts=[
            result["_structured"].get("about_text") or "",
            result["_structured"].get("careers_text") or "",
        ],
    )
    print(f"[Research] Contact: {len(result['contact_data'].get('emails',[]))} emails, "
          f"{len(result['contact_data'].get('phones',[]))} phones")

    # Wikipedia is fetched in parallel from run() — optional here for back-compat
    if include_wiki:
        brand_for_wiki = _brand_from_domain(parsed.netloc.replace("www.", ""))
        wiki = _fetch_wikipedia_text(brand_for_wiki, parsed.netloc.replace("www.", ""))
        result["wikipedia_text"] = wiki.get("text") or ""
        result["wikipedia_url"] = wiki.get("url") or ""
        result["wikipedia_summary"] = wiki.get("summary") or ""
        result["wikipedia_description"] = wiki.get("description") or ""
        if wiki.get("title"):
            result["preferred_display_name"] = wiki["title"]
    else:
        result["wikipedia_text"] = ""
        result["wikipedia_url"] = ""
        result["wikipedia_summary"] = ""
        result["wikipedia_description"] = ""

    # Skip CIN / Zauba entirely — global public-web research only
    result["zaubacorp_text"] = ""
    result["zaubacorp_url"] = ""
    result["zaubacorp_structured"] = {}
    result["zauba_match_confidence"] = "Low"
    result["zauba_match_score"] = 0
    result["zauba_match_reason"] = "CIN/MCA disabled — website + public web only"
    result["zauba_alternatives"] = []
    result["entity_signals"] = {}
    if not result.get("preferred_display_name"):
        result["preferred_display_name"] = ""
    result["cin_verified"] = False
    result["verified_cin"] = ""
    print("[Research] CIN/MCA disabled — using website + public web only")

    print(f"[Research] Total website data: {sum(len(v) for v in result.values() if isinstance(v,str))} chars")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — MCP Multi-Source: Search many public sites → scrape each one
# ─────────────────────────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int = 8) -> list:
    try:
        from ddgs import DDGS
        backends = ("duckduckgo", "yahoo") if RESEARCH_FAST else ("duckduckgo", "yahoo", "auto")
        supports_backend = True
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            backends = ("auto",)
            supports_backend = False
        except ImportError as exc:
            print(f"[Research] Public search package unavailable ({type(exc).__name__})")
            return []

    failures = []
    for backend in backends:
        try:
            with _DDG_SEARCH_SEMAPHORE:
                try:
                    client = DDGS(timeout=3 if RESEARCH_FAST else 5)
                except TypeError:  # older duckduckgo_search versions
                    client = DDGS()
                with client as ddgs:
                    try:
                        rows = ddgs.text(
                            query,
                            max_results=max_results,
                            **({"backend": backend} if supports_backend else {}),
                        )
                    except TypeError:
                        # Preserve compatibility with older versions that don't
                        # accept a backend selector on text().
                        rows = ddgs.text(query, max_results=max_results)
            if rows:
                return list(rows)
        except Exception as exc:  # noqa: BLE001
            failures.append(type(exc).__name__)
    if failures:
        print(f"[Research] Public search backends failed for '{query}' ({','.join(failures[:3])})")
    return []


def _research_web_search(query: str, max_results: int = 5) -> list[dict]:
    """Use an explicitly configured research search API, otherwise free DDG."""
    api_key = os.getenv("RESEARCH_SERPAPI_KEY", "").strip()
    if api_key:
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": api_key,
                    "num": max(1, min(int(max_results), 10)),
                },
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()
            rows = []
            for item in payload.get("organic_results") or []:
                href = str(item.get("link") or "").strip()
                if not href:
                    continue
                rows.append({
                    "title": item.get("title") or "",
                    "href": href,
                    "body": item.get("snippet") or "",
                    "published_at": item.get("date") or "",
                })
                if len(rows) >= max(1, min(int(max_results), 10)):
                    break
            return rows
        except Exception as exc:  # noqa: BLE001
            # Exception strings from HTTP clients can include request URLs and
            # query parameters; do not write credentials into application logs.
            print(
                "[Research] Configured search provider failed; falling back to DDG "
                f"({type(exc).__name__})"
            )
    return _ddg_search(query, max_results=max_results)


def _ddg_news_search(query: str, max_results: int = 4) -> list:
    """Use DDGS news results when available, with public web search as fallback."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        try:
            client = DDGS(timeout=5)
        except TypeError:  # older duckduckgo_search versions
            client = DDGS()
        with client as ddgs:
            search = getattr(ddgs, "news", None)
            if callable(search):
                rows = list(search(query, max_results=max_results) or [])
                if rows:
                    return rows
    except Exception as e:
        print(f"[Research] DDG News failed for '{query}': {e}")
    # Some installed DDGS backends do not expose news(), or may temporarily
    # fail. Search snippets remain candidates only; the article page is fetched
    # and checked before anything is shown as company news.
    return _ddg_search(query, max_results=max_results)


def _is_valid_phone(num: str) -> bool:
    """Reject stock ticks / decimals / too-short fragments mistaken as phones."""
    raw = (num or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return False
    # Stock quotes like "522.90 -4.10 (-0.78)"
    if re.search(r"\.\d{2}", raw) and ("-" in raw or "(" in raw or "%" in raw):
        return False
    if raw.count(".") >= 1 and raw.count("-") >= 1 and len(digits) <= 12:
        # decimal price movement patterns
        if re.search(r"\d+\.\d+\s*-\d+", raw):
            return False
    if digits.startswith("20") and len(digits) <= 8:
        return False
    # Must look like a phone (starts with + / 0 / 91 / Indian mobile 6-9)
    if not (raw.startswith("+") or digits.startswith(("91", "0", "6", "7", "8", "9"))):
        return False
    return True


def _email_domain_ok(email: str, company_domain: str) -> bool:
    """Prefer company-domain emails; drop obvious unrelated corporate domains."""
    em = (email or "").lower().strip()
    if not em or "@" not in em:
        return False
    edom = em.split("@")[-1]
    cdom = (company_domain or "").lower().replace("www.", "")
    stem = cdom.split(".")[0] if cdom else ""
    # Always allow same domain / subdomain
    if cdom and (edom == cdom or edom.endswith("." + cdom) or stem and stem in edom):
        return True
    # Common public freemail — keep as low-confidence contact ok
    if edom in _GENERIC_EMAIL_DOMAINS:
        return True
    # Reject other companies' domains (e.g. 9xmedia.in for saregama.com)
    blocked_foreign = (
        "9xmedia", "keka.com", "googlemail", "example.com",
    )
    if any(b in edom for b in blocked_foreign):
        return False
    # If we have a company stem, require stem appear in email domain OR it's a known free mail
    if stem and len(stem) >= 4 and stem not in edom:
        # allow investor/holding domains containing brand later; for now require stem
        return False
    return True


def _wiki_page_matches_company(data: dict, company_name: str, domain: str = "") -> bool:
    """Reject wrong Wikipedia hits (songs, people, unrelated articles)."""
    extract = (data.get("extract") or data.get("summary") or "").lower()
    desc = (data.get("description") or "").lower()
    title = (data.get("title") or "").lower()
    blob = f"{title} {desc} {extract}"
    brand = (_domain_stem(domain) if domain else "") or (company_name or "").split()[0].lower()
    if not brand or len(brand) < 3:
        return False
    if brand not in blob:
        return False
    # Song / album / media-work pages often hijack brand searches
    workish = any(x in desc for x in ("song", "single by", "album", "ep by", "film", "episode", "television series"))
    orgish = any(x in blob for x in (
        "company", "label", "corporation", "limited", "ltd", "inc", "enterprise",
        "organization", "organisation", "record", "founded", "headquarter",
    ))
    if workish and not orgish:
        return False
    return True


def _fetch_wikipedia_text(company_name: str, domain: str = "") -> dict:
    """Fetch clean Wikipedia summary (API) + page text for leadership/HQ facts."""
    out = {
        "text": "", "url": "", "title": "",
        "summary": "", "description": "",
    }
    brand = _brand_from_domain(domain) if domain else (company_name or "")
    brand = re.sub(r"[^\w\s\-]", "", brand).strip() or (company_name or "").strip()

    # Prefer exact company titles before fuzzy DDG (avoids song/album collisions)
    title_candidates = []
    for t in (brand, company_name):
        t = re.sub(r"\s+", " ", (t or "").strip())
        if t and t not in title_candidates:
            title_candidates.append(t)
    if RESEARCH_DEEP:
        for t in (f"{brand} India", f"{brand}_India"):
            t = re.sub(r"\s+", " ", (t or "").strip())
            if t and t not in title_candidates:
                title_candidates.append(t)

    def _try_summary(title_guess: str) -> dict:
        api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title_guess.replace(' ', '_')}"
        resp = requests.get(api, headers=HEADERS, timeout=5)
        if not resp.ok:
            return {}
        data = resp.json() or {}
        if data.get("type") == "disambiguation":
            return {}
        extract = (data.get("extract") or "").strip()
        if len(extract) < 80:
            return {}
        if not _wiki_page_matches_company(data, company_name or brand, domain):
            return {}
        page_url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        return {
            "summary": extract[:1200],
            "description": (data.get("description") or "").strip()[:200],
            "url": page_url or api,
            "title": (data.get("title") or title_guess).replace("_", " "),
            "text": extract[:8000],
        }

    for cand in title_candidates:
        try:
            hit = _try_summary(cand)
            if hit:
                out.update(hit)
                print(f"[Research] Wikipedia summary API: {out['url']} ({len(out.get('summary') or '')} chars)")
                break
        except Exception as e:
            print(f"[Research] Wikipedia summary API failed ({cand}): {e}")

    # Direct Wikipedia REST summary only (skip slow DDG fallback unless RESEARCH_DEEP)
    if not out.get("summary") and RESEARCH_DEEP:
        queries = [
            f"site:en.wikipedia.org {brand} company OR label OR Ltd",
            f"site:en.wikipedia.org {brand}",
        ]
        for q in queries:
            for r in _ddg_search(q, max_results=5):
                href = r.get("href") or ""
                if "wikipedia.org/wiki/" not in href.lower():
                    continue
                if ":" in href.split("/wiki/")[-1]:
                    continue
                title_guess = href.rstrip("/").split("/")[-1]
                try:
                    hit = _try_summary(title_guess.replace("_", " "))
                    if hit:
                        out.update(hit)
                        wiki_url = out["url"]
                        print(f"[Research] Wikipedia via search: {out['url']}")
                        break
                except Exception:
                    continue
            if out.get("summary"):
                break

    if not out.get("summary"):
        return {"text": "", "url": "", "title": "", "summary": "", "description": ""}

    wiki_url = out.get("url") or ""
    # Extra HTML fetch only in deep mode — summary API is enough for HQ/CEO sentences
    if RESEARCH_DEEP and wiki_url and len(out.get("text") or "") < 600:
        raw = _fetch_page(wiki_url, timeout=8)
        brand_l = brand.lower()
        if raw and brand_l and brand_l in raw.lower():
            out["text"] = ((out.get("summary") or "") + "\n" + raw)[:8000]
            print(f"[Research] Wikipedia page: {wiki_url} ({len(out['text'])} chars)")

    # Final brand gate
    blob = (out.get("summary") or out.get("text") or "").lower()
    stem = _domain_stem(domain) if domain else brand.lower()
    if stem and stem not in blob and brand.lower() not in blob:
        print(f"[Research] Wikipedia rejected (brand mismatch): {out.get('url')}")
        return {"text": "", "url": "", "title": "", "summary": "", "description": ""}
    return out


def _wiki_product_hints(text: str) -> list:
    """Extract product/service names only when sources explicitly list them."""
    if not text:
        return []
    found = []
    patterns = [
        r"(?i)(?:products?(?:\s+and\s+services)?|services|offerings?|portfolio)\s+(?:include|includes|are|span)\s+([^.]+)",
        r"(?i)(?:best known for|known for)\s+([^.]+)",
        r"(?i)(?:develops?|sells?|offers?|provides?)\s+([^.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        chunk = m.group(1)
        for part in re.split(r",|;| and | & |\n|•", chunk):
            part = re.sub(r"\s+", " ", part).strip(" .")
            part = re.sub(r"(?i)^(such as|including|like)\s+", "", part)
            if 3 < len(part) < 55 and not _is_illogical_text(part):
                if part[0].isupper() or any(c.isupper() for c in part[1:]):
                    found.append(part)
            if len(found) >= 8:
                break
        if len(found) >= 6:
            break
    return found[:6]


# Words that mean the "name" is an organisation, institution or publication.
_ORG_NAME_TOKENS = {
    "sons", "group", "bank", "corp", "corporation", "institute", "institution",
    "university", "college", "school", "academy", "foundation", "trust", "society",
    "association", "council", "ministry", "department", "authority", "board",
    "committee", "fund", "capital", "partners", "ventures", "holdings", "industries",
    "enterprises", "technologies", "technology", "systems", "solutions", "services",
    "software", "labs", "consulting", "networks", "media", "press", "news", "times",
    "journal", "report", "magazine", "iit", "iim", "nit", "bits", "ieee", "limited",
    "ltd", "inc", "llc", "plc", "gmbh", "pvt", "private", "company", "team", "division",
    "global", "international", "worldwide", "ventures",
}


def _is_org_like_name(name: str) -> bool:
    """Reject "Tata Sons", "IIT Roorkee", "Ok Ok" and similar non-people."""
    toks = [re.sub(r"[^a-z]", "", t.lower()) for t in (name or "").split()]
    toks = [t for t in toks if t]
    if not toks:
        return True
    if any(t in _ORG_NAME_TOKENS for t in toks):
        return True
    if len(set(toks)) < len(toks):          # repeated word — "Ok Ok"
        return True
    return all(len(t) <= 2 for t in toks)   # initials only


def _normalize_leader_row(leader: dict, company_name: str = "", scraped: dict = None) -> dict | None:
    """Clean title fragments stuck on names; fix Founder mislabels for legacy firms."""
    if not isinstance(leader, dict):
        return None
    name = re.sub(r"\s+", " ", (leader.get("name") or "").strip(" ,;.|"))
    role = re.sub(r"\s+", " ", (leader.get("role") or "").strip(" ,;.|"))
    if not name or len(name) < 5:
        return None

    # Strip publisher / site prefixes mistaken as part of the person name.
    # "The Org" scrapes concatenate with no space: "The OrgManoj Raghavan".
    name = re.sub(r"(?i)^the\s*org\s*(?=[A-Z])", "", name).strip()
    name = re.sub(
        r"(?i)^(medianama|economictimes|crunchbase|linkedin|wikipedia|campaign\s*brief|"
        r"business\s*standard|moneycontrol|the\s*hindu|times\s*of\s*india|theorg)\s+",
        "",
        name,
    ).strip()
    # Honorifics are not part of the name
    name = re.sub(r"(?i)^(?:mr|mrs|ms|miss|dr|prof|shri|smt|sri)\.?\s+", "", name).strip()
    # Scraped cards sometimes concatenate the company brand or ticker to a
    # person's name (for example, "Satya NadellaMSFT"). Keep the person name
    # clean while leaving legitimate separated suffixes untouched.
    if company_name:
        company_l = re.sub(r"[^a-z0-9]", "", company_name.lower())
        for brand, ticker in KNOWN_TICKERS.items():
            if brand in company_l:
                name = re.sub(rf"(?i)(?<!\s){re.escape(ticker)}$", "", name).strip()
                break
        name = re.sub(rf"(?i)^{re.escape(company_name)}\s+(?=[A-Z])", "", name).strip()

    # Role hygiene: drop the company name and any "at <Company>" tail
    role = re.sub(r"(?i)\s+at\s+[A-Z][\w&.'\- ]{2,40}$", "", role).strip()
    if company_name:
        role = re.sub(rf"(?i)^{re.escape(company_name)}\s*", "", role).strip(" ,-–—")
        for tok in _brand_tokens(company_name):
            role = re.sub(rf"(?i)^{re.escape(tok)}\w*(?:\s+\w+){{0,2}}?\s+(?=chief|managing|executive|co-?founder|founder|president|chair|director|head|vice)",
                          "", role).strip()
    # Anything left in front of the actual title is leftover company wording
    # ("Quick Heal Technologies Chief Technology Officer" -> "Chief Technology Officer")
    tm = re.search(
        r"(?i)\b(chief|managing\s+director|executive\s+director|co-?founder|founder|"
        r"president|chair(?:man|person|woman)?|head\s+of|vice\s+president|partner|"
        r"principal|owner|proprietor|general\s+manager|country\s+head|\bceo\b|\bcto\b|"
        r"\bcfo\b|\bcoo\b)\b", role)
    if tm and tm.start() > 0:
        lead = role[:tm.start()].strip(" ,-–—&")
        if lead and _is_org_like_name(lead):
            role = role[tm.start():]
    role = re.sub(r"\s+", " ", role).strip(" ,;.|-–—")

    if _is_org_like_name(name):
        return None

    # Move role fragments that leaked into the name field
    suffix_map = [
        (r"(?i)^(.+?)\s+Ind\.?\s*Non(?:[- ]?Exec(?:utive)?)?(?:\s+Director)?$",
         "Independent Non-Executive Director"),
        (r"(?i)^(.+?)\s+Non[- ]?Executive(?:\s+Director)?$", "Non-Executive Director"),
        (r"(?i)^(.+?)\s+Independent\s+Director$", "Independent Director"),
        (r"(?i)^(.+?)\s+Managing\s+Director$", "Managing Director"),
        (r"(?i)^(.+?)\s+Executive\s+Director$", "Executive Director"),
        (r"(?i)^(.+?)\s+Whole[- ]?time\s+Director$", "Whole-time Director"),
        (r"(?i)^(.+?)\s+Chairman$", "Chairman"),
        (r"(?i)^(.+?)\s+CEO$", "CEO"),
        (r"(?i)^(.+?)\s+MD$", "Managing Director"),
    ]
    for pat, role_fix in suffix_map:
        m = re.match(pat, name)
        if m:
            name = m.group(1).strip()
            if not role or role.lower() in ("leadership", "director", "executive director"):
                role = role_fix
            break

    # Clean role abbreviations
    role = re.sub(r"(?i)\bInd\.?\s*Non(?:[- ]?Exec(?:utive)?)?(?:\s+Director)?\b",
                  "Independent Non-Executive Director", role)
    role = re.sub(r"(?i)\bMD\b", "Managing Director", role)
    role = re.sub(r"\s+", " ", role).strip() or "Leadership"

    # Legacy companies (founded before ~1985): "Founder" from Crunchbase is often wrong
    blob = " ".join([
        (scraped or {}).get("wikipedia_summary") or "",
        (scraped or {}).get("wikipedia_text") or "",
        (scraped or {}).get("description") or "",
        (scraped or {}).get("about_text") or "",
        (scraped or {}).get("homepage_text") or "",
    ])
    founded_yr = None
    ym = re.search(r"(?i)\b(?:founded|established|est\.?|incorporated)\s*(?:in\s*)?(18\d{2}|19[0-7]\d)\b", blob)
    if not ym:
        # Wikipedia often states the year near "Gramophone Company" / company intro
        ym = re.search(r"\b(18\d{2}|19[0-4]\d)\b", blob)
    if ym:
        try:
            founded_yr = int(ym.group(1))
        except ValueError:
            founded_yr = None
    if founded_yr and founded_yr < 1985 and re.search(r"(?i)founder", role):
        if re.search(r"(?i)managing\s*director|\bmd\b|ceo|chairman|president", role):
            role = re.sub(r"(?i)(?:co-?)?founders?(?:\s*[&,/|]\s*)?", "", role).strip(" &,/")
            role = re.sub(r"\s+", " ", role).strip(" &,/") or "Managing Director"
        else:
            # Keep as historical context — never as current operating exec / POC
            if re.search(r"(?i)co-?founder|cofounder", role):
                role = "Co-founder (historical)"
            else:
                role = "Founder (historical)"
            leader = dict(leader)
            leader["status"] = "historical"
            leader["is_current"] = False

    # Drop names that still look like headlines / publishers
    if re.search(r"(?i)\b(news|latest|announcement|copyright case)\b", name):
        return None

    toks = name.split()
    if not (2 <= len(toks) <= 5):
        return None
    if any(t.lower() in ("ind", "non", "executive", "director", "limited") for t in toks):
        toks = [t for t in toks if t.lower() not in ("ind", "non", "executive", "director", "limited", "pvt")]
        name = " ".join(toks)
        if len(name.split()) < 2:
            return None

    out = dict(leader)
    out["name"] = name
    out["role"] = role[:80]
    out["status"] = out.get("status") or auth.leader_status(out["role"])
    out["is_current"] = out["status"] == "current"
    src = str(out.get("source") or "").lower()
    # Soft sources must keep brand proximity evidence in background/source blob
    soft = any(x in src for x in ("campaign", "crunchbase", "medianama", "public web", "web search"))
    if soft and company_name and re.search(r"(?i)founder|co-?founder", role):
        evidence = f"{out.get('background') or ''} {src} {blob[:500]}"
        if not _name_near_company(evidence + " " + company_name, name, company_name):
            # allow MD/CEO roles through; drop weak co-founder claims
            if not re.search(r"(?i)managing\s*director|ceo|chairman", role):
                return None
    return out


def _normalize_leadership_list(leaders: list, company_name: str = "", scraped: dict = None) -> list:
    out, seen = [], set()
    for l in leaders or []:
        fixed = _normalize_leader_row(l, company_name, scraped)
        if not fixed:
            continue
        key = (fixed.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(fixed)
    return out[:8]


def _name_near_company(blob: str, person_name: str, company_name: str, window: int = 140) -> bool:
    """Require person name to appear near the company brand (reduces wrong-company founders)."""
    text = (blob or "").lower()
    person = (person_name or "").lower().strip()
    brand = (company_name or "").lower().strip()
    if not text or not person or len(person) < 5:
        return False
    if person not in text:
        return False
    # Wikipedia / company site already brand-scoped
    if "wikipedia" in text[:80] or brand.split()[0] in text[:200]:
        return True
    tokens = _brand_tokens(company_name)
    if not tokens:
        return True
    idx = text.find(person)
    while idx >= 0:
        start = max(0, idx - window)
        end = min(len(text), idx + len(person) + window)
        window_txt = text[start:end]
        if any(t in window_txt for t in tokens):
            return True
        idx = text.find(person, idx + 1)
    return False


_ROLE_KEYWORDS = (
    r"chief\s+[\w ]{2,24}\s*officer|c\.?e\.?o\.?|c\.?t\.?o\.?|c\.?f\.?o\.?|c\.?o\.?o\.?|"
    r"c\.?i\.?o\.?|cmo|chro|cpo|cro|co-?\s?founders?|founders?|managing\s+director|"
    r"executive\s+director|whole[- ]time\s+director|independent\s+director|"
    r"chair(?:man|person|woman)?|vice\s+chair(?:man|person)?|president|vice\s+president|"
    r"managing\s+partner|general\s+manager|country\s+head|global\s+head|"
    r"head\s+of\s+[\w &/-]{2,40}|director\s+[\w &/-]{2,30}|director|partner|principal|"
    r"board\s+member|proprietor|owner"
)
_ROLE_LINE_RE = re.compile(rf"(?i)\b(?:{_ROLE_KEYWORDS})\b")
_LEADERSHIP_HEADING = re.compile(
    r"(?i)\b(?:leadership|our\s+team|the\s+team|meet\s+the\s+team|meet\s+our|"
    r"management\s+team|executive\s+team|our\s+people|board\s+of\s+directors|"
    r"our\s+founders|core\s+team|who\s+we\s+are)\b"
)
# Headings that mean the leadership block has ended — testimonials are full of
# "Name / CEO, SomeOtherCompany" cards that would otherwise be scraped as our execs.
_SECTION_BREAK = re.compile(
    r"(?i)\b(?:testimonial|happy\s+clients?|our\s+clients?|what\s+our|client\s+speak|"
    r"case\s+stud|latest\s+news|newsletter|subscribe|awards?\s+(?:and|&)|"
    r"trusted\s+by|customers?\s+say|our\s+partners?|related\s+(?:post|article))\b"
)
_NAME_STOPWORDS = {
    "solutions", "technologies", "technology", "services", "private", "limited", "company",
    "group", "systems", "software", "consulting", "labs", "ventures", "capital", "holdings",
    "industries", "enterprise", "enterprises", "global", "team", "learn", "read", "more",
    "view", "our", "the", "we", "us", "contact", "careers", "platform", "products", "about",
    "home", "blog", "news", "resources", "privacy", "policy", "terms", "all", "rights",
}


def _looks_like_person_name(line: str) -> bool:
    s = line.strip(" .,|·-–—•")
    if not (5 <= len(s) <= 48):
        return False
    toks = s.split()
    if not (2 <= len(toks) <= 4):
        return False
    for t in toks:
        core = re.sub(r"[^A-Za-z.'\-]", "", t)
        if not core or not core[0].isupper() or not re.fullmatch(r"[A-Za-z.'\-]+", core):
            return False
    if _ROLE_LINE_RE.search(s):
        return False
    if any(w in _NAME_STOPWORDS for w in s.lower().split()):
        return False
    return not _is_org_like_name(s)


def _is_role_line(line: str) -> bool:
    s = line.strip(" .,|·-–—•")
    if not (2 <= len(s) <= 70) or len(s.split()) > 9:
        return False
    return bool(_ROLE_LINE_RE.search(s))


def _role_company_ok(role_line: str, company_name: str, domain: str = "") -> bool:
    """Reject "CEO, SomeOtherCorp" style captions that belong to clients, not this company."""
    m = re.search(r"(?:,|\bat\b|\bof\b)\s+([A-Z][\w&.'\- ]{2,40})$", role_line.strip())
    if not m:
        return True
    tail = m.group(1).strip()
    # A compound title ("Co-founder, CEO and Managing Director") is not a company
    if _ROLE_LINE_RE.search(tail):
        return True
    if re.match(r"(?i)^(?:the\s+)?(?:company|board|directors?|operations|engineering|sales|"
                r"marketing|product|technology|finance|india|america|europe|apac|emea|"
                r"asia|uk|usa|projects?|delivery|strategy)\b", tail):
        return True
    tokens = _brand_tokens(company_name, domain)
    if not tokens:
        return True
    return any(t in tail.lower() for t in tokens)


def _is_dedicated_team_page(page_url: str) -> bool:
    """True when the URL itself says this page is the team/leadership page."""
    try:
        segs = [s for s in urlparse(page_url or "").path.strip("/").lower().split("/") if s]
    except Exception:
        return False
    if not segs or segs[0] in _NOISE_SECTIONS:
        return False
    return bool(re.search(
        r"^(?:our-|the-|meet-)?(?:leadership|team|management|executives?|people|"
        r"founders|board)(?:-(?:team|members|of-directors))?$", segs[-1]
    ))


def _parse_leadership_cards(lines_text: str, source: str, company_name: str = "",
                            domain: str = "", page_url: str = "") -> list:
    """
    Extract leadership from card layouts where the name and the role sit on adjacent
    lines with no separator between them:

        Kaushal Mashruwala
        CO-Founder

    The line-oriented regexes in ``_parse_leadership_from_text`` need a dash, colon or
    pipe, so they miss this layout entirely — which is how most team pages render.
    """
    if not lines_text:
        return []
    lines = [ln.strip() for ln in lines_text.split("\n")]
    lines = [ln for ln in lines if ln]

    # A page can mention "who we are" or "our team" in nav long before the real
    # leadership block, so collect every heading and scan each section.
    windows = []
    for i, ln in enumerate(lines):
        if len(ln) <= 80 and _LEADERSHIP_HEADING.search(ln):
            rest = lines[i + 1:i + 80]
            for k, nxt in enumerate(rest):
                if len(nxt) <= 80 and _SECTION_BREAK.search(nxt):
                    rest = rest[:k]
                    break
            if len(rest) >= 2:
                windows.append(rest)
    scoped = bool(windows)
    if not scoped:
        windows = [lines]

    out, seen = [], set()
    window = [ln for w in windows for ln in w]
    n = len(window)
    for i, line in enumerate(window):
        if not _looks_like_person_name(line):
            continue
        nxt = window[i + 1] if i + 1 < n else ""
        role = ""
        if nxt and _is_role_line(nxt):
            role = nxt
        elif nxt and not _looks_like_person_name(nxt) and i + 2 < n and _is_role_line(window[i + 2]):
            role = window[i + 2]
        elif i > 0 and _is_role_line(window[i - 1]) and not _looks_like_person_name(window[i - 1]):
            role = window[i - 1]
        if not role or not _role_company_ok(role, company_name, domain):
            continue

        name = re.sub(r"\s+", " ", line.strip(" .,|·-–—•"))
        if company_name and company_name.lower() in name.lower():
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        role = re.sub(r"\s+", " ", role.strip(" .,|·-–—•"))
        # Drop a trailing ", <own brand>" so the role reads as a title
        for tok in _brand_tokens(company_name, domain):
            role = re.sub(rf"(?i)\s*[,–—-]\s*{re.escape(tok)}\w*\s*$", "", role)
        role = re.sub(r"(?i)\bco[- ]?founder\b", "Co-Founder", role).strip(" ,-–—") or "Leadership"

        src_l = (source or "").lower()
        trusted = any(x in src_l for x in ("company leadership", "company about", "company website"))
        out.append({
            "name": name,
            "role": role[:60],
            "source": source,
            "confidence": "High" if trusted else "Medium",
            "background": f"Listed on {source}" if trusted else f"Mentioned in {source}",
        })
        if len(out) >= 12:
            break

    if not scoped and not _is_dedicated_team_page(page_url):
        # Without a "Leadership Team" heading or a team URL, an unscoped scan mostly
        # picks up client testimonial cards ("Name / CIO, SomeOtherCorp").
        return []
    return out


def _parse_leadership_from_text(text: str, source: str, company_name: str = "") -> list:
    """Extract founder/CEO/MD/chairman mentions from source text — never invent."""
    if not text:
        return []
    leaders = []
    seen = set()
    role_words = (
        r"CEO|CTO|COO|CFO|Chief Executive Officer|Chief Technology Officer|"
        r"Managing Director|MD|Chairman|Chairperson|Vice Chairperson|Vice Chairman|"
        r"Founder|Co-Founder|Cofounder|Co Founder|Executive Director|"
        r"Whole[- ]time Director|Director|"
        r"Head of Digital Solutions(?: Practice)?|Head of [A-Z][A-Za-z &]{2,40}"
    )
    patterns = [
        r"(?:founded by|Founded by|co-?founders?(?:\s+include)?|founders?(?:\s+include)?)\s*[:\-]?\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3})",
        # Name — Co-Founder & CTO   /   Name - Founder
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s*[—–\-:|]\s*((?:(?i:{role_words})(?:\s*&\s*[A-Za-z][A-Za-z /&-]{{0,40}})?))",
        # Present tense only — "was the CEO" describes a predecessor, not the incumbent
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s+(?:has been|is currently|currently serves as|serves as|is)\s+(?:the\s+)?(?i:{role_words})\b",
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s+succeeded\b.{{0,48}}?\bas\s+(?i:CEO|Chief Executive Officer|Chairman|Managing Director|President)",
        rf"(?i:{role_words})\s*[:\-]\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})",
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s*\(\s*(?i:{role_words})\s*\)",
    ]
    role_aliases = {
        "ceo", "cto", "coo", "cfo", "md", "chairman", "chairperson", "founder", "co-founder",
        "cofounder", "co founder", "managing director", "chief executive officer",
        "chief technology officer", "executive director", "whole-time director",
        "whole time director", "vice chairperson", "vice chairman", "director",
    }
    for pat in patterns:
        for m in re.finditer(pat, text):
            groups = [g for g in m.groups() if g]
            full = m.group(0)
            name = groups[0].strip() if groups else ""
            role = "Leadership"
            if len(groups) >= 2:
                a, b = groups[0].strip(), groups[1].strip()
                a_l, b_l = a.lower(), b.lower()
                if a_l in role_aliases or re.match(rf"(?i)^(?:{role_words})", a):
                    role, name = a, b
                else:
                    name, role = a, b
            else:
                rm = re.search(rf"(?i:{role_words})", full)
                if rm:
                    role = rm.group(0)
                elif re.search(r"(?i)founder", full):
                    role = "Founder"
            name = re.sub(r"\s+", " ", name).strip(" ,;.|")
            name = re.sub(r"\.+$", "", name).strip()
            role = re.sub(r"\s+", " ", role).strip(" ,;|")
            key = name.lower()
            if key in seen or len(name) < 5 or len(name) > 60:
                continue
            if company_name and company_name.lower() in key:
                continue
            if any(w in key for w in (
                "limited", "private", "company", "india", "wikipedia", "click",
                "founded", "director", "managing", "chairman", "officer",
                "products", "services", "portable", "key people",
            )):
                continue
            toks = name.split()
            if not (2 <= len(toks) <= 4) or not all(t[:1].isupper() for t in toks):
                continue
            # Reject org fragments mistaken as people ("PayPal Co", "Startup Success Co")
            if toks[-1].lower() in ("co", "inc", "ltd", "llc", "pvt", "private", "limited"):
                continue
            if any(t.lower() in ("startup", "success", "company", "solutions", "technologies") for t in toks):
                continue
            seen.add(key)
            src_l = (source or "").lower()
            # Wikipedia is useful background, not IR-grade for current officers
            if any(x in src_l for x in ("wikidata",)):
                conf = "High"
            elif any(x in src_l for x in ("wikipedia",)):
                conf = "Medium"
            elif any(x in src_l for x in ("theorg", "the.org", "linkedin", "company leadership", "company website")):
                conf = "High" if "linkedin" not in src_l else "Medium"
            else:
                conf = "Medium"
            # Non-trusted sources must mention person near company brand
            trusted = any(x in src_l for x in ("wikipedia", "company leadership", "company about", "company website"))
            if company_name and not trusted and not _name_near_company(text, name, company_name):
                continue
            role_fmt = re.sub(r"\s+", " ", role).strip()
            role_fmt = re.sub(r"\bcto\b", "CTO", role_fmt, flags=re.I)
            role_fmt = re.sub(r"\bceo\b", "CEO", role_fmt, flags=re.I)
            role_fmt = re.sub(r"\bcfo\b", "CFO", role_fmt, flags=re.I)
            role_fmt = re.sub(r"\bcoo\b", "COO", role_fmt, flags=re.I)
            leaders.append({
                "name": name,
                "role": role_fmt[:60],
                "source": source,
                "confidence": conf,
                "background": f"Mentioned in {source}",
            })
    return leaders[:10]


def _brand_tokens(company_name: str, domain: str = "") -> list:
    toks = []
    stem = _domain_stem(domain) if domain else ""
    if stem and len(stem) >= 4:
        toks.append(stem.lower())
    for w in re.findall(r"[A-Za-z]{4,}", company_name or ""):
        wl = w.lower()
        if wl not in ("limited", "private", "company", "solutions", "technologies", "india", "tech", "pvt"):
            toks.append(wl)
    out, seen = [], set()
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:4]


def _blob_matches_brand(blob: str, company_name: str, domain: str = "") -> bool:
    low = (blob or "").lower()
    tokens = _brand_tokens(company_name, domain)
    if not tokens:
        return True
    return any(t in low for t in tokens)


def _parse_llm_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or ""), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}") + 1
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start:end])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


# Evidence blobs computed in the background while the main LLM call runs, keyed by (company, domain).
_EVIDENCE_PREFETCH: dict = {}

# A failed contact lookup must not make repeated UI retries fan out into a new
# set of searches and model calls.  Cache only the final, sanitized decision —
# never the raw model answer or the search snippets.
_PUBLIC_CONTACT_CACHE: dict = {}
_PUBLIC_CONTACT_CACHE_LOCK = Lock()
_PUBLIC_CONTACT_CACHE_TTL = 15 * 60


def _public_contact_cache_key(company_name: str, domain: str) -> str:
    return f"{(domain or '').lower().strip()}::{(company_name or '').lower().strip()}"


def _public_contact_cache_get(key: str) -> dict | None:
    with _PUBLIC_CONTACT_CACHE_LOCK:
        row = _PUBLIC_CONTACT_CACHE.get(key)
        if not row:
            return None
        if time.monotonic() - row.get("at", 0) > _PUBLIC_CONTACT_CACHE_TTL:
            _PUBLIC_CONTACT_CACHE.pop(key, None)
            return None
        # Reports are mutated after the fallback is attached.  Return a JSON
        # copy so one request cannot change the cached decision for another.
        return json.loads(json.dumps(row.get("value") or {}))


def _public_contact_cache_put(key: str, value: dict) -> None:
    with _PUBLIC_CONTACT_CACHE_LOCK:
        _PUBLIC_CONTACT_CACHE[key] = {
            "at": time.monotonic(),
            "value": json.loads(json.dumps(value or {})),
        }


def _public_contact_evidence(
    company_name: str,
    domain: str,
    scraped: dict | None = None,
    intel: dict | None = None,
) -> list[dict]:
    """Collect small, public evidence records for the contact verifier.

    This is intentionally separate from the broad research sweep.  It searches
    only for the exact company and only forwards snippets/URLs to the two-pass
    contact flow.  ChatGPT/OpenAI/login pages are excluded before the model sees
    them, so they can never become citations for a contact.
    """
    scraped = scraped or {}
    intel = intel or {}
    records: list[dict] = []
    seen: set[str] = set()
    blocked_hosts = (
        "chatgpt.com", "chat.openai.com", "openai.com/chat",
        "accounts.google", "login.microsoftonline", "duckduckgo.com",
    )

    def _same_company_url(href: str) -> bool:
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
        except Exception:
            return False
        cd = (domain or "").lower().replace("www.", "")
        return bool(cd and (host == cd or host.endswith("." + cd)))

    def _add(
        href: str,
        title: str,
        snippet: str,
        source: str = "Public web",
        *,
        retrieved: bool = True,
        published_at: str = "",
    ) -> None:
        href = str(href or "").strip()
        if not href.startswith(("http://", "https://")):
            return
        low = href.lower()
        if any(host in low for host in blocked_hosts):
            return
        snippet = re.sub(r"\s+", " ", str(snippet or "")).strip()
        title = re.sub(r"\s+", " ", str(title or "")).strip()
        blob = f"{title} {snippet}"
        if not _same_company_url(href) and not _blob_matches_brand(blob, company_name, domain):
            return
        # Keep the exact page once.  A URL with no useful text is not evidence.
        key = href.rstrip("/").lower()
        if key in seen or (not title and not snippet):
            return
        seen.add(key)
        records.append({
            "url": href,
            "title": title[:180],
            "snippet": snippet[:900],
            "source": source[:100],
            "retrieved": bool(retrieved),
        })

    cd = scraped.get("contact_data") or {}
    contact_pages = list(cd.get("source_pages") or [])
    fallback_page = contact_pages[0] if contact_pages else f"https://{domain}/"
    for item in (cd.get("emails") or [])[:8]:
        if isinstance(item, dict) and item.get("email"):
            _add(
                fallback_page,
                "Public company contact page",
                f"Public business email listed: {item.get('email')} "
                f"{item.get('person') or item.get('person_name') or ''}",
                "Company Website",
            )
    for item in (cd.get("phones") or [])[:8]:
        if isinstance(item, dict) and item.get("number"):
            _add(
                fallback_page,
                "Public company contact page",
                f"Public business phone listed: {item.get('number')} "
                f"{item.get('person') or item.get('person_name') or ''}",
                "Company Website",
            )

    structured = scraped.get("_structured") or {}
    page_urls = scraped.get("_page_urls") or {}
    for key, label in (
        ("leadership_text", "Company leadership page"),
        ("about_text", "Company about page"),
        ("homepage_text", "Company website"),
    ):
        text_value = structured.get(key) or scraped.get(key) or ""
        if text_value:
            _add(
                page_urls.get(key) or f"https://{domain}/",
                label,
                text_value[:1100],
                "Company Website",
            )

    wiki_url = scraped.get("wikipedia_url") or ""
    wiki_text = scraped.get("wikipedia_summary") or scraped.get("wikipedia_text") or ""
    if wiki_url and wiki_text:
        _add(wiki_url, "Wikipedia", wiki_text[:1100], "Wikipedia")

    wd = scraped.get("_wikidata") or intel.get("_wikidata") or {}
    if wd.get("source_url") and (wd.get("ceo") or wd.get("chair") or wd.get("founders")):
        _add(
            wd.get("source_url"),
            "Wikidata company record",
            f"{company_name} ({domain}) current CEO: " + ", ".join(wd.get("ceo") or [])
            + "; current chair: " + ", ".join(wd.get("chair") or [])
            + "; founders: " + ", ".join(wd.get("founders") or []),
            "Wikidata",
        )

    for page in (intel.get("_scraped_pages") or [])[:12]:
        _add(
            page.get("url") or "",
            page.get("title") or page.get("domain") or "Public company profile",
            page.get("text") or page.get("snippet") or "",
            page.get("category") or "Public web",
            retrieved=page.get("retrieved") is not False and bool(page.get("text")),
        )

    # Search is the recovery path when the company site does not publish a
    # contact.  Run the bounded queries concurrently and keep only branded hits.
    queries = [
        f'"{company_name}" current CEO OR "managing director" OR president',
        f'"{company_name}" contact email OR phone',
        f'site:{domain} (contact OR leadership OR team OR "about us")',
    ]

    def _search_one(query: str) -> list:
        try:
            return _ddg_search(query, max_results=5)
        except Exception as exc:  # noqa: BLE001 - one source must not break research
            print(f"[Research] Contact search failed for '{query}': {exc}")
            return []

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        for query, query_rows in zip(queries, pool.map(_search_one, queries)):
            for row in query_rows or []:
                if not isinstance(row, dict):
                    continue
                href = row.get("href") or row.get("link") or ""
                title = row.get("title") or ""
                body = row.get("body") or row.get("snippet") or ""
                _add(
                    href,
                    title,
                    f"{body} Search query: {query}",
                    _site_category(href, domain) if href else "Public Web",
                    retrieved=False,
                )

    # Official pages and structured records are more useful to the judge than
    # generic result pages.  The order also keeps the prompt within its bound.
    records.sort(key=lambda r: (0 if _same_company_url(r.get("url") or "") else 1, r.get("url") or ""))
    return records[:18]


def _public_contact_fallback(
    company_name: str,
    domain: str,
    scraped: dict,
    intel: dict,
    existing_leaders: list | None = None,
) -> dict:
    """Use a model knowledge fallback, then show it only after a judge gate.

    The returned ``contact`` is already sanitized and may be rendered.  Raw
    extraction output and rejected candidates are intentionally not returned.
    """
    from backend.services import llm_judge

    cache_key = _public_contact_cache_key(company_name, domain)
    cached = _public_contact_cache_get(cache_key)
    if cached is not None:
        return cached

    result = {"status": "unavailable", "contact": {}, "source_urls": []}
    evidence = _public_contact_evidence(company_name, domain, scraped, intel)
    if not evidence:
        result["status"] = "no_public_evidence"
        _public_contact_cache_put(cache_key, result)
        return result

    prompt = f"""Find a PUBLIC business point of contact for this exact company.

Company: {company_name}
Official website: https://{domain}/

Use only the public evidence below plus clearly known public company knowledge. The answer
is a candidate, not proof, and will be sent to a separate authenticity judge. Never provide
confidential/private data. Do not invent email addresses or phone numbers. A current CEO,
Managing Director, President, Chair, Founder/Owner, or an explicitly listed official contact
is acceptable. Historical founders are not current contacts.

PUBLIC EVIDENCE:
{json.dumps(evidence, ensure_ascii=False)[:9000]}

Return JSON only:
{{
  "name": "public contact name or empty",
  "title": "current role or empty",
  "email": "exact email shown in evidence or empty",
  "phone": "exact phone shown in evidence or empty",
  "source_urls": ["URLs from evidence that support the answer"],
  "reason": "short explanation"
}}
"""
    try:
        raw = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Find public business contacts, never private data. "
                        "Do not guess emails, phones, names, or titles."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=650,
            json_mode=True,
            timeout=PROFILE_LLM_TIMEOUT,
            reasoning_effort="low",
        )
        candidate = _parse_llm_json(raw)
    except Exception as exc:  # noqa: BLE001 - fallback is optional by design
        print(f"[Research] Public contact candidate failed: {exc}")
        result["status"] = "candidate_unavailable"
        _public_contact_cache_put(cache_key, result)
        return result

    allowed_urls = {r.get("url") for r in evidence if r.get("url")}
    candidate["source_urls"] = [
        u for u in (candidate.get("source_urls") or [])
        if isinstance(u, str) and u in allowed_urls
    ]
    if not any(str(candidate.get(k) or "").strip() for k in ("name", "email", "phone")):
        result["status"] = "candidate_empty"
        _public_contact_cache_put(cache_key, result)
        return result

    verdict = llm_judge.judge_public_point_of_contact(
        website_url=f"https://{domain}/",
        domain=domain,
        company_name=company_name,
        candidate=candidate,
        evidence=evidence,
        existing_leaders=existing_leaders,
        timeout=PROFILE_JUDGE_TIMEOUT,
    )
    if verdict.get("_error") or not verdict.get("accept"):
        result["status"] = "rejected"
        _public_contact_cache_put(cache_key, result)
        return result

    source_urls = [u for u in (verdict.get("source_urls") or []) if u in allowed_urls]
    confidence = str(verdict.get("confidence") or "Low")
    if confidence.lower() == "low" or not source_urls:
        result["status"] = "rejected_low_confidence"
        _public_contact_cache_put(cache_key, result)
        return result

    name = re.sub(r"\s+", " ", str(verdict.get("name") or "")).strip(" ,;.|")
    title = re.sub(r"\s+", " ", str(verdict.get("title") or "")).strip(" ,;.|")
    email = str(verdict.get("email") or "").strip().lower()
    phone = str(verdict.get("phone") or "").strip()
    if name and (_is_org_like_name(name) or len(name.split()) < 2):
        name = ""
        title = ""
    if email and not _email_domain_ok(email, domain):
        email = ""
    if phone and not _is_valid_phone(phone):
        phone = ""
    if phone and not any(
        urlparse(u).netloc.lower().replace("www.", "") in (domain, "www." + domain)
        or urlparse(u).netloc.lower().replace("www.", "").endswith("." + domain)
        for u in source_urls
    ):
        # A phone number from a directory is not safe enough to promote as a
        # personal point of contact; official company pages remain eligible.
        phone = ""
    if not any((name, email, phone)):
        result["status"] = "rejected_after_sanitize"
        _public_contact_cache_put(cache_key, result)
        return result

    result = {
        "status": "verified",
        "contact": {
            "name": name,
            "title": title,
            "email": email,
            "phone": phone,
            "source": "Public contact judge",
            "source_urls": source_urls[:5],
            "confidence": confidence if confidence in ("High", "Medium") else "Medium",
            "verified": True,
            "provenance": "public-contact-judge",
            "reason": str(verdict.get("reason") or "Supported by public company evidence")[:260],
        },
        "source_urls": source_urls[:5],
    }
    _public_contact_cache_put(cache_key, result)
    return result


def _maybe_add_public_point_of_contact(
    report: dict,
    company_name: str,
    domain: str,
    scraped: dict,
    intel: dict,
) -> dict:
    """Attach only a verified fallback contact; never attach the raw candidate."""
    ci = report.get("contact_intelligence") if isinstance(report.get("contact_intelligence"), dict) else {}
    existing_named_email = any(
        isinstance(e, dict) and e.get("email") and (e.get("person") or e.get("person_name") or e.get("name"))
        for e in (ci.get("emails") or [])
    )
    if existing_named_email or auth.has_operating_exec(report.get("leadership_team") or []):
        report["_contact_verification"] = {"status": "existing_public_contact", "source_urls": []}
        # The caller keeps the function result as the full report.  Returning
        # only the status object here silently replaced every report section
        # with {status, source_urls}, leaving only fields rebuilt later.
        return report

    found = _public_contact_fallback(
        company_name, domain, scraped, intel, report.get("leadership_team") or []
    )
    contact = found.get("contact") if isinstance(found, dict) else {}
    if found.get("status") == "verified" and isinstance(contact, dict) and any(
        contact.get(k) for k in ("name", "email", "phone")
    ):
        ci["public_point_of_contact"] = contact
        emails = list(ci.get("emails") or [])
        if contact.get("email") and not any(
            isinstance(e, dict) and e.get("email", "").lower() == contact["email"]
            for e in emails
        ):
            emails.append({
                "email": contact["email"],
                "person": contact.get("name") or "",
                "person_name": contact.get("name") or "",
                "title": contact.get("title") or "",
                "label": contact.get("title") or "Public point of contact",
                "source": contact.get("source") or "Public contact judge",
                "source_urls": contact.get("source_urls") or [],
                "confidence": contact.get("confidence") or "Medium",
                "verified": True,
                "provenance": "public-contact-judge",
            })
        ci["emails"] = emails[:20]
        phones = list(ci.get("phones") or [])
        if contact.get("phone") and not any(
            isinstance(p, dict) and re.sub(r"\D", "", p.get("number", "")) == re.sub(r"\D", "", contact["phone"])
            for p in phones
        ):
            phones.append({
                "number": contact["phone"],
                "person": contact.get("name") or "",
                "person_name": contact.get("name") or "",
                "label": contact.get("title") or "Public point of contact",
                "source": contact.get("source") or "Public contact judge",
                "source_urls": contact.get("source_urls") or [],
                "confidence": contact.get("confidence") or "Medium",
                "verified": True,
                "provenance": "public-contact-judge",
            })
        ci["phones"] = phones[:20]
        report["contact_intelligence"] = ci
        report["_contact_verification"] = {
            "status": "verified",
            "source_urls": found.get("source_urls") or [],
        }
    else:
        report["_contact_verification"] = {
            "status": found.get("status") or "unavailable",
            "source_urls": [],
        }
    return report


def _site_evidence_blob(company_name: str, domain: str, scraped: dict) -> str:
    """Website + search snippets the verifier can check a claim against."""
    pending = _EVIDENCE_PREFETCH.pop((company_name, domain), None)
    if pending is not None:
        try:
            return pending.result()
        except Exception as e:  # noqa: BLE001 - fall through and compute it here
            print(f"[Research] Prefetched evidence failed ({e}) - recomputing")
    return _build_site_evidence_blob(company_name, domain, scraped)


def _build_site_evidence_blob(company_name: str, domain: str, scraped: dict) -> str:
    structured = (scraped or {}).get("_structured") or {}
    cd = (scraped or {}).get("contact_data") or {}
    parts = [
        f"Company: {company_name}  Website: {domain}",
        scraped.get("description") or "",
        structured.get("leadership_text") or scraped.get("leadership_text") or "",
        structured.get("about_text") or scraped.get("about_text") or "",
        scraped.get("homepage_text") or "",
        scraped.get("wikipedia_summary") or scraped.get("wikipedia_text") or "",
        "Addresses: " + "; ".join((cd.get("addresses") or [])[:4]),
        cd.get("address") or "",
    ]
    queries = [
        f'"{company_name}" headquarters OR "head office" OR "registered office"',
        f'"{company_name}" founder OR co-founder OR CEO OR president OR "managing director"',
        f'"{company_name}" founded OR "founded in" OR established',
        f'site:{domain} leadership OR "about us" OR team',
    ]
    for q in queries[: 4 if RESEARCH_DEEP else 3]:
        for r in _ddg_search(q, max_results=4):
            href = (r.get("href") or "").lower()
            if any(x in href for x in ("chatgpt.com", "chat.openai.com", "openai.com/chat")):
                continue
            if domain and domain.lower() in href and re.search(
                r"/(?:resources?|case-stud|success-stor|blog|news|webinar|testimonial)", href
            ):
                continue
            parts.append(f"{r.get('title','')}: {r.get('body','')}")
    return "\n".join(p for p in parts if p and str(p).strip())[:7000]


def _fetch_public_profile_page(url: str, timeout: int = 4) -> dict:
    """Fetch one bounded public HTML page; reject private IPs and unsafe redirects."""
    current = str(url or "").strip()
    for _ in range(4):
        parsed = urlparse(current)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".local", ".internal"))
        ):
            return {}
        try:
            address = ipaddress.ip_address(host)
            addresses = [address]
        except ValueError:
            try:
                addresses = [
                    ipaddress.ip_address(row[4][0])
                    for row in socket.getaddrinfo(
                        host, parsed.port or (443 if parsed.scheme == "https" else 80)
                    )
                ]
            except (OSError, ValueError):
                return {}
        if not addresses or any(not address.is_global for address in addresses):
            return {}

        try:
            with requests.get(
                current, headers=HEADERS, timeout=timeout,
                allow_redirects=False, stream=True,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location") or ""
                    if not location:
                        return {}
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return {}
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if content_type and not any(
                    marker in content_type for marker in ("text/html", "application/xhtml")
                ):
                    return {}
                chunks, total = [], 0
                for chunk in response.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 1_200_000:
                        break
                encoding = response.encoding or "utf-8"
                html = b"".join(chunks)[:1_200_000].decode(encoding, errors="replace")
        except Exception:
            return {}

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:4200]
        except Exception:
            return {}
        return {"url": current, "title": title[:180], "text": text, "html": html}
    return {}


def _ai_profile_evidence(
    company_name: str,
    domain: str,
    scraped: dict | None = None,
    intel: dict | None = None,
) -> list[dict]:
    """Build URL-preserving evidence for business and people-profile fill.

    The normal report prompt is intentionally compact.  This pass keeps the
    exact result URL and snippet for business-profile and leadership/contact
    queries so each claim can be tied back to a source for the exact company.
    """
    scraped = scraped or {}
    intel = intel or {}
    records: list[dict] = []
    seen: set[str] = set()
    industry_label = str(_industry_context(scraped, intel).get("label") or "general")
    industry_query = {
        "music_entertainment": "music",
        "professional_services": "professional services",
        "travel_tourism": "travel",
        "healthcare": "pharma",
    }.get(industry_label, industry_label.replace("_", " ") if industry_label != "general" else "")
    blocked = ("chatgpt.com", "chat.openai.com", "openai.com/chat", "accounts.google", "login.microsoftonline")

    def _same_company(href: str) -> bool:
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
        except Exception:
            return False
        base = (domain or "").lower().replace("www.", "")
        return bool(base and (host == base or host.endswith("." + base)))

    def _matches_market_industry(text: str) -> bool:
        industry_patterns = {
            "healthcare": r"\bhealth[\s-]?care\b|pharma(?:ceutical)?s?|life sciences|biotech|clinical|medical|active pharmaceutical ingredients|biosimilars|generic drugs",
            "travel_tourism": r"travel|tourism|hospitality|trip planning|vacation|airline",
            "music_entertainment": r"music|entertainment|streaming|record label|film",
            "software": r"software|technology|cloud|saas|artificial intelligence|\bAI\b|cybersecurity",
            "manufacturing": r"manufactur(?:ing|er)|industrial|factory|supply chain|production",
            "engineering": r"engineering|construction|infrastructure|\bEPC\b|civil",
            "professional_services": r"professional services|consulting|advisory|accounting|legal services",
            "ecommerce": r"e-commerce|ecommerce|retail|marketplace|online shopping",
            "education": r"education|learning|university|school|training|edtech",
            "logistics": r"logistics|supply chain|freight|shipping|warehouse|courier",
        }
        pattern = industry_patterns.get(industry_label)
        if not pattern and industry_query:
            pattern = re.escape(industry_query)
        return bool(pattern and re.search(pattern, str(text or ""), re.I))

    def _leadership_excerpt(value: str, limit: int = 4200) -> str:
        raw_lines = [re.sub(r"\s+", " ", line).strip() for line in str(value or "").splitlines()]
        lines = [line for line in raw_lines if line]
        role_pattern = re.compile(
            r"(?i)\b(?:chief executive|\bceo\b|chief technology|\bcto\b|chief financial|\bcfo\b|"
            r"chief operating|\bcoo\b|managing director|vice chairman|chairman|chairperson|"
            r"president|founder|co-founder|director|executive director)\b"
        )
        nav_only = {"board of directors", "management", "leadership", "our team", "team"}
        selected: set[int] = set()
        hits = [
            index for index, line in enumerate(lines)
            if line.lower() not in nav_only and role_pattern.search(line)
        ]
        for index in hits[:28]:
            selected.update(range(max(0, index - 1), min(len(lines), index + 2)))
        if not selected:
            return "\n".join(lines)[:limit]
        excerpt = []
        size = 0
        for index in sorted(selected):
            line = lines[index]
            if size + len(line) + 1 > limit:
                break
            excerpt.append(line)
            size += len(line) + 1
        return "\n".join(excerpt)

    def _add(
        href: str,
        title: str,
        snippet: str,
        source: str = "Public web",
        *,
        retrieved: bool = True,
        published_at: str = "",
        search_snippet: str = "",
    ) -> None:
        href = str(href or "").strip()
        if not href.startswith(("http://", "https://")) or any(x in href.lower() for x in blocked):
            return
        if auth.is_junk_citation(href):
            return
        title = re.sub(r"\s+", " ", str(title or "")).strip()
        snippet = re.sub(r"\s+", " ", str(snippet or "")).strip()
        if not title and not snippet:
            return
        exact_brand_match = _blob_matches_brand(f"{title} {snippet}", company_name, domain)
        market_trend_match = source == "Market Trends & Risk" and _matches_market_industry(f"{title} {snippet}")
        if not _same_company(href) and not exact_brand_match and not market_trend_match:
            return
        key = href.rstrip("/").lower()
        if key in seen:
            return
        seen.add(key)
        records.append({
            "url": href,
            "title": title[:180],
            "snippet": snippet[:1000],
            "source": (source or auth.classify_source(href, domain))[:100],
            "retrieved": bool(retrieved),
            "published_at": str(published_at or "")[:32],
            "search_snippet": str(search_snippet or (snippet if not retrieved else ""))[:1000],
        })

    structured = scraped.get("_structured") or {}
    page_urls = scraped.get("_page_urls") or {}
    for key, label in (
        ("leadership_text", "Company leadership page"),
        ("about_text", "Company about page"),
        ("homepage_text", "Company website"),
        ("careers_text", "Company careers page"),
    ):
        text_value = structured.get(key) or scraped.get(key) or ""
        if text_value:
            if key == "leadership_text":
                text_value = _leadership_excerpt(text_value)
            category = "Leadership" if key == "leadership_text" else "Company Website"
            _add(page_urls.get(key) or f"https://{domain}/", label, text_value[:4200], category)

    contact = scraped.get("contact_data") or {}
    contact_url = (contact.get("source_pages") or [f"https://{domain}/"])[0]
    for item in (contact.get("emails") or [])[:12]:
        if isinstance(item, dict) and item.get("email"):
            _add(
                contact_url,
                "Public company contact page",
                f"Email: {item.get('email')} {item.get('person') or item.get('person_name') or ''}",
                "Company Website",
            )
    for item in (contact.get("phones") or [])[:12]:
        if isinstance(item, dict) and item.get("number"):
            _add(
                contact_url,
                "Public company contact page",
                f"Phone: {item.get('number')} {item.get('person') or item.get('person_name') or ''}",
                "Company Website",
            )

    wiki_url = scraped.get("wikipedia_url") or ""
    wiki_text = scraped.get("wikipedia_summary") or scraped.get("wikipedia_text") or ""
    if wiki_url and wiki_text:
        _add(wiki_url, "Wikipedia", wiki_text[:2200], "Wikipedia")

    wd = scraped.get("_wikidata") or intel.get("_wikidata") or {}
    if wd.get("source_url"):
        _add(
            wd["source_url"],
            "Wikidata company record",
            f"CEO: {', '.join(wd.get('ceo') or [])}; chair: {', '.join(wd.get('chair') or [])}; "
            f"founders: {', '.join(wd.get('founders') or [])}; HQ: {wd.get('headquarters') or ''}",
            "Wikidata",
        )

    for page in (intel.get("_scraped_pages") or [])[:12]:
        _add(
            page.get("url") or "",
            page.get("title") or page.get("domain") or "Public company profile",
            page.get("text") or page.get("snippet") or "",
            page.get("category") or "Public web",
            retrieved=page.get("retrieved") is not False and bool(page.get("text")),
        )

    trend_query = (
        f"{datetime.now().year} {industry_query} industry trends market outlook"
        if industry_query else
        f'"{company_name}" market outlook trends {datetime.now().year}'
    )
    query_specs = [
        ("Competitors", f'"{company_name}" competitors peers alternatives market comparison'),
        ("Competitors", f'"{company_name}" peer comparison competitors market'),
        ("Products & Services", f'"{company_name}" products services customers'),
        ("Market & Geography", f'"{company_name}" market position regions countries'),
        ("Leadership", f'"{company_name}" current CEO founder leadership executives'),
        ("Leadership", f'site:{domain} (leadership OR executive OR management OR founders OR CEO OR "about us")'),
        ("Leadership", f'site:theorg.com/org "{company_name}" CEO founder leadership'),
        ("Leadership", f'site:inc42.com/company "{company_name}" CEO founder leadership'),
        ("Financials", f'"{company_name}" revenue employees annual report'),
        ("Market Trends & Risk", trend_query),
        ("Public Contacts", f'site:{domain} contact leadership email phone'),
    ]
    if not RESEARCH_DEEP:
        # Keep one bounded parallel sweep while prioritizing the official site,
        # peer evidence, an org chart source, and a dated industry outlook.
        query_specs = [query_specs[index] for index in (0, 2, 3, 5, 8, 9)]

    def _search(spec: tuple[str, str]) -> list:
        _, query = spec
        try:
            return _research_web_search(query, max_results=3)
        except Exception as exc:  # noqa: BLE001
            print(f"[Research] AI profile search failed for '{query}': {exc}")
            return []

    with ThreadPoolExecutor(max_workers=min(3, len(query_specs))) as pool:
        for (category, query), query_rows in zip(query_specs, pool.map(_search, query_specs)):
            for row in query_rows or []:
                if not isinstance(row, dict):
                    continue
                href = row.get("href") or row.get("link") or ""
                _add(
                    href,
                    row.get("title") or "Public search result",
                    f"{row.get('body') or row.get('snippet') or ''} Search query: {query}",
                    category or (auth.classify_source(href, domain) if href else "Public Web"),
                    retrieved=False,
                    published_at=(
                        row.get("published_at") or row.get("published") or row.get("date")
                        or _search_result_date(row.get("body") or row.get("snippet") or "")
                    ),
                    search_snippet=(row.get("body") or row.get("snippet") or ""),
                )

    # Search results are useful for discovery, but the report judge needs readable
    # source text. Fetch a small, diverse subset before the judge runs; all fetches
    # are bounded and public-address checked, and failures remain ordinary misses.
    already_fetched = {
        _canonical_public_url(str(page.get("url") or ""))
        for page in (intel.get("_scraped_pages") or [])
        if isinstance(page, dict) and page.get("url")
    }
    already_fetched.update(
        _canonical_public_url(str(value or ""))
        for value in page_urls.values()
        if value
    )
    profile_fetch_limit = 6 if not RESEARCH_DEEP else 8
    by_category = {}
    for record in records:
        category = str(record.get("source") or "Public Web")
        by_category.setdefault(category, []).append(record)
    fetch_candidates = []
    preferred_categories = (
        "Competitors", "Products & Services", "Leadership", "Market & Geography",
        "Financials", "Market Trends & Risk", "Public Contacts",
    )
    for category in preferred_categories:
        category_records = list(by_category.get(category, []))
        if category == "Leadership":
            leadership_terms = ("leadership", "key people", "founder", "ceo", "executive", "team", "about")
            category_records.sort(
                key=lambda row: -sum(
                    term in str(row.get("title") or "").lower()
                    for term in leadership_terms
                )
            )
        category_limit = 2 if category in {"Leadership", "Competitors"} else 1
        selected_for_category = 0
        selected_hosts = set()
        for record in category_records:
            canonical = _canonical_public_url(record.get("url") or "")
            host = (urlparse(str(record.get("url") or "")).hostname or "").lower().removeprefix("www.")
            # LinkedIn commonly serves a sign-in shell to anonymous crawlers;
            # keep its search snippet as a lead and fetch another source instead.
            if host == "linkedin.com" or host.endswith(".linkedin.com"):
                continue
            if host in selected_hosts:
                continue
            if not canonical or canonical in already_fetched:
                continue
            fetch_candidates.append(record)
            already_fetched.add(canonical)
            selected_hosts.add(host)
            selected_for_category += 1
            if selected_for_category >= category_limit or len(fetch_candidates) >= profile_fetch_limit:
                break
        if len(fetch_candidates) >= profile_fetch_limit:
            break
    if len(fetch_candidates) < profile_fetch_limit:
        for record in records:
            canonical = _canonical_public_url(record.get("url") or "")
            if not canonical or canonical in already_fetched:
                continue
            fetch_candidates.append(record)
            already_fetched.add(canonical)
            if len(fetch_candidates) >= profile_fetch_limit:
                break

    def _fetch_one(record: dict) -> tuple[dict, dict]:
        return record, _fetch_public_profile_page(str(record.get("url") or ""))

    if fetch_candidates:
        with ThreadPoolExecutor(max_workers=min(6, len(fetch_candidates))) as pool:
            for record, fetched in pool.map(_fetch_one, fetch_candidates):
                search_excerpt = str(record.get("snippet") or "")[:1000]
                text = str(fetched.get("text") or "")
                title = str(fetched.get("title") or record.get("title") or "")
                if record.get("source") == "Leadership" and fetched.get("html"):
                    try:
                        from bs4 import BeautifulSoup
                        page_soup = BeautifulSoup(fetched["html"], "html.parser")
                        for tag in page_soup(["script", "style", "noscript", "svg", "iframe"]):
                            tag.decompose()
                        leadership_lines = page_soup.get_text(separator="\n", strip=True)
                        text = _leadership_excerpt(leadership_lines)
                    except Exception:
                        pass
                page_evidence = f"{title} {text[:2500]}"
                page_matches_company = _blob_matches_brand(page_evidence, company_name, domain)
                page_matches_industry = (
                    record.get("source") == "Market Trends & Risk"
                    and _matches_market_industry(page_evidence)
                )
                if len(text) < 120 or not (page_matches_company or page_matches_industry):
                    continue
                if (
                    _is_blocked_page_text(title, text)
                    or _is_parked_page_text(title, text)
                    or _is_illogical_text(text[:900])
                ):
                    # Login walls and generic site chrome are not fetched evidence.
                    continue
                final_url = str(fetched.get("url") or record.get("url") or "")
                extracted_date = _news_date_from_html(fetched.get("html") or "")
                if not extracted_date and _parse_public_news_date(record.get("published_at")):
                    parsed_search_date = _parse_public_news_date(record.get("published_at"))
                    extracted_date = parsed_search_date.strftime("%Y-%m-%d")
                text_limit = 4200 if record.get("source") == "Leadership" else 2200
                record.update({
                    "url": final_url,
                    "title": title[:180],
                    "snippet": text[:text_limit],
                    "page_text": text[:text_limit],
                    "search_snippet": search_excerpt,
                    "retrieved": True,
                    "published_at": extracted_date or record.get("published_at") or _search_result_date(search_excerpt),
                })

    category_rank = {
        "Competitors": 0,
        "Products & Services": 1,
        "Leadership": 2,
        "Market & Geography": 3,
        "Financials": 4,
        "Market Trends & Risk": 5,
        "Public Contacts": 6,
    }
    records.sort(key=lambda r: (
        0 if _same_company(r.get("url") or "") else 1,
        0 if r.get("retrieved") else 1,
        category_rank.get(str(r.get("source") or ""), 7),
        r.get("url") or "",
    ))
    return records[:40 if RESEARCH_DEEP else 24]


def _merge_profile_evidence_into_intel(evidence: list[dict], intel: dict) -> None:
    """Expose profile search/fetch evidence to synthesis, judging, and citations."""
    source_rows = intel.setdefault("_source_urls", [])
    pages = intel.setdefault("_scraped_pages", [])
    existing_source_urls = {
        _canonical_public_url(str(row.get("url") or ""))
        for row in source_rows if isinstance(row, dict)
    }
    existing_page_urls = {
        _canonical_public_url(str(row.get("url") or ""))
        for row in pages if isinstance(row, dict)
    }
    profile_sources = []
    profile_pages = []
    seen_profile_sources = set()
    seen_profile_pages = set()
    for row in evidence or []:
        if not isinstance(row, dict):
            continue
        href = str(row.get("url") or "").strip()
        canonical = _canonical_public_url(href)
        if not canonical:
            continue
        category = str(row.get("source") or "Public Web")[:80]
        title = str(row.get("title") or "Public source")[:180]
        page_text = str(row.get("page_text") or (row.get("snippet") if row.get("retrieved") else ""))[:4200]
        search_excerpt = str(row.get("search_snippet") or (row.get("snippet") if not row.get("retrieved") else ""))[:1000]
        text = page_text
        if search_excerpt and search_excerpt not in text:
            text = f"{text}\nSearch result excerpt: {search_excerpt}"[:4200]
        published_at = str(row.get("published_at") or "")[:32]
        if canonical not in existing_source_urls and canonical not in seen_profile_sources:
            profile_sources.append({
                "title": title,
                "url": href,
                "category": category,
                "snippet": text[:700],
                "retrieved": bool(row.get("retrieved")),
                "published_at": published_at,
                "search_snippet": search_excerpt,
            })
            seen_profile_sources.add(canonical)
        if (
            row.get("retrieved") and text
            and canonical not in existing_page_urls
            and canonical not in seen_profile_pages
        ):
            host = (urlparse(href).netloc or "").lower().removeprefix("www.")
            profile_pages.append({
                "title": title,
                "url": href,
                "domain": host,
                "category": category,
                "snippet": text[:700],
                "text": page_text,
                "search_snippet": search_excerpt,
                "published_at": published_at,
                "emails": [],
                "phones": [],
                "retrieved": True,
            })
            seen_profile_pages.add(canonical)
    # Profile evidence is the targeted, category-labeled sweep. Put it first so
    # compact prompts and judge context do not get crowded out by old generic hits.
    intel["_source_urls"] = profile_sources + [
        row for row in source_rows
        if not isinstance(row, dict)
        or _canonical_public_url(str(row.get("url") or "")) not in seen_profile_sources
    ]
    intel["_scraped_pages"] = profile_pages + [
        row for row in pages
        if not isinstance(row, dict)
        or _canonical_public_url(str(row.get("url") or "")) not in seen_profile_pages
    ]


def _run_ai_profile_fallback(
    report: dict,
    company_name: str,
    domain: str,
    scraped: dict,
    intel: dict,
) -> dict:
    """Fill missing profile facts from retrieved public evidence and judge them."""
    from backend.services import llm_judge

    base_result = {
        "status": "unavailable",
        "provider": "Public web profile research + fact judge",
        "judge_score": 0,
        "summary": "Public profile research was not available.",
        "evidence_count": 0,
        "source_urls": [],
        "leaders_added": 0,
        "point_of_contact": {},
    }
    if not RESEARCH_AI_PROFILE_FALLBACK:
        base_result["status"] = "disabled"
        base_result["summary"] = "AI profile fallback is disabled by configuration."
        report["ai_enrichment"] = base_result
        return report

    evidence = intel.get("_profile_evidence")
    if not isinstance(evidence, list):
        evidence = _ai_profile_evidence(company_name, domain, scraped, intel)
    base_result["evidence_count"] = len(evidence)
    if not evidence:
        base_result["status"] = "complete_no_new_facts"
        base_result["summary"] = "No additional accessible public-source evidence was retrieved."
        report["ai_enrichment"] = base_result
        return report
    existing = [
        {"name": l.get("name"), "role": l.get("role"), "status": l.get("status")}
        for l in (report.get("leadership_team") or [])[:8]
        if isinstance(l, dict) and l.get("name")
    ]
    contact = report.get("contact_intelligence") if isinstance(report.get("contact_intelligence"), dict) else {}
    company_profile = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    products = report.get("products_services") if isinstance(report.get("products_services"), dict) else {}
    market = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    tech = report.get("tech_stack") if isinstance(report.get("tech_stack"), dict) else {}
    current_offerings = [
        (row.get("item") or row.get("value") or "") if isinstance(row, dict) else str(row)
        for row in (products.get("primary_offerings") or [])[:6]
    ]
    candidate_prompt = f"""Build a public company-profile candidate for this exact company.

COMPANY: {company_name}
WEBSITE: https://{domain}/
EXISTING LEADERS: {json.dumps(existing, ensure_ascii=False)}
EXISTING PUBLIC CONTACTS: {json.dumps({
    'emails': (contact.get('emails') or [])[:10],
    'phones': (contact.get('phones') or [])[:10],
}, ensure_ascii=False)[:2500]}
CURRENT PROFILE: {json.dumps({
    'name': _field_text(company_profile.get('name')),
    'headquarters': _field_text(company_profile.get('headquarters')),
    'founded': _field_text(company_profile.get('founded')),
}, ensure_ascii=False)}
CURRENT BUSINESS PROFILE: {json.dumps({
    'description': _field_text(company_profile.get('description')),
    'industry': _field_text(market.get('industry') or company_profile.get('industry')),
    'products_services': current_offerings,
    'market_position': _field_text(market.get('market_position')),
    'geographic_reach': _field_text(market.get('geographic_reach')),
    'website_technology_detected': _field_text(tech.get('website_cms') or tech.get('cms')),
    'competitors_already_supported': [c.get('name') for c in (report.get('competitors') or [])[:6] if isinstance(c, dict)],
}, ensure_ascii=False)[:3200]}

PUBLIC EVIDENCE (snippets and URLs):
{json.dumps(evidence, ensure_ascii=False)[:14000] or '[]'}

Return ONLY JSON:
{{
  "leadership": [{{"name":"Full Name","role":"CEO|CTO|CFO|COO|Founder|Co-founder|Chairperson|President|Managing Director|Director","status":"current|historical","basis":"evidence","confidence":"High|Medium|Low"}}],
  "point_of_contact": {{"name":"","title":"","email":"","phone":"","basis":"evidence","confidence":"High|Medium|Low"}},
  "headquarters": "city, country or empty",
  "founded": "YYYY or empty",
  "business_profile": {{
    "products_services": [{{"item":"...","basis":"evidence","confidence":"High|Medium|Low"}}],
    "market_position": {{"value":"...","basis":"evidence","confidence":"High|Medium|Low"}},
    "geographic_reach": {{"value":"...","basis":"evidence","confidence":"High|Medium|Low"}},
    "competitor_candidates": [{{"name":"...","official_domain":"... or empty","market_location":"... or empty","overlap_reason":"...","basis":"evidence","confidence":"High|Medium|Low"}}]
  }}
}}

Rules:
- Prefer current CEO, CTO, COO, CFO, President, Chair, Founder/Co-founder, or MD.
- Use only the supplied public evidence. If a current leader is not supported there, leave that person out.
- Historical founders must be status=historical and must not be the POC unless still operating.
- Never invent an email or phone. Only copy exact values visible in PUBLIC EVIDENCE.
- Never use private data, guessed email patterns, or a similarly named company.
- For products, market position, reach, and competitors, use only claims supported by the supplied public evidence and return their exact source URLs.
- Competitor candidates must overlap in business domain and actual operating market; do not fill a quota. Leave official_domain empty unless known with confidence.
- Do not use model memory for latest news, current hiring, revenue/funding numbers, email addresses, or phone numbers. Those require current public evidence.
- Empty is correct when the identity is not unambiguous.
"""
    try:
        raw = llm_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Return valid JSON only. Research the exact public company. "
                        "Separate evidence-backed facts from model knowledge and never invent contact details."
                    ),
                },
                {"role": "user", "content": candidate_prompt},
            ],
            temperature=0.1,
            max_tokens=2200,
            json_mode=True,
            timeout=PROFILE_LLM_TIMEOUT,
            reasoning_effort="low",
        )
        candidate = _parse_llm_json(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[Research] AI profile candidate failed: {exc}")
        base_result["status"] = "candidate_unavailable"
        base_result["summary"] = "AI profile candidate generation failed; public crawl data was kept."
        report["ai_enrichment"] = base_result
        return report

    verdict = llm_judge.judge_ai_profile(
        website_url=f"https://{domain}/",
        domain=domain,
        company_name=company_name,
        candidate=candidate,
        evidence=evidence,
        existing_leaders=report.get("leadership_team") or [],
        timeout=PROFILE_JUDGE_TIMEOUT,
    )
    if verdict.get("_error"):
        base_result["status"] = "judge_unavailable"
        base_result["summary"] = "AI profile candidate was not promoted because the fact judge was unavailable."
        report["ai_enrichment"] = base_result
        return report

    existing_rows = list(report.get("leadership_team") or [])
    existing_keys = {(str(l.get("name") or "").strip().lower()) for l in existing_rows if isinstance(l, dict)}
    added = 0
    accepted_source_urls = []
    profile_evidence_urls = {
        str(item.get("url") or "").strip()
        for item in evidence
        if isinstance(item, dict) and str(item.get("url") or "").strip().startswith(("http://", "https://"))
    }

    def _source_supported(status: str, urls: list[str]) -> bool:
        return status in {"evidence-verified", "search-snippet-supported"} and any(
            url in profile_evidence_urls for url in urls
        )

    def _ai_status_source(status: str, urls: list[str] | None = None) -> str:
        for source_url in urls or []:
            if source_url not in profile_evidence_urls:
                continue
            host = (urlparse(source_url).netloc or "").lower().removeprefix("www.")
            if host:
                return f"{host} search result" if status == "search-snippet-supported" else host
        return "Public source"

    for row in verdict.get("leadership") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        name = row.get("name")
        key = str(name).strip().lower()
        urls = [u for u in (row.get("source_urls") or []) if isinstance(u, str) and u]
        status = row.get("verification_status") or "model-knowledge-reviewed"
        if not _source_supported(status, urls):
            continue
        accepted_source_urls.extend(urls)
        if key in existing_keys:
            continue
        source = _ai_status_source(status, urls)
        existing_rows.append({
            "name": str(name).strip(),
            "role": str(row.get("role") or "Leadership").strip(),
            "source": source,
            "confidence": row.get("confidence") or "Medium",
            "verification_score": row.get("verification_score") or 0,
            "verification_status": status,
            "source_urls": urls,
            "background": row.get("reason") or "Reviewed by the AI profile judge",
            "status": row.get("status") or "current",
            "is_current": (row.get("status") or "current") == "current",
            "provenance": (
                "public-evidence" if status == "evidence-verified"
                else "search-snippet" if status == "search-snippet-supported"
                else "ai-knowledge"
            ),
        })
        existing_keys.add(key)
        added += 1

    report["leadership_team"] = auth.rank_leadership(
        _normalize_leadership_list(existing_rows, company_name, scraped)
    )

    ai_poc = verdict.get("point_of_contact") if isinstance(verdict.get("point_of_contact"), dict) else {}
    ai_poc = dict(ai_poc or {})
    ai_poc_urls = [
        u for u in (ai_poc.get("source_urls") or [])
        if isinstance(u, str) and u in profile_evidence_urls
    ]
    ai_poc_status = str(ai_poc.get("verification_status") or "model-knowledge-reviewed")
    if not _source_supported(ai_poc_status, ai_poc_urls):
        ai_poc = {}
    if not ai_poc and report.get("leadership_team"):
        for leader in report.get("leadership_team") or []:
            if leader.get("status") == "current" and re.search(
                r"(?i)ceo|chief executive|managing director|president|chair|founder|owner", leader.get("role") or ""
            ):
                ai_poc = {
                    "name": leader.get("name") or "",
                    "title": leader.get("role") or "",
                    "confidence": leader.get("confidence") or "Medium",
                    "verification_status": leader.get("verification_status") or "model-knowledge-reviewed",
                    "verification_score": leader.get("verification_score") or 0,
                    "source_urls": leader.get("source_urls") or [],
                    "reason": "Selected from the highest-ranked current leader after AI judging.",
                }
                break

    if ai_poc:
        poc_urls = [
            u for u in (ai_poc.get("source_urls") or [])
            if isinstance(u, str) and u in profile_evidence_urls
        ]
        if not _source_supported(
            str(ai_poc.get("verification_status") or "model-knowledge-reviewed"), poc_urls
        ):
            ai_poc = {}

    if ai_poc.get("name") or ai_poc.get("email") or ai_poc.get("phone"):
        # Keep a model-known executive separate from contact details. A public
        # email or phone may be copied into the contact list only when its exact
        # value appears in the evidence; attach a person's name only when the
        # same evidence record contains both the name and the contact value.
        poc_status = ai_poc.get("verification_status") or "model-knowledge-reviewed"
        poc_name = str(ai_poc.get("name") or "").strip()
        candidate_email = str(ai_poc.get("email") or "").strip().lower()
        candidate_phone = str(ai_poc.get("phone") or "").strip()
        evidence_rows = [row for row in evidence if isinstance(row, dict)]

        def _matching_contact_rows(value: str, *, phone_value: bool = False) -> list[dict]:
            if not value:
                return []
            matches = []
            for evidence_row in evidence_rows:
                evidence_text = " ".join((
                    str(evidence_row.get("title") or ""),
                    str(evidence_row.get("snippet") or ""),
                ))
                if phone_value:
                    found = llm_judge._phone_literal_in_text(value, evidence_text)
                else:
                    found = value.lower() in evidence_text
                if found:
                    matches.append(evidence_row)
            return matches

        email_rows = _matching_contact_rows(candidate_email)
        phone_rows = _matching_contact_rows(candidate_phone, phone_value=True)
        name_in_evidence = any(
            poc_name.lower() in " ".join((str(row.get("title") or ""), str(row.get("snippet") or ""))).lower()
            for row in evidence_rows
        ) if poc_name else False
        email_named_rows = [
            row for row in email_rows
            if poc_name and poc_name.lower() in " ".join((str(row.get("title") or ""), str(row.get("snippet") or ""))).lower()
        ]
        phone_named_rows = [
            row for row in phone_rows
            if poc_name and poc_name.lower() in " ".join((str(row.get("title") or ""), str(row.get("snippet") or ""))).lower()
        ]
        ai_poc["source"] = _ai_status_source(poc_status, ai_poc.get("source_urls") or [])
        ai_poc["verification_status"] = poc_status
        ai_poc["verified"] = poc_status == "evidence-verified" and name_in_evidence
        ai_poc["provenance"] = (
            "public-evidence" if ai_poc["verified"]
            else "search-snippet" if poc_status == "search-snippet-supported"
            else "ai-knowledge"
        )
        ai_poc["source_urls"] = [u for u in (ai_poc.get("source_urls") or []) if isinstance(u, str) and u]
        # Never associate a model-memory name with an unrelated public inbox or
        # switchboard number. Exact values can still be retained as generic
        # company contacts when they are present in the supplied evidence.
        ai_poc["email"] = candidate_email if any(row.get("retrieved") for row in email_named_rows) and poc_status == "evidence-verified" else ""
        ai_poc["phone"] = candidate_phone if any(row.get("retrieved") for row in phone_named_rows) and poc_status == "evidence-verified" else ""
        accepted_source_urls.extend(ai_poc.get("source_urls") or [])
        ci = report.get("contact_intelligence") if isinstance(report.get("contact_intelligence"), dict) else {}
        emails = list(ci.get("emails") or [])
        email = candidate_email if email_rows and _email_domain_ok(candidate_email, domain) else ""
        email_is_named = bool(email and any(row.get("retrieved") for row in email_named_rows) and poc_status == "evidence-verified")
        if email and not any(
            isinstance(e, dict) and str(e.get("email") or "").lower() == email for e in emails
        ):
            email_sources = list(dict.fromkeys(str(row.get("url") or "") for row in (email_named_rows if email_is_named else email_rows) if row.get("url")))
            accepted_source_urls.extend(email_sources)
            email_status = "evidence-verified" if any(row.get("retrieved") for row in email_rows) else "search-snippet-supported"
            emails.append({
                "email": email,
                "person": poc_name if email_is_named else "",
                "person_name": poc_name if email_is_named else "",
                "title": ai_poc.get("title") or "" if email_is_named else "",
                "label": (ai_poc.get("title") or "Public company email") if email_is_named else "Public company email",
                "source": _ai_status_source(email_status, email_sources),
                "source_urls": email_sources,
                "confidence": ai_poc.get("confidence") or "Medium",
                "verified": email_status == "evidence-verified",
                "verification_status": email_status,
                "provenance": "public-evidence" if email_status == "evidence-verified" else "search-snippet",
            })
        ci["emails"] = emails[:20]
        phones = list(ci.get("phones") or [])
        phone = candidate_phone if phone_rows and _is_valid_phone(candidate_phone) else ""
        phone_is_named = bool(phone and any(row.get("retrieved") for row in phone_named_rows) and poc_status == "evidence-verified")
        if phone and _is_valid_phone(phone) and not any(
            isinstance(p, dict) and re.sub(r"\D", "", str(p.get("number") or "")) == re.sub(r"\D", "", phone)
            for p in phones
        ):
            phone_sources = list(dict.fromkeys(str(row.get("url") or "") for row in (phone_named_rows if phone_is_named else phone_rows) if row.get("url")))
            accepted_source_urls.extend(phone_sources)
            phone_status = "evidence-verified" if any(row.get("retrieved") for row in phone_rows) else "search-snippet-supported"
            phones.append({
                "number": phone,
                "person": poc_name if phone_is_named else "",
                "person_name": poc_name if phone_is_named else "",
                "label": (ai_poc.get("title") or "Public company phone") if phone_is_named else "Public company phone",
                "source": _ai_status_source(phone_status, phone_sources),
                "source_urls": phone_sources,
                "confidence": ai_poc.get("confidence") or "Medium",
                "verified": phone_status == "evidence-verified",
                "verification_status": phone_status,
                "provenance": "public-evidence" if phone_status == "evidence-verified" else "search-snippet",
            })
        ci["phones"] = phones[:20]
        report["contact_intelligence"] = ci

    cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    for key, label in (("headquarters", "headquarters"), ("founded", "founded")):
        fact = verdict.get(key) if isinstance(verdict.get(key), dict) else {}
        if not fact.get("value"):
            continue
        current = _field_text(cp.get(key))
        if current and "not publicly" not in current.lower() and "not available" not in current.lower():
            continue
        status = fact.get("verification_status") or "model-knowledge-reviewed"
        urls = [u for u in (fact.get("source_urls") or []) if isinstance(u, str) and u]
        if not _source_supported(status, urls):
            continue
        cp[key] = _field(
            fact["value"],
            _ai_status_source(status, urls),
            fact.get("confidence") or "Medium",
        )
        cp[key]["verification_status"] = status
        cp[key]["source_urls"] = urls
        accepted_source_urls.extend(urls)
    report["company_profile"] = cp

    # Fill only stable business-profile gaps. AI-knowledge-only values remain
    # explicitly labeled suggestions; recent news, hiring, financial amounts,
    # emails, and phone numbers still require current public evidence.
    business = verdict.get("business_profile") if isinstance(verdict.get("business_profile"), dict) else {}
    business_fields_added = 0
    ps = report.get("products_services") if isinstance(report.get("products_services"), dict) else {}
    current_offerings = [
        row for row in (ps.get("primary_offerings") or [])
        if isinstance(row, dict) and str(row.get("item") or row.get("value") or "").strip()
        and "not publicly" not in str(row.get("item") or row.get("value") or "").lower()
    ]
    weak_offering_coverage = (
        len(current_offerings) < 2
        or (current_offerings and all(str(row.get("confidence") or "").lower() == "low" for row in current_offerings))
    )
    if weak_offering_coverage:
        filled_offerings = list(current_offerings)
        existing_offering_keys = {
            str(row.get("item") or row.get("value") or "").strip().lower()
            for row in current_offerings
        }
        for row in business.get("products_services") or []:
            item = str(row.get("item") or "").strip() if isinstance(row, dict) else ""
            if not item or item.lower() in existing_offering_keys:
                continue
            status = row.get("verification_status") or "model-knowledge-reviewed"
            urls = [u for u in (row.get("source_urls") or []) if isinstance(u, str) and u]
            if not _source_supported(status, urls):
                continue
            source_label = _ai_status_source(status, urls)
            filled_offerings.append({
                "item": item,
                "source": source_label,
                "confidence": row.get("confidence") or "Medium",
                "verification_status": status,
                "source_urls": urls,
            })
            accepted_source_urls.extend(urls)
            existing_offering_keys.add(item.lower())
        if len(filled_offerings) > len(current_offerings):
            ps["primary_offerings"] = filled_offerings[:8]
            business_fields_added += 1
            report["products_services"] = ps

    ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    for key in ("market_position", "geographic_reach"):
        current_text = _field_text(ma.get(key))
        missing = not current_text or any(marker in current_text.lower() for marker in (
            "not publicly available", "not available", "unknown", "n/a",
        ))
        if key == "geographic_reach" and current_text.lower().startswith("headquartered in "):
            # HQ is location information, but does not establish operating reach.
            missing = True
        fact = business.get(key) if isinstance(business.get(key), dict) else {}
        if not missing or not fact.get("value"):
            continue
        status = fact.get("verification_status") or "model-knowledge-reviewed"
        urls = [u for u in (fact.get("source_urls") or []) if isinstance(u, str) and u]
        if not _source_supported(status, urls):
            continue
        ma[key] = _field(
            fact.get("value"),
            _ai_status_source(status, urls),
            fact.get("confidence") or "Medium",
        )
        ma[key]["verification_status"] = status
        ma[key]["source_urls"] = urls
        ma[key]["reason"] = fact.get("reason") or "Reviewed by the AI profile judge"
        accepted_source_urls.extend(urls)
        business_fields_added += 1
    report["market_analysis"] = ma

    competitor_candidates = []
    for row in business.get("competitor_candidates") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        status = str(row.get("verification_status") or "model-knowledge-reviewed")
        urls = [u for u in (row.get("source_urls") or []) if isinstance(u, str) and u in profile_evidence_urls]
        # Do not send model-memory-only names to the UI. Keep competitor leads
        # only when the profile judge tied the name to a retrieved public source.
        if status not in ("evidence-verified", "search-snippet-supported") or not urls:
            continue
        accepted_source_urls.extend(urls)
        candidate = {
            "name": str(row.get("name") or "").strip(),
            "official_domain": str(row.get("official_domain") or "").strip(),
            "market_location": str(row.get("market_location") or "").strip(),
            "overlap_reason": str(row.get("overlap_reason") or "").strip(),
            "confidence": row.get("confidence") or "Medium",
            "verification_status": status,
            "source_urls": urls,
            "reason": row.get("reason") or "Reviewed by the AI profile judge",
        }
        if not candidate["name"]:
            continue
        competitor_candidates.append(candidate)
    report["competitor_candidates"] = competitor_candidates[:4]
    competitor_candidates_added = len(competitor_candidates[:4])
    if competitor_candidates_added:
        business_fields_added += 1

    unique_urls = list(dict.fromkeys(accepted_source_urls))[:20]
    accepted_count = added + (1 if ai_poc else 0) + business_fields_added
    base_result.update({
        "status": "complete" if accepted_count else "complete_no_new_facts",
        "judge_score": int(verdict.get("overall_score") or 0),
        "summary": verdict.get("summary") or "AI profile facts were reviewed for company identity and evidence.",
        "source_urls": unique_urls,
        "leaders_added": added,
        "point_of_contact": ai_poc,
        "business_fields_added": business_fields_added,
        "competitor_candidates_added": competitor_candidates_added,
        "evidence_count": len(evidence),
    })
    report["ai_enrichment"] = base_result
    print(
        f"[Research] AI profile judge: score={base_result['judge_score']} "
        f"leaders_added={added} poc={bool(ai_poc)} evidence={len(evidence)}"
    )
    return report


def _llm_public_profile_fill(company_name: str, domain: str, scraped: dict,
                             existing_leaders: list | None = None) -> dict:
    """
    Always-on public-fact fill for leadership, HQ, founded year, and hiring.

    Pass 1 — extract like a public researcher (the same facts ChatGPT returns).
    Pass 2 — a separate LLM-as-judge keep/drop. Shown facts are never cited as ChatGPT.
    """
    empty = {
        "leaders": list(existing_leaders or []),
        "headquarters": "",
        "founded": "",
        "hiring": [],
        "urls": [],
    }
    evidence = _site_evidence_blob(company_name, domain, scraped)
    already = [{"name": l.get("name"), "role": l.get("role")} for l in (existing_leaders or [])[:8]]
    careers_hint = (scraped or {}).get("_page_urls", {}).get("careers_text") or f"https://{domain}/careers"
    structured = (scraped or {}).get("_structured") or {}
    slim_evidence = "\n".join(p for p in [
        f"Company: {company_name}  Website: {domain}",
        (scraped or {}).get("wikipedia_summary") or ((scraped or {}).get("wikipedia_text") or "")[:1200],
        (structured.get("leadership_text") or (scraped or {}).get("leadership_text") or "")[:2500],
        (structured.get("about_text") or (scraped or {}).get("about_text") or "")[:2000],
    ] if p).strip()
    scrape_names_officers = bool(already) or bool(re.search(
        r"(?i)\b(managing director|\bmd\b|ceo|chief executive|chairman|chairperson|president)\b.{0,40}"
        r"[A-Z][a-z]+|[A-Z][a-z]+\s+[A-Z][a-z].{0,40}"
        r"\b(managing director|\bmd\b|ceo|chairman|president)\b",
        slim_evidence,
    ))
    scrape_note = (
        "SITE SCRAPE HAS NO SITTING OFFICER NAMES. Return an officer only when reliable public evidence "
        "identifies this exact company and role. An empty leaders array is correct when evidence is missing; "
        "never fill from memory or guesswork."
        if not scrape_names_officers else
        "Prefer officers named in EVIDENCE. You may add another officer only when reliable public evidence "
        "identifies this exact company and role; otherwise omit the person."
    )

    extract_prompt = f"""You are filling a public company dossier.

{scrape_note}

Company: {company_name}
Website: {domain}
Already extracted leaders: {json.dumps(already)}

SHORT EVIDENCE (may omit officers):
{slim_evidence or "(site scrape was thin)"}

Return ONLY JSON:
{{
  "headquarters": "city, region, country (street if well known)",
  "founded": "YYYY",
  "leaders": [
    {{"name":"Full Name","role":"Managing Director|CEO|Chairman|President|Director","status":"current|historical","confidence":"High|Medium"}}
  ],
  "careers_url": "https:// official careers page or empty",
  "hiring_roles": [{{"role":"Job title","source_url":"https://..."}}]
}}

Rules:
- THIS company only, matching {domain}. Ignore similarly named firms.
- Return a sitting MD/CEO or Chairman only when supported by the evidence or a clearly matched public source.
  If the role cannot be verified, return no row rather than guessing or using a 19th-century inventor as current.
- Century-old companies: mark origin figures historical. Current operating officers are current.
- Include Vice Chair / whole-time directors when publicly known.
- hiring_roles: job titles tied to an official careers/ATS URL. If openings are not listed
  but a careers page is known, return that URL and one row "Open roles on official careers page".
- Never invent emails, phones, revenue, DIN.
- Never mention ChatGPT, OpenAI, or any AI model.
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Public officers of this exact company; omit any role that is not supported by reliable evidence."},
                {"role": "user", "content": extract_prompt},
            ],
            temperature=0.1, max_tokens=1400, json_mode=True, timeout=80.0 if RESEARCH_DEEP else 35.0,
            reasoning_effort="low",
        )
        extracted = _parse_llm_json(raw)
        print(f"[Research] Public-profile extract: {len(extracted.get('leaders') or [])} people, {len(raw or '')} chars")
    except Exception as e:
        print(f"[Research] Public-profile extract failed: {e}")
        return empty

    def _has_current_officer(rows) -> bool:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "")
            st = str(row.get("status") or auth.leader_status(role))
            if st == "historical":
                continue
            if re.search(r"(?i)\b(managing director|\bmd\b|ceo|chief executive|chairman|chairperson|president|vice chair)", role):
                return True
        return False

    if not _has_current_officer(extracted.get("leaders") or []):
        retry_prompt = f"""Identify CURRENT public officers of {company_name} (official site {domain}).
Return the sitting MD or CEO and Chairman only if reliable public evidence identifies them at this exact company.
If the evidence does not support either person, return an empty leaders array. Do not guess.

Return ONLY JSON:
{{"leaders":[{{"name":"Full Name","role":"Managing Director|CEO|Chairman|President","status":"current","confidence":"High"}}],"careers_url":"https://... or empty"}}
"""
        try:
            raw_r = llm_client.chat(
                [
                    {"role": "system", "content": "Return valid JSON only. Sitting public officers of this exact company; return an empty list when unsupported."},
                    {"role": "user", "content": retry_prompt},
                ],
                temperature=0.0, max_tokens=600, json_mode=True, timeout=50.0 if RESEARCH_DEEP else 25.0,
                reasoning_effort="low",
            )
            retry = _parse_llm_json(raw_r)
            if _has_current_officer(retry.get("leaders") or []):
                print("[Research] Compact leadership retry recovered sitting officers")
                extracted["leaders"] = retry.get("leaders") or extracted.get("leaders") or []
                if retry.get("careers_url") and not extracted.get("careers_url"):
                    extracted["careers_url"] = retry["careers_url"]
        except Exception as e:
            print(f"[Research] Compact leadership retry failed: {e}")
    elif not any(re.search(r"(?i)chair", str((row or {}).get("role") or "")) for row in (extracted.get("leaders") or []) if isinstance(row, dict)):
        chair_prompt = f"""Who is the current Chairman or Chairperson of {company_name} ({domain})?
If the company has a board, name the sitting Chair. Also name Vice Chair if publicly known.

Return ONLY JSON:
{{"leaders":[{{"name":"Full Name","role":"Chairman|Chairperson|Vice Chairperson","status":"current","confidence":"High"}}]}}
"""
        try:
            raw_c = llm_client.chat(
                [
                    {"role": "system", "content": "Return valid JSON only. Sitting board chair of this exact company."},
                    {"role": "user", "content": chair_prompt},
                ],
                temperature=0.0, max_tokens=400, json_mode=True, timeout=40.0 if RESEARCH_DEEP else 25.0,
                reasoning_effort="low",
            )
            extra = _parse_llm_json(raw_c)
            extra_rows = [r for r in (extra.get("leaders") or []) if isinstance(r, dict) and r.get("name")]
            if extra_rows:
                print(f"[Research] Added {len(extra_rows)} chair/vice-chair from supplement")
                extracted["leaders"] = list(extracted.get("leaders") or []) + extra_rows
        except Exception as e:
            print(f"[Research] Chair supplement failed: {e}")

    verify_prompt = f"""You are the LLM-as-judge. Independently keep or drop each claim about
{company_name} (website {domain}).

CANDIDATES:
{json.dumps({
    "headquarters": extracted.get("headquarters") or "",
    "founded": extracted.get("founded") or "",
    "leaders": extracted.get("leaders") or [],
    "careers_url": extracted.get("careers_url") or "",
    "hiring_roles": extracted.get("hiring_roles") or [],
}, ensure_ascii=False)[:3200]}

EVIDENCE (may be incomplete — you MAY use well-known public knowledge of this firm):
{evidence or "(thin)"}

Return ONLY JSON:
{{
  "headquarters": "kept value or empty",
  "founded": "YYYY or empty",
  "keep_leaders": [{{"name":"Full Name","role":"...","status":"current|historical","confidence":"High|Medium"}}],
  "careers_url": "https:// or empty",
  "hiring_roles": [{{"role":"...","source_url":"https://..."}}]
}}

Judge rules:
- KEEP the current MD, CEO, Chairman, President, Vice Chair only when reliable evidence supports that exact seat at THIS company.
- An empty keep_leaders list is correct when the candidates are not supported by evidence. Never add a person from memory.
- DROP customer/partner executives and anyone at a different company.
- DROP 19th/early-20th century inventors labelled as current founder of a listed successor company; they may be kept only as historical.
- Keep hiring_roles only with an official careers/ATS URL for this employer.
- Never mention ChatGPT, OpenAI, or any AI model.
"""
    try:
        raw2 = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. You are a strict verifier. Keep only public officers supported for this exact firm; empty is valid when uncertain."},
                {"role": "user", "content": verify_prompt},
            ],
            temperature=0.0, max_tokens=1200, json_mode=True, timeout=80.0 if RESEARCH_DEEP else 35.0,
            reasoning_effort="low",
        )
        verified = _parse_llm_json(raw2)
    except Exception as e:
        print(f"[Research] Public-profile verify failed: {e}")
        verified = {}

    if verified and "keep_leaders" in verified:
        source_rows = list(verified.get("keep_leaders") or [])
        if not source_rows:
            print("[Research] Profile judge kept no unsupported officer claims")
    else:
        # A failed or malformed verification pass must not leak unverified
        # model-generated people into the report. Existing scraped/Wikidata
        # leaders remain available for the mandatory final report judge.
        source_rows = []

    out_leaders = list(existing_leaders or [])
    seen = {(l.get("name") or "").lower() for l in out_leaders}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        name = re.sub(r"\s+", " ", (row.get("name") or "").strip())
        role = (row.get("role") or "Leadership").strip()
        conf = str(row.get("confidence") or "High")
        if conf.lower() == "low" or not name or len(name.split()) < 2:
            continue
        if company_name.lower() in name.lower() or _is_org_like_name(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        status = str(row.get("status") or auth.leader_status(role))
        out_leaders.append({
            "name": name,
            "role": role[:80],
            "source": "Public company profiles",
            "confidence": "High" if conf.lower() != "medium" else "Medium",
            "background": "Publicly listed executive profile",
            "status": status if status in ("current", "historical") else auth.leader_status(role),
            "is_current": status == "current",
        })

    hq = re.sub(r"\s+", " ", str((verified.get("headquarters") if verified else None)
                                 or extracted.get("headquarters") or "")).strip(" ,;")
    founded = re.sub(r"\s+", " ", str((verified.get("founded") if verified else None)
                                      or extracted.get("founded") or "")).strip()
    ym = re.search(r"\b(19|20)\d{2}\b", founded or "")
    founded = ym.group(0) if ym else ""
    if hq and ("not publicly" in hq.lower() or len(hq) < 4):
        hq = ""

    careers_url = str(
        (verified.get("careers_url") if verified else None)
        or extracted.get("careers_url")
        or careers_hint
        or ""
    ).strip()
    if careers_url and not careers_url.startswith("http"):
        careers_url = ""
    hire_rows = []
    for row in (verified.get("hiring_roles") if verified and "hiring_roles" in verified else None) or extracted.get("hiring_roles") or []:
        if not isinstance(row, dict):
            continue
        role = re.sub(r"\s+", " ", str(row.get("role") or "")).strip()
        href = str(row.get("source_url") or careers_url or "").strip()
        if not role or len(role) < 4:
            continue
        hire_rows.append({"role": role[:80], "source_url": href, "platform": "Official Careers"})
    if not hire_rows and careers_url:
        hire_rows.append({
            "role": "Open roles on official careers page",
            "source_url": careers_url,
            "platform": "Official Careers",
        })

    print(f"[Research] Public-profile fill: {len(out_leaders)} leaders, hq={bool(hq)}, "
          f"founded={founded or '-'}, hiring={len(hire_rows)}")
    return {
        "leaders": out_leaders[:8],
        "headquarters": hq,
        "founded": founded,
        "hiring": hire_rows[:6],
        "urls": [careers_url] if careers_url else [],
    }


def _enrich_leadership_via_llm(company_name: str, domain: str, existing: list) -> list:
    """Back-compat wrapper — two-pass public-profile fill for people only."""
    current = [l for l in (existing or []) if isinstance(l, dict) and (l.get("status") or "current") == "current"]
    if auth.has_operating_exec(existing) and len(current) >= 2:
        return existing or []
    filled = _llm_public_profile_fill(company_name, domain, {}, existing)
    return filled.get("leaders") or (existing or [])


def _enrich_headquarters_via_llm(company_name: str, domain: str) -> dict:
    """
    Resolve the head-office location when the site never publishes one.

    Bot-protected and JS-rendered sites (and plenty of SaaS companies) simply have no
    address in their HTML. Search snippets are used as evidence and the resulting
    value is attributed to the public profiles it came from — never to the model.
    """
    snippets, urls = [], []
    for q in [
        f'"{company_name}" headquarters address city',
        f'"{company_name}" "head office" OR "corporate office" location',
    ]:
        for r in _ddg_search(q, max_results=4):
            href = r.get("href") or ""
            if any(x in href.lower() for x in ("chatgpt.com", "chat.openai.com")):
                continue
            snippets.append(f"{r.get('title','')}: {r.get('body','')}")
            if href.startswith("http"):
                urls.append(href)
    evidence = "\n".join(snippets)[:3000]
    prompt = f"""From the EVIDENCE, identify the head-office location of this exact company.
If evidence is thin, you MAY use well-known public knowledge of THIS company only
(the one whose website is {domain}).

Company: {company_name}
Website: {domain}

EVIDENCE:
{evidence or "(no search snippets)"}

Rules:
- Only use the company that matches the website domain above. Ignore similarly named firms.
- Return the city and country at minimum; include the street address only if you are confident.
- If you cannot identify this company's head office, return an empty string.
- Never invent an address. Never mention ChatGPT, OpenAI or any AI model.

Return ONLY JSON: {{"headquarters":"City, State, Country","confidence":"High|Medium|Low"}}"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Extract from evidence or well-known public knowledge of this firm; prefer empty over guesses."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.05, max_tokens=250, json_mode=True, timeout=60.0,
        )
        data = _parse_llm_json(raw)
    except Exception as e:
        print(f"[Research] HQ enrich failed: {e}")
        return {}

    hq = re.sub(r"\s+", " ", str(data.get("headquarters") or "")).strip(" ,;")
    conf = str(data.get("confidence") or "Medium")
    if not hq or len(hq) < 4 or conf.lower() == "low":
        return {}
    head = re.split(r"[,\n]", hq)[0].strip()
    if evidence and len(head) > 2 and head.lower() not in evidence.lower() and conf.lower() != "high":
        print(f"[Research] Dropped ungrounded HQ '{hq}' for {company_name}")
        return {}
    print(f"[Research] HQ resolved from public profiles: {hq}")
    return {"headquarters": hq, "confidence": "Medium" if conf.lower() != "high" else "High", "urls": urls[:3]}


def _collect_leadership(
    company_name: str,
    domain: str,
    scraped: dict,
    intel: dict,
    *,
    search_public_web: bool = True,
) -> list:
    """Gather leadership: Wikidata current execs first, then website/Wikipedia, then LLM gap-fill."""
    leaders = []
    wd = (intel or {}).get("_wikidata") or (scraped or {}).get("_wikidata") or {}
    leaders.extend(wikidata_client.leaders_from_wikidata(wd))
    structured = (scraped or {}).get("_structured") or {}
    page_urls = (scraped or {}).get("_page_urls") or {}
    for key, label in (
        ("leadership_text", "Company leadership page"),
        ("about_text", "Company about page"),
        ("homepage_text", "Company website"),
    ):
        # Card layouts first — they carry the real title next to the name
        leaders.extend(_parse_leadership_cards(
            structured.get(key) or "", label, company_name, domain, page_urls.get(key, "")
        ))
        leaders.extend(_parse_leadership_from_text(scraped.get(key) or "", label, company_name))

    wiki = scraped.get("wikipedia_text") or ""
    wiki_url = scraped.get("wikipedia_url") or ""
    if wiki:
        leaders.extend(_parse_leadership_from_text(wiki, wiki_url or "Wikipedia", company_name))

    leaders.extend(_parse_leadership_from_text(intel.get("ceo_founder") or "", "Public web", company_name))
    for page in intel.get("_scraped_pages") or []:
        cat = (page.get("category") or "").lower()
        dom = (page.get("domain") or "").lower()
        if any(k in cat for k in ("encyclopedia", "company profile", "news", "financial", "org chart")):
            leaders.extend(_parse_leadership_from_text(
                page.get("text") or "", page.get("domain") or "Public web", company_name
            ))
        elif any(x in dom for x in ("theorg.com", "the.org", "linkedin.com", "crunchbase.com")):
            leaders.extend(_parse_leadership_from_text(
                page.get("text") or page.get("snippet") or "", page.get("domain") or "Public web", company_name
            ))

    # Public-web people search whenever the site did not name a sitting MD/CEO/Chair.
    if search_public_web and not auth.has_operating_exec(leaders):
        queries = [
            f'"{company_name}" current "managing director" OR MD OR CEO OR chairman',
            f'"{company_name}" current CEO OR "chief executive"',
            f"site:theorg.com {company_name}",
            f'"{company_name}" founder OR co-founder',
        ]
        if not RESEARCH_DEEP:
            queries = queries[:2]
        def _leadership_search(query: str) -> list:
            try:
                return _ddg_search(query, max_results=3)
            except Exception as exc:  # noqa: BLE001
                print(f"[Research] Leadership search failed for '{query}': {exc}")
                return []

        # These are independent public searches. Running them together reduces
        # network wait without changing the source filters or accepted rows.
        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
            for q, search_rows in zip(queries, pool.map(_leadership_search, queries)):
                for r in search_rows or []:
                    href = (r.get("href") or "").lower()
                    if any(x in href for x in ("chatgpt.com", "chat.openai.com", "openai.com/chat")):
                        continue
                    blob = f"{r.get('title','')} {r.get('body','')}"
                    if not _blob_matches_brand(blob, company_name, domain):
                        continue
                    src = urlparse(r.get("href") or "").netloc.replace("www.", "") or "Web search"
                    leaders.extend(_parse_leadership_from_text(blob, src, company_name))

    out, seen = [], set()
    for l in leaders:
        key = (l.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(l)
    out = _normalize_leadership_list(out, company_name, scraped)
    print(f"[Research] Leadership extracted from public web: {len(out)} people")
    return auth.rank_leadership(out)[:8]


def _snippets(results: list, max_chars: int = 2000) -> str:
    parts = [f"[{r.get('title','')}] {r.get('body','')}" for r in results if r.get("body")]
    return " | ".join(parts)[:max_chars]


PUBLIC_SOURCE_SITES = [
    ("tofler.in", "Financial / Directors"),
    ("ambitionbox.com", "Employee Reviews"),
    ("glassdoor.", "Employee Reviews"),
    ("linkedin.com", "Company Profile"),
    ("theorg.com", "Org Chart / Leadership"),
    ("the.org", "Org Chart / Leadership"),
    ("crunchbase.com", "Funding / Company"),
    ("tracxn.com", "Startup / Funding"),
    ("wikipedia.org", "Encyclopedia"),
    ("justdial.com", "Local Business Contacts"),
    ("indiamart.com", "B2B Catalog / Contacts"),
    ("tradeindia.com", "B2B Catalog / Contacts"),
    ("economictimes.", "News / Business"),
    ("business-standard.com", "News / Business"),
    ("moneycontrol.com", "Finance"),
    ("opencorporates.com", "Global Registry"),
    ("bloomberg.com", "News / Finance"),
    ("reuters.com", "News"),
]


def _site_category(url: str, company_domain: str = "") -> str:
    return auth.classify_source(url, company_domain)


def _extract_contacts_from_text(text: str, source_label: str) -> dict:
    emails, phones = [], []
    email_pat = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    phone_pat = re.compile(
        r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{3,5}(?:[\s\-]?\d{2,5})?"
    )
    name_phone = re.compile(
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z\.]+){0,3})\s*[:\-]?\s*((?:\+?\d[\d\s\-().]{8,}\d))"
    )
    seen_e, seen_p = set(), set()
    for em in email_pat.findall(text or ""):
        em = em.lower()
        if em in seen_e or em.endswith((".png", ".jpg", ".css", ".js")):
            continue
        if "example" in em or "domain.com" in em:
            continue
        seen_e.add(em)
        person = ""
        m = re.match(r"^([a-zA-Z]+(?:[._\-][a-zA-Z]+)+)@", em)
        if m:
            person = m.group(1).replace(".", " ").replace("_", " ").replace("-", " ").title()
        emails.append({
            "email": em, "label": person or "Public Web", "person": person,
            "source": source_label, "confidence": "Medium", "verified": True,
        })
    for m in name_phone.finditer(text or ""):
        name, num = m.group(1).strip(), m.group(2).strip()
        if not _is_valid_phone(num):
            continue
        digits = re.sub(r"\D", "", num)
        if digits in seen_p:
            continue
        seen_p.add(digits)
        phones.append({
            "number": num, "label": name, "person": name,
            "source": source_label, "confidence": "Medium", "verified": True,
        })
    for m in phone_pat.finditer(text or ""):
        num = m.group(0).strip()
        if not _is_valid_phone(num):
            continue
        digits = re.sub(r"\D", "", num)
        if digits in seen_p:
            continue
        seen_p.add(digits)
        phones.append({
            "number": num, "label": "Public Web", "person": "",
            "source": source_label, "confidence": "Low", "verified": True,
        })
    return {"emails": emails[:8], "phones": phones[:8]}


def _mcp_discover_urls(company_name: str, domain: str) -> list:
    """Search Agent — find public URLs across many websites (fast path)."""
    print(f"[MCP Search] Discovering public sources for '{company_name}'...")
    found, seen = [], set()
    if RESEARCH_DEEP:
        site_queries = [
            f'"{company_name}" company overview',
            f"site:linkedin.com/company {company_name}",
            f"{company_name} {domain} competitors",
            f'"{company_name}" alternatives',
            f"{company_name} news",
            f'"{company_name}" CEO OR founder',
        ]
        max_results = 3
    else:
        site_queries = [
            f'"{company_name}" competitors',
            f'"{company_name}" alternatives',
            f'"{company_name}" news',
        ]
        max_results = 2

    def _one_query(q: str) -> list:
        rows = []
        for r in _ddg_search(q, max_results=max_results):
            href = r.get("href") or r.get("link") or ""
            if not href.startswith("http"):
                continue
            try:
                d = urlparse(href).netloc.replace("www.", "").lower()
            except Exception:
                continue
            if not d:
                continue
            if any(x in d for x in (
                "google.", "youtube.com", "duckduckgo", "zaubacorp.com",
                "chatgpt.com", "chat.openai.com", "openai.com/chat",
                "accounts.google", "login.microsoftonline",
            )):
                continue
            rows.append({
                "title": (r.get("title") or d)[:80],
                "url": href,
                "category": _site_category(href, domain),
                "domain": d,
                "snippet": (r.get("body") or "")[:300],
            })
        return rows

    with ThreadPoolExecutor(max_workers=min(4, len(site_queries))) as pool:
        for rows in pool.map(_one_query, site_queries):
            for item in rows:
                d = item.get("domain")
                if not d or d in seen:
                    continue
                seen.add(d)
                found.append(item)

    print(f"[MCP Search] Discovered {len(found)} unique public domains")
    return found


def _mcp_scrape_sources(discovered: list, company_domain: str, max_pages: int = 12) -> list:
    """Turn search hits into source records. Default: snippets only (no extra HTTP)."""
    if not RESEARCH_DEEP:
        pages = []
        for item in (discovered or [])[:max_pages]:
            pages.append({
                "url": item.get("url") or "",
                "domain": item.get("domain") or "",
                "category": item.get("category") or "Public Web",
                "title": item.get("title") or "",
                "text": item.get("snippet") or "",
                "emails": [],
                "phones": [],
                "retrieved": False,
            })
        print(f"[MCP Scrape] Using {len(pages)} search snippets (no extra page downloads)")
        return pages

    from backend.services.llm_judge import is_junk_page_text
    print(f"[MCP Scrape] Visiting up to {max_pages} public websites...")
    scraped_pages = []
    priority, rest = [], []
    for item in discovered:
        cat = item.get("category", "")
        url_l = (item.get("url") or "").lower()
        if any(x in url_l for x in ("keka.com", "/login", "signin", "accounts.google", "zaubacorp.com")):
            continue
        if any(k in cat for k in ("Registry", "Reviews", "Contacts", "Financial", "Company Profile", "B2B", "News")):
            priority.append(item)
        else:
            rest.append(item)

    candidates = []
    for item in (priority + rest):
        if company_domain and company_domain in (item.get("domain") or ""):
            continue
        candidates.append(item)
        if len(candidates) >= max_pages * 2:
            break

    page_timeout = 4 if RESEARCH_FAST else 8

    def _scrape_one(item: dict) -> dict | None:
        url = item["url"]
        try:
            text = _fetch_page(url, timeout=page_timeout)
            if len(text) < 200 or is_junk_page_text(text, url):
                print(f"[MCP Scrape] skip (thin/junk): {item.get('domain')}")
                return None
            contacts = _extract_contacts_from_text(
                text, f"{item.get('domain')} ({item.get('category')})"
            )
            print(
                f"[MCP Scrape] OK {item.get('domain')} — {len(text)} chars, "
                f"{len(contacts['emails'])}e/{len(contacts['phones'])}p"
            )
            return {
                "title": item.get("title", ""),
                "url": url,
                "domain": item.get("domain", ""),
                "category": item.get("category", "Public Web"),
                "snippet": item.get("snippet", ""),
                "text": text[:2500],
                "emails": contacts["emails"],
                "phones": contacts["phones"],
                "retrieved": True,
                "favicon": f"https://www.google.com/s2/favicons?domain={item.get('domain','')}&sz=64",
            }
        except Exception as e:
            print(f"[MCP Scrape] fail {item.get('domain')}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(candidates)))) as pool:
        futures = [pool.submit(_scrape_one, item) for item in candidates]
        for fut in as_completed(futures):
            page = fut.result()
            if page:
                scraped_pages.append(page)
            if len(scraped_pages) >= max_pages:
                for other in futures:
                    other.cancel()
                break

    print(f"[MCP Scrape] Successfully scraped {len(scraped_pages)} public sites")
    return scraped_pages[:max_pages]


def _collect_intelligence(company_name: str, domain: str) -> dict:
    """
    MCP pipeline:
      1. Search Agent  — find many public URLs (ZaubaCorp, Tofler, AmbitionBox, Justdial, …)
      2. Scrape Agent  — visit & scrape each site (not just search snippets)
      3. Merge         — combine text + contacts from everywhere
    """
    intel = {
        "_source_urls": [],
        "_scraped_pages": [],
        "_multi_contacts": {"emails": [], "phones": []},
    }

    discovered = _mcp_discover_urls(company_name, domain)
    for d in discovered:
        intel["_source_urls"].append({
            "title": d.get("title", ""),
            "url": d.get("url", ""),
            "category": d.get("category", "Public Web"),
        })

    scraped_pages = _mcp_scrape_sources(
        discovered, domain, max_pages=6 if RESEARCH_DEEP else 4
    )
    intel["_scraped_pages"] = scraped_pages

    seen_e, seen_p = set(), set()
    for page in scraped_pages:
        for e in page.get("emails", []):
            if e["email"] not in seen_e:
                seen_e.add(e["email"])
                intel["_multi_contacts"]["emails"].append(e)
        for ph in page.get("phones", []):
            key = re.sub(r"\D", "", ph.get("number", ""))
            if key and key not in seen_p:
                seen_p.add(key)
                intel["_multi_contacts"]["phones"].append(ph)

    buckets = {k: [] for k in (
        "competitors_direct", "revenue", "employees", "glassdoor",
        "ceo_founder", "news_recent", "market_position", "products",
        "contact_email", "india_registry",
    )}
    for page in scraped_pages:
        cat = (page.get("category") or "").lower()
        blob = f"[{page.get('domain')}] {page.get('text','')[:500]}"
        if "review" in cat:
            buckets["glassdoor"].append(blob)
            buckets["employees"].append(blob)
        elif "registry" in cat or "financial" in cat:
            buckets["india_registry"].append(blob)
            buckets["revenue"].append(blob)
            buckets["ceo_founder"].append(blob)
        elif "news" in cat:
            buckets["news_recent"].append(blob)
        elif "contact" in cat or "b2b" in cat:
            buckets["contact_email"].append(blob)
            buckets["products"].append(blob)
        elif "company profile" in cat:
            buckets["ceo_founder"].append(blob)
            buckets["employees"].append(blob)
        else:
            buckets["market_position"].append(blob)

    for key, parts in buckets.items():
        intel[key] = " || ".join(parts)[:1200]

    digest = []
    for page in scraped_pages[:10]:
        digest.append(
            f"SOURCE: {page.get('domain')} ({page.get('category')})\n"
            f"URL: {page.get('url')}\n"
            f"CONTENT: {page.get('text','')[:700]}\n"
        )
    intel["multi_source_digest"] = "\n---\n".join(digest)[:5500]

    print(f"[MCP] Done — {len(scraped_pages)} sites scraped, "
          f"{len(intel['_multi_contacts']['emails'])} emails, "
          f"{len(intel['_multi_contacts']['phones'])} phones from public web")
    return intel


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — Prompt + Analysis
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior business intelligence analyst for GLOBAL company research.
Produce ACCURATE reports using ONLY the website + public web sources provided.
Rules:
- Never invent private data (emails, phones, DIN, revenue). Public officers and HQ may be filled from well-known public knowledge of THIS company when the scrape is thin; a later verification pass will drop anything unsure.
- Do NOT use Indian MCA / ZaubaCorp / CIN. Leadership only if clearly named in the provided sources (website, Wikipedia, reputable scrapes).
- Stay faithful to sources: copy names/roles exactly as written; never guess founders or directors.
- Cite a source domain for each fact. Output ONLY valid JSON.
- For numeric facts (revenue, funding, headcount) missing from sources => Not publicly available.
- Competitors MUST be same industry / same work domain as the website. Never mix unrelated domains.
- Geographic reach MUST be a short STRING (e.g. "Global" or "India, UAE") — never a nested object.
- Leadership: prefer CURRENT CEO / MD / President. Founders who no longer run the company are historical, not the point of contact.
- For numeric facts (revenue, funding, headcount) missing from sources => Not publicly available.
- Revenue must include currency AND scale (million/billion/crore). Never use a stock price as revenue.
- Competitors MUST be same industry / same work domain as the website. Never mix unrelated domains.
- If unsure about a fact, use Not publicly available with Low confidence — never guess."""


def _build_prompt(url, company_name, scraped, intel):
    """Compact prompt — must stay under Groq free-tier TPM (~8000 tokens)."""
    def clip(s, n=600):
        return (s or "")[:n]

    contact = scraped.get("contact_data") or {}

    wd = intel.get("_wikidata") or scraped.get("_wikidata") or {}
    wd_line = ""
    if wd.get("matched"):
        wd_line = (
            f"WIKIDATA (official-website match — treat as high-trust, do not contradict):\n"
            f"CEO={', '.join(wd.get('ceo') or []) or 'n/a'}; "
            f"chair={', '.join(wd.get('chair') or []) or 'n/a'}; "
            f"founders={', '.join(wd.get('founders') or []) or 'n/a'}; "
            f"HQ={wd.get('headquarters') or 'n/a'}; founded={wd.get('founded_year') or 'n/a'}; "
            f"employees={wd.get('employees') or 'n/a'}; revenue={wd.get('revenue') or 'n/a'}\n"
        )

    # The deep-search stage already retrieves these public pages, so pass a
    # compact, URL-preserving subset into synthesis instead of asking the model
    # to fill profile fields from the company homepage alone.
    public_evidence = []
    seen_evidence_urls = set()
    for page in (intel.get("_scraped_pages") or [])[:6]:
        if not isinstance(page, dict):
            continue
        source_url = str(page.get("url") or "").strip()
        text = re.sub(r"\s+", " ", str(page.get("text") or page.get("snippet") or "")).strip()
        if not source_url.startswith(("http://", "https://")) or not text:
            continue
        public_evidence.append({
            "category": str(page.get("category") or "Public Web")[:50],
            "title": str(page.get("title") or page.get("domain") or "Public source")[:100],
            "url": source_url,
            "excerpt": text[:420],
        })
        seen_evidence_urls.add(source_url)
    for row in (intel.get("_source_urls") or []):
        if len(public_evidence) >= 9:
            break
        if not isinstance(row, dict):
            continue
        source_url = str(row.get("url") or "").strip()
        if not source_url.startswith(("http://", "https://")) or source_url in seen_evidence_urls:
            continue
        public_evidence.append({
            "category": str(row.get("category") or "Public Web")[:50],
            "title": str(row.get("title") or "Search result")[:100],
            "url": source_url,
            "excerpt": "Search result reference; page text was not retrieved.",
        })
        seen_evidence_urls.add(source_url)
    public_evidence_text = json.dumps(public_evidence, ensure_ascii=False)[:3000]

    return f"""Company: {company_name}
URL: {url}
Title: {clip(scraped.get('title'), 120)}
Description: {clip(scraped.get('description'), 300)}
Homepage: {clip(scraped.get('homepage_text'), 500)}
About: {clip(scraped.get('about_text'), 900)}
Products: {clip(scraped.get('products_text'), 320)}
Leadership page: {clip(scraped.get('leadership_text') or (scraped.get('_structured') or {}).get('leadership_text') or (scraped.get('_structured') or {}).get('about_text'), 800)}
Wikipedia: {clip(scraped.get('wikipedia_summary') or scraped.get('wikipedia_text'), 800)}
{wd_line}
ADDITIONAL PUBLIC WEB EVIDENCE (each URL is a candidate source; do not treat an un-fetched search result as page verification):
{public_evidence_text}
CONTACTS already scraped (copy into contact_intelligence, do not invent):
emails={clip(json.dumps(contact.get('emails',[])), 400)}
phones={clip(json.dumps(contact.get('phones',[])), 400)}
address={clip(contact.get('address'), 160)}

Return ONLY compact JSON. IMPORTANT schema rules:
- company_profile: object with name, website, description; founded/etc as {{value,source,confidence}}
- products_services: {{"primary_offerings":[{{"item","source","confidence"}}], "pricing_model":{{...}}, "target_customers":{{...}}}}
- market_analysis: {{"industry":{{...}},"market_position":{{...}},"market_trends":{{"value":"...","source_url":"...","confidence":"..."}},"geographic_reach":{{...}}}}
- swot_analysis: strengths/weaknesses/opportunities/threats as arrays of
  {{"point","source","confidence"}}. Include only supported observations or clearly labeled analysis; fewer than 3 is better than padding with generic claims.
- competitors: up to 4 evidence-supported objects {{"name","description","official_domain","market_location","overlap_reason","evidence_url","threat_level","source","confidence"}}. Return fewer when the evidence does not establish a direct competitor in the same business domain and market.
- leadership_team: array of {{"name","role","source","confidence","background"}} for people supported by Wikipedia/website/leadership sources or clearly domain-matched public evidence. If evidence is missing, return an empty array; never fill a role from memory.
- risk_assessment: overall_risk_level plus regulatory/competitive/operational/reputational_risks as arrays of {{"risk","source","confidence","evidence_url","basis"}}. Do not infer a company-specific risk from generic industry assumptions.
- financial_data: revenue/funding only if found in retrieved source text or domain-matched Wikidata; else Not publicly available. Never infer a funding stage or profitability.
- recent_news: up to 4 company-specific news items or events with a date, source_url, summary, kind (news/event), and confidence. Only include items supported by supplied sources; upcoming dates are allowed only for clearly identified events. Do not invent news or events.
- intelligence_score: {{"overall","data_completeness","source_reliability","summary"}}
Do NOT wrap whole sections in a single {{value,source,confidence}} object.
Never invent people or exact revenue/funding numbers. No CIN / MCA fields."""


def _analyze_with_llm(prompt: str) -> dict:
    """Analyze scraped intel with Azure OpenAI (production primary)."""
    safe_prompt = (
        "No invented people/revenue. Leadership only from website or clear public sources. "
        "Do not use Indian MCA / ZaubaCorp. Competitors must match the company's actual domain of work. "
        "Never cite ChatGPT sign-in pages or UI chrome. If unsure, use Not publicly available. "
        "Geographic reach must match THIS company (global / regional / HQ country) — never default to India. "
        "Return ONLY valid JSON.\n\n"
        + prompt
    )
    # Keep under reasoning-model practical limits (large prompts → empty Azure content)
    if len(safe_prompt) > 8000:
        safe_prompt = safe_prompt[:8000]

    max_tok = 3500
    llm_timeout = REPORT_LLM_TIMEOUT

    def _call(prompt_text: str, tokens: int = max_tok) -> str:
        return llm_client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT[:1200]},
                {"role": "user", "content": prompt_text},
            ],
            temperature=0.15,
            max_tokens=tokens,
            json_mode=True,
            timeout=llm_timeout,
            reasoning_effort="low",
            retry_empty=False,
        )

    def _parse(raw_text: str) -> dict:
        text = re.sub(r"^```(?:json)?", "", (raw_text or ""), flags=re.MULTILINE).strip()
        text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
        return json.loads(text)

    raw = _call(safe_prompt)
    print(f"[Research] LLM raw response: {len(raw)} chars")
    try:
        return _parse(raw)
    except json.JSONDecodeError as e:
        print(f"[Research] JSON parse error: {e} — using baseline (skip slow LLM retry)")
        return {"error": f"JSON parse failed: {e}", "raw": (raw or "")[:2000]}


def _analyze_with_groq(prompt: str) -> dict:
    """Back-compat alias."""
    return _analyze_with_llm(prompt)


def _baseline_report(url, company_name, scraped) -> dict:
    """Scrape-only report when LLM fails — still fill competitors/SWOT/news from public signals."""
    cd = scraped.get("contact_data") or {}
    domain = urlparse(url).netloc.replace("www.", "")
    intel_stub = {
        "competitors_direct": "",
        "news_recent": "",
        "market_position": scraped.get("wikipedia_summary") or "",
        "glassdoor": "",
        "employees": "",
        "multi_source_digest": scraped.get("wikipedia_text") or "",
        "_scraped_pages": [],
        "_source_urls": [],
    }
    wiki_sum = _clean_snippet(scraped.get("wikipedia_summary") or "", 320) or ""
    site_desc = _clean_snippet(scraped.get("description") or "", 280) or ""
    leaders = _normalize_leadership_list(
        _collect_leadership(company_name, domain, scraped, intel_stub),
        company_name,
        scraped,
    )
    comps = _extract_competitors(company_name, intel_stub, scraped)
    return {
        "company_profile": {
            "name": company_name,
            "website": url,
            "description": wiki_sum or site_desc or (scraped.get("homepage_text") or "")[:280],
            "industry": _field(
                scraped.get("wikipedia_description") or "Not publicly available",
                "Wikipedia" if scraped.get("wikipedia_description") else "Website",
                "High" if scraped.get("wikipedia_description") else "Low",
            ),
            "founded": {
                "value": "Not publicly available",
                "source": "Website",
                "confidence": "Low",
            },
            "headquarters": {
                "value": cd.get("address") or "Not publicly available",
                "source": "Website", "confidence": "Medium" if cd.get("address") else "Low",
            },
        },
        "leadership_team": leaders,
        "contact_intelligence": {
            "emails": cd.get("emails") or [],
            "phones": [p for p in (cd.get("phones") or []) if _is_valid_phone(p.get("number") or "")],
            "registered_address": cd.get("address") or "",
        },
        "competitors": comps,
        "swot_analysis": _heuristic_swot(scraped, intel_stub, company_name),
        "market_analysis": {
            "industry": _field(
                scraped.get("wikipedia_description") or "Not publicly available",
                "Wikipedia" if scraped.get("wikipedia_description") else "Website",
                "High" if scraped.get("wikipedia_description") else "Low",
            ),
            "market_position": _field(
                wiki_sum or site_desc or "Not publicly available",
                "Wikipedia" if wiki_sum else "Website",
                "High" if wiki_sum else "Low",
            ),
            "geographic_reach": _field("Not publicly available", "Public sources", "Low"),
        },
        "products_services": {
            "primary_offerings": _offerings_from_scrape(scraped),
            "pricing_model": _field("Quote-based / not listed publicly", "Website", "Medium"),
            "target_customers": _field("Not publicly available", "Website", "Low"),
        },
        "intelligence_score": {
            "overall": 55,
            "data_completeness": 45,
            "source_reliability": 55,
            "summary": "Public-web scrape report (LLM synthesis unavailable — facts from sources only).",
        },
        "ai_conclusion": f"Public scrape report for {company_name} using website and verified public sources.",
        "signals_used": [],
        "hiring_signals": [],
        "recent_news": [],
    }


def _is_india_subsidiary_for_global_site(legal_name: str, domain: str, site_title: str = "") -> bool:
    """
    True when MCA entity is an India local arm, but researched website is the global brand
    (e.g. microsoft.com → Microsoft Corporation (India) Pvt Ltd).
    MCA directors are REAL for that India entity — NOT global company leadership (CEO/board).
    """
    legal = (legal_name or "").upper()
    if not legal:
        return False
    dom = (domain or "").lower().replace("www.", "")
    if dom.endswith(".in") or ".co.in" in dom:
        return False  # Indian site → India entity is appropriate

    has_india_in_name = bool(re.search(r"\bINDIA\b", legal)) or "(INDIA)" in legal
    global_stems = {
        "microsoft", "google", "amazon", "apple", "meta", "facebook", "ibm",
        "oracle", "salesforce", "adobe", "intel", "nvidia", "netflix", "uber",
        "airbnb", "spotify", "twitter", "x", "linkedin", "github", "samsung",
        "sony", "cisco", "dell", "hp", "huawei", "tiktok", "bytedance",
    }
    stem = dom.split(".")[0]
    is_global_brand_site = stem in global_stems

    if is_global_brand_site and has_india_in_name:
        return True
    if is_global_brand_site and ("PRIVATE LIMITED" in legal or "PVT" in legal):
        # Global brand site matched an India Pvt Ltd entity
        return True
    if has_india_in_name and is_global_brand_site:
        return True
    return False


def _field(value, source="Website", confidence="Medium"):
    if isinstance(value, dict) and "value" in value:
        inner = auth.flatten_display(value.get("value"))
        return {
            "value": inner or "Not publicly available",
            "source": value.get("source") or source,
            "confidence": value.get("confidence") or confidence,
        }
    text = auth.flatten_display(value)
    return {
        "value": text if text else "Not publicly available",
        "source": source,
        "confidence": confidence if text else "Low",
    }


def _looks_empty(section) -> bool:
    if not section:
        return True
    if isinstance(section, dict):
        # Groq sometimes returns {"value":"Not publicly available",...} for a whole section
        if set(section.keys()) <= {"value", "source", "confidence"}:
            v = section.get("value")
            if v in (None, "", [], {}) or (isinstance(v, str) and "not publicly" in v.lower()):
                return True
            # value is a list of products — not empty, but wrong shape
            return False
        if "strengths" in section or "primary_offerings" in section or "market_position" in section:
            return False
    return False


def _industry_context(scraped: dict, intel: dict) -> dict:
    """Detect industry label + peer set that works for ANY company type."""
    blob = " ".join([
        scraped.get("title") or "",
        scraped.get("description") or "",
        scraped.get("homepage_text") or "",
        scraped.get("about_text") or "",
        scraped.get("products_text") or "",
        intel.get("products") or "",
        intel.get("market_position") or "",
        intel.get("multi_source_digest") or "",
    ]).lower()

    # Prefer company identity and offering copy. Broad terms buried in long
    # pages (e.g. "engineering" on a pharma careers page) should not override
    # the actual business sector.
    primary_blob = " ".join([
        scraped.get("title") or "",
        scraped.get("description") or "",
        scraped.get("keywords") or "",
        (scraped.get("products_text") or "")[:3000],
        (scraped.get("about_text") or "")[:2500],
    ]).lower()

    # (label, keywords, peer list of (name, desc, threat))
    catalogs = [
        ("engineering",
         r"structural|civil engineer|bim|construction|epc|infrastructure|consulting engineer",
         [
             ("Larsen & Toubro", "Large Indian engineering & construction conglomerate", "High"),
             ("Tata Projects", "Major Indian EPC / infrastructure player", "High"),
             ("AECOM", "Global infrastructure consulting firm", "High"),
             ("Jacobs", "Global technical professional services", "Medium"),
             ("WSP", "Global engineering professional services", "Medium"),
         ]),
        ("software",
         r"\bsaas\b|software|cloud|devops|fintech|app development|ai\b|machine learning|it services|digital product",
         [
             ("Infosys", "Large Indian IT services firm", "High"),
             ("TCS", "Global IT services & consulting", "High"),
             ("Wipro", "IT services & digital transformation", "High"),
             ("Freshworks", "SaaS product company", "Medium"),
             ("Zoho", "Business software suite", "Medium"),
         ]),
        ("manufacturing",
         r"manufactur|factory|industrial|automotive|textile|chemical|steel|pharma production",
         [
             ("Tata Steel", "Large industrial manufacturer", "High"),
             ("Reliance Industries", "Diversified industrial conglomerate", "High"),
             ("Mahindra", "Auto / industrial group", "Medium"),
             ("Bharat Forge", "Engineering / manufacturing peer", "Medium"),
         ]),
        ("healthcare",
         r"hospital|clinic|pharma|healthcare|medical|diagnostic|biotech",
         [
             ("Apollo Hospitals", "Large hospital chain", "High"),
             ("Fortis Healthcare", "Hospital / healthcare network", "High"),
             ("Dr. Reddy's", "Pharmaceutical company", "Medium"),
             ("Practo", "Digital health platform", "Medium"),
         ]),
        ("travel_tourism",
         r"travel|tourism|trip planning|travel planner|itinerary|holiday packages|vacation booking",
         [
             ("Expedia Group", "Online travel booking and trip-planning services", "High"),
             ("Booking Holdings", "Online travel booking platforms", "High"),
             ("Tripadvisor", "Travel planning, reviews, and booking marketplace", "Medium"),
             ("MakeMyTrip", "Online travel booking and holiday packages", "Medium"),
         ]),
        ("music_entertainment",
         r"music|record label|songs?|film music|audio|entertainment label|carvaan|gramophone|streaming music|music company",
         [
             ("T-Series", "Indian music / film soundtrack label", "High"),
             ("Sony Music Entertainment", "Global music major / Indian operations", "High"),
             ("Warner Music Group", "Global music major", "High"),
             ("Zee Music Company", "Indian film music label", "Medium"),
             ("Tips Industries", "Indian music & film entertainment", "Medium"),
         ]),
        ("ecommerce",
         r"e-?commerce|online store|marketplace|retail|d2c|fashion brand",
         [
             ("Amazon", "Global marketplace / e-commerce", "High"),
             ("Flipkart", "Major e-commerce platform", "High"),
             ("Myntra", "Fashion e-commerce", "Medium"),
             ("Shopify merchants / DTC peers", "Direct-to-consumer brands in the same category", "Medium"),
         ]),
        ("education",
         r"edtech|education|university|school|learning|training institute|coaching",
         [
             ("BYJU'S", "Large edtech brand", "High"),
             ("Unacademy", "Online learning platform", "High"),
             ("upGrad", "Higher-ed / upskilling", "Medium"),
             ("Coursera", "Global online learning", "Medium"),
         ]),
        ("logistics",
         r"logistics|supply chain|warehouse|freight|shipping|courier|3pl",
         [
             ("Delhivery", "Indian logistics / fulfillment", "High"),
             ("Blue Dart", "Express logistics", "High"),
             ("Mahindra Logistics", "Supply-chain services", "Medium"),
             ("Gati", "Freight / logistics", "Medium"),
         ]),
        ("professional_services",
         r"consulting|advisory|legal|audit|accounting|marketing agency|creative agency",
         [
             ("Deloitte", "Big-4 professional services", "High"),
             ("EY", "Big-4 advisory / assurance", "High"),
             ("Accenture", "Global consulting / digital", "High"),
             ("McKinsey", "Strategy consulting", "Medium"),
         ]),
    ]
    specific_first = ("healthcare", "travel_tourism", "music_entertainment", "education", "logistics")
    for preferred_label in specific_first:
        for label, pattern, peers in catalogs:
            if label == preferred_label and re.search(pattern, primary_blob):
                return {"label": label, "peers": peers, "blob": blob}
    for label, pattern, peers in catalogs:
        if label in specific_first:
            continue
        if re.search(pattern, blob):
            return {"label": label, "peers": peers, "blob": blob}

    return {
        "label": "general",
        "peers": [
            ("Regional market leaders", "Larger firms with overlapping customers in the same sector", "High"),
            ("Specialist boutiques", "Niche players competing on expertise / price", "Medium"),
            ("Digital-first entrants", "Newer firms using online acquisition channels", "Medium"),
            ("Global vendors", "International brands expanding into the same geography", "Medium"),
        ],
        "blob": blob,
    }


def _heuristic_swot(scraped: dict, intel: dict, company_name: str = "") -> dict:
    """Build only observable SWOT signals; avoid generic company-risk claims."""
    about = (scraped.get("about_text") or scraped.get("homepage_text") or "")
    products = (scraped.get("products_text") or "")
    desc = (scraped.get("description") or "")
    reviews = (intel.get("glassdoor") or intel.get("employees") or "")
    market = (intel.get("market_position") or intel.get("competitors_direct") or "")
    home_l = (about + " " + desc + " " + products).lower()
    ctx = _industry_context(scraped, intel)
    label = ctx["label"]
    name = company_name or "Company"

    strengths = []
    for m in re.finditer(
        r"(\d+\+?\s*(?:years?|yrs?|projects?|clients?|customers?|users?|team members?|"
        r"employees?|engineers?|offices?|stores?|%[^.\n]{0,40}))",
        about + " " + desc, re.I,
    ):
        strengths.append({"point": m.group(1).strip(), "source": "Homepage", "confidence": "High"})
    if products:
        strengths.append({"point": "Clear public product/service offering documented on the website",
                          "source": "Company Website", "confidence": "High"})
    if scraped.get("social_links"):
        domains = [urlparse(s).netloc.replace("www.", "") for s in scraped["social_links"][:3]]
        strengths.append({"point": f"Public social presence ({', '.join(domains)})",
                          "source": "Social Media", "confidence": "High"})
    if (scraped.get("contact_data") or {}).get("emails") or (scraped.get("contact_data") or {}).get("phones"):
        strengths.append({"point": "Public contact channels (email/phone) listed for enquiries",
                          "source": "Homepage / Footer", "confidence": "High"})
    weaknesses = []
    if not scraped.get("pricing_text"):
        weaknesses.append({
            "point": "No pricing information was found on the pages crawled; this is a public-information gap, not proof of a business weakness.",
            "source": "Website scan", "confidence": "Medium", "basis": "evidence-limit",
        })
    if len(reviews) < 80:
        weaknesses.append({
            "point": "The sources checked did not provide enough employee-review text for a reliable culture assessment.",
            "source": "Public-source coverage", "confidence": "Low", "basis": "evidence-limit",
        })

    # An opportunity or threat needs company- and market-specific evidence.
    # The baseline path cannot establish those from an industry label alone.
    opportunities = []
    threats = []
    return {
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:5],
        "opportunities": opportunities[:5],
        "threats": threats[:5],
    }


def _extract_competitors(company_name: str, intel: dict, scraped: dict = None) -> list:
    """
    Domain-specific competitors from public search + Wikipedia + industry peers.
    Prefer names that appear next to this company; never invent cross-domain peers.
    """
    scraped = scraped or {}
    comps = []
    seen = set()

    def _add(name: str, desc: str, source: str, threat: str = "Medium", conf: str = "Medium"):
        name = re.sub(r"\s+", " ", (name or "")).strip(" ,.|")
        if not name or len(name) < 2 or len(name) > 60:
            return
        low = name.lower()
        brand = (company_name or "").lower()
        if low == brand or brand in low or low in brand:
            return
        if low in seen or "competitor" in low or "not publicly" in low:
            return
        if any(x in low for x in ("wikipedia", "linkedin", "crunchbase", "click here")):
            return
        seen.add(low)
        comps.append({
            "name": name,
            "description": (desc or "Same-industry peer")[:160],
            "strengths": "",
            "weaknesses": "",
            "threat_level": threat,
            "source": source,
            "confidence": conf,
        })

    # 1) Explicit competitor mentions in Wikipedia / digests
    blob = " ".join([
        scraped.get("wikipedia_summary") or "",
        scraped.get("wikipedia_text") or "",
        intel.get("competitors_direct") or "",
        intel.get("multi_source_digest") or "",
        intel.get("market_position") or "",
    ])
    for pat in (
        rf"(?i)(?:competitors?|rivals?|peers?|compete(?:s|d)? with|versus|vs\.?)\s+(?:include|includes|are|:)?\s*([^.|;]+)",
        rf"(?i){re.escape(company_name)}\s+(?:vs\.?|versus)\s+([A-Z][\w&.'\-\s]{{2,40}})",
    ):
        for m in re.finditer(pat, blob):
            chunk = m.group(1)
            for part in re.split(r",|;| and | & |/|\|", chunk):
                part = re.sub(r"(?i)^(such as|including|like|the)\s+", "", part.strip())
                part = re.sub(r"\s+\(.*?\)$", "", part).strip()
                if 2 < len(part) < 50 and part[0].isupper():
                    _add(part, "Mentioned as peer/competitor in public sources", "Wikipedia / public web", "High", "High")

    # 2) Web search for competitors (deep mode only — DDG is slow)
    if RESEARCH_DEEP:
        for q in [
            f'"{company_name}" competitors',
            f'"{company_name}" vs',
        ]:
            for r in _ddg_search(q, max_results=4):
                href = r.get("href") or ""
                title = r.get("title") or ""
                body = r.get("body") or ""
                if href:
                    intel.setdefault("_source_urls", []).append({
                        "title": title[:80], "url": href, "category": "Competitors",
                    })
                text = f"{title} {body}"
                for m in re.finditer(
                    rf"(?i){re.escape(company_name)}\s+(?:vs\.?|versus)\s+([A-Z][\w&.'\-](?:[\w&.'\- ]{{0,35}}[\w&.'\-])?)",
                    text,
                ):
                    _add(m.group(1), "Named in competitive comparison", urlparse(href).netloc or "Web search", "High", "Medium")
                for m in re.finditer(
                    r"(?i)(?:competitors?|rivals?)\s*(?:include|:)?\s*([A-Z][\w&.'\-]+(?:\s+[A-Z][\w&.'\-]+){0,3})",
                    text,
                ):
                    _add(m.group(1), "Named in competitor list", urlparse(href).netloc or "Web search", "Medium", "Medium")

    # Do not fill a competitor quota with generic industry peers. A company
    # can have fewer than three publicly evidenced direct competitors.
    return comps[:6]


def _clean_swot_points(items) -> list:
    fixed = []
    for it in items or []:
        if isinstance(it, str):
            pt, src, conf = it, "Analysis", "Medium"
        elif isinstance(it, dict):
            pt = it.get("point") or it.get("value") or ""
            src = it.get("source") or "Analysis"
            conf = it.get("confidence") or "Medium"
        else:
            continue
        if not pt or "not publicly" in str(pt).lower() or "not available" in str(pt).lower():
            continue
        if _is_illogical_text(str(pt)):
            continue
        if "not publicly" in str(src).lower():
            src = "Analysis"
        fixed.append({"point": str(pt)[:280], "source": str(src), "confidence": str(conf)})
    return fixed


def _offerings_from_scrape(scraped: dict) -> list:
    offerings = []
    seen = set()

    def _add(item: str, source: str, conf: str = "Medium"):
        item = re.sub(r"\s+", " ", (item or "")).strip(" .;,-")
        if not item or len(item) < 3 or len(item) > 70:
            return
        if _is_illogical_text(item):
            return
        key = item.lower()
        if key in seen:
            return
        seen.add(key)
        offerings.append({"item": item, "source": source, "confidence": conf})

    # Wikipedia / clean summary product hints first (high signal)
    for hint in _wiki_product_hints(
        (scraped.get("wikipedia_summary") or "") + " " + (scraped.get("wikipedia_text") or "")
    ):
        _add(hint, scraped.get("wikipedia_url") or "Wikipedia", "High")

    text = (scraped.get("products_text") or scraped.get("homepage_text") or "")
    skip = {
        "home", "about", "contact", "blog", "news", "careers", "login", "privacy",
        "sign in", "cookie", "menu", "search",
    }
    for link in scraped.get("nav_links") or []:
        low = link.strip().lower()
        if not low or low in skip or len(link) > 40:
            continue
        if any(w in low for w in (
            "service", "design", "engineer", "consult", "solution", "project",
            "product", "platform", "cloud", "software", "hardware",
        )):
            _add(link.strip(), "Website nav", "Medium")

    if len(offerings) < 3 and text:
        for part in re.split(r"[\n•\|]+", text)[:40]:
            part = part.strip()
            if 8 < len(part) < 60 and part[0].isupper() and not _is_illogical_text(part):
                _add(part, "Website", "Low")
            if len(offerings) >= 6:
                break

    # Meta description product-ish clauses
    desc = scraped.get("description") or ""
    if len(offerings) < 3 and desc and not _is_illogical_text(desc):
        for part in re.split(r",|;| and | \| ", desc):
            part = part.strip()
            if 4 < len(part) < 55:
                _add(part, "Website description", "Medium")
            if len(offerings) >= 6:
                break
    return offerings[:6]


def _field_confidence(field) -> str:
    if isinstance(field, dict):
        return str(field.get("confidence") or "").lower()
    return ""


def _is_illogical_text(val: str) -> bool:
    if not val:
        return True
    low = val.lower().strip()
    if len(low) < 12:
        return True
    markers = [
        "login to", "continue with google", "continue with microsoft",
        "forgot password", "cookie", "captcha", "sign in",
        "what's on your mind", "whats on your mind",
        "create images", "ai mode", "add images", "add files",
        "google offered in", "report inappropriate",
        "request has been blocked", "skip to main content",
        # Wikipedia / CMS chrome mistakenly used as market copy
        "jump to content", "main menu", "move to sidebar", "hide navigation",
        "random article", "contents current events", "about wikipedia",
        "edit links", "tools tools", "appearance", "toggle the table of contents",
        "from wikipedia, the free encyclopedia",
        # ChatGPT / AI chat chrome — never treat as company facts
        "chatgpt", "chat.openai", "sign up to chat", "log in to chatgpt",
        "what can i help with", "message chatgpt", "upgrade to plus",
    ]
    if any(m in low for m in markers):
        return True
    # scraped nav garbage
    if low.count("continue") >= 2 and "login" in low:
        return True
    # too many UI chrome tokens
    ui_hits = sum(1 for t in ("store", "images", "tools", "delete", "see more", "menu", "sidebar") if t in low)
    if ui_hits >= 3 and len(low) < 500:
        return True
    # Looks like a raw search-snippet dump rather than a sentence
    if low.startswith("[") and "wikipedia" in low and "jump to" in low:
        return True
    return False


def _clean_snippet(text: str, max_len: int = 280) -> str:
    """Strip search/wiki chrome; keep a readable sentence for UI fields."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if not t:
        return ""
    # Drop leading [domain] title crumbs + Wikipedia nav chrome first
    t = re.sub(r"^\[.*?\]\s*", "", t)
    t = re.sub(r"(?i)^.*?wikipedia\s*[-–|]\s*", "", t, count=1)
    t = re.sub(r"(?i)jump to content.*?(?:hide\s*)?", " ", t)
    t = re.sub(r"(?i)main menu.*?(?:navigation\s*)?", " ", t)
    t = re.sub(r"(?i)move to sidebar.*?hide", " ", t)
    t = re.sub(r"(?i)contents current events random article about wikipedia\s*", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -–|")
    if len(t) < 24 or _is_illogical_text(t):
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = " ".join(parts[:2]).strip()
    return out[:max_len]


def _score_to_int(v, default: int = 50) -> int:
    """Normalize LLM score labels (High/Medium/Low) or numbers to 0–100."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        # Models sometimes return 0.6 meaning 60%
        if 0 < float(v) <= 1:
            return max(0, min(100, int(round(float(v) * 100))))
        return max(0, min(100, int(round(float(v)))))
    s = str(v or "").strip().lower()
    mapping = {
        "very high": 90, "high": 80, "medium": 60, "med": 60,
        "low": 35, "very low": 20,
    }
    if s in mapping:
        return mapping[s]
    try:
        num = float(s)
        if 0 < num <= 1:
            return max(0, min(100, int(round(num * 100))))
        return max(0, min(100, int(round(num))))
    except Exception:
        return default


def _apply_llm_judge(
    report: dict,
    scraped: dict,
    company_name: str,
    url: str,
    intel: dict | None = None,
) -> dict:
    """Final confidence gate — LLM judge sanitizes the report before UI sees it."""
    from backend.services import llm_judge

    intel = intel or {}
    domain = urlparse(url).netloc.replace("www.", "")
    offerings = []
    for o in ((report.get("products_services") or {}).get("primary_offerings") or [])[:6]:
        if isinstance(o, dict):
            offerings.append(o.get("item") or o.get("value") or "")
        else:
            offerings.append(str(o))
    offerings_hint = ", ".join(x for x in offerings if x) or (scraped.get("description") or "")[:300]
    offerings_hint = "\n".join(
        part for part in (offerings_hint, scraped.get("products_text") or "") if part
    )[:1800]
    wd = scraped.get("_wikidata") or {}
    site_evidence = "\n".join(
        part for part in (
            scraped.get("title") or "",
            scraped.get("description") or "",
            scraped.get("about_text") or "",
            scraped.get("leadership_text") or "",
            scraped.get("homepage_text") or "",
        ) if part
    )[:2600]

    public_evidence = []
    allowed_evidence_urls = set()
    evidence_text_by_url = {}
    evidence_page_text_by_url = {}
    evidence_meta_by_url = {}
    if str(url).startswith(("http://", "https://")):
        site_retrieved = bool(scraped.get("_homepage_reachable") and not scraped.get("_scrape_blocked"))
        allowed_evidence_urls.add(str(url).strip())
        evidence_text_by_url[str(url).strip()] = site_evidence
        if site_retrieved:
            evidence_page_text_by_url[str(url).strip()] = site_evidence
        evidence_meta_by_url[str(url).strip()] = {
            "category": "Company Website",
            "title": company_name or domain,
            "retrieved": site_retrieved,
            "evidence_type": "page" if site_retrieved else "search_snippet",
        }
        public_evidence.append({
            "url": str(url).strip(),
            "title": company_name or domain,
            "category": "Company Website",
            "text": site_evidence[:2600],
            "retrieved": site_retrieved,
            "evidence_type": "page" if site_retrieved else "search_snippet",
        })
        canonical_site_url = _canonical_public_url(str(url))
        if canonical_site_url:
            allowed_evidence_urls.add(canonical_site_url)
            evidence_text_by_url[canonical_site_url] = site_evidence
            if site_retrieved:
                evidence_page_text_by_url[canonical_site_url] = site_evidence
            evidence_meta_by_url[canonical_site_url] = evidence_meta_by_url[str(url).strip()]
    def _evidence_category_rank(value: Any) -> int:
        category = str(value or "").lower()
        for rank, markers in enumerate((
            ("leadership",),
            ("competitor",),
            ("market trends", "trend"),
            ("products", "services"),
            ("market", "geography"),
            ("financial", "revenue"),
            ("news", "event"),
        )):
            if any(marker in category for marker in markers):
                return rank
        return 8

    # Leadership was already fetched as part of the website crawl. Keep it as a
    # separate, role-focused evidence row so a long homepage cannot truncate it
    # before the judge sees the names and titles.
    structured_site = scraped.get("_structured") or {}
    site_page_urls = scraped.get("_page_urls") or {}
    leadership_text = str(
        structured_site.get("leadership_text") or scraped.get("leadership_text") or ""
    ).strip()
    leadership_url = str(
        site_page_urls.get("leadership_text") or f"https://{domain}/"
    ).strip()
    if leadership_text and leadership_url.startswith(("http://", "https://")):
        leadership_excerpt = leadership_text[:4200]
        canonical_leadership_url = _canonical_public_url(leadership_url)
        allowed_evidence_urls.update((leadership_url, canonical_leadership_url))
        evidence_text_by_url[leadership_url] = leadership_excerpt
        evidence_page_text_by_url[leadership_url] = leadership_excerpt
        evidence_meta_by_url[leadership_url] = {
            "category": "Leadership",
            "title": "Company leadership page",
            "retrieved": True,
            "evidence_type": "page",
        }
        if canonical_leadership_url:
            evidence_text_by_url[canonical_leadership_url] = leadership_excerpt
            evidence_page_text_by_url[canonical_leadership_url] = leadership_excerpt
            evidence_meta_by_url[canonical_leadership_url] = evidence_meta_by_url[leadership_url]
        if not any(_canonical_public_url(str(row.get("url") or "")) == canonical_leadership_url for row in public_evidence):
            public_evidence.append({
                "url": leadership_url,
                "title": "Company leadership page",
                "category": "Leadership",
                "text": leadership_excerpt,
                "retrieved": True,
                "evidence_type": "page",
            })

    candidate_pages = [
        page for page in (intel.get("_scraped_pages") or [])
        if isinstance(page, dict)
    ]
    candidate_pages.sort(key=lambda page: (
        _evidence_category_rank(page.get("category")),
        0 if page.get("retrieved") is not False and page.get("text") else 1,
    ))
    for page in candidate_pages[:10]:
        page_url = str(page.get("url") or "").strip()
        if not page_url.startswith(("http://", "https://")):
            continue
        page_category = str(page.get("category") or "Public Web")
        is_leadership_page = "leadership" in page_category.lower()
        allowed_evidence_urls.add(page_url)
        page_text = str(page.get("text") or page.get("snippet") or "")[:
            2400 if is_leadership_page else 700
        ]
        validation_text = f"{page.get('title') or ''} {page_text}"[:
            4200 if is_leadership_page else 1100
        ]
        evidence_text_by_url[page_url] = validation_text
        if page.get("retrieved") is not False and page.get("text"):
            evidence_page_text_by_url[page_url] = validation_text
        evidence_meta_by_url[page_url] = {
            "category": page_category,
            "title": str(page.get("title") or "Public source"),
            "published_at": str(page.get("published_at") or ""),
            "retrieved": page.get("retrieved") is not False and bool(page.get("text")),
            "evidence_type": "page" if page.get("retrieved") is not False and page.get("text") else "search_snippet",
        }
        canonical_page_url = _canonical_public_url(page_url)
        if canonical_page_url:
            allowed_evidence_urls.add(canonical_page_url)
            evidence_text_by_url[canonical_page_url] = validation_text
            if page.get("retrieved") is not False and page.get("text"):
                evidence_page_text_by_url[canonical_page_url] = validation_text
            evidence_meta_by_url[canonical_page_url] = evidence_meta_by_url[page_url]
        public_evidence.append({
            "url": page_url,
            "title": page.get("title") or page.get("domain") or "Public source",
            "category": page_category,
            "text": page_text,
            "published_at": page.get("published_at") or "",
            "retrieved": page.get("retrieved") is not False and bool(page.get("text")),
            "evidence_type": "page" if page.get("retrieved") is not False and page.get("text") else "search_snippet",
            "search_result_excerpt": str(page.get("search_snippet") or "")[:1000],
        })
    evidence_counts = {}
    for item in public_evidence:
        rank = _evidence_category_rank(item.get("category"))
        evidence_counts[rank] = evidence_counts.get(rank, 0) + 1
    source_rows = sorted(
        (row for row in (intel.get("_source_urls") or []) if isinstance(row, dict)),
        key=lambda row: (
            _evidence_category_rank(row.get("category")),
            0 if row.get("retrieved") else 1,
        ),
    )
    for row in source_rows:
        source_url = str(row.get("url") or "").strip()
        if not source_url.startswith(("http://", "https://")):
            continue
        category = str(row.get("category") or "Public Web")
        snippet_text = f"{row.get('title') or ''} {row.get('snippet') or ''}"[:720]
        canonical_source_url = _canonical_public_url(source_url)
        if source_url in allowed_evidence_urls or canonical_source_url in allowed_evidence_urls:
            # The same URL can appear as both a fetched page and a search hit.
            # Preserve the richer category/date metadata and exact snippet.
            for evidence_url in (source_url, canonical_source_url):
                if not evidence_url:
                    continue
                meta = evidence_meta_by_url.setdefault(evidence_url, {})
                if _evidence_category_rank(category) < _evidence_category_rank(meta.get("category")):
                    meta["category"] = category
                if row.get("title") and not meta.get("title"):
                    meta["title"] = str(row.get("title"))
                if row.get("retrieved"):
                    meta["retrieved"] = True
                meta["evidence_type"] = "page" if meta.get("retrieved") else "search_snippet"
                if row.get("search_snippet"):
                    meta["search_snippet"] = str(row.get("search_snippet"))[:1000]
                if row.get("retrieved") and evidence_url not in evidence_page_text_by_url and row.get("snippet"):
                    evidence_page_text_by_url[evidence_url] = str(row.get("snippet"))[:4200]
                if row.get("published_at") and not meta.get("published_at"):
                    meta["published_at"] = str(row.get("published_at"))
                prior_text = evidence_text_by_url.get(evidence_url, "")
                if snippet_text and snippet_text not in prior_text:
                    evidence_text_by_url[evidence_url] = f"{prior_text} {snippet_text}"[:4200]
            existing_evidence = next(
                (item for item in public_evidence if item.get("url") == source_url),
                None,
            )
            if existing_evidence:
                if _evidence_category_rank(category) < _evidence_category_rank(existing_evidence.get("category")):
                    existing_evidence["category"] = category
                if row.get("published_at") and not existing_evidence.get("published_at"):
                    existing_evidence["published_at"] = row.get("published_at")
                if row.get("search_snippet"):
                    existing_evidence["search_result_excerpt"] = str(row.get("search_snippet"))[:1000]
                if snippet_text and snippet_text not in str(existing_evidence.get("text") or ""):
                    existing_evidence["text"] = f"{existing_evidence.get('text') or ''} {snippet_text}"[:2200]
            continue
        if len(public_evidence) >= 18:
            continue
        rank = _evidence_category_rank(category)
        category_caps = {0: 4, 1: 4, 2: 3, 3: 2, 4: 2, 5: 2, 6: 2, 8: 2}
        if evidence_counts.get(rank, 0) >= category_caps.get(rank, 2):
            continue
        allowed_evidence_urls.add(source_url)
        evidence_text_by_url[source_url] = snippet_text
        evidence_meta_by_url[source_url] = {
            "category": category,
            "title": str(row.get("title") or "Search result"),
            "published_at": str(row.get("published_at") or ""),
            "retrieved": bool(row.get("retrieved")),
            "evidence_type": "page" if row.get("retrieved") else "search_snippet",
            "search_snippet": str(row.get("search_snippet") or "")[:1000],
        }
        if canonical_source_url:
            allowed_evidence_urls.add(canonical_source_url)
            evidence_text_by_url[canonical_source_url] = snippet_text
            evidence_meta_by_url[canonical_source_url] = evidence_meta_by_url[source_url]
        public_evidence.append({
            "url": source_url,
            "title": row.get("title") or "Search result",
            "category": category,
            "text": snippet_text,
            "published_at": row.get("published_at") or "",
            "retrieved": bool(row.get("retrieved")),
            "evidence_type": "page" if row.get("retrieved") else "search_snippet",
            "search_result_excerpt": str(row.get("search_snippet") or "")[:1000],
        })
        evidence_counts[rank] = evidence_counts.get(rank, 0) + 1

    verdict = llm_judge.judge_research_report(
        website_url=url,
        domain=domain,
        brand_name=company_name,
        site_excerpt=site_evidence,
        offerings_hint=offerings_hint,
        report=report,
        wikidata_hint=wd,
        public_evidence=public_evidence,
        timeout=REPORT_JUDGE_TIMEOUT,
    )
    judge_available = not bool(verdict.get("_error"))
    print(
        "[Judge] quality=%s drop_registry=%s leadership_keep=%s reasons=%s"
        % (
            verdict.get("quality_score"),
            verdict.get("drop_registry"),
            verdict.get("leadership_keep"),
            str(verdict.get("rejected_reasons") or [])[:240].encode("ascii", "replace").decode("ascii"),
        )
    )

    display = (verdict.get("display_name") or company_name or "").strip()
    # Hard identity gate: never accept an unrelated display_name (e.g. Sevan for microsoft.com)
    display = _anchor_company_name(display, domain, scraped)
    if display:
        cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
        cp["name"] = display
        report["company_profile"] = cp
        company_name = display

    # Industry / market position from judge when present
    if isinstance(verdict.get("industry"), dict) and verdict["industry"].get("value"):
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        ma["industry"] = verdict["industry"]
        report["market_analysis"] = ma
    mp = verdict.get("market_position")
    if isinstance(mp, dict) and mp.get("value") and not _is_illogical_text(str(mp.get("value"))):
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        ma["market_position"] = mp
        report["market_analysis"] = ma
    else:
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        cur = ma.get("market_position")
        cur_val = cur.get("value") if isinstance(cur, dict) else cur
        if _is_illogical_text(str(cur_val or "")):
            ma["market_position"] = _field("Not publicly available", "Judge", "Low")
            report["market_analysis"] = ma

    trend = verdict.get("market_trends") if isinstance(verdict.get("market_trends"), dict) else {}
    trend_value = re.sub(r"\s+", " ", str(trend.get("value") or "")).strip()
    trend_url = str(trend.get("source_url") or "").strip()
    trend_canonical_url = _canonical_public_url(trend_url)
    allowed_canonical_urls = {
        _canonical_public_url(value) for value in allowed_evidence_urls
        if _canonical_public_url(value)
    }
    trend_meta = evidence_meta_by_url.get(trend_url) or evidence_meta_by_url.get(trend_canonical_url) or {}
    trend_published_at = str(trend_meta.get("published_at") or "").strip()
    trend_date = _parse_public_news_date(trend_published_at)
    trend_year_only = None
    if not trend_date:
        year_match = re.search(
            r"\b(20(?:2[3-9]|3\d))\b",
            " ".join((str(trend_meta.get("title") or ""), str(trend_meta.get("search_snippet") or ""), trend_published_at)),
        )
        if year_match:
            trend_year_only = int(year_match.group(1))
            trend_date = datetime(trend_year_only, 1, 1, tzinfo=timezone.utc)
    if trend_date and trend_date.tzinfo is None:
        trend_date = trend_date.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    trend_is_recent = bool(
        trend_date
        and (
            trend_year_only is not None
            and now_utc.year - 3 <= trend_year_only <= now_utc.year
            or trend_year_only is None
            and trend_date <= now_utc
            and trend_date.timestamp() >= now_utc.timestamp() - 3 * 365 * 86400
        )
    )
    trend_is_snippet = trend_meta.get("evidence_type") == "search_snippet"
    trend_has_usable_evidence = bool(
        trend_meta.get("retrieved")
        or (trend_is_snippet and (trend_meta.get("published_at") or trend_year_only is not None))
    )
    if (
        trend_value
        and len(trend_value) <= 320
        and (trend_url in allowed_evidence_urls or trend_canonical_url in allowed_canonical_urls)
        and "market trends" in str(trend_meta.get("category") or "").lower()
        and trend_has_usable_evidence
        and trend_is_recent
    ):
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        trend_source = urlparse(trend_url).netloc.replace("www.", "") or "Public source"
        ma["market_trends"] = _field(
            trend_value, trend_source, trend.get("confidence") or "Medium"
        )
        ma["market_trends"].update({
            "verification_status": "search-snippet-supported" if trend_is_snippet else "evidence-verified",
            "evidence_type": "search result excerpt" if trend_is_snippet else "fetched page",
            "source_urls": [trend_url],
            "published_at": (
                f"{trend_year_only} (year only)" if trend_year_only is not None
                else trend_published_at
            ),
            "date_precision": "year" if trend_year_only is not None else "day",
        })
        report["market_analysis"] = ma
    else:
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        ma.pop("market_trends", None)
        report["market_analysis"] = ma

    # A fetched competitor source may confirm a direct competitor. A search
    # snippet can only be shown as a sourced lead until its page is checked.
    judged_comps = []
    competitor_candidates = []
    brand_l = company_name.lower()
    competitor_rows = list(verdict.get("competitors") or []) + list(verdict.get("competitor_candidates") or [])
    seen_competitor_names = set()
    for c in competitor_rows:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if name.lower() == brand_l or brand_l in name.lower() or name.lower() in brand_l:
            continue
        normalized_competitor_name = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower())).strip()
        if not normalized_competitor_name or normalized_competitor_name in seen_competitor_names:
            continue
        conf = str(c.get("confidence") or "Medium")
        evidence_url = str(c.get("evidence_url") or "").strip()
        evidence_canonical_url = _canonical_public_url(evidence_url)
        if (
            conf.lower() == "low"
            or (evidence_url not in allowed_evidence_urls and evidence_canonical_url not in allowed_canonical_urls)
        ):
            continue
        source_meta = evidence_meta_by_url.get(evidence_url) or evidence_meta_by_url.get(evidence_canonical_url) or {}
        page_source_text = evidence_page_text_by_url.get(evidence_url) or evidence_page_text_by_url.get(evidence_canonical_url) or ""
        search_source_text = str(source_meta.get("search_snippet") or "")
        normalized_name = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower())).strip()
        normalized_page_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", page_source_text.lower()))
        normalized_search_text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", search_source_text.lower()))
        name_in_fetched_page = bool(normalized_name and normalized_name in normalized_page_text)
        name_in_search_excerpt = bool(normalized_name and normalized_name in normalized_search_text)
        is_page_verified = bool(source_meta.get("retrieved") and name_in_fetched_page)
        is_search_snippet = not is_page_verified
        if is_search_snippet and (
            "competitor" not in str(source_meta.get("category") or "").lower()
            or not name_in_search_excerpt
        ):
            continue
        official_domain = str(c.get("official_domain") or "").strip().lower().rstrip("/")
        official_domain = official_domain.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        known_hosts = {
            urlparse(source_url).netloc.lower().removeprefix("www.")
            for source_url in allowed_evidence_urls
            if urlparse(source_url).netloc
        }
        if official_domain and not any(
            official_domain == host or host.endswith("." + official_domain) or official_domain.endswith("." + host)
            for host in known_hosts
        ):
            official_domain = ""
        candidate = {
            "name": name,
            "description": c.get("description") or "",
            "strengths": c.get("strengths") or "",
            "weaknesses": c.get("weaknesses") or "",
            "official_domain": official_domain,
            "market_location": c.get("market_location") or "",
            "overlap_reason": c.get("overlap_reason") or "",
            "evidence_url": evidence_url,
            "source_urls": [evidence_url],
            "threat_level": c.get("threat_level") or "Medium",
            "source": c.get("source") or "Judge-validated",
            "confidence": conf if conf in ("High", "Medium") else "Medium",
            "verification_status": "evidence-verified" if is_page_verified else "search-snippet-supported",
        }
        if is_search_snippet:
            competitor_candidates.append(candidate)
        else:
            judged_comps.append(candidate)
        seen_competitor_names.add(normalized_competitor_name)
    # Never pad with generic industry peers. Search snippets stay visibly marked
    # as leads; only fetched evidence appears among confirmed competitors.
    report["competitors"] = judged_comps[:6] if judge_available else []

    # Some search systems provide an explicit competitor list in their snippet,
    # while the LLM judge correctly declines to call it page-verified. Preserve
    # those named leads with the original result URL instead of losing them.
    if judge_available:
        candidates_by_name = {
            re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(row.get("name") or "").lower())).strip(): row
            for row in competitor_candidates
            if isinstance(row, dict) and row.get("name")
        }
        competitor_evidence_rows = list(intel.get("_profile_evidence") or [])
        if not competitor_evidence_rows:
            competitor_evidence_rows = list(intel.get("_source_urls") or [])
        extraction_patterns = (
            r"\bcompetitors?\s+(?:include|are|such as|comprise)\s+(.{2,320})",
            r"\bcompetitors?\b[^:\n.]{0,100}:\s*(.{2,320})",
            r"\bpeers?\s+in\s+[^.\n]{1,80}\binclude\s+(.{2,320})",
            r"\b(?:listed\s+)?peers?\s+(?:include|are|such as)\s+(.{2,320})",
            r"\bpeers?\b[^:\n.]{0,80}:\s*(.{2,320})",
        )
        explicit_snippet_names = set()
        generic_competitor_text = re.compile(
            r"(?i)\b(?:ranked here|market capitali[sz]ation|market cap|peer comparison|"
            r"performance snapshot|listed peers|frequently asked questions|competitor analysis|"
            r"alternatives|competitors|top competitors|main competitors)\b"
        )
        for row in competitor_evidence_rows:
            if not isinstance(row, dict) or "competitor" not in str(row.get("source") or row.get("category") or "").lower():
                continue
            source_url = str(row.get("url") or "").strip()
            if not source_url.startswith(("http://", "https://")):
                continue
            search_excerpt = str(
                row.get("search_snippet")
                or row.get("snippet")
                or row.get("text")
                or ""
            )[:1400]
            if not _blob_matches_brand(f"{row.get('title') or ''} {search_excerpt}", company_name, domain):
                continue
            source_names = []
            for pattern in extraction_patterns:
                match = re.search(pattern, search_excerpt, re.I)
                if match:
                    names_text = re.split(
                        r"(?i)\s+(?:see\b|compare\b|get\b|discover\b|visit\b|read\b|search query:)",
                        match.group(1),
                        maxsplit=1,
                    )[0]
                    names_text = re.sub(
                        r"(?i)\.\s+(?:the full|the list|the company|these|this|according|for more|a comprehensive)\b.*$",
                        "",
                        names_text,
                    ).strip(" .…")
                    source_names = [part for part in re.split(r"\s*,\s*", names_text) if part.strip()]
                    if source_names:
                        final_part = source_names[-1]
                        if re.search(r"(?i)\s+and\s+", final_part):
                            first, last = re.split(r"(?i)\s+and\s+", final_part, maxsplit=1)
                            source_names[-1:] = [first, last]
                        elif len(source_names) > 1 and re.search(r"\s+&\s+", final_part):
                            first, last = re.split(r"\s+&\s+", final_part, maxsplit=1)
                            source_names[-1:] = [first, last]
                    if search_excerpt.rstrip().endswith(("…", "...")) and source_names:
                        # The last token of a truncated snippet may be only a
                        # partial company name; don't promote that fragment.
                        source_names = source_names[:-1]
                    break
            source_host = urlparse(source_url).netloc.replace("www.", "")
            for raw_name in source_names:
                name = re.sub(r"\s+", " ", str(raw_name)).strip(" \t\r\n,;:-|\"'")
                name = re.sub(r"(?i)^and\s+", "", name).strip()
                name = re.sub(r"(?i)\s+(?:see|compare|read|learn|visit)\b.*$", "", name).strip()
                normalized_name = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower())).strip()
                normalized_brand = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", company_name.lower())).strip()
                if (
                    len(name) < 2 or len(name) > 64 or not normalized_name
                    or normalized_name in normalized_brand
                    or normalized_brand in normalized_name
                    or generic_competitor_text.search(name)
                ):
                    continue
                explicit_snippet_names.add(normalized_name)
                candidate = candidates_by_name.get(normalized_name)
                if candidate:
                    source_urls = list(candidate.get("source_urls") or [])
                    if source_url not in source_urls:
                        source_urls.append(source_url)
                    candidate["source_urls"] = source_urls[:4]
                    continue
                candidate = {
                    "name": name,
                    "description": f"Named in a public competitor search result from {source_host}.",
                    "official_domain": "",
                    "market_location": "",
                    "overlap_reason": "The search excerpt lists this company among the target's competitors; the linked page was not fetched for this claim.",
                    "evidence_url": source_url,
                    "source_urls": [source_url],
                    "threat_level": "Medium",
                    "source": source_host or "Public search result",
                    "confidence": "Medium",
                    "verification_status": "search-snippet-supported",
                }
                candidates_by_name[normalized_name] = candidate
                competitor_candidates.append(candidate)
        # Keep model-judged search leads first; the same candidate may have
        # appeared in the explicit snippet extraction above.
        competitor_candidates = [
            row for key, row in candidates_by_name.items()
            if key in explicit_snippet_names
        ]
    report["competitor_candidates"] = competitor_candidates[:4] if judge_available else []

    # SWOT and risk output is fact-gated: every retained point must refer to an
    # exact company-site or retrieved public-evidence URL. Analysis stays
    # labeled as analysis and is never promoted into a sourced company fact.
    def _validated_analysis_items(section: str, key: str, text_key: str) -> list[dict]:
        source = verdict.get(section) if isinstance(verdict.get(section), dict) else {}
        output = []
        seen = set()
        for row in (source.get(key) or [])[:8]:
            if not isinstance(row, dict):
                continue
            point = re.sub(r"\s+", " ", str(row.get(text_key) or "")).strip()
            source_url = str(row.get("source_url") or "").strip()
            if not point or len(point) > 280 or source_url not in allowed_evidence_urls:
                continue
            norm = point.lower()
            if norm in seen:
                continue
            seen.add(norm)
            basis = str(row.get("basis") or "fact").strip().lower()
            if basis not in {"fact", "analysis"}:
                basis = "analysis"
            confidence = str(row.get("confidence") or "Medium").strip().title()
            if confidence not in {"High", "Medium", "Low"}:
                confidence = "Medium"
            host = urlparse(source_url).netloc.replace("www.", "")
            output.append({
                text_key: point,
                "source": host or "Public source",
                "source_url": source_url,
                "confidence": confidence,
                "basis": basis,
                "verification_status": "evidence-verified",
            })
            if len(output) >= 4:
                break
        return output

    if judge_available:
        report["swot_analysis"] = {
            quadrant: _validated_analysis_items("swot_analysis", quadrant, "point")
            for quadrant in ("strengths", "weaknesses", "opportunities", "threats")
        }
        judged_risk = {
            category: _validated_analysis_items("risk_assessment", category, "risk")
            for category in (
                "regulatory_risks", "competitive_risks", "operational_risks", "reputational_risks",
            )
        }
        requested_level = str(
            (verdict.get("risk_assessment") or {}).get("overall_risk_level") or "Undetermined"
        ).strip().title()
        has_supported_risk = any(judged_risk.values())
        judged_risk["overall_risk_level"] = (
            requested_level if has_supported_risk and requested_level in {"Low", "Medium", "High"}
            else "Undetermined"
        )
        report["risk_assessment"] = judged_risk
    else:
        report["swot_analysis"] = {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}
        report["risk_assessment"] = {
            "overall_risk_level": "Undetermined",
            "regulatory_risks": [], "competitive_risks": [],
            "operational_risks": [], "reputational_risks": [],
        }

    # Geographic reach — must be a display string
    ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    geo_v = verdict.get("geographic_reach")
    if isinstance(geo_v, dict) and auth.flatten_display(geo_v.get("value")):
        ma["geographic_reach"] = _field(
            geo_v.get("value"), geo_v.get("source") or "Judge", geo_v.get("confidence") or "Medium"
        )
    else:
        hq = _field_text((report.get("company_profile") or {}).get("headquarters"))
        desc = _field_text((report.get("company_profile") or {}).get("description"))
        ma["geographic_reach"] = auth.normalize_geographic_reach(ma.get("geographic_reach"), hq, desc)
    report["market_analysis"] = ma

    # Revenue and funding — require a domain-matched structured fact or a value
    # that occurs in the supplied source text. A judge assertion alone is not
    # financial evidence.
    fin = report.get("financial_data") if isinstance(report.get("financial_data"), dict) else {}
    rev_v = verdict.get("revenue_estimate")
    wd_rev = auth.sanitize_revenue((scraped.get("_wikidata") or {}).get("revenue"))

    def _validated_financial_value(row, scaled_amount: bool = False):
        if not isinstance(row, dict):
            return "", "", ""
        value = re.sub(r"\s+", " ", str(row.get("value") or "")).strip()
        source_url = str(row.get("source_url") or "").strip()
        if not value or value.lower() in {"not publicly available", "unknown", "n/a", "undisclosed"}:
            return "", "", ""
        if source_url not in allowed_evidence_urls:
            return "", "", ""
        source_text = evidence_text_by_url.get(source_url, "").lower()
        if value.lower() not in source_text:
            canonical = _canonical_public_url(source_url)
            source_text = evidence_text_by_url.get(canonical, "").lower()
        if value.lower() not in source_text:
            return "", "", ""
        if scaled_amount:
            value = auth.sanitize_revenue(value)
            if not value:
                return "", "", ""
        return value, source_url, str(row.get("confidence") or "Medium")

    judged_rev, judged_rev_url, judged_rev_conf = _validated_financial_value(rev_v, scaled_amount=True)
    best_rev = wd_rev or judged_rev or ""
    if best_rev:
        src = "Wikidata" if wd_rev else (
            urlparse(judged_rev_url).netloc.replace("www.", "") or "Public source"
        )
        conf = "High" if wd_rev else judged_rev_conf
        fin["revenue_estimate"] = _field(best_rev, src, conf or "Medium")
        revenue_source_url = (scraped.get("_wikidata") or {}).get("source_url") if wd_rev else judged_rev_url
        fin["revenue_estimate"].update({
            "verification_status": "evidence-verified",
            "source_urls": [revenue_source_url] if revenue_source_url else [],
        })
    else:
        fin["revenue_estimate"] = _field("Not publicly available", "Public filings", "Low")

    financial_intelligence = verdict.get("financial_intelligence") if isinstance(verdict.get("financial_intelligence"), dict) else {}
    for key in ("funding_status", "total_funding", "funding_stage", "profitability_status"):
        value, source_url, confidence = _validated_financial_value(
            financial_intelligence.get(key),
            scaled_amount=(key == "total_funding"),
        )
        if value:
            fin[key] = _field(value, urlparse(source_url).netloc.replace("www.", "") or "Public source", confidence)
            fin[key].update({"verification_status": "evidence-verified", "source_urls": [source_url]})
        else:
            fin[key] = _field("Not publicly available", "Public sources", "Low")
    report["financial_data"] = fin
    cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    if best_rev:
        cp["annual_revenue"] = _field(best_rev, fin["revenue_estimate"].get("source") or "Public filings",
                                      fin["revenue_estimate"].get("confidence") or "Medium")
        cp["annual_revenue"].update({
            key: fin["revenue_estimate"][key]
            for key in ("verification_status", "source_urls")
            if key in fin["revenue_estimate"]
        })
    else:
        cp["annual_revenue"] = _field("Not publicly available", "Public filings", "Low")

    # Leadership / registry gates — no CIN/MCA
    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": "Public web research — current executives from Wikidata / company site / Wikipedia. Historical founders are labelled and are not the point of contact.",
        "entity_scope": "none",
        "directors": [],
        "cin": "",
    }
    drop_names = {(n or "").strip().lower() for n in (verdict.get("drop_people") or []) if n}
    judged_keep = {}
    for row in verdict.get("leadership") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        if row.get("keep") is False:
            drop_names.add((row.get("name") or "").lower())
            continue
        judged_keep[(row.get("name") or "").lower()] = row

    def _supported_leadership_source(row: dict) -> tuple[str, dict] | None:
        source_url = str(row.get("source_url") or "").strip()
        canonical = _canonical_public_url(source_url)
        meta = evidence_meta_by_url.get(source_url) or evidence_meta_by_url.get(canonical) or {}
        excerpt = str(evidence_text_by_url.get(source_url) or evidence_text_by_url.get(canonical) or "")
        name = re.sub(r"\s+", " ", str(row.get("name") or "")).strip().lower()
        role = re.sub(r"\s+", " ", str(row.get("role") or "")).strip().lower()
        text = re.sub(r"\s+", " ", excerpt).lower()
        if (
            not source_url
            or (source_url not in allowed_evidence_urls and canonical not in allowed_evidence_urls)
            or not name
            or name not in text
            or not role
        ):
            return None
        role_aliases = (
            ("chief executive officer", "ceo"),
            ("chief technology officer", "cto"),
            ("chief financial officer", "cfo"),
            ("chief operating officer", "coo"),
            ("managing director", "md"),
            ("president",),
            ("chairperson", "chairman", "chair"),
            ("founder", "co-founder", "cofounder"),
            ("director",),
        )
        aliases = next((group for group in role_aliases if any(token in role for token in group)), (role,))
        if not any(alias in text for alias in aliases):
            return None
        return source_url, meta

    leaders = []
    if judge_available:
        for ldr in report.get("leadership_team") or []:
            if not isinstance(ldr, dict) or not ldr.get("name"):
                continue
            key = ldr["name"].strip().lower()
            # A leader must be explicitly kept by the judge. Omission is not
            # treated as approval for a CEO/founder/chairman claim.
            if key in drop_names or key not in judged_keep:
                continue
            src = str(ldr.get("source") or "").lower()
            if "zauba" in src or "mca" in src or "cin" in src or ldr.get("din"):
                continue
            if str(ldr.get("confidence") or "").lower() == "low":
                continue
            j = judged_keep[key]
            supported = _supported_leadership_source({**j, "name": ldr.get("name")})
            if not supported:
                continue
            source_url, source_meta = supported
            ldr = dict(ldr)
            if j.get("role"):
                ldr["role"] = j["role"]
            if j.get("status") in ("current", "historical"):
                ldr["status"] = j["status"]
                ldr["is_current"] = j["status"] == "current"
            host = urlparse(source_url).netloc.lower().removeprefix("www.")
            ldr.update({
                "source": host or "Public source",
                "source_urls": [source_url],
                "verification_status": (
                    "evidence-verified" if source_meta.get("retrieved")
                    else "search-snippet-supported"
                ),
                "provenance": "public-evidence" if source_meta.get("retrieved") else "search-snippet",
            })
            leaders.append(ldr)

    # Add source-backed leaders found by the judge even when the initial
    # company-site scrape did not include them.
    existing_keys = {(l.get("name") or "").lower() for l in leaders}
    if judge_available:
        for row in verdict.get("leadership") or []:
            if not isinstance(row, dict) or row.get("keep") is False:
                continue
            name = (row.get("name") or "").strip()
            key = name.lower()
            if not name or key in existing_keys:
                continue
            if row.get("status") not in {"current", "historical"}:
                continue
            supported = _supported_leadership_source(row)
            if not supported:
                continue
            source_url, source_meta = supported
            host = urlparse(source_url).netloc.lower().removeprefix("www.")
            leaders.append({
                "name": name,
                "role": row.get("role") or "Leadership",
                "source": host or "Public source",
                "source_urls": [source_url],
                "confidence": "High" if source_meta.get("retrieved") else "Medium",
                "verification_status": (
                    "evidence-verified" if source_meta.get("retrieved")
                    else "search-snippet-supported"
                ),
                "background": "Named with this role in the linked public source.",
                "status": row.get("status"),
                "is_current": row.get("status") == "current",
                "provenance": "public-evidence" if source_meta.get("retrieved") else "search-snippet",
            })
            existing_keys.add(key)

    report["leadership_team"] = auth.rank_leadership(leaders)
    for k in ("cin", "mca_status", "authorized_capital", "paid_up_capital", "zaubacorp_url"):
        cp.pop(k, None)
    report["company_profile"] = cp

    q = int(verdict.get("quality_score") or 40)
    report["_judge"] = {
        "quality_score": q,
        "rejected_reasons": verdict.get("rejected_reasons") or [],
        "poc_name": verdict.get("poc_name") or "",
        "poc_title": verdict.get("poc_title") or "",
        "provider": "azure/llm-judge",
        "status": "verified" if judge_available else "unavailable",
        "summary": verdict.get("summary") or "",
    }
    if not judge_available:
        # Do not quietly present sensitive people/competitor facts when the
        # required verification call could not run.
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        ma["market_position"] = _field("Not publicly available", "Judge unavailable", "Low")
        report["market_analysis"] = ma
    return report


def _field_text(v) -> str:
    return auth.flatten_display(v)


def _normalize_report(report: dict, scraped: dict, company_name: str, url: str, intel: dict) -> dict:
    """
    Fix Groq schema drift so the Streamlit tabs always get usable structures.
    Citations already work; this repairs Overview / SWOT / etc.
    """
    domain = urlparse(url).netloc.replace("www.", "")
    if not isinstance(report, dict):
        report = {}

    # ── company_profile ──────────────────────────────────────────────
    cp = report.get("company_profile")
    if not isinstance(cp, dict):
        cp = {}
    # Sometimes entire profile is {"value": "..."}
    if set(cp.keys()) <= {"value", "source", "confidence"} and isinstance(cp.get("value"), str):
        cp = {"description": cp.get("value"), "name": company_name}
    if not cp.get("name") or str(cp.get("name")).strip() in ("", "None", "Company"):
        cp["name"] = company_name
    cp.setdefault("website", url)
    # Prefer clean description — never keep homepage UI chrome / emoji junk
    raw_desc = cp.get("description")
    desc_v = raw_desc.get("value") if isinstance(raw_desc, dict) else raw_desc
    scrape_desc = scraped.get("description") or ""
    if not desc_v or _is_illogical_text(str(desc_v)):
        if scrape_desc and not _is_illogical_text(scrape_desc):
            cp["description"] = scrape_desc
        else:
            about = (scraped.get("about_text") or "")[:280]
            if about and not _is_illogical_text(about):
                cp["description"] = about
            else:
                cp["description"] = (
                    f"{company_name} is a public company website at {urlparse(url).netloc}. "
                    "Detailed corporate copy was limited in the scrape."
                )
    # Alias employees → employee_count for frontend KPIs
    if cp.get("employees") and not cp.get("employee_count"):
        cp["employee_count"] = cp["employees"] if isinstance(cp.get("employees"), dict) else _field(
            cp.get("employees"), "Public web", "Medium"
        )
    for key in ("founded", "headquarters", "industry", "employee_count", "annual_revenue",
                "cin", "mca_status", "authorized_capital", "paid_up_capital", "roc"):
        if key in cp and not isinstance(cp.get(key), dict):
            cp[key] = _field(cp.get(key), "Website", "Medium")
    wd = intel.get("_wikidata") or scraped.get("_wikidata") or {}
    if wd.get("matched"):
        if wd.get("headquarters") and (not _field_text(cp.get("headquarters")) or "not publicly" in _field_text(cp.get("headquarters")).lower()):
            cp["headquarters"] = _field(wd["headquarters"], "Wikidata", "High")
        if wd.get("founded_year") and (not _field_text(cp.get("founded")) or "not publicly" in _field_text(cp.get("founded")).lower()):
            cp["founded"] = _field(wd["founded_year"], "Wikidata", "High")
        if wd.get("employees") and (not _field_text(cp.get("employee_count")) or "not publicly" in _field_text(cp.get("employee_count")).lower()):
            cp["employee_count"] = _field(wd["employees"], "Wikidata", "High")
        if wd.get("revenue"):
            cp["annual_revenue"] = _field(wd["revenue"], "Wikidata", "High")
        elif not auth.sanitize_revenue(cp.get("annual_revenue")):
            cp["annual_revenue"] = _field("Not publicly available", "Public filings", "Low")
    report["company_profile"] = cp
    # Fill from Zauba if missing
    zauba = scraped.get("zaubacorp_structured") or {}
    if zauba:
        mapping = {
            "founded": "Date of Incorporation",
            "headquarters": "Registered Address",
            "cin": "CIN",
            "mca_status": "Status",
            "authorized_capital": "Authorized Capital",
            "paid_up_capital": "Paid Up Capital",
            "roc": "RoC",
        }
        for dst, src in mapping.items():
            cur = cp.get(dst)
            cur_val = cur.get("value") if isinstance(cur, dict) else cur
            if (not cur_val or "not publicly" in str(cur_val).lower()) and zauba.get(src):
                cp[dst] = _field(zauba[src], "ZaubaCorp", "High")
    if scraped.get("zaubacorp_url"):
        cp["zaubacorp_url"] = scraped["zaubacorp_url"]
    report["company_profile"] = cp

    # ── products_services ────────────────────────────────────────────
    prod = report.get("products_services")
    if isinstance(prod, dict) and isinstance(prod.get("value"), list):
        report["products_services"] = {
            "primary_offerings": [
                {"item": x, "source": prod.get("source") or "Website", "confidence": prod.get("confidence") or "Medium"}
                if not isinstance(x, dict) else x
                for x in prod["value"]
            ],
            "pricing_model": _field("Not publicly available", "Website", "Low"),
            "target_customers": _field("Not publicly available", "Website", "Low"),
        }
    elif not isinstance(prod, dict) or not prod.get("primary_offerings"):
        offs = _offerings_from_scrape(scraped)
        report["products_services"] = {
            "primary_offerings": offs,
            "pricing_model": _field("Quote-based / not listed publicly", "Website", "Medium"),
            "target_customers": _field("Not publicly available", "Website", "Low"),
        }
    else:
        fixed = []
        for o in prod.get("primary_offerings") or []:
            if isinstance(o, str):
                fixed.append({"item": o, "source": "Website", "confidence": "Medium"})
            elif isinstance(o, dict):
                if "item" not in o and o.get("value"):
                    o = {"item": o["value"], "source": o.get("source", "Website"), "confidence": o.get("confidence", "Medium")}
                fixed.append(o)
        prod["primary_offerings"] = fixed
        report["products_services"] = prod

    # Drop junk offerings; backfill from scrape/wiki if thin
    prod = report.get("products_services") if isinstance(report.get("products_services"), dict) else {}
    clean_offs = []
    for o in prod.get("primary_offerings") or []:
        item = o.get("item") if isinstance(o, dict) else str(o)
        if item and not _is_illogical_text(str(item)):
            clean_offs.append(o if isinstance(o, dict) else {"item": item, "source": "Website", "confidence": "Medium"})
    if len(clean_offs) < 2:
        for o in _offerings_from_scrape(scraped):
            if o["item"].lower() not in {str(x.get("item") if isinstance(x, dict) else x).lower() for x in clean_offs}:
                clean_offs.append(o)
            if len(clean_offs) >= 6:
                break
    prod["primary_offerings"] = clean_offs[:6]
    report["products_services"] = prod

    # ── market_analysis ──────────────────────────────────────────────
    wiki_sum = _clean_snippet(scraped.get("wikipedia_summary") or "", 320) or ""
    site_desc = _clean_snippet(scraped.get("description") or "", 280) or ""
    clean_market = wiki_sum or site_desc

    mkt = report.get("market_analysis")
    if _looks_empty(mkt) or (isinstance(mkt, dict) and "market_position" not in mkt and "industry" not in mkt):
        industry_hint = scraped.get("wikipedia_description") or (site_desc.split(".")[0] if site_desc else "")
        report["market_analysis"] = {
            "industry": _field(
                industry_hint or "Not publicly available",
                "Wikipedia" if scraped.get("wikipedia_description") else "Website",
                "High" if industry_hint else "Low",
            ),
            "market_position": _field(
                clean_market or "Not publicly available",
                "Wikipedia" if wiki_sum else "Website",
                "High" if wiki_sum else ("Medium" if site_desc else "Low"),
            ),
            "geographic_reach": auth.normalize_geographic_reach(
                None,
                "",
                wiki_sum + " " + site_desc,
            ),
            "key_differentiators": [],
        }
    elif isinstance(mkt, dict):
        for k in ("industry", "market_position", "market_trends", "geographic_reach", "market_size_tam", "growth_rate"):
            if k in mkt and not isinstance(mkt[k], dict):
                mkt[k] = _field(mkt[k])
            elif k == "geographic_reach":
                mkt[k] = auth.normalize_geographic_reach(
                    mkt.get(k),
                    _field_text((report.get("company_profile") or {}).get("headquarters")),
                    wiki_sum + " " + site_desc,
                )
        # Replace junk market_position with clean Wikipedia/site prose
        mp = mkt.get("market_position")
        mp_val = mp.get("value") if isinstance(mp, dict) else mp
        if _is_illogical_text(str(mp_val or "")) or not str(mp_val or "").strip():
            mkt["market_position"] = _field(
                clean_market or "Not publicly available",
                "Wikipedia" if wiki_sum else "Website",
                "High" if wiki_sum else "Low",
            )
        report["market_analysis"] = mkt

    # Prefer Wikipedia summary for empty/junk company description
    cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    desc = cp.get("description")
    desc_v = desc.get("value") if isinstance(desc, dict) else desc
    if (not desc_v or _is_illogical_text(str(desc_v))) and (wiki_sum or site_desc):
        cp["description"] = _field(
            wiki_sum or site_desc,
            "Wikipedia" if wiki_sum else "Website",
            "High" if wiki_sum else "Medium",
        )
        report["company_profile"] = cp
    # Industry from Wikipedia short description when missing
    ind = cp.get("industry")
    ind_v = ind.get("value") if isinstance(ind, dict) else ind
    if (not ind_v or "not publicly" in str(ind_v).lower()) and scraped.get("wikipedia_description"):
        cp["industry"] = _field(scraped["wikipedia_description"], "Wikipedia", "High")
        report["company_profile"] = cp

    # ── swot_analysis ────────────────────────────────────────────────
    swot = report.get("swot_analysis")
    if _looks_empty(swot) or not isinstance(swot, dict) or "strengths" not in swot:
        report["swot_analysis"] = _heuristic_swot(scraped, intel, company_name)
    else:
        for key in ("strengths", "weaknesses", "opportunities", "threats"):
            swot[key] = _clean_swot_points(swot.get(key) or [])
        # Do not pad an evidence-thin quadrant with generic industry advice.
        report["swot_analysis"] = swot

    # ── competitors / news lists ─────────────────────────────────────
    comps = report.get("competitors")
    if not isinstance(comps, list):
        comps = []
    # Drop empty / N/A / junk competitors
    clean_comps = []
    for c in comps:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        low = name.lower()
        if not name or "not publicly" in low or len(name) < 3 or len(name) > 50:
            continue
        if re.match(r"^competitor\s*\d+$", low):
            continue
        if any(x in low for x in ("gmail", "iniciar", "ordenador", "click here", "not available")):
            continue
        if "." in name and not re.search(r"(ltd|inc|llc)\.?$", low, re.I):
            continue
        clean_comps.append(c)
    comps = clean_comps
    if len(comps) < 3:
        extra = _extract_competitors(company_name, intel, scraped)
        have = {c["name"].lower() for c in comps}
        for c in extra:
            if c["name"].lower() not in have:
                comps.append(c)
                have.add(c["name"].lower())
            if len(comps) >= 6:
                break
    report["competitors"] = comps

    if not isinstance(report.get("recent_news"), list):
        rn = report.get("recent_news")
        if isinstance(rn, dict) and isinstance(rn.get("value"), list):
            report["recent_news"] = rn["value"]
        else:
            report["recent_news"] = []
    # Enrich news from scraped pages / search snippets if empty
    if len(report.get("recent_news") or []) < 2:
        news_items = []
        seen_titles = set()

        def _push_news(title, source, url="", summary="", conf="Medium", date=""):
            title = _clean_snippet(title or "", 120) or (title or "")[:120]
            if not title or len(title) < 12:
                return
            key = title.lower()[:80]
            if key in seen_titles or _is_illogical_text(title):
                return
            if not url or auth.is_junk_citation(url):
                return
            # Search results often mix similarly named publishers and companies.
            # Keep only items whose title/snippet identifies this company.
            if not _blob_matches_brand(f"{title} {summary or ''}", company_name, domain):
                return
            seen_titles.add(key)
            news_items.append({
                "title": title,
                "date": str(date or "").strip(),
                "source": source,
                "source_url": url,
                "summary": _clean_snippet(summary, 220) or summary[:220],
                "sentiment": "Neutral",
                "confidence": conf,
            })

        for page in intel.get("_scraped_pages") or []:
            if "news" in (page.get("category") or "").lower() or any(
                x in (page.get("domain") or "") for x in ("economictimes", "reuters", "bloomberg", "business-standard", "moneycontrol")
            ):
                _push_news(
                    page.get("title") or page.get("domain"),
                    page.get("domain"),
                    page.get("url") or "",
                    (page.get("text") or "")[:220],
                    "Medium",
                    page.get("published_at") or page.get("date") or "",
                )
        # Dedicated news search only in deep mode
        if RESEARCH_DEEP and len(news_items) < 2:
            for r in _ddg_search(f'"{company_name}" news', max_results=6):
                href = r.get("href") or ""
                host = urlparse(href).netloc.replace("www.", "")
                _push_news(
                    r.get("title") or "", host, href, r.get("body") or "", "Medium",
                    r.get("date") or r.get("published") or r.get("published_at") or "",
                )
                intel.setdefault("_source_urls", []).append({
                    "title": (r.get("title") or "")[:80], "url": href, "category": "News",
                })
        if not news_items:
            for s in (intel.get("_source_urls") or [])[:5]:
                if "news" in (s.get("category") or "").lower() or "News" in (s.get("category") or ""):
                    _push_news(
                        s.get("title") or s.get("url"),
                        urlparse(s.get("url", "")).netloc.replace("www.", ""),
                        s.get("url") or "",
                        "Discovered via public web search — open source for full article.",
                        "Low",
                    )
        report["recent_news"] = (report.get("recent_news") or []) + news_items
        report["recent_news"] = report["recent_news"][:4]

    # ── content_strategy ─────────────────────────────────────────────
    cs = report.get("content_strategy")
    if _looks_empty(cs) or not isinstance(cs, dict) or not cs.get("content_pillars"):
        name = company_name
        label = _industry_context(scraped, intel)["label"]
        pillars = {
            "engineering": ["Projects & Case Studies", "Engineering Expertise", "Safety & Quality", "Industry Insights"],
            "software": ["Product Updates", "Customer Stories", "Engineering Blog", "Thought Leadership"],
            "healthcare": ["Patient Stories", "Clinical Expertise", "Wellness Education", "Hospital Updates"],
            "ecommerce": ["Product Drops", "Customer Reviews", "Lifestyle Content", "Offers & Bundles"],
            "education": ["Student Outcomes", "Faculty Expertise", "Career Guidance", "Course Explainers"],
            "manufacturing": ["Factory Capability", "Quality Certifications", "Client Projects", "Sustainability"],
            "logistics": ["Network Reach", "On-time Stories", "Ops Excellence", "Customer Support"],
            "professional_services": ["Case Studies", "Expert Opinions", "Team Culture", "Industry Trends"],
            "music_entertainment": ["Catalog Highlights", "Artist Stories", "Licensing Use-Cases", "Fan Engagement"],
            "general": ["Case Studies", "Expertise", "Company Culture", "Industry Insights"],
        }
        ideas = {
            "engineering": [f"Before/after design stories from {name}", "Site visit reels", "Client testimonial carousels"],
            "software": [f"Feature demos for {name}", "Customer ROI breakdowns", "Founder/engineering AMAs"],
            "healthcare": ["Doctor explainer shorts", "Patient journey carousels", "Facility tour reels"],
            "ecommerce": ["Unboxing / styling content", "UGC customer looks", "Behind-the-scenes ops"],
            "education": ["Alumni success stories", "Day-in-the-life reels", "Exam tip carousels"],
            "music_entertainment": [f"Catalog deep-dives for {name}", "Artist collaboration stories", "Licensing explainers"],
            "general": [f"Customer success stories from {name}", "Team culture reels", "Myth-busting industry posts"],
        }
        report["content_strategy"] = {
            "brand_voice": f"Professional, clear voice for {name}",
            "content_pillars": pillars.get(label, pillars["general"]),
            "viral_content_ideas": ideas.get(label, ideas["general"]),
            "top_hashtags": [f"#{name.replace(' ', '')[:20]}", f"#{str(label).replace('_', '')}", "#Business", "#Growth"],
            "competitor_content_gap": "Publish more public case studies and proof-of-work content",
        }

    # ── tech_stack ───────────────────────────────────────────────────
    tech = report.get("tech_stack")
    if not isinstance(tech, dict) or _looks_empty(tech):
        hints = scraped.get("tech_hints") or []
        report["tech_stack"] = {
            "note": "Website technology only — detected from homepage HTML/scripts",
            "website_cms": _field(hints[0] if hints else "Not publicly available", "Homepage scan", "Medium"),
            "frontend_framework": _field(
                next((h for h in hints if h.lower() in ("react", "vue", "angular", "bootstrap", "jquery")),
                     "Not publicly available"),
                "Homepage scan", "Medium"),
            "analytics_tools": [{"item": h, "source": "Homepage scan", "confidence": "Medium"}
                                for h in hints if "analytics" in h.lower() or "gtag" in h.lower()],
        }

    # ── intelligence_score (always numeric for frontend "/100" display) ──
    sc = report.get("intelligence_score") if isinstance(report.get("intelligence_score"), dict) else {}
    n_contacts = len((scraped.get("contact_data") or {}).get("emails") or [])
    n_pages = len(intel.get("_scraped_pages") or [])
    n_comps = len(report.get("competitors") or [])
    swot = report.get("swot_analysis") or {}
    n_swot = sum(len(swot.get(k) or []) for k in ("strengths", "weaknesses", "opportunities", "threats"))
    completeness = min(88, 35 + n_pages * 2 + n_contacts * 3 + n_comps * 2 + min(n_swot, 12))
    computed_overall = min(80, completeness)
    summary = sc.get("summary") or ""
    if not summary or _is_illogical_text(summary):
        summary = f"Multi-source report for {company_name} — scores are authenticity-capped, not completeness-capped."
    report["intelligence_score"] = {
        "overall": _score_to_int(sc.get("overall"), computed_overall),
        "data_completeness": _score_to_int(sc.get("data_completeness"), completeness),
        "source_reliability": _score_to_int(sc.get("source_reliability"), 55),
        "verified_fields_count": int(sc.get("verified_fields_count") or (n_contacts + n_pages + n_comps)),
        "estimated_fields_count": int(sc.get("estimated_fields_count") or max(0, n_swot // 2)),
        "unverified_fields_count": int(sc.get("unverified_fields_count") or 0),
        "summary": summary,
    }

    # ── risk / financial ─────────────────────────────────────────────
    def _default_risks(label: str) -> dict:
        # Industry-wide possibilities are not evidence that this company has
        # an actual exposure. Leave the assessment undetermined until sourced.
        return {
            "overall_risk_level": "Undetermined",
            "competitive_risks": [],
            "regulatory_risks": [],
            "operational_risks": [],
            "reputational_risks": [],
        }

    industry_label = _industry_context(scraped, intel)["label"]
    if _looks_empty(report.get("risk_assessment")):
        report["risk_assessment"] = _default_risks(industry_label)
    else:
        risk = report.get("risk_assessment") or {}
        rl = risk.get("overall_risk_level")
        if isinstance(rl, dict):
            risk["overall_risk_level"] = rl.get("value") or "Undetermined"
        elif not rl:
            risk["overall_risk_level"] = "Undetermined"
        defaults = _default_risks(industry_label)
        for cat in ("regulatory_risks", "competitive_risks", "operational_risks", "reputational_risks"):
            items = risk.get(cat) or []
            fixed = []
            for it in items if isinstance(items, list) else [items]:
                if isinstance(it, str):
                    if "not publicly" in it.lower() or "not enough" in it.lower():
                        continue
                    fixed.append({"risk": it, "source": "Analysis", "confidence": "Medium"})
                elif isinstance(it, dict):
                    rsk = it.get("risk") or it.get("value") or ""
                    if rsk and "not enough public data" not in str(rsk).lower() \
                            and "not publicly" not in str(rsk).lower():
                        fixed.append({
                            "risk": rsk,
                            "source": it.get("source") or "Analysis",
                            "confidence": it.get("confidence") or "Medium",
                            "basis": it.get("basis") or "analysis",
                            "source_url": it.get("source_url") or it.get("evidence_url") or "",
                        })
            if not fixed:
                fixed = defaults.get(cat) or []
            risk[cat] = fixed
        report["risk_assessment"] = risk

    fin = report.get("financial_data")
    zauba = scraped.get("zaubacorp_structured") or {}
    rev_match = re.search(
        r"(?:₹|Rs\.?|INR|USD|\$)\s?[\d,.]+\s?(?:cr|crore|million|bn|billion)?",
        (intel.get("revenue") or "") + " " + (intel.get("multi_source_digest") or ""),
        re.I,
    )
    if _looks_empty(fin):
        raw_rev = rev_match.group(0) if rev_match else ""
        clean_rev = auth.sanitize_revenue(raw_rev) or auth.sanitize_revenue(
            (intel.get("_wikidata") or scraped.get("_wikidata") or {}).get("revenue")
        )
        report["financial_data"] = {
            "authorized_capital": _field("Not publicly available", "Public web", "Low"),
            "paid_up_capital": _field("Not publicly available", "Public web", "Low"),
            "revenue_estimate": _field(
                clean_rev or "Not publicly available",
                "Wikidata" if (intel.get("_wikidata") or {}).get("revenue") and clean_rev else (
                    "Public filings" if clean_rev else "Public web"
                ),
                "High" if (intel.get("_wikidata") or {}).get("revenue") and clean_rev else (
                    "Medium" if clean_rev else "Low"
                ),
            ),
            "funding_stage": _field("Not publicly available", "Public web", "Low"),
            "profitability_status": _field("Unknown — not disclosed publicly", "Public web", "Low"),
        }
    else:
        for k, v in list((fin or {}).items()):
            if k in ("key_investors",):
                continue
            if not isinstance(v, dict):
                fin[k] = _field(v, "Public web", "Medium")
        for dst, src in (("authorized_capital", "Authorized Capital"),
                         ("paid_up_capital", "Paid Up Capital")):
            cur = fin.get(dst)
            cur_v = cur.get("value") if isinstance(cur, dict) else cur
            if (not cur_v or "not publicly" in str(cur_v).lower()) and zauba.get(src):
                fin[dst] = _field(zauba[src], "ZaubaCorp", "High")
        rev = fin.get("revenue_estimate")
        rev_v = rev.get("value") if isinstance(rev, dict) else rev
        if (not rev_v or "not publicly" in str(rev_v).lower()) and rev_match:
            fin["revenue_estimate"] = _field(rev_match.group(0), "Public web scrape", "Medium")
        elif not rev_v or "not publicly" in str(rev_v).lower():
            fin["revenue_estimate"] = _field(
                "Not disclosed in public scrapes",
                "Public web", "Low")
        cleaned = auth.sanitize_revenue(fin.get("revenue_estimate"))
        wd_rev = auth.sanitize_revenue((intel.get("_wikidata") or scraped.get("_wikidata") or {}).get("revenue"))
        if wd_rev:
            fin["revenue_estimate"] = _field(wd_rev, "Wikidata", "High")
        elif cleaned:
            fin["revenue_estimate"] = _field(cleaned, "Public filings", "Medium")
        else:
            fin["revenue_estimate"] = _field("Not publicly available", "Public filings", "Low")
        report["financial_data"] = fin

    if _looks_empty(report.get("employee_insights")):
        # try to pull headcount from homepage stats
        headcount = "Not publicly available"
        m = re.search(r"(\d+\+?)\s*(?:team members?|employees?|engineers?|people)",
                      (scraped.get("homepage_text") or "") + " " + (scraped.get("description") or ""), re.I)
        if m:
            headcount = m.group(0)
        report["employee_insights"] = {
            "total_employees": _field(headcount, "Homepage" if m else "Public web", "High" if m else "Low"),
            "glassdoor_rating": _field("Not publicly available", "Glassdoor scrape", "Low"),
            "culture_summary": _field(
                (intel.get("glassdoor") or "")[:220] or "Limited public culture reviews found",
                "Public web scrape", "Low"),
            "hiring_trend": _field("Not publicly available", "Public web", "Low"),
            "remote_policy": _field("Not publicly available", "Public web", "Low"),
        }
    else:
        emp = report.get("employee_insights") or {}
        for k, v in list(emp.items()):
            if k in ("top_perks", "pain_points", "top_hiring_roles"):
                continue
            if not isinstance(v, dict) and not isinstance(v, list):
                emp[k] = _field(v)
        # fill headcount from homepage if empty
        te = emp.get("total_employees")
        te_v = te.get("value") if isinstance(te, dict) else te
        if not te_v or "not publicly" in str(te_v).lower():
            m = re.search(r"(\d+\+?)\s*(?:team members?|employees?|engineers?|people)",
                          (scraped.get("homepage_text") or "") + " " + (scraped.get("description") or ""), re.I)
            if m:
                emp["total_employees"] = _field(m.group(0), "Homepage", "High")
        report["employee_insights"] = emp

    return report


def _job_board_slugs(company_name: str, domain: str) -> list[str]:
    stem = _domain_stem(domain)
    raw = re.sub(r"[^a-z0-9]+", "-", (company_name or "").lower()).strip("-")
    raw = re.sub(
        r"-(inc|ltd|llc|limited|corp|corporation|pvt|private|company|co)$", "", raw
    ).strip("-")
    compact = raw.replace("-", "")
    out = []
    for s in (stem, raw, compact):
        if s and len(s) >= 2 and s not in out:
            out.append(s)
    return out


def _canonical_hiring_urls(company_name: str, domain: str, scraped: dict | None = None) -> list[dict]:
    """Return only employer pages that were actually discovered on the site."""
    careers = ((scraped or {}).get("_page_urls") or {}).get("careers_text") or ""
    rows = []
    if careers:
        rows.append((f"Careers at {company_name}", careers, "Official Careers"))
    out, seen = [], set()
    for role, url, platform in rows:
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "role": role,
            "count": 1,
            "platform": platform,
            "source_url": url,
            "source_title": f"{platform} — {company_name}",
            "snippet": f"Public hiring page for {company_name}",
        })
    return out


def _llm_hiring_fill(company_name: str, domain: str) -> list:
    """Public job-board URLs + role families, then filtered. Never cited as ChatGPT."""
    prompt = f"""List CURRENT public hiring pages for {company_name} (website {domain}).
Include official careers, LinkedIn company jobs, Naukri, Indeed, Glassdoor when they exist.

Return ONLY JSON:
{{
  "roles": [
    {{"role":"Job title or 'Careers at {company_name}'","source_url":"https://...","platform":"Official Careers|LinkedIn|Naukri|Indeed|Glassdoor"}}
  ]
}}
Rules:
- URLs must be this employer's own jobs page, not a keyword search for a product.
- Prefer LinkedIn /company/.../jobs, Naukri brand-jobs, Indeed /cmp/, jobs.{domain}, /careers.
- Never mention ChatGPT, OpenAI, or any AI model.
"""
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return valid JSON only. Public hiring pages of this employer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1, max_tokens=700, json_mode=True, timeout=HIRING_LLM_TIMEOUT,
            reasoning_effort="low",
        )
        data = _parse_llm_json(raw)
    except Exception as e:
        print(f"[Research] Hiring LLM fill failed: {e}")
        return []
    rows = []
    for row in data.get("roles") or []:
        if not isinstance(row, dict):
            continue
        href = str(row.get("source_url") or "").strip()
        role = re.sub(r"\s+", " ", str(row.get("role") or "")).strip()
        if not href.startswith("http") or not role:
            continue
        rows.append({
            "role": role[:80],
            "count": 1,
            "platform": row.get("platform") or "Hiring",
            "source_url": href,
            "source_title": role,
            "snippet": f"Public hiring for {company_name}",
        })
    return rows[:8]


def _judge_hiring_rows(company_name: str, domain: str, rows: list) -> list:
    """Validate hiring rows without erasing them when the judge is unavailable."""
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    if not rows:
        return []
    try:
        from backend.services import llm_judge
        verdict = llm_judge.judge_hiring_signals(
            company_name=company_name, domain=domain, signals=rows,
            timeout=HIRING_JUDGE_TIMEOUT,
        )
        if verdict.get("_error"):
            print("[Research] Hiring judge unavailable; keeping source-filtered signals")
            return rows

        def _hire_url_key(value: str) -> str:
            parsed = urlparse(value or "")
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/").lower()

        keep_urls = {_hire_url_key(u) for u in (verdict.get("keep_urls") or [])}
        return [
            row for row in rows
            if _hire_url_key(row.get("source_url") or "") in keep_urls
        ]
    except Exception as e:
        print(f"[Research] Hiring judge unavailable; keeping source-filtered signals: {e}")
        return rows


def _fetch_hiring_signals(company_name: str, domain: str, careers_text: str = "",
                          scraped: dict | None = None) -> list:
    """
    Official careers + LinkedIn + Naukri + Indeed + ATS.
    Keyword product searches are dropped; an LLM-as-judge checks leftover rows.
    """
    signals = []
    seen_urls = set()

    def _add(role: str, url: str, platform: str, title: str = "", snippet: str = ""):
        role = re.sub(r"\s+", " ", role or "").strip(" -|,")
        if not role or len(role) < 4 or len(role) > 90:
            return
        if not url or not str(url).startswith("http"):
            return
        key = url.split("?")[0].rstrip("/").lower()
        if key in seen_urls:
            return
        seen_urls.add(key)
        signals.append({
            "role": role.title() if role.islower() else role,
            "count": 1,
            "platform": platform,
            "source_url": url,
            "source_title": title or f"{platform} — {role}",
            "snippet": (snippet or "")[:200],
        })

    for row in _canonical_hiring_urls(company_name, domain, scraped):
        _add(row["role"], row["source_url"], row["platform"], row.get("source_title"), row.get("snippet"))

    careers_url = ((scraped or {}).get("_page_urls") or {}).get("careers_text") or f"https://{domain}/careers"
    if careers_text:
        for line in re.split(r"[\n•|]", careers_text):
            line = line.strip()
            if len(line) < 8 or len(line) > 100:
                continue
            if re.search(r"(engineer|developer|manager|designer|architect|analyst|consultant|lead|head of|scientist|specialist)", line, re.I):
                _add(line, careers_url, "Official Careers", line, careers_text[:200])

    queries = [
        (f'site:{domain} (careers OR jobs) "{company_name}"', "Official Careers"),
        (f'site:linkedin.com/company {company_name} jobs', "LinkedIn"),
        (f'site:naukri.com {company_name} jobs', "Naukri"),
        (f'site:indeed.com/cmp {company_name} jobs', "Indeed"),
        (f'site:glassdoor.com {company_name} jobs', "Glassdoor"),
        (f'site:boards.greenhouse.io {company_name}', "Company ATS"),
        (f'site:jobs.lever.co {company_name}', "Company ATS"),
        (f'site:myworkdayjobs.com {company_name}', "Company ATS"),
    ]
    if RESEARCH_SKIP_HIRING_SEARCH:
        print("[Research] Hiring web-search: official + LinkedIn + Naukri + Indeed (fast)")
        queries = queries[:4]

    if queries:
        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
            futs = {pool.submit(_ddg_search, q, 3): plat for q, plat in queries}
            for fut, platform in futs.items():
                try:
                    results = fut.result()
                except Exception:
                    results = []
                for r in results or []:
                    href = r.get("href", "")
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if not href.startswith("http"):
                        continue
                    role = title
                    for pat in [r"^(.+?)\s+at\s+", r"^(.+?)\s*[-–|]\s*"]:
                        m = re.search(pat, title, re.I)
                        if m:
                            cand = m.group(1).strip()
                            if 4 <= len(cand) <= 80:
                                role = cand
                            break
                    _add(role, href, platform, title, body)

    kept = auth.filter_hiring_signals(signals, company_name, domain)
    if len(kept) < 2:
        print("[Research] Hiring search thin — LLM public job-board fill + judge")
        extra = _llm_hiring_fill(company_name, domain)
        kept = auth.filter_hiring_signals(list(kept) + extra, company_name, domain) or kept
        if extra and not kept:
            kept = auth.filter_hiring_signals(extra, company_name, domain) or extra[:4]

    # In fast mode the source/domain filter is sufficient for the interactive
    # result.  Deep mode adds the employer judge, but a temporary model failure
    # must not hide real official/company job pages.
    if not RESEARCH_SKIP_JUDGE:
        kept = _judge_hiring_rows(company_name, domain, kept)

    print("[Research] Hiring kept " + str(len(kept)) + " pages: "
          + ", ".join(sorted({h.get("platform") or "?" for h in kept})))
    return kept[:8]


def _ai_conclusion_from_hiring(company_name: str, hiring: list, report: dict) -> dict:
    """One-sentence conclusion from VERIFIED employer openings only."""
    base = auth.hiring_conclusion(company_name, hiring)
    if not hiring:
        return base
    try:
        co = report.get("company_profile") or {}
        prompt = f"""Write one sentence about what {company_name} appears to be investing in, based ONLY on these verified official job listings.
If the listings are too generic, say they show active hiring without naming a specific initiative.
Do not invent job counts. Do not treat product-keyword searches as company jobs.

INDUSTRY: {co.get('industry', '')}
VERIFIED OPENINGS:
{json.dumps([{"role": h.get("role"), "platform": h.get("platform")} for h in hiring[:8]], indent=2)}

Return ONLY JSON: {{"ai_conclusion": "one sentence", "signals_used": ["role", ...]}}"""
        raw = llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
            json_mode=True,
        )
        data = json.loads(raw)
        if data.get("ai_conclusion"):
            return {
                "ai_conclusion": data["ai_conclusion"],
                "signals_used": data.get("signals_used") or base.get("signals_used") or [],
            }
    except Exception:
        pass
    return base


def _parse_public_news_date(value: Any) -> datetime | None:
    """Parse common publisher/search dates without guessing a missing year."""
    text = str(value or "").strip()
    if not text or text.lower() in {"date not verified", "unknown", "recent"}:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        pass
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y",
        "%d %b %Y", "%d %B %Y", "%Y-%m",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _search_result_date(value: Any) -> str:
    """Extract an explicitly written calendar date from a search snippet."""
    text = str(value or "")
    patterns = (
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        candidate = re.sub(r"(?i)(\d)(st|nd|rd|th)\b", r"\1", match.group(0))
        parsed = _parse_public_news_date(candidate)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    return ""


def _news_date_from_html(html: str, prefer_event_date: bool = False) -> str:
    """Read an explicitly published date from article metadata, not the search snippet."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""

    candidates, event_dates = [], []
    date_keys = {
        "article:published_time", "og:published_time", "datepublished",
        "publishdate", "pubdate", "parsely-pub-date", "date", "startdate", "event:start_time",
    }
    for node in soup.find_all("meta"):
        key = str(node.get("property") or node.get("name") or node.get("itemprop") or "").lower()
        if key in date_keys:
            destination = event_dates if key in {"startdate", "event:start_time"} else candidates
            destination.append(node.get("content") or node.get("value") or "")
    for node in soup.find_all("time"):
        value = node.get("datetime") or node.get_text(" ", strip=True)
        destination = event_dates if "startdate" in str(node.get("itemprop") or "").lower() else candidates
        destination.append(value)

    def collect_json_dates(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in {"datepublished", "datecreated", "startdate"} and isinstance(child, str):
                    destination = event_dates if str(key).lower() == "startdate" else candidates
                    destination.append(child)
                else:
                    collect_json_dates(child)
        elif isinstance(value, list):
            for child in value:
                collect_json_dates(child)

    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            collect_json_dates(json.loads(script.string or script.get_text()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    ordered_candidates = event_dates + candidates if prefer_event_date else candidates + event_dates
    for value in ordered_candidates:
        parsed = _parse_public_news_date(value)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    return ""


def _collect_company_news_events(company_name: str, domain: str) -> list[dict]:
    """Bounded public search for dated news/events; only fetched pages become evidence."""
    queries = (
        ("News", f'"{company_name}" company news announcement press release'),
        ("Event", f'"{company_name}" conference event webinar'),
    )
    candidates = []
    seen_urls = set()

    def search_for_kind(kind: str, query: str) -> list:
        return _ddg_news_search(query, 3) if kind == "News" else _ddg_search(query, 3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        search_futures = [pool.submit(search_for_kind, kind, query) for kind, query in queries]
        for (kind, _), future in zip(queries, search_futures):
            try:
                results = future.result(timeout=7)
            except Exception as exc:  # search is best-effort; the main report must continue
                print(f"[Research] {kind} lookup failed: {exc}")
                continue
            for result in results or []:
                if not isinstance(result, dict):
                    continue
                href = str(result.get("url") or result.get("href") or result.get("link") or "").strip()
                parsed = urlparse(href)
                host = (parsed.hostname or "").lower().removeprefix("www.")
                if (
                    parsed.scheme not in {"http", "https"}
                    or not host
                    or parsed.username
                    or parsed.password
                    or host in {"localhost", "127.0.0.1", "::1"}
                    or host.endswith((".local", ".internal"))
                    or auth.is_junk_citation(href)
                ):
                    continue
                canonical = _canonical_public_url(href)
                if not canonical or canonical in seen_urls:
                    continue
                title = str(result.get("title") or "").strip()
                snippet = str(result.get("body") or result.get("snippet") or "").strip()
                if not _blob_matches_brand(f"{title} {snippet}", company_name, domain):
                    continue
                seen_urls.add(canonical)
                candidates.append({
                    "kind": kind,
                    "title": title[:180],
                    "url": href,
                    "domain": host,
                    "snippet": snippet[:500],
                })
                if len(candidates) >= 6:
                    break
            if len(candidates) >= 6:
                break

    def fetch_public_page(url: str) -> dict:
        """Fetch a small public HTML page while rejecting private-network targets."""
        current = url
        for _ in range(4):
            parsed = urlparse(current)
            host = (parsed.hostname or "").lower()
            if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
                return {}
            if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
                return {}
            try:
                address = ipaddress.ip_address(host)
                addresses = [address]
            except ValueError:
                try:
                    addresses = [
                        ipaddress.ip_address(row[4][0])
                        for row in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
                    ]
                except (OSError, ValueError):
                    return {}
            if not addresses or any(not address.is_global for address in addresses):
                return {}
            try:
                with requests.get(
                    current, headers=HEADERS, timeout=4, allow_redirects=False, stream=True
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location") or ""
                        if not location:
                            return {}
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        return {}
                    content_type = str(response.headers.get("Content-Type") or "").lower()
                    if content_type and not any(x in content_type for x in ("text/html", "application/xhtml")):
                        return {}
                    chunks, total = [], 0
                    for chunk in response.iter_content(chunk_size=16384):
                        if not chunk:
                            continue
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= 1_500_000:
                            break
                    encoding = response.encoding or "utf-8"
                    html = b"".join(chunks)[:1_500_000].decode(encoding, errors="replace")
            except Exception:
                return {}
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                    tag.decompose()
                lines = re.sub(r"[ \t\xa0]+", " ", soup.get_text(separator="\n", strip=True))
                lines = re.sub(r"\n\s*\n+", "\n", lines).strip()
                text = re.sub(r"\s+", " ", lines)[:5000]
            except Exception:
                return {}
            return {"status": 200, "final_url": current, "text": text, "html": html}
        return {}

    def fetch_candidate(candidate: dict) -> dict | None:
        fetched = fetch_public_page(candidate["url"])
        text = str(fetched.get("text") or "")
        if fetched.get("status") != 200 or len(text) < 100:
            return None
        if _is_blocked_page_text(str(fetched.get("title") or ""), text) or _is_illogical_text(text[:800]):
            return None
        title = candidate.get("title") or str(fetched.get("title") or "").strip()
        if not _blob_matches_brand(f"{title} {text[:2500]}", company_name, domain):
            return None
        final_url = str(fetched.get("final_url") or candidate["url"])
        host = urlparse(final_url).netloc.lower().removeprefix("www.")
        if not host or auth.is_junk_citation(final_url):
            return None
        published_at = _news_date_from_html(
            fetched.get("html") or "", prefer_event_date=candidate.get("kind") == "Event"
        )
        if not published_at:
            return None
        kind = "event" if candidate.get("kind") == "Event" and re.search(
            r"\b(webinar|conference|summit|expo|trade show|forum|meetup|event)\b",
            f"{title} {text[:1800]}",
            re.I,
        ) else "news"
        return {
            "title": title[:180],
            "url": final_url,
            "domain": host,
            "category": "Events" if kind == "event" else "News",
            "kind": kind,
            "text": text[:5000],
            "published_at": published_at,
            "date_verified": True,
            "emails": [],
            "phones": [],
            "retrieved": True,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = [page for page in pool.map(fetch_candidate, candidates[:4]) if page]
    print(f"[Research] Verified {len(pages)} dated public news/event pages")
    return pages


def _canonical_public_url(value: str) -> str:
    try:
        parsed = urlparse(str(value or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        host = parsed.netloc.lower().removeprefix("www.")
        path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/")
        return f"{host}{path}"
    except Exception:
        return ""


def _merge_retrieved_news(report: dict, intel: dict) -> None:
    """Put fetched/date-verified pages first; the final sanitizer still checks content."""
    fetched = []
    for page in (intel or {}).get("_scraped_pages") or []:
        if not isinstance(page, dict) or not page.get("date_verified"):
            continue
        published_at = str(page.get("published_at") or "").strip()
        if not _parse_public_news_date(published_at):
            continue
        fetched.append({
            "title": page.get("title") or "Company update",
            "date": published_at,
            "source": page.get("domain") or "Public source",
            "source_url": page.get("url") or "",
            "summary": page.get("text") or "",
            "kind": page.get("kind") or "news",
            "confidence": "High",
        })
    existing = report.get("recent_news") or []
    if isinstance(existing, dict):
        existing = existing.get("value") if isinstance(existing.get("value"), list) else []
    candidates = fetched + [item for item in existing if isinstance(item, dict)]
    unique_news, seen_news = [], set()
    for item in candidates:
        key = (
            str(item.get("title") or "").strip().lower(),
            _canonical_public_url(str(item.get("source_url") or item.get("url") or "")),
        )
        if key in seen_news:
            continue
        seen_news.add(key)
        unique_news.append(item)
    report["recent_news"] = unique_news[:8]


def _sanitize_recent_news(report: dict, company_name: str, domain: str, intel: dict) -> list[dict]:
    """Keep only company news supported by text from a page the app retrieved."""
    page_rows = list((intel or {}).get("_scraped_pages") or [])
    allowed_urls = {
        _canonical_public_url(str(row.get("url") or ""))
        for row in page_rows
        if isinstance(row, dict) and row.get("retrieved") is not False and row.get("text")
    }
    page_text = {
        _canonical_public_url(str(row.get("url") or "")): str(row.get("text") or "")[:5000]
        for row in page_rows
        if isinstance(row, dict) and row.get("url") and row.get("retrieved") is not False and row.get("text")
    }
    page_by_url = {
        _canonical_public_url(str(row.get("url") or "")): row
        for row in page_rows
        if isinstance(row, dict) and row.get("url") and row.get("retrieved") is not False and row.get("text")
    }
    rows = []
    seen = set()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for item in (report.get("recent_news") or []):
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("source_url") or item.get("url") or "").strip()
        canonical = _canonical_public_url(source_url)
        if not canonical or canonical not in allowed_urls or auth.is_junk_citation(source_url):
            continue
        source_page = page_by_url.get(canonical) or {}
        source_text = page_text.get(canonical, "")
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        summary = re.sub(r"\s+", " ", str(item.get("summary") or item.get("description") or "")).strip()
        evidence_blob = " ".join((title, source_text))
        if not title or not _blob_matches_brand(evidence_blob, company_name, domain):
            continue
        normalized_title = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        normalized_source = re.sub(r"[^a-z0-9]+", " ", source_text.lower())
        title_terms = {word for word in normalized_title.split() if len(word) >= 4}
        if not normalized_title or (
            normalized_title not in normalized_source
            and (len(title_terms) < 3 or len(title_terms & set(normalized_source.split())) / len(title_terms) < 0.7)
        ):
            continue
        title_offset = source_text.lower().find(title.lower())
        if title_offset < 0:
            matching_offsets = [source_text.lower().find(term) for term in title_terms if source_text.lower().find(term) >= 0]
            title_offset = min(matching_offsets) if matching_offsets else 0
        source_excerpt = source_text[title_offset:title_offset + 900]
        date_text = str(
            item.get("date") or item.get("published_at") or item.get("published")
            or source_page.get("published_at") or ""
        ).strip()
        parsed_date = _parse_public_news_date(date_text)
        metadata_date_verified = bool(source_page.get("date_verified")) and (
            parsed_date is not None
            and parsed_date.date() == (_parse_public_news_date(source_page.get("published_at")) or parsed_date).date()
        )
        if parsed_date and not metadata_date_verified:
            date_forms = {
                parsed_date.strftime(fmt).lower()
                for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")
            }
            if not any(date_form in source_text.lower() for date_form in date_forms):
                parsed_date = None
        is_event = str(item.get("kind") or source_page.get("kind") or "").lower() in {"event", "events"}
        date_status = "date-unverified"
        if parsed_date:
            if parsed_date > now.replace(hour=23, minute=59, second=59, microsecond=0):
                if not is_event or (parsed_date - now).days > 548:
                    continue
                date_status = "date-verified-upcoming"
            elif (now - parsed_date).days > 548:
                continue
            else:
                date_status = "date-verified"
            date_text = parsed_date.strftime("%Y-%m-%d")
        else:
            date_text = "Date not verified"
        key = (title.lower(), canonical)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            **item,
            "title": title[:180],
            "date": date_text,
            "date_status": date_status,
            "source_url": source_url,
            "summary": (_clean_snippet(source_excerpt, 360) or "")[:360],
            "confidence": item.get("confidence") or ("Medium" if parsed_date else "Low"),
        })
    def news_order(row):
        parsed = _parse_public_news_date(row.get("date"))
        status = str(row.get("date_status") or "")
        if status == "date-verified-upcoming":
            return (1, parsed.timestamp() if parsed else float("inf"))
        if status == "date-verified":
            return (0, -parsed.timestamp() if parsed else 0)
        return (2, 0)

    rows.sort(key=news_order)
    return rows[:4]


def _company_ai_conclusion(company_name: str, report: dict) -> dict:
    """Summarize the company and evidence; do not turn hiring links into the whole conclusion."""
    profile = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    market = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    products = report.get("products_services") if isinstance(report.get("products_services"), dict) else {}

    def _value(field):
        return _field_text(field) if field is not None else ""

    def _is_unverified_ai_fact(field):
        if not isinstance(field, dict):
            return False
        status = str(field.get("verification_status") or "").lower()
        source = str(field.get("source") or "").lower()
        return status in {"model-knowledge-reviewed", "search-snippet-supported"} or "unverified" in source

    offerings = []
    for row in (products.get("primary_offerings") or [])[:6]:
        value = row.get("item") or row.get("value") if isinstance(row, dict) else row
        if (
            value
            and str(value).strip()
            and "not publicly" not in str(value).lower()
            and not _is_unverified_ai_fact(row)
        ):
            offerings.append(str(value).strip()[:140])
    market_position = market.get("market_position")
    market_trends = market.get("market_trends")
    geographic_reach = market.get("geographic_reach")
    snapshot = {
        "company": company_name,
        "domain": (report.get("_meta") or {}).get("domain") or "",
        "description": _value(profile.get("description")),
        "industry": _value(market.get("industry") or profile.get("industry")),
        "products_services": offerings,
        "market_position": "" if _is_unverified_ai_fact(market_position) else _value(market_position),
        "market_trends": "" if _is_unverified_ai_fact(market_trends) else _value(market_trends),
        "geographic_reach": "" if _is_unverified_ai_fact(geographic_reach) else _value(geographic_reach),
        "recent_news": [
            {"title": n.get("title"), "date": n.get("date"), "summary": n.get("summary"), "source_url": n.get("source_url")}
            for n in (report.get("recent_news") or [])[:4]
            if isinstance(n, dict) and n.get("date_status") == "date-verified"
        ],
        "verified_hiring": [
            {"role": h.get("role"), "source_url": h.get("source_url")}
            for h in (report.get("hiring_signals") or [])[:4] if isinstance(h, dict)
        ],
        "evidence_links": [
            {"title": c.get("title"), "url": c.get("url")}
            for c in ((report.get("_meta") or {}).get("citations") or [])[:8]
            if isinstance(c, dict) and c.get("url")
        ],
    }
    supported_fields = [
        label for label, value in (
            ("Company profile", snapshot["description"]),
            ("Products and services", offerings),
            ("Market position", snapshot["market_position"]),
            ("Market trends", snapshot["market_trends"]),
            ("Geographic reach", snapshot["geographic_reach"]),
            ("Recent news", snapshot["recent_news"]),
            ("Verified hiring", snapshot["verified_hiring"]),
        ) if value
    ]
    if not any((snapshot["description"], offerings, snapshot["market_position"], snapshot["geographic_reach"])):
        return {
            "ai_conclusion": f"Public evidence is too limited to make a specific company-level conclusion about {company_name}.",
            "signals_used": [],
            "source": "Evidence-limited fallback",
        }
    try:
        raw = llm_client.chat(
            [
                {"role": "system", "content": "Return JSON only. Summarize only the supplied company facts; never invent facts or cite a source not listed."},
                {"role": "user", "content": f"""Write a concise 1–2 sentence company-level conclusion for this research report.
Describe what the company does and the market/geography it serves when supported. Mention a recent development only if it is dated and company-specific. Hiring may be one signal, but do not make the conclusion a list of job boards or job links. Separate fact from inference and avoid claims about strategy, growth, or market leadership unless directly supported. If evidence is thin, say so.

REPORT FACTS:
{json.dumps(snapshot, ensure_ascii=False)[:4200]}

Return JSON: {{"ai_conclusion":"...","signals_used":["one of: {', '.join(supported_fields)}"]}}"""},
            ],
            temperature=0.0,
            max_tokens=320,
            json_mode=True,
            timeout=CONCLUSION_LLM_TIMEOUT,
            reasoning_effort="low",
        )
        data = _parse_llm_json(raw)
        conclusion = re.sub(r"\s+", " ", str(data.get("ai_conclusion") or "")).strip()
        if conclusion and len(conclusion) <= 700:
            allowed = set(supported_fields)
            used = [str(x) for x in (data.get("signals_used") or []) if str(x) in allowed]
            return {"ai_conclusion": conclusion, "signals_used": used, "source": "AI synthesis of report evidence"}
    except Exception as exc:  # noqa: BLE001 - readable fallback is still available
        print(f"[Research] Company conclusion generation failed: {exc}")
    description = snapshot["description"] or "; ".join(offerings)
    if snapshot["industry"] and description and snapshot["industry"].lower() not in description.lower():
        description = f"{description} ({snapshot['industry']})"
    return {
        "ai_conclusion": f"{company_name} is described in available public sources as {description[:360]}. Recent strategic conclusions are limited to the evidence collected.",
        "signals_used": [x for x in supported_fields if x in {"Company profile", "Products and services", "Market position", "Geographic reach"}],
        "source": "Evidence-based fallback",
    }


def _has_target_evidence(scraped: dict, wiki: dict, wikidata: dict) -> bool:
    """Require at least one real public signal before synthesising a report."""
    scraped = scraped or {}
    if scraped.get("_site_parked"):
        return False
    site_fields = (
        "title", "description", "homepage_text", "about_text", "products_text",
        "careers_text", "leadership_text", "pricing_text", "blog_text",
    )
    if any(str(scraped.get(key) or "").strip() for key in site_fields):
        return True
    # A real server may block datacenter scraping with 403/429. Do not confuse
    # that with a nonexistent domain; the report will retain low-confidence
    # fields rather than inventing content from an unreachable host.
    if scraped.get("_homepage_reachable"):
        return True
    if (wiki or {}).get("text") or (wiki or {}).get("summary"):
        return True
    return bool((wikidata or {}).get("matched"))


def run(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    domain = urlparse(url).netloc.replace("www.", "")
    t_all = time.time()

    print(f"\n[Research] ====== Deep Intelligence: {url} ======")
    print(f"[Research] FAST={RESEARCH_FAST} DEEP={RESEARCH_DEEP} SKIP_JUDGE={RESEARCH_SKIP_JUDGE} "
          f"SKIP_HIRING_SEARCH={RESEARCH_SKIP_HIRING_SEARCH}")

    brand = _brand_from_domain(domain)
    print("[Research] Phase 1: Parallel scrape + Wikipedia + Wikidata...")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_site = pool.submit(_scrape_website, url, False)
        f_wiki = pool.submit(_fetch_wikipedia_text, brand, domain)
        f_wd = pool.submit(wikidata_client.lookup_company, brand, domain, url)
        scraped = f_site.result()
        wiki = f_wiki.result() or {}
        wd = f_wd.result() or {}
    scraped["wikipedia_text"] = wiki.get("text") or ""
    scraped["wikipedia_url"] = wiki.get("url") or ""
    scraped["wikipedia_summary"] = wiki.get("summary") or ""
    scraped["wikipedia_description"] = wiki.get("description") or ""
    scraped["_wikidata"] = wd
    if not _has_target_evidence(scraped, wiki, wd):
        raise ValueError(
            "Could not verify this target website. The domain returned no public company evidence."
        )
    print(f"[Research] Phase 1 done in {time.time()-t0:.1f}s")

    title = scraped.get("title", "")
    site_name = re.split(r"[|\-:]", title)[0].strip() if title else brand
    if len(site_name) > 48:
        site_name = brand
    site_name_matches_domain = _name_matches_domain(site_name, domain)
    company_name = _anchor_company_name(site_name, domain, scraped)
    # The official site's own title wins over a loosely matched Wikipedia or
    # Wikidata label. Name/domain substring matches can confuse a person or a
    # related organization with the operating company.
    if not site_name_matches_domain and scraped.get("preferred_display_name"):
        company_name = _anchor_company_name(scraped["preferred_display_name"], domain, scraped)
    if not site_name_matches_domain and wd.get("matched") and wd.get("label"):
        company_name = _anchor_company_name(wd["label"], domain, scraped)

    intel = {
        "_source_urls": [],
        "_scraped_pages": [],
        "_multi_contacts": {"emails": [], "phones": []},
        "_wikidata": wd,
        "competitors_direct": "",
        "revenue": wd.get("revenue") or "",
        "employees": wd.get("employees") or "",
        "glassdoor": "",
        "ceo_founder": " ".join((wd.get("ceo") or []) + (wd.get("founders") or [])),
        "news_recent": "",
        "market_position": scraped.get("wikipedia_summary") or "",
        "products": "",
        "contact_email": "",
        "india_registry": "",
        "multi_source_digest": (scraped.get("wikipedia_summary") or "")[:2000],
    }
    if RESEARCH_DEEP:
        print(f"[Research] Phase 2: Intelligence sweep for '{company_name}'...")
        t0 = time.time()
        intel = _collect_intelligence(company_name, domain)
        intel["_wikidata"] = wd
        print(f"[Research] Phase 2 done in {time.time()-t0:.1f}s")
    else:
        print("[Research] Phase 2 skipped (fast path — site + Wikipedia + Wikidata)")

    # These three only need the scraped site data, not the LLM report, so they run in the
    # background while the (slowest) main LLM call is in flight instead of one after another.
    # A result is only used if the inputs it was computed with are still the ones we need.
    prefetch_name = company_name
    bg = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prefetch")
    f_hiring = bg.submit(_fetch_hiring_signals, prefetch_name, domain, scraped.get("careers_text") or "", scraped)
    # The profile-evidence pass below performs the bounded public leadership
    # search in fast mode. Avoid a second overlapping DDG search here.
    f_leaders = bg.submit(
        _collect_leadership,
        prefetch_name,
        domain,
        scraped,
        intel,
        search_public_web=RESEARCH_DEEP,
    )
    # Search and fetch a small set of company-specific news/events while the
    # main report model is working. The result is added only after page fetch
    # and date verification; a search snippet alone is never shown as news.
    f_news = bg.submit(_collect_company_news_events, prefetch_name, domain)
    # Discover public evidence alongside hiring, leadership, and news prefetch.
    # The report judge consumes it after the main profile synthesis returns.
    profile_intel_snapshot = dict(intel)
    profile_intel_snapshot["_scraped_pages"] = list(intel.get("_scraped_pages") or [])
    profile_intel_snapshot["_source_urls"] = list(intel.get("_source_urls") or [])
    f_profile_evidence = (
        bg.submit(_ai_profile_evidence, prefetch_name, domain, scraped, profile_intel_snapshot)
        if RESEARCH_AI_PROFILE_FALLBACK else None
    )
    if not RESEARCH_AI_PROFILE_FALLBACK:
        _EVIDENCE_PREFETCH[(prefetch_name, domain)] = bg.submit(
            _build_site_evidence_blob, prefetch_name, domain, scraped
        )

    print(f"[Research] Phase 3: Azure/LLM ({MODEL}) analysis...")
    t0 = time.time()
    prompt = _build_prompt(url, company_name, scraped, intel)
    try:
        report = _analyze_with_llm(prompt)
        if report.get("error") and not report.get("company_profile"):
            print("[Research] LLM parse issue — using baseline scrape report")
            report = _baseline_report(url, company_name, scraped)
    except Exception as e:
        print(f"[Research] LLM failed ({e}) — using baseline scrape report with contacts")
        report = _baseline_report(url, company_name, scraped)
    print(f"[Research] Phase 3 done in {time.time()-t0:.1f}s")

    # Search/fetch runs at the same time as the main model call. Give this
    # bounded pass a short grace period after synthesis; dropping all evidence
    # at an overly tight join timeout made good public results disappear.
    profile_evidence = []
    if f_profile_evidence:
        try:
            profile_evidence = f_profile_evidence.result(timeout=12)
            intel["_profile_evidence"] = profile_evidence
            _merge_profile_evidence_into_intel(profile_evidence, intel)
            fetched_count = sum(1 for row in profile_evidence if row.get("retrieved"))
            print(
                f"[Research] Public evidence ready: {len(profile_evidence)} references, "
                f"{fetched_count} fetched pages"
            )
        except Exception as e:  # noqa: BLE001
            print(f"[Research] Public profile evidence timed out or failed: {e}")
            intel["_profile_evidence"] = []

    try:
        news_pages = f_news.result(timeout=8)
    except Exception as e:  # bounded public search must not hold up the company report
        print(f"[Research] News/events enrichment unavailable or timed out: {e}")
        news_pages = []
    if news_pages:
        intel.setdefault("_scraped_pages", []).extend(news_pages)
        intel.setdefault("_source_urls", []).extend({
            "title": page.get("title") or "Company news/event",
            "url": page.get("url") or "",
            "category": page.get("category") or "News",
        } for page in news_pages)

    # ALWAYS inject verified contacts from company site + public sites (filter junk)
    cd = scraped.get("contact_data") or {}
    multi = intel.get("_multi_contacts") or {"emails": [], "phones": []}
    merged_emails, merged_phones = [], []
    seen_e, seen_p = set(), set()
    for e in (cd.get("emails") or []) + (multi.get("emails") or []):
        em = (e.get("email") or "").lower().strip()
        if not em or em in seen_e:
            continue
        if not _email_domain_ok(em, domain):
            continue
        seen_e.add(em)
        e = dict(e)
        e["email"] = em
        merged_emails.append(e)
    # Prefer company-domain emails first
    stem = _domain_stem(domain)
    merged_emails.sort(
        key=lambda x: (0 if stem and stem in (x.get("email") or "") else 1, x.get("email") or "")
    )

    for ph in (cd.get("phones") or []) + (multi.get("phones") or []):
        num = (ph.get("number") or "").strip()
        if not _is_valid_phone(num):
            continue
        key = re.sub(r"\D", "", num)
        if key and key not in seen_p:
            seen_p.add(key)
            merged_phones.append(ph)

    sources_used = ["Company Website (Homepage / Footer)"]
    for page in intel.get("_scraped_pages") or []:
        if page.get("emails") or page.get("phones"):
            sources_used.append(page.get("domain", "public"))
    reg_addr = cd.get("address") or ""
    report["contact_intelligence"] = {
        "phones": merged_phones,
        "emails": merged_emails,
        "whatsapp": cd.get("whatsapp") or "Not publicly available",
        "toll_free": cd.get("toll_free") or "Not publicly available",
        "registered_address": reg_addr,
        "addresses": cd.get("addresses", []) or ([reg_addr] if reg_addr else []),
        "address_source": " + ".join(sources_used[:6]),
        "address_confidence": "High" if merged_emails or merged_phones or reg_addr else "Low",
    }
    print(f"[Research] Injected contacts from {len(sources_used)} sources: "
          f"{len(merged_emails)} emails, {len(merged_phones)} phones")

    # Leadership was gathered in the background; join it before the report is normalised.
    try:
        extracted = f_leaders.result()
    except Exception as e:  # noqa: BLE001
        print(f"[Research] Background leadership failed ({e}) - collecting inline")
        extracted = _collect_leadership(company_name, domain, scraped, intel)

    # Fix Groq schema drift so Overview / SWOT / etc. always render
    report = _normalize_report(report, scraped, company_name, url, intel)
    _merge_retrieved_news(report, intel)

    # Leadership from public web + silent Azure gap-fill (never cite ChatGPT)
    scrape_blob = " ".join([
        scraped.get("wikipedia_text") or "",
        scraped.get("leadership_text") or "",
        scraped.get("about_text") or "",
        scraped.get("homepage_text") or "",
        (scraped.get("_structured") or {}).get("about_text") or "",
        (scraped.get("_structured") or {}).get("leadership_text") or "",
        intel.get("ceo_founder") or "",
        intel.get("multi_source_digest") or "",
    ]).lower()
    llm_kept = []
    for l in report.get("leadership_team") or []:
        if not isinstance(l, dict):
            continue
        name = (l.get("name") or "").strip()
        src = str(l.get("source") or "").lower()
        if not name or l.get("din") or "zauba" in src or "mca" in src or "cin" in src:
            continue
        if "chatgpt" in src or "openai" in src:
            continue
        # The analysis model's people are only kept when the scraped sources corroborate
        # them. Accepting its own "public profiles" label let it self-authorize a name
        # that appeared nowhere in the evidence. Grounded gap-fill runs separately.
        if name.lower() in scrape_blob:
            llm_kept.append({
                "name": name,
                "role": l.get("role") or "Leadership",
                "source": "Public company profiles" if "chatgpt" in src else (l.get("source") or "Public web"),
                "confidence": l.get("confidence") or "Medium",
                "background": l.get("background") or "",
            })
    merged_leaders, seen_n = [], set()
    for l in extracted + llm_kept:
        key = (l.get("name") or "").lower()
        if not key or key in seen_n:
            continue
        # Never surface ChatGPT as a source label
        src = str(l.get("source") or "")
        if "chatgpt" in src.lower() or "openai" in src.lower():
            l = dict(l)
            l["source"] = "Public company profiles"
        seen_n.add(key)
        merged_leaders.append(l)

    # Site scrape missed HQ / people: extract from public knowledge, then a
    # second LLM pass keeps or drops each fact. Never cited as ChatGPT.
    profile_fill = {}
    hq_now = _field_text((report.get("company_profile") or {}).get("headquarters")) if isinstance(report.get("company_profile"), dict) else ""
    founded_now = _field_text((report.get("company_profile") or {}).get("founded")) if isinstance(report.get("company_profile"), dict) else ""
    current_named = [
        l for l in merged_leaders
        if isinstance(l, dict) and (l.get("status") or "current") != "historical"
    ]
    # Always fill when the sitting MD/CEO/Chair is missing — a random named person is not enough.
    needs_people = (not auth.has_operating_exec(merged_leaders)) or len(current_named) < 2
    needs_hq = (not hq_now) or "not publicly" in hq_now.lower()
    needs_founded = (not founded_now) or "not publicly" in founded_now.lower()
    if (
        RESEARCH_LLM_ENRICH
        and (needs_people or needs_hq or needs_founded)
        and not RESEARCH_AI_PROFILE_FALLBACK
    ):
        print("[Research] Public-profile fill (extract + LLM verify) for missing HQ/leadership/hiring")
        profile_fill = _llm_public_profile_fill(company_name, domain, scraped, merged_leaders)
        merged_leaders = profile_fill.get("leaders") or merged_leaders
    elif RESEARCH_AI_PROFILE_FALLBACK and (needs_people or needs_hq or needs_founded):
        print("[Research] Missing profile fields will be kept only when public evidence supports them")
    report["leadership_team"] = auth.rank_leadership(
        _normalize_leadership_list(merged_leaders, company_name, scraped)
    )

    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": (
            "Public research mode — founders/directors from company site, The Org, LinkedIn, "
            "Wikipedia, and public profiles. Confidential private data is omitted when not public."
        ),
        "entity_scope": "none",
        "directors": [],
        "cin": "",
    }
    if isinstance(report.get("company_profile"), dict):
        for k in ("cin", "mca_status", "authorized_capital", "paid_up_capital", "zaubacorp_url"):
            report["company_profile"].pop(k, None)

    # Preferred display name from brand heuristics only (no MCA)
    if scraped.get("preferred_display_name"):
        company_name = _anchor_company_name(scraped["preferred_display_name"], domain, scraped)
        if isinstance(report.get("company_profile"), dict):
            report["company_profile"]["name"] = company_name

    # The report judge runs in both modes by default. Only an explicit
    # RESEARCH_SKIP_JUDGE setting takes this lightweight hard-filter path.
    if RESEARCH_SKIP_JUDGE:
        print("[Research] Phase 3b: LLM judge skipped (fast mode)")
        ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
        cur = ma.get("market_position")
        cur_val = cur.get("value") if isinstance(cur, dict) else cur
        if _is_illogical_text(str(cur_val or "")):
            ma["market_position"] = _field("Not publicly available", "Fast filter", "Low")
            report["market_analysis"] = ma
        company_name = _anchor_company_name(
            (report.get("company_profile") or {}).get("name") or company_name,
            domain,
            scraped,
        )
        if isinstance(report.get("company_profile"), dict):
            report["company_profile"]["name"] = company_name
    else:
        print("[Research] Phase 3b: LLM-as-judge validating report...")
        report = _apply_llm_judge(report, scraped, company_name, url, intel)
        if isinstance(report.get("company_profile"), dict) and report["company_profile"].get("name"):
            company_name = _anchor_company_name(report["company_profile"]["name"], domain, scraped)
            report["company_profile"]["name"] = company_name

    # Apply the final source/registry hygiene in both modes.  In fast mode this
    # preserves the already-normalized public leadership list; in deep mode it
    # preserves the judge-approved list.
    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": (
            "Public web research — current executives from Wikidata, company website, and Wikipedia. "
            "Historical founders are labelled and are not the default point of contact."
        ),
        "entity_scope": "none",
        "directors": [],
        "cin": "",
    }
    post_leaders = [
        l for l in (report.get("leadership_team") or [])
        if isinstance(l, dict)
        and l.get("name")
        and "zauba" not in str(l.get("source") or "").lower()
        and "mca" not in str(l.get("source") or "").lower()
        and "cin" not in str(l.get("source") or "").lower()
        and not l.get("din")
    ]
    if not post_leaders and not RESEARCH_SKIP_JUDGE:
        # Judge emptied the list — restore only independently structured current
        # officers, never registry/MCA rows.
        post_leaders = wikidata_client.leaders_from_wikidata(wd)
    report["leadership_team"] = auth.rank_leadership(
        _normalize_leadership_list(post_leaders, company_name, scraped)
    )
    if isinstance(report.get("company_profile"), dict):
        for k in ("cin", "mca_status", "authorized_capital", "paid_up_capital", "zaubacorp_url"):
            report["company_profile"].pop(k, None)

    # In fast mode the report judge already sees the targeted profile evidence,
    # validates leadership/competitors/market claims, and attaches exact source
    # URLs. Reuse that pass instead of making two more serial model calls.
    report_judge_ok = (report.get("_judge") or {}).get("status") == "verified"
    if RESEARCH_FAST and RESEARCH_AI_PROFILE_FALLBACK and report_judge_ok:
        profile_rows = intel.get("_profile_evidence") or []
        report["ai_enrichment"] = {
            "status": "complete" if profile_rows else "complete_no_new_facts",
            "provider": "Public evidence + report judge",
            "judge_score": (report.get("_judge") or {}).get("quality_score", 0),
            "summary": "Profile claims were reviewed against the retrieved public sources.",
            "evidence_count": len(profile_rows),
            "source_urls": [
                str(row.get("url")) for row in profile_rows
                if isinstance(row, dict) and str(row.get("url") or "").startswith(("http://", "https://"))
            ][:20],
            "leaders_added": 0,
            "point_of_contact": {},
        }
    else:
        # Keep the independent profile pass as a fail-soft path when the report
        # judge is unavailable and for explicitly requested deep research.
        report = _run_ai_profile_fallback(report, company_name, domain, scraped, intel)

    # The dedicated AI profile pass already searched and judged public contact
    # evidence. Do not repeat the older candidate+judge pair on the normal
    # path; retain it as a fail-soft fallback if the dedicated pass failed.
    ai_profile_status = (report.get("ai_enrichment") or {}).get("status", "")
    ai_profile_failed = ai_profile_status in {
        "unavailable", "candidate_unavailable", "judge_unavailable",
    }
    existing_public_contact = (
        any(
            isinstance(e, dict)
            and e.get("email")
            and (e.get("person") or e.get("person_name") or e.get("name"))
            for e in ((report.get("contact_intelligence") or {}).get("emails") or [])
        )
        or auth.has_operating_exec(report.get("leadership_team") or [])
    )
    if RESEARCH_AI_PROFILE_FALLBACK and not ai_profile_failed and not existing_public_contact:
        report["_contact_verification"] = {
            "status": "public_report_judge_used",
            "source_urls": (report.get("ai_enrichment") or {}).get("source_urls", []),
        }
    elif RESEARCH_FAST and RESEARCH_AI_PROFILE_FALLBACK and ai_profile_failed:
        # The dedicated profile pass already tried public evidence and its own
        # judge. Repeating the legacy contact-model pair after a timeout adds
        # latency without adding independent evidence; keep existing scraped
        # contacts and report the enrichment as unavailable instead.
        report["_contact_verification"] = {
            "status": "ai_profile_unavailable",
            "source_urls": [],
        }
    else:
        report = _maybe_add_public_point_of_contact(
            report, company_name, domain, scraped, intel
        )

    # Final identity hard-lock (blocked scrapes / judge drift)
    company_name = _anchor_company_name(company_name, domain, scraped)
    if isinstance(report.get("company_profile"), dict):
        report["company_profile"]["name"] = company_name
    if scraped.get("_scrape_blocked"):
        report.setdefault("_meta_flags", {})
        # stored later in _meta; keep a note on profile description if empty/junk
        desc = report["company_profile"].get("description") if isinstance(report.get("company_profile"), dict) else ""
        desc_v = desc.get("value") if isinstance(desc, dict) else desc
        if not desc_v or _is_blocked_page_text(str(desc_v), "") or _is_illogical_text(str(desc_v)):
            report["company_profile"]["description"] = _field(
                f"{company_name} (website partially blocked bot scrapers; profile from public web + domain brand)",
                "Domain brand lock",
                "Medium",
            )

    # Hiring — official employer listings, then LLM-as-judge public fill if still empty
    print("[Research] Phase 4: Verifying official hiring signals...")
    t0 = time.time()
    careers_text = scraped.get("careers_text") or ""
    hiring = None
    hiring_wait_timed_out = False
    if company_name == prefetch_name:
        try:
            hiring = f_hiring.result(timeout=12 if RESEARCH_FAST else None)
        except TimeoutError:
            # Keep the report responsive if a public job board/search provider
            # stalls. The bounded lookup continues in its worker and is omitted
            # from this report rather than repeated inline.
            hiring = []
            hiring_wait_timed_out = True
            print("[Research] Hiring lookup exceeded the fast-mode budget; continuing without it")
        except Exception as e:  # noqa: BLE001
            print(f"[Research] Background hiring lookup failed ({e}) - retrying inline")
    if hiring is None and not hiring_wait_timed_out:
        hiring = _fetch_hiring_signals(company_name, domain, careers_text, scraped)
    if (
        RESEARCH_LLM_ENRICH
        and not hiring
        and (
            not RESEARCH_AI_PROFILE_FALLBACK
            or ai_profile_failed
        )
    ):
        if not profile_fill:
            print("[Research] Public-profile fill for missing hiring status")
            profile_fill = _llm_public_profile_fill(company_name, domain, scraped, merged_leaders)
            # The leadership gate has already run. This fill is used only for
            # hiring URLs here; it must not re-inject unjudged people.
    fill_hire = list((profile_fill or {}).get("hiring") or [])
    if fill_hire:
        combined = list(hiring or []) + fill_hire
        filtered = auth.filter_hiring_signals(combined, company_name, domain)
        # Fast mode keeps the same source-filtered fill as the main hiring path;
        # deep mode applies the employer judge with a fail-soft fallback.
        hiring = _judge_hiring_rows(company_name, domain, filtered) if not RESEARCH_SKIP_JUDGE else filtered
    print(f"[Research] Phase 4 done in {time.time()-t0:.1f}s")
    uniq_hire, seen_keys = [], set()
    for h in hiring or []:
        role = (h.get("role") or "").strip()
        href = (h.get("source_url") or "").split("?")[0].rstrip("/").lower()
        key = href or role.lower()
        if not role or key in seen_keys:
            continue
        seen_keys.add(key)
        uniq_hire.append(h)
    report["hiring_signals"] = uniq_hire[:8]
    _merge_retrieved_news(report, intel)
    report["recent_news"] = _sanitize_recent_news(report, company_name, domain, intel)

    citations = []
    seen_urls = set()
    retrieved_public_urls = {
        _canonical_public_url(str(page.get("url") or ""))
        for page in (intel.get("_scraped_pages") or [])
        if isinstance(page, dict) and page.get("retrieved") is not False and page.get("text")
    }
    retrieved_public_urls.update(
        _canonical_public_url(str(source_url))
        for source_url in (scraped.get("contact_data") or {}).get("source_pages", [])
        if source_url
    )
    if wiki.get("url") and wiki.get("text"):
        retrieved_public_urls.add(_canonical_public_url(wiki["url"]))
    if wd.get("source_url"):
        retrieved_public_urls.add(_canonical_public_url(wd["source_url"]))
    if scraped.get("_homepage_reachable") and not scraped.get("_scrape_blocked"):
        retrieved_public_urls.add(_canonical_public_url(url))

    # also skip discovery of zauba in _add_cite helper when disabled
    def _add_cite(title, cite_url, category="Web", retrieved=None):
        if not cite_url or not str(cite_url).startswith("http"):
            return
        if auth.is_junk_citation(cite_url):
            return
        low = str(cite_url).lower()
        if (not ENABLE_ZAUBACORP) and (not scraped.get("cin_verified")) and "zaubacorp.com" in low:
            return
        try:
            d = urlparse(cite_url).netloc.replace("www.", "").lower()
        except Exception:
            return
        if not d:
            return
        was_retrieved = (
            _canonical_public_url(cite_url) in retrieved_public_urls
            if retrieved is None else bool(retrieved)
        )
        # The global source list contains only pages fetched and checked during
        # this run. Search-result leads can remain attached to individual facts.
        if not was_retrieved or cite_url in seen_urls:
            return
        seen_urls.add(cite_url)
        cat = category
        if cat in ("Web", "Search", "Public Web", "Social Media"):
            cat = auth.classify_source(cite_url, domain)
        citations.append({
            "title": title or d,
            "url": cite_url,
            "domain": d,
            "category": cat,
            "retrieved": was_retrieved,
            "favicon": f"https://www.google.com/s2/favicons?domain={d}&sz=64",
        })

    _add_cite(company_name + " Website", url, "Company Website", retrieved=bool(scraped.get("_homepage_reachable") and not scraped.get("_scrape_blocked")))
    if wd.get("source_url"):
        _add_cite("Wikidata", wd["source_url"], "Wikidata", retrieved=True)
    if scraped.get("wikipedia_url"):
        _add_cite("Wikipedia", scraped["wikipedia_url"], "Encyclopedia", retrieved=True)
    elif scraped.get("wikipedia_text"):
        _add_cite(
            "Wikipedia",
            f"https://en.wikipedia.org/wiki/{company_name.replace(' ', '_')}",
            "Wikipedia",
            retrieved=bool(scraped.get("wikipedia_text")),
        )
    for cp in (scraped.get("contact_data") or {}).get("source_pages", []):
        _add_cite("Contact / Footer", cp, "Contact", retrieved=True)
    for contact_url in ((report.get("contact_intelligence") or {}).get("public_point_of_contact") or {}).get("source_urls", []):
        _add_cite("Public contact evidence", contact_url, "Public Web")
    for profile_url in (report.get("ai_enrichment") or {}).get("source_urls", []):
        _add_cite("Public profile source", profile_url, "Public Web")
    for sl in scraped.get("social_links", [])[:8]:
        if auth.host_is_social(sl):
            _add_cite(urlparse(sl).netloc.replace("www.", ""), sl, "Social Media")
    # Citations = sites we actually visited/scraped first, then discovery URLs
    for page in intel.get("_scraped_pages") or []:
        page_url = page.get("url") or ""
        if "zaubacorp.com" in page_url.lower():
            continue
        _add_cite(
            page.get("title") or page.get("domain", ""),
            page_url,
            page.get("category", "Public Web"),
            retrieved=page.get("retrieved") is not False and bool(page.get("text")),
        )
    for s in intel.get("_source_urls", []):
        s_url = s.get("url") or ""
        if "zaubacorp.com" in s_url.lower():
            continue
        _add_cite(s.get("title", ""), s_url, s.get("category", "Search"), retrieved=False)
    for n in (report.get("recent_news") or []):
        if isinstance(n, dict) and n.get("source_url"):
            _add_cite(n.get("title") or n.get("source", ""), n["source_url"], "News")
    for h in uniq_hire:
        if h.get("source_url"):
            _add_cite(
                h.get("source_title") or h.get("role", "Job Posting"),
                h["source_url"],
                h.get("platform") or "Official Careers",
            )
    for u in (profile_fill or {}).get("urls") or []:
        _add_cite("Official careers", u, "Official Careers")

    # Fill HQ / employees / revenue when the scrape or the model came back thin
    cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}

    def _hq_missing() -> bool:
        v = _field_text(cp.get("headquarters"))
        return not v or "not publicly" in v.lower() or "not available" in v.lower()

    def _founded_missing() -> bool:
        v = _field_text(cp.get("founded"))
        return not v or "not publicly" in v.lower() or "not available" in v.lower()

    # The office address we actually scraped is better evidence than anything inferred
    if _hq_missing() and reg_addr:
        cp["headquarters"] = _field(reg_addr, "Company contact page", "High")
    if wd.get("matched"):
        if _hq_missing() and wd.get("headquarters"):
            cp["headquarters"] = _field(wd["headquarters"], "Wikidata", "High")
        if wd.get("founded_year") and _founded_missing():
            cp["founded"] = _field(wd["founded_year"], "Wikidata", "High")
    if _hq_missing() and (profile_fill or {}).get("headquarters"):
        cp["headquarters"] = _field(profile_fill["headquarters"], "Public company profiles", "Medium")
    if _founded_missing() and (profile_fill or {}).get("founded"):
        cp["founded"] = _field(profile_fill["founded"], "Public company profiles", "Medium")
    # Last resort HQ search if the combined fill still left it empty
    if (
        _hq_missing()
        and RESEARCH_LLM_ENRICH
        and not (profile_fill or {}).get("headquarters")
        and (not RESEARCH_AI_PROFILE_FALLBACK or ai_profile_failed)
    ):
        hq_fill = _enrich_headquarters_via_llm(company_name, domain)
        if hq_fill.get("headquarters"):
            cp["headquarters"] = _field(
                hq_fill["headquarters"], "Public company profiles", hq_fill.get("confidence", "Medium")
            )
            for u in hq_fill.get("urls") or []:
                _add_cite("Company profile", u, "Public Web")
    if wd.get("employees"):
        emp_v = _field_text(cp.get("employee_count"))
        if not emp_v or "not publicly" in emp_v.lower():
            cp["employee_count"] = _field(wd["employees"], "Wikidata", "High")
    if wd.get("revenue"):
        cp["annual_revenue"] = _field(wd["revenue"], "Wikidata", "High")
        fin = report.get("financial_data") if isinstance(report.get("financial_data"), dict) else {}
        fin["revenue_estimate"] = _field(wd["revenue"], "Wikidata", "High")
        report["financial_data"] = fin
    report["company_profile"] = cp

    # Final flatten — never ship nested objects to the UI
    ma = report.get("market_analysis") if isinstance(report.get("market_analysis"), dict) else {}
    ma["geographic_reach"] = auth.normalize_geographic_reach(
        ma.get("geographic_reach"),
        _field_text(cp.get("headquarters")),
        _field_text(cp.get("description")),
    )
    report["market_analysis"] = ma
    fin = report.get("financial_data") if isinstance(report.get("financial_data"), dict) else {}
    raw_revenue = fin.get("revenue_estimate")
    cleaned_rev = auth.sanitize_revenue(raw_revenue)
    if cleaned_rev:
        fin["revenue_estimate"] = _field(
            cleaned_rev,
            raw_revenue.get("source") if isinstance(raw_revenue, dict) else "Public filings",
            "High" if wd.get("revenue") else "Medium",
        )
        if isinstance(raw_revenue, dict):
            for key in ("verification_status", "source_urls"):
                if key in raw_revenue:
                    fin["revenue_estimate"][key] = raw_revenue[key]
        cp["annual_revenue"] = dict(fin["revenue_estimate"])
    else:
        fin["revenue_estimate"] = _field("Not publicly available", "Public filings", "Low")
    report["financial_data"] = fin
    if not cleaned_rev:
        cp["annual_revenue"] = _field("Not publicly available", "Public filings", "Low")
        report["company_profile"] = cp

    report["leadership_team"] = auth.rank_leadership(report.get("leadership_team") or [])
    report["point_of_contact"] = auth.select_point_of_contact(report)

    judge_q = None
    if isinstance(report.get("_judge"), dict):
        try:
            judge_q = int(report["_judge"].get("quality_score"))
        except (TypeError, ValueError):
            judge_q = None
    report["_meta"] = {
        "queried_url": url,
        "company_name": company_name,
        "domain": domain,
        "scrape_blocked": bool(scraped.get("_scrape_blocked")),
        "cin_verified": False,
        "verified_cin": "",
        "social_links": scraped.get("social_links", []),
        "model_used": MODEL,
        "wikidata_qid": wd.get("qid") or "",
        "sources_checked": [
            "Company Website + Footer",
            "Wikidata (current officers / HQ / revenue, domain-matched)",
            "Wikipedia (background)",
            "Public web (LinkedIn company, news, org charts)",
        ],
        "mcp_sites_scraped": [p.get("domain") for p in (intel.get("_scraped_pages") or [])],
        "citations": citations[:20],
        "citation_count": min(len(citations), 20),
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "elapsed_seconds": round(time.time() - t_all, 1),
        "fast_mode": RESEARCH_FAST,
        "judge_required": not RESEARCH_SKIP_JUDGE,
        "judge_status": (
            "skipped" if RESEARCH_SKIP_JUDGE
            else (report.get("_judge") or {}).get("status", "unavailable")
        ),
        "public_contact_status": (report.get("_contact_verification") or {}).get("status", "unavailable"),
        "public_contact_sources": (report.get("_contact_verification") or {}).get("source_urls", []),
        "ai_profile_status": (report.get("ai_enrichment") or {}).get("status", "unavailable"),
        "ai_profile_judge_score": (report.get("ai_enrichment") or {}).get("judge_score", 0),
        "ai_profile_evidence_count": (report.get("ai_enrichment") or {}).get("evidence_count", 0),
    }
    conclusion = _company_ai_conclusion(company_name, report)
    report["ai_conclusion"] = conclusion.get("ai_conclusion") or ""
    report["signals_used"] = conclusion.get("signals_used") or []
    report["ai_conclusion_source"] = conclusion.get("source") or "AI synthesis"
    report["intelligence_score"] = auth.compute_honest_scores(
        report, citations=citations, judge_quality=judge_q
    )

    bg.shutdown(wait=False)
    _EVIDENCE_PREFETCH.pop((prefetch_name, domain), None)   # not consumed when no profile fill was needed

    print(f"[Research] ====== Complete in {time.time()-t_all:.1f}s: contacts={len(cd.get('emails', []))}e/"
          f"{len(cd.get('phones', []))}p citations={len(citations)} "
          f"leadership={len(report.get('leadership_team') or [])} "
          f"score={report['intelligence_score'].get('overall')} ======\n")
    return report
