import pytest

from backend.events.processors.pipeline import ingest_event
from backend.events.tests.conftest import days, make_raw

_n = 0


def add(db, review="approved", **over):
    global _n
    _n += 1
    over.setdefault("source", {"name": "T", "source_event_id": f"api-{_n}"})
    over.setdefault("title", f"Generic Event {_n}")
    over.setdefault("description", "A generic professional gathering with sessions and networking.")
    over.setdefault("location", {"venue": f"Hall {_n}", "city": "Berlin", "country": "Germany"})
    r = ingest_event(db, make_raw(**over), use_ai=False)
    if review != "approved":
        db["events"].update_one({"_id": r.event_id}, {"$set": {"review_status": review}})
    return r.event_id


# ------------------------------------------------------------------------- public list
def test_list_shape_pagination_and_summary_projection(client, db):
    for i in range(5):
        add(db, start_date=days(10 + i), end_date=days(10 + i))
    r = client.get("/api/events?limit=2&page=2")
    body = r.json()
    assert r.status_code == 200
    assert {k: body[k] for k in ("page", "limit", "total", "total_pages")} == {"page": 2, "limit": 2, "total": 5, "total_pages": 3}
    assert len(body["events"]) == 2
    assert "description" not in body["events"][0] and "image_url" in body["events"][0]
    assert client.get("/api/events?page=99").json()["events"] == []


def test_default_listing_only_shows_approved_upcoming_or_ongoing(client, db):
    ok = add(db, title="Visible One")
    add(db, title="Pending One", review="pending")
    add(db, title="Rejected One", review="rejected")
    add(db, title="Dup One", review="duplicate")
    add(db, title="Cancelled One", status="cancelled")
    add(db, title="Ongoing One", start_date=days(-1), end_date=days(2))
    titles = {e["title"] for e in client.get("/api/events?limit=100").json()["events"]}
    assert titles == {"Visible One", "Ongoing One"}
    # explicit status opt-in
    assert {e["title"] for e in client.get("/api/events?status=cancelled").json()["events"]} == {"Cancelled One"}
    assert ok


def test_stale_stored_status_never_leaks_ended_events(client, db):
    eid = add(db, title="Just Ended")
    db["events"].update_one({"_id": eid}, {"$set": {"status": "upcoming", "start_date": days(-5), "end_date": days(-2)}})
    assert client.get("/api/events").json()["total"] == 0


def test_limit_is_capped_and_validated(client):
    r = client.get("/api/events?limit=101")
    assert r.status_code == 400 and r.json()["detail"] == "Invalid request"
    assert client.get("/api/events?page=0").status_code == 400
    assert client.get("/api/events?limit=abc").status_code == 400


# --------------------------------------------------------------------------- search
def test_search_matches_word_starts_not_substrings(client, db):
    add(db, title="AI & ML Summit", categories=["Artificial Intelligence"])
    add(db, title="Spain Travel Expo", location={"city": "Madrid", "country": "Spain"}, description="Training days in Spain.")
    add(db, title="Cooking Festival", organizer={"name": "Kitchen Guild"})
    titles = lambda q: {e["title"] for e in client.get(f"/api/events?search={q}").json()["events"]}  # noqa: E731
    assert titles("AI") == {"AI & ML Summit"}  # not Spain / training
    assert titles("madrid") == {"Spain Travel Expo"}
    assert titles("kitchen") == {"Cooking Festival"}  # organizer
    assert titles("germany") == {"AI & ML Summit", "Cooking Festival"}  # country
    assert titles("artificial") == {"AI & ML Summit"}  # category
    assert titles("summit%20berlin") == {"AI & ML Summit"}  # every token must match
    assert titles("zzzz") == set()


def test_search_input_is_treated_literally(client, db):
    add(db, title="C++ Conference")
    add(db, title="Plain Event")
    r = client.get("/api/events", params={"search": ".*"})
    assert r.status_code == 200 and r.json()["total"] == 0  # regex metacharacters are escaped
    r = client.get("/api/events", params={"search": "C++"})
    assert {e["title"] for e in r.json()["events"]} == {"C++ Conference"}
    assert client.get("/api/events", params={"search": "(unclosed["}).status_code == 200


