"""
Company Intelligence Research Engine  v2
==========================================
Phase 1 — SCRAPE    : Homepage + /about + /team + /products + /pricing + /careers + Wikipedia
Phase 2 — SEARCH    : 20+ DuckDuckGo targeted queries across every intelligence dimension
Phase 3 — SCRAPE+   : Fetch & read top news article content directly
Phase 4 — ANALYZE   : Azure OpenAI (primary) via shared LLM client
Phase 5 — REPORT    : Structured deep intelligence JSON
"""

import os, re, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
import requests
from dotenv import load_dotenv
load_dotenv()

from backend.services import llm as llm_client

MODEL = (
    llm_client.AZURE_MODEL
    if llm_client.azure_configured()
    else (
        llm_client.GROQ_MODEL
        if getattr(llm_client, "RESEARCH_USE_GROQ", False) and llm_client.groq_configured()
        else (llm_client.AZURE_MODEL if llm_client.azure_configured() else "gpt-5-mini")
    )
)

# Fast research mode (default ON) — target ~45–70s instead of 3–4 minutes.
# Set RESEARCH_FAST=0 for deeper (slower) sweeps.
RESEARCH_FAST = os.getenv("RESEARCH_FAST", "1").strip().lower() not in ("0", "false", "no", "off")
# Skip second LLM judge pass in fast mode (biggest latency win after scrape/search).
RESEARCH_SKIP_JUDGE = os.getenv(
    "RESEARCH_SKIP_JUDGE",
    "1" if RESEARCH_FAST else "0",
).strip().lower() not in ("0", "false", "no", "off")
# Skip multi-query hiring search in fast mode (careers page text only).
RESEARCH_SKIP_HIRING_SEARCH = os.getenv(
    "RESEARCH_SKIP_HIRING_SEARCH",
    "1" if RESEARCH_FAST else "0",
).strip().lower() not in ("0", "false", "no", "off")

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


def _domain_stem(domain: str) -> str:
    d = (domain or "").lower().replace("www.", "")
    return (d.split(".")[0] if d else "").strip()


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
    emails = list(dict.fromkeys(re.findall(email_pat, combined, re.I)))[:12]
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
# CONTACT INTELLIGENCE — extract emails, phones with person names
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_contact_page(origin: str, raw_html: str = "", homepage_soup=None) -> dict:
    """
    Scrape homepage HTML + /contact pages for phones/emails WITH person names.
    Uses raw HTML first (footer is often where contacts live).
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
        for email in email_pat.findall(page_text):
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

        # Addresses — look for office blocks
        for kw in ["Mumbai HQ", "Mumbai Office", "Registered Office", "Head Office",
                   "Mangalore Office", "Surat Office", "Office Address", "Get In Touch"]:
            if kw.lower() in page_text.lower():
                idx = page_text.lower().find(kw.lower())
                snippet = re.sub(r"\s+", " ", page_text[idx:idx + 250]).strip()
                if snippet and snippet not in contact["addresses"]:
                    contact["addresses"].append(snippet[:220])
        if contact["addresses"] and not contact["address"]:
            contact["address"] = contact["addresses"][0]

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

    # 2) Contact pages (fast: 2 paths parallel; deep: more sequential)
    contact_paths = (
        ["/contact", "/contact-us"]
        if RESEARCH_FAST
        else ["/contact", "/contact-us", "/contactus", "/reach-us",
              "/get-in-touch", "/about/contact", "/connect"]
    )

    def _fetch_contact(path: str):
        try:
            resp = requests.get(origin + path, headers=HEADERS, timeout=5 if RESEARCH_FAST else 12)
            if resp.status_code == 200 and len(resp.text) > 500:
                return path, resp.text
        except Exception:
            pass
        return path, None

    with ThreadPoolExecutor(max_workers=min(4, len(contact_paths))) as pool:
        for path, html in pool.map(lambda p: _fetch_contact(p), contact_paths):
            if html:
                _parse_html(html, f"Contact page ({path})")
                contact["source_pages"].append(origin + path)
                print(f"[Contact] Scraped {path}")
                if RESEARCH_FAST and (contact["emails"] or contact["phones"]):
                    break

    # 3) Fallback soup if provided
    if homepage_soup and not contact["emails"] and not contact["phones"]:
        _parse_html(str(homepage_soup), "Homepage soup")

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

def _fetch_page(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return cleaned text."""
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:5000]
    except Exception:
        return ""


def _scrape_one_subpage(origin: str, key: str, paths: list, timeout: int = 6) -> tuple:
    """Try paths for one content bucket; return (key, text)."""
    for path in paths:
        text = _fetch_page(origin + path, timeout=timeout)
        if len(text) > 300:
            return key, text, path
    return key, "", ""


