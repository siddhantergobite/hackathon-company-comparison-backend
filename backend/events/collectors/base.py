"""Collector contract for Event Hub sources.

Collectors know how to FETCH events from one source and yield flat "raw" dicts
(title, description, start, end, url, venue, city, country, ...). They know nothing about
MongoDB or the API: validation, normalisation, dedupe and storage live in `processors/`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from backend.common.http import CollectorError, PoliteHttpClient  # noqa: F401  (re-exported for collectors)


class BaseCollector(ABC):
    name: str = ""            # unique key used on the CLI and in ingestion logs
    label: str = ""           # human name
    description: str = ""
    source_name: str = ""     # stored in event.source.name
    source_url: str | None = None

    @abstractmethod
    def is_configured(self) -> bool:
        """True when everything needed to run (credentials / URLs) is present."""

    @abstractmethod
    def collect(self) -> Iterator[dict]:
        """Yield raw event dicts. May raise CollectorError."""