# --------------------------------------------------------------------------- filters
def test_filters(client, db):
    add(db, title="Berlin Startup Night", event_type="startup_event", categories=["Startups"], registration={"price": 0})
    add(db, title="Paris Cloud Conf", event_type="conference", categories=["Cloud"], location={"city": "Paris", "state": "IDF", "country": "France"}, registration={"price": 99, "currency": "EUR"})
    add(db, title="Online Bootcamp", event_type="training", is_online=True, location={}, registration={"price": 10})
    add(db, title="Hybrid Meetup", event_type="meetup", format="hybrid")
    q = lambda s: {e["title"] for e in client.get(f"/api/events?{s}").json()["events"]}  # noqa: E731
    assert q("event_type=startup") == {"Berlin Startup Night"}                       # friendly alias
    assert q("event_type=conference,training") == {"Paris Cloud Conf", "Online Bootcamp"}
    assert q("country=france") == {"Paris Cloud Conf"}                                # case-insensitive
    assert q("country=France&state=idf&city=PARIS") == {"Paris Cloud Conf"}
    assert q("category=cloud") == {"Paris Cloud Conf"}
    assert q("category=Startups,Cloud") == {"Berlin Startup Night", "Paris Cloud Conf"}
    assert q("is_online=true") == {"Online Bootcamp"} and "Online Bootcamp" not in q("is_online=false")
    assert q("format=hybrid") == {"Hybrid Meetup"}
    assert q("price_type=free") == {"Berlin Startup Night"}
    assert q("price_type=paid") == {"Paris Cloud Conf", "Online Bootcamp"}


@pytest.mark.parametrize("qs", ["event_type=nope", "format=teleport", "price_type=cheap", "status=maybe", "start_date=2026-99-99", "sort=random", "start_date=2026-05-02&end_date=2026-05-01"])
def test_bad_filter_values_are_400_not_500(client, qs):
    r = client.get(f"/api/events?{qs}")
    assert r.status_code == 400 and "detail" in r.json()


def test_date_range_selects_overlapping_events(client, db):
    add(db, title="Inside", start_date=days(10), end_date=days(11))
    add(db, title="Straddles Start", start_date=days(3), end_date=days(8))
    add(db, title="Later", start_date=days(40), end_date=days(41))
    got = lambda a, b: {e["title"] for e in client.get(f"/api/events?start_date={days(a)}&end_date={days(b)}").json()["events"]}  # noqa: E731
    assert got(9, 12) == {"Inside"}
    assert got(7, 12) == {"Straddles Start", "Inside"}          # overlap, not containment
    assert got(30, 50) == {"Later"}
    assert client.get(f"/api/events?start_date={days(30)}").json()["total"] == 1  # open-ended


def test_sorting(client, db):
    a = add(db, title="Event Alpha", start_date=days(30), end_date=days(30))
    b = add(db, title="Event Bravo", start_date=days(10), end_date=days(10))
    c = add(db, title="Event Charlie", start_date=days(20), end_date=days(20))
    order = lambda s: [e["title"] for e in client.get(f"/api/events?sort={s}").json()["events"]]  # noqa: E731
    assert order("soonest") == ["Event Bravo", "Event Charlie", "Event Alpha"] and order("latest") == ["Event Alpha", "Event Charlie", "Event Bravo"]
    assert client.get("/api/events").json()["events"][0]["title"] == "Event Bravo"       # default = soonest
    assert order("recently_added")[0] == "Event Charlie"
    db["events"].update_one({"_id": a}, {"$set": {"updated_at": __import__("datetime").datetime(2099, 1, 1, tzinfo=__import__("datetime").timezone.utc)}})
    assert order("recently_updated")[0] == "Event Alpha"
    assert b and c


# --------------------------------------------------------------------------- detail
def test_detail_by_id_and_slug_full_payload(client, db):
    eid = add(db, title="Detail Event", description="Full text " * 20, topics=["LLM"], audience=["CTOs"])
    by_id = client.get(f"/api/events/{eid}")
    by_slug = client.get("/api/events/slug/detail-event-" + days(30)[:4])
    assert by_id.status_code == by_slug.status_code == 200
    d = by_slug.json()
    assert d["id"] == eid and d["description"].startswith("Full text") and d["audience"] == ["CTOs"]
    assert d["organizer"]["name"] == "Acme Events" and d["source"]["name"] == "T" and d["last_verified"]
    assert set(d) >= {"location", "registration", "topics", "categories", "event_url", "source", "timezone"}
    assert "review_status" not in d  # admin-only fields stay private


