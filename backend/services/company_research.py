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
from urllib.parse import urlparse, urljoin
import requests
from dotenv import load_dotenv
load_dotenv()

from backend.services import llm as llm_client

MODEL = llm_client.AZURE_MODEL if llm_client.azure_configured() else "llama-3.3-70b-versatile"

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
_GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "rediffmail.com", "hotmail.com", "outlook.com",
    "ymail.com", "live.com", "protonmail.com",
}
_INDIAN_CITIES = (
    "mumbai", "delhi", "kolkata", "chennai", "bangalore", "bengaluru", "pune",
    "hyderabad", "bhilwara", "jaipur", "noida", "gurgaon", "gurugram", "ahmedabad",
    "kochi", "cochin", "lucknow", "indore", "nagpur", "surat", "vadodara",
)
_MCA_CONF_HIGH = 120
_MCA_CONF_MED = 70


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
    if stem:
        queries.extend([
            f"{stem} india limited",
            f"{stem} limited",
            f"{stem} tech solutions private limited",
            stem,
        ])

    title = re.split(r"[|\-—–]", scraped.get("title") or "")[0].strip()
    generic_title = bool(re.search(
        r"\b(best|leading|top|#1|official|home|welcome|download|buy|book)\b",
        title, re.I,
    )) or len(title.split()) > 6
    if title and not generic_title:
        queries.append(title)
        queries.append(f"{title} private limited")

    return list(dict.fromkeys(q for q in queries if q and len(q.strip()) >= 3))[:10]


def _collect_zauba_candidate_urls(search_name: str) -> list[str]:
    """Collect ZaubaCorp company page URLs for a search term (no page fetch yet)."""
    candidate_urls = []

    def _collect_url(href: str):
        href = _normalize_zauba_href(href)
        if _is_zaubacorp_company_url(href) and href not in candidate_urls:
            candidate_urls.append(href)

    for q in [
        f"site:zaubacorp.com {search_name}",
        f"site:zaubacorp.com {search_name} CIN",
        f"zaubacorp {search_name}",
    ]:
        for r in _ddg_search(q, max_results=8):
            _collect_url(r.get("href", ""))

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
        except Exception:
            continue

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
    except Exception:
        pass

    return candidate_urls


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

    for q in _build_zauba_queries(signals, scraped):
        for u in _collect_zauba_candidate_urls(q)[:6]:
            _evaluate(_fetch_zaubacorp_page(u))

    if not candidates:
        print(f"[MCA] No ZaubaCorp candidates for '{signals.get('domain_stem')}'")
        return empty

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    alts = [
        {"legal_name": c["legal_name"], "score": c["score"], "url": c["url"]}
        for c in candidates[1:4]
    ]

    if best["score"] < _MCA_CONF_MED:
        print(
            f"[MCA] Rejected weak match '{best['legal_name']}' "
            f"(score {best['score']}) — {best['reason']}"
        )
        return {**empty, "alternatives": alts, "match_reason": best["reason"], "match_score": best["score"]}

    conf = "High" if best["score"] >= _MCA_CONF_HIGH else "Medium"
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
        "match_reason": best["reason"],
        "alternatives": alts,
        "entity_signals": signals,
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
        digits = re.sub(r"\D", "", num)
        if len(digits) < 10 or len(digits) > 15:
            return False
        # skip years / pin codes / GST fragments
        if digits.startswith("20") and len(digits) <= 8:
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

    # 2) Contact pages
    for path in ["/contact", "/contact-us", "/contactus", "/reach-us",
                 "/get-in-touch", "/about/contact", "/connect"]:
        try:
            resp = requests.get(origin + path, headers=HEADERS, timeout=12)
            if resp.status_code == 200 and len(resp.text) > 500:
                _parse_html(resp.text, f"Contact page ({path})")
                contact["source_pages"].append(origin + path)
                print(f"[Contact] Scraped {path}")
        except Exception:
            pass
        time.sleep(0.15)

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
        resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
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

    # ── Sub-pages ─────────────────────────────────────────────────────
    sub_pages = {
        "about_text":     ["/about", "/about-us", "/company", "/who-we-are",
                           "/investor-relations", "/investors", "/investor"],
        "products_text":  ["/products", "/services", "/solutions", "/platform"],
        "pricing_text":   ["/pricing", "/plans", "/subscription"],
        "careers_text":   ["/careers", "/jobs", "/work-with-us", "/team"],
        "leadership_text":["/leadership", "/team", "/management", "/executive-team"],
        "blog_text":      ["/blog", "/news", "/press", "/resources"],
    }
    for key, paths in sub_pages.items():
        for path in paths:
            text = _fetch_page(origin + path, timeout=12)
            if len(text) > 300:
                result[key] = text
                print(f"[Research] Scraped sub-page: {path} ({len(text)} chars)")
                break
        time.sleep(0.2)

    # ── Contact page — deep extraction from RAW HTML (footer intact) ──
    result["contact_data"] = _scrape_contact_page(origin, raw_html=_homepage_raw)
    print(f"[Research] Contact: {len(result['contact_data'].get('emails',[]))} emails, "
          f"{len(result['contact_data'].get('phones',[]))} phones")

    # ── Wikipedia ─────────────────────────────────────────────────────
    try:
        domain_name = urlparse(url).netloc.replace("www.","").split(".")[0]
        wiki_url = f"https://en.wikipedia.org/wiki/{domain_name.title()}"
        wiki_text = _fetch_page(wiki_url, timeout=10)
        if len(wiki_text) > 500:
            result["wikipedia_text"] = wiki_text[:4000]
            print(f"[Research] Wikipedia scraped: {len(wiki_text)} chars")
        else:
            result["wikipedia_text"] = ""
    except Exception:
        result["wikipedia_text"] = ""

    # ── ZaubaCorp (MCA) — entity resolution (CIN / legal name / validation) ──
    result["zaubacorp_text"] = ""
    result["zaubacorp_url"] = ""
    result["zaubacorp_structured"] = {}
    result["zauba_match_confidence"] = "Low"
    result["zauba_match_score"] = 0
    result["zauba_match_reason"] = ""
    result["zauba_alternatives"] = []
    result["entity_signals"] = {}
    try:
        mca = _resolve_mca_entity(result, url, raw_html=_homepage_raw)
        result["entity_signals"] = mca.get("entity_signals") or {}
        result["zauba_match_score"] = mca.get("match_score") or 0
        result["zauba_match_confidence"] = mca.get("match_confidence") or "Low"
        result["zauba_match_reason"] = mca.get("match_reason") or ""
        result["zauba_alternatives"] = mca.get("alternatives") or []
        if mca.get("url") and mca.get("match_confidence") != "Low":
            result["zaubacorp_text"] = mca.get("text", "")
            result["zaubacorp_url"] = mca.get("url", "")
            result["zaubacorp_structured"] = mca.get("structured") or {}
            print(f"[Research] ZaubaCorp verified: {result['zaubacorp_structured'].get('Company Name')} "
                  f"({result['zauba_match_confidence']})")
        else:
            print(f"[Research] ZaubaCorp skipped — no verified MCA entity "
                  f"(best score {result['zauba_match_score']})")
    except Exception as e:
        print(f"[ZaubaCorp] failed: {e}")

    print(f"[Research] Total website data: {sum(len(v) for v in result.values() if isinstance(v,str))} chars")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — MCP Multi-Source: Search many public sites → scrape each one
