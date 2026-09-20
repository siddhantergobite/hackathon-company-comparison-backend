"""Turn a raw feed item into the canonical article shape (or reject it).

Only headline, a short teaser, the link and metadata are kept. The publisher's full text is
never stored (content stays null): the app shows a summary, attribution and a link out.
"""
from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DESCRIPTION_MAX = 500
TITLE_MIN, TITLE_MAX = 12, 300


class InvalidArticle(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class TooOld(InvalidArticle):
    """Not an error: the item is simply older than the configured window."""


_TAG_BREAK = re.compile(r"</?(?:br|p|div|li|ul|ol|h[1-6]|tr)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$|cmp$|ocid$|cid$|_ga$|at_|maro$|taid$|sr_share$|smid$|smtyp$|source$|src$|xtor$|ito$)", re.I)
_BOILERPLATE = re.compile(r"\s*(the post .{0,200}? appeared first on .{0,120}?\.?|continue reading\W*|read more\W*|\[…\]|\[\.\.\.\]|the article .{0,120}? appeared first on .{0,120}?\.?)\s*$", re.I)


def strip_html(value: Any, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    s = _TAG_BREAK.sub(" ", str(value))
    s = _TAG.sub("", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        cut = s[: max_len - 1]
        if " " in cut[int(max_len * 0.6):]:
            cut = cut[: cut.rfind(" ")]
        s = cut.rstrip(" ,;:-–—") + "…"
    return s


def canonical_url(url: Any) -> str | None:
    """Stable identity for an article link: https, no www, no tracking params, no fragment."""
    if not url:
        return None
    s = str(url).strip()
    if len(s) > 2048:
        return None
    try:
        p = urlparse(s)
    except ValueError:
        return None
    if p.scheme.lower() not in ("http", "https") or not p.netloc or " " in p.netloc:
        return None
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)))
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", query, ""))


def article_id(canonical: str) -> str:
    """Deterministic id from the canonical URL, so the same link can never be stored twice."""
    return "n_" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


def http_url(value: Any) -> str | None:
    s = str(value).strip() if value else ""
    if not s or len(s) > 2048:
        return None
    if s.startswith("//"):
        s = "https:" + s
    p = urlparse(s)
    return s if p.scheme in ("http", "https") and p.netloc else None


def parse_datetime(value: Any) -> datetime | None:
    """feedparser struct_time, datetime, ISO-8601 or RFC-822 -> aware UTC datetime."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, time.struct_time):
            return datetime(*value[:6], tzinfo=timezone.utc)
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        s = str(value).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(s)
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean_title(title: str, source_name: str | None) -> str:
    t = title
    if source_name:
        # "Headline - Reuters" / "Headline | The Verge" syndication suffixes
        t = re.sub(rf"\s*[-–—|:]\s*{re.escape(source_name)}\s*$", "", t, flags=re.I)
    return t.strip()


def normalize_article(raw: dict, source: dict, *, now: datetime | None = None, max_age_days: int = 7) -> dict:
    """Return the canonical article dict (without scoring/classification). Raises InvalidArticle."""
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []

    source_name = strip_html(raw.get("source_name")) or source.get("name")
    title = strip_html(raw.get("title"), TITLE_MAX)
    if title:
        title = _clean_title(title, source_name)
    if not title or len(title) < TITLE_MIN:
        errors.append("title is missing or too short")
    elif title.lower() == (source_name or "").lower():
        errors.append("title is just the source name")

    canon = canonical_url(raw.get("link") or raw.get("url"))
    if not canon:
        errors.append("link is missing or not an http(s) URL")
    if errors:
        raise InvalidArticle(errors)

    published = parse_datetime(raw.get("published"))
    estimated = published is None
    if published is None:
        published = now
    elif published > now + timedelta(hours=1):  # misconfigured feed clock
        published = now
    if published < now - timedelta(days=max_age_days):
        raise TooOld(["older than the configured window"])

    description = strip_html(raw.get("description"))
    if description:
        description = _BOILERPLATE.sub("", description).strip()
        description = strip_html(description, DESCRIPTION_MAX)
    if description and description.lower().rstrip(".…") == title.lower().rstrip(".…"):
        description = None
    if description and len(description) < 20:
        description = None

    site = source.get("homepage") or (f"https://{urlparse(canon).netloc}")
    return {
        "_id": article_id(canon),
        "title": title,
        "description": description,
        "content": None,
        "url": canon,
        "original_url": http_url(raw.get("link") or raw.get("url")),
        "image_url": http_url(raw.get("image")),
        "source": {"id": source.get("_id"), "name": source_name, "url": site, "via": source.get("name") if source_name != source.get("name") else None},
        "language": (source.get("language") or "en")[:8],
        "author": strip_html(raw.get("author"), 120),
        "published_at": published,
        "published_estimated": estimated,
        "collected_at": now,
        "feed_tags": [t for t in (strip_html(x, 40) for x in (raw.get("tags") or [])) if t][:10],
    }
