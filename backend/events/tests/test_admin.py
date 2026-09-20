import pytest

from backend.events.tests.conftest import days, make_raw
from backend.events.tests.test_api import add


def body(**over):
    b = {
        "title": "Admin Created Summit", "event_type": "summit", "start_date": days(45), "end_date": days(46),
        "location": {"city": "Lisbon", "country": "PT"}, "categories": ["ai"], "event_url": "https://example.com/admin-summit",
        "organizer": {"name": "Admin Org"}, "registration": {"price": 0},
    }
    b.update(over)
    return b


# ---------------------------------------------------------------------------- auth
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}, {"X-Admin-Key": ""}])
def test_admin_requires_the_key(client, headers):
    for method, path in (("get", "/api/admin/events"), ("get", "/api/admin/stats"), ("post", "/api/admin/events"), ("delete", "/api/admin/events/x")):
        r = getattr(client, method)(path, headers=headers)
        assert r.status_code == 401, (method, path)


def test_admin_disabled_when_no_key_is_configured(client, monkeypatch):
    from backend.events.routes import admin as admin_routes

    class S:
        admin_api_key = ""

    monkeypatch.setattr(admin_routes, "get_settings", lambda: S())
    r = client.get("/api/admin/events", headers={"X-Admin-Key": "anything"})
    assert r.status_code == 503 and "EVENT_ADMIN_API_KEY" in r.json()["detail"]


def test_session_check(client, admin_headers):
    assert client.get("/api/admin/session", headers=admin_headers).json() == {"ok": True}


# ---------------------------------------------------------------------------- CRUD
def test_create_edit_delete_lifecycle(client, admin_headers):
    r = client.post("/api/admin/events", json=body(), headers=admin_headers)
    assert r.status_code == 201
    ev = r.json()
    assert ev["slug"] == "admin-created-summit-" + days(45)[:4] and ev["review_status"] == "approved" and ev["manually_edited"] is True
    assert ev["location"]["country"] == "Portugal" and ev["categories"] == ["Artificial Intelligence"]
    assert ev["registration"]["ticket_type"] == "free" and ev["source"]["name"] == "manual"
    assert client.get(f"/api/events/{ev['id']}").status_code == 200          # published immediately

    up = client.put(f"/api/admin/events/{ev['id']}", json={"title": "Renamed Summit", "location": {"venue": "Pavilion"}}, headers=admin_headers)
    assert up.status_code == 200
    u = up.json()
    assert u["title"] == "Renamed Summit" and u["slug"] == ev["slug"]          # URL stays stable
    assert u["location"]["venue"] == "Pavilion" and u["location"]["city"] == "Lisbon"  # nested merge, not replace

    assert client.delete(f"/api/admin/events/{ev['id']}", headers=admin_headers).json()["deleted"] is True
    assert client.get(f"/api/events/{ev['id']}").status_code == 404
    assert client.delete(f"/api/admin/events/{ev['id']}", headers=admin_headers).status_code == 404


def test_slug_change_keeps_old_url_working(client, admin_headers):
    ev = client.post("/api/admin/events", json=body(), headers=admin_headers).json()
    r = client.put(f"/api/admin/events/{ev['id']}", json={"slug": "new-pretty-slug"}, headers=admin_headers)
    assert r.json()["slug"] == "new-pretty-slug"
    assert client.get("/api/events/slug/new-pretty-slug").status_code == 200
    assert client.get(f"/api/events/slug/{ev['slug']}").json()["id"] == ev["id"]   # old slug still resolves


def test_validation_errors_are_400_with_clear_messages(client, admin_headers):
    assert client.post("/api/admin/events", json={"title": "No dates"}, headers=admin_headers).status_code == 400
    r = client.post("/api/admin/events", json=body(start_date="soon"), headers=admin_headers)
    assert r.status_code == 400 and "start_date" in r.json()["detail"]
    r = client.post("/api/admin/events", json=body(event_type="not_a_type"), headers=admin_headers)
    assert r.status_code == 400
    ev = client.post("/api/admin/events", json=body(), headers=admin_headers).json()
    assert client.put(f"/api/admin/events/{ev['id']}", json={}, headers=admin_headers).status_code == 400
    assert client.put(f"/api/admin/events/{ev['id']}", json={"start_date": "31/31/2026"}, headers=admin_headers).status_code == 400
    assert client.put("/api/admin/events/missing", json={"title": "x y z"}, headers=admin_headers).status_code == 404


