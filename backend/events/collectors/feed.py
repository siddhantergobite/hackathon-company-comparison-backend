"""Generic public-feed collectors: iCalendar (.ics) and JSON feeds.

Feeds are declared in `collectors/sources.json` (see sources.example.json). Only add feeds
that the publisher makes available for this use: read their terms, keep `respect_robots`
on, and record the licence in the feed's `license` note. A feed `url` may also be a local
file path, which is how the tests and samples run without a network.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

from backend.events.config import PROJECT_ROOT, Settings, get_settings
from backend.events.collectors.base import BaseCollector, CollectorError, PoliteHttpClient

log = logging.getLogger(__name__)


# ------------------------------------------------------------------------------------ iCal
def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _unescape(v: str) -> str:
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def parse_ics(text: str) -> list[dict]:
    """Minimal RFC 5545 reader: returns one dict per VEVENT with lower-case property names."""
    events: list[dict] = []
    cur: dict | None = None
    for line in _unfold(text):
        if line.upper() == "BEGIN:VEVENT":
            cur = {}
        elif line.upper() == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            head, _, value = line.partition(":")
            name, *params = head.split(";")
            pdict = {}
            for p in params:
                k, _, v = p.partition("=")
                pdict[k.upper()] = v.strip('"')
            cur[name.lower()] = {"value": _unescape(value), "params": pdict}
    return events


def _all_day(prop: dict | None) -> bool:
    return bool(prop) and (prop["params"].get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", prop["value"].strip()) is not None)


_ONLINE = re.compile(r"\b(online|virtual|zoom|webinar|teams|google meet|livestream)\b", re.I)


def ics_event_to_raw(ev: dict, defaults: dict) -> dict:
    def val(k: str) -> str | None:
        return ev[k]["value"].strip() if k in ev and ev[k]["value"].strip() else None

    dtstart, dtend = ev.get("dtstart"), ev.get("dtend")
    end_value = val("dtend")
    if dtend and _all_day(dtend) and end_value and re.fullmatch(r"\d{8}", end_value):
        # all-day DTEND is exclusive: the event's last day is the day before
        d = date(int(end_value[:4]), int(end_value[4:6]), int(end_value[6:8])) - timedelta(days=1)
        end_value = d.isoformat()
    location = val("location") or ""
    raw: dict[str, Any] = {
        "title": val("summary"),
        "description": val("description"),
        "start": val("dtstart"),
        "end": end_value,
        "timezone": (dtstart or {}).get("params", {}).get("TZID"),
        "event_url": val("url"),
        "source_event_id": val("uid"),
        "categories": [c.strip() for c in (val("categories") or "").split(",") if c.strip()],
        "address": location or None,
    }
    if "geo" in ev and ";" in ev["geo"]["value"]:
        lat, _, lon = ev["geo"]["value"].partition(";")
        raw["latitude"], raw["longitude"] = lat, lon
    org = ev.get("organizer")
    if org:
        raw["organizer"] = {"name": org["params"].get("CN")}
    if _ONLINE.search(location) or _ONLINE.search(raw.get("event_url") or "") and not location:
        raw["is_online"] = True
    for k, v in defaults.items():
        if raw.get(k) in (None, "", [], {}):
            raw[k] = v
    return raw


# ------------------------------------------------------------------------------------ JSON
def _dig(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def json_item_to_raw(item: dict, mapping: dict[str, str], defaults: dict) -> dict:
    raw = {k: _dig(item, path) for k, path in mapping.items()} if mapping else dict(item)
    for k, v in defaults.items():
        if raw.get(k) in (None, "", [], {}):
            raw[k] = v
    return raw


# --------------------------------------------------------------------------------- collector
class FeedCollector(BaseCollector):
    def __init__(self, cfg: dict, settings: Settings | None = None, client: PoliteHttpClient | None = None):
        self.cfg = cfg
        self.settings = settings or get_settings()
        self.name = f"feed:{cfg['name']}"
        self.label = cfg.get("label") or cfg["name"]
        self.source_name = self.label
        self.source_url = cfg.get("site_url")
        self.description = cfg.get("license") or f"{cfg.get('type', 'ical').upper()} feed"
        self.group = cfg.get("group", "general")
        self.client = client or PoliteHttpClient(
            self.settings.ingest_user_agent,
            min_interval=float(cfg.get("min_interval_seconds", 2.0)),
            respect_robots=bool(cfg.get("respect_robots", True)),
        )

    def is_configured(self) -> bool:
        return bool(self.cfg.get("url")) and self.cfg.get("enabled", True)

    def _fetch(self) -> str:
        url = self.cfg["url"]
        if re.match(r"^https?://", url, re.I):
            return self.client.get(url).text
        path = Path(url)
        path = path if path.is_absolute() else PROJECT_ROOT / path
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CollectorError(f"cannot read feed file {path}: {exc}") from exc

    def collect(self) -> Iterator[dict]:
        if not self.is_configured():
            raise CollectorError(f"feed '{self.cfg.get('name')}' is disabled or has no url")
        text = self._fetch()
        defaults = self.cfg.get("defaults") or {}
        kind = (self.cfg.get("type") or "ical").lower()
        if kind == "ical":
            for ev in parse_ics(text):
                yield ics_event_to_raw(ev, defaults)
        elif kind == "json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CollectorError(f"feed is not valid JSON: {exc}") from exc
            items = _dig(data, self.cfg["items_path"]) if self.cfg.get("items_path") else data
            if not isinstance(items, list):
                raise CollectorError("JSON feed: items_path did not resolve to a list")
            for item in items:
                if isinstance(item, dict):
                    yield json_item_to_raw(item, self.cfg.get("mapping") or {}, defaults)
        else:
            raise CollectorError(f"unsupported feed type '{kind}'")


def load_feeds(settings: Settings | None = None, group: str | None = None) -> list[FeedCollector]:
    """Feed collectors declared in the sources file (empty list if the file doesn't exist)."""
    settings = settings or get_settings()
    path = settings.feed_sources_path
    if not path.is_file():
        return []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("cannot read feed sources file %s: %s", path, exc)
        return []
    out = []
    for feed in cfg.get("feeds", []):
        if not feed.get("name") or not feed.get("enabled", True):
            continue
        if group and feed.get("group", "general") != group:
            continue
        out.append(FeedCollector(feed, settings))
    return out
