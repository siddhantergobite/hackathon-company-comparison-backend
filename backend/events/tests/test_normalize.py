from datetime import date, datetime, timezone

import pytest

from backend.events.processors.normalize import (
    ValidationFailure, clean_text, clean_url, compute_status, map_event_type, normalize_country,
    normalize_event, parse_datetime_value, slugify,
)
from backend.events.tests.conftest import days, make_raw


def test_clean_text_strips_html_and_entities():
    assert clean_text("<p>Hello&nbsp;<b>World</b> &amp; co</p>") == "Hello World & co"
    assert clean_text("   ") is None
    assert clean_text(None) is None
    assert clean_text("a" * 50, max_len=10).endswith("…")


def test_clean_url_blocks_dangerous_schemes_and_tracking():
    assert clean_url("javascript:alert(1)") is None
    assert clean_url("data:text/html,<script>") is None
    assert clean_url("ftp://example.com/x") is None
    assert clean_url("https://example.com/e?utm_source=x&id=7#frag") == "https://example.com/e?id=7"
    assert clean_url("example.com/page") == "https://example.com/page"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("US", "USA"), ("usa", "USA"), ("United States of America", "USA"), ("gb", "UK"),
        ("United Kingdom", "UK"), ("IN", "India"), ("DEU", "Germany"), ("UAE", "UAE"), ("Deutschland", "Germany"),
    ],
)
def test_country_normalization(value, expected):
    assert normalize_country(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-10-12", ("2026-10-12", None, None)),
        ("2026-10-12T09:30:00", ("2026-10-12", "09:30", None)),
        ("2026-10-12T09:30:00Z", ("2026-10-12", "09:30", "UTC")),
        ("2026-10-12T18:30:00-07:00", ("2026-10-12", "18:30", "UTC-07:00")),
        ("20261012", ("2026-10-12", None, None)),
        ("20261012T093000Z", ("2026-10-12", "09:30", "UTC")),
        ("12 October 2026", ("2026-10-12", None, None)),
        ("not a date", (None, None, None)),
        ("20261345", (None, None, None)),
        (None, (None, None, None)),
    ],
)
def test_parse_datetime_value(value, expected):
    assert parse_datetime_value(value) == expected


def test_compute_status():
    today = date(2026, 6, 15)
    assert compute_status("2026-06-20", "2026-06-21", today) == "upcoming"
    assert compute_status("2026-06-14", "2026-06-16", today) == "ongoing"
    assert compute_status("2026-06-15", "2026-06-15", today) == "ongoing"
    assert compute_status("2026-06-01", "2026-06-14", today) == "completed"


def test_map_event_type():
    assert map_event_type("Tech Conference") == "conference"
    assert map_event_type("startup") == "startup_event"
    assert map_event_type("Industry Seminar") == "industry_seminar"
    assert map_event_type("business_networking") == "business_networking"
    assert map_event_type("gibberish") is None


def test_slugify():
    assert slugify("AI & ML Summit 2026") == "ai-ml-summit-2026"
    assert slugify("Café Été — Größe!") == "cafe-ete-groe"


def test_normalize_full_event():
    ev, warnings = normalize_event(make_raw(
        title="  <b>AI & ML</b>   Summit 2026 ",
        location={"city": "San Francisco", "country": "us", "latitude": "37.77", "longitude": "-122.41"},
        registration={"price": "$299", "currency": "usd", "url": "https://example.com/r?utm_campaign=x"},
        categories=["ai", "Machine Learning", "AI"],
        organizer={"name": "Org", "website": "javascript:evil()", "social_links": {"X": "https://x.com/org", "bad": "nope"}},
    ))
    assert ev["title"] == "AI & ML Summit 2026"
    assert ev["location"]["country"] == "USA"
    assert ev["location"]["latitude"] == 37.77
    assert ev["registration"] == {"url": "https://example.com/r", "price": 299.0, "currency": "USD", "ticket_type": "paid", "ticket_info": None}
    assert ev["categories"] == ["Artificial Intelligence", "Machine Learning"]  # aliased + de-duplicated
    assert ev["organizer"]["website"] is None
    assert ev["organizer"]["social_links"] == {"x": "https://x.com/org"}
    assert ev["status"] == "upcoming"
    assert ev["format"] == "offline" and ev["is_online"] is False


def test_normalize_free_and_online():
    ev, _ = normalize_event(make_raw(is_online=True, price="Free"))
    assert ev["is_online"] is True and ev["format"] == "online"
    assert ev["registration"]["ticket_type"] == "free" and ev["registration"]["price"] == 0.0


def test_normalize_accepts_flat_collector_shape():
    ev, _ = normalize_event({
        "title": "Flat Shape Meetup", "start": "2026-11-05T18:00:00", "end": "2026-11-05T20:00:00",
        "url": "https://example.com/m", "city": "Lisbon", "country": "PT", "organizer_name": "Guild",
        "source_name": "S", "source_event_id": 42, "lat": 38.7, "lng": -9.1,
    })
    assert ev["start_date"] == "2026-11-05" and ev["start_time"] == "18:00" and ev["end_time"] == "20:00"
    assert ev["location"]["country"] == "Portugal" and ev["location"]["latitude"] == 38.7
    assert ev["event_url"] == "https://example.com/m"
    assert ev["source"] == {"name": "S", "url": None, "source_event_id": "42"}


def test_normalize_fixes_reversed_dates_with_warning():
    ev, warnings = normalize_event(make_raw(start_date=days(10), end_date=days(5)))
    assert ev["end_date"] == ev["start_date"]
    assert any("end_date" in w for w in warnings)


def test_normalize_half_coordinates_dropped():
    ev, _ = normalize_event(make_raw(location={"city": "X", "latitude": 10}))
    assert ev["location"]["latitude"] is None and ev["location"]["longitude"] is None


def test_normalize_honours_cancelled():
    ev, _ = normalize_event(make_raw(status="cancelled"))
    assert ev["status"] == "cancelled"


@pytest.mark.parametrize("bad", [{"title": ""}, {"title": "ab"}, {"start_date": "soon"}, {"start_date": None}])
def test_normalize_rejects_invalid(bad):
    with pytest.raises(ValidationFailure):
        normalize_event(make_raw(**bad))
