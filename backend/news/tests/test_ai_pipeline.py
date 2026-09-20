import json
from datetime import timedelta

import pytest

from backend.news import pipeline
from backend.news.collectors.base import BaseNewsCollector, CollectorError, FetchResult
from backend.news.config import get_settings
from backend.news.processing import ai, classify
from backend.news.tests.conftest import ago, ingest, make_raw, make_source

GOOD = {
    "summary": "OpenAI released a new model aimed at developers. The company says it responds faster and costs less.",
    "key_points": ["New model released", "Aimed at developers", "Faster and cheaper"],
    "event": "OpenAI released a new AI model.",
    "category": "AI", "categories": ["AI", "Technology"], "topics": ["LLMs", "Developer Tools"],
    "entities": {"people": ["Sam Altman"], "organizations": ["OpenAI", "Google"], "countries": ["United States"], "locations": [], "products": [], "technologies": []},
}


@pytest.fixture()
def ai_on(monkeypatch):
    monkeypatch.setattr(ai, "ai_available", lambda: True)
    monkeypatch.setattr(pipeline.ai, "ai_available", lambda: True)


# ------------------------------------------------------------------------------------- ai.py
def test_ai_off_by_default_in_tests():
    assert ai.ai_available() is False


def test_extractive_fallbacks_use_only_the_teaser():
    d = "The bank raised rates on Monday. Analysts had expected a pause. Markets fell sharply after the news. Bonds rallied."
    s = ai.extractive_summary(d)
    assert s.startswith("The bank raised rates on Monday.") and "Analysts" in s
    assert len(ai.extractive_key_points(d)) == 3 and ai.extractive_key_points("One sentence only here.") == []
    assert ai.extractive_summary(None) is None


def test_entities_the_model_invents_are_discarded():
    text = "OpenAI released a model on Tuesday. Sam Altman commented."
    got = ai.ground_entities(["OpenAI", "Google", "Sam Altman", "Elon Musk", "openai"], text)
    assert got == ["OpenAI", "Sam Altman"]


def test_build_updates_validates_category_and_grounds_entities(db):
    idx = classify.load_index(db, force=True)
    art = {"title": "OpenAI releases new model", "description": "OpenAI released a new model for developers in the United States, Sam Altman said."}
    up = ai.build_updates(GOOD, art, idx)
    assert up["summary"].startswith("OpenAI released") and up["ai_status"] == "done" and up["summary_source"] == "ai"
    assert up["category"] == "ai" and up["categories"] == ["ai", "technology"]
    assert "Google" not in up["entities"] and {"OpenAI", "Sam Altman"} <= set(up["entities"])
    assert up["location"] == ["United States"] and len(up["key_points"]) == 3
    bad = ai.build_updates({**GOOD, "category": "Astrology"}, art, idx)
    assert "category" not in bad                     # unknown category: keep the rule-based one


def test_unusable_model_output_raises():
    with pytest.raises(ValueError):
        ai.parse_response("I'm sorry, I can't help with that")
    idx = classify.default_index()
    with pytest.raises(ValueError):
        ai.build_updates({"summary": "short"}, {"title": "t", "description": "d"}, idx)


def test_enrich_article_end_to_end_with_fenced_json(db, ai_on, monkeypatch):
    monkeypatch.setattr(ai, "_llm_chat", lambda messages: "```json\n" + json.dumps(GOOD) + "\n```")
    a = {"title": "OpenAI releases new model", "description": "OpenAI released a new model for developers. Sam Altman commented.", "source": {"name": "X"}, "published_at": ago(minutes=5)}
    up = ai.enrich_article(a, classify.load_index(db, force=True))
    assert up["category"] == "ai" and "Sam Altman" in up["entities"]


def test_the_prompt_forbids_invention_and_only_sends_headline_and_teaser(db, ai_on, monkeypatch):
    seen = {}

    def spy(messages):
        seen["system"], seen["user"] = messages[0]["content"], json.loads(messages[1]["content"])
        return json.dumps(GOOD)

    monkeypatch.setattr(ai, "_llm_chat", spy)
    ai.enrich_article({"title": "T" * 20, "description": "D" * 80, "source": {"name": "BBC"}, "published_at": ago(), "url": "https://secret.example/x"}, classify.default_index())
    assert "Never add facts" in seen["system"] and "only names that appear in the text" in seen["system"]
    assert set(seen["user"]) == {"headline", "teaser", "publisher", "published"}   # no URL, no full text


