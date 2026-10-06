from datetime import datetime, timedelta, timezone

from backend.services import live_jobs


def test_greenhouse_board_token_only_accepts_greenhouse_board_hosts():
    assert live_jobs._greenhouse_board_token("https://boards.greenhouse.io/acme") == "acme"
    assert live_jobs._greenhouse_board_token(
        "https://job-boards.greenhouse.io/acme/jobs/123"
    ) == "acme"
    assert live_jobs._greenhouse_board_token("https://example.com/acme/jobs/123") == ""
    assert live_jobs._is_job_url("https://boards.greenhouse.io/acme/jobs/123")


def test_greenhouse_board_url_is_classified_without_guessing_company(monkeypatch):
    monkeypatch.setattr(live_jobs, "_greenhouse_request", lambda _url: {"name": "Acme, Inc."})

    info = live_jobs._classify_source_url("https://boards.greenhouse.io/acme")

    assert info["kind"] == "greenhouse"
    assert info["company"] == "Acme, Inc."


def test_greenhouse_feed_uses_first_published_and_not_updated_at(monkeypatch):
    published = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()

    def fake_request(url):
        if url.endswith("/jobs?content=true"):
            return {
                "jobs": [
                    {"id": 101, "title": "Backend Engineer", "updated_at": published},
                    {"id": 102, "title": "AI Engineer", "updated_at": published},
                ]
            }
        if url.endswith("/jobs/101?content=true"):
            return {
                "id": 101,
                "title": "Backend Engineer",
                "company_name": "Acme",
                "first_published": published,
                "location": {"name": "Remote"},
                "content": "<p>Python and PostgreSQL required.</p>",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
            }
        # Deliberately no first_published: a recent updated_at must not qualify.
        return {"id": 102, "title": "AI Engineer", "updated_at": published}

    monkeypatch.setattr(live_jobs, "_greenhouse_request", fake_request)
    rows = live_jobs._greenhouse_board_jobs("https://boards.greenhouse.io/acme")

    assert len(rows) == 1
    assert rows[0]["title"] == "Backend Engineer"
    assert rows[0]["company"] == "Acme"
    assert rows[0]["platform"] == "Greenhouse"
    assert rows[0]["source"] == "greenhouse_public_board_api"
    assert 44 <= rows[0]["posted_minutes"] <= 46
    assert "Python" in rows[0]["description"]


def test_weak_job_details_return_no_strong_match_and_closest_role_resume():
    evidence = live_jobs._match_evidence(
        {"title": "Software Engineer", "description": "", "track": "software"},
        {
            "people": {
                "ai-person": {
                    "loaded": True,
                    "slot": "ai-person",
                    "name": "AI Candidate",
                    "track": "ai",
                    "skills": ["Python"],
                },
                "software-person": {
                    "loaded": True,
                    "slot": "software-person",
                    "name": "Software Candidate",
                    "track": "software",
                    "skills": ["Java"],
                },
            }
        },
    )

    assert evidence["fit_level"] == "no_strong_match"
    assert evidence["candidate"]["name"] == "Software Candidate"
    assert evidence["candidate"]["basis"] == "role_only"
    assert evidence["matched_skills"] == []


def test_resume_search_queries_prioritize_candidate_roles_then_refine_with_skills():
    people = [
        {
            "loaded": True,
            "title": "Senior Software Developer - Mobile Platform",
            "skills": ["Kotlin", "Android SDK", "Jetpack Compose", "Flutter"],
        },
        {
            "loaded": True,
            "title": "Senior Full-Stack Developer",
            "skills": ["React", "Next.js", "TypeScript", "Node.js"],
        },
        {
            "loaded": True,
            "title": "Backend Software Engineer",
            "skills": ["Java", "Spring Boot", "Python", "PostgreSQL"],
        },
        {
            "loaded": True,
            "title": "AI Engineer - Computer Vision",
            "skills": ["Python", "PyTorch", "OpenCV", "Docker"],
        },
    ]

    queries = live_jobs._heuristic_search_queries(people)

    assert queries[:4] == [
        "android developer",
        "full stack developer",
        "backend engineer",
        "computer vision engineer",
    ]
    assert queries[4:] == [
        "android developer Kotlin",
        "full stack developer React",
        "backend engineer Spring Boot",
        "computer vision engineer OpenCV",
    ]
    assert len(queries) <= 8
    naukri_queries = live_jobs._queries(["naukri"], queries)
    assert 'site:naukri.com "android developer"' in naukri_queries


