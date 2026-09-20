"""Duplicate detection / story clustering: the most important behaviour of the tool."""
import pytest

from backend.news.processing import cluster
from backend.news.tests.conftest import ago, ingest, make_raw, make_source


def art(title, **kw):
    from backend.news.processing import entities

    return {"title": title, "title_tokens": cluster.distinctive_tokens(title), "entities": entities.extract(title, "")["entities"], "topics": [], "published_at": ago(minutes=10), **kw}


def test_launch_verbs_are_folded_so_headlines_align():
    a = cluster.distinctive_tokens("OpenAI announces new AI model")
    b = cluster.distinctive_tokens("OpenAI launches new AI model")
    c = cluster.distinctive_tokens("OpenAI introduces new AI model")
    assert a == b == c == ["openai", "ai", "model"]


def test_the_specs_three_publishers_score_as_one_story():
    r, t, v = art("OpenAI announces new AI model"), art("OpenAI launches new AI model"), art("OpenAI introduces new AI model")
    for x, y in ((r, t), (r, v), (t, v)):
        score, detail = cluster.score_pair(x, y)
        assert score >= cluster.JOIN_SCORE, (score, detail)


def test_different_events_from_the_same_company_stay_apart():
    a, b = art("Apple unveils new iPhone with faster chip"), art("Apple reports record quarterly earnings")
    assert cluster.score_pair(a, b)[0] < cluster.JOIN_SCORE


def test_single_shared_word_never_joins():
    assert cluster.score_pair(art("Fed raises interest rates again"), art("Fed chair praised for handling of crisis"))[0] < cluster.JOIN_SCORE
    assert cluster.score_pair(art("Tesla recalls vehicles over software bug"), art("Bitcoin surges past record high on ETF news"))[0] == 0.0


def test_different_numbers_are_different_events():
    a, b = art("Fed raises rates by 25 basis points"), art("Fed raises rates by 50 basis points")
    assert cluster.score_pair(a, b)[0] < cluster.JOIN_SCORE


def test_paraphrase_with_shared_entities_and_topic_words_joins():
    a = art("Nvidia shares jump after strong chip demand forecast")
    b = art("Nvidia stock jumps on strong chip demand outlook")
    assert cluster.score_pair(a, b)[0] >= cluster.JOIN_SCORE


# -------------------------------------------------------------------------- with MongoDB
def test_three_outlets_one_event_become_one_story(db):
    srcs = [make_source(db, name=n, priority=p) for n, p in (("Reuters", 5), ("TechCrunch", 4), ("The Verge", 4))]
    titles = ["OpenAI announces new AI model", "OpenAI launches new AI model", "OpenAI introduces new AI model"]
    ids = [ingest(db, make_raw(t, image=None if i else "https://x/y.jpg"), s)[0] for i, (t, s) in enumerate(zip(titles, srcs))]
    assert [r.action for r in ids] == ["created", "clustered", "clustered"]
    gids = {r.group_id for r in ids}
    assert len(gids) == 1

    members = list(db["news"].find({"duplicate_group_id": gids.pop()}))
    assert len(members) == 3 and sum(1 for m in members if m["is_lead"]) == 1
    lead = next(m for m in members if m["is_lead"])
    assert lead["coverage"]["count"] == 3 and set(lead["coverage"]["sources"]) == {"Reuters", "TechCrunch", "The Verge"}
    assert all(m["coverage"]["count"] == 3 for m in members)
    assert all(len(m["related_articles"]) == 2 for m in members)
    story = db["stories"].find_one({})
    assert story["article_count"] == 3 and story["source_count"] == 3 and story["lead_article_id"] == lead["_id"]
    assert db["stories"].count_documents({}) == 1


def test_unrelated_articles_get_their_own_stories(db):
    ingest(db, make_raw("OpenAI announces new AI model"))
    ingest(db, make_raw("Heavy flooding hits southern India as rivers overflow", description="Thousands were evacuated as rainfall broke records across the region."))
    assert db["stories"].count_documents({}) == 2
    assert db["news"].count_documents({"is_lead": True}) == 2


def test_articles_far_apart_in_time_do_not_cluster(db):
    ingest(db, make_raw("OpenAI announces new AI model", published=ago(days=5)))
    r, _ = ingest(db, make_raw("OpenAI launches new AI model", published=ago(minutes=5)))
    assert r.action == "created"


def test_the_same_link_from_two_sources_is_one_article(db):
    raw = make_raw("Central bank holds interest rates steady", link="https://example.org/same?utm_source=rss")
    a, _ = ingest(db, raw)
    b, _ = ingest(db, {**raw, "link": "https://www.example.org/same/"})
    assert a.action == "created" and b.action == "unchanged" and a.article_id == b.article_id
    assert db["news"].count_documents({}) == 1