# ----------------------------------------------------------------------- enrich_pending
def test_thin_teasers_are_never_sent_to_the_model(db):
    r, _ = ingest(db, make_raw("Government announces sweeping new climate policy", description=None))
    doc = db["news"].find_one({"_id": r.article_id})
    assert doc["ai_status"] == "skipped" and doc["summary"] is None      # no invented summary


def test_enrich_pending_upgrades_the_most_important_first(db, ai_on, monkeypatch):
    monkeypatch.setattr(ai, "_llm_chat", lambda messages: json.dumps(GOOD))
    low, _ = ingest(db, make_raw("Local council approves new parking rules downtown", description="The council voted on Tuesday to approve new downtown parking rules after a long debate."), make_source(db, priority=1))
    high, _ = ingest(db, make_raw("OpenAI releases new model for developers"), make_source(db, priority=5))
    out = pipeline.enrich_pending(db, limit=1)
    assert out["enriched"] == 1
    assert db["news"].find_one({"_id": high.article_id})["ai_status"] == "done"
    assert db["news"].find_one({"_id": low.article_id})["ai_status"] == "pending"
    assert db["news"].find_one({"_id": high.article_id})["summary_source"] == "ai"


def test_failed_enrichment_keeps_rule_based_fields_and_gives_up_after_three_tries(db, ai_on, monkeypatch):
    def boom(messages):
        raise RuntimeError("All LLM providers failed")

    monkeypatch.setattr(ai, "_llm_chat", boom)
    r, _ = ingest(db, make_raw("OpenAI releases new model for developers"))
    before = db["news"].find_one({"_id": r.article_id})
    for _ in range(3):
        assert pipeline.enrich_pending(db, limit=5)["failed"] in (0, 1)
    after = db["news"].find_one({"_id": r.article_id})
    assert after["ai_status"] == "failed" and after["ai_attempts"] == 3
    assert after["summary"] == before["summary"] and after["category"] == before["category"]   # nothing lost
    assert db["news_errors"].count_documents({"type": "ai"}) == 3
    assert pipeline.enrich_pending(db, limit=5)["enriched"] == 0


def test_enrichment_can_move_a_story_between_categories_and_refreshes_it(db, ai_on, monkeypatch):
    monkeypatch.setattr(ai, "_llm_chat", lambda messages: json.dumps({**GOOD, "category": "Cybersecurity", "categories": ["Cybersecurity"]}))
    r, _ = ingest(db, make_raw("OpenAI releases new model for developers"))
    pipeline.enrich_pending(db, limit=5)
    assert db["stories"].find_one({})["category"] == "cybersecurity"


def test_enrichment_is_a_no_op_when_ai_is_unavailable(db):
    ingest(db, make_raw("OpenAI releases new model for developers"))
    assert pipeline.enrich_pending(db, limit=5) == {"enriched": 0, "failed": 0, "skipped": "ai_unavailable"}


# --------------------------------------------------------------------------- run_source
class Fake(BaseNewsCollector):
    type = "rss"

    def __init__(self, items=None, exc=None, not_modified=False):
        self.items, self.exc, self.not_modified = items or [], exc, not_modified

    def is_available(self, source):
        return True, ""

    def fetch(self, source):
        if self.exc:
            raise self.exc
        return FetchResult(items=self.items, etag='"abc"', last_modified="Sat, 19 Sep 2026 10:00:00 GMT", not_modified=self.not_modified)


def test_run_source_success_updates_source_and_logs_run(db):
    src = make_source(db)
    res = pipeline.run_source(db, src, collector=Fake([make_raw("OpenAI announces new AI model"), make_raw("Heavy flooding hits southern India as rivers overflow")]))
    assert res["status"] == "success" and res["counts"]["created"] == 2
    s = db["news_sources"].find_one({"_id": src["_id"]})
    assert s["articles_total"] == 2 and s["last_success_at"] and s["consecutive_failures"] == 0 and s["etag"] == '"abc"'
    assert db["news_runs"].find_one({"source_id": src["_id"]})["status"] == "success"


