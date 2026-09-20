import json

import pytest
import requests

from backend.events.collectors.base import CollectorError, PoliteHttpClient
from backend.events.collectors.eventbrite import EventbriteCollector
from backend.events.collectors.feed import FeedCollector, parse_ics
from backend.events.collectors.meetup import MeetupCollector
from backend.events.processors.pipeline import run_collector
from backend.events.tests.conftest import days


def ymd(n: int) -> str:
    return days(n).replace("-", "")


def ics(future=15, past=-30) -> str:
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "BEGIN:VEVENT", "UID:abc-1@example.com", r"SUMMARY:Founders Meetup\, Berlin",
        f"DTSTART;TZID=Europe/Berlin:{ymd(future)}T183000", f"DTEND;TZID=Europe/Berlin:{ymd(future)}T210000",
        r"LOCATION:Factory Berlin\, Rheinsberger Str. 76",
        r"DESCRIPTION:Line one\nLine two that is long and gets", "  folded across two lines",
        "URL:https://example.com/e/1?utm_source=cal", "GEO:52.5;13.4", "CATEGORIES:Startups,Networking",
        "ORGANIZER;CN=Berlin Founders:mailto:x@example.com", "END:VEVENT",
        "BEGIN:VEVENT", "UID:abc-2", "SUMMARY:Two Day Expo", f"DTSTART;VALUE=DATE:{ymd(20)}", f"DTEND;VALUE=DATE:{ymd(22)}", "END:VEVENT",
        "BEGIN:VEVENT", "UID:abc-3", "SUMMARY:Old Event", f"DTSTART;VALUE=DATE:{ymd(past)}", "END:VEVENT",
        "END:VCALENDAR",
    ])


def test_parse_ics_unfolds_and_unescapes():
    evs = parse_ics(ics())
    assert len(evs) == 3
    first = evs[0]
    assert first["summary"]["value"] == "Founders Meetup, Berlin"
    assert first["description"]["value"] == "Line one\nLine two that is long and gets folded across two lines"
    assert first["dtstart"]["params"]["TZID"] == "Europe/Berlin"


def feed(tmp_path, text, **cfg):
    f = tmp_path / "feed.ics"
    f.write_text(text, encoding="utf-8")
    return FeedCollector({"name": "t", "label": "Test Feed", "type": "ical", "url": str(f), "respect_robots": False, **cfg})


def test_ical_feed_collector_maps_fields_and_all_day_end(tmp_path):
    raws = list(feed(tmp_path, ics(), defaults={"country": "Germany", "city": "Berlin"}).collect())
    first, expo = raws[0], raws[1]
    assert first["title"] == "Founders Meetup, Berlin" and first["timezone"] == "Europe/Berlin"
    assert first["source_event_id"] == "abc-1@example.com" and first["latitude"] == "52.5"
    assert first["organizer"]["name"] == "Berlin Founders" and first["country"] == "Germany"
    # all-day DTEND is exclusive: 20..22 means the event runs 20th and 21st
    assert expo["start"] == ymd(20) and expo["end"] == days(21)


def test_feed_end_to_end_skips_past_and_stores_rest(db, tmp_path):
    c = feed(tmp_path, ics(), defaults={"country": "Germany", "city": "Berlin", "event_type": "startup_event"})
    s = run_collector(db, c, use_ai=False)
    assert s["status"] == "success" and s["counts"]["created"] == 2 and s["counts"]["skipped"] == 1
    meetup = db["events"].find_one({"source.source_event_id": "abc-1@example.com"})
    assert meetup["source"]["name"] == "Test Feed" and meetup["event_url"] == "https://example.com/e/1"
    assert meetup["start_time"] == "18:30" and meetup["location"]["country"] == "Germany"
    # second run is a no-op refresh, not a duplicate
    s2 = run_collector(db, c, use_ai=False)
    assert s2["counts"]["created"] == 0 and db["events"].count_documents({}) == 2


