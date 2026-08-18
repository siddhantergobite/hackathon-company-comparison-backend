"""End-to-end verify: source brochure + target research + pitch (post-Zauba removal)."""
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


def check_report(label: str, url: str, report: dict) -> dict:
    issues = []
    ok = []
    meta = report.get("_meta") or {}
    cp = report.get("company_profile") or {}
    name = val(cp.get("name")) or meta.get("company_name") or ""
    reg = report.get("registry_intelligence") or {}
    leaders = report.get("leadership_team") or []
    comps = report.get("competitors") or []
    ci = report.get("contact_intelligence") or {}
    swot = report.get("swot_analysis") or {}
    ma = report.get("market_analysis") or {}
    blob = json.dumps(report).lower()

    if reg.get("cin"):
        issues.append(f"registry still has CIN: {reg.get('cin')}")
    elif reg.get("source") == "disabled" or not reg.get("cin"):
        ok.append("registry disabled / no CIN")

    if '"source": "zaubacorp' in blob or '"source":"zaubacorp' in blob:
        issues.append("ZaubaCorp still cited as a data source")
    else:
        ok.append("no ZaubaCorp source citations")

    if "zaubacorp.com" in blob:
        issues.append("zaubacorp.com URL still present")
    else:
        ok.append("no zaubacorp.com URLs")

    mca_leaders = [
        l
        for l in leaders
        if isinstance(l, dict)
        and (
            l.get("din")
            or "mca" in str(l.get("source") or "").lower()
            or "zauba" in str(l.get("source") or "").lower()
        )
    ]
    if mca_leaders:
        issues.append(f"MCA/Zauba leaders: {[l.get('name') for l in mca_leaders]}")
    else:
        ok.append("no MCA/Zauba leadership rows")

    if not name or str(name).lower() in ("unknown", "not publicly available"):
        issues.append(f"bad company name: {name!r}")
    else:
        ok.append(f"name={name}")

    # Buffer-specific identity check
    if "buffer.com" in url.lower():
        nl = name.lower()
        if "buffer" not in nl:
            issues.append(f"expected Buffer brand in name, got {name!r}")
        else:
            ok.append("Buffer brand identity OK")

    if "microsoft.com" in url.lower():
        if any(l.get("din") for l in leaders if isinstance(l, dict)):
            issues.append("Microsoft still has DIN directors")
        else:
            ok.append(f"Microsoft leadership clean (count={len(leaders)})")

    good_comps = [
        c
        for c in comps
        if isinstance(c, dict)
        and c.get("name")
        and not str(c.get("name")).lower().startswith("competitor")
    ]
    if len(good_comps) < 2:
        issues.append(f"too few competitors: {len(good_comps)}")
    else:
        ok.append(f"{len(good_comps)} competitors: {[c.get('name') for c in good_comps[:5]]}")

    # Cross-domain junk competitors (soft for Buffer)
    if "buffer.com" in url.lower():
        bad_tokens = ("keka", "naukri", "tcs", "infosys", "wipro")
        bad = [c.get("name") for c in good_comps if any(t in str(c.get("name") or "").lower() for t in bad_tokens)]
        if bad:
            issues.append(f"wrong-domain competitors: {bad}")
        else:
            ok.append("competitors look social/marketing-adjacent")

    mp = val(ma.get("market_position") if isinstance(ma, dict) else "")
    junk_tokens = ("login", "sign in", "cookie", "keka", "password")
    if mp and any(t in mp.lower() for t in junk_tokens):
        issues.append(f"junk market_position: {mp[:120]!r}")
    elif mp:
        ok.append(f"market_position ok ({mp[:90]})")
    else:
        issues.append("missing market_position")

    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        arr = swot.get(k) or []
        if not isinstance(arr, list) or len(arr) < 1:
            issues.append(f"SWOT {k} empty")
        else:
            ok.append(f"SWOT {k}={len(arr)}")

    emails = ci.get("emails") or []
    phones = ci.get("phones") or []
    ok.append(f"contacts emails={len(emails)} phones={len(phones)}")

    return {
        "label": label,
        "url": url,
        "name": name,
        "ok": ok,
        "issues": issues,
        "pass": len(issues) == 0,
        "score": (report.get("intelligence_score") or {}).get("overall"),
        "registry": {
            "source": reg.get("source"),
            "message": (reg.get("message") or "")[:160],
        },
        "leaders": [l.get("name") for l in leaders if isinstance(l, dict)][:8],
        "competitors": [c.get("name") for c in good_comps][:6],
        "emails": [e.get("email") for e in emails[:5] if isinstance(e, dict)],
        "market_position": (mp or "")[:200],
    }


