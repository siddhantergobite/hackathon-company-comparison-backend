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


def test_resume_search_queries_combine_each_candidate_role_with_extracted_skills():
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
        "android developer Kotlin Android SDK",
        "full stack developer React Node.js",
        "backend engineer Spring Boot Java",
        "computer vision engineer OpenCV PyTorch",
    ]
    assert len(queries) <= 8
    naukri_queries = live_jobs._queries(["naukri"], queries)
    assert "site:naukri.com/job-listings android developer Kotlin Android SDK" in naukri_queries