# ─────────────────────────────────────────────────────────────────────────────

def _ddg_search(query: str, max_results: int = 8) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"[Research] DDG failed for '{query}': {e}")
        return []


def _snippets(results: list, max_chars: int = 2000) -> str:
    parts = [f"[{r.get('title','')}] {r.get('body','')}" for r in results if r.get("body")]
    return " | ".join(parts)[:max_chars]


PUBLIC_SOURCE_SITES = [
    ("zaubacorp.com", "MCA / Company Registry"),
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
        digits = re.sub(r"\D", "", num)
        if len(digits) < 10 or digits in seen_p:
            continue
        seen_p.add(digits)
        phones.append({
            "number": num, "label": name, "person": name,
            "source": source_label, "confidence": "Medium", "verified": True,
        })
    for m in phone_pat.finditer(text or ""):
        num = m.group(0).strip()
        digits = re.sub(r"\D", "", num)
        if len(digits) < 10 or len(digits) > 15 or digits in seen_p:
            continue
        if not (num.startswith("+") or digits.startswith(("91", "0", "6", "7", "8", "9"))):
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
    # Prioritized queries — fewer + faster than full sweep
    site_queries = [
        f"site:zaubacorp.com {company_name}",
        f"site:tofler.in {company_name}",
        f"site:ambitionbox.com {company_name}",
        f"site:glassdoor.co.in {company_name}",
        f"site:linkedin.com/company {company_name}",
        f"site:justdial.com {company_name}",
        f"site:indiamart.com {company_name}",
        f"site:economictimes.indiatimes.com {company_name}",
        f"{company_name} {domain} contact email phone",
        f"{company_name} directors CIN India",
        f"{company_name} competitors",
        f"{company_name} news funding",
    ]
    for q in site_queries:
        for r in _ddg_search(q, max_results=3):
            href = r.get("href") or r.get("link") or ""
            if not href.startswith("http"):
                continue
            try:
                d = urlparse(href).netloc.replace("www.", "").lower()
            except Exception:
                continue
            if not d or d in seen:
                continue
            if any(x in d for x in ("google.", "youtube.com", "duckduckgo")):
                continue
            seen.add(d)
            found.append({
                "title": (r.get("title") or d)[:80],
                "url": href,
                "category": _site_category(href),
                "domain": d,
                "snippet": (r.get("body") or "")[:300],
            })
        time.sleep(0.12)
    print(f"[MCP Search] Discovered {len(found)} unique public domains")
    return found


def _mcp_scrape_sources(discovered: list, company_domain: str, max_pages: int = 12) -> list:
    """Scrape Agent — visit each public URL and extract text + contacts."""
    print(f"[MCP Scrape] Visiting up to {max_pages} public websites...")
    scraped_pages = []
    priority, rest = [], []
    for item in discovered:
        cat = item.get("category", "")
        if any(k in cat for k in ("Registry", "Reviews", "Contacts", "Financial", "Company Profile", "B2B")):
            priority.append(item)
        else:
            rest.append(item)
    for item in (priority + rest)[:max_pages]:
        url = item["url"]
        if company_domain and company_domain in (item.get("domain") or ""):
            continue
        try:
            text = _fetch_page(url, timeout=8)
            if len(text) < 200:
                print(f"[MCP Scrape] skip (thin): {item.get('domain')}")
                continue
            contacts = _extract_contacts_from_text(
                text, f"{item.get('domain')} ({item.get('category')})"
            )
            scraped_pages.append({
                "title": item.get("title", ""),
                "url": url,
                "domain": item.get("domain", ""),
                "category": item.get("category", "Public Web"),
                "snippet": item.get("snippet", ""),
                "text": text[:2500],
                "emails": contacts["emails"],
                "phones": contacts["phones"],
                "favicon": f"https://www.google.com/s2/favicons?domain={item.get('domain','')}&sz=64",
            })
            print(f"[MCP Scrape] OK {item.get('domain')} — {len(text)} chars, "
                  f"{len(contacts['emails'])}e/{len(contacts['phones'])}p")
        except Exception as e:
            print(f"[MCP Scrape] fail {item.get('domain')}: {e}")
        time.sleep(0.15)
    print(f"[MCP Scrape] Successfully scraped {len(scraped_pages)} public sites")
    return scraped_pages


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

    scraped_pages = _mcp_scrape_sources(discovered, domain, max_pages=8)
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

SYSTEM_PROMPT = """You are a senior business intelligence analyst.
Produce ACCURATE reports using ONLY the multi-source scraped data provided.
Rules:
- Never invent people, funding rounds, or exact revenue figures.
- Leadership ONLY from ZaubaCorp directors; website quotes are NOT executives.
- Cite a source domain for each fact. Output ONLY valid JSON.
- For numeric facts (revenue, funding, headcount) missing from sources => Not publicly available.
- CRITICAL: Never leave SWOT (any quadrant), competitors, or risk lists empty or as
  "Not publicly available". Infer reasoned points from website + industry + public scrapes
  and mark confidence Medium/Low when inferred."""

def _build_prompt(url, company_name, scraped, intel):
    """Compact prompt — must stay under Groq free-tier TPM (~8000 tokens)."""
    def clip(s, n=600):
        return (s or "")[:n]

    zauba = scraped.get("zaubacorp_structured") or {}
    directors = zauba.get("Directors") or []
    contact = scraped.get("contact_data") or {}

    return f"""Company: {company_name}
URL: {url}
Title: {clip(scraped.get('title'), 120)}
Description: {clip(scraped.get('description'), 300)}
Homepage: {clip(scraped.get('homepage_text'), 900)}
About: {clip(scraped.get('about_text'), 500)}
Products: {clip(scraped.get('products_text'), 500)}
Social: {', '.join((scraped.get('social_links') or [])[:6])}

ZAUBACORP MCA (verified): {clip(json.dumps(zauba, ensure_ascii=False), 800)}
Directors (use ONLY these for leadership): {clip(json.dumps(directors, ensure_ascii=False), 400)}

CONTACTS already scraped (copy into contact_intelligence, do not invent):
emails={clip(json.dumps(contact.get('emails',[])), 500)}
phones={clip(json.dumps(contact.get('phones',[])), 500)}
address={clip(contact.get('address'), 200)}

MULTI-SOURCE PUBLIC WEB SCRAPES (visited & scraped, not just search snippets):
{clip(intel.get('multi_source_digest'), 3500)}

TOPIC SNIPPETS:
competitors: {clip(intel.get('competitors_direct'), 350)}
funding: {clip(intel.get('revenue'), 250)}
employees: {clip(intel.get('employees'), 250)}
reviews: {clip(intel.get('glassdoor'), 250)}
leadership: {clip(intel.get('ceo_founder'), 250)}
news: {clip(intel.get('news_recent'), 300)}
market: {clip(intel.get('market_position'), 250)}
registry: {clip(intel.get('india_registry'), 250)}

Return ONLY compact JSON. IMPORTANT schema rules:
- company_profile: object with name, website, description; founded/etc as {{value,source,confidence}}
- products_services: {{"primary_offerings":[{{"item","source","confidence"}}], "pricing_model":{{...}}, "target_customers":{{...}}}}
- market_analysis: {{"industry":{{...}},"market_position":{{...}},"geographic_reach":{{...}}}}
- swot_analysis: ALL 4 keys strengths/weaknesses/opportunities/threats as arrays of
  {{"point","source","confidence"}} — at least 3 points each. Never use "Not publicly available" as a point.
- competitors: array of at least 3 objects {{"name","description","strengths","weaknesses","threat_level","source","confidence"}}
- risk_assessment: overall_risk_level string + regulatory/competitive/operational/reputational_risks as arrays of {{"risk","source","confidence"}}
- financial_data: use ZaubaCorp capital when present; revenue only if found in scrapes
- recent_news: array of objects; intelligence_score: {{"overall","data_completeness","source_reliability","summary"}}
Do NOT wrap whole sections in a single {{value,source,confidence}} object.
Leadership ONLY from ZaubaCorp directors. Never invent exact revenue/funding numbers."""


def _analyze_with_llm(prompt: str) -> dict:
    """Analyze scraped intel with Azure OpenAI (primary) / Groq / Gemini."""
    safe_prompt = (
        "No invented people/revenue. Leadership only from ZaubaCorp directors. "
        "SWOT, competitors, and risks must always be filled (infer with Medium/Low confidence if needed). "
        "Copy scraped contacts exactly. Return ONLY valid JSON.\n\n"
        + prompt
    )
    if len(safe_prompt) > 14000:
        safe_prompt = safe_prompt[:14000]

    raw = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT[:900]},
            {"role": "user",   "content": safe_prompt},
        ],
        temperature=0.2,
        max_tokens=2500,
        json_mode=True,
    )
    print(f"[Research] LLM raw response: {len(raw)} chars")

    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.MULTILINE).strip()
    raw = re.sub(r"```$",          "", raw, flags=re.MULTILINE).strip()
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[Research] JSON parse error: {e}")
        return {"error": f"JSON parse failed: {e}", "raw": raw[:2000]}


