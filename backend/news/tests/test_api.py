import pytest

from backend.news.cache import cache
from backend.news.tests.conftest import ago, ingest, make_raw, make_source


@pytest.fixture()
def world(db):
    """A small realistic newsroom: one 3-outlet AI story plus stories in other categories."""
    src = {n: make_source(db, name=n, priority=p, category=c) for n, p, c in (
        ("Reuters", 5, "world"), ("TechCrunch", 4, "technology"), ("The Verge", 4, "technology"),
        ("BBC News", 5, "world"), ("Nature", 5, "science"), ("Economic Times", 4, "finance"))}
    ids = {}
    for key, title, source, kw in (
        ("ai1", "OpenAI announces new AI model", "Reuters", dict(published=ago(minutes=50))),
        ("ai2", "OpenAI launches new AI model", "TechCrunch", dict(published=ago(minutes=40))),
        ("ai3", "OpenAI introduces new AI model", "The Verge", dict(published=ago(minutes=30), image=None)),
        ("world", "Ceasefire talks resume as diplomats meet in Geneva", "BBC News", dict(published=ago(minutes=20), description="Diplomats from several countries met in Geneva on Monday to resume ceasefire talks after weeks of conflict.")),
        ("sci", "Astronomers detect rare galaxy merger with James Webb telescope", "Nature", dict(published=ago(hours=3), description="Researchers used the James Webb telescope to observe two galaxies merging in the early universe, the study says.")),
        ("fin", "Sensex jumps as RBI holds interest rates in Mumbai", "Economic Times", dict(published=ago(hours=5), description="Indian stocks rallied on Wednesday after the RBI kept interest rates unchanged, lifting the Sensex and Nifty.")),
        ("nv", "Nvidia shares surge on strong chip demand", "Economic Times", dict(published=ago(hours=8), description="Nvidia shares jumped after the chipmaker forecast strong demand for its GPUs from cloud customers.")),
    ):
        r, _ = ingest(db, make_raw(title, **kw), src[source])
        ids[key] = r.article_id
    cache.clear()
    return ids


def titles(resp):
    return [a["title"] for a in resp.json()["articles"]]


# ----------------------------------------------------------------------------------- feed
def test_feed_shows_one_card_per_story_with_coverage(client, world):
    d = client.get("/api/news").json()
    assert d["total"] == 5                                   # 7 articles, 3 of them one story
    ai = next(a for a in d["articles"] if "OpenAI" in a["title"])
    assert ai["coverage"]["count"] == 3 and set(ai["coverage"]["sources"]) == {"Reuters", "TechCrunch", "The Verge"}
    assert "content" not in ai and "title_tokens" not in ai
    assert {"id", "title", "summary", "url", "image_url", "source", "category", "categories", "topics", "entities", "published_at", "collected_at", "trending_score", "importance_score", "duplicate_group_id"} <= set(ai)


def test_ungrouped_mode_lists_every_article(client, world):
    assert client.get("/api/news?group=false").json()["total"] == 7


def test_newest_activity_first_and_pagination(client, world):
    d = client.get("/api/news?limit=2&page=1").json()
    assert d["has_more"] is True and d["total_pages"] == 3 and len(d["articles"]) == 2
    assert d["articles"][0]["title"].startswith(("OpenAI", "Ceasefire")) or "Ceasefire" in d["articles"][0]["title"] or "OpenAI" in d["articles"][0]["title"]
    last = client.get("/api/news?limit=2&page=3").json()
    assert last["has_more"] is False and len(last["articles"]) == 1
    assert client.get("/api/news?page=99").json()["articles"] == []
    assert client.get("/api/news?limit=51").status_code == 400 and client.get("/api/news?page=0").status_code == 400


def test_category_filters(client, world):
    ai = client.get("/api/news?category=ai")
    assert "OpenAI announces new AI model" in titles(ai) or any("OpenAI" in t for t in titles(ai))
    assert not any("Geneva" in t or "galaxy" in t for t in titles(ai))
    assert client.get("/api/news/category/AI").json()["total"] == ai.json()["total"]        # name or slug, any case
    assert client.get("/api/news?category=all").json()["total"] == 5
    assert client.get("/api/news?category=science").json()["total"] == 1
    r = client.get("/api/news?category=astrology")
    assert r.status_code == 404 and "Unknown category" in r.json()["detail"]


