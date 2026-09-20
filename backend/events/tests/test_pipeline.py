import pytest

from backend.events.processors.pipeline import find_by_identity, ingest_event, run_collector
from backend.events.services import admin_service as admin
from backend.events.services import event_service as svc
from backend.events.tests.conftest import days, make_raw

_n = 0


def add(db, **over):
    """Ingest a valid event with a unique source id; returns the IngestResult."""
    global _n
    _n += 1
    raw = make_raw(**over)
    raw.setdefault("source", {})
    if "source" not in over:
        raw["source"] = {"name": "TestSource", "source_event_id": f"t-{_n}"}
    return ingest_event(db, raw, use_ai=False)


def test_create_sets_identity_slug_review_and_classification(db):
    r = add(db, title="AI & ML Summit 2026", event_type=None, summary=None, categories=[])
    assert r.action == "created"
    doc = db["events"].find_one({"_id": r.event_id})
    assert doc["slug"] == "ai-ml-summit-2026"
    assert doc["review_status"] == "approved" and doc["manually_edited"] is False
    assert doc["event_type"] and doc["summary"] and doc["categories"]  # filled by rules
    assert doc["created_at"] and doc["updated_at"] and doc["last_verified"]


def test_reingest_same_source_id_is_idempotent_and_updates(db):
    src = {"name": "S", "source_event_id": "42"}
    a = ingest_event(db, make_raw(source=src), use_ai=False)
    b = ingest_event(db, make_raw(source=src), use_ai=False)
    assert (a.action, b.action) == ("created", "unchanged") and a.event_id == b.event_id
    c = ingest_event(db, make_raw(source=src, description="A brand new description of the summit."), use_ai=False)
    assert c.action == "updated" and c.event_id == a.event_id
    assert "brand new" in db["events"].find_one({"_id": a.event_id})["description"]
    assert db["events"].count_documents({}) == 1


def test_slug_collisions_get_unique_slugs(db):
    a = add(db, title="Same Title", location={"city": "Berlin", "country": "Germany"}, start_date=days(40), end_date=days(40))
    b = add(db, title="Same Title", location={"city": "Paris", "country": "France"}, start_date=days(40), end_date=days(40))
    c = add(db, title="Same Title", location={"city": "Paris", "country": "France"}, start_date=days(80), end_date=days(80))
    slugs = {db["events"].find_one({"_id": x.event_id})["slug"] for x in (a, b, c)}
    assert len(slugs) == 3


def test_invalid_records_are_rejected_without_writing(db):
    r = ingest_event(db, make_raw(title="", start_date="whenever"), use_ai=False)
    assert r.action == "invalid" and r.errors
    assert db["events"].count_documents({}) == 0


def test_past_events_are_skipped(db):
    r = add(db, start_date=days(-20), end_date=days(-19))
    assert r.action == "skipped" and db["events"].count_documents({}) == 0


def test_cross_source_duplicate_is_merged_not_created(db):
    a = ingest_event(db, make_raw(title="AI & ML Summit 2026", source={"name": "A", "source_event_id": "1"}, image_url=None), use_ai=False)
    b = ingest_event(
        db,
        make_raw(title="AI and ML Summit 2026", source={"name": "B", "source_event_id": "77"}, image_url="https://example.com/i.jpg"),
        use_ai=False,
    )
    assert b.action == "merged" and b.duplicate_of == a.event_id
    assert db["events"].count_documents({}) == 1
    master = db["events"].find_one({"_id": a.event_id})
    assert master["image_url"] == "https://example.com/i.jpg"  # gap filled from the other source
    assert master["other_sources"][0]["name"] == "B"
    # re-ingesting the merged source's record must not resurrect a second event
    again = ingest_event(db, make_raw(title="AI and ML Summit 2026", source={"name": "B", "source_event_id": "77"}), use_ai=False)
    assert again.action in ("unchanged", "updated") and db["events"].count_documents({}) == 1


def test_possible_duplicate_is_stored_pending_and_hidden(db):
    a = ingest_event(db, make_raw(title="AI Summit 2026", source={"name": "A", "source_event_id": "1"}), use_ai=False)
    b = ingest_event(db, make_raw(title="Global AI Summit 2026", source={"name": "B", "source_event_id": "2"}), use_ai=False)
    assert b.action == "flagged" and b.duplicate_of == a.event_id
    doc = db["events"].find_one({"_id": b.event_id})
    assert doc["review_status"] == "pending" and doc["possible_duplicate_of"] == a.event_id
    assert svc.get_event(db, b.event_id) is None  # not public


def test_no_event_url_or_auto_approve_off_means_pending(db):
    a = add(db, event_url=None)
    b = ingest_event(db, make_raw(source={"name": "X", "source_event_id": "9"}, title="Other Event"), auto_approve=False, use_ai=False)
    assert db["events"].find_one({"_id": a.event_id})["review_status"] == "pending"
    assert db["events"].find_one({"_id": b.event_id})["review_status"] == "pending"