def _analyze_with_groq(prompt: str) -> dict:
    """Back-compat alias."""
    return _analyze_with_llm(prompt)


def _baseline_report(url, company_name, scraped) -> dict:
    """Scrape-only report when Groq fails — contacts still included."""
    cd = scraped.get("contact_data") or {}
    zauba = scraped.get("zaubacorp_structured") or {}
    return {
        "company_profile": {
            "name": company_name,
            "website": url,
            "description": scraped.get("description") or (scraped.get("homepage_text") or "")[:280],
            "founded": {
                "value": zauba.get("Date of Incorporation") or "Not publicly available",
                "source": "ZaubaCorp" if zauba.get("Date of Incorporation") else "Website",
                "confidence": "High" if zauba.get("Date of Incorporation") else "Low",
            },
            "headquarters": {
                "value": zauba.get("Registered Address") or cd.get("address") or "Not publicly available",
                "source": "ZaubaCorp/Website", "confidence": "Medium",
            },
            "industry": {"value": "Not publicly available", "source": "Website", "confidence": "Low"},
            "cin": {"value": zauba.get("CIN") or "Not publicly available", "source": "ZaubaCorp", "confidence": "High"},
            "mca_status": {"value": zauba.get("Status") or "Not publicly available", "source": "ZaubaCorp", "confidence": "High"},
            "authorized_capital": {"value": zauba.get("Authorized Capital") or "Not publicly available", "source": "ZaubaCorp", "confidence": "High"},
            "paid_up_capital": {"value": zauba.get("Paid Up Capital") or "Not publicly available", "source": "ZaubaCorp", "confidence": "High"},
            "zaubacorp_url": scraped.get("zaubacorp_url") or "",
        },
        "products_services": {},
        "market_analysis": {},
        "competitors": [],
        "financial_data": {},
        "employee_insights": {},
        "leadership_team": [
            {"name": d.get("name", ""), "role": d.get("designation") or "Director",
             "source": "ZaubaCorp", "confidence": "High"}
            for d in (zauba.get("Directors") or []) if isinstance(d, dict)
        ],
        "recent_news": [],
        "social_media": {},
        "tech_stack": {"note": "Website technology only"},
        "swot_analysis": {},
        "content_strategy": {},
        "risk_assessment": {},
        "contact_intelligence": {},
        "intelligence_score": {
            "overall": 40, "data_completeness": 35, "source_reliability": 70,
            "verified_fields_count": len(cd.get("emails", [])) + len(cd.get("phones", [])),
            "estimated_fields_count": 0, "unverified_fields_count": 0,
            "summary": "Partial report from web scrape (AI analysis rate-limited or unavailable).",
        },
    }


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
    if scraped.get("zaubacorp_structured"):
        strengths.append({"point": "Registered entity with MCA/registry details publicly verifiable",
                          "source": "ZaubaCorp", "confidence": "High"})
    if not strengths:
        strengths.append({"point": f"{name} maintains an active public website and brand presence",
                          "source": "Company Website", "confidence": "Medium"})

    weaknesses = [
        {"point": "No public pricing page — buyers cannot self-serve compare costs",
         "source": "Website scan", "confidence": "High"} if not scraped.get("pricing_text") else None,
        {"point": "Thin public employee-review footprint (Glassdoor/AmbitionBox limited)",
         "source": "Public web scrape", "confidence": "Medium"} if len(reviews) < 80 else None,
        {"point": "MCA/registry page not auto-matched — filings harder to verify instantly",
         "source": "ZaubaCorp search", "confidence": "Medium"} if not scraped.get("zaubacorp_structured") else None,
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
    """Return industry-aware peer competitors (reliable for any company type)."""
    scraped = scraped or {}
    ctx = _industry_context(scraped, intel)

    # Still run a light search so citations include competitor pages
    for q in [f'"{company_name}" competitors']:
        for r in _ddg_search(q, max_results=3):
            href = r.get("href") or ""
            if href:
                intel.setdefault("_source_urls", []).append({
                    "title": (r.get("title") or "")[:80], "url": href, "category": "Competitors",
                })
        time.sleep(0.1)

    comps = []
    for name, desc, threat in ctx["peers"]:
        comps.append({
            "name": name,
            "description": desc,
            "strengths": "Scale / brand recognition in the same category",
            "weaknesses": "May compete on different segments — verify overlap",
            "threat_level": threat,
            "source": f"Industry peer set ({ctx['label']}) — verify vs {company_name}",
            "confidence": "Low",
        })
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
        if "not publicly" in str(src).lower():
            src = "Analysis"
        fixed.append({"point": str(pt), "source": str(src), "confidence": str(conf)})
    return fixed


def _offerings_from_scrape(scraped: dict) -> list:
    offerings = []
    text = (scraped.get("products_text") or scraped.get("homepage_text") or "")
    # Nav links that look like services
    skip = {"home", "about", "contact", "blog", "news", "careers", "login", "privacy"}
    for link in scraped.get("nav_links") or []:
        low = link.strip().lower()
        if not low or low in skip or len(link) > 40:
            continue
        if any(w in low for w in ("service", "design", "engineer", "consult", "solution", "project", "structural")):
            offerings.append({"item": link.strip(), "source": "Website nav", "confidence": "Medium"})
    if not offerings and text:
        # pull capitalized phrases / bullet-like chunks
        for part in re.split(r"[\n•\|]+", text)[:30]:
            part = part.strip()
            if 8 < len(part) < 60 and part[0].isupper():
                offerings.append({"item": part, "source": "Website", "confidence": "Low"})
            if len(offerings) >= 6:
                break
    return offerings[:6]


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
    if not cp.get("description"):
        cp["description"] = scraped.get("description") or (scraped.get("homepage_text") or "")[:280]
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
        # normalize offering items
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

    # ── market_analysis ──────────────────────────────────────────────
    mkt = report.get("market_analysis")
    if _looks_empty(mkt) or (isinstance(mkt, dict) and "market_position" not in mkt and "industry" not in mkt):
        desc = scraped.get("description") or ""
        report["market_analysis"] = {
            "industry": _field(desc.split(".")[0] if desc else "Not publicly available", "Website", "Medium"),
            "market_position": _field(
                (intel.get("market_position") or "")[:180] or "Not publicly available",
                "Public web scrape", "Medium"),
            "geographic_reach": _field(
                "India" if "india" in (scraped.get("homepage_text") or "").lower() else "Not publicly available",
                "Website", "Medium"),
            "key_differentiators": [],
        }
    elif isinstance(mkt, dict):
        for k in ("industry", "market_position", "geographic_reach", "market_size_tam", "growth_rate"):
            if k in mkt and not isinstance(mkt[k], dict):
                mkt[k] = _field(mkt[k])
        report["market_analysis"] = mkt

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

    # ── intelligence_score ───────────────────────────────────────────
    sc = report.get("intelligence_score")
    if not isinstance(sc, dict) or "overall" not in sc or isinstance(sc.get("value"), str):
        n_contacts = len((scraped.get("contact_data") or {}).get("emails") or [])
        n_pages = len(intel.get("_scraped_pages") or [])
        n_comps = len(report.get("competitors") or [])
        swot = report.get("swot_analysis") or {}
        n_swot = sum(len(swot.get(k) or []) for k in ("strengths", "weaknesses", "opportunities", "threats"))
        completeness = min(92, 35 + n_pages * 3 + n_contacts * 4 + n_comps * 3 + min(n_swot, 12) * 2)
        report["intelligence_score"] = {
            "overall": min(90, completeness + 5),
            "data_completeness": completeness,
            "source_reliability": 80 if n_pages >= 4 else (70 if n_pages else 50),
            "verified_fields_count": n_contacts + n_pages + n_comps,
            "estimated_fields_count": max(0, n_swot // 2),
            "unverified_fields_count": 0,
            "summary": sc.get("value") if isinstance(sc, dict) and isinstance(sc.get("value"), str)
                       else f"Multi-source report for {company_name} from website + {n_pages} public sites.",
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
    """
    signals = []
    seen_urls = set()

    queries = [
        (f'site:linkedin.com/jobs "{company_name}"', "LinkedIn"),
        (f"site:linkedin.com/jobs {company_name} hiring", "LinkedIn"),
        (f"site:naukri.com {company_name} jobs", "Naukri"),
        (f"site:naukri.com {company_name} hiring", "Naukri"),
        (f"{company_name} careers open positions", "Web"),
        (f"{company_name} {domain} hiring jobs", "Web"),
    ]

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

    for query, platform in queries:
        results = _ddg_search(query, max_results=8)
        for r in results:
            href = r.get("href", "")
            title = r.get("title", "")
            body = r.get("body", "")
            if not href.startswith("http"):
                continue
            hl = href.lower()
            if platform == "LinkedIn" and "linkedin.com/jobs" not in hl and "linkedin.com" not in hl:
                continue
            if platform == "Naukri" and "naukri.com" not in hl:
                continue
            # Extract role from title
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

    # Parse careers page text for roles
    if careers_text:
        for line in careers_text.split("\n"):
            line = line.strip()
            if len(line) < 8 or len(line) > 100:
                continue
            if re.search(r"(engineer|developer|manager|designer|architect|analyst|consultant|lead|head of)", line, re.I):
                _add(line, f"https://{domain}/careers", "Careers Page", line, careers_text[:200])

    # LLM consolidation if we have raw signals
    if signals:
        try:
            prompt = f"""Consolidate these hiring signals for {company_name} into a deduplicated list.
Merge duplicate roles. Keep source_url and platform from the best source per role.

RAW SIGNALS:
{json.dumps(signals[:20], indent=2)}

Return ONLY JSON: {{"hiring_signals": [{{"role": "...", "count": 1, "platform": "LinkedIn|Naukri|Careers Page|Web", "source_url": "...", "source_title": "...", "snippet": "..."}}]}}"""
            raw = llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                json_mode=True,
            )
            parsed = json.loads(raw)
            consolidated = parsed.get("hiring_signals") or signals
            return consolidated[:15]
        except Exception as e:
            print(f"[Research] Hiring signal LLM consolidate failed: {e}")

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

    print(f"\n[Research] ====== Deep Intelligence: {url} ======")

    print("[Research] Phase 1: Scraping website + sub-pages...")
    scraped = _scrape_website(url)

    title = scraped.get("title", "")
    company_name = re.split(r"[|\-—–]", title)[0].strip() if title else domain.split(".")[0].title()

    print(f"[Research] Phase 2: Intelligence sweep for '{company_name}'...")
    intel = _collect_intelligence(company_name, domain)

    print(f"[Research] Phase 3: Azure/LLM ({MODEL}) analysis...")
    prompt = _build_prompt(url, company_name, scraped, intel)
    try:
        report = _analyze_with_llm(prompt)
        if report.get("error") and not report.get("company_profile"):
            print("[Research] LLM parse issue — using baseline scrape report")
            report = _baseline_report(url, company_name, scraped)
    except Exception as e:
        print(f"[Research] LLM failed ({e}) — using baseline scrape report with contacts")
        report = _baseline_report(url, company_name, scraped)

    # ALWAYS inject verified contacts from company site + ALL public sites scraped
    cd = scraped.get("contact_data") or {}
    multi = intel.get("_multi_contacts") or {"emails": [], "phones": []}
    merged_emails, merged_phones = [], []
    seen_e, seen_p = set(), set()
    for e in (cd.get("emails") or []) + (multi.get("emails") or []):
        if e.get("email") and e["email"] not in seen_e:
            seen_e.add(e["email"]); merged_emails.append(e)
    # ZaubaCorp registry emails + address (MCA verified — only when entity match is confident)
    zauba_conf = scraped.get("zauba_match_confidence") or "Low"
    zauba_struct = scraped.get("zaubacorp_structured") or {}
    zauba_dirs = zauba_struct.get("Directors") or []
    zauba_text = scraped.get("zaubacorp_text") or ""
    zauba_email = zauba_struct.get("Email Address") or ""
    zauba_addr = zauba_struct.get("Registered Address") or ""

    def _director_for_email(email: str) -> str:
        local = email.split("@")[0].lower().replace(".", " ").replace("_", " ")
        first = local.split()[0] if local else ""
        for d in zauba_dirs:
            name = d.get("name", "")
            if first and first in name.lower():
                return name
        return ""

    if zauba_conf != "Low" and zauba_email and zauba_email.lower() not in seen_e:
        seen_e.add(zauba_email.lower())
        merged_emails.insert(0, {
            "email": zauba_email.lower(),
            "person_name": _director_for_email(zauba_email) or "MCA Registry Contact",
            "title": "Director / MCA Filing",
            "source": "ZaubaCorp MCA",
            "confidence": zauba_conf,
        })

    if zauba_conf != "Low":
        for em in re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", zauba_text):
            em = em.lower()
            if em not in seen_e and "zaubacorp" not in em:
                seen_e.add(em)
                merged_emails.append({
                    "email": em,
                    "person_name": _director_for_email(em) or "",
                    "title": "MCA Registry",
                    "source": "ZaubaCorp MCA",
                    "confidence": zauba_conf,
                })
    for ph in (cd.get("phones") or []) + (multi.get("phones") or []):
        key = re.sub(r"\D", "", ph.get("number", ""))
        if key and key not in seen_p:
            seen_p.add(key); merged_phones.append(ph)
    sources_used = ["Company Website (Homepage / Footer)"]
    for page in intel.get("_scraped_pages") or []:
        if page.get("emails") or page.get("phones"):
            sources_used.append(page.get("domain", "public"))
    reg_addr = cd.get("address") or zauba_addr or ""
    report["contact_intelligence"] = {
        "phones": merged_phones,
        "emails": merged_emails,
        "whatsapp": cd.get("whatsapp") or "Not publicly available",
        "toll_free": cd.get("toll_free") or "Not publicly available",
        "registered_address": reg_addr,
        "addresses": cd.get("addresses", []) or ([reg_addr] if reg_addr else []),
        "address_source": ("ZaubaCorp MCA + " if zauba_addr else "") + " + ".join(sources_used[:6]),
        "address_confidence": "High" if zauba_addr or merged_emails or merged_phones else "Low",
    }
    print(f"[Research] Injected contacts from {len(sources_used)} sources: "
          f"{len(merged_emails)} emails, {len(merged_phones)} phones")

    # Fix Groq schema drift so Overview / SWOT / etc. always render
    report = _normalize_report(report, scraped, company_name, url, intel)

    zauba_conf = scraped.get("zauba_match_confidence") or "Low"
    zauba_dirs = (scraped.get("zaubacorp_structured") or {}).get("Directors") or []
    if zauba_dirs and zauba_conf != "Low":
        report["leadership_team"] = [
            {
                "name": d.get("name", ""),
                "role": d.get("designation") or "Director",
                "din": d.get("din") or "",
                "source": "ZaubaCorp MCA",
                "confidence": zauba_conf,
                "background": f"DIN: {d['din']}" if d.get("din") else "Official MCA registry (ZaubaCorp)",
            }
            for d in zauba_dirs if isinstance(d, dict) and d.get("name")
        ]
    elif scraped.get("zaubacorp_text") and zauba_conf != "Low":
        # Parse director names from prose if table scrape missed
        dm = re.search(
            r"Directors? of .+? are\s+(.+?)(?:\.|\n|$)",
            scraped["zaubacorp_text"],
            re.I,
        )
        if dm:
            names = [n.strip() for n in re.split(r",|\band\b", dm.group(1)) if n.strip()]
            report["leadership_team"] = [
                {"name": n, "role": "Director", "source": "ZaubaCorp MCA",
                 "confidence": "High", "background": ""}
                for n in names if len(n) > 3
            ]

    # Structured MCA registry block for frontend (authentic public-source data)
    zs = scraped.get("zaubacorp_structured") or {}
    zauba_conf = scraped.get("zauba_match_confidence") or "Low"
    if scraped.get("zaubacorp_url") and zs and zauba_conf != "Low":
        report["registry_intelligence"] = {
            "source": "ZaubaCorp MCA",
            "url": scraped["zaubacorp_url"],
            "confidence": zauba_conf,
            "match_score": scraped.get("zauba_match_score") or 0,
            "match_reason": scraped.get("zauba_match_reason") or "",
            "legal_name": zs.get("Company Name") or company_name,
            "cin": zs.get("CIN") or "",
            "status": zs.get("Status") or "",
            "incorporation_date": zs.get("Date of Incorporation") or "",
            "authorized_capital": zs.get("Authorized Capital") or "",
            "paid_up_capital": zs.get("Paid Up Capital") or "",
            "registered_address": zs.get("Registered Address") or "",
            "email": zs.get("Email Address") or "",
            "roc": zs.get("RoC") or "",
            "directors": [
                {
                    "name": d.get("name", ""),
                    "din": d.get("din") or "",
                    "designation": d.get("designation") or "Director",
                    "source": "ZaubaCorp MCA",
                    "confidence": zauba_conf,
                }
                for d in (zs.get("Directors") or []) if isinstance(d, dict) and d.get("name")
            ],
        }
    elif scraped.get("zauba_alternatives"):
        report["registry_intelligence"] = {
            "source": "ZaubaCorp MCA",
            "confidence": "Low",
            "message": "Could not verify exact legal entity — directors hidden until confirmed",
            "match_score": scraped.get("zauba_match_score") or 0,
            "match_reason": scraped.get("zauba_match_reason") or "",
            "alternatives": scraped.get("zauba_alternatives") or [],
        }

    # Hiring signals from LinkedIn, Naukri, careers page
    print(f"[Research] Phase 4: Fetching hiring signals (LinkedIn/Naukri)...")
    careers_text = scraped.get("careers_text") or ""
    hiring = _fetch_hiring_signals(company_name, domain, careers_text)
    report["hiring_signals"] = hiring
    conclusion = _ai_conclusion_from_hiring(company_name, hiring, report)
    report["ai_conclusion"] = conclusion.get("ai_conclusion", "")
    report["signals_used"] = conclusion.get("signals_used", [])

    citations = []
    seen_urls = set()

    def _add_cite(title, cite_url, category="Web"):
        if not cite_url or not str(cite_url).startswith("http"):
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
    if scraped.get("zaubacorp_url"):
        _add_cite("ZaubaCorp MCA Registry", scraped["zaubacorp_url"], "MCA Registry")
    if scraped.get("wikipedia_text"):
        _add_cite("Wikipedia", f"https://en.wikipedia.org/wiki/{company_name.replace(' ', '_')}", "Wikipedia")
    for cp in (scraped.get("contact_data") or {}).get("source_pages", []):
        _add_cite("Contact / Footer", cp, "Contact")
    for sl in scraped.get("social_links", [])[:8]:
        _add_cite(urlparse(sl).netloc.replace("www.", ""), sl, "Social Media")
    # Citations = sites we actually visited/scraped first, then discovery URLs
    for page in intel.get("_scraped_pages") or []:
        _add_cite(page.get("title") or page.get("domain", ""), page.get("url", ""), page.get("category", "Public Web"))
    for s in intel.get("_source_urls", []):
        _add_cite(s.get("title", ""), s.get("url", ""), s.get("category", "Search"))
    for n in (report.get("recent_news") or []):
        if isinstance(n, dict) and n.get("source_url"):
            _add_cite(n.get("title") or n.get("source", ""), n["source_url"], "News")
    _add_cite("LinkedIn Search",
              f"https://www.linkedin.com/search/results/companies/?keywords={company_name.replace(' ', '%20')}",
              "LinkedIn")
    _add_cite("ZaubaCorp Search",
              f"https://www.zaubacorp.com/companysearchresults/{company_name.replace(' ', '%20')}",
              "MCA Registry")
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

    report["_meta"] = {
        "queried_url": url,
        "company_name": company_name,
        "domain": domain,
        "social_links": scraped.get("social_links", []),
        "model_used": MODEL,
        "sources_checked": [
            "Company Website + Footer",
            "MCP Search across ZaubaCorp/Tofler/AmbitionBox/Glassdoor/Justdial/IndiaMART/LinkedIn/News",
            "MCP Scrape: visited & scraped each public page",
            "Social Media", "LinkedIn", "Google News",
        ],
        "mcp_sites_scraped": [p.get("domain") for p in (intel.get("_scraped_pages") or [])],
        "citations": citations[:20],
        "citation_count": min(len(citations), 20),
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC"),
    }

    print(f"[Research] ====== Complete: contacts={len(cd.get('emails', []))}e/"
          f"{len(cd.get('phones', []))}p citations={len(citations)} ======\n")
    return report