def test_linkedin_uses_structured_location_and_naukri_keeps_location_in_query(monkeypatch):
    calls = []
    monkeypatch.setattr(
        live_jobs,
        "_linkedin_guest_search",
        lambda keyword, start=0, tpr=live_jobs.TPR_PAST_HOUR, company_id=None, location=None: calls.append(
            (keyword, start, tpr, company_id, location)
        ) or [],
    )

    live_jobs._collect_linkedin_live(["AI engineer"], ["india"])

    assert calls == [("AI engineer", 0, live_jobs.TPR_PAST_HOUR, None, "India"),
                     ("AI engineer", 10, live_jobs.TPR_PAST_HOUR, None, "India")]
    naukri = live_jobs._queries(["naukri"], ["AI engineer"], ["india"])
    assert naukri == ['site:naukri.com AI engineer ("India")']


def test_scan_terms_do_not_encode_location_as_a_linkedin_keyword(monkeypatch):
    monkeypatch.setattr(live_jobs, "search_queries_for_scan", lambda _bench: ["AI engineer"])

    terms, _ = live_jobs._scan_search_terms({"people": {}}, [], ["india"])

    assert terms == ["AI engineer"]


def test_live_scan_filters_jobs_by_selected_skills_and_locations(monkeypatch):
    monkeypatch.setattr(live_jobs, "get_bench", lambda: {"people": {}})
    monkeypatch.setattr(live_jobs, "search_queries_for_scan", lambda _bench: ["software engineer"])
    monkeypatch.setattr(live_jobs, "_collect_linkedin_live", lambda _terms, _locations=None: [
        {
            "url": "https://www.linkedin.com/jobs/view/python-india",
            "title": "Python Engineer",
            "location": "Bengaluru, India",
            "description": "Python and Django backend role",
            "posted_minutes": 5,
        },
        {
            "url": "https://www.linkedin.com/jobs/view/java-usa",
            "title": "Java Engineer",
            "location": "New York, USA",
            "description": "Java and Spring Boot backend role",
            "posted_minutes": 6,
        },
        {
            "url": "https://www.linkedin.com/jobs/view/python-usa",
            "title": "Python Engineer",
            "location": "Seattle, USA",
            "description": "Python and FastAPI backend role",
            "posted_minutes": 7,
        },
        {
            "url": "https://www.linkedin.com/jobs/view/rust-india",
            "title": "Rust Engineer",
            "location": "Pune, India",
            "description": "Rust systems role",
            "posted_minutes": 8,
        },
    ])
    monkeypatch.setattr(live_jobs, "_enrich_linkedin_descriptions", lambda _jobs: None)

    result = live_jobs.scan(
        minutes=30,
        sources=["linkedin"],
        skills=["Python", "Java"],
        locations=["india"],
    )

    assert [job["title"] for job in result["jobs"]] == ["Python Engineer"]
    assert result["filters"] == {"skills": ["Python", "Java"], "locations": ["india"]}
    assert result["dropped"]["skill_filter"] == 1
    assert result["dropped"]["location_filter"] == 2
    assert result["source_diagnostics"]["linkedin"]["filtered_by_skill"] == 1
    assert result["source_diagnostics"]["linkedin"]["filtered_by_location"] == 2


def test_live_scan_filters_support_ai_ml_and_cap_user_input():
    assert live_jobs._normalize_scan_skills(
        ["Python", "Java", "Kotlin", "AI/ML", "React", "Rust", "Python"]
    ) == ["Python", "Java", "Kotlin", "AI/ML", "React"]
    assert live_jobs._job_matches_skill_filters(
        {"title": "Machine Learning Engineer", "description": "Build ML systems"},
        ["AI/ML"],
    )
    assert not live_jobs._job_matches_skill_filters(
        {"title": "Frontend Engineer", "description": "Build React interfaces"},
        ["AI/ML"],
    )


def test_serpapi_search_normalizes_google_results_and_uses_dedicated_key(monkeypatch):
    monkeypatch.setenv("LIVE_JOBS_SERPAPI_KEY", "test-key")
    params_seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"organic_results": [{
                "title": "Backend Engineer",
                "link": "https://www.naukri.com/job-listings/backend-engineer-123",
                "snippet": "Python and PostgreSQL",
            }]}

    def fake_get(url, *, params, timeout):
        params_seen.update(params)
        assert url == "https://serpapi.com/search"
        assert timeout == live_jobs.SEARCH_TIMEOUT_SECONDS
        return Response()

    monkeypatch.setattr(live_jobs.requests, "get", fake_get)

    rows = live_jobs._ddg("site:naukri.com/job-listings backend engineer", 12, "d")

    assert rows == [{
        "title": "Backend Engineer",
        "url": "https://www.naukri.com/job-listings/backend-engineer-123",
        "snippet": "Python and PostgreSQL",
        "search_provider": "serpapi_google",
    }]
    assert params_seen["api_key"] == "test-key"
    assert params_seen["tbs"] == "qdr:d"
    assert params_seen["gl"] == "in"