def main():
    print("=== 1) SOURCE: brochure-search Ergobite ===", flush=True)
    t0 = time.time()
    src = post("/api/brochure-search", {"company_name": "Ergobite"}, timeout=180)
    print(f"Source done in {time.time() - t0:.1f}s", flush=True)

    src_issues = []
    src_ok = []
    if not (src.get("company_name") or "").strip():
        src_issues.append("missing company_name")
    else:
        src_ok.append(f"company_name={src.get('company_name')}")
    svcs = src.get("services") or []
    if len(svcs) < 1:
        src_issues.append("no services")
    else:
        src_ok.append(f"services={len(svcs)}: {svcs[:4]}")
    if not (src.get("summary") or "").strip():
        src_issues.append("empty summary")
    else:
        src_ok.append(f"summary_len={len(src.get('summary') or '')}")
    print(json.dumps({"ok": src_ok, "issues": src_issues, "pass": not src_issues}, indent=2), flush=True)

    print("=== 2) TARGET: company-research buffer.com ===", flush=True)
    t0 = time.time()
    tgt = post("/api/company-research", {"url": "https://buffer.com"}, timeout=600)
    print(f"Target done in {time.time() - t0:.1f}s", flush=True)
    tgt_check = check_report("Buffer", "https://buffer.com", tgt)
    print(json.dumps(tgt_check, indent=2), flush=True)

    print("=== 3) PITCH: Ergobite -> Buffer ===", flush=True)
    t0 = time.time()
    pitch = post("/api/generate-pitch", {"brochure": src, "target": tgt}, timeout=180)
    print(f"Pitch done in {time.time() - t0:.1f}s", flush=True)
    print("pitch keys:", list(pitch.keys()), flush=True)

    pitch_issues = []
    pitch_ok = []
    mm = pitch.get("matching_matrix") or pitch.get("match_matrix") or []
    email = pitch.get("outreach_email") or pitch.get("email") or pitch.get("outreach") or ""
    summary = (
        pitch.get("executive_summary")
        or pitch.get("summary")
        or pitch.get("pitch_summary")
        or pitch.get("ai_conclusion")
        or ""
    )
    if isinstance(email, dict):
        email = email.get("body") or email.get("text") or json.dumps(email)[:200]
    if summary:
        pitch_ok.append(f"summary_len={len(str(summary))}")
    else:
        pitch_issues.append(f"missing pitch summary; keys={list(pitch.keys())}")
    if mm:
        pitch_ok.append(f"matching_matrix={len(mm)}")
    else:
        pitch_issues.append("missing matching_matrix")
    if email and len(str(email)) > 40:
        pitch_ok.append(f"outreach_len={len(str(email))}")
    else:
        # still pass if other pitch body exists
        bodyish = pitch.get("pitch") or pitch.get("cold_email") or pitch.get("message")
        if bodyish and len(str(bodyish)) > 40:
            pitch_ok.append("outreach-like field present")
        else:
            pitch_issues.append("weak/missing outreach")
    if "zaubacorp" in json.dumps(pitch).lower():
        pitch_issues.append("zaubacorp mentioned in pitch")
    else:
        pitch_ok.append("no zauba in pitch")
    print(json.dumps({"ok": pitch_ok, "issues": pitch_issues, "pass": not pitch_issues}, indent=2), flush=True)

    out = {
        "source": {
            "name": src.get("company_name"),
            "services": (src.get("services") or [])[:6],
            "summary": (src.get("summary") or "")[:300],
            "check_ok": src_ok,
            "check_issues": src_issues,
        },
        "target": tgt_check,
        "pitch": {"ok": pitch_ok, "issues": pitch_issues, "keys": list(pitch.keys())},
        "overall_pass": (not src_issues) and tgt_check["pass"] and (not pitch_issues),
    }
    with open("e2e_verify_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    slim = {
        "company_profile": tgt.get("company_profile"),
        "registry_intelligence": tgt.get("registry_intelligence"),
        "leadership_team": tgt.get("leadership_team"),
        "competitors": tgt.get("competitors"),
        "market_analysis": tgt.get("market_analysis"),
        "swot_analysis": {
            k: (tgt.get("swot_analysis") or {}).get(k)
            for k in ("strengths", "weaknesses", "opportunities", "threats")
        },
        "contact_intelligence": {
            k: (tgt.get("contact_intelligence") or {}).get(k)
            for k in ("emails", "phones", "address")
        },
        "intelligence_score": tgt.get("intelligence_score"),
        "_meta": tgt.get("_meta"),
    }
    with open("e2e_target_slim.json", "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)

    print("OVERALL_PASS=", out["overall_pass"], flush=True)
    return 0 if out["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
