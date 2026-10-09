from backend.services import company_research


def test_normalize_report_filters_news_using_requested_domain(monkeypatch):
    monkeypatch.setattr(company_research, "RESEARCH_DEEP", False)
    news_page = {
        "category": "News",
        "title": "Expleo announces expanded digital engineering services",
        "domain": "reuters.com",
        "url": "https://www.reuters.com/technology/expleo-digital-engineering-expansion/",
        "text": "Expleo announced an expansion of its digital engineering services.",
    }
    scraped = {
        "title": "Expleo",
        "description": "Expleo provides engineering and technology services.",
        "wikipedia_summary": "Expleo is an engineering, technology and consulting company.",
        "wikipedia_description": "Engineering and technology services company",
        "contact_data": {},
        "tech_hints": [],
    }
    intel = {"_scraped_pages": [news_page], "_source_urls": [], "_wikidata": {}}

    report = company_research._normalize_report(
        {}, scraped, "Expleo", "https://expleo.com/", intel
    )

    assert report["company_profile"]["name"] == "Expleo"
    assert report["recent_news"]
    assert report["recent_news"][0]["title"] == news_page["title"]
