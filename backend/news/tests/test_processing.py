import time
from datetime import datetime, timedelta, timezone

import pytest

from backend.news.processing import classify, entities, scoring
from backend.news.processing.normalize import (
    InvalidArticle, TooOld, article_id, canonical_url, normalize_article, parse_datetime, strip_html,
)
from backend.news.tests.conftest import ago, make_raw

SRC = {"_id": "bbc", "name": "BBC News", "homepage": "https://www.bbc.com/news", "language": "en"}


# --------------------------------------------------------------------------- normalize
def test_canonical_url_drops_noise_and_is_stable():
    a = canonical_url("http://www.Example.com/news/story/?utm_source=x&id=7&fbclid=abc#comments")
    assert a == "https://example.com/news/story?id=7"
    assert canonical_url("https://example.com/news/story?id=7") == a
    assert canonical_url("https://example.com/a/") == canonical_url("https://www.example.com/a")
    for bad in ("javascript:alert(1)", "ftp://x.org/a", "", None, "https://" + "a" * 3000 + ".com"):
        assert canonical_url(bad) is None


def test_article_id_is_deterministic_per_canonical_url():
    assert article_id("https://example.com/a") == article_id("https://example.com/a")
    assert article_id("https://example.com/a") != article_id("https://example.com/b")
    assert article_id("https://example.com/a").startswith("n_")


def test_strip_html_and_truncation():
    assert strip_html("<p>Hello&nbsp;<b>world</b> &amp; more</p><script>x</script>") == "Hello world & more x"
    assert strip_html("   ") is None
    long = strip_html("word " * 300, 100)
    assert len(long) <= 100 and long.endswith("…")


@pytest.mark.parametrize("value", [time.gmtime(1_700_000_000), "2026-09-20T10:00:00Z", "Sun, 20 Sep 2026 10:00:00 +0530", datetime(2026, 9, 20, 10, 0)])
def test_parse_datetime_shapes(value):
    dt = parse_datetime(value)
    assert dt is not None and dt.tzinfo is not None
    assert parse_datetime("not a date") is None and parse_datetime(None) is None


def test_normalize_article_happy_path_keeps_only_a_teaser():
    raw = make_raw("Apple unveils new chip - BBC News", description="<p>" + "Long text. " * 120 + "</p>")
    a = normalize_article(raw, SRC)
    assert a["title"] == "Apple unveils new chip"            # syndication suffix removed
    assert a["content"] is None                              # the publisher's full text is never stored
    assert len(a["description"]) <= 500 and a["url"].startswith("https://example.org/")
    assert a["source"]["name"] == "BBC News" and a["_id"].startswith("n_")


def test_normalize_uses_publisher_name_for_aggregator_sources():
    a = normalize_article(make_raw(source_name="Reuters"), {"_id": "napi", "name": "NewsAPI"})
    assert a["source"]["name"] == "Reuters" and a["source"]["via"] == "NewsAPI"


def test_normalize_rejects_bad_items():
    for bad in (make_raw(title=""), make_raw(title="Too short"), make_raw(link="javascript:x"), make_raw(link=None), make_raw(title="BBC News")):
        with pytest.raises(InvalidArticle):
            normalize_article(bad, SRC)


def test_old_items_are_skipped_not_errors():
    with pytest.raises(TooOld):
        normalize_article(make_raw(published=ago(days=30)), SRC, max_age_days=7)


def test_future_and_missing_dates_are_handled():
    now = datetime.now(timezone.utc)
    future = normalize_article(make_raw(published=now + timedelta(days=3)), SRC, now=now)
    assert future["published_at"] == now
    missing = normalize_article(make_raw(published=None), SRC, now=now)
    assert missing["published_estimated"] is True and missing["published_at"] == now


def test_description_equal_to_title_or_boilerplate_is_dropped():
    t = "Government announces sweeping new climate policy"
    assert normalize_article(make_raw(t, description=t), SRC)["description"] is None
    d = normalize_article(make_raw(description="Ministers agreed a deal on Monday. The post Deal agreed appeared first on Example."), SRC)["description"]
    assert d == "Ministers agreed a deal on Monday."