def test_breaking_category_shows_only_breaking_and_recent(client, db, world):
    r, _ = ingest(db, make_raw("BREAKING: Major earthquake strikes coastal city", description="A powerful earthquake struck the coast early on Sunday, officials said.", published=ago(minutes=5)), make_source(db, name="Wire"))
    cache.clear()
    got = titles(client.get("/api/news?category=breaking"))
    assert "BREAKING: Major earthquake strikes coastal city" in got                 # flagged by its headline
    assert any("OpenAI" in t for t in got)                                         # 3 outlets within 90 minutes = breaking pickup
    assert not any("Geneva" in t or "galaxy" in t or "Sensex" in t for t in got)   # ordinary stories are not
    assert r.article_id


def test_source_filter_lists_that_publishers_articles_even_inside_a_story(client, world):
    d = client.get("/api/news/source/the%20verge").json()               # case-insensitive
    assert [a["source"]["name"] for a in d["articles"]] == ["The Verge"] and d["total"] == 1
    assert client.get("/api/news?source=Reuters").json()["total"] == 1
    assert client.get("/api/news/source/Nobody").json()["total"] == 0


def test_topic_filter(client, world):
    d = client.get("/api/news/topic/semiconductors").json()
    assert any("Nvidia" in a["title"] for a in d["articles"])


def test_date_filters(client, world):
    assert client.get("/api/news", params={"from": ago(hours=1).isoformat()}).json()["total"] == 2        # the AI story + ceasefire
    assert client.get("/api/news", params={"to": ago(hours=4).isoformat()}).json()["total"] == 2          # finance items (stories last active > 4h ago)
    assert client.get(f"/api/news?from={ago(hours=1).isoformat()}").json()["total"] == 2                  # an unencoded "+00:00" still works
    assert client.get("/api/news?from=2020-01-01&to=2020-01-02").json()["total"] == 0
    assert client.get("/api/news?from=nonsense").status_code == 400
    assert client.get("/api/news?from=2026-09-20&to=2026-09-01").status_code == 400


def test_sorting(client, world):
    t = client.get("/api/news?sort=trending").json()["articles"]
    assert [a["trending_score"] for a in t] == sorted([a["trending_score"] for a in t], reverse=True)
    assert "OpenAI" in t[0]["title"]                                        # 3 outlets, fresh: trends highest
    assert client.get("/api/news?sort=importance").status_code == 200
    assert client.get("/api/news?sort=random").status_code == 400


def test_unpublished_articles_never_appear(client, db, world):
    db["news"].update_many({}, {"$set": {"status": "hidden"}})
    cache.clear()
    assert client.get("/api/news").json()["total"] == 0
    assert client.get(f"/api/news/{world['sci']}").status_code == 404
    assert client.get("/api/news/search?q=OpenAI").json()["total"] == 0


# --------------------------------------------------------------------------------- search
def test_search_matches_title_entities_source_topics_and_category(client, world):
    assert titles(client.get("/api/news/search?q=OpenAI")) and all("OpenAI" in t for t in titles(client.get("/api/news/search?q=OpenAI")))
    assert client.get("/api/news/search?q=Reuters").json()["total"] == 1                     # source name
    assert any("Nvidia" in t for t in titles(client.get("/api/news/search?q=semiconductors")))      # topic
    assert client.get("/api/news/search?q=Geneva").json()["total"] == 1
    assert client.get("/api/news/search?q=zzzznothing").json()["total"] == 0


def test_search_collapses_a_story_covered_by_many_outlets(client, world):
    d = client.get("/api/news/search?q=OpenAI").json()
    assert d["total"] == 1 and d["articles"][0]["coverage"]["count"] == 3


def test_search_supports_partial_words_multiple_terms_and_filters(client, world):
    assert any("Nvidia" in t for t in titles(client.get("/api/news/search?q=nvid")))              # prefix fallback
    assert client.get("/api/news/search?q=interest%20rates").json()["total"] == 1
    assert client.get("/api/news/search?q=OpenAI&category=science").json()["total"] == 0
    assert client.get("/api/news/search?q=OpenAI&category=ai").json()["total"] == 1