def test_naukri_undated_results_are_returned_but_not_counted_as_fresh(monkeypatch):
    monkeypatch.setattr(live_jobs, "get_bench", lambda: {"people": {}})
    monkeypatch.setattr(live_jobs, "search_queries_for_scan", lambda _bench: ["backend engineer"])
    monkeypatch.setattr(live_jobs, "_ddg", lambda *_args: [{
        "title": "Backend Engineer",
        "url": "https://www.naukri.com/job-listings/backend-engineer-123",
        "snippet": "Python and PostgreSQL",
        "search_provider": "serpapi_google",
    }])
    monkeypatch.setattr(live_jobs, "_fetch_job_page", lambda _url: {"html": "", "text": ""})
    monkeypatch.setattr(live_jobs, "_enrich_linkedin_descriptions", lambda _jobs: None)

    result = live_jobs.scan(minutes=30, sources=["naukri"], include_unverified_recent=True)

    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["recency"] == "date_unverified"
    assert result["jobs"][0]["date_confidence"] == "unverified"
    assert result["in_window_count"] == 0
    assert result["verified_job_count"] == 0
    assert result["unverified_job_count"] == 1
    assert result["source_diagnostics"]["naukri"]["date_unverified"] == 1
    assert result["source_diagnostics"]["naukri"]["search_providers"] == {"serpapi_google": 1}


def test_undated_naukri_jobs_keep_visible_slots_when_linkedin_fills_verified_cap(monkeypatch):
    monkeypatch.setattr(live_jobs, "get_bench", lambda: {"people": {}})
    monkeypatch.setattr(live_jobs, "search_queries_for_scan", lambda _bench: ["software engineer"])
    monkeypatch.setattr(live_jobs, "_collect_linkedin_live", lambda _terms, _locations=None: [
        {
            "url": f"https://www.linkedin.com/jobs/view/{index}",
            "title": f"Software Engineer {index}",
            "posted_minutes": 5,
            "description": "Python software engineering",
        }
        for index in range(live_jobs.MAX_JOBS)
    ])
    monkeypatch.setattr(live_jobs, "_ddg", lambda *_args: [
        {
            "title": f"Backend Engineer {index}",
            "url": f"https://www.naukri.com/job-listings/backend-engineer-{index}",
            "snippet": "Backend engineering position",
        }
        for index in range(5)
    ])
    monkeypatch.setattr(live_jobs, "_fetch_job_page", lambda _url: {"html": "", "text": ""})
    monkeypatch.setattr(live_jobs, "_enrich_linkedin_descriptions", lambda _jobs: None)

    result = live_jobs.scan(
        minutes=30,
        sources=["linkedin", "naukri"],
        include_unverified_recent=True,
    )

    assert result["verified_job_count"] == live_jobs.MAX_JOBS - 5
    assert result["unverified_job_count"] == 5
    assert len(result["jobs"]) == live_jobs.MAX_JOBS
    assert sum(job["platform"] == "Naukri" for job in result["jobs"]) == 5
    assert sum(job["platform"] == "LinkedIn" for job in result["jobs"]) == 15
    assert result["source_diagnostics"]["naukri"]["display_target_min"] == 5
    assert result["source_diagnostics"]["naukri"]["display_target_max"] == 8


def test_company_discovery_respects_requested_window_and_keeps_only_naukri_undated(monkeypatch):
    monkeypatch.setattr(live_jobs, "get_bench", lambda: {"people": {}})
    monkeypatch.setattr(live_jobs, "_enrich_linkedin_descriptions", lambda _jobs: None)
    monkeypatch.setattr(live_jobs, "_attach_talent", lambda job, _bench: job)
    rows = [
        {
            "title": "Backend Engineer", "company": "Acme",
            "url": "https://www.naukri.com/job-listings/backend-engineer-123",
            "platform": "Naukri", "posted_minutes": 10 * 24 * 60,
        },
        {
            "title": "Frontend Engineer", "company": "Acme",
            "url": "https://www.naukri.com/job-listings/frontend-engineer-456",
            "platform": "Naukri", "posted_minutes": None,
        },
        {
            "title": "QA Engineer", "company": "Acme",
            "url": "https://boards.greenhouse.io/acme/jobs/789",
            "platform": "Greenhouse", "posted_minutes": None,
        },
    ]
    metrics = {}

    jobs = live_jobs._finalize_url_jobs(rows, "Acme", require_company=False, window_days=7, metrics=metrics)

    assert [job["title"] for job in jobs] == ["Frontend Engineer"]
    assert jobs[0]["recency"] == "date_unverified"
    assert metrics["within_window"] == 0
    assert metrics["outside_window"] == 1
    assert metrics["date_unverified"] == 2