def test_hidden_or_missing_events_are_404(client, db):
    pend = add(db, title="Hidden Pending", review="pending")
    assert client.get(f"/api/events/{pend}").status_code == 404
    assert client.get("/api/events/slug/hidden-pending-" + days(30)[:4]).status_code == 404
    r = client.get("/api/events/evt_nope")
    assert r.status_code == 404 and r.json() == {"detail": "Event not found"}
    assert client.get("/api/events/slug/nope").status_code == 404


def test_sparse_documents_never_break_reads(client, db):
    db["events"].insert_one({"_id": "sparse", "slug": "sparse-one", "title": "Sparse", "start_date": days(5), "end_date": days(5),
                             "status": "upcoming", "review_status": "approved", "location": None, "organizer": None, "categories": None})
    assert client.get("/api/events").json()["events"][0]["location"] == {k: None for k in ("venue", "address", "city", "state", "country", "latitude", "longitude")}
    d = client.get("/api/events/slug/sparse-one").json()
    assert d["categories"] == [] and d["organizer"]["name"] is None and d["source"]["name"] is None


# ------------------------------------------------------------------------- facets
def test_types_categories_locations(client, db):
    add(db, event_type="conference", categories=["Cloud"], location={"city": "Paris", "state": "IDF", "country": "France"})
    add(db, event_type="conference", categories=["Cloud", "Startups"], location={"city": "Lyon", "state": "ARA", "country": "France"})
    add(db, event_type="meetup", categories=["Startups"], location={"city": "Berlin", "country": "Germany"})
    types = {t["value"]: t["count"] for t in client.get("/api/events/types").json()}
    assert types["conference"] == 2 and types["meetup"] == 1 and types["hackathon"] == 0 and len(types) == 13
    cats = {c["name"]: c["count"] for c in client.get("/api/events/categories").json()}
    assert cats["Cloud"] == 2 and cats["Startups"] == 2
    assert "Blockchain" in {c["name"] for c in client.get("/api/events/categories?include_empty=true").json()}
    loc = client.get("/api/events/locations").json()
    assert {c["name"]: c["count"] for c in loc["countries"]} == {"France": 2, "Germany": 1} and loc["states"] == []
    loc = client.get("/api/events/locations?country=france").json()
    assert {s["name"] for s in loc["states"]} == {"IDF", "ARA"} and {c["name"] for c in loc["cities"]} == {"Paris", "Lyon"}
    assert {c["name"] for c in client.get("/api/events/locations?country=France&state=IDF").json()["cities"]} == {"Paris"}


# ------------------------------------------------------------------ error handling
def test_unexpected_errors_are_500_without_internals(client, monkeypatch):
    from backend.events.services import event_service

    def boom(*a, **k):
        raise RuntimeError("secret connection string mongodb://user:pw@host")

    monkeypatch.setattr(event_service, "list_events", boom)
    r = client.get("/api/events")
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
    assert "pw@host" not in r.text and "Traceback" not in r.text


def test_database_down_is_503(client, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    from backend.events.services import event_service

    def down(*a, **k):
        raise ServerSelectionTimeoutError("localhost:27017: timed out")

    monkeypatch.setattr(event_service, "list_events", down)
    r = client.get("/api/events")
    assert r.status_code == 503 and "localhost" not in r.text


def test_missing_configuration_is_503_not_a_crash(client, monkeypatch):
    from backend.events.errors import ApiError
    from backend.events.routes import events as events_routes

    def unconfigured():
        raise ApiError(503, "Event Hub is not configured: set EVENT_MONGO_URI in .env")

    client.app.dependency_overrides[events_routes.get_db] = unconfigured
    r = client.get("/api/events")
    client.app.dependency_overrides.clear()
    assert r.status_code == 503 and "EVENT_MONGO_URI" in r.json()["detail"]


# ------------------------------------------------------- integration with Casefile app
def test_event_hub_is_mounted_in_the_real_casefile_app_without_disturbing_it(db):
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/events?limit=1").status_code == 200
    assert c.get("/health").status_code == 200                            # existing endpoint untouched
    paths = set(app.openapi()["paths"])
    assert {"/api/company-research", "/api/aeo-geo-audit", "/api/export-pdf"} <= paths   # Casefile API intact
    assert {"/api/events", "/api/events/slug/{slug}", "/api/admin/events"} <= paths
    # Casefile keeps FastAPI's default 422 for its own validation errors (error mapping is scoped to the hub)
    assert c.post("/api/company-research", json={}).status_code == 422
