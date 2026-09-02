"""Strip HTML files fetched from community.nividous.com down to readable text + link lists."""
import re
import sys
from html import unescape
from pathlib import Path


def clean(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(html)
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.split("\n")]
    out, prev_blank = [], False
    for ln in lines:
        if not ln:
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out)


def links(html: str, filt: str = "") -> list[str]:
    found = re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html)
    seen, res = set(), []
    for href, label in found:
        label = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", "", unescape(label))).strip()
        if filt and filt not in href:
            continue
        key = (href, label)
        if key in seen:
            continue
        seen.add(key)
        res.append(f"{label}  ->  {href}")
    return res


if __name__ == "__main__":
    path = Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else "text"
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if mode == "links":
        body = "\n".join(links(raw, sys.argv[3] if len(sys.argv) > 3 else ""))
        out = path.with_suffix(".links.txt")
    else:
        body = clean(raw)
        out = path.with_suffix(".txt")
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(body)} chars)")