def test_json_feed_with_mapping(tmp_path):
    f = tmp_path / "f.json"
    f.write_text(json.dumps({"data": {"events": [{"id": 7, "name": "JSON Conf", "starts_at": days(30), "url": "https://example.com/j", "venue": {"city": "Lisbon", "country": "PT"}}]}}))
    c = FeedCollector({
        "name": "j", "type": "json", "url": str(f), "items_path": "data.events", "respect_robots": False,
        "mapping": {"title": "name", "start": "starts_at", "event_url": "url", "source_event_id": "id", "city": "venue.city", "country": "venue.country"},
    })
    [raw] = list(c.collect())
    assert raw["title"] == "JSON Conf" and raw["city"] == "Lisbon" and raw["source_event_id"] == 7


def test_feed_errors_are_reported_not_raised_by_run_collector(db, tmp_path):
    c = FeedCollector({"name": "missing", "type": "ical", "url": str(tmp_path / "nope.ics")})
    s = run_collector(db, c, use_ai=False)
    assert s["status"] == "failed" and "cannot read feed file" in s["error"]
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    s = run_collector(db, FeedCollector({"name": "b", "type": "json", "url": str(bad)}), use_ai=False)
    assert s["status"] == "failed" and "not valid JSON" in s["error"]


def test_unconfigured_api_collectors_refuse_to_run():
    for c in (EventbriteCollector(), MeetupCollector()):
        assert c.is_configured() is False
        with pytest.raises(CollectorError):
            list(c.collect())


def test_eventbrite_payload_mapping():
    raw = EventbriteCollector.to_raw({
        "id": "123", "name": {"text": "EB Event"}, "url": "https://eventbrite.com/e/123", "summary": "Sum",
        "description": {"text": "Desc"}, "start": {"local": "2027-01-10T09:00:00", "timezone": "America/New_York"},
        "end": {"local": "2027-01-10T17:00:00"}, "online_event": False, "is_free": False,
        "venue": {"name": "Hall", "address": {"address_1": "1 Main", "city": "NYC", "region": "NY", "country": "US", "latitude": "40.7", "longitude": "-74"}},
        "organizer": {"name": "Org"}, "ticket_availability": {"minimum_ticket_price": {"major_value": "25.00", "currency": "USD"}},
        "logo": {"url": "https://img/x.png"}, "status": "canceled",
    })
    from backend.events.processors.normalize import normalize_event

    ev, _ = normalize_event({**raw, "source_name": "Eventbrite"})
    assert ev["title"] == "EB Event" and ev["timezone"] == "America/New_York"
    assert ev["location"]["country"] == "USA" and ev["registration"]["price"] == 25.0
    assert ev["status"] == "cancelled" and ev["source"]["source_event_id"] == "123"


# ------------------------------------------------------------------------- robots.txt
class _Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text, self.headers = status, text, {}

    def raise_for_status(self): ...


def test_robots_txt_is_respected(monkeypatch):
    c = PoliteHttpClient("TestBot/1.0", min_interval=0)
    monkeypatch.setattr(c._session, "get", lambda url, **k: _Resp(200, "User-agent: *\nDisallow: /private/"))
    assert c.allowed_by_robots("https://example.com/public/events") is True
    assert c.allowed_by_robots("https://example.com/private/events") is False
    with pytest.raises(CollectorError, match="robots.txt"):
        c.get("https://example.com/private/events")


def test_robots_unreachable_or_5xx_is_conservative_but_404_allows(monkeypatch):
    c = PoliteHttpClient("TestBot/1.0", min_interval=0)
    monkeypatch.setattr(c._session, "get", lambda url, **k: _Resp(404))
    assert c.allowed_by_robots("https://a.example/x") is True
    monkeypatch.setattr(c._session, "get", lambda url, **k: _Resp(503))
    assert c.allowed_by_robots("https://b.example/x") is False

    def down(url, **k):
        raise requests.ConnectionError()

    monkeypatch.setattr(c._session, "get", down)
    assert c.allowed_by_robots("https://c.example/x") is False
