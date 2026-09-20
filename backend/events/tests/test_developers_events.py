import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.events.collectors.base import CollectorError
from backend.events.collectors.developers_events import ATTRIBUTION, DevelopersEventsCollector
from backend.events.processors.pipeline import run_collector


def ms(days_from_now: int) -> int:
    d = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_from_now)
    return int(d.timestamp() * 1000)


def item(**over):
    base = {
        "name": "Apidays Paris", "date": [ms(40), ms(41)], "hyperlink": "https://www.apidays.global/paris",
        "location": "Paris (France)", "city": "Paris", "country": "France", "misc": "<a>badge</a>",
        "cfp": {}, "tags": [{"key": "tech", "value": "cybersecurity"}, {"key": "topic", "value": "api"}, {"key": "language", "value": "english"}],
    }
    base.update(over)
    return base


class Settings:
    ingest_user_agent = "test"
    developers_events_enabled = True


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, **k):
        payload = self.payload

        class R:
            def json(self_inner):
                if isinstance(payload, Exception):
                    raise payload
                return payload

        return R()


def collector(payload, enabled=True):
    s = Settings()
    s.developers_events_enabled = enabled
    return DevelopersEventsCollector(s, FakeClient(payload))


def test_maps_fields_dates_and_attribution():
    raw = DevelopersEventsCollector.to_raw(item())
    assert raw["title"] == "Apidays Paris" and raw["format"] == "offline"
    assert raw["start"] == (datetime.now(timezone.utc) + timedelta(days=40)).date().isoformat()
    assert raw["end"] == (datetime.now(timezone.utc) + timedelta(days=41)).date().isoformat()
    assert raw["city"] == "Paris" and raw["country"] == "France"
    assert ATTRIBUTION in raw["description"] and "CC BY-NC" in raw["description"]
    assert "Language: english." in raw["description"]
    assert raw["categories"][:2] == ["Technology", "Software"] and "Cybersecurity" in raw["categories"]
    assert "Api" in raw["topics"]  # unmapped tag values become topics, not made-up categories
    assert raw["event_type"] == "conference" and raw["audience"] == ["Developers"]
    assert len(raw["source_event_id"]) == 16


def test_online_hybrid_and_type_detection():
    online = DevelopersEventsCollector.to_raw(item(name="Cloud Meetup", city="Online", country="Online", location="Online"))
    assert online["format"] == "online" and online["city"] is None and online["country"] is None and online["event_type"] == "meetup"
    hybrid = DevelopersEventsCollector.to_raw(item(location="Paris (France) & Online"))
    assert hybrid["format"] == "hybrid" and "and online" in hybrid["description"]
    assert DevelopersEventsCollector.to_raw(item(name="Kubernetes Hackathon"))["event_type"] == "hackathon"


def test_single_date_and_bad_rows():
    one = DevelopersEventsCollector.to_raw(item(date=[ms(10)]))
    assert one["start"] == one["end"]
    assert DevelopersEventsCollector.to_raw(item(date=[])) is None
    assert DevelopersEventsCollector.to_raw(item(name="  ")) is None
    assert DevelopersEventsCollector.to_raw(item(tags=None))["categories"] == ["Technology", "Software"]


def test_open_cfp_is_mentioned_but_a_past_cfp_is_not():
    future = item(cfp={"link": "https://sessionize.com/x", "until": "1-Dec-2099", "untilDate": ms(200)})
    past = item(cfp={"link": "https://sessionize.com/y", "until": "1-Jan-2020", "untilDate": ms(-500)})
    assert "Call for papers is open until 1-Dec-2099" in DevelopersEventsCollector.to_raw(future)["description"]
    assert "Call for papers" not in DevelopersEventsCollector.to_raw(past)["description"]


def test_disabled_until_licence_is_accepted():
    c = collector([item()], enabled=False)
    assert c.is_configured() is False
    with pytest.raises(CollectorError, match="CC BY-NC"):
        list(c.collect())


def test_collect_skips_ended_events_and_rejects_bad_payloads():
    payload = [item(name="Future One"), item(name="Ended Long Ago", date=[ms(-400), ms(-399)]), item(name="Ends Today", date=[ms(-1), ms(0)])]
    titles = [r["title"] for r in collector(payload).collect()]
    assert titles == ["Future One", "Ends Today"]
    with pytest.raises(CollectorError, match="unexpected payload"):
        list(collector({"not": "a list"}).collect())
    with pytest.raises(CollectorError, match="invalid JSON"):
        list(collector(json.JSONDecodeError("x", "y", 0)).collect())


def test_end_to_end_import_is_idempotent_and_publishes(db):
    payload = [item(name="Apidays Paris"), item(name="Rust Summit", city="Berlin", country="Germany", location="Berlin (Germany)", hyperlink="https://rust.example/")]
    c = collector(payload)
    s1 = run_collector(db, c, use_ai=False)
    assert s1["status"] == "success" and s1["counts"]["created"] == 2
    ev = db["events"].find_one({"title": "Rust Summit"})
    assert ev["source"] == {"name": "developers.events", "url": "https://developers.events", "source_event_id": ev["source"]["source_event_id"]}
    assert ev["review_status"] == "approved" and ev["location"]["country"] == "Germany" and ev["event_type"] == "summit"
    assert "CC BY-NC" in ev["description"] and ev["summary"]
    s2 = run_collector(db, c, use_ai=False)
    assert s2["counts"]["created"] == 0 and s2["counts"]["unchanged"] == 2 and db["events"].count_documents({}) == 2
