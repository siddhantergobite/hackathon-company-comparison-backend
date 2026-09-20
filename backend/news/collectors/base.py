"""Collector contract for news sources.

A collector knows how to FETCH items from one kind of source (RSS, an API, ...) and returns flat
raw dicts: title, link, description, published, image, author, tags, source_name. It knows nothing
about MongoDB, categories, dedupe or AI: that is the pipeline's job. New source types are added
by writing a collector and registering it in `registry.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from backend.common.http import CollectorError, PoliteHttpClient  # noqa: F401  (re-exported)


@dataclass
class FetchResult:
    items: list[dict] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class BaseNewsCollector(ABC):
    type: str = ""

    @abstractmethod
    def is_available(self, source: dict) -> tuple[bool, str]:
        """(ok, reason): whether this source can run (credentials/URL present)."""

    @abstractmethod
    def fetch(self, source: dict) -> FetchResult:
        """Fetch the source. Raise CollectorError on failure."""
