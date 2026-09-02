"""
Production readiness benchmark for /api/company-research.

Runs a mixed set of Indian and global companies against a locally running backend
and grades each report against publicly verifiable ground truth: the company name,
the headquarters city, and at least one known executive.

    python -m uvicorn backend.main:app --port 8765
    python benchmark_companies.py                 # all companies
    python benchmark_companies.py nividous zoho   # subset by key

Writes benchmark_results.json with the full per-company breakdown.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API = "http://127.0.0.1:8765/api/company-research"
TIMEOUT = 420
WORKERS = 3

# hq: any one token must appear in the headquarters field
# people: any one name must appear in leadership_team
# Founders are preferred over CEOs in the expectations because they do not churn.
COMPANIES = [
    ("nividous",     "https://nividous.com",      "Nividous",     ["mumbai"],                 ["mashruwala", "shvetal", "hester"]),
    ("ergobite",     "https://ergobite.com",      "ErgoBite",     ["pune"],                   []),
    ("zoho",         "https://www.zoho.com",      "Zoho",         ["chennai", "tenkasi", "estancia", "tamil nadu", "austin"], ["vembu"]),
    ("freshworks",   "https://www.freshworks.com", "Freshworks",  ["san mateo", "chennai", "california"], ["mathrubootham", "woodside"]),
    ("zerodha",      "https://zerodha.com",       "Zerodha",      ["bengaluru", "bangalore"], ["kamath"]),
    ("razorpay",     "https://razorpay.com",      "Razorpay",     ["bengaluru", "bangalore"], ["harshil", "shashank"]),
    ("postman",      "https://www.postman.com",   "Postman",      ["san francisco", "california"], ["asthana"]),
    ("browserstack", "https://www.browserstack.com", "BrowserStack", ["mumbai", "san francisco", "dublin"], ["ritesh", "nakul"]),
    ("chargebee",    "https://www.chargebee.com", "Chargebee",    ["chennai", "bethesda", "maryland", "san francisco"], ["krish", "subramanian"]),
    ("infosys",      "https://www.infosys.com",   "Infosys",      ["bengaluru", "bangalore"], ["parekh", "nilekani", "murthy"]),
    ("tcs",          "https://www.tcs.com",       "Tata Consultancy", ["mumbai"],             ["krithivasan", "chandrasekaran"]),
    ("wipro",        "https://www.wipro.com",     "Wipro",        ["bengaluru", "bangalore"], ["pallia", "premji"]),
    ("hcltech",      "https://www.hcltech.com",   "HCLTech",      ["noida", "delhi"],         ["vijayakumar", "malhotra", "nadar"]),
    ("techmahindra", "https://www.techmahindra.com", "Tech Mahindra", ["pune", "mumbai"],     ["joshi", "mahindra"]),
    ("ltimindtree",  "https://www.ltimindtree.com", "LTIMindtree", ["mumbai"],                ["lambu", "chatterjee"]),
    ("persistent",   "https://www.persistent.com", "Persistent",  ["pune"],                   ["kalra", "deshpande"]),
    ("mphasis",      "https://www.mphasis.com",   "Mphasis",      ["bengaluru", "bangalore"], ["rakesh"]),
    ("cyient",       "https://www.cyient.com",    "Cyient",       ["hyderabad"],              ["bodanapu", "mohan reddy"]),
    ("happiestminds", "https://www.happiestminds.com", "Happiest Minds", ["bengaluru", "bangalore"], ["soota", "anantharaju", "venkatraman"]),
    ("kpit",         "https://www.kpit.com",      "KPIT",         ["pune"],                   ["patil", "pawar"]),
    ("tataelxsi",    "https://www.tataelxsi.com", "Tata Elxsi",   ["bengaluru", "bangalore"], ["raghavan"]),
    ("quickheal",    "https://www.quickheal.co.in", "Quick Heal", ["pune"],                   ["katkar"]),
    ("notion",       "https://www.notion.so",     "Notion",       ["san francisco", "california"], ["zhao"]),
    ("atlassian",    "https://www.atlassian.com", "Atlassian",    ["sydney", "australia"],    ["cannon-brookes", "farquhar"]),
]


def _text(field):
    if isinstance(field, dict):
        return str(field.get("value") or "")
    return str(field or "")


def _missing(value: str) -> bool:
    low = (value or "").strip().lower()
    return not low or "not publicly" in low or "not available" in low or low == "unknown"


def audit(key, url, expect_name, expect_hq, expect_people):
    row = {"key": key, "url": url, "checks": {}, "problems": []}
    t0 = time.time()
    try:
        resp = requests.post(API, json={"url": url}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        row["error"] = str(e)[:200]
        row["elapsed"] = round(time.time() - t0, 1)
        row["score"] = 0
        row["problems"].append(f"request failed: {str(e)[:120]}")
        return row
    row["elapsed"] = round(time.time() - t0, 1)

    profile = data.get("company_profile") or {}
    name = _text(profile.get("name"))
    hq = _text(profile.get("headquarters"))
    leaders = [l for l in (data.get("leadership_team") or []) if isinstance(l, dict)]
    leader_blob = " ".join(f"{l.get('name','')} {l.get('role','')}" for l in leaders).lower()

    row["name"] = name
    row["headquarters"] = hq
    row["leaders"] = [f"{l.get('name')} — {l.get('role')}" for l in leaders]

    # 1) brand identity
    ok_name = bool(name) and any(
        w in name.lower() for w in expect_name.lower().split() if len(w) > 2
    )
    row["checks"]["name"] = ok_name
    if not ok_name:
        row["problems"].append(f"name mismatch: got {name!r}, expected ~{expect_name!r}")

    # 2) headquarters populated
    row["checks"]["hq_present"] = not _missing(hq)
    if _missing(hq):
        row["problems"].append("headquarters empty")

    # 3) headquarters correct
    ok_hq = any(tok in hq.lower() for tok in expect_hq) if expect_hq else True
    row["checks"]["hq_correct"] = ok_hq
    if not _missing(hq) and not ok_hq:
        row["problems"].append(f"hq wrong: got {hq!r}, expected one of {expect_hq}")

    # 4) leadership populated
    row["checks"]["leaders_present"] = bool(leaders)
    if not leaders:
        row["problems"].append("leadership empty")

    # 5) leadership matches a known executive
    ok_people = any(p in leader_blob for p in expect_people) if expect_people else bool(leaders)
    row["checks"]["leaders_correct"] = ok_people
    if leaders and expect_people and not ok_people:
        row["problems"].append(f"no expected exec found; got {row['leaders']}")

    # 6) provenance hygiene — the model must never be cited as a source.
    # Only source labels and citations are inspected; plenty of these companies
    # legitimately mention OpenAI in their own marketing copy.
    labels = [str(l.get("source") or "") for l in leaders]
    labels += [str((c or {}).get("url", "")) + " " + str((c or {}).get("title", ""))
               for c in ((data.get("_meta") or {}).get("citations") or [])]
    for section in ("company_profile", "market_analysis", "financial_data"):
        block = data.get(section)
        if isinstance(block, dict):
            labels += [str(v.get("source") or "") for v in block.values() if isinstance(v, dict)]
    src_blob = " ".join(labels).lower()
    clean_src = not any(x in src_blob for x in ("chatgpt", "openai", "as an ai", "language model", "gpt-"))
    row["checks"]["clean_sources"] = clean_src
    if not clean_src:
        row["problems"].append(f"model cited as a source: {src_blob[:160]}")

    # 7) every leader carries a source label
    labelled = all((l.get("source") or "").strip() for l in leaders) if leaders else True
    row["checks"]["leaders_sourced"] = labelled
    if not labelled:
        row["problems"].append("leadership row missing a source label")

    row["score"] = round(100 * sum(row["checks"].values()) / len(row["checks"]))
    return row


def main():
    wanted = [a.lower() for a in sys.argv[1:]]
    targets = [c for c in COMPANIES if not wanted or c[0] in wanted]
    print(f"Benchmarking {len(targets)} companies against {API}\n")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for row in pool.map(lambda c: audit(*c), targets):
            results.append(row)
            status = "PASS" if row["score"] == 100 else ("FAIL" if row["score"] < 60 else "WARN")
            print(f"[{status}] {row['key']:<14} {row['score']:>3}/100  {row['elapsed']:>6}s  "
                  f"hq={row.get('headquarters','')[:45]!r} leaders={len(row.get('leaders') or [])}")
            for p in row["problems"]:
                print(f"         - {p}")

    checks = {}
    for row in results:
        for k, v in row["checks"].items():
            checks.setdefault(k, []).append(bool(v))

    print("\n── per-check pass rate ───────────────────────────────")
    for k, vals in checks.items():
        print(f"  {k:<18} {sum(vals):>2}/{len(vals)}  ({round(100*sum(vals)/len(vals))}%)")

    avg = round(sum(r["score"] for r in results) / max(len(results), 1))
    full = sum(1 for r in results if r["score"] == 100)
    print(f"\n  overall average   {avg}/100")
    print(f"  perfect reports   {full}/{len(results)}")

    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump({"average": avg, "results": results}, f, indent=2, ensure_ascii=False)
    print("\nwrote benchmark_results.json")


if __name__ == "__main__":
    main()