def test_unsafe_urls_are_stripped_on_save(client, admin_headers):
    ev = client.post("/api/admin/events", json=body(event_url="javascript:alert(1)", image_url="data:image/png;base64,AAA",
                                                    organizer={"name": "O", "website": "javascript:x"}), headers=admin_headers).json()
    assert ev["event_url"] is None and ev["image_url"] is None and ev["organizer"]["website"] is None


def test_admin_list_sees_everything_and_filters(client, db, admin_headers):
    add(db, title="Live One")
    add(db, title="Waiting One", review="pending")
    add(db, title="Refused One", review="rejected")
    h = admin_headers
    assert client.get("/api/admin/events?limit=100", headers=h).json()["total"] == 3
    assert {e["title"] for e in client.get("/api/admin/events?review_status=pending", headers=h).json()["events"]} == {"Waiting One"}
    assert {e["title"] for e in client.get("/api/admin/events?review_status=pending,rejected", headers=h).json()["events"]} == {"Waiting One", "Refused One"}
    assert client.get("/api/admin/events?needs_review=true", headers=h).json()["total"] == 1
    assert client.get("/api/admin/events?search=refused", headers=h).json()["total"] == 1
    assert client.get("/api/admin/events?source=t", headers=h).json()["total"] == 3
    ev = client.get("/api/admin/events", headers=h).json()["events"][0]
    assert {"review_status", "source", "manually_edited"} <= set(ev)
    assert client.get("/api/admin/events?review_status=bogus", headers=h).status_code == 400


# ------------------------------------------------------------------------ moderation
def test_approve_and_reject(client, db, admin_headers):
    eid = add(db, title="Needs Review", review="pending")
    assert client.get(f"/api/events/{eid}").status_code == 404
    assert client.post(f"/api/admin/events/{eid}/approve", headers=admin_headers).json()["review_status"] == "approved"
    assert client.get(f"/api/events/{eid}").status_code == 200
    assert client.post(f"/api/admin/events/{eid}/reject", headers=admin_headers).json()["review_status"] == "rejected"
    assert client.get(f"/api/events/{eid}").status_code == 404
    assert client.post("/api/admin/events/nope/approve", headers=admin_headers).status_code == 404