def _scrape_website(url: str) -> dict:
    """Scrape homepage + key sub-pages for maximum context."""
    from bs4 import BeautifulSoup

    result = {
        "url": url, "title": "", "description": "", "keywords": "",
        "homepage_text": "", "about_text": "", "products_text": "",
        "pricing_text": "", "careers_text": "", "blog_text": "",
        "leadership_text": "", "nav_links": [], "social_links": [],
        "emails": [], "phones": [], "tech_hints": [],
    }

    base = url.rstrip("/")
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    _homepage_raw = ""   # keep raw HTML for contact scraper (footer intact)

    # ── Homepage ──────────────────────────────────────────────────────
    try:
        home_timeout = 12 if RESEARCH_FAST else 20
        resp = requests.get(url, headers=HEADERS, timeout=home_timeout, allow_redirects=True)
        if resp.status_code == 403:
            # Some enterprise sites block datacenter UAs — retry with alternate UA
            alt = dict(HEADERS)
            alt["User-Agent"] = (
                "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
            )
            resp = requests.get(url, headers=alt, timeout=home_timeout, allow_redirects=True)
        resp.raise_for_status()
        _homepage_raw = resp.text
        soup = BeautifulSoup(resp.text, "html.parser")

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
        social_patterns = ["linkedin.com","twitter.com","instagram.com",
                           "facebook.com","youtube.com","tiktok.com","x.com"]
        result["social_links"] = list({
            a["href"] for a in soup.find_all("a", href=True)
            if any(p in a["href"].lower() for p in social_patterns)
        })[:12]

        # Nav links
        result["nav_links"] = list({
            a.get_text(strip=True)
            for a in soup.find_all("a", href=True)
            if a.get_text(strip=True) and len(a.get_text(strip=True)) < 40
        })[:40]

        # Emails & phones (quick pass from raw HTML before footer is removed)
        email_pat = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        result["emails"] = list(set(re.findall(email_pat, resp.text)))[:10]

        # Clean homepage body text for LLM (footer removed here only for body_text)
        soup_body = BeautifulSoup(resp.text, "html.parser")
        for tag in soup_body(["script","style","nav","footer","header","noscript"]):
            tag.decompose()
        result["homepage_text"] = re.sub(r"\s+", " ", soup_body.get_text(separator=" ", strip=True))[:6000]

    except Exception as e:
        print(f"[Research] Homepage scrape failed: {e}")

    # Detect WAF / bot-block pages — these poison brand naming if used as title
    result["_scrape_blocked"] = _is_blocked_page_text(
        result.get("title") or "", result.get("homepage_text") or ""
    )
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

    # ── Sub-pages (parallel; fewer buckets in fast mode) ──────────────
    if RESEARCH_FAST:
        sub_pages = {
            "about_text":     ["/about", "/about-us", "/company", "/investor-relations", "/investors"],
            "products_text":  ["/products", "/services", "/solutions", "/platform"],
            "careers_text":   ["/careers", "/jobs"],
            "leadership_text":["/leadership", "/team", "/management", "/board-of-directors"],
        }
        sub_timeout = 5
    else:
        sub_pages = {
            "about_text":     ["/about", "/about-us", "/company", "/who-we-are",
                               "/investor-relations", "/investors", "/investor"],
            "products_text":  ["/products", "/services", "/solutions", "/platform"],
            "pricing_text":   ["/pricing", "/plans", "/subscription"],
            "careers_text":   ["/careers", "/jobs", "/work-with-us", "/team"],
            "leadership_text":["/leadership", "/team", "/management", "/executive-team"],
            "blog_text":      ["/blog", "/news", "/press", "/resources"],
        }
        sub_timeout = 10

    with ThreadPoolExecutor(max_workers=min(6, len(sub_pages))) as pool:
        futures = [
            pool.submit(_scrape_one_subpage, origin, key, paths, sub_timeout)
            for key, paths in sub_pages.items()
        ]
        for fut in as_completed(futures):
            try:
                key, text, path = fut.result()
                if text:
                    result[key] = text
                    print(f"[Research] Scraped sub-page: {path} ({len(text)} chars)")
            except Exception as e:
                print(f"[Research] sub-page fail: {e}")

    # ── Contact page — deep extraction from RAW HTML (footer intact) ──
    result["contact_data"] = _scrape_contact_page(origin, raw_html=_homepage_raw)
    print(f"[Research] Contact: {len(result['contact_data'].get('emails',[]))} emails, "
          f"{len(result['contact_data'].get('phones',[]))} phones")

    # Wikipedia for leadership / HQ (faithful public source)
    brand_for_wiki = _brand_from_domain(parsed.netloc.replace("www.", ""))
    title0 = (result.get("title") or "").strip()
    if title0 and not _is_blocked_page_text(title0, ""):
        brand_for_wiki = re.split(r"[|\-—–:]", title0)[0].strip() or brand_for_wiki
    wiki = _fetch_wikipedia_text(brand_for_wiki, parsed.netloc.replace("www.", ""))
    result["wikipedia_text"] = wiki.get("text") or ""
    result["wikipedia_url"] = wiki.get("url") or ""
    result["wikipedia_summary"] = wiki.get("summary") or ""
    result["wikipedia_description"] = wiki.get("description") or ""

    # Skip CIN / Zauba entirely — global public-web research only
    result["zaubacorp_text"] = ""
    result["zaubacorp_url"] = ""
    result["zaubacorp_structured"] = {}
    result["zauba_match_confidence"] = "Low"
    result["zauba_match_score"] = 0
    result["zauba_match_reason"] = "CIN/MCA disabled — website + public web only"
    result["zauba_alternatives"] = []
    result["entity_signals"] = {}
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
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"[Research] DDG failed for '{query}': {e}")
        return []


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


def _fetch_wikipedia_text(company_name: str, domain: str = "") -> dict:
    """Fetch clean Wikipedia summary (API) + page text for leadership/HQ facts."""
    out = {
        "text": "", "url": "", "title": "",
        "summary": "", "description": "",
    }
    queries = [
        f"site:en.wikipedia.org {company_name}",
        f"site:en.wikipedia.org {company_name} company",
    ]
    if domain:
        queries.append(f"site:en.wikipedia.org {domain.split('.')[0]}")
    wiki_url = ""
    for q in queries:
        for r in _ddg_search(q, max_results=4):
            href = r.get("href") or ""
            if "wikipedia.org/wiki/" in href.lower() and ":" not in href.split("/wiki/")[-1]:
                wiki_url = href.split("#")[0]
                break
        if wiki_url:
            break
    title_guess = ""
    if wiki_url:
        title_guess = wiki_url.rstrip("/").split("/")[-1]
    elif domain:
        title_guess = _brand_from_domain(domain).replace(" ", "_")

    # Prefer REST summary — clean prose, no nav chrome
    if title_guess:
        try:
            api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title_guess}"
            resp = requests.get(api, headers=HEADERS, timeout=8)
            if resp.ok:
                data = resp.json() or {}
                extract = (data.get("extract") or "").strip()
                desc = (data.get("description") or "").strip()
                page_url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
                if extract and len(extract) > 80:
                    out["summary"] = extract[:1200]
                    out["description"] = desc[:200]
                    out["url"] = page_url or wiki_url or api
                    out["title"] = (data.get("title") or title_guess).replace("_", " ")
                    out["text"] = extract[:8000]
                    print(f"[Research] Wikipedia summary API: {out['url']} ({len(extract)} chars)")
        except Exception as e:
            print(f"[Research] Wikipedia summary API failed: {e}")

    if not wiki_url and out.get("url"):
        wiki_url = out["url"]
    if not wiki_url and not out.get("summary"):
        return out

    # Extra page text for leadership parsing when summary alone is thin
    if wiki_url and len(out.get("text") or "") < 500:
        raw = _fetch_page(wiki_url, timeout=8)
        if raw and (
            company_name.split()[0].lower() in raw.lower()
            or _domain_stem(domain) in raw.lower()
        ):
            out["text"] = ((out.get("summary") or "") + "\n" + raw)[:8000]
            out["url"] = out.get("url") or wiki_url
            if not out.get("summary"):
                cleaned = _clean_snippet(raw, max_len=600)
                if cleaned:
                    out["summary"] = cleaned
            print(f"[Research] Wikipedia page: {wiki_url} ({len(out['text'])} chars)")
    elif wiki_url and not out.get("url"):
        out["url"] = wiki_url

    blob = (out.get("summary") or out.get("text") or "").lower()
    if blob and company_name.split()[0].lower() not in blob and _domain_stem(domain) not in blob:
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


def _parse_leadership_from_text(text: str, source: str, company_name: str = "") -> list:
    """Extract founder/CEO/MD/chairman mentions from source text — never invent."""
    if not text:
        return []
    leaders = []
    seen = set()
    # Roles matched case-insensitively; person names stay Title Case (no re.I on names).
    role_words = (
        r"CEO|Chief Executive Officer|Managing Director|MD|Chairman|Chairperson|"
        r"Vice Chairperson|Vice Chairman|Founder|Co-Founder|Executive Director|"
        r"Whole[- ]time Director|Director"
    )
    patterns = [
        r"(?:founded by|Founded by|founder[s]?|co-?founders?)\s*[:\-]?\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3})",
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s*(?:is|was|serves as|,)\s+(?:the\s+)?(?i:{role_words})\b",
        rf"(?i:{role_words})\s*[:\-]\s*([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})",
        # Wikipedia infobox: Name ( managing director )
        rf"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){{1,3}})\s*\(\s*(?i:{role_words})\s*\)",
    ]
    role_aliases = {
        "ceo", "md", "chairman", "chairperson", "founder", "co-founder",
        "managing director", "chief executive officer", "executive director",
        "whole-time director", "whole time director", "vice chairperson",
        "vice chairman", "director",
    }
    for pat in patterns:
        for m in re.finditer(pat, text):
            groups = [g for g in m.groups() if g]
            # full match may include role via (?i:...) non-capturing — find role from match text
            full = m.group(0)
            name = groups[0].strip() if groups else ""
            role = "Leadership"
            # Prefer explicit role capture if present
            if len(groups) >= 2:
                a, b = groups[0].strip(), groups[1].strip()
                if a.lower() in role_aliases:
                    role, name = a, b
                elif b.lower() in role_aliases:
                    name, role = a, b
                else:
                    name, role = a, b
            else:
                rm = re.search(rf"(?i:{role_words})", full)
                if rm:
                    role = rm.group(0)
            name = re.sub(r"\s+", " ", name).strip(" ,;.|")
            name = re.sub(r"\.+$", "", name).strip()
            role = re.sub(r"\s+", " ", role).strip()
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
            seen.add(key)
            leaders.append({
                "name": name,
                "role": role.title() if len(role) <= 40 else role[:40],
                "source": source,
                "confidence": "High" if "wikipedia" in source.lower() else "Medium",
                "background": f"Mentioned in {source}",
            })
    return leaders[:8]


