"""Small in-process TTL cache for hot read endpoints (latest, trending, categories, ...).

Cleared whenever ingestion or enrichment changes the data, so short TTLs are a safety net rather
than the freshness mechanism. Keys must be hashable; values must not be mutated by callers.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

MAX_ENTRIES = 512


class TTLCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_entries
        self.hits = 0
        self.misses = 0

    def get_or_set(self, key: Any, ttl: float, producer: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > now:
                self._data.move_to_end(key)
                self.hits += 1
                return hit[1]
            self.misses += 1
        value = producer()   # computed outside the lock: two racing misses just compute twice
        with self._lock:
            self._data[key] = (now + ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


cache = TTLCache()
