"""Public News API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from backend.common.errors import ApiError, HubRoute
from backend.news.cache import cache
from backend.news.config import get_settings
from backend.news.database import get_db
from backend.news.models import ArticleOut, ArticlePage, ArticleSummary, StoryDetail
from backend.news.services import news_service as svc
from backend.news.services.news_service import ListParams

router = APIRouter(prefix="/api/news", tags=["news"], route_class=HubRoute)


def _short() -> int:
    return get_settings().cache_ttl_short


def _long() -> int:
    return get_settings().cache_ttl_long


def _params(
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(20, ge=1, le=50, description="Page size (max 50)"),
    category: str | None = Query(None, description="Category slug or name; 'breaking' and 'all' are supported"),
    source: str | None = Query(None, description="Publisher name (lists that source's individual articles)"),
    topic: str | None = None,
    date_from: str | None = Query(None, alias="from", description="ISO date/datetime"),
    date_to: str | None = Query(None, alias="to", description="ISO date/datetime"),
    sort: str = Query("latest", description="latest | trending | importance"),
    group: bool = Query(True, description="true: one card per story; false: every article"),
    q: str | None = Query(None, max_length=200),
) -> ListParams:
    return ListParams(page=page, limit=limit, category=category, source=source, topic=topic, date_from=date_from,
                      date_to=date_to, sort=sort, group=group, q=q)


def _key(name: str, p: ListParams) -> tuple:
    return (name, *sorted(p.__dict__.items()))


@router.get("", response_model=ArticlePage)
def list_news(p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    return cache.get_or_set(_key("list", p), _short(), lambda: svc.list_articles(db, p))


# NOTE: fixed paths are declared before "/{article_id}".
@router.get("/latest", response_model=ArticlePage)
def latest(p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    p.sort = "latest"
    return cache.get_or_set(_key("latest", p), _short(), lambda: svc.list_articles(db, p))


@router.get("/trending")
def trending(limit: int = Query(10, ge=1, le=30), db: Database = Depends(get_db)):
    return cache.get_or_set(("trending", limit), _short(), lambda: {"articles": svc.trending(db, limit)})


@router.get("/top-stories")
def top_stories(limit: int = Query(5, ge=1, le=12), db: Database = Depends(get_db)):
    return cache.get_or_set(("top", limit), _short(), lambda: {"articles": svc.top_stories(db, limit)})


@router.get("/whats-happening")
def whats_happening(per_group: int = Query(3, ge=1, le=6), db: Database = Depends(get_db)):
    return cache.get_or_set(("now", per_group), _short(), lambda: {"groups": svc.whats_happening(db, per_group)})


@router.get("/search", response_model=ArticlePage)
def search(p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    if not p.q or len(p.q.strip()) < 2:
        raise ApiError(400, "Provide a search term: /api/news/search?q=OpenAI (at least 2 characters)")
    return cache.get_or_set(_key("search", p), _short(), lambda: svc.list_articles(db, p))


@router.get("/categories")
def categories(db: Database = Depends(get_db)):
    return cache.get_or_set(("categories",), _long(), lambda: svc.list_categories(db))


@router.get("/sources")
def sources(db: Database = Depends(get_db)):
    return cache.get_or_set(("sources",), _long(), lambda: svc.list_sources(db))


@router.get("/topics")
def topics(limit: int = Query(24, ge=1, le=60), db: Database = Depends(get_db)):
    return cache.get_or_set(("topics", limit), _long(), lambda: svc.list_topics(db, limit))


@router.get("/category/{category_slug}", response_model=ArticlePage)
def by_category(category_slug: str, p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    p.category = category_slug
    return cache.get_or_set(_key("cat", p), _short(), lambda: svc.list_articles(db, p))


@router.get("/source/{source_name}", response_model=ArticlePage)
def by_source(source_name: str, p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    p.source = source_name
    return cache.get_or_set(_key("src", p), _short(), lambda: svc.list_articles(db, p))


@router.get("/topic/{topic_name}", response_model=ArticlePage)
def by_topic(topic_name: str, p: ListParams = Depends(_params), db: Database = Depends(get_db)):
    p.topic = topic_name
    return cache.get_or_set(_key("topic", p), _short(), lambda: svc.list_articles(db, p))


@router.get("/story/{story_id}", response_model=StoryDetail)
def story(story_id: str, db: Database = Depends(get_db)):
    doc = cache.get_or_set(("story", story_id), _short(), lambda: svc.get_story(db, story_id))
    if not doc:
        raise ApiError(404, "Story not found")
    return doc


@router.get("/related/{article_id}", response_model=list[ArticleSummary])
def related(article_id: str, limit: int = Query(8, ge=1, le=20), db: Database = Depends(get_db)):
    return cache.get_or_set(("related", article_id, limit), _short(), lambda: svc.related_articles(db, article_id, limit))


@router.get("/{article_id}", response_model=ArticleOut)
def article(article_id: str, db: Database = Depends(get_db)):
    doc = cache.get_or_set(("article", article_id), _short(), lambda: svc.get_article(db, article_id))
    if not doc:
        raise ApiError(404, "Article not found")
    return doc
