import json

import pytest

from backend.services import company_research, llm_judge, research_authenticity


@pytest.fixture(autouse=True)
def clear_contact_cache():
    with company_research._PUBLIC_CONTACT_CACHE_LOCK:
        company_research._PUBLIC_CONTACT_CACHE.clear()
    yield
    with company_research._PUBLIC_CONTACT_CACHE_LOCK:
        company_research._PUBLIC_CONTACT_CACHE.clear()


def _site() -> dict:
    return {
        "_page_urls": {"leadership_text": "https://acme.example/team"},
        "_structured": {},
        "leadership_text": "Acme leadership\nAlice Example\nChief Executive Officer",
        "about_text": "Acme builds public infrastructure software.",
        "homepage_text": "Acme public infrastructure software.",
        "contact_data": {"emails": [], "phones": [], "source_pages": []},
        "_wikidata": {},
    }


def test_public_contact_is_shown_only_after_candidate_and_judge(monkeypatch):
    evidence_row = {
        "href": "https://acme.example/team",
        "title": "Acme leadership — Alice Example, CEO",
        "body": "Alice Example is the current Chief Executive Officer of Acme.",
    }
    monkeypatch.setattr(company_research, "_ddg_search", lambda *_args, **_kwargs: [evidence_row])

    responses = iter([
        json.dumps({
            "name": "Alice Example",
            "title": "Chief Executive Officer",
            "source_urls": ["https://acme.example/team"],
        }),
        json.dumps({
            "accept": True,
            "name": "Alice Example",
            "title": "Chief Executive Officer",
            "source_urls": ["https://acme.example/team"],
            "confidence": "High",
            "reason": "The company leadership page names the current CEO.",
        }),
    ])
    monkeypatch.setattr(company_research.llm_client, "chat", lambda *_args, **_kwargs: next(responses))

    result = company_research._public_contact_fallback(
        "Acme", "acme.example", _site(), {}, []
    )

    assert result["status"] == "verified"
    assert result["contact"]["name"] == "Alice Example"
    assert result["contact"]["title"] == "Chief Executive Officer"
    assert result["contact"]["verified"] is True
    assert result["contact"]["source_urls"] == ["https://acme.example/team"]


def test_contact_judge_rejects_values_not_in_public_evidence(monkeypatch):
    monkeypatch.setattr(
        llm_judge.llm_client,
        "chat",
        lambda *_args, **_kwargs: json.dumps({
            "accept": True,
            "name": "Invented Person",
            "title": "CEO",
            "email": "invented@acme.example",
            "source_urls": ["https://acme.example/team"],
            "confidence": "High",
        }),
    )
    result = llm_judge.judge_public_point_of_contact(
        website_url="https://acme.example/",
        domain="acme.example",
        company_name="Acme",
        candidate={"name": "Invented Person"},
        evidence=[{
            "url": "https://acme.example/team",
            "title": "Acme leadership",
            "snippet": "Alice Example is the current CEO of Acme.",
        }],
        existing_leaders=[],
    )

    assert result["accept"] is False
    assert not result.get("name")
    assert not result.get("email")


def test_point_of_contact_prefers_named_email_over_generic_inbox():
    report = {
        "company_profile": {"name": "Acme"},
        "contact_intelligence": {
            "emails": [
                {"email": "info@acme.example", "label": "General", "source": "Company Website"},
                {
                    "email": "alice@acme.example",
                    "person": "Alice Example",
                    "title": "CEO",
                    "source": "Company Website",
                },
            ],
            "phones": [],
        },
        "leadership_team": [],
    }

    contact = research_authenticity.select_point_of_contact(report)

    assert contact["name"] == "Alice Example"
    assert contact["email"] == "alice@acme.example"