@pytest.mark.parametrize("qs", ["q=a", "q=", ""])
def test_search_requires_a_real_term(client, qs):
    r = client.get(f"/api/news/search?{qs}")
    assert r.status_code == 400 and r.json()["detail"]


def test_search_input_is_treated_literally(client, world):
    assert client.get("/api/news/search", params={"q": ".*"}).status_code == 200
    assert client.get("/api/news/search", params={"q": "(unclosed["}).status_code == 200
    assert client.get("/api/news/search", params={"q": '" OR 1=1 //'}).status_code == 200


# --------------------------------------------------------------------------------- detail
def test_article_detail_is_full_but_never_contains_publisher_text(client, world):
    d = client.get(f"/api/news/{world['ai1']}").json()
    assert d["id"] == world["ai1"] and d["content"] is None
    assert {"key_points", "event", "entities_detail", "language", "summary_source", "coverage", "topics", "entities"} <= set(d)
    assert d["url"].startswith("https://") and d["source"]["name"] == "Reuters"
    assert client.get("/api/news/n_missing").status_code == 404


def test_story_endpoint_returns_lead_and_every_source_article(client, world):
    gid = client.get(f"/api/news/{world['ai1']}").json()["duplicate_group_id"]
    d = client.get(f"/api/news/story/{gid}").json()
    assert d["story"]["source_count"] == 3 and d["story"]["article_count"] == 3
    assert {a["source"]["name"] for a in d["articles"]} == {"Reuters", "TechCrunch", "The Verge"}
    assert d["lead"]["id"] == d["story"]["lead_article_id"]
    assert client.get("/api/news/story/st_missing").status_code == 404


def test_related_coverage_lists_the_same_story_first(client, world):
    rel = client.get(f"/api/news/related/{world['ai1']}").json()
    assert {a["source"]["name"] for a in rel[:2]} == {"TechCrunch", "The Verge"}
    assert world["ai1"] not in {a["id"] for a in rel}
    assert client.get("/api/news/related/n_missing").status_code == 404


# ---------------------------------------------------------------- top / trending / now
def test_top_stories_lead_with_an_illustrated_story(client, world):
    d = client.get("/api/news/top-stories?limit=3").json()["articles"]
    assert len(d) == 3 and d[0]["image_url"]
    assert len({a["duplicate_group_id"] for a in d}) == 3          # distinct stories, never the same one thrice


def test_trending_is_ordered_by_score_and_covers_recent_stories(client, world):
    d = client.get("/api/news/trending?limit=10").json()["articles"]
    scores = [a["trending_score"] for a in d]
    assert scores == sorted(scores, reverse=True) and "OpenAI" in d[0]["title"]


def test_whats_happening_groups_stories_with_source_counts(client, world):
    groups = {g["key"]: g for g in client.get("/api/news/whats-happening").json()["groups"]}
    assert "ai" in groups and "OpenAI" in groups["ai"]["articles"][0]["title"] and groups["ai"]["articles"][0]["coverage"]["count"] == 3
    assert "global" in groups and "india" in groups and groups["ai"]["label"] == "AI"
    assert all(g["articles"] for g in groups.values())               # empty sections are omitted


# ---------------------------------------------------------------------------------- facets
def test_categories_endpoint_has_virtual_entries_counts_and_order(client, world):
    cats = client.get("/api/news/categories").json()
    slugs = [c["slug"] for c in cats]
    assert slugs[:2] == ["all", "breaking"] and {"ai", "technology", "world", "india", "cybersecurity", "travel"} <= set(slugs)
    by = {c["slug"]: c for c in cats}
    assert by["all"]["count"] == 5 and by["ai"]["count"] >= 1 and len(cats) == 20


def test_sources_and_topics_endpoints(client, world):
    names = {s["name"]: s["count"] for s in client.get("/api/news/sources").json()}
    assert names["Reuters"] == 1 and names["Economic Times"] == 2
    assert any(t["name"] == "Semiconductors" for t in client.get("/api/news/topics").json())


