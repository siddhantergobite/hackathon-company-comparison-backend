import pytest

from backend.news import pipeline
from backend.news.collectors.base import CollectorError
from backend.news.services import admin_service as admin
from backend.news.tests.conftest import ago, ingest, make_raw, make_source
from backend.news.tests.test_ai_pipeline import Fake


def public_dns(monkeypatch, ip="93.184.216.34"):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])


# ---------------------------------------------------------------------------------- auth
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "wrong"}, {"X-Admin-Key": ""}])
def test_admin_requires_the_key(client, headers):
    for method, path in (("get", "/api/admin/news/sources"), ("get", "/api/admin/news/stats"), ("post", "/api/admin/news/sources"), ("delete", "/api/admin/news/sources/x"), ("post", "/api/admin/news/enrich")):
        assert getattr(client, method)(path, headers=headers).status_code == 401, (method, path)


def test_admin_is_disabled_without_a_key(client, monkeypatch):
    from backend.news.routes import admin as routes

    class S:
        admin_api_key = ""

    monkeypatch.setattr(routes, "get_settings", lambda: S())
    r = client.get("/api/admin/news/sources", headers={"X-Admin-Key": "x"})
    assert r.status_code == 503 and "NEWS_ADMIN_API_KEY" in r.json()["detail"]


def test_session(client, admin_headers):
    assert client.get("/api/admin/news/session", headers=admin_headers).json() == {"ok": True}


# --------------------------------------------------------------------------------- sources
def test_add_source_then_it_shows_up_with_health(client, admin_headers, monkeypatch):
    public_dns(monkeypatch)
    body = {"name": "Example Wire", "type": "rss", "url": "https://example.org/rss.xml", "category": "technology", "poll_minutes": 30, "priority": 4}
    r = client.post("/api/admin/news/sources", json=body, headers=admin_headers)
    assert r.status_code == 201
    s = r.json()
    assert s["id"] == "example-wire" and s["enabled"] is True and s["health"] == "never" and s["poll_minutes"] == 30 and s["due"] is True
    rows = client.get("/api/admin/news/sources", headers=admin_headers).json()
    assert [x["id"] for x in rows] == ["example-wire"]
    assert client.post("/api/admin/news/sources", json=body, headers=admin_headers).status_code == 409


@pytest.mark.parametrize("url,ip", [
    ("http://localhost/rss", "127.0.0.1"), ("http://intranet.corp/rss", "10.0.0.5"), ("http://192.168.1.10/rss", "192.168.1.10"),
    ("http://metadata.internal/latest", "169.254.169.254"), ("http://[::1]/rss", "::1"),
])
def test_private_and_internal_feed_urls_are_refused(client, admin_headers, monkeypatch, url, ip):
    public_dns(monkeypatch, ip)
    r = client.post("/api/admin/news/sources", json={"name": "Sneaky", "url": url}, headers=admin_headers)
    assert r.status_code == 400 and "private or internal" in r.json()["detail"]


@pytest.mark.parametrize("url", ["ftp://example.org/rss", "javascript:alert(1)", "not a url", "", "file:///etc/passwd"])
def test_only_http_feed_urls_are_accepted(client, admin_headers, url):
    r = client.post("/api/admin/news/sources", json={"name": "Bad Url Source", "url": url}, headers=admin_headers)
    assert r.status_code == 400


def test_source_validation(client, admin_headers, monkeypatch):
    public_dns(monkeypatch)
    ok = {"name": "Valid One", "url": "https://example.org/rss.xml"}
    assert client.post("/api/admin/news/sources", json={**ok, "poll_minutes": 0}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/news/sources", json={**ok, "priority": 9}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/news/sources", json={**ok, "category": "astrology"}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/news/sources", json={**ok, "type": "carrier-pigeon"}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/news/sources", json={"name": "NewsAPI No Scope", "type": "newsapi"}, headers=admin_headers).status_code == 400
    assert client.post("/api/admin/news/sources", json={"name": "NewsAPI Scoped", "type": "newsapi", "config": {"sources": "reuters"}}, headers=admin_headers).status_code == 201


def test_edit_disable_enable_and_delete(client, db, admin_headers, monkeypatch):
    public_dns(monkeypatch)
    s = make_source(db, name="Editable", last_fetch_at=ago(minutes=1), consecutive_failures=4, etag='"x"')
    sid = s["_id"]
    r = client.put(f"/api/admin/news/sources/{sid}", json={"poll_minutes": 5, "category": "science", "priority": 5, "url": "https://example.org/new.xml"}, headers=admin_headers).json()
    assert r["poll_minutes"] == 5 and r["category"] == "science" and r["priority"] == 5 and r["etag"] is None        # new URL forgets cache validators
    off = client.post(f"/api/admin/news/sources/{sid}/enabled", json={"enabled": False}, headers=admin_headers).json()
    assert off["enabled"] is False and off["health"] == "disabled" and off["due"] is False
    on = client.post(f"/api/admin/news/sources/{sid}/enabled", json={"enabled": True}, headers=admin_headers).json()
    assert on["enabled"] is True and on["consecutive_failures"] == 0 and on["due"] is True      # re-enabling clears back-off
    assert client.put(f"/api/admin/news/sources/{sid}", json={}, headers=admin_headers).status_code == 400
    assert client.put("/api/admin/news/sources/nope", json={"poll_minutes": 5}, headers=admin_headers).status_code == 404
    ingest(db, make_raw("Article that must survive its source"), s)
    assert client.delete(f"/api/admin/news/sources/{sid}", headers=admin_headers).json()["deleted"] is True
    assert db["news"].count_documents({}) == 1                  # collected articles are kept
    assert client.delete(f"/api/admin/news/sources/{sid}", headers=admin_headers).status_code == 404