def test_admin_edited_events_are_protected_from_source_updates(db):
    src = {"name": "S", "source_event_id": "5"}
    r = ingest_event(db, make_raw(source=src), use_ai=False)
    admin.update_event(db, r.event_id, {"title": "Curated Title By Admin"})
    res = ingest_event(db, make_raw(source=src, title="Source Changed Title"), use_ai=False)
    assert res.action == "unchanged"
    assert db["events"].find_one({"_id": r.event_id})["title"] == "Curated Title By Admin"


def test_dry_run_writes_nothing(db):
    r = ingest_event(db, make_raw(), use_ai=False, dry_run=True)
    assert r.action == "created" and db["events"].count_documents({}) == 0


def test_classification_failure_never_blocks_storage(db, monkeypatch):
    from backend.events.processors import pipeline

    def boom(*a, **k):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(pipeline, "classify_event", boom)
    r = add(db)
    assert r.action == "created" and any("classification failed" in w for w in r.warnings)
    assert db["events"].find_one({"_id": r.event_id})["event_type"]


# ------------------------------------------------------------------- run_collector
class FakeCollector:
    name, label, source_name, source_url = "fake", "Fake", "FakeSource", "https://example.com"

    def __init__(self, records, fail_after=None):
        self.records, self.fail_after = records, fail_after

    def is_configured(self):
        return True

    def collect(self):
        for i, r in enumerate(self.records):
            if self.fail_after is not None and i == self.fail_after:
                raise ConnectionError("upstream went away")
            yield r


def test_run_collector_isolates_bad_records_and_logs_them(db):
    good = make_raw(source={"name": "FakeSource", "source_event_id": "g1"})
    bad = {"title": "x", "start_date": "nonsense"}
    also_good = make_raw(title="Second Good Event", source={"name": "FakeSource", "source_event_id": "g2"})
    s = run_collector(db, FakeCollector([good, bad, also_good]), use_ai=False)
    assert s["status"] == "partial"
    assert s["counts"]["created"] == 2 and s["counts"]["invalid"] == 1
    assert db["events"].count_documents({}) == 2
    assert db["ingestion_errors"].count_documents({"source": "fake"}) == 1
    run = db["ingestion_runs"].find_one({"source": "fake"})
    assert run["status"] == "partial" and run["finished_at"]


def test_run_collector_survives_source_failure_midway(db):
    recs = [make_raw(source={"name": "FakeSource", "source_event_id": "a"}), make_raw(title="Never Reached", source={"name": "FakeSource", "source_event_id": "b"})]
    s = run_collector(db, FakeCollector(recs, fail_after=1), use_ai=False)
    assert s["status"] == "partial" and "upstream went away" in s["error"]
    assert db["events"].count_documents({}) == 1


def test_run_collector_total_failure_is_reported(db):
    s = run_collector(db, FakeCollector([make_raw()], fail_after=0), use_ai=False)
    assert s["status"] == "failed" and db["events"].count_documents({}) == 0
    assert db["ingestion_errors"].count_documents({}) == 1


def test_run_collector_dry_run_logs_nothing(db):
    s = run_collector(db, FakeCollector([make_raw()]), use_ai=False, dry_run=True)
    assert s["status"] == "success"
    assert db["events"].count_documents({}) == 0 and db["ingestion_runs"].count_documents({}) == 0


def test_find_by_identity_sees_merged_sources(db):
    a = ingest_event(db, make_raw(title="Merge Master Event", source={"name": "A", "source_event_id": "1"}), use_ai=False)
    db["events"].update_one({"_id": a.event_id}, {"$set": {"other_sources": [{"name": "B", "source_event_id": "9"}]}})
    assert find_by_identity(db, "B", "9")["_id"] == a.event_id
    assert find_by_identity(db, "B", "10") is None
    assert find_by_identity(db, None, "9") is None


def test_refresh_statuses_moves_events_through_lifecycle(db):
    for eid, start, end, status in (
        ("e_done", days(-10), days(-5), "upcoming"),
        ("e_now", days(-1), days(2), "upcoming"),
        ("e_next", days(5), days(6), "ongoing"),
        ("e_cancel", days(-10), days(-5), "cancelled"),
    ):
        db["events"].insert_one({"_id": eid, "slug": eid, "title": eid, "start_date": start, "end_date": end, "status": status, "review_status": "approved"})
    out = svc.refresh_statuses(db)
    got = {d["_id"]: d["status"] for d in db["events"].find()}
    assert got == {"e_done": "completed", "e_now": "ongoing", "e_next": "upcoming", "e_cancel": "cancelled"}
    assert out["completed"] == 1


def test_source_identity_is_unique_at_the_database_level(db):
    from pymongo.errors import DuplicateKeyError

    doc = {"title": "T", "start_date": days(5), "end_date": days(5), "source": {"name": "S", "source_event_id": "1"}}
    db["events"].insert_one({"_id": "a", "slug": "a", **doc})
    with pytest.raises(DuplicateKeyError):
        db["events"].insert_one({"_id": "b", "slug": "b", **doc})
    # events without a source id are not constrained
    db["events"].insert_one({"_id": "c", "slug": "c", "title": "T", "source": {"name": "S"}})
    db["events"].insert_one({"_id": "d", "slug": "d", "title": "T", "source": {"name": "S"}})