def test_contact_fallback_failure_is_fail_soft_and_cached(monkeypatch):
    search_calls = {"count": 0}

    def fail_search(*_args, **_kwargs):
        search_calls["count"] += 1
        raise RuntimeError("temporary search outage")

    monkeypatch.setattr(company_research, "_ddg_search", fail_search)
    monkeypatch.setattr(
        company_research.llm_client,
        "chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )

    first = company_research._public_contact_fallback("Acme", "acme.example", _site(), {}, [])
    second = company_research._public_contact_fallback("Acme", "acme.example", _site(), {}, [])

    assert first["status"] in {"no_public_evidence", "candidate_unavailable", "candidate_empty"}
    assert second == first
    assert search_calls["count"] == 3


def test_verified_fallback_is_attached_as_the_report_point_of_contact(monkeypatch):
    report = {
        "company_profile": {"name": "Acme"},
        "contact_intelligence": {"emails": [], "phones": []},
        "leadership_team": [],
    }
    monkeypatch.setattr(
        company_research,
        "_public_contact_fallback",
        lambda *_args, **_kwargs: {
            "status": "verified",
            "source_urls": ["https://acme.example/team"],
            "contact": {
                "name": "Alice Example",
                "title": "CEO",
                "email": "alice@acme.example",
                "phone": "",
                "source": "Public contact judge",
                "source_urls": ["https://acme.example/team"],
                "confidence": "High",
                "verified": True,
                "reason": "Named on the public leadership page.",
            },
        },
    )

    company_research._maybe_add_public_point_of_contact(
        report, "Acme", "acme.example", _site(), {}
    )
    contact = research_authenticity.select_point_of_contact(report)

    assert contact["name"] == "Alice Example"
    assert contact["email"] == "alice@acme.example"
    assert report["_contact_verification"]["status"] == "verified"


def test_existing_public_contact_does_not_replace_the_report():
    report = {
        "company_profile": {"name": "Acme"},
        "products_services": {"primary_offerings": [{"item": "Infrastructure software"}]},
        "contact_intelligence": {
            "emails": [{"email": "alice@acme.example", "person": "Alice Example"}],
            "phones": [],
        },
        "leadership_team": [],
    }

    returned = company_research._maybe_add_public_point_of_contact(
        report, "Acme", "acme.example", _site(), {}
    )

    assert returned is report
    assert returned["company_profile"]["name"] == "Acme"
    assert returned["products_services"]["primary_offerings"]
    assert returned["_contact_verification"]["status"] == "existing_public_contact"


def test_parked_domain_is_not_company_evidence():
    assert company_research._is_parked_page_text(
        "MnrSolutions.com (domain listing on HugeDomains)",
        "This domain is for sale",
    )
    assert not company_research._is_parked_page_text(
        "Acme leadership", "Acme is a software company"
    )


def test_ai_profile_judge_labels_model_knowledge_and_strips_ungrounded_contact(monkeypatch):
    monkeypatch.setattr(
        llm_judge.llm_client,
        "chat",
        lambda *_args, **_kwargs: json.dumps({
            "overall_score": 82,
            "summary": "The leader is supported; the email was not supported.",
            "leadership": [{
                "name": "Alice Example",
                "role": "CEO",
                "status": "current",
                "keep": True,
                "confidence": "High",
                "verification_status": "evidence-verified",
                "source_urls": ["https://acme.example/team"],
            }],
            "point_of_contact": {
                "keep": True,
                "name": "Alice Example",
                "title": "CEO",
                "email": "alice@example.com",
                "confidence": "High",
                "verification_status": "evidence-verified",
                "source_urls": ["https://acme.example/team"],
            },
            "business_profile": {
                "competitor_candidates": [{
                    "name": "SAP",
                    "official_domain": "sap.com",
                    "market_location": "Global",
                    "overlap_reason": "Enterprise software overlap",
                    "keep": True,
                    "confidence": "High",
                    "source_urls": ["https://sap.com/about"],
                }],
            },
        }),
    )

    result = llm_judge.judge_ai_profile(
        website_url="https://acme.example/",
        domain="acme.example",
        company_name="Acme",
        candidate={"leadership": [{"name": "Alice Example"}]},
        evidence=[{
            "url": "https://acme.example/team",
            "title": "Acme leadership",
            "snippet": "Alice Example is the current CEO of Acme.",
        }, {
            "url": "https://sap.com/about",
            "title": "SAP enterprise software",
            "snippet": "SAP provides enterprise software for businesses.",
        }],
    )

    assert result["leadership"][0]["verification_status"] == "evidence-verified"
    assert result["point_of_contact"]["name"] == "Alice Example"
    assert result["point_of_contact"]["email"] == ""
    assert result["business_profile"]["competitor_candidates"][0]["official_domain"] == "sap.com"


def test_ai_profile_fallback_adds_judged_leader_and_point_of_contact(monkeypatch):
    monkeypatch.setattr(company_research, "RESEARCH_AI_PROFILE_FALLBACK", True)
    monkeypatch.setattr(
        company_research,
        "_ai_profile_evidence",
        lambda *_args, **_kwargs: [{
            "url": "https://acme.example/team",
            "title": "Acme leadership",
            "snippet": "Bob Example is the current CEO of Acme.",
            "source": "Company Website",
        }],
    )
    responses = iter([
        json.dumps({
            "leadership": [{
                "name": "Bob Example",
                "role": "CEO",
                "status": "current",
                "basis": "evidence",
                "confidence": "High",
            }],
            "point_of_contact": {"name": "Bob Example", "title": "CEO", "confidence": "High"},
        }),
        json.dumps({
            "overall_score": 88,
            "summary": "Bob Example is supported by the company team page.",
            "leadership": [{
                "name": "Bob Example",
                "role": "CEO",
                "status": "current",
                "keep": True,
                "confidence": "High",
                "verification_status": "evidence-verified",
                "source_urls": ["https://acme.example/team"],
            }],
            "point_of_contact": {
                "keep": True,
                "name": "Bob Example",
                "title": "CEO",
                "confidence": "High",
                "verification_status": "evidence-verified",
                "source_urls": ["https://acme.example/team"],
            },
        }),
    ])
    monkeypatch.setattr(company_research.llm_client, "chat", lambda *_args, **_kwargs: next(responses))

    report = {
        "company_profile": {"name": "Acme", "headquarters": {"value": "Not publicly available"}},
        "contact_intelligence": {"emails": [], "phones": []},
        "leadership_team": [],
    }
    result = company_research._run_ai_profile_fallback(
        report, "Acme", "acme.example", _site(), {}
    )

    assert result["ai_enrichment"]["status"] == "complete"
    assert result["ai_enrichment"]["judge_score"] == 88
    assert result["leadership_team"][0]["name"] == "Bob Example"
    assert result["leadership_team"][0]["verification_status"] == "evidence-verified"
    contact = research_authenticity.select_point_of_contact(result)
    assert contact["name"] == "Bob Example"
    assert contact["verification_status"] == "evidence-verified"


def test_ai_profile_evidence_preserves_search_query_context(monkeypatch):
    monkeypatch.setattr(
        company_research,
        "_ddg_search",
        lambda query, **_kwargs: [{
            "href": "https://acme.example/public-leadership",
            "title": "Acme leadership",
            "body": f"Public result for {query}",
        }],
    )

    records = company_research._ai_profile_evidence("Acme", "acme.example", _site(), {})

    assert records
    assert any("Search query:" in record["snippet"] for record in records)