def test_best_article_becomes_the_lead(db):
    weak = make_source(db, name="Small Blog", priority=1)
    strong = make_source(db, name="Big Paper", priority=5)
    desc = "Researchers said the quantum machine cut error rates to a new low, a step toward practical quantum computing."
    ingest(db, make_raw("Quantum computer breaks new record in error correction", image=None, description=None), weak)
    ingest(db, make_raw("Quantum computer sets new record in error correction", description=desc), strong)
    lead = db["news"].find_one({"is_lead": True})
    assert lead["source"]["name"] == "Big Paper"


def test_breaking_flag_from_title_and_from_fast_multi_source_pickup(db):
    r, _ = ingest(db, make_raw("BREAKING: Earthquake strikes coastal city", description="A powerful earthquake struck the coast early on Sunday, officials said."))
    assert db["news"].find_one({"_id": r.article_id})["is_breaking"] is True
    for i in range(3):
        ingest(db, make_raw("Major bridge collapses in northern region", description="Officials confirmed the collapse and began rescue efforts.", published=ago(minutes=20 - i)), make_source(db, name=f"Outlet {i}"))
    story = db["stories"].find_one({"title": {"$regex": "bridge"}})
    assert story["is_breaking"] is True and story["source_count"] == 3


def test_rescore_recent_decays_trending(db):
    ingest(db, make_raw("OpenAI announces new AI model", published=ago(minutes=5)))
    before = db["stories"].find_one({})["trending_score"]
    db["stories"].update_one({}, {"$set": {"last_activity_at": ago(hours=30)}})
    cluster.rescore_recent(db, hours=96)
    after = db["stories"].find_one({})["trending_score"]
    assert after < before / 3
    assert db["news"].find_one({})["trending_score"] == after


# ---------------------------- the real-world Gemini event: 7 outlets, 7 different headlines
GEMINI = [
    ("Gemini hacked three companies in first known breakout by Google's AI", "Indian Express", 4),
    ("Gemini went rogue, hacked three companies, and Google hid it", "The Verge", 3),
    ("Google Gemini Broke Into Real Company Systems After Security Test Domain Mix-Up", "The Hacker News", 5),
    ("Google says its Gemini AI model hacked three other companies", "The Guardian AI", 12),
    ("Google's Gemini AI hacked three companies in security test", "BBC World", 2),
    ("Google's Gemini becomes latest AI model to break out and hack computer systems", "CNBC", 11),
    ("Google's Gemini is the latest AI model to hack other companies", "TechCrunch AI", 1),
]


def test_paraphrased_headlines_about_one_event_are_recognised_by_the_strong_overlap_rule():
    a = art("Gemini hacked three companies in first known breakout by Google's AI")
    b = art("Google's Gemini AI hacked three companies in security test")
    score, detail = cluster.score_pair(a, b)
    assert detail.get("strong_overlap") and score >= cluster.JOIN_SCORE


def test_a_different_story_about_the_same_products_is_not_swallowed():
    launch = art("Introducing Gemini 3.8 Live and 3.8 Live Extended Thinking", published_at=ago(days=4))
    hack = art("Google's Gemini AI hacked three companies in security test")
    assert cluster.score_pair(launch, hack)[0] < cluster.JOIN_SCORE
    other = art("Google unveils Gemini features for Chrome browser users")
    assert cluster.score_pair(other, hack)[0] < cluster.JOIN_SCORE          # two shared entities but too little else


def test_ingest_time_clustering_and_the_recluster_pass_unite_the_whole_event(db):
    for title, source, minutes in GEMINI:
        ingest(db, make_raw(title, description="Google said its Gemini AI model hacked three companies during a security test, according to a report.", published=ago(hours=minutes)), make_source(db, name=source))
    before = db["stories"].count_documents({})
    out = cluster.recluster(db, hours=48)
    after = db["stories"].count_documents({})
    assert after == 1, (before, after, out)                   # one event -> one story
    story = db["stories"].find_one({})
    assert story["source_count"] == 7 and story["article_count"] == 7
    assert db["news"].count_documents({"is_lead": True}) == 1


def test_recluster_keeps_story_ids_stable_and_is_idempotent(db):
    for title, source, minutes in GEMINI[:4]:
        ingest(db, make_raw(title, description="Google said its Gemini AI model hacked three companies during a security test, according to a report.", published=ago(hours=minutes)), make_source(db, name=source))
    cluster.recluster(db, hours=48)
    gid = db["stories"].find_one({})["_id"]
    again = cluster.recluster(db, hours=48)
    assert again["moved"] == 0 and again["merged_groups"] == 0 and db["stories"].find_one({})["_id"] == gid


def test_recluster_never_merges_unrelated_stories_or_grows_mega_stories(db):
    unrelated = ["OpenAI announces new AI model", "Heavy flooding hits southern India as rivers overflow", "Central bank holds interest rates steady",
                 "NASA rocket reaches orbit after smooth launch", "Apple unveils new iPhone with faster chip", "Apple reports record quarterly earnings"]
    for t in unrelated:
        ingest(db, make_raw(t, description="A short description of the event that is long enough to be kept as a teaser."), make_source(db))
    assert cluster.recluster(db, hours=48)["merged_groups"] == 0
    assert db["stories"].count_documents({}) == len(unrelated)
