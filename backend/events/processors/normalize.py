"""Validate + normalise raw event data into the canonical storage shape.

`normalize_event(raw)` accepts either the nested schema shape or the flat shape that
collectors naturally produce (`venue`, `city`, `start`, `url`, ...), and returns
`(event_dict, warnings)`. It raises `ValidationFailure` when the event is unusable.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.events.models import EVENT_TYPE_ALIASES, EVENT_TYPE_LABELS
from backend.events.taxonomy import canonical_category, slugify

__all__ = [
    "ValidationFailure", "normalize_event", "clean_text", "clean_url", "normalize_country",
    "parse_datetime_value", "compute_status", "map_event_type", "slugify",
]


class ValidationFailure(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# --------------------------------------------------------------------------- text helpers
_TAG_BREAK = re.compile(r"</?(?:br|p|div|li|ul|ol|h[1-6]|tr)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\f\v ]+")


def clean_text(value: Any, max_len: int | None = None, multiline: bool = False) -> str | None:
    """Strip HTML, unescape entities, collapse whitespace. Returns None for empty input."""
    if value is None:
        return None
    s = str(value)
    if multiline:
        s = _TAG_BREAK.sub("\n", s)
    s = _TAG.sub(" " if not multiline else "", s)
    s = html.unescape(s).replace("\r", "")
    if multiline:
        lines = [_WS.sub(" ", ln).strip() for ln in s.split("\n")]
        s = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    else:
        s = _WS.sub(" ", s.replace("\n", " ")).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_cid$|mc_eid$|ref$|ref_src$)", re.I)


def clean_url(value: Any) -> str | None:
    """Only http(s) URLs survive (blocks javascript:/data: links); tracking params are dropped."""
    s = clean_text(value)
    if not s or len(s) > 2048:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", s, re.I) and re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", s):
        s = "https://" + s
    try:
        p = urlparse(s)
    except ValueError:
        return None
    if p.scheme.lower() not in ("http", "https") or not p.netloc or " " in p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)])
    return urlunparse((p.scheme.lower(), p.netloc, p.path, p.params, query, ""))


def clean_list(values: Any, max_items: int = 30, max_len: int = 60, canonical=None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = re.split(r"[,;|\n]", values)
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if isinstance(v, dict):
            v = v.get("name") or v.get("label") or v.get("value")
        t = clean_text(v, max_len=max_len)
        if not t:
            continue
        if canonical:
            t = canonical(t) or t
        key = t.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_items:
            break
    return out


# ------------------------------------------------------------------------------ countries
_SHORT_NAMES = {"United States": "USA", "United Kingdom": "UK", "United Arab Emirates": "UAE"}
_COUNTRY_ALIASES = {
    "us": "USA", "u.s.": "USA", "usa": "USA", "u.s.a.": "USA", "united states": "USA",
    "united states of america": "USA", "america": "USA",
    "uk": "UK", "u.k.": "UK", "united kingdom": "UK", "great britain": "UK", "gb": "UK",
    "england": "UK", "scotland": "UK", "wales": "UK", "northern ireland": "UK",
    "uae": "UAE", "united arab emirates": "UAE", "holland": "Netherlands",
    "south korea": "South Korea", "korea, republic of": "South Korea", "republic of korea": "South Korea",
    "russia": "Russia", "russian federation": "Russia", "czechia": "Czechia", "czech republic": "Czechia",
    "turkiye": "Türkiye", "türkiye": "Türkiye", "turkey": "Türkiye", "vietnam": "Vietnam",
    # common native-language names (pycountry only knows English)
    "deutschland": "Germany", "españa": "Spain", "espana": "Spain", "italia": "Italy",
    "brasil": "Brazil", "nederland": "Netherlands", "österreich": "Austria", "osterreich": "Austria",
    "schweiz": "Switzerland", "suisse": "Switzerland", "svizzera": "Switzerland", "belgië": "Belgium",
    "belgique": "Belgium", "polska": "Poland", "sverige": "Sweden", "norge": "Norway",
    "danmark": "Denmark", "suomi": "Finland", "méxico": "Mexico", "日本": "Japan", "中国": "China",
}


def normalize_country(value: Any) -> str | None:
    s = clean_text(value, max_len=80)
    if not s:
        return None
    key = s.lower().strip(". ")
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    try:
        import pycountry

        c = None
        if re.fullmatch(r"[A-Za-z]{2}", s):
            c = pycountry.countries.get(alpha_2=s.upper())
        elif re.fullmatch(r"[A-Za-z]{3}", s):
            c = pycountry.countries.get(alpha_3=s.upper())
        if c is None:
            c = pycountry.countries.lookup(s)
        name = getattr(c, "common_name", None) or c.name
        return _SHORT_NAMES.get(name, name)
    except (LookupError, ImportError):
        return s.title() if s.islower() else s


# --------------------------------------------------------------------------------- dates
_ICAL_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$")
_TEXT_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%Y/%m/%d")


def _fmt_offset(dt: datetime) -> str | None:
    off = dt.utcoffset()
    if off is None:
        return None
    if off == timedelta(0):
        return "UTC"
    total = int(off.total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"UTC{sign}{total // 60:02d}:{total % 60:02d}"


def parse_datetime_value(value: Any) -> tuple[str | None, str | None, str | None]:
    """Parse many date/datetime shapes -> (YYYY-MM-DD, HH:MM | None, tz label | None).

    The wall-clock time in the value's own offset is kept (no conversion), matching how
    events are displayed: "09:00 local time".
    """
    if value is None or value == "":
        return None, None, None
    if isinstance(value, datetime):
        return value.date().isoformat(), value.strftime("%H:%M"), _fmt_offset(value)
    if isinstance(value, date):
        return value.isoformat(), None, None
    s = str(value).strip()
    m = _ICAL_COMPACT.match(s)
    if m:
        y, mo, d, hh, mm, _ss, z = m.groups()
        try:
            day = date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return None, None, None
        if hh is None:
            return day, None, None
        return day, f"{hh}:{mm}", "UTC" if z else None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date().isoformat(), None, None
        return dt.date().isoformat(), dt.strftime("%H:%M"), _fmt_offset(dt)
    except ValueError:
        pass
    for fmt in _TEXT_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat(), None, None
        except ValueError:
            continue
    return None, None, None


def _clean_time(value: Any) -> str | None:
    if value is None or value == "":
        return None
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?\s*", str(value))
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        h = h % 12 + (12 if ap.lower() == "pm" else 0)
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def compute_status(start_date: str | None, end_date: str | None, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    if not start_date:
        return "upcoming"
    end = end_date or start_date
    t = today.isoformat()
    if end < t:
        return "completed"
    if start_date <= t <= end:
        return "ongoing"
    return "upcoming"


# ------------------------------------------------------------------------------- mapping
_TYPE_HINTS = (
    ("hackathon", "hackathon"), ("webinar", "webinar"), ("workshop", "workshop"),
    ("meetup", "meetup"), ("meet-up", "meetup"), ("trade show", "trade_show"),
    ("tradeshow", "trade_show"), ("expo", "expo"), ("summit", "summit"),
    ("networking", "business_networking"), ("seminar", "industry_seminar"),
    ("training", "training"), ("bootcamp", "training"), ("course", "training"),
    ("demo day", "startup_event"), ("pitch", "startup_event"), ("startup", "startup_event"),
    ("conference", "conference"), ("congress", "conference"), ("symposium", "conference"),
    ("forum", "conference"), ("convention", "conference"),
)


def map_event_type(value: Any) -> str | None:
    """Map free text ("Tech Conference", "startup") to an EventType value; None if unknown."""
    s = clean_text(value)
    if not s:
        return None
    key = s.lower().replace("_", " ").strip()
    canonical = key.replace(" ", "_")
    if canonical in EVENT_TYPE_LABELS:
        return canonical
    if key in EVENT_TYPE_ALIASES:
        return EVENT_TYPE_ALIASES[key]
    for needle, result in _TYPE_HINTS:
        if needle in key:
            return result
    return None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _coord(value: Any, limit: float) -> float | None:
    n = _num(value)
    return n if n is not None and -limit <= n <= limit else None


# ----------------------------------------------------------------------------- flat -> nested
def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _adapt_flat(raw: dict) -> dict:
    """Fold flat collector-style keys into the nested schema shape (nested values win)."""
    r = dict(raw)
    loc = dict(r.get("location") or {}) if isinstance(r.get("location"), dict) else {}
    if isinstance(r.get("location"), str) and not loc:
        loc["address"] = r["location"]
    for key, aliases in {
        "venue": ("venue", "venue_name"), "address": ("address", "street"),
        "city": ("city",), "state": ("state", "region", "province"),
        "country": ("country", "country_code"), "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "lng", "lon"),
    }.items():
        if loc.get(key) in (None, ""):
            v = _pick(r, *aliases)
            if v is not None:
                loc[key] = v
    r["location"] = loc

    org = r.get("organizer")
    if isinstance(org, str):
        org = {"name": org}
    org = dict(org or {})
    if not org.get("name"):
        org["name"] = _pick(r, "organizer_name", "organiser", "host")
    if not org.get("website"):
        org["website"] = _pick(r, "organizer_url", "organizer_website")
    if not org.get("description"):
        org["description"] = _pick(r, "organizer_description")
    r["organizer"] = org

    reg = dict(r.get("registration") or {})
    if not reg.get("url"):
        reg["url"] = _pick(r, "registration_url", "ticket_url")
    for k_src, k_dst in (("price", "price"), ("currency", "currency"), ("ticket_type", "ticket_type"), ("ticket_info", "ticket_info")):
        if reg.get(k_dst) in (None, ""):
            v = r.get(k_src)
            if v is not None:
                reg[k_dst] = v
    if r.get("is_free") is True and not reg.get("ticket_type"):
        reg["ticket_type"] = "free"
    r["registration"] = reg

    src = dict(r.get("source") or {})
    if not src.get("name"):
        src["name"] = _pick(r, "source_name")
    if not src.get("url"):
        src["url"] = _pick(r, "source_url")
    if src.get("source_event_id") in (None, ""):
        src["source_event_id"] = _pick(r, "source_event_id", "external_id", "uid")
    r["source"] = src

    if r.get("start_date") in (None, ""):
        r["start_date"] = _pick(r, "start", "starts_at", "start_datetime", "dtstart")
    if r.get("end_date") in (None, ""):
        r["end_date"] = _pick(r, "end", "ends_at", "end_datetime", "dtend")
    if r.get("event_url") in (None, ""):
        r["event_url"] = _pick(r, "url", "link", "website")
    if r.get("image_url") in (None, ""):
        r["image_url"] = _pick(r, "image", "logo_url", "banner_url")
    if r.get("event_type") in (None, ""):
        r["event_type"] = _pick(r, "type", "kind")
    return r


# --------------------------------------------------------------------------------- normalize
def normalize_event(raw: dict, *, now: datetime | None = None) -> tuple[dict, list[str]]:
    now = now or datetime.now(timezone.utc)
    r = _adapt_flat(raw)
    errors: list[str] = []
    warnings: list[str] = []

    title = clean_text(r.get("title") or r.get("name"), max_len=200)
    if not title or len(title) < 3:
        errors.append("title is required (min 3 characters)")

    start_date, start_time, start_tz = parse_datetime_value(r.get("start_date"))
    if not start_date:
        errors.append("start_date is missing or not a recognisable date")
    end_date, end_time, end_tz = parse_datetime_value(r.get("end_date"))

    if errors:
        raise ValidationFailure(errors)

    # explicit *_time fields win over times parsed out of datetimes
    start_time = _clean_time(r.get("start_time")) or start_time
    end_time = _clean_time(r.get("end_time")) or end_time
    tz_name = clean_text(r.get("timezone"), max_len=64) or start_tz or end_tz

    if not end_date:
        end_date = start_date
    elif end_date < start_date:
        warnings.append("end_date was before start_date; set to start_date")
        end_date = start_date
    # iCal all-day events use an exclusive end date; a "midnight next day" end means the same day
    if end_time == "00:00" and end_date > start_date and not start_time:
        end_time = None

    loc_in = r.get("location") or {}
    location = {
        "venue": clean_text(loc_in.get("venue"), max_len=200),
        "address": clean_text(loc_in.get("address"), max_len=300),
        "city": clean_text(loc_in.get("city"), max_len=100),
        "state": clean_text(loc_in.get("state"), max_len=100),
        "country": normalize_country(loc_in.get("country")),
        "latitude": _coord(loc_in.get("latitude"), 90),
        "longitude": _coord(loc_in.get("longitude"), 180),
    }
    if (location["latitude"] is None) != (location["longitude"] is None):
        location["latitude"] = location["longitude"] = None

    # format / is_online
    fmt_raw = (clean_text(r.get("format") or r.get("attendance_mode")) or "").lower().replace("-", "_")
    is_online_raw = r.get("is_online")
    if fmt_raw in ("online", "virtual", "webinar", "remote"):
        fmt = "online"
    elif fmt_raw in ("hybrid", "mixed"):
        fmt = "hybrid"
    elif fmt_raw in ("offline", "in_person", "inperson", "onsite", "physical", "in person"):
        fmt = "offline"
    elif is_online_raw is True:
        fmt = "online"
    else:
        fmt = "offline"
    if fmt == "offline" and not any(location[k] for k in ("venue", "city", "address", "country")):
        # no place information at all and no explicit statement -> leave as offline (unknown place)
        warnings.append("no location information")

    org_in = r.get("organizer") or {}
    social = {}
    for k, v in (org_in.get("social_links") or {}).items():
        u = clean_url(v)
        if k and u:
            social[str(k).strip().lower()[:30]] = u
    organizer = {
        "name": clean_text(org_in.get("name"), max_len=200),
        "description": clean_text(org_in.get("description"), max_len=1000, multiline=True),
        "website": clean_url(org_in.get("website")),
        "social_links": social,
    }

    reg_in = r.get("registration") or {}
    price = _num(reg_in.get("price"))
    if price is not None and price < 0:
        price = None
    currency = clean_text(reg_in.get("currency"), max_len=3)
    currency = currency.upper() if currency and re.fullmatch(r"[A-Za-z]{3}", currency) else None
    ticket_type = (clean_text(reg_in.get("ticket_type")) or "").lower() or None
    ticket_info = clean_text(reg_in.get("ticket_info"), max_len=500)
    if isinstance(reg_in.get("price"), str) and re.search(r"\bfree\b", reg_in["price"], re.I):
        ticket_type, price = "free", 0.0
    if price is not None and price == 0:
        ticket_type = "free"
    elif price is not None and price > 0:
        ticket_type = "paid"
    elif ticket_type not in ("free", "paid"):
        ticket_type = None
    registration = {
        "url": clean_url(reg_in.get("url")),
        "price": price,
        "currency": currency,
        "ticket_type": ticket_type,
        "ticket_info": ticket_info,
    }

    src_in = r.get("source") or {}
    sid = src_in.get("source_event_id")
    source = {
        "name": clean_text(src_in.get("name"), max_len=100) or "manual",
        "url": clean_url(src_in.get("url")),
        "source_event_id": str(sid).strip() if sid not in (None, "") else None,
    }

    event_url = clean_url(r.get("event_url")) or registration["url"]
    if not event_url:
        warnings.append("no event URL")

    event_type = map_event_type(r.get("event_type"))

    status_raw = (clean_text(r.get("status")) or "").lower()
    status = status_raw if status_raw in ("cancelled", "postponed") else compute_status(start_date, end_date, now.date())

    event = {
        "title": title,
        "event_type": event_type,
        "summary": clean_text(r.get("summary"), max_len=300),
        "description": clean_text(r.get("description"), max_len=10000, multiline=True),
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": tz_name,
        "location": location,
        "is_online": fmt == "online",
        "format": fmt,
        "categories": clean_list(r.get("categories"), max_items=12, canonical=canonical_category),
        "topics": clean_list(r.get("topics"), max_items=30),
        "audience": clean_list(r.get("audience"), max_items=20),
        "keywords": clean_list(r.get("keywords"), max_items=30),
        "organizer": organizer,
        "registration": registration,
        "image_url": clean_url(r.get("image_url")),
        "event_url": event_url,
        "source": source,
        "status": status,
        "last_verified": now,
    }
    if r.get("slug"):
        event["slug"] = slugify(str(r["slug"]))
    return event, warnings