def test_bad_items_are_isolated_and_logged(db):
    src = make_source(db)
    items = [make_raw("OpenAI announces new AI model"), {"title": "", "link": "x"}, make_raw(link="javascript:evil()"), make_raw("Heavy flooding hits southern India as rivers overflow")]
    res = pipeline.run_source(db, src, collector=Fake(items))
    assert res["status"] == "partial" and res["counts"]["created"] == 2 and res["counts"]["invalid"] == 2
    assert db["news_errors"].count_documents({"source_id": src["_id"], "type": "validation"}) == 2


def test_a_failing_source_is_recorded_and_backs_off(db):
    src = make_source(db, poll_minutes=10)
    for _ in range(3):
        res = pipeline.run_source(db, db["news_sources"].find_one({"_id": src["_id"]}), collector=Fake(exc=CollectorError("HTTP 503 from feed")))
    assert res["status"] == "failed" and "503" in res["error"]
    s = db["news_sources"].find_one({"_id": src["_id"]})
    assert s["consecutive_failures"] == 3 and "503" in s["last_error"]
    assert pipeline.next_due(s) - s["last_fetch_at"] == timedelta(minutes=80)     # 10min * 2^3
    assert pipeline.is_due(s) is False
    # recovery clears the failure state
    pipeline.run_source(db, s, collector=Fake([make_raw("OpenAI announces new AI model")]))
    assert db["news_sources"].find_one({"_id": src["_id"]})["consecutive_failures"] == 0


def test_not_modified_feeds_cost_nothing(db):
    src = make_source(db, etag='"abc"')
    res = pipeline.run_source(db, src, collector=Fake(not_modified=True))
    assert res["status"] == "success" and res["counts"]["fetched"] == 0
    assert db["news_sources"].find_one({"_id": src["_id"]})["etag"] == '"abc"'


def test_item_cap_and_old_items(db):
    src = make_source(db)
    s = get_settings()
    items = [make_raw(f"Distinct headline number {i} about {w} developments", link=f"https://example.org/x{i}") for i, w in enumerate(["alpha", "bravo", "charlie"])]
    items.append(make_raw("Ancient headline about old history archives", published=ago(days=60), link="https://example.org/old"))
    res = pipeline.run_source(db, src, collector=Fake(items))
    assert res["counts"]["skipped"] == 1 and db["news"].count_documents({}) == 3
    assert s.max_items_per_fetch >= 3


def test_updated_headline_or_image_refreshes_the_same_article(db):
    src = make_source(db)
    raw = make_raw("Central bank holds interest rates steady", image=None)
    ingest(db, raw, src)
    r, _ = ingest(db, {**raw, "title": "Central bank holds interest rates steady, signals cuts", "image": "https://x/new.jpg"}, src)
    assert r.action == "updated"
    doc = db["news"].find_one({})
    assert doc["title"].endswith("signals cuts") and doc["image_url"] == "https://x/new.jpg"


# ---------------------------------------------------------------------- due / lease / cycle
def test_due_logic_and_disabled_sources(db):
    now = pipeline.utcnow()
    assert pipeline.is_due({"enabled": True, "last_fetch_at": None}, now)
    assert not pipeline.is_due({"enabled": False, "last_fetch_at": None}, now)
    assert not pipeline.is_due({"enabled": True, "poll_minutes": 15, "last_fetch_at": now - timedelta(minutes=5)}, now)
    assert pipeline.is_due({"enabled": True, "poll_minutes": 15, "last_fetch_at": now - timedelta(minutes=16)}, now)


def test_lease_prevents_two_workers_running_the_same_cycle(db):
    assert pipeline.acquire_lease(db, "cycle", 600) is True
    db["news_locks"].update_one({"_id": "cycle"}, {"$set": {"owner": "someone-else:1"}})
    assert pipeline.acquire_lease(db, "cycle", 600) is False
    assert pipeline.run_due_sources(db) == {"skipped": "another worker holds the lease"}
    db["news_locks"].update_one({"_id": "cycle"}, {"$set": {"expires_at": ago(minutes=1)}})
    assert pipeline.acquire_lease(db, "cycle", 600) is True
    pipeline.release_lease(db, "cycle")


