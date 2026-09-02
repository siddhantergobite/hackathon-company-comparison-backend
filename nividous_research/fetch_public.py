"""Map nividous.com: collect every internal link from the homepage, then fetch the key ones."""
import re
import sys
from html import unescape
from pathlib import Path

import requests

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0"


def to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head|footer)[^>]*>.*?</\1>", " ", html)
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


home = s.get("https://nividous.com/", timeout=90).text
links = sorted({
    u.split("#")[0].rstrip("/")
    for u in re.findall(r'href="(https://nividous\.com/[^"?#]*)"', home)
})
Path("public_links.txt").write_text("\n".join(links), encoding="utf-8")
print(f"{len(links)} internal links found\n")
for l in links:
    print(l)
sys.stdout.flush()
