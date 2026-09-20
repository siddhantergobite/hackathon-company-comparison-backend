from backend.events.processors import classify
from backend.events.processors.classify import classify_event, classify_rules, make_summary
from backend.events.processors.deduplicate import normalize_title, score_pair, title_similarity
from backend.events.processors.normalize import normalize_event
from backend.events.tests.conftest import days, make_raw


def _ev(**over):
    return normalize_event(make_raw(**over))[0]


# ------------------------------------------------------------------------------- dedupe
def test_normalize_title_ignores_year_case_and_ampersand():
    assert normalize_title("AI & ML Summit 2026") == normalize_title("ai and ml summit")
    assert normalize_title("The Global AI Summit 2027") == "global ai summit"


def test_spec_example_titles_are_related_but_not_identical():
    assert title_similarity("AI Summit 2026", "AI & ML Summit 2026") >= 0.85
    assert title_similarity("AI Summit 2026", "Global AI Summit 2026") >= 0.85
    assert title_similarity("AI Summit 2026", "Cooking Festival") < 0.5


def test_same_event_two_sources_scores_high():
    a = _ev(title="AI & ML Summit 2026", source={"name": "A", "source_event_id": "1"})
    b = _ev(title="AI and ML Summit 2026", source={"name": "B", "source_event_id": "9"})
    score, reasons = score_pair(a, b)
    assert score >= 0.9, (score, reasons)


def test_near_titles_same_day_city_are_only_possible():
    a = _ev(title="AI Summit 2026", source={"name": "A", "source_event_id": "1"})
    b = _ev(title="Global AI Summit 2026 for Healthcare", source={"name": "B", "source_event_id": "2"})
    score, _ = score_pair(a, b)
    assert 0.75 <= score < 0.9  # flagged for a human, never auto-merged


def test_different_city_or_date_is_never_a_duplicate():
    a = _ev(title="AI Summit 2026")
    other_city = _ev(title="AI Summit 2026", location={"city": "Paris", "country": "France"}, source={"name": "B", "source_event_id": "2"})
    other_date = _ev(title="AI Summit 2026", start_date=days(90), end_date=days(91), source={"name": "C", "source_event_id": "3"})
    assert score_pair(a, other_city)[0] <= 0.5
    assert score_pair(a, other_date)[0] == 0.0


def test_same_source_id_is_exact():
    a = _ev()
    assert score_pair(a, dict(a)) == (1.0, ["same source event id"])


# ---------------------------------------------------------------------------- classify
def test_rules_classify_type_categories_audience():
    ev = _ev(
        title="Startup Pitch Night for Founders and Investors",
        event_type=None, description="Founders pitch to angel investors and venture capital funds. Seed stage startups welcome.",
    )
    c = classify_rules(ev)
    assert c.event_type == "startup_event"
    assert "Startups" in c.categories
    assert "Founders" in c.audience and "Investors" in c.audience
    assert c.summary


def test_type_from_title_beats_body():
    ev = _ev(title="Kubernetes Hackathon", event_type=None, description="A conference-style weekend of building.")
    assert classify_rules(ev).event_type == "hackathon"


def test_classify_only_fills_missing_and_never_overwrites():
    ev = _ev(categories=["Real Estate"], summary="My own summary.", event_type="expo")
    updates = classify_event(ev)
    assert "categories" not in updates and "summary" not in updates and "event_type" not in updates
    forced = classify_event(ev, force=True)
    assert "categories" in forced  # force replaces


def test_summary_fallback_without_description():
    ev = _ev(description=None, event_type="meetup")
    assert "Berlin" in make_summary(ev)


def test_ai_failure_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(classify, "ai_available", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("All LLM providers failed")

    monkeypatch.setattr(classify, "_llm_chat", boom)
    ev = _ev(event_type=None, categories=[], summary=None)
    updates = classify_event(ev, use_ai=True)
    assert updates["event_type"] and updates["summary"]  # rule-based result still applied
    assert updates.get("classified_by") == "rules"


def test_ai_bad_json_falls_back(monkeypatch):
    monkeypatch.setattr(classify, "ai_available", lambda: True)

    monkeypatch.setattr(classify, "_llm_chat", lambda messages: "sorry, I can't")
    ev = _ev(event_type=None, summary=None)
    assert classify.classify_llm(ev) is None
    assert classify_event(ev, use_ai=True)["summary"]


def test_ai_good_response_is_used_and_validated(monkeypatch):
    monkeypatch.setattr(classify, "ai_available", lambda: True)
    payload = '{"summary":"AI summary.","event_type":"Conference","categories":["ai","Made Up Cat"],"topics":["LLM"],"audience":["CTOs"],"keywords":[]}'

    monkeypatch.setattr(classify, "_llm_chat", lambda messages: "```json\n" + payload + "\n```")
    ev = _ev(event_type=None, summary=None, categories=[])
    up = classify_event(ev, use_ai=True)
    assert up["summary"] == "AI summary." and up["event_type"] == "conference"
    assert up["categories"] == ["Artificial Intelligence", "Made Up Cat"]
    assert up["classified_by"] == "llm"


def test_numbered_editions_are_different_events():
    a = _ev(title="Founders Meetup #7", start_date=days(10), end_date=days(10), source={"name": "A", "source_event_id": "1"})
    b = _ev(title="Founders Meetup #8", start_date=days(11), end_date=days(11), source={"name": "A", "source_event_id": "2"})
    assert score_pair(a, b)[0] < 0.75
    same = _ev(title="Founders Meetup #7", start_date=days(10), end_date=days(10), source={"name": "B", "source_event_id": "3"})
    assert score_pair(a, same)[0] >= 0.9   # same number -> still recognised as the same event
