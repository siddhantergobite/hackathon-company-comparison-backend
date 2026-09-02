"""Download and flatten the RoboHelp tables of contents for every Nividous help project.

RoboHelp chunks the TOC: nodes of type "book" carry a `key` (e.g. "toc7") whose children
live in whxdata/<key>.new.js. This walks those chunks recursively.
"""
import json
import re
from pathlib import Path

import requests

ROOT = "https://community.nividous.com/help-documents/"
PROJECTS = [
    "Nividous-RPA-Help",
    "Nividous-LPA-Help",
    "CC-Help",
    "API-Help",
    "Smart-Bot-Help",
    "RPA-Quick-Start",
    "LPA-Quick-Start",
    "Studio-Installation-Help",
    "CC-Installation-Help",
    "Bot-Installation-Help",
    "Infrastructure-Help",
]

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"
out_dir = Path("toc")
out_dir.mkdir(exist_ok=True)


def load_chunk(proj: str, name: str):
    r = s.get(f"{ROOT}{proj}/whxdata/{name}.new.js", timeout=90)
    if r.status_code != 200:
        return None
    m = re.search(r"=\s*(\[[\s\S]*?\]);\s*window\.rh", r.text)
    if not m:
        m = re.search(r"(\[[\s\S]*\])", r.text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk(proj, nodes, depth, lines, seen):
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        name = n.get("name", "?")
        url = n.get("url", "")
        lines.append(f"{'    ' * depth}- {name}" + (f"  <{url}>" if url else ""))
        key = n.get("key")
        if key and key not in seen:
            seen.add(key)
            child = load_chunk(proj, key)
            if child:
                walk(proj, child, depth + 1, lines, seen)
        if isinstance(n.get("child"), list):
            walk(proj, n["child"], depth + 1, lines, seen)


summary = []
for proj in PROJECTS:
    root = load_chunk(proj, "toc")
    if root is None:
        summary.append(f"{proj}: FAILED to parse root toc")
        continue
    lines, seen = [], set()
    walk(proj, root, 0, lines, seen)
    (out_dir / f"{proj}.toc.txt").write_text("\n".join(lines), encoding="utf-8")
    summary.append(f"{proj}: {len(lines)} topics across {len(seen) + 1} chunks")

print("\n".join(summary))