def test_health_states(db):
    now = pipeline.utcnow()
    assert admin.health({"enabled": False}, now) == "disabled"
    assert admin.health({"enabled": True, "last_fetch_at": None}, now) == "never"
    assert admin.health({"enabled": True, "last_fetch_at": now, "last_success_at": now, "consecutive_failures": 0, "poll_minutes": 15}, now) == "active"
    assert admin.health({"enabled": True, "last_fetch_at": now, "last_success_at": now, "consecutive_failures": 2}, now) == "failed"
    from datetime import timedelta

    assert admin.health({"enabled": True, "last_fetch_at": now, "last_success_at": now - timedelta(hours=5), "consecutive_failures": 0, "poll_minutes": 15}, now) == "stale"


def test_fetch_now_runs_the_pipeline_and_reports(client, db, admin_headers, monkeypatch):
    s = make_source(db, name="Fetch Me")
    monkeypatch.setattr(pipeline, "make_collector", lambda *a, **k: Fake([make_raw("OpenAI announces new AI model")]))
    r = client.post(f"/api/admin/news/sources/{s['_id']}/fetch", headers=admin_headers).json()
    assert r["status"] == "success" and r["counts"]["created"] == 1 and r["source"]["health"] == "active" and r["source"]["articles_total"] == 1
    monkeypatch.setattr(pipeline, "make_collector", lambda *a, **k: Fake(exc=CollectorError("HTTP 500")))
    bad = client.post(f"/api/admin/news/sources/{s['_id']}/fetch", headers=admin_headers).json()
    assert bad["status"] == "failed" and bad["source"]["health"] == "failed" and "500" in bad["source"]["last_error"]
    assert client.post("/api/admin/news/sources/nope/fetch", headers=admin_headers).status_code == 404


def test_errors_runs_and_stats(client, db, admin_headers, monkeypatch):
    s = make_source(db, name="Noisy")
    pipeline.run_source(db, s, collector=Fake([make_raw("OpenAI announces new AI model"), {"title": "", "link": "x"}]))
    pipeline.run_source(db, db["news_sources"].find_one({"_id": s["_id"]}), collector=Fake(exc=CollectorError("timeout")))
    errs = client.get("/api/admin/news/errors", headers=admin_headers).json()
    assert {e["type"] for e in errs} == {"validation", "CollectorError"} and all(e["source_name"] == "Noisy" for e in errs)
    assert client.get("/api/admin/news/errors?source=other", headers=admin_headers).json() == []
    runs = client.get("/api/admin/news/runs", headers=admin_headers).json()
    assert [r["status"] for r in runs] == ["failed", "partial"]
    st = client.get("/api/admin/news/stats", headers=admin_headers).json()
    assert st["articles"] == 1 and st["stories"] == 1 and st["errors_24h"] == 2 and st["sources_by_health"] == {"failed": 1}


# ------------------------------------------------------------------------------- categories
def test_admin_can_add_a_category_that_immediately_classifies(client, db, admin_headers):
    r = client.post("/api/admin/news/categories", json={"name": "Gaming", "icon": "🎮", "keywords": ["Playstation", "xbox", "esports"]}, headers=admin_headers)
    assert r.status_code == 201 and r.json()["slug"] == "gaming" and r.json()["keywords"] == ["esports", "playstation", "xbox"]
    got, _ = ingest(db, make_raw("Xbox and PlayStation prices rise ahead of holidays", description="Console makers raised prices, and esports fans reacted angrily to the news on Tuesday."))
    assert db["news"].find_one({"_id": got.article_id})["category"] == "gaming"
    assert "gaming" in [c["slug"] for c in client.get("/api/news/categories").json()]
    assert client.post("/api/admin/news/categories", json={"name": "Gaming"}, headers=admin_headers).status_code == 409
    assert client.post("/api/admin/news/categories", json={"name": "All"}, headers=admin_headers).status_code == 400
    up = client.put("/api/admin/news/categories/gaming", json={"enabled": False}, headers=admin_headers).json()
    assert up["enabled"] is False and "gaming" not in [c["slug"] for c in client.get("/api/news/categories").json()]
    assert client.put("/api/admin/news/categories/nope", json={"enabled": True}, headers=admin_headers).status_code == 404


def test_enrich_endpoint_reports_when_ai_is_unavailable(client, db, admin_headers):
    ingest(db, make_raw("OpenAI announces new AI model"))
    r = client.post("/api/admin/news/enrich?limit=5", headers=admin_headers).json()
    assert r == {"enriched": 0, "failed": 0, "skipped": "ai_unavailable"}


# --------------------------------------------------------------------------------- seeding
def test_default_sources_are_seeded_once_and_never_overwrite_edits(db):
    from backend.news.config import get_settings
    from backend.news.sources import ensure_default_sources

    n = ensure_default_sources(db, get_settings())
    assert n >= 40 and db["news_sources"].count_documents({"type": "rss"}) >= 40
    db["news_sources"].update_one({"_id": "bbc-news"}, {"$set": {"enabled": False, "poll_minutes": 99}})
    assert ensure_default_sources(db, get_settings()) == 0
    bbc = db["news_sources"].find_one({"_id": "bbc-news"})
    assert bbc["enabled"] is False and bbc["poll_minutes"] == 99
    napi = db["news_sources"].find_one({"type": "newsapi"})
    assert napi["enabled"] is False and napi["config"]["sources"] == "reuters,associated-press"     # off until NEWS_API_KEY exists
    assert all(s["url"].startswith("https://") for s in db["news_sources"].find({"type": "rss"}))
