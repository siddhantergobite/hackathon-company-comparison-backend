"""Locate the RoboHelp data-file naming scheme used by the Nividous help sites."""
import re
import sys

import requests

BASE = "https://community.nividous.com/help-documents/Nividous-RPA-Help/"
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"

for script in ("template/scripts/layout.min.js", "template/scripts/common.min.js",
               "template/scripts/rh.min.js", "template/scripts/layoutwidgets.min.js"):
    r = s.get(BASE + script, timeout=60)
    if r.status_code != 200:
        print(script, "->", r.status_code)
        continue
    t = r.text
    hits = sorted(set(re.findall(r"[\w./\-]{0,30}whxdata[\w./\-]{0,40}", t)))
    print(f"\n### {script}  ({len(t)} chars)")
    for h in hits:
        print("   ", h)
    for pat in ("toc", "index_", "search_", "chunk"):
        near = sorted(set(re.findall(r"['\"][\w./\-]*" + pat + r"[\w./\-]*['\"]", t)))[:25]
        if near:
            print(f"   [{pat}]", near)

sys.stdout.flush()
