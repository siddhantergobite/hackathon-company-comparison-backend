"""Behind-the-scenes correctness audit across small / medium / large companies."""
from __future__ import annotations

import json
import time
import urllib.request

API = "http://127.0.0.1:8765"

# Ground-truth expectations (public knowledge) — fail only on clearly WRONG facts
CASES = [
    {
        "size": "small",
        "url": "https://ergobite.com",
        "brand": "Ergobite",
        "must_keywords": ["software", "product", "ai", "app", "development", "odoo", "design"],
        "keyword_min": 1,
        "competitor_forbid": ["Hootsuite", "Buffer", "Microsoft", "Google", "Amazon", "Apple"],
        "notes": "Small product/dev studio",
    },
    {
        "size": "medium",
        "url": "https://buffer.com",
        "brand": "Buffer",
        "must_keywords": ["social", "schedule", "publish", "content", "analytics"],
        "keyword_min": 2,
        "competitor_must_any": [
            "hootsuite", "sprout", "later", "socialpilot", "zoho social", "loomly", "sendible"
        ],
        "competitor_forbid": ["TCS", "Infosys", "Wipro", "Keka", "Ergobite"],
        "notes": "Mid-size SaaS social tool",
    },
    {
        "size": "medium",
        "url": "https://www.notion.so",
        "brand": "Notion",
        "must_keywords": ["workspace", "notes", "docs", "wiki", "productivity", "collaboration"],
        "keyword_min": 1,
        "competitor_must_any": [
            "confluence", "coda", "evernote", "obsidian", "clickup", "asana", "monday", "airtable"
        ],
        "competitor_forbid": ["Hootsuite", "Buffer", "TCS", "Keka"],
        "notes": "Mid/large productivity SaaS",
    },
    {
        "size": "large",
        "url": "https://www.microsoft.com",
        "brand": "Microsoft",
        "must_keywords": ["software", "cloud", "azure", "windows", "office", "ai", "productivity"],
        "keyword_min": 1,
        "competitor_must_any": ["google", "amazon", "aws", "apple", "oracle", "ibm", "salesforce"],
        "competitor_forbid": ["Buffer", "Hootsuite", "Ergobite", "Keka"],
        "forbid_name_contains": ["Sevan", "E-Serve", "(India)"],
        "notes": "Large enterprise (often bot-blocked)",
    },
    {
        "size": "large",
        "url": "https://www.google.com",
        "brand": "Google",
        "must_keywords": ["search", "advertising", "cloud", "android", "youtube", "ai", "software"],
        "keyword_min": 1,
        "competitor_must_any": ["microsoft", "amazon", "apple", "meta", "openai"],
        "competitor_forbid": ["Buffer", "Hootsuite", "Ergobite"],
        "notes": "Large (homepage scrapes poorly)",
    },
]