def test_cycle_runs_only_due_enabled_sources_and_one_failure_does_not_stop_the_rest(db, monkeypatch):
    good = make_source(db, name="Good Feed")
    bad = make_source(db, name="Bad Feed", url="https://bad.example.org/rss")
    off = make_source(db, name="Off Feed", enabled=False)
    fresh = make_source(db, name="Fresh Feed", last_fetch_at=pipeline.utcnow())

    def fake_make(source, settings=None, client=None):
        if source["_id"] == bad["_id"]:
            return Fake(exc=CollectorError("connection refused"))
        return Fake([make_raw(f"Unique story about {source['name']} results")])

    monkeypatch.setattr(pipeline, "make_collector", fake_make)
    out = pipeline.run_due_sources(db)
    by = {r["source"]: r["status"] for r in out["results"]}
    assert by == {"Good Feed": "success", "Bad Feed": "failed"}
    assert db["news"].count_documents({}) == 1
    assert good and off and fresh


def test_retention_cleanup_removes_only_old_articles(db):
    ingest(db, make_raw("Recent headline about markets and trade", published=ago(days=1)))
    old, _ = ingest(db, make_raw("Old headline about a long forgotten event", published=ago(days=6)))
    db["news"].update_one({"_id": old.article_id}, {"$set": {"published_at": ago(days=400)}})
    out = pipeline.cleanup(db, force=True)
    assert out["articles"] == 1 and db["news"].count_documents({}) == 1
    assert pipeline.cleanup(db) == {"skipped": True}        # at most every 12h


# --------------------------------------------- hard guard against claims the source never made
def test_unsupported_claims_are_detected_including_the_real_former_president_case():
    src = "MS NOW, CNN and Politico journalists blocked from White House after Trump ban. Journalists from MS NOW, CNN and Politico were denied access to the White House, one day after Trump banned three media outlets over their coverage of him."
    bad = ai.unsupported_terms(["Journalists from MS NOW, CNN and Politico were denied access. This occurred a day after former president Trump banned three media outlets."], src)
    assert "former" in bad
    assert ai.unsupported_terms(["Journalists from MS NOW, CNN and Politico were denied access to the White House a day after Trump banned three outlets."], src) == []
    assert "Donald" in ai.unsupported_terms(["The reporters were blocked, a day after President Donald Trump acted."], src)      # first name from the model's own knowledge
    assert "2,000" in ai.unsupported_terms(["About 2,000 people were affected."], "Thousands were affected.")
    assert ai.unsupported_terms(["The bank raised rates by 25 points."], "The bank raised rates by 25 points on Monday.") == []
    assert ai.unsupported_terms(["It happened on Saturday."], "It happened.") == []          # weekdays are not flagged


def test_a_bad_first_answer_gets_one_correction_and_is_accepted_if_fixed(db, ai_on, monkeypatch):
    calls = []
    bad = {**GOOD, "summary": "OpenAI released a model, said former chief Sam Altman. It is faster than before, the company says."}

    def chat(messages):
        calls.append(messages)
        return json.dumps(bad if len(calls) == 1 else GOOD)

    monkeypatch.setattr(ai, "_llm_chat", chat)
    a = {"title": "OpenAI releases new model", "description": "OpenAI released a new model for developers, and is faster. Sam Altman commented.", "source": {"name": "Wire"}, "published_at": ago(minutes=5)}
    up = ai.enrich_article(a, classify.load_index(db, force=True))
    assert len(calls) == 2 and "former" in calls[1][-1]["content"] and up["summary"] == GOOD["summary"]


def test_repeated_unsupported_claims_reject_the_ai_result(db, ai_on, monkeypatch):
    bad = {**GOOD, "summary": "The former president released a model. Officials in Berlin confirmed it."}
    monkeypatch.setattr(ai, "_llm_chat", lambda messages: json.dumps(bad))
    r, _ = ingest(db, make_raw("OpenAI releases new model for developers"))
    out = pipeline.enrich_pending(db, limit=5)
    doc = db["news"].find_one({"_id": r.article_id})
    assert out["failed"] == 1 and doc["summary_source"] == "extractive" and doc["ai_status"] == "pending"     # keeps the publisher's own words
    assert "unsupported claims" in db["news_errors"].find_one({"type": "ai"})["message"]
