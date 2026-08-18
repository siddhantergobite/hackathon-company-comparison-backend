import json

d = json.load(open("frontend_check_google.json", encoding="utf-8"))
co = d.get("company_profile") or {}
sc = d.get("intelligence_score") or {}
meta = d.get("_meta") or {}


def val(field):
    if isinstance(field, dict) and "value" in field:
        return field.get("value") or ""
    return field or ""


issues = []
overall = sc.get("overall")
if overall is not None and not isinstance(overall, (int, float)):
    issues.append(
        f"Score UI shows '{overall}/100' but overall is type {type(overall).__name__}"
    )

desc = val(co.get("description"))
if not desc:
    issues.append("Description empty — hero summary may be blank/weak")

if not (d.get("competitors") or []):
    issues.append("No competitors — Competitors tab empty")

if co.get("employees") and not (
    co.get("employee_count")
    or (d.get("employee_insights") or {}).get("total_employees")
):
    issues.append(
        "Headcount in co.employees but UI reads employee_count / employee_insights"
    )

# Check if score rendering would look wrong
score_text = f"{overall}/100 overall" if overall else "—"

out = {
    "frontend_would_show": {
        "hero_name": meta.get("company_name") or val(co.get("name")),
        "hero_sub": " · ".join(
            x
            for x in [val(co.get("industry")), val(co.get("founded"))]
            if x and "not publicly" not in str(x).lower()
        )
        or meta.get("domain"),
        "score_text": score_text,
        "competitors": [c.get("name") for c in (d.get("competitors") or [])][:6],
        "offerings_count": len(
            ((d.get("products_services") or {}).get("primary_offerings") or [])
        ),
        "emails": len(((d.get("contact_intelligence") or {}).get("emails") or [])),
        "elapsed": meta.get("elapsed_seconds"),
    },
    "raw_score": sc,
    "profile_keys": list(co.keys()),
    "description_preview": str(desc)[:240],
    "market_position": (d.get("market_analysis") or {}).get("market_position"),
    "frontend_issues": issues,
}

open("frontend_check_summary.json", "w", encoding="utf-8").write(
    json.dumps(out, indent=2, ensure_ascii=True)
)
print("OK", len(issues), "issues")
for i in issues:
    print("ISSUE:", i)
print("SCORE_TEXT:", score_text)
print("NAME:", out["frontend_would_show"]["hero_name"])
print("COMPS:", out["frontend_would_show"]["competitors"])
