import pytest

from backend.news.collectors.base import CollectorError
from backend.news.collectors.newsapi import NewsApiCollector
from backend.news.collectors.registry import make_collector
from backend.news.collectors.rss import RssCollector, entry_to_raw
from backend.news.pipeline import run_source
from backend.news.tests.conftest import make_source

RSS = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Example</title>
<item><title>OpenAI announces new AI model</title><link>https://example.org/a?utm_source=rss</link>
 <description>&lt;p&gt;OpenAI said on Tuesday it released a new model for developers.&lt;/p&gt;</description>
 <pubDate>Sat, 19 Sep 2026 10:00:00 GMT</pubDate><media:thumbnail url="https://example.org/a.jpg"/><category>AI</category></item>
<item><title>Flooding hits southern India as rivers overflow</title><link>https://example.org/b</link>
 <description>Thousands were evacuated. &lt;img src="https://example.org/inline.png"/&gt;</description><pubDate>Sat, 19 Sep 2026 09:00:00 GMT</pubDate></item>
<item><title></title><link>https://example.org/c</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Feed</title>
<entry><title>NASA rocket reaches orbit after smooth launch</title><link href="https://example.org/nasa"/><updated>2026-09-19T08:00:00Z</updated>
<summary>The satellite launch went well and the rocket reached orbit as planned.</summary><author><name>Jane</name></author></entry></feed>"""


class Resp:
    def __init__(self, content=b"", status=200, headers=None):
        self.content, self.status_code, self.headers = content, status, headers or {}

    def json(self):
        import json

        return json.loads(self.content)


class Client:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return self.resp


def test_rss_entries_are_mapped_with_images_tags_and_dates():
    client = Client(Resp(RSS, headers={"ETag": '"v1"', "Last-Modified": "Sat, 19 Sep 2026 10:00:00 GMT"}))
    res = RssCollector(client=client).fetch({"url": "https://example.org/feed"})
    assert len(res.items) == 3 and res.etag == '"v1"'
    first, second = res.items[0], res.items[1]
    assert first["title"] == "OpenAI announces new AI model" and first["image"] == "https://example.org/a.jpg" and first["tags"] == ["AI"]
    assert first["published"] is not None
    assert second["image"] == "https://example.org/inline.png"            # falls back to an <img> in the teaser


def test_atom_feeds_work_too():
    res = RssCollector(client=Client(Resp(ATOM))).fetch({"url": "https://example.org/atom"})
    assert res.items[0]["title"].startswith("NASA rocket") and res.items[0]["link"] == "https://example.org/nasa" and res.items[0]["author"] == "Jane"


def test_conditional_get_headers_are_sent_and_304_is_free():
    client = Client(Resp(status=304))
    res = RssCollector(client=client).fetch({"url": "https://example.org/feed", "etag": '"v1"', "last_modified": "Sat, 19 Sep 2026 10:00:00 GMT"})
    sent = client.calls[0][1]["headers"]
    assert sent["If-None-Match"] == '"v1"' and sent["If-Modified-Since"].startswith("Sat, 19 Sep")
    assert res.not_modified and res.items == [] and res.etag == '"v1"'


def test_non_feed_content_is_reported_not_crashed():
    with pytest.raises(CollectorError, match="not a valid RSS/Atom feed"):
        RssCollector(client=Client(Resp(b"<html><body>Please enable JavaScript</body></html>"))).fetch({"url": "https://example.org/x"})
    assert RssCollector(client=Client(Resp(b'<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>'))).fetch({"url": "https://x.org/e"}).items == []


def test_rss_end_to_end_through_the_pipeline(db):
    src = make_source(db, name="Example Wire")
    res = run_source(db, src, collector=RssCollector(client=Client(Resp(RSS))))
    assert res["counts"]["created"] == 2 and res["counts"]["invalid"] == 1
    doc = db["news"].find_one({"title": "OpenAI announces new AI model"})
    assert doc["url"] == "https://example.org/a" and doc["image_url"] == "https://example.org/a.jpg"
    assert doc["source"]["name"] == "Example Wire" and doc["content"] is None and doc["category"] == "ai"


def test_newsapi_needs_a_key_and_a_scope():
    class NoKey:
        news_api_key = ""
        user_agent = "t"

    class WithKey(NoKey):
        news_api_key = "k"

    with pytest.raises(CollectorError, match="NEWS_API_KEY"):
        NewsApiCollector(NoKey(), Client(Resp())).fetch({"config": {"sources": "reuters"}})
    with pytest.raises(CollectorError, match="needs sources"):
        NewsApiCollector(WithKey(), Client(Resp())).fetch({"config": {}})


def test_newsapi_items_keep_the_real_publisher_name(db):
    import json

    payload = {"status": "ok", "articles": [
        {"title": "Central bank holds interest rates steady", "url": "https://reuters.com/x", "description": "The bank kept rates unchanged on Thursday, as expected.", "publishedAt": "2026-09-19T10:00:00Z", "urlToImage": "https://img/x.jpg", "source": {"name": "Reuters"}, "author": "A"},
        {"title": "[Removed]", "url": "https://removed.com", "source": {"name": "X"}},
    ]}

    class S:
        news_api_key = "k"
        user_agent = "t"

    src = make_source(db, name="NewsAPI wire", type="newsapi", url=None, config={"sources": "reuters"})
    res = run_source(db, src, collector=NewsApiCollector(S(), Client(Resp(json.dumps(payload).encode()))))
    assert res["counts"]["created"] == 1
    doc = db["news"].find_one({})
    assert doc["source"]["name"] == "Reuters" and doc["source"]["via"] == "NewsAPI wire"


def test_newsapi_error_payloads_surface_clearly():
    import json

    class S:
        news_api_key = "k"
        user_agent = "t"

    body = json.dumps({"status": "error", "message": "Your API key is invalid"}).encode()
    with pytest.raises(CollectorError, match="invalid"):
        NewsApiCollector(S(), Client(Resp(body))).fetch({"config": {"sources": "reuters"}})


def test_registry_selects_collector_by_type():
    assert isinstance(make_collector({"type": "rss"}), RssCollector) and isinstance(make_collector({"type": "newsapi"}), NewsApiCollector)
    with pytest.raises(ValueError):
        make_collector({"type": "carrier-pigeon"})


def test_entry_to_raw_handles_content_only_entries():
    class E(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    raw = entry_to_raw(E({"title": "T", "link": "https://x.org/a", "content": [{"value": "<p>Body text of the entry here.</p>"}]}))
    assert "Body text" in raw["description"] and raw["image"] is None