# ----------------------------------------------------------------------------------- caching
def test_repeated_requests_are_served_from_cache_and_invalidated_by_ingestion(client, db, world):
    cache.clear()
    h0 = cache.hits
    a = client.get("/api/news?limit=5").json()
    b = client.get("/api/news?limit=5").json()
    assert a == b and cache.hits == h0 + 1
    # new data arrives via a collector run -> cache is dropped, so readers see it at once
    from backend.news import pipeline
    from backend.news.tests.test_ai_pipeline import Fake

    pipeline.run_source(db, make_source(db, name="Late Wire"), collector=Fake([make_raw("Volcano erupts near remote island village", description="A volcano erupted on Tuesday, sending ash into the sky, officials said.")]))
    assert client.get("/api/news?limit=5").json()["total"] == a["total"] + 1


def test_categories_are_cached_longer_than_the_feed(client, world):
    from backend.news.config import get_settings

    s = get_settings()
    assert s.cache_ttl_long > s.cache_ttl_short


# --------------------------------------------------------------------------- errors
def test_unexpected_errors_are_500_without_internals(client, monkeypatch):
    from backend.news.services import news_service

    def boom(*a, **k):
        raise RuntimeError("secret mongodb://user:pw@host")

    monkeypatch.setattr(news_service, "list_articles", boom)
    r = client.get("/api/news")
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"} and "pw@host" not in r.text


def test_database_down_is_503(client, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    from backend.news.services import news_service

    def down(*a, **k):
        raise ServerSelectionTimeoutError("localhost:27017 timed out")

    monkeypatch.setattr(news_service, "list_articles", down)
    r = client.get("/api/news")
    assert r.status_code == 503 and "localhost" not in r.text


def test_unconfigured_news_is_503_not_a_crash(client):
    from backend.common.errors import ApiError
    from backend.news.routes import news as news_routes

    def unconfigured():
        raise ApiError(503, "News is not configured: set NEWS_MONGO_URI")

    client.app.dependency_overrides[news_routes.get_db] = unconfigured
    r = client.get("/api/news")
    client.app.dependency_overrides.clear()
    assert r.status_code == 503 and "NEWS_MONGO_URI" in r.json()["detail"]


def test_news_is_mounted_in_the_real_casefile_app_without_disturbing_it(db):
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/news?limit=1").status_code == 200 and c.get("/health").status_code == 200
    paths = set(app.openapi()["paths"])
    assert {"/api/news", "/api/news/{article_id}", "/api/news/search", "/api/news/story/{story_id}", "/api/admin/news/sources"} <= paths
    assert {"/api/company-research", "/api/events", "/api/admin/events"} <= paths             # other tools intact
    assert c.post("/api/company-research", json={}).status_code == 422                     # Casefile keeps FastAPI's default 422


# ------------------------------------------------------------------ source diversity in "Latest"
def test_latest_interleaves_sources_so_one_burst_cannot_fill_the_page(client, db):
    burst = make_source(db, name="Sports Desk", category="sports")
    other = make_source(db, name="World Wire", category="world")
    distinct = ["Quarterback Ranking Revealed", "Golf Contender Surges", "Recruit Commits Early", "Coach Praises Defence", "Rivalry Game Preview",
                "Injury Report Released", "Draft Prospects Analysed", "Tennis Final Rescheduled", "Marathon Record Falls", "Cricket Series Squad Named"]
    for i, t in enumerate(distinct):                       # ten items in the last ten minutes
        ingest(db, make_raw(f"{t} Today", published=ago(minutes=i)), burst)
    ingest(db, make_raw("Ministers agree new trade framework in Brussels", published=ago(minutes=50),
                        description="Ministers meeting in Brussels agreed a new framework for trade between the two blocs after long talks."), other)
    cache.clear()
    page1 = [a["source"]["name"] for a in client.get("/api/news?limit=6").json()["articles"]]
    assert "World Wire" in page1                            # would be 11th in a pure time sort
    assert page1[0] == "Sports Desk"                        # still newest-first at the top
    assert client.get("/api/news?limit=50").json()["total"] == 11
    only = client.get("/api/news?source=Sports%20Desk&limit=50").json()["articles"]
    assert [a["source"]["name"] for a in only] == ["Sports Desk"] * 10   # explicit filters stay chronological