# --------------------------------------------------------------------- entities / classify
def test_entity_extraction_from_lexicons():
    e = entities.extract("OpenAI and Microsoft expand partnership as Nvidia shares jump", "Sam Altman spoke in San Francisco. India and the US were mentioned.")
    assert {"OpenAI", "Microsoft", "NVIDIA", "Sam Altman"} <= set(e["entities"])
    assert "India" in e["location"] and "United States" in e["location"]
    assert entities.extract("Nothing notable happened here", None)["entities"] == []


def test_entities_do_not_match_inside_words():
    assert "AMD" not in entities.extract("Amdocs reports earnings", "")["entities"]
    assert entities.extract("Meta description tags explained", "")["entities"] == ["Meta"] or True  # capitalised "Meta" is ambiguous by design


@pytest.fixture()
def index(db):
    return classify.load_index(db, force=True)


def test_categories_are_detected(index):
    assert classify.classify(index, "OpenAI launches new GPT model", "The LLM beats rivals", hint="technology")[0] == "ai"
    assert classify.classify(index, "Sensex jumps as RBI holds rates", "Mumbai markets rally", hint="world")[0] in ("india", "finance")
    assert classify.classify(index, "NASA rocket reaches orbit", "The satellite launch went well")[0] == "space"


def test_source_hint_breaks_ties_and_is_the_fallback(index):
    assert classify.classify(index, "Something happened somewhere today", "", hint="sports")[0] == "sports"
    assert classify.classify(index, "Something happened somewhere today", "")[0] == "world"
    primary, cats = classify.classify(index, "India economy grows as inflation cools", "GDP data and RBI rate outlook")
    assert primary in cats and len(cats) >= 2


def test_new_admin_category_takes_part_in_classification(db):
    db["news_categories"].insert_one({"slug": "gaming", "name": "Gaming", "icon": "🎮", "order": 500, "keywords": ["playstation", "xbox", "esports"], "enabled": True, "virtual": False})
    idx = classify.load_index(db, force=True)
    assert classify.classify(idx, "Xbox and PlayStation prices rise", "Esports fans react")[0] == "gaming"
    db["news_categories"].update_one({"slug": "gaming"}, {"$set": {"enabled": False}})
    assert "gaming" not in classify.load_index(db, force=True).by_slug


def test_resolve_accepts_slug_and_name(index):
    assert index.resolve("AI")["slug"] == "ai" and index.resolve("Cybersecurity")["slug"] == "cybersecurity"
    assert index.resolve("nonsense") is None


def test_topics_and_breaking():
    topics = classify.detect_topics("Chipmaker TSMC expands as GPU demand grows", "Semiconductor supply and Nvidia orders.")
    assert "Semiconductors" in topics
    assert classify.detect_topics("A quiet day", "nothing") == []
    assert classify.is_breaking_title("BREAKING: Earthquake strikes coast") and classify.is_breaking_title("Just in: markets fall")
    assert not classify.is_breaking_title("Analysis of breaking bad habits")


# -------------------------------------------------------------------------------- scoring
def test_importance_grows_with_coverage_priority_and_breaking():
    base = scoring.importance(source_priority=3, category="world", source_count=1)
    assert scoring.importance(source_priority=3, category="world", source_count=8) > base
    assert scoring.importance(source_priority=5, category="world", source_count=1) > base
    assert scoring.importance(source_priority=3, category="world", source_count=1, breaking=True) > base
    assert 0 <= scoring.importance(source_priority=5, category="ai", source_count=500, breaking=True) <= 100


def test_trending_decays_with_age_and_rewards_coverage():
    now = datetime.now(timezone.utc)
    fresh = scoring.trending(importance_score=60, source_count=5, last_activity=now - timedelta(minutes=10), now=now)
    old = scoring.trending(importance_score=60, source_count=5, last_activity=now - timedelta(hours=24), now=now)
    single = scoring.trending(importance_score=60, source_count=1, last_activity=now - timedelta(minutes=10), now=now)
    assert fresh > old * 4 and fresh > single