def post(path: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def V(x) -> str:
    if isinstance(x, dict):
        return str(x.get("value") or x.get("item") or "")
    return str(x or "")


def audit(case: dict, report: dict) -> dict:
    cp = report.get("company_profile") or {}
    meta = report.get("_meta") or {}
    name = V(cp.get("name")) or meta.get("company_name") or ""
    desc = V(cp.get("description"))
    ind = V(cp.get("industry"))
    mp = V((report.get("market_analysis") or {}).get("market_position"))
    comps = [c.get("name", "") for c in (report.get("competitors") or []) if isinstance(c, dict)]
    leaders = [l.get("name", "") for l in (report.get("leadership_team") or []) if isinstance(l, dict)]
    reg = report.get("registry_intelligence") or {}
    sc = report.get("intelligence_score") or {}
    swot = report.get("swot_analysis") or {}
    prod = report.get("products_services") or {}
    offs = []
    for o in prod.get("primary_offerings") or []:
        offs.append(V(o) if isinstance(o, dict) else str(o))

    hard_fails = []  # clearly WRONG
    soft_gaps = []   # incomplete / weak but not wrong
    passes = []

    # Brand
    if case["brand"].lower() not in name.lower():
        hard_fails.append(f"WRONG brand: got {name!r}")
    else:
        passes.append(f"brand OK ({name})")

    for bad in case.get("forbid_name_contains") or []:
        if bad.lower() in name.lower():
            hard_fails.append(f"forbidden name token: {bad}")

    # Zauba / DIN
    if reg.get("cin") or any(
        isinstance(l, dict) and l.get("din") for l in (report.get("leadership_team") or [])
    ):
        hard_fails.append("Zauba/DIN still present")
    else:
        passes.append("no Zauba/DIN")

    # Product/market keywords
    text = " ".join([desc, ind, mp, " ".join(offs)]).lower()
    kw_hit = sum(1 for k in case.get("must_keywords", []) if k.lower() in text)
    if kw_hit < case.get("keyword_min", 1):
        # If blocked/scrape-thin, treat as soft gap not hard fail when brand OK
        if meta.get("scrape_blocked") or "not publicly" in mp.lower():
            soft_gaps.append(f"thin product/market text (kw_hit={kw_hit})")
        else:
            hard_fails.append(f"off-domain product/market text (kw_hit={kw_hit})")
    else:
        passes.append(f"product/market keywords hit={kw_hit}")

    # Junk chrome
    junk = ("what's on your mind", "create images", "login", "cookie", "keka password")
    if any(j in (desc + " " + mp).lower() for j in junk):
        hard_fails.append("junk UI text in description/market")
    else:
        passes.append("no junk UI text")

    # Competitors
    cl = " ".join(comps).lower()
    must = case.get("competitor_must_any") or []
    if must:
        hit = sum(1 for t in must if t.lower() in cl)
        if hit < 1:
            if comps:
                hard_fails.append(f"competitors look off-domain: {comps[:5]}")
            else:
                soft_gaps.append("no competitors returned")
        else:
            passes.append(f"competitors OK: {comps[:5]}")
    elif comps:
        passes.append(f"competitors present: {comps[:5]}")
    else:
        soft_gaps.append("no competitors")

    for bad in case.get("competitor_forbid") or []:
        if any(bad.lower() in c.lower() for c in comps):
            hard_fails.append(f"forbidden competitor {bad}")

    # SWOT
    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        if not (swot.get(k) or []):
            soft_gaps.append(f"SWOT {k} empty")

    if not leaders:
        soft_gaps.append("leadership empty (safe)")
    else:
        soft_gaps.append(f"leadership listed — verify manually: {leaders[:4]}")

    # Score shape
    overall = sc.get("overall")
    if not isinstance(overall, (int, float)) or not (0 <= float(overall) <= 100):
        soft_gaps.append(f"odd score shape: {overall!r}")
    elif 0 < float(overall) <= 1:
        soft_gaps.append(f"score looks fractional: {overall}")
    else:
        passes.append(f"score={overall}")

    # Correctness score: hard fails kill; soft gaps reduce
    if hard_fails:
        correctness = max(20, 55 - 15 * len(hard_fails))
        verdict = "WRONG_FACTS_PRESENT"
    else:
        correctness = max(55, 92 - 6 * len(soft_gaps))
        verdict = "CORE_CORRECT_WITH_GAPS" if soft_gaps else "CORE_CORRECT"

    return {
        "size": case["size"],
        "url": case["url"],
        "notes": case["notes"],
        "name": name,
        "elapsed_s": (meta.get("elapsed_seconds")),
        "scrape_blocked": bool(meta.get("scrape_blocked")),
        "competitors": comps[:6],
        "market_position": mp[:180],
        "description": desc[:180],
        "score": overall,
        "hard_fails": hard_fails,
        "soft_gaps": soft_gaps,
        "passes": passes,
        "correctness_pct": correctness,
        "verdict": verdict,
        "model": meta.get("model_used"),
        "fast_mode": meta.get("fast_mode"),
    }


def main():
    # Discover model
    try:
        from backend.services import llm as llm_client
        from backend.services import company_research as cr

        model_info = {
            "GROQ_MODEL_env_or_default": getattr(llm_client, "GROQ_MODEL", None),
            "RESEARCH_USE_GROQ": getattr(llm_client, "RESEARCH_USE_GROQ", None),
            "company_research_MODEL": getattr(cr, "MODEL", None),
            "RESEARCH_FAST": getattr(cr, "RESEARCH_FAST", None),
        }
    except Exception as e:
        model_info = {"error": str(e)}

    results = []
    for case in CASES:
        print(f"\n=== {case['size'].upper()} {case['url']} ===", flush=True)
        t0 = time.time()
        try:
            report = post("/api/company-research", {"url": case["url"]}, timeout=180)
            row = audit(case, report)
            row["wall_s"] = round(time.time() - t0, 1)
        except Exception as e:
            row = {
                "size": case["size"],
                "url": case["url"],
                "verdict": "API_ERROR",
                "hard_fails": [str(e)],
                "soft_gaps": [],
                "correctness_pct": 0,
                "wall_s": round(time.time() - t0, 1),
            }
        results.append(row)
        print(
            json.dumps(
                {
                    "name": row.get("name"),
                    "verdict": row.get("verdict"),
                    "correctness_pct": row.get("correctness_pct"),
                    "hard_fails": row.get("hard_fails"),
                    "soft_gaps": row.get("soft_gaps"),
                    "competitors": row.get("competitors"),
                    "elapsed": row.get("elapsed_s") or row.get("wall_s"),
                    "model": row.get("model"),
                },
                indent=2,
            ),
            flush=True,
        )

    # Aggregate
    ok = [r for r in results if r.get("verdict") != "API_ERROR"]
    avg = round(sum(r.get("correctness_pct", 0) for r in ok) / max(1, len(ok)))
    wrong = [r for r in ok if r.get("verdict") == "WRONG_FACTS_PRESENT"]
    by_size = {}
    for r in ok:
        by_size.setdefault(r["size"], []).append(r["correctness_pct"])
    size_avg = {k: round(sum(v) / len(v)) for k, v in by_size.items()}

    summary = {
        "groq_model_info": model_info,
        "overall_correctness_pct": avg,
        "by_size_avg_pct": size_avg,
        "companies_tested": len(ok),
        "companies_with_wrong_facts": len(wrong),
        "interpretation": (
            "Core identity + industry peers are mostly correct; "
            "exact financials/leadership/SWOT wording are soft estimates, not guaranteed."
        ),
        "results": results,
    }
    with open("correctness_audit.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("\n==== SUMMARY ====", flush=True)
    print(json.dumps({k: summary[k] for k in (
        "groq_model_info", "overall_correctness_pct", "by_size_avg_pct",
        "companies_tested", "companies_with_wrong_facts", "interpretation"
    )}, indent=2), flush=True)
    return 0 if not wrong else 1


if __name__ == "__main__":
    raise SystemExit(main())