def test_mark_duplicate_hides_event_and_guards_bad_input(client, db, admin_headers):
    a, b = add(db, title="Original"), add(db, title="Copy Of It")
    r = client.post(f"/api/admin/events/{b}/duplicate", json={"duplicate_of": a}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["review_status"] == "duplicate" and r.json()["duplicate_of"] == a
    assert client.get(f"/api/events/{b}").status_code == 404
    assert client.post(f"/api/admin/events/{a}/duplicate", json={"duplicate_of": a}, headers=admin_headers).status_code == 400
    c = add(db, title="Third")
    assert client.post(f"/api/admin/events/{c}/duplicate", json={"duplicate_of": b}, headers=admin_headers).status_code == 400  # b is itself a duplicate


def test_merge_combines_fields_sources_and_slugs(client, db, admin_headers):
    a = add(db, title="Master Event", image_url=None, topics=["A"])
    b = add(db, title="Master Event Copy", image_url="https://example.com/x.png", topics=["B"], source={"name": "Other", "source_event_id": "o1"})
    slug_b = db["events"].find_one({"_id": b})["slug"]
    r = client.post("/api/admin/merge", json={"master_id": a, "duplicate_ids": [b]}, headers=admin_headers)
    assert r.status_code == 200
    m = r.json()
    assert m["image_url"] == "https://example.com/x.png" and set(m["topics"]) == {"A", "B"}
    assert [s["name"] for s in m["other_sources"]] == ["Other"] and m["merged_from"][0]["id"] == b
    assert db["events"].count_documents({"_id": b}) == 0
    assert client.get(f"/api/events/slug/{slug_b}").json()["id"] == a       # the merged event's URL redirects to the master
    assert client.post("/api/admin/merge", json={"master_id": a, "duplicate_ids": [a]}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/merge", json={"master_id": a, "duplicate_ids": ["ghost"]}, headers=admin_headers).status_code == 404
    assert client.post("/api/admin/merge", json={"master_id": a, "duplicate_ids": []}, headers=admin_headers).status_code == 400


def test_duplicate_suggestions_and_dismissal(client, db, admin_headers):
    a = add(db, title="AI Summit 2026", source={"name": "A", "source_event_id": "1"})
    b = add(db, title="Global AI Summit 2026", source={"name": "B", "source_event_id": "2"})
    add(db, title="Totally Unrelated Gala", start_date=days(90), end_date=days(90))
    s = client.get("/api/admin/duplicates", headers=admin_headers).json()
    assert len(s) == 1 and {s[0]["a"]["id"], s[0]["b"]["id"]} == {a, b} and s[0]["reasons"] and s[0]["score"] >= 0.75
    assert client.post("/api/admin/duplicates/dismiss", json={"a_id": a, "b_id": b}, headers=admin_headers).status_code == 200
    assert client.get("/api/admin/duplicates", headers=admin_headers).json() == []      # stays dismissed


def test_approving_a_flagged_event_means_not_a_duplicate(client, db, admin_headers):
    a = add(db, title="AI Summit 2026", source={"name": "A", "source_event_id": "1"})
    b = add(db, title="Global AI Summit 2026", source={"name": "B", "source_event_id": "2"})   # flagged -> pending
    flagged = db["events"].find_one({"_id": b})
    assert flagged["review_status"] == "pending" or flagged.get("possible_duplicate_of")
    client.post(f"/api/admin/events/{b}/approve", headers=admin_headers)
    assert client.get("/api/admin/duplicates", headers=admin_headers).json() == []
    assert client.get(f"/api/events/{b}").status_code == 200 and a


def test_reprocess_refills_classification(client, db, admin_headers):
    eid = add(db, title="Kubernetes Hackathon", event_type="other", description="Build cloud native tools with Kubernetes and serverless.")
    db["events"].update_one({"_id": eid}, {"$set": {"categories": [], "summary": None, "topics": []}})
    r = client.post(f"/api/admin/events/{eid}/reprocess", json={}, headers=admin_headers).json()
    assert r["event_type"] == "hackathon" and r["summary"] and "Cloud" in r["categories"]
    assert client.post(f"/api/admin/events/{eid}/reprocess", headers=admin_headers).status_code == 200   # body optional
    assert client.post("/api/admin/events/nope/reprocess", headers=admin_headers).status_code == 404


# ------------------------------------------------------------ stats + ingestion health
def test_stats_sources_runs_and_errors(client, db, admin_headers):
    from backend.events.processors.pipeline import run_collector
    from backend.events.tests.test_pipeline import FakeCollector

    add(db, title="One")
    add(db, title="Two", review="pending")
    run_collector(db, FakeCollector([make_raw(), {"title": "x", "start_date": "bad"}]), use_ai=False)

    st = client.get("/api/admin/stats", headers=admin_headers).json()
    assert st["total"] >= 3 and st["by_review_status"]["pending"] >= 1 and st["ingestion_errors_24h"] == 1 and st["needs_review"] >= 1

    rows = {r["name"]: r for r in client.get("/api/admin/sources", headers=admin_headers).json()}
    assert rows["eventbrite"]["health"] == "not_configured" and rows["meetup"]["configured"] is False
    assert rows["TestSource"]["health"] == "manual" and rows["TestSource"]["events"] == 1   # events from sources without a collector

    runs = client.get("/api/admin/ingestion/runs", headers=admin_headers).json()
    assert runs[0]["source"] == "fake" and runs[0]["status"] == "partial" and runs[0]["counts"]["created"] == 1
    errs = client.get("/api/admin/ingestion/errors", headers=admin_headers).json()
    assert len(errs) == 1 and errs[0]["source"] == "fake" and errs[0]["error_type"] == "validation" and errs[0]["record"]
    assert client.get("/api/admin/ingestion/errors?source=other", headers=admin_headers).json() == []
