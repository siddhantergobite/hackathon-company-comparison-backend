"""Polite HTTP client shared by the Event Hub and News collectors.

Honest User-Agent, per-host rate limit, retries with backoff, optional robots.txt checks,
and conditional GET (a 304 is returned as-is so callers can skip unchanged feeds).
"""
from __future__ import annotations

import logging
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class CollectorError(RuntimeError):
    """A source could not be read (auth failure, blocked by robots.txt, bad payload...)."""


class PoliteHttpClient:
    """requests wrapper: honest User-Agent, per-host rate limit, retries, and robots.txt.

    `api=True` marks calls to an official API (governed by its terms/token, not robots.txt).
    """

    def __init__(self, user_agent: str, min_interval: float = 1.0, timeout: float = 20.0, respect_robots: bool = True):
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._last: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def _throttle(self, host: str) -> None:
        wait = self._last.get(host, 0) + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def allowed_by_robots(self, url: str) -> bool:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                r = self._session.get(f"{root}/robots.txt", timeout=self.timeout)
                if r.status_code >= 500:
                    rp = None  # server trouble: be conservative
                elif r.status_code >= 400:
                    rp.parse([])  # no robots.txt -> everything allowed
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[root] = rp
        rp = self._robots[root]
        return bool(rp and rp.can_fetch(self.user_agent, url))

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None, api: bool = False, retries: int = 3) -> requests.Response:
        if self.respect_robots and not api and not self.allowed_by_robots(url):
            raise CollectorError(f"robots.txt disallows fetching {url}")
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(retries):
            self._throttle(host)
            try:
                r = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2**attempt)
                continue
            if r.status_code in (429, 503):
                delay = float(r.headers.get("Retry-After", 2**attempt)) if str(r.headers.get("Retry-After", "")).replace(".", "").isdigit() else 2**attempt
                time.sleep(min(delay, 30))
                last_exc = CollectorError(f"HTTP {r.status_code} from {host}")
                continue
            if r.status_code in (401, 403):
                raise CollectorError(f"HTTP {r.status_code} from {host}: check credentials/permissions")
            if r.status_code == 304:  # conditional GET: nothing changed
                return r
            r.raise_for_status()
            return r
        raise CollectorError(f"giving up on {url}: {last_exc}")

    def post_json(self, url: str, *, json: dict, headers: dict | None = None) -> requests.Response:
        self._throttle(urlparse(url).netloc)
        try:
            r = self._session.post(url, json=json, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise CollectorError(f"request to {urlparse(url).netloc} failed: {exc.__class__.__name__}") from exc
        if r.status_code in (401, 403):
            raise CollectorError(f"HTTP {r.status_code} from {urlparse(url).netloc}: check credentials/permissions")
        r.raise_for_status()
        return r
