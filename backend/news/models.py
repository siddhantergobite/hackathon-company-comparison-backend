"""Pydantic schemas for the News API.

Read models are lenient (every field optional) so a partially-populated document can never
make a read endpoint fail. Write models validate admin input.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    url: str | None = None


class Coverage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    count: int = 1
    sources: list[str] = Field(default_factory=list)


class _Read(BaseModel):
    model_config = ConfigDict(extra="ignore")

    @field_validator("source", mode="before", check_fields=False)
    @classmethod
    def _src(cls, v: Any) -> Any:
        return {} if v is None else v

    @field_validator("coverage", mode="before", check_fields=False)
    @classmethod
    def _cov(cls, v: Any) -> Any:
        return {"count": 1, "sources": []} if v is None else v

    @field_validator("topics", "entities", "location", "categories", "key_points", mode="before", check_fields=False)
    @classmethod
    def _list(cls, v: Any) -> Any:
        return [] if v is None else v


class ArticleSummary(_Read):
    """What a card needs."""

    id: str
    title: str
    summary: str | None = None
    description: str | None = None
    url: str | None = None
    image_url: str | None = None
    source: SourceRef = Field(default_factory=SourceRef)
    category: str | None = None
    categories: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    collected_at: datetime | None = None
    last_activity_at: datetime | None = None
    importance_score: float = 0
    trending_score: float = 0
    duplicate_group_id: str | None = None
    is_breaking: bool = False
    coverage: Coverage = Field(default_factory=Coverage)
    ai_status: str | None = None


class ArticleOut(ArticleSummary):
    """Full article record (never contains the publisher's full text)."""

    key_points: list[str] = Field(default_factory=list)
    event: str | None = None
    entities_detail: dict[str, list[str]] = Field(default_factory=dict)
    language: str | None = None
    author: str | None = None
    summary_source: str | None = None
    content: str | None = None
    status: str | None = None


class ArticlePage(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    has_more: bool
    articles: list[ArticleSummary]


class StoryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str | None = None
    summary: str | None = None
    category: str | None = None
    categories: list[str] = Field(default_factory=list)
    image_url: str | None = None
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    article_count: int = 1
    source_count: int = 1
    sources: list[str] = Field(default_factory=list)
    lead_article_id: str | None = None
    first_published_at: datetime | None = None
    last_activity_at: datetime | None = None
    trending_score: float = 0
    importance_score: float = 0
    is_breaking: bool = False


class StoryDetail(BaseModel):
    story: StoryOut
    lead: ArticleOut | None = None
    articles: list[ArticleSummary]


# -------------------------------------------------------------------- admin write models
class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=120)
    type: str = Field(default="rss", pattern="^(rss|newsapi)$")
    url: str | None = Field(default=None, max_length=2048)
    homepage: str | None = Field(default=None, max_length=2048)
    category: str | None = Field(default=None, max_length=60, description="Default category hint for this source")
    language: str = "en"
    country: str | None = None
    enabled: bool = True
    poll_minutes: int = Field(default=15, ge=1, le=1440)
    priority: int = Field(default=3, ge=1, le=5, description="Editorial weight 1-5 used in importance scoring")
    config: dict[str, Any] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, min_length=2, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    homepage: str | None = None
    category: str | None = None
    language: str | None = None
    country: str | None = None
    enabled: bool | None = None
    poll_minutes: int | None = Field(default=None, ge=1, le=1440)
    priority: int | None = Field(default=None, ge=1, le=5)
    config: dict[str, Any] | None = None


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=2, max_length=60)
    icon: str | None = Field(default=None, max_length=8)
    keywords: list[str] = Field(default_factory=list, max_length=200)
    order: int = Field(default=500, ge=0, le=10000)
    enabled: bool = True


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, min_length=2, max_length=60)
    icon: str | None = None
    keywords: list[str] | None = None
    order: int | None = Field(default=None, ge=0, le=10000)
    enabled: bool | None = None
