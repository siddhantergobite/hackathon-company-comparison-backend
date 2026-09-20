"""News Intelligence settings, read from the project's `.env`.

MongoDB: uses NEWS_MONGO_URI, or MONGODB_URI, or falls back to the Event Hub's
EVENT_MONGO_URI so both tools can share one server. The URI is never hardcoded.
LLM: reuses Casefile's shared client (Azure OpenAI primary); no separate key is needed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.common.errors import ApiError

NEWS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = NEWS_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    mongo_uri: str = Field(validation_alias=AliasChoices("NEWS_MONGO_URI", "MONGODB_URI", "EVENT_MONGO_URI"))
    mongo_db: str = Field("news_data", validation_alias="NEWS_MONGO_DB")

    # Protects /api/admin/news/*. Falls back to the Event Hub admin key so one password covers both.
    admin_api_key: str = Field("", validation_alias=AliasChoices("NEWS_ADMIN_API_KEY", "EVENT_ADMIN_API_KEY"))

    # Optional commercial news API (newsapi.org): the only lawful route to Reuters / AP headlines.
    news_api_key: str = Field("", validation_alias="NEWS_API_KEY")

    # Background collection
    worker_enabled: bool = Field(True, validation_alias="NEWS_WORKER_ENABLED")
    poll_interval_seconds: int = Field(300, validation_alias="NEWS_POLL_INTERVAL_SECONDS")   # how often the worker wakes
    startup_delay_seconds: int = Field(20, validation_alias="NEWS_STARTUP_DELAY_SECONDS")
    default_poll_minutes: int = Field(15, validation_alias="NEWS_DEFAULT_POLL_MINUTES")      # per-source default
    max_items_per_fetch: int = Field(60, validation_alias="NEWS_MAX_ITEMS_PER_FETCH")
    max_article_age_days: int = Field(7, validation_alias="NEWS_MAX_ARTICLE_AGE_DAYS")       # ignore older items
    retention_days: int = Field(45, validation_alias="NEWS_RETENTION_DAYS")                  # delete older articles
    user_agent: str = Field("CasefileNewsHub/1.0", validation_alias="NEWS_USER_AGENT")

    # AI enrichment (summary, key points, category, topics, entities)
    ai_enabled: bool = Field(True, validation_alias="NEWS_AI_ENABLED")
    ai_max_per_cycle: int = Field(30, validation_alias="NEWS_AI_MAX_PER_CYCLE")
    ai_concurrency: int = Field(3, validation_alias="NEWS_AI_CONCURRENCY")

    # Story clustering / duplicate detection
    cluster_window_hours: int = Field(72, validation_alias="NEWS_CLUSTER_WINDOW_HOURS")

    # Response caching (seconds)
    cache_ttl_short: int = Field(30, validation_alias="NEWS_CACHE_TTL_SHORT")
    cache_ttl_long: int = Field(300, validation_alias="NEWS_CACHE_TTL_LONG")

    default_page_size: int = 20
    max_page_size: int = 50

    @property
    def newsapi_configured(self) -> bool:
        return bool(self.news_api_key)


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        if any(e["type"] == "missing" for e in exc.errors()):
            raise ApiError(503, f"News is not configured: set NEWS_MONGO_URI (or EVENT_MONGO_URI) in {PROJECT_ROOT / '.env'}") from None
        raise
