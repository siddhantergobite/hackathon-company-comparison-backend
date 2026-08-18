"""Strict ground-truth audit — catch WRONG results, not just empty gaps."""
from __future__ import annotations

import json
import time
import urllib.request

API = "http://127.0.0.1:8765"


def post(path: str, body: dict, timeout: int = 600) -> dict:
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


def audit(url: str, expect: dict) -> dict:
    r = post("/api/company-research", {"url": url})
    cp = r.get("company_profile") or {}
    name = V(cp.get("name")) or (r.get("_meta") or {}).get("company_name") or ""
    desc = V(cp.get("description")) or ""
    ind = V(cp.get("industry"))
    mp = V((r.get("market_analysis") or {}).get("market_position"))
    comps = [c.get("name", "") for c in (r.get("competitors") or []) if isinstance(c, dict)]
    leaders = [l.get("name", "") for l in (r.get("leadership_team") or []) if isinstance(l, dict)]
    reg = r.get("registry_intelligence") or {}
    cites = (r.get("_meta") or {}).get("citations") or []
    swot = r.get("swot_analysis") or {}
    prod = r.get("products_services") or {}
    offs = []
    for o in prod.get("primary_offerings") or []:
        if isinstance(o, dict):
            offs.append(V(o))
        elif isinstance(o, str):
            offs.append(o)

    fails, warns, passes = [], [], []

    if expect["brand"].lower() not in name.lower():
        fails.append(f"WRONG BRAND: got {name!r}")
    else:
        passes.append(f"brand OK: {name}")

    for bad in expect.get("forbidden_names", []):
        if bad.lower() in name.lower():
            fails.append(f"wrong entity name contains {bad}")

    if reg.get("cin") or any("zaubacorp.com" in str(c.get("url", "")).lower() for c in cites):
        fails.append("Zauba still leaking into registry/citations")
    else:
        passes.append("Zauba off")

    if any(
        isinstance(l, dict) and l.get("din")
        for l in (r.get("leadership_team") or [])
    ):
        fails.append("DIN directors present (wrong for global mode)")
    else:
        passes.append("no DIN directors")

    cl = " ".join(comps).lower()
    hit = sum(1 for t in expect.get("competitor_must_any", []) if t.lower() in cl)
    if hit < expect.get("competitor_min_hits", 1):
        fails.append(f"competitors off-domain: {comps}")
    else:
        passes.append(f"competitors OK: {comps[:5]}")

    for bad in expect.get("competitor_forbid", []):
        if any(bad.lower() in c.lower() for c in comps):
            fails.append(f"forbidden competitor {bad} in {comps}")

    text = (desc + " " + mp + " " + " ".join(offs) + " " + ind).lower()
    kw_hit = sum(1 for k in expect.get("keywords_any", []) if k.lower() in text)
    if kw_hit < expect.get("keyword_min", 1):
        fails.append(
            f"product/market text weak/wrong. desc={desc[:120]!r} mp={mp[:120]!r} offs={offs[:4]}"
        )
    else:
        passes.append(f"product/market keywords hit={kw_hit}")

    for junk in ("login", "sign in", "cookie policy", "keka", "password"):
        if junk in mp.lower() or junk in desc.lower():
            fails.append(f"junk text: {junk}")

    for bad in expect.get("forbidden_leaders", []):
        if any(bad.lower() in str(x).lower() for x in leaders):
            fails.append(f"wrong leader {bad}")

    if leaders:
        warns.append(f"leadership listed (manual verify): {leaders}")
    else:
        passes.append("leadership empty (safe — no invented people)")

    # Soft competitor quality: flag stretch peers but do not fail hard alone
    for stretch in expect.get("competitor_stretch_warn", []):
        if any(stretch.lower() in c.lower() for c in comps):
            warns.append(f"stretch competitor (not core peer): {stretch}")

    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        if not (swot.get(k) or []):
            warns.append(f"SWOT {k} empty")

    # Numeric claims with High confidence but no source domain — soft warn
    for field in ("employees", "employee_count", "founded", "annual_revenue"):
        f = cp.get(field)
        if isinstance(f, dict) and str(f.get("confidence", "")).lower() == "high":
            src = str(f.get("source") or "")
            if not src or src.lower() in ("n/a", "website", "public web"):
                warns.append(f"{field} High confidence with weak source: {f}")

    return {
        "url": url,
        "name": name,
        "industry": ind,
        "offerings": offs[:6],
        "competitors": comps[:6],
        "leaders": leaders[:6],
        "market_position": mp[:220],
        "description": desc[:220],
        "score": (r.get("intelligence_score") or {}).get("overall"),
        "PASS_NO_WRONG": len(fails) == 0,
        "fails": fails,
        "warns": warns,
        "passes": passes,
    }


def main():
    time.sleep(1)
    cases = [
        (
            "https://buffer.com",
            {
                "brand": "Buffer",
                "forbidden_names": ["TCS E-Serve", "Microsoft Corporation (India)"],
                "competitor_must_any": [
                    "hootsuite",
                    "sprout",
                    "later",
                    "socialpilot",
                    "zoho social",
                    "hubspot",
                    "metricool",
                    "publer",
                    "loomly",
                ],
                "competitor_min_hits": 1,
                "competitor_forbid": ["TCS", "Infosys", "Wipro", "Keka", "Naukri", "Ergobite"],
                "keywords_any": ["social", "schedule", "publish", "analytics", "content"],
                "keyword_min": 2,
            },
        ),
        (
            "https://www.microsoft.com",
            {
                "brand": "Microsoft",
                "forbidden_names": ["Microsoft Corporation (India)", "E-Serve"],
                "competitor_must_any": [
                    "google",
                    "amazon",
                    "aws",
                    "apple",
                    "oracle",
                    "ibm",
                    "salesforce",
                ],
                "competitor_min_hits": 2,
                "competitor_forbid": ["Buffer", "Hootsuite", "Keka", "Ergobite"],
                "competitor_stretch_warn": ["Sony"],
                "keywords_any": [
                    "software",
                    "cloud",
                    "azure",
                    "windows",
                    "office",
                    "ai",
                    "productivity",
                ],
                "keyword_min": 2,
            },
        ),
    ]

    out = []
    for url, exp in cases:
        print("AUDITING", url, flush=True)
        res = audit(url, exp)
        out.append(res)
        print(
            json.dumps(
                {
                    "name": res["name"],
                    "PASS_NO_WRONG": res["PASS_NO_WRONG"],
                    "fails": res["fails"],
                    "warns": res["warns"],
                    "competitors": res["competitors"],
                    "score": res["score"],
                },
                indent=2,
            ),
            flush=True,
        )

    with open("ground_truth_audit.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    all_pass = all(x["PASS_NO_WRONG"] for x in out)
    print("ALL_PASS_NO_WRONG=", all_pass, flush=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
