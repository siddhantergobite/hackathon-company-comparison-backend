"""Re-verify after citation cleanup: Buffer target + Microsoft Zauba-off + pitch keys."""
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


def val(x):
    if isinstance(x, dict):
        return x.get("value") or x.get("item") or ""
    return x or ""


def check_target(label: str, url: str, report: dict) -> dict:
    issues, ok = [], []
    meta = report.get("_meta") or {}
    cp = report.get("company_profile") or {}
    name = val(cp.get("name")) or meta.get("company_name") or ""
    reg = report.get("registry_intelligence") or {}
    leaders = report.get("leadership_team") or []
    comps = [
        c
        for c in (report.get("competitors") or [])
        if isinstance(c, dict) and c.get("name") and not str(c.get("name")).lower().startswith("competitor")
    ]
    ma = report.get("market_analysis") or {}
    swot = report.get("swot_analysis") or {}
    ci = report.get("contact_intelligence") or {}
    cites = meta.get("citations") or []

    if reg.get("source") != "disabled" and reg.get("cin"):
        issues.append(f"registry still active cin={reg.get('cin')}")
    else:
        ok.append("registry disabled")

    zauba_cites = [c for c in cites if "zaubacorp" in str(c.get("url") or "").lower() or "zaubacorp" in str(c.get("domain") or "").lower()]
    if zauba_cites:
        issues.append(f"zauba still in citations: {zauba_cites[:2]}")
    else:
        ok.append("no zauba citations")

    sources = " | ".join(meta.get("sources_checked") or []).lower()
    if "zaubacorp" in sources:
        issues.append("zaubacorp still listed in sources_checked")
    else:
        ok.append("sources_checked clean")

    mca_leaders = [
        l
        for l in leaders
        if isinstance(l, dict)
        and (l.get("din") or "mca" in str(l.get("source") or "").lower() or "zauba" in str(l.get("source") or "").lower())
    ]
    if mca_leaders:
        issues.append(f"MCA leaders present: {[l.get('name') for l in mca_leaders]}")
    else:
        ok.append("no MCA leadership")

    if not name:
        issues.append("missing name")
    else:
        ok.append(f"name={name}")

    if "buffer.com" in url.lower() and "buffer" not in name.lower():
        issues.append(f"wrong brand for Buffer: {name}")
    if "microsoft.com" in url.lower() and "microsoft" not in name.lower():
        issues.append(f"wrong brand for Microsoft: {name}")

    if len(comps) < 2:
        issues.append(f"few competitors: {len(comps)}")
    else:
        ok.append(f"competitors={[c.get('name') for c in comps[:5]]}")

    mp = val(ma.get("market_position") if isinstance(ma, dict) else "")
    if not mp:
        issues.append("missing market_position")
    elif any(t in mp.lower() for t in ("login", "cookie", "keka", "password")):
        issues.append(f"junk market_position: {mp[:100]}")
    else:
        ok.append(f"market_position ok")

    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        n = len(swot.get(k) or [])
        if n < 1:
            issues.append(f"SWOT {k} empty")
        else:
            ok.append(f"SWOT {k}={n}")

    ok.append(f"emails={len(ci.get('emails') or [])} phones={len(ci.get('phones') or [])}")
    ok.append(f"leaders={ [l.get('name') for l in leaders if isinstance(l, dict)][:5] }")

    return {
        "label": label,
        "url": url,
        "name": name,
        "pass": not issues,
        "issues": issues,
        "ok": ok,
        "score": (report.get("intelligence_score") or {}).get("overall"),
        "competitors": [c.get("name") for c in comps[:6]],
        "registry_source": reg.get("source"),
    }


def main():
    # Wait briefly for reload
    time.sleep(2)
    try:
        urllib.request.urlopen(API + "/docs", timeout=5)
    except Exception as e:
        print("Backend not up:", e)
        return 1

    print("=== SOURCE Ergobite ===", flush=True)
    src = post("/api/brochure-search", {"company_name": "Ergobite"}, timeout=180)
    src_ok = bool(src.get("company_name") and (src.get("services") or []) and src.get("summary"))
    print(json.dumps({"pass": src_ok, "name": src.get("company_name"), "services": (src.get("services") or [])[:4]}, indent=2), flush=True)

    print("=== TARGET Buffer ===", flush=True)
    t0 = time.time()
    buffer = post("/api/company-research", {"url": "https://buffer.com"}, timeout=600)
    print(f"Buffer in {time.time()-t0:.1f}s", flush=True)
    bcheck = check_target("Buffer", "https://buffer.com", buffer)
    print(json.dumps(bcheck, indent=2), flush=True)

    print("=== TARGET Microsoft (Zauba regression) ===", flush=True)
    t0 = time.time()
    ms = post("/api/company-research", {"url": "https://www.microsoft.com"}, timeout=600)
    print(f"Microsoft in {time.time()-t0:.1f}s", flush=True)
    mcheck = check_target("Microsoft", "https://www.microsoft.com", ms)
    print(json.dumps(mcheck, indent=2), flush=True)

    print("=== PITCH Ergobite -> Buffer ===", flush=True)
    pitch = post("/api/generate-pitch", {"brochure": src, "target": buffer}, timeout=180)
    pitch_issues = []
    pitch_ok = []
    if pitch.get("ai_conclusion"):
        pitch_ok.append("ai_conclusion")
    else:
        pitch_issues.append("missing ai_conclusion")
    if pitch.get("matches"):
        pitch_ok.append(f"matches={len(pitch.get('matches') or [])}")
    else:
        pitch_issues.append("missing matches")
    ed = pitch.get("email_draft") or {}
    body = ed.get("body") if isinstance(ed, dict) else str(ed)
    if body and len(str(body)) > 40:
        pitch_ok.append(f"email_draft_len={len(str(body))}")
    else:
        pitch_issues.append("weak email_draft")
    if "zaubacorp.com" in json.dumps(pitch).lower():
        pitch_issues.append("zaubacorp.com in pitch")
    else:
        pitch_ok.append("no zauba url in pitch")
    print(json.dumps({"pass": not pitch_issues, "ok": pitch_ok, "issues": pitch_issues, "match_score": pitch.get("match_score")}, indent=2), flush=True)

    overall = src_ok and bcheck["pass"] and mcheck["pass"] and (not pitch_issues)
    out = {
        "source_pass": src_ok,
        "buffer": bcheck,
        "microsoft": mcheck,
        "pitch": {"pass": not pitch_issues, "ok": pitch_ok, "issues": pitch_issues, "match_score": pitch.get("match_score")},
        "overall_pass": overall,
    }
    with open("e2e_verify_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("OVERALL_PASS=", overall, flush=True)
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
