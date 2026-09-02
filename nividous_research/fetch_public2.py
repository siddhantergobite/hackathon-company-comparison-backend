"""Fetch the substantive nividous.com pages as readable text."""
import re
from html import unescape
from pathlib import Path

import requests

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"

PAGES = [
    "automation/agentic-ai",
    "automation/intelligent-automation",
    "automation/intelligent-document-processing",
    "automation/hyperautomation",
    "automation/rpa",
    "platform/control-center",
    "services",
    "solutions/quick-start-program",
    "solutions/industry/finance-and-banking-automation",
    "solutions/industry/insurance-automation",
    "solutions/industry/healthcare-automation",
    "solutions/industry/manufacturing-automation",
    "solutions/industry/life-sciences-automation",
    "solutions/industry/logistics-and-supply-chain",
    "solutions/industry/optical-practices-automation",
    "solutions/function/finance-and-accounting-automation",
    "solutions/function/healthcare-revenue-cycle-management",
    "solutions/function/it-automation",
    "solutions/function/hr-automation",
    "solutions/function/contact-center-automation",
    "solutions/function/automation-across-business-functions",
    "resources/webinars/agentic-ai-use-cases",
    "resources/case-studies/insurance-underwriting-process-automation-with-nividous-smart-bots",
    "resources/case-studies/accounts-payable-process-automation-for-a-leading-manufacturing-company",
    "resources/case-studies/leading-eyecare-group-revolutionizes-its-complete-revenue-cycle-management-with-nividous-rpa-bots",
]


def to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr|/td)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    lines = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in unescape(html).split("\n")]
    res, blank = [], False
    for l in lines:
        if not l:
            if not blank:
                res.append("")
            blank = True
        else:
            res.append(l)
            blank = False
    return "\n".join(res)


out = Path("public")
out.mkdir(exist_ok=True)
for p in PAGES:
    try:
        r = s.get(f"https://nividous.com/{p}/", timeout=120)
    except requests.RequestException as e:
        print(f"{p}: ERROR {e}")
        continue
    if r.status_code != 200:
        print(f"{p}: HTTP {r.status_code}")
        continue
    txt = to_text(r.text)
    (out / (p.replace("/", "__") + ".txt")).write_text(txt, encoding="utf-8")
    print(f"{p}: {len(txt)} chars")
