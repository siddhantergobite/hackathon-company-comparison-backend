"""
Wikidata structured facts for company intelligence.

Used as a high-trust source for CURRENT executives (CEO/chair), HQ, founding year,
and revenue — only when the entity's official website (P856) matches the queried domain.
Never invent; empty result if identity cannot be verified.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
HEADERS = {
    "User-Agent": "CompanyIntelligenceCasefile/3.0 (research; local-dev)",
    "Accept": "application/json",
}

# Common currency entities
_CURRENCY = {
    "Q4917": "USD",
    "Q8142": "USD",  # United States dollar (sometimes used)
    "Q25224": "GBP",
    "Q4916": "EUR",
    "Q80524": "INR",
    "Q1104069": "INR",
    "Q25344": "CHF",
    "Q8146": "JPY",
    "Q163712": "CNY",
}

P_OFFICIAL_WEBSITE = "P856"
P_CEO = "P169"
P_CHAIR = "P488"
P_DIRECTOR = "P1037"
P_FOUNDED_BY = "P112"
P_HQ = "P159"
P_INCEPTION = "P571"
P_EMPLOYEES = "P1128"
P_REVENUE = "P2139"
P_INDUSTRY = "P452"


def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower().replace("www.", "")
        return h.split(":")[0]
    except Exception:
        return ""


def _stem(host: str) -> str:
    h = (host or "").lower().replace("www.", "")
    return (h.split(".")[0] if h else "").strip()


def _hosts_match(a: str, b: str) -> bool:
    a, b = _host(a) if "://" in (a or "") else (a or "").lower(), _host(b) if "://" in (b or "") else (b or "").lower()
    a, b = a.replace("www.", ""), b.replace("www.", "")
    if not a or not b:
        return False
    if a == b:
        return True
    # microsoft.com vs microsoft.co.in / microsoft.com.au — same stem, corporate TLD
    return _stem(a) == _stem(b) and len(_stem(a)) >= 4


def _snak_value(snak: dict) -> Any:
    dv = (snak or {}).get("datavalue") or {}
    return dv.get("value")


def _claim_entity_ids(entity: dict, pid: str, *, current_only: bool = False) -> list[str]:
    out = []
    for c in (entity.get("claims") or {}).get(pid, []) or []:
        if current_only and (c.get("qualifiers") or {}).get("P582"):
            continue  # ended role
        val = _snak_value(c.get("mainsnak") or {})
        if isinstance(val, dict) and val.get("id"):
            out.append(val["id"])
    return out


def _claim_urls(entity: dict, pid: str) -> list[str]:
    out = []
    for c in (entity.get("claims") or {}).get(pid, []) or []:
        val = _snak_value(c.get("mainsnak") or {})
        if isinstance(val, str) and val.startswith("http"):
            out.append(val)
    return out


def _claim_times(entity: dict, pid: str) -> list[str]:
    years = []
    for c in (entity.get("claims") or {}).get(pid, []) or []:
        val = _snak_value(c.get("mainsnak") or {})
        if isinstance(val, dict) and val.get("time"):
            m = re.search(r"(\d{4})", val["time"])
            if m:
                years.append(m.group(1))
    return years


def _claim_quantities(entity: dict, pid: str) -> list[dict]:
    rows = []
    for c in (entity.get("claims") or {}).get(pid, []) or []:
        val = _snak_value(c.get("mainsnak") or {})
        if not isinstance(val, dict) or "amount" not in val:
            continue
        amount = str(val.get("amount") or "").lstrip("+")
        unit = str(val.get("unit") or "")
        unit_qid = unit.rsplit("/", 1)[-1] if "wikidata.org" in unit else ""
        point = ""
        for qlist in (c.get("qualifiers") or {}).get("P585", []) or []:
            qv = _snak_value(qlist)
            if isinstance(qv, dict) and qv.get("time"):
                m = re.search(r"(\d{4})", qv["time"])
                if m:
                    point = m.group(1)
                    break
        rows.append({"amount": amount, "unit_qid": unit_qid, "year": point})
    return rows


def _labels_for(qids: list[str]) -> dict[str, str]:
    ids = [q for q in qids if q and q.startswith("Q")]
    if not ids:
        return {}
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(ids[:30]),
                "props": "labels",
                "languages": "en",
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        ents = (resp.json() or {}).get("entities") or {}
        out = {}
        for qid, ent in ents.items():
            lab = ((ent.get("labels") or {}).get("en") or {}).get("value") or ""
            if lab:
                out[qid] = lab
        return out
    except Exception as e:
        print(f"[Wikidata] label fetch failed: {e}")
        return {}


def _search_entities(name: str, limit: int = 5) -> list[str]:
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "type": "item",
                "limit": limit,
                "format": "json",
            },
            headers=HEADERS,
            timeout=6,
        )
        resp.raise_for_status()
        return [h["id"] for h in (resp.json() or {}).get("search") or [] if h.get("id")]
    except Exception as e:
        print(f"[Wikidata] search failed: {e}")
        return []


def _get_entity(qid: str) -> dict:
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|claims|sitelinks",
                "languages": "en",
                "format": "json",
            },
            headers=HEADERS,
            timeout=8,
        )
        resp.raise_for_status()
        return ((resp.json() or {}).get("entities") or {}).get(qid) or {}
    except Exception as e:
        print(f"[Wikidata] entity {qid} failed: {e}")
        return {}


def _format_revenue(row: dict) -> str:
    try:
        n = float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    cur = _CURRENCY.get(row.get("unit_qid") or "", "USD" if (row.get("unit_qid") or "").startswith("Q") else "")
    # Scale to human units
    if n >= 1_000_000_000_000:
        mag, div = "trillion", 1_000_000_000_000
    elif n >= 1_000_000_000:
        mag, div = "billion", 1_000_000_000
    elif n >= 1_000_000:
        mag, div = "million", 1_000_000
    else:
        return ""  # too small / likely not annual revenue
    val = n / div
    shown = f"{val:.2f}".rstrip("0").rstrip(".")
    year = f" ({row['year']})" if row.get("year") else ""
    prefix = f"{cur} " if cur else ""
    return f"{prefix}{shown} {mag}{year}".strip()


def lookup_company(company_name: str, domain: str, website_url: str = "") -> dict:
    """
    Return structured Wikidata facts only if official website matches domain.
    """
    empty = {
        "matched": False,
        "qid": "",
        "label": "",
        "ceo": [],
        "chair": [],
        "directors": [],
        "founders": [],
        "headquarters": "",
        "founded_year": "",
        "employees": "",
        "revenue": "",
        "industry": "",
        "source_url": "",
    }
    name = (company_name or "").strip()
    if not name or len(name) < 2:
        return empty

    candidates = _search_entities(name, limit=3)
    stem = _stem(domain)
    if not candidates and stem and stem.lower() not in name.lower():
        candidates = _search_entities(stem.title(), limit=2)

    for qid in candidates[:3]:
        ent = _get_entity(qid)
        if not ent:
            continue
        sites = _claim_urls(ent, P_OFFICIAL_WEBSITE)
        if not sites:
            continue
        if not any(_hosts_match(s, domain) or (website_url and _hosts_match(s, website_url)) for s in sites):
            continue

        ceo_ids = _claim_entity_ids(ent, P_CEO, current_only=True)
        chair_ids = _claim_entity_ids(ent, P_CHAIR, current_only=True)
        dir_ids = _claim_entity_ids(ent, P_DIRECTOR, current_only=True)
        founder_ids = _claim_entity_ids(ent, P_FOUNDED_BY)
        hq_ids = _claim_entity_ids(ent, P_HQ)
        industry_ids = _claim_entity_ids(ent, P_INDUSTRY)
        need = ceo_ids + chair_ids + dir_ids[:3] + founder_ids[:4] + hq_ids[:2] + industry_ids[:2]
        labels = _labels_for(need)

        years = _claim_times(ent, P_INCEPTION)
        emp_rows = _claim_quantities(ent, P_EMPLOYEES)
        emp = ""
        if emp_rows:
            try:
                emp = f"{int(float(emp_rows[0]['amount'])):,}"
                if emp_rows[0].get("year"):
                    emp += f" ({emp_rows[0]['year']})"
            except (TypeError, ValueError):
                emp = ""

        rev_rows = _claim_quantities(ent, P_REVENUE)
        # Prefer the most recent year
        rev_rows.sort(key=lambda r: r.get("year") or "", reverse=True)
        revenue = ""
        for r in rev_rows[:4]:
            revenue = _format_revenue(r)
            if revenue:
                break

        label = ((ent.get("labels") or {}).get("en") or {}).get("value") or name
        wiki = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title") or ""
        source = f"https://www.wikidata.org/wiki/{qid}"

        result = {
            "matched": True,
            "qid": qid,
            "label": label,
            "ceo": [labels[i] for i in ceo_ids if i in labels],
            "chair": [labels[i] for i in chair_ids if i in labels],
            "directors": [labels[i] for i in dir_ids if i in labels][:4],
            "founders": [labels[i] for i in founder_ids if i in labels][:4],
            "headquarters": ", ".join(labels[i] for i in hq_ids if i in labels),
            "founded_year": years[0] if years else "",
            "employees": emp,
            "revenue": revenue,
            "industry": ", ".join(labels[i] for i in industry_ids if i in labels),
            "wikipedia_title": wiki,
            "source_url": source,
            "official_websites": sites[:3],
        }
        print(
            f"[Wikidata] matched {label} ({qid}) ceo={result['ceo']} "
            f"hq={result['headquarters']} revenue={revenue or 'n/a'}"
        )
        return result

    print(f"[Wikidata] no official-website match for {name} / {domain}")
    return empty


def leaders_from_wikidata(wd: dict) -> list[dict]:
    """Turn Wikidata facts into leadership rows (current execs first)."""
    if not wd or not wd.get("matched"):
        return []
    src = wd.get("source_url") or "Wikidata"
    rows = []
    seen = set()

    def add(name: str, role: str, status: str, conf: str = "High"):
        key = (name or "").strip().lower()
        if not key or key in seen or len(name.split()) < 2:
            return
        seen.add(key)
        rows.append({
            "name": name.strip(),
            "role": role,
            "source": src,
            "confidence": conf,
            "background": f"Wikidata structured claim ({status})",
            "status": status,
            "is_current": status == "current",
            "provenance": "wikidata",
        })

    for n in wd.get("ceo") or []:
        add(n, "CEO", "current")
    for n in wd.get("chair") or []:
        add(n, "Chairperson", "current")
    for n in (wd.get("directors") or [])[:3]:
        add(n, "Director", "current", "Medium")
    for n in wd.get("founders") or []:
        add(n, "Founder (historical)", "historical", "High")
    return rows
