"""Event Hub settings, read from the project's `.env` (all keys prefixed EVENT_).

The MongoDB URI has no default on purpose: it must come from the environment, never code.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.events.errors import ApiError

EVENTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVENTS_DIR.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    event_mongo_uri: str = Field(validation_alias="EVENT_MONGO_URI")
    event_mongo_db: str = Field("event_data", validation_alias="EVENT_MONGO_DB")

    # Protects /api/admin/*. Empty = admin API disabled.
    admin_api_key: str = Field("", validation_alias="EVENT_ADMIN_API_KEY")
    status_refresh_minutes: int = Field(15, validation_alias="EVENT_STATUS_REFRESH_MINUTES")
    ingest_auto_approve: bool = Field(True, validation_alias="EVENT_INGEST_AUTO_APPROVE")

    ingest_user_agent: str = Field("CasefileEventHub/1.0", validation_alias="EVENT_INGEST_USER_AGENT")
    eventbrite_token: str = Field("", validation_alias="EVENT_EVENTBRITE_TOKEN")
    eventbrite_organization_ids: str = Field("", validation_alias="EVENT_EVENTBRITE_ORGANIZATION_IDS")
    meetup_access_token: str = Field("", validation_alias="EVENT_MEETUP_ACCESS_TOKEN")
    meetup_group_urlnames: str = Field("", validation_alias="EVENT_MEETUP_GROUP_URLNAMES")
    feed_sources_file: str = Field("backend/events/collectors/sources.json", validation_alias="EVENT_FEED_SOURCES_FILE")

    # developers.events data is CC BY-NC (non-commercial). Opt-in records that you accept that.
    developers_events_enabled: bool = Field(False, validation_alias="EVENT_DEVELOPERS_EVENTS_ENABLED")

    # Use the project's existing LLM client (Azure OpenAI primary) for classification.
    ai_enabled: bool = Field(False, validation_alias="EVENT_AI_ENABLED")

    @property
    def feed_sources_path(self) -> Path:
        p = Path(self.feed_sources_file)
        return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        if any(e["type"] == "missing" for e in exc.errors()):
            # 503 for API callers; a readable message for scripts.
            raise ApiError(503, f"Event Hub is not configured: set EVENT_MONGO_URI in {PROJECT_ROOT / '.env'}") from None
        raise