def _collect_leadership(company_name: str, domain: str, scraped: dict, intel: dict) -> list:
    """Gather leadership ONLY from scraped public sources (Wikipedia, about, leadership page)."""
    leaders = []
    # Website pages
    for key, label in (
        ("leadership_text", "Company leadership page"),
        ("about_text", "Company about page"),
        ("homepage_text", "Company website"),
    ):
        leaders.extend(_parse_leadership_from_text(scraped.get(key) or "", label, company_name))

    # Wikipedia
    wiki = scraped.get("wikipedia_text") or ""
    wiki_url = scraped.get("wikipedia_url") or ""
    if wiki:
        leaders.extend(_parse_leadership_from_text(wiki, wiki_url or "Wikipedia", company_name))

    # Public scrape digest / CEO snippets
    leaders.extend(_parse_leadership_from_text(intel.get("ceo_founder") or "", "Public web", company_name))
    for page in intel.get("_scraped_pages") or []:
        cat = (page.get("category") or "").lower()
        if any(k in cat for k in ("encyclopedia", "company profile", "news", "financial")):
            leaders.extend(_parse_leadership_from_text(
                page.get("text") or "", page.get("domain") or "Public web", company_name
            ))

    # Targeted search snippets for CEO/founder (faithful — titles/snippets only)
    for q in [
        f'"{company_name}" CEO',
        f'"{company_name}" Managing Director',
        f'"{company_name}" founder',
    ][:2]:
        for r in _ddg_search(q, max_results=3):
            blob = f"{r.get('title','')} {r.get('body','')}"
            src = urlparse(r.get("href") or "").netloc.replace("www.", "") or "Web search"
            leaders.extend(_parse_leadership_from_text(blob, src, company_name))

    # Dedup by name
    out, seen = [], set()
    for l in leaders:
        key = (l.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(l)
    print(f"[Research] Leadership extracted: {len(out)} people")
    return out[:6]


def _snippets(results: list, max_chars: int = 2000) -> str:
    parts = [f"[{r.get('title','')}] {r.get('body','')}" for r in results if r.get("body")]
    return " | ".join(parts)[:max_chars]


PUBLIC_SOURCE_SITES = [
    ("tofler.in", "Financial / Directors"),
    ("ambitionbox.com", "Employee Reviews"),
    ("glassdoor.", "Employee Reviews"),
    ("linkedin.com", "Company Profile"),
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


def _site_category(url: str) -> str:
    u = (url or "").lower()
    for needle, cat in PUBLIC_SOURCE_SITES:
        if needle in u:
            return cat
    return "Public Web"


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
    if RESEARCH_FAST:
        site_queries = [
            f'"{company_name}" company overview',
            f"{company_name} competitors",
            f'site:en.wikipedia.org "{company_name}"',
            f'"{company_name}" CEO OR "Managing Director" OR founder',
            f"site:linkedin.com/company {company_name}",
        ]
        max_results = 3
    else:
        site_queries = [
            f'"{company_name}" company overview',
            f"site:linkedin.com/company {company_name}",
            f"site:opencorporates.com {company_name}",
            f"{company_name} {domain} competitors",
            f"{company_name} news",
            f"site:crunchbase.com {company_name}",
            f'site:en.wikipedia.org "{company_name}"',
            f'"{company_name}" CEO OR "Managing Director" OR founder',
        ]
        max_results = 3

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
                "category": _site_category(href),
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
    """Scrape Agent — visit each public URL and extract text + contacts. Skip junk/login pages."""
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
        discovered, domain, max_pages=2 if RESEARCH_FAST else 4
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
- Never invent people, funding rounds, or exact revenue figures.
- Do NOT use Indian MCA / ZaubaCorp / CIN. Leadership only if clearly named in the provided sources (website, Wikipedia, reputable scrapes).
- Stay faithful to sources: copy names/roles exactly as written; never guess founders or directors.
- Cite a source domain for each fact. Output ONLY valid JSON.
- For numeric facts (revenue, funding, headcount) missing from sources => Not publicly available.
- Competitors MUST be same industry / same work domain as the website. Never mix unrelated domains.
- Do NOT invent SWOT points from login pages or unrelated HR portals.
- If unsure about a fact, use Not publicly available with Low confidence — never guess."""


def _build_prompt(url, company_name, scraped, intel):
    """Compact prompt — must stay under Groq free-tier TPM (~8000 tokens)."""
    def clip(s, n=600):
        return (s or "")[:n]

    contact = scraped.get("contact_data") or {}

    return f"""Company: {company_name}
URL: {url}
Title: {clip(scraped.get('title'), 120)}
Description: {clip(scraped.get('description'), 300)}
Homepage: {clip(scraped.get('homepage_text'), 550 if RESEARCH_FAST else 900)}
About: {clip(scraped.get('about_text'), 350 if RESEARCH_FAST else 500)}
Products: {clip(scraped.get('products_text'), 350 if RESEARCH_FAST else 500)}
Leadership page: {clip(scraped.get('leadership_text'), 250 if RESEARCH_FAST else 400)}
Wikipedia: {clip(scraped.get('wikipedia_summary') or scraped.get('wikipedia_text'), 900 if RESEARCH_FAST else 1400)}
Social: {', '.join((scraped.get('social_links') or [])[:6])}

CONTACTS already scraped (copy into contact_intelligence, do not invent):
emails={clip(json.dumps(contact.get('emails',[])), 500)}
phones={clip(json.dumps(contact.get('phones',[])), 500)}
address={clip(contact.get('address'), 200)}

MULTI-SOURCE PUBLIC WEB SCRAPES (visited & scraped, not just search snippets):
{clip(intel.get('multi_source_digest'), 1800 if RESEARCH_FAST else 3500)}

TOPIC SNIPPETS:
competitors: {clip(intel.get('competitors_direct'), 250 if RESEARCH_FAST else 350)}
funding: {clip(intel.get('revenue'), 180 if RESEARCH_FAST else 250)}
employees: {clip(intel.get('employees'), 180 if RESEARCH_FAST else 250)}
reviews: {clip(intel.get('glassdoor'), 180 if RESEARCH_FAST else 250)}
leadership: {clip(intel.get('ceo_founder'), 250 if RESEARCH_FAST else 400)}
news: {clip(intel.get('news_recent'), 200 if RESEARCH_FAST else 300)}
market: {clip(intel.get('market_position'), 200 if RESEARCH_FAST else 250)}

Return ONLY compact JSON. IMPORTANT schema rules:
- company_profile: object with name, website, description; founded/etc as {{value,source,confidence}}
- products_services: {{"primary_offerings":[{{"item","source","confidence"}}], "pricing_model":{{...}}, "target_customers":{{...}}}}
- market_analysis: {{"industry":{{...}},"market_position":{{...}},"geographic_reach":{{...}}}}
- swot_analysis: ALL 4 keys strengths/weaknesses/opportunities/threats as arrays of
  {{"point","source","confidence"}} — at least 3 points each. Never use "Not publicly available" as a point.
- competitors: array of at least 3 objects {{"name","description","strengths","weaknesses","threat_level","source","confidence"}}
- leadership_team: array of {{"name","role","source","confidence","background"}} ONLY for people named in Wikipedia/website/leadership sources above — empty array if none named
- risk_assessment: overall_risk_level string + regulatory/competitive/operational/reputational_risks as arrays of {{"risk","source","confidence"}}
- financial_data: revenue/funding only if found in scrapes; else Not publicly available
- recent_news: array of objects; intelligence_score: {{"overall","data_completeness","source_reliability","summary"}}
Do NOT wrap whole sections in a single {{value,source,confidence}} object.
Never invent people or exact revenue/funding numbers. No CIN / MCA fields."""


def _analyze_with_llm(prompt: str) -> dict:
    """Analyze scraped intel with Azure OpenAI (production primary)."""
    safe_prompt = (
        "No invented people/revenue. Leadership only from website or clear public sources. "
        "Do not use Indian MCA / ZaubaCorp. Competitors must match the company's actual domain of work. "
        "Never cite ChatGPT sign-in pages or UI chrome. If unsure, use Not publicly available. "
        "Return ONLY valid JSON.\n\n"
        + prompt
    )
    # Azure gpt-5 / research prompts can be longer than Groq free tier
    if len(safe_prompt) > 16000:
        safe_prompt = safe_prompt[:16000]

    max_tok = 4000 if RESEARCH_FAST else 5000
    llm_timeout = 90.0 if RESEARCH_FAST else 150.0

    def _call(prompt_text: str) -> str:
        return llm_client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT[:1200]},
                {"role": "user", "content": prompt_text},
            ],
            temperature=0.15,
            max_tokens=max_tok,
            json_mode=True,
            timeout=llm_timeout,
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
        print(f"[Research] JSON parse error: {e} — retrying compact prompt")
        retry = (
            "Return ONLY valid compact JSON for this company research. "
            "Keep SWOT to 2 points each. Max 4 competitors. No trailing commas.\n\n"
            + safe_prompt[:8000]
        )
        try:
            raw2 = _call(retry)
            return _parse(raw2)
        except Exception as e2:
            print(f"[Research] JSON retry failed: {e2}")
            return {"error": f"JSON parse failed: {e}", "raw": (raw or "")[:2000]}


def _analyze_with_groq(prompt: str) -> dict:
    """Back-compat alias."""
    return _analyze_with_llm(prompt)


def _baseline_report(url, company_name, scraped) -> dict:
    """Scrape-only report when Groq fails — contacts still included."""
    cd = scraped.get("contact_data") or {}
    return {
        "company_profile": {
            "name": company_name,
            "website": url,
            "description": scraped.get("description") or (scraped.get("homepage_text") or "")[:280],
            "founded": {
                "value": "Not publicly available",
                "source": "Website",
                "confidence": "Low",
            },
            "headquarters": {
                "value": cd.get("address") or "Not publicly available",
                "source": "Website", "confidence": "Medium" if cd.get("address") else "Low",
            },
            "industry": {"value": "Not publicly available", "source": "Website", "confidence": "Low"},
        },
        "leadership_team": _collect_leadership(company_name, urlparse(url).netloc.replace("www.", ""), scraped, {}),
        "contact_intelligence": {
            "emails": cd.get("emails") or [],
            "phones": [p for p in (cd.get("phones") or []) if _is_valid_phone(p.get("number") or "")],
            "registered_address": cd.get("address") or "",
        },
        "competitors": [],
        "swot_analysis": {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []},
        "intelligence_score": {
            "overall": 40,
            "data_completeness": 30,
            "source_reliability": 50,
            "summary": "Baseline scrape report (LLM unavailable).",
        },
        "ai_conclusion": f"Public scrape baseline for {company_name}.",
        "signals_used": [],
        "hiring_signals": [],
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
        return value
    return {"value": value if value else "Not publicly available",
            "source": source, "confidence": confidence}


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
        scraped.get("description") or "",
        scraped.get("homepage_text") or "",
        scraped.get("about_text") or "",
        scraped.get("products_text") or "",
        intel.get("products") or "",
        intel.get("market_position") or "",
        intel.get("multi_source_digest") or "",
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
        ("ecommerce",
         r"e-?commerce|online store|marketplace|retail|d2c|fashion brand",
         [
             ("Amazon India", "Marketplace / e-commerce giant", "High"),
             ("Flipkart", "Major Indian e-commerce platform", "High"),
             ("Myntra", "Fashion e-commerce", "Medium"),
             ("Meesho", "Social commerce marketplace", "Medium"),
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
    for label, pattern, peers in catalogs:
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
    """Always return a full 4-quadrant SWOT from public signals — never 'N/A' placeholders."""
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
    if not strengths:
        strengths.append({"point": f"{name} maintains an active public website and brand presence",
                          "source": "Company Website", "confidence": "Medium"})

    weaknesses = [
        {"point": "No public pricing page — buyers cannot self-serve compare costs",
         "source": "Website scan", "confidence": "High"} if not scraped.get("pricing_text") else None,
        {"point": "Thin public employee-review footprint (Glassdoor/AmbitionBox limited)",
         "source": "Public web scrape", "confidence": "Medium"} if len(reviews) < 80 else None,
        {"point": "Public financials (revenue/profit) largely undisclosed vs listed peers",
         "source": "Public web scrape", "confidence": "Medium"},
        {"point": "Limited third-party news coverage reduces brand discovery outside owned channels",
         "source": "News scrape", "confidence": "Low"} if len(intel.get("news_recent") or "") < 60 else None,
    ]
    weaknesses = [w for w in weaknesses if w]
    if len(weaknesses) < 2:
        weaknesses.append({"point": "Brand awareness may lag larger, better-funded competitors in the same category",
                           "source": "Competitive analysis", "confidence": "Medium"})

    opportunities = []
    if "india" in home_l or "mumbai" in home_l or "delhi" in home_l or "bengaluru" in home_l:
        opportunities.append({"point": "India growth market — expand coverage across metros and Tier-2 cities",
                              "source": "Market context + Website", "confidence": "Medium"})
    opp_by_industry = {
        "engineering": "Package digital engineering / BIM / sustainability as premium offerings",
        "software": "Productize services into recurring SaaS / managed offerings",
        "manufacturing": "Export markets and supplier diversification create expansion upside",
        "healthcare": "Telehealth / diagnostics partnerships can widen patient reach",
        "ecommerce": "Content + community commerce can lift organic acquisition",
        "education": "Corporate upskilling and hybrid learning programs are underserved",
        "logistics": "E-commerce fulfillment demand supports network density plays",
        "professional_services": "Thought-leadership content can drive inbound B2B leads",
        "general": "Publish case studies and SEO content to capture high-intent buyers",
    }
    opportunities.append({"point": opp_by_industry.get(label, opp_by_industry["general"]),
                          "source": "Industry analysis", "confidence": "Medium"})
    if market:
        opportunities.append({"point": f"Public market chatter to leverage: {market[:140].rstrip()}…",
                              "source": "Public web scrape", "confidence": "Medium"})
    opportunities.append({"point": "Partnerships / channel alliances to reach customers beyond current footprint",
                          "source": "Strategic analysis", "confidence": "Medium"})
    opportunities.append({"point": "Hire publicly for scarce skills to signal growth and attract talent",
                          "source": "Talent market", "confidence": "Low"})

    threat_by_industry = {
        "engineering": "Competition from larger national/global engineering consultancies",
        "software": "Price pressure from global IT majors and low-cost offshore rivals",
        "manufacturing": "Input-cost volatility and import competition",
        "healthcare": "Regulatory compliance and reputation risk around patient outcomes",
        "ecommerce": "Heavy discounting and ad-cost inflation from marketplace giants",
        "education": "High CAC and trust scrutiny in consumer education brands",
        "logistics": "Fuel costs and last-mile competition compress margins",
        "professional_services": "Client consolidation and in-housing of advisory work",
        "general": "Larger competitors with stronger brand and distribution",
    }
    threats = [
        {"point": threat_by_industry.get(label, threat_by_industry["general"]),
         "source": "Industry analysis", "confidence": "High"},
        {"point": "Talent competition for specialized roles increases wage and retention pressure",
         "source": "Workforce analysis", "confidence": "Medium"},
        {"point": "Negative reviews or project issues can spread quickly on public platforms",
         "source": "Reputational risk", "confidence": "Medium"},
        {"point": "Macro slowdown reducing discretionary / capex spend among target customers",
         "source": "Macro risk", "confidence": "Medium"},
    ]
    return {
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:5],
        "opportunities": opportunities[:5],
        "threats": threats[:5],
    }


def _extract_competitors(company_name: str, intel: dict, scraped: dict = None) -> list:
    """
    Do NOT invent cross-domain peers.
    Return empty here — LLM analysis + LLM-as-judge supply domain-specific competitors.
    Keep a light search only for citation URLs.
    """
    scraped = scraped or {}
    for q in [f'"{company_name}" competitors', f'"{company_name}" vs alternatives']:
        for r in _ddg_search(q, max_results=3):
            href = r.get("href") or ""
            if href:
                intel.setdefault("_source_urls", []).append({
                    "title": (r.get("title") or "")[:80], "url": href, "category": "Competitors",
                })
        time.sleep(0.05)
    return []


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
        if "not publicly" in str(src).lower():
            src = "Analysis"
        fixed.append({"point": str(pt), "source": str(src), "confidence": str(conf)})
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


def _apply_llm_judge(report: dict, scraped: dict, company_name: str, url: str) -> dict:
    """Final confidence gate — LLM judge sanitizes the report before UI sees it."""
    from backend.services import llm_judge

    domain = urlparse(url).netloc.replace("www.", "")
    offerings = []
    for o in ((report.get("products_services") or {}).get("primary_offerings") or [])[:6]:
        if isinstance(o, dict):
            offerings.append(o.get("item") or o.get("value") or "")
        else:
            offerings.append(str(o))
    offerings_hint = ", ".join(x for x in offerings if x) or (scraped.get("description") or "")[:300]

    verdict = llm_judge.judge_research_report(
        website_url=url,
        domain=domain,
        brand_name=company_name,
        site_excerpt=(scraped.get("about_text") or scraped.get("homepage_text") or "")[:1400],
        offerings_hint=offerings_hint,
        report=report,
    )
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

    # Competitors: judge list only (domain-specific). Drop Low-confidence generics.
    judged_comps = []
    brand_l = company_name.lower()
    for c in verdict.get("competitors") or []:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if name.lower() == brand_l or brand_l in name.lower() or name.lower() in brand_l:
            continue
        conf = str(c.get("confidence") or "Medium")
        if conf.lower() == "low":
            continue
        judged_comps.append({
            "name": name,
            "description": c.get("description") or "",
            "strengths": c.get("strengths") or "",
            "weaknesses": c.get("weaknesses") or "",
            "threat_level": c.get("threat_level") or "Medium",
            "source": c.get("source") or "Judge-validated",
            "confidence": conf if conf in ("High", "Medium") else "Medium",
        })
    if judged_comps:
        report["competitors"] = judged_comps[:6]

    # Leadership / registry gates — no CIN/MCA; keep source-faithful leadership
    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": "Public web research — leadership from company website, Wikipedia, and reputable sources only.",
        "entity_scope": "none",
        "directors": [],
        "cin": "",
    }
    report["leadership_team"] = [
        l for l in (report.get("leadership_team") or [])
        if isinstance(l, dict)
        and l.get("name")
        and "zauba" not in str(l.get("source") or "").lower()
        and "mca" not in str(l.get("source") or "").lower()
        and "cin" not in str(l.get("source") or "").lower()
        and not l.get("din")
    ]
    cp = report.get("company_profile") if isinstance(report.get("company_profile"), dict) else {}
    for k in ("cin", "mca_status", "authorized_capital", "paid_up_capital", "zaubacorp_url"):
        cp.pop(k, None)
    report["company_profile"] = cp

    if not verdict.get("leadership_keep", True):
        # Judge asked to drop — still keep High / Wikipedia-sourced names
        report["leadership_team"] = [
            l for l in (report.get("leadership_team") or [])
            if str(l.get("confidence") or "").lower() == "high"
            or "wikipedia" in str(l.get("source") or "").lower()
        ]

    # Strip Low-confidence / MCA-sourced people
    leaders = []
    for ldr in report.get("leadership_team") or []:
        if not isinstance(ldr, dict) or not ldr.get("name"):
            continue
        if str(ldr.get("confidence") or "").lower() == "low":
            continue
        if (
            "zauba" in str(ldr.get("source") or "").lower()
            or "mca" in str(ldr.get("source") or "").lower()
            or ldr.get("din")
        ):
            continue
        leaders.append(ldr)
    report["leadership_team"] = leaders

    # Intelligence score from judge quality
    q = int(verdict.get("quality_score") or 40)
    report["intelligence_score"] = {
        "overall": q,
        "data_completeness": min(100, q),
        "source_reliability": 85 if not verdict.get("drop_registry") else 55,
        "verified_fields_count": len(report.get("competitors") or []) + len(report.get("leadership_team") or []),
        "estimated_fields_count": 0,
        "unverified_fields_count": 0,
        "summary": verdict.get("summary")
        or "Judge-validated report — low-confidence / wrong-domain facts removed.",
    }
    report["_judge"] = {
        "quality_score": q,
        "rejected_reasons": verdict.get("rejected_reasons") or [],
        "provider": "groq",
    }
    return report


def _normalize_report(report: dict, scraped: dict, company_name: str, url: str, intel: dict) -> dict:
    """
    Fix Groq schema drift so the Streamlit tabs always get usable structures.
    Citations already work; this repairs Overview / SWOT / etc.
    """
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
            "geographic_reach": _field(
                "Global" if any(x in (wiki_sum + site_desc).lower() for x in ("worldwide", "global", "multinational"))
                else ("India" if "india" in (scraped.get("homepage_text") or "").lower() else "Not publicly available"),
                "Public sources", "Medium"),
            "key_differentiators": [],
        }
    elif isinstance(mkt, dict):
        for k in ("industry", "market_position", "geographic_reach", "market_size_tam", "growth_rate"):
            if k in mkt and not isinstance(mkt[k], dict):
                mkt[k] = _field(mkt[k])
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
        # If LLM left W/O/T empty or N/A-only, fill from heuristic
        filled = _heuristic_swot(scraped, intel, company_name)
        for key in ("strengths", "weaknesses", "opportunities", "threats"):
            existing = swot.get(key) or []
            if len(existing) < 3:
                pad = [p for p in filled[key] if p["point"] not in {e["point"] for e in existing}]
                swot[key] = (existing + pad)[:5]
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
    # Enrich news from scraped pages if empty
    if len(report.get("recent_news") or []) < 2:
        news_items = []
        for page in intel.get("_scraped_pages") or []:
            if "news" in (page.get("category") or "").lower() or "economictimes" in (page.get("domain") or ""):
                news_items.append({
                    "title": page.get("title") or page.get("domain"),
                    "date": "",
                    "source": page.get("domain"),
                    "source_url": page.get("url"),
                    "summary": (page.get("text") or "")[:220],
                    "sentiment": "Neutral",
                    "confidence": "Medium",
                })
        if not news_items:
            for s in (intel.get("_source_urls") or [])[:5]:
                if "news" in (s.get("category") or "").lower() or "News" in (s.get("category") or ""):
                    news_items.append({
                        "title": s.get("title") or s.get("url"),
                        "date": "",
                        "source": urlparse(s.get("url","")).netloc.replace("www.",""),
                        "source_url": s.get("url"),
                        "summary": "Discovered via public web search — open source for full article.",
                        "sentiment": "Neutral",
                        "confidence": "Low",
                    })
        report["recent_news"] = (report.get("recent_news") or []) + news_items
        report["recent_news"] = report["recent_news"][:6]

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
            "general": ["Case Studies", "Expertise", "Company Culture", "Industry Insights"],
        }
        ideas = {
            "engineering": [f"Before/after design stories from {name}", "Site visit reels", "Client testimonial carousels"],
            "software": [f"Feature demos for {name}", "Customer ROI breakdowns", "Founder/engineering AMAs"],
            "healthcare": ["Doctor explainer shorts", "Patient journey carousels", "Facility tour reels"],
            "ecommerce": ["Unboxing / styling content", "UGC customer looks", "Behind-the-scenes ops"],
            "education": ["Alumni success stories", "Day-in-the-life reels", "Exam tip carousels"],
            "general": [f"Customer success stories from {name}", "Team culture reels", "Myth-busting industry posts"],
        }
        report["content_strategy"] = {
            "brand_voice": f"Professional, clear voice for {name}",
            "content_pillars": pillars.get(label, pillars["general"]),
            "viral_content_ideas": ideas.get(label, ideas["general"]),
            "top_hashtags": [f"#{name.replace(' ', '')[:20]}", "#Business", "#India", "#Growth", "#Innovation"],
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
    completeness = min(92, 35 + n_pages * 3 + n_contacts * 4 + n_comps * 3 + min(n_swot, 12) * 2)
    computed_overall = min(90, completeness + 5)
    summary = sc.get("summary") or ""
    if not summary or _is_illogical_text(summary):
        summary = f"Multi-source report for {company_name} from website + {n_pages} public sites."
    report["intelligence_score"] = {
        "overall": _score_to_int(sc.get("overall"), computed_overall),
        "data_completeness": _score_to_int(sc.get("data_completeness"), completeness),
        "source_reliability": _score_to_int(
            sc.get("source_reliability"),
            80 if n_pages >= 2 else (70 if n_pages else 50),
        ),
        "verified_fields_count": int(sc.get("verified_fields_count") or (n_contacts + n_pages + n_comps)),
        "estimated_fields_count": int(sc.get("estimated_fields_count") or max(0, n_swot // 2)),
        "unverified_fields_count": int(sc.get("unverified_fields_count") or 0),
        "summary": summary,
    }

    # ── risk / financial ─────────────────────────────────────────────
    def _default_risks(label: str) -> dict:
        reg = {
            "engineering": "Construction/safety compliance and municipal approval delays",
            "software": "Data protection / IT Act compliance and client security audits",
            "healthcare": "Clinical / patient-data regulatory compliance requirements",
            "manufacturing": "Factory safety, pollution, and labour compliance obligations",
            "ecommerce": "Consumer protection and marketplace listing compliance",
            "education": "Advertising / disclosure rules for education brands",
            "logistics": "Transport permits and labour compliance across states",
            "professional_services": "Professional licensing and client confidentiality rules",
            "general": "Sector-specific licensing and compliance obligations",
        }
        return {
            "overall_risk_level": "Medium",
            "competitive_risks": [
                {"risk": "Peer firms and larger brands competing for the same customers",
                 "source": "Industry analysis", "confidence": "High"},
            ],
            "regulatory_risks": [
                {"risk": reg.get(label, reg["general"]),
                 "source": "Industry analysis", "confidence": "Medium"},
            ],
            "operational_risks": [
                {"risk": "Key-person dependency and specialized talent retention",
                 "source": "Workforce analysis", "confidence": "Medium"},
            ],
            "reputational_risks": [
                {"risk": "Service/quality issues can spread quickly via public reviews/news",
                 "source": "Reputational analysis", "confidence": "Medium"},
            ],
        }

    industry_label = _industry_context(scraped, intel)["label"]
    if _looks_empty(report.get("risk_assessment")):
        report["risk_assessment"] = _default_risks(industry_label)
    else:
        risk = report.get("risk_assessment") or {}
        rl = risk.get("overall_risk_level")
        if isinstance(rl, dict):
            risk["overall_risk_level"] = rl.get("value") or "Medium"
        elif not rl:
            risk["overall_risk_level"] = "Medium"
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
        report["financial_data"] = {
            "authorized_capital": _field(zauba.get("Authorized Capital") or "Not publicly available", "ZaubaCorp", "High"),
            "paid_up_capital": _field(zauba.get("Paid Up Capital") or "Not publicly available", "ZaubaCorp", "High"),
            "revenue_estimate": _field(
                rev_match.group(0) if rev_match else "Not disclosed in public scrapes",
                "Public web scrape" if rev_match else "Public web", "Medium" if rev_match else "Low"),
            "funding_stage": _field(
                "Private limited (MCA)" if zauba else "Not publicly available",
                "ZaubaCorp" if zauba else "Public web", "High" if zauba else "Low"),
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
                "Not disclosed in public scrapes — check MCA filings / Tofler for private cos",
                "Public web", "Low")
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


def _fetch_hiring_signals(company_name: str, domain: str, careers_text: str = "") -> list:
    """
    Discover open roles from LinkedIn Jobs, Naukri, and careers page snippets.
    Returns structured hiring_signals with source URLs for citations.
    Fast mode: careers page only (no multi-query DDG + no LLM consolidate).
    """
    signals = []
    seen_urls = set()

    role_patterns = [
        r"(senior|lead|principal|staff|junior|associate)?\s*"
        r"([A-Za-z][A-Za-z\s/&\-]{3,40}?)\s*(engineer|developer|architect|manager|analyst|designer|consultant|specialist|lead|head)",
        r"([A-Za-z][A-Za-z\s/&\-]{3,50}?)\s*-\s*(?:\d+\s*)?(?:open|vacancies|positions)",
    ]

    def _add(role: str, url: str, platform: str, title: str = "", snippet: str = ""):
        role = re.sub(r"\s+", " ", role).strip(" -|,")
        if not role or len(role) < 4 or len(role) > 80:
            return
        if url in seen_urls:
            return
        seen_urls.add(url)
        count = 1
        cm = re.search(r"(\d+)\s*(?:open|vacanc|position|role)", snippet or title, re.I)
        if cm:
            count = min(int(cm.group(1)), 20)
        signals.append({
            "role": role.title() if role.islower() else role,
            "count": count,
            "platform": platform,
            "source_url": url,
            "source_title": title or f"{platform} — {role}",
            "snippet": (snippet or "")[:200],
        })

    # Parse careers page text for roles (always — free/fast)
    if careers_text:
        for line in re.split(r"[\n•|]", careers_text):
            line = line.strip()
            if len(line) < 8 or len(line) > 100:
                continue
            if re.search(r"(engineer|developer|manager|designer|architect|analyst|consultant|lead|head of)", line, re.I):
                _add(line, f"https://{domain}/careers", "Careers Page", line, careers_text[:200])

    if RESEARCH_SKIP_HIRING_SEARCH:
        print("[Research] Hiring web-search skipped (fast mode)")
        return signals[:8]

    queries = [
        (f'site:linkedin.com/jobs "{company_name}"', "LinkedIn"),
        (f"site:naukri.com {company_name} jobs", "Naukri"),
        (f"{company_name} careers open positions", "Web"),
    ]

    for query, platform in queries:
        results = _ddg_search(query, max_results=4)
        for r in results:
            href = r.get("href", "")
            title = r.get("title", "")
            body = r.get("body", "")
            if not href.startswith("http"):
                continue
            hl = href.lower()
            if platform == "LinkedIn" and "linkedin.com" not in hl:
                continue
            if platform == "Naukri" and "naukri.com" not in hl:
                continue
            role = title
            for pat in [
                r"^(.+?)\s+at\s+",
                r"^(.+?)\s*[-–|]\s*",
                r"^(.+?)\s+hiring",
            ]:
                m = re.search(pat, title, re.I)
                if m:
                    role = m.group(1).strip()
                    break
            if len(role) < 5:
                for pat in role_patterns:
                    m = re.search(pat, title + " " + body, re.I)
                    if m:
                        role = m.group(0).strip()
                        break
            _add(role, href, platform, title, body)

    # No LLM consolidate in fast path; deep mode keeps heuristic list only for speed
    return signals[:15]


def _ai_conclusion_from_hiring(company_name: str, hiring: list, report: dict) -> dict:
    """Generate AI conclusion and signal tags from hiring + report context."""
    if not hiring:
        return {"ai_conclusion": "", "signals_used": []}
    try:
        co = report.get("company_profile") or {}
        prompt = f"""Based on these hiring signals for {company_name}, write a one-sentence AI conclusion about what project/initiative they are likely building.

COMPANY: {company_name}
INDUSTRY: {co.get('industry', '')}
HIRING:
{json.dumps(hiring[:10], indent=2)}

Return ONLY JSON: {{"ai_conclusion": "one compelling sentence", "signals_used": ["tag1", "tag2"]}}"""
        raw = llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            json_mode=True,
        )
        return json.loads(raw)
    except Exception:
        tags = [f"{h.get('count', 1)}x {h.get('role', '')}" for h in hiring[:4]]
        return {
            "ai_conclusion": f"{company_name} is actively hiring for {', '.join(h.get('role','') for h in hiring[:3])} — signals point to a current growth or platform initiative.",
            "signals_used": tags,
        }


def run(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    domain = urlparse(url).netloc.replace("www.", "")
    t_all = time.time()

    print(f"\n[Research] ====== Deep Intelligence: {url} ======")
    print(f"[Research] FAST={RESEARCH_FAST} SKIP_JUDGE={RESEARCH_SKIP_JUDGE} "
          f"SKIP_HIRING_SEARCH={RESEARCH_SKIP_HIRING_SEARCH}")

    print("[Research] Phase 1: Scraping website + sub-pages...")
    t0 = time.time()
    scraped = _scrape_website(url)
    print(f"[Research] Phase 1 done in {time.time()-t0:.1f}s")

    title = scraped.get("title", "")
    company_name = re.split(r"[|\-—–:]", title)[0].strip() if title else _brand_from_domain(domain)
    if len(company_name) > 48:
        company_name = _brand_from_domain(domain)
    company_name = _anchor_company_name(company_name, domain, scraped)
    if scraped.get("preferred_display_name"):
        company_name = _anchor_company_name(scraped["preferred_display_name"], domain, scraped)

    print(f"[Research] Phase 2: Intelligence sweep for '{company_name}'...")
    t0 = time.time()
    intel = _collect_intelligence(company_name, domain)
    print(f"[Research] Phase 2 done in {time.time()-t0:.1f}s")

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

    # Fix Groq schema drift so Overview / SWOT / etc. always render
    report = _normalize_report(report, scraped, company_name, url, intel)

    # Leadership from Wikipedia + website + public snippets (source-faithful, never invent)
    extracted = _collect_leadership(company_name, domain, scraped, intel)
    scrape_blob = " ".join([
        scraped.get("wikipedia_text") or "",
        scraped.get("leadership_text") or "",
        scraped.get("about_text") or "",
        scraped.get("homepage_text") or "",
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
        # Keep LLM person only if name appears in scraped sources (faithful)
        if name.lower() in scrape_blob:
            llm_kept.append({
                "name": name,
                "role": l.get("role") or "Leadership",
                "source": l.get("source") or "Public web",
                "confidence": l.get("confidence") or "Medium",
                "background": l.get("background") or "",
            })
    merged_leaders, seen_n = [], set()
    for l in extracted + llm_kept:
        key = (l.get("name") or "").lower()
        if not key or key in seen_n:
            continue
        seen_n.add(key)
        merged_leaders.append(l)
    report["leadership_team"] = merged_leaders[:8]

    # No CIN / MCA — public research only
    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": "Public web research — leadership from company website, Wikipedia, and reputable sources only.",
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

    # LLM-as-judge final gate — optional in fast mode (saves 15–40s)
    if RESEARCH_SKIP_JUDGE:
        print("[Research] Phase 3b: LLM judge skipped (fast mode)")
        # Still drop MCA/junk leadership + illogical market position
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
        print("[Research] Phase 3b: LLM-as-judge (Groq) validating report...")
        report = _apply_llm_judge(report, scraped, company_name, url)
        if isinstance(report.get("company_profile"), dict) and report["company_profile"].get("name"):
            company_name = _anchor_company_name(report["company_profile"]["name"], domain, scraped)
            report["company_profile"]["name"] = company_name

    # After judge: re-assert no CIN + keep source-extracted leadership
    report["registry_intelligence"] = {
        "source": "disabled",
        "confidence": "Low",
        "message": "Public web research — leadership from company website, Wikipedia, and reputable sources only.",
        "entity_scope": "none",
        "directors": [],
        "cin": "",
    }
    # Re-merge leadership if judge wiped it; never reintroduce MCA/CIN people
    post_leaders = [
        l for l in (report.get("leadership_team") or [])
        if isinstance(l, dict)
        and l.get("name")
        and "zauba" not in str(l.get("source") or "").lower()
        and "mca" not in str(l.get("source") or "").lower()
        and "cin" not in str(l.get("source") or "").lower()
        and not l.get("din")
    ]
    if not post_leaders and merged_leaders:
        post_leaders = merged_leaders
    elif merged_leaders:
        # Prefer extracted names; keep judge-approved extras that appear in scrape
        seen_n = {(l.get("name") or "").lower() for l in merged_leaders}
        for l in post_leaders:
            key = (l.get("name") or "").lower()
            if key and key not in seen_n and key in scrape_blob:
                merged_leaders.append(l)
                seen_n.add(key)
        post_leaders = merged_leaders
    report["leadership_team"] = post_leaders[:8]
    if isinstance(report.get("company_profile"), dict):
        for k in ("cin", "mca_status", "authorized_capital", "paid_up_capital", "zaubacorp_url"):
            report["company_profile"].pop(k, None)

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

    # Hiring signals (lighter / faster — no second LLM call)
    print("[Research] Phase 4: Fetching hiring signals (LinkedIn/Naukri)...")
    t0 = time.time()
    careers_text = scraped.get("careers_text") or ""
    hiring = _fetch_hiring_signals(company_name, domain, careers_text)
    print(f"[Research] Phase 4 done in {time.time()-t0:.1f}s")
    # Drop illogical duplicate "1 open" noise — keep unique roles only
    uniq_hire, seen_roles = [], set()
    for h in hiring or []:
        role = (h.get("role") or "").strip().lower()
        if not role or role in seen_roles:
            continue
        seen_roles.add(role)
        uniq_hire.append(h)
    report["hiring_signals"] = uniq_hire[:8]
    if uniq_hire:
        top = ", ".join((h.get("role") or "")[:40] for h in uniq_hire[:3])
        report["ai_conclusion"] = (
            f"{company_name} shows public hiring activity related to: {top}."
        )
        report["signals_used"] = [h.get("role") for h in uniq_hire[:4] if h.get("role")]
    else:
        report["ai_conclusion"] = f"No confident public hiring signals found for {company_name}."
        report["signals_used"] = []

    citations = []
    seen_urls = set()

    # also skip discovery of zauba in _add_cite helper when disabled
    def _add_cite(title, cite_url, category="Web"):
        if not cite_url or not str(cite_url).startswith("http"):
            return
        low = str(cite_url).lower()
        if (not ENABLE_ZAUBACORP) and (not scraped.get("cin_verified")) and "zaubacorp.com" in low:
            return
        # Never cite ChatGPT / AI chat login walls as sources
        if any(x in low for x in (
            "chatgpt.com", "chat.openai.com", "openai.com/chat",
            "accounts.google", "login.microsoftonline",
        )):
            return
        if cite_url in seen_urls:
            return
        seen_urls.add(cite_url)
        try:
            d = urlparse(cite_url).netloc.replace("www.", "").lower()
        except Exception:
            return
        if not d:
            return
        citations.append({
            "title": title or d,
            "url": cite_url,
            "domain": d,
            "category": category,
            "favicon": f"https://www.google.com/s2/favicons?domain={d}&sz=64",
        })

    _add_cite(company_name + " Website", url, "Company Website")
    if scraped.get("wikipedia_url"):
        _add_cite("Wikipedia", scraped["wikipedia_url"], "Wikipedia")
    elif scraped.get("wikipedia_text"):
        _add_cite(
            "Wikipedia",
            f"https://en.wikipedia.org/wiki/{company_name.replace(' ', '_')}",
            "Wikipedia",
        )
    for cp in (scraped.get("contact_data") or {}).get("source_pages", []):
        _add_cite("Contact / Footer", cp, "Contact")
    for sl in scraped.get("social_links", [])[:8]:
        _add_cite(urlparse(sl).netloc.replace("www.", ""), sl, "Social Media")
    # Citations = sites we actually visited/scraped first, then discovery URLs
    for page in intel.get("_scraped_pages") or []:
        page_url = page.get("url") or ""
        if "zaubacorp.com" in page_url.lower():
            continue
        _add_cite(page.get("title") or page.get("domain", ""), page_url, page.get("category", "Public Web"))
    for s in intel.get("_source_urls", []):
        s_url = s.get("url") or ""
        if "zaubacorp.com" in s_url.lower():
            continue
        _add_cite(s.get("title", ""), s_url, s.get("category", "Search"))
    for n in (report.get("recent_news") or []):
        if isinstance(n, dict) and n.get("source_url"):
            _add_cite(n.get("title") or n.get("source", ""), n["source_url"], "News")
    _add_cite("LinkedIn Search",
              f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}",
              "LinkedIn")
    _add_cite("Google News",
              f"https://news.google.com/search?q={company_name.replace(' ', '+')}",
              "News")
    for h in hiring:
        if h.get("source_url"):
            _add_cite(
                h.get("source_title") or h.get("role", "Job Posting"),
                h["source_url"],
                h.get("platform", "Hiring"),
            )

    # Boost completeness when leadership / contacts / products present
    score = report.get("intelligence_score") if isinstance(report.get("intelligence_score"), dict) else {}
    completeness = int(score.get("data_completeness") or score.get("overall") or 40)
    if report.get("leadership_team"):
        completeness = min(100, completeness + 25)
    if merged_emails or merged_phones:
        completeness = min(100, completeness + 10)
    if (report.get("competitors") or []):
        completeness = min(100, completeness + 5)
    overall = int(score.get("overall") or completeness)
    if report.get("leadership_team"):
        overall = max(overall, min(100, overall + 10))
    report["intelligence_score"] = {
        "overall": overall,
        "data_completeness": completeness,
        "source_reliability": int(score.get("source_reliability") or 60),
        "verified_fields_count": (
            len(report.get("competitors") or [])
            + len(report.get("leadership_team") or [])
            + len(merged_emails)
            + len(merged_phones)
        ),
        "estimated_fields_count": score.get("estimated_fields_count") or 0,
        "unverified_fields_count": score.get("unverified_fields_count") or 0,
        "summary": score.get("summary")
        or "Public-web research — facts tied to scraped sources only.",
    }

    report["_meta"] = {
        "queried_url": url,
        "company_name": company_name,
        "domain": domain,
        "scrape_blocked": bool(scraped.get("_scrape_blocked")),
        "cin_verified": False,
        "verified_cin": "",
        "social_links": scraped.get("social_links", []),
        "model_used": MODEL,
        "sources_checked": [
            "Company Website + Footer",
            "Wikipedia (leadership / company facts)",
            "MCP Search across LinkedIn/Crunchbase/OpenCorporates/News/Reviews/B2B catalogs",
            "MCP Scrape: visited & scraped each public page",
            "Social Media", "LinkedIn", "Google News",
        ],
        "mcp_sites_scraped": [p.get("domain") for p in (intel.get("_scraped_pages") or [])],
        "citations": citations[:20],
        "citation_count": min(len(citations), 20),
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
        "elapsed_seconds": round(time.time() - t_all, 1),
        "fast_mode": RESEARCH_FAST,
    }

    print(f"[Research] ====== Complete in {time.time()-t_all:.1f}s: contacts={len(cd.get('emails', []))}e/"
          f"{len(cd.get('phones', []))}p citations={len(citations)} "
          f"leadership={len(report.get('leadership_team') or [])} ======\n")
    return report
