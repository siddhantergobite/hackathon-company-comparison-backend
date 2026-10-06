from backend.services import live_jobs


def test_result_batches_are_five_rows_and_cover_the_exact_result():
    result = {"jobs": [{"id": f"job-{index}", "url": f"https://example.test/{index}"} for index in range(12)]}
    events = []

    live_jobs._emit_result_batches(result, events.append)

    assert [len(event["jobs"]) for event in events] == [5, 5, 2]
    assert [event["batch_index"] for event in events] == [1, 2, 3]
    assert all(event["batch_count"] == 3 for event in events)
    assert [job["id"] for event in events for job in event["jobs"]] == [f"job-{index}" for index in range(12)]
    assert all("jobs" not in event["summary"] for event in events)


def test_scan_emits_early_five_then_authoritative_batches(monkeypatch):
    monkeypatch.setattr(live_jobs, "get_bench", lambda: {"people": {}})
    monkeypatch.setattr(live_jobs, "search_queries_for_scan", lambda _bench: ["software engineer"])
    monkeypatch.setattr(live_jobs, "_collect_linkedin_live", lambda _terms, _locations=None: [
        {
            "url": f"https://www.linkedin.com/jobs/view/{index}",
            "title": f"Software Engineer {index}",
            "description": "Python software engineering",
            "posted_minutes": index,
        }
        for index in range(7)
    ])
    monkeypatch.setattr(live_jobs, "_enrich_linkedin_descriptions", lambda _jobs: None)

    events = []
    result = live_jobs.scan(minutes=30, sources=["linkedin"], on_batch=events.append)

    assert events[0]["phase"] == "early"
    assert len(events[0]["jobs"]) == 5
    final_events = [event for event in events if event["phase"] == "final"]
    assert [len(event["jobs"]) for event in final_events] == [5, 2]
    assert [job["id"] for event in final_events for job in event["jobs"]] == [
        job["id"] for job in result["jobs"]
    ]
