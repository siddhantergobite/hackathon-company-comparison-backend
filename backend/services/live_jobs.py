"""
Exhibit G — Live AI / software jobs from public LinkedIn, Naukri, and ATS listings.

Does not log into LinkedIn or Naukri, and does not auto-send messages on those
sites. Recency uses listing snippets ("Xm ago") plus first-seen tracking in
this service. It finds recent listings and matches them against uploaded resumes.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from backend.services import brochure_extract
from backend.services import llm as llm_client

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "live_jobs"
BENCH_PATH = DATA_DIR / "bench.json"
SEEN_PATH = DATA_DIR / "seen_jobs.json"

WINDOW_MINUTES_DEFAULT = 30
FALLBACK_MINUTES = 60
URL_DISCOVER_DAYS = 14
URL_DISCOVER_MINUTES = URL_DISCOVER_DAYS * 24 * 60
TPR_PAST_HOUR = "r3600"
TPR_TWO_WEEKS = f"r{URL_DISCOVER_DAYS * 24 * 3600}"
MAX_JOBS = 20
MAX_URL_JOBS = 20
MAX_JOB_DETAIL_FETCH = 8
PAGE_FETCH = 20
HTTP_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MAX_BENCH_RESUMES = 20
GENERIC_SKILLS = {
    "communication", "communication skills", "teamwork", "team player",
    "leadership", "ms office", "microsoft office", "excel", "word",
    "powerpoint", "english", "hardworking", "problem solving",
    "time management", "adaptability", "interpersonal", "ai",
    "artificial intelligence", "software", "software engineering",
    "software development",
}

SKILL_ALIASES = {
    "Python": ("python",),
    "Java": ("java",),
    "JavaScript": ("javascript", "js"),
    "TypeScript": ("typescript", "ts"),
    "C++": ("c++",),
    "C#": ("c#", "c sharp"),
    ".NET": (".net", "dotnet"),
    "Golang": ("go language", "go programming"),
    "Rust": ("rust",),
    "PHP": ("php",),
    "Ruby": ("ruby",),
    "Swift": ("swift",),
    "Kotlin": ("kotlin",),
    "R": ("r programming", "rstudio"),
    "React": ("react", "react.js", "reactjs"),
    "Angular": ("angular",),
    "Vue": ("vue", "vue.js", "vuejs"),
    "Next.js": ("next.js", "nextjs"),
    "Node.js": ("node.js", "nodejs"),
    "Express": ("express.js", "expressjs"),
    "React Native": ("react native",),
    "HTML": ("html",),
    "CSS": ("css",),
    "SQL": ("sql",),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "MongoDB": ("mongodb", "mongo db"),
    "Redis": ("redis",),
    "Snowflake": ("snowflake",),
    "Databricks": ("databricks",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("microsoft azure", "azure"),
    "Google Cloud": ("google cloud", "google cloud platform", "gcp"),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "Terraform": ("terraform",),
    "Linux": ("linux",),
    "Git": ("git",),
    "REST API": ("rest api", "restful api", "restful services"),
    "GraphQL": ("graphql",),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Flask": ("flask",),
    "Spring Boot": ("spring boot",),
    "Machine learning": ("machine learning", "machine-learning", "ml"),
    "Deep learning": ("deep learning",),
    "NLP": ("natural language processing", "nlp"),
    "Computer vision": ("computer vision",),
    "Generative AI": ("generative ai", "genai", "generative artificial intelligence"),
    "LLMs": ("large language model", "large language models", "llm", "llms"),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "scikit-learn": ("scikit-learn", "scikit learn"),
    "LangChain": ("langchain",),
    "Pandas": ("pandas",),
    "Apache Spark": ("apache spark", "pyspark"),
    "Kafka": ("kafka",),
    "Airflow": ("airflow", "apache airflow"),
    "MLOps": ("mlops",),
    "CI/CD": ("ci/cd", "continuous integration", "continuous delivery"),
    "Jenkins": ("jenkins",),
    "Microservices": ("microservices", "micro services"),
    "Power BI": ("power bi",),
    "Tableau": ("tableau",),
}

AI_TERMS = (
    "ai ", " ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "generative ai", "genai", "nlp", "computer vision", "data scientist",
    "ml engineer", "mlops", "prompt engineer", "applied scientist",
)
SOFTWARE_TERMS = (
    "software engineer", "software developer", "backend", "frontend",
    "full stack", "fullstack", "sde", "python developer", "java developer",
    "react", "node.js", "golang", "devops", "platform engineer",
    "mobile developer", "android", "ios engineer",
)

JOB_URL_OK = re.compile(
    r"(linkedin\.com/jobs/view/|naukri\.com/job-listings|"
    r"(?:boards|job-boards)\.greenhouse\.io/[^/]+/jobs/\d+)",
    re.I,
)
JOB_URL_SKIP = re.compile(
    r"(login|signup|checkpoint|authwall|jobs/search/?$|/jobs/?$)",
    re.I,
)
MINUTES_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:minutes?|mins?|m)\s*ago",
    re.I,
)
HOURS_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:hours?|hrs?|h)\s*ago",
    re.I,
)
DAYS_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:days?|d)\s*ago",
    re.I,
)
WEEKS_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:weeks?|w)\s*ago",
    re.I,
)
MONTHS_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:months?|mos?)\s*ago",
    re.I,
)
YEARS_RE = re.compile(
    r"(?:posted\s+)?(\d+)\s*(?:years?|yrs?)\s*ago",
    re.I,
)
JUST_NOW_RE = re.compile(r"\b(just now|moments ago|few seconds ago|posted now)\b", re.I)
AN_HOUR_RE = re.compile(r"\b(?:an|1)\s+hours?\s+ago\b", re.I)
AN_WEEK_RE = re.compile(r"\b(?:a|1)\s+weeks?\s+ago\b", re.I)
YESTERDAY_RE = re.compile(r"\byesterday\b", re.I)
LINKEDIN_COMPANY_URN_RE = re.compile(
    r"urn:li:(?:fsd_company|fs_normalized_company|company|organization):(\d{3,})",
    re.I,
)
LINKEDIN_F_C_RE = re.compile(r"(?:[?&]f_C=|currentCompany=|companyIds?=)(\d{3,})")
SKIP_WEB_HOSTS = {
    "google.com", "www.google.com", "bing.com", "yahoo.com", "facebook.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com", "wikipedia.org",
    "github.com", "linkedin.com", "www.linkedin.com",
}
JUNK_LISTING_RE = re.compile(
    r"64% of job seekers|boost your chances of getting hired|use linkedin jobs to|"
    r"see who you know|sign in to view|job seeker guidance",
    re.I,
)
LISTED_AT_RE = re.compile(r'"listedAt"\s*:\s*"?(\d{10,13})"?')
DATE_POSTED_RE = re.compile(
    r'"(?:datePosted|datePublished|postedDate|postedOn|createdAt)"\s*:\s*"([^"]+)"',
    re.I,
)

COMPANY_FROM_TITLE = re.compile(
    r"^(?P<title>.+?)\s+(?:[-–|]|at|@)\s+(?P<company>.+)$",
    re.I,
)


def _now() -> float:
    return time.time()


def _iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or _now(), tz=timezone.utc).isoformat()


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[LiveJobs] read {path.name} failed: {e}")
    return default


def _save_json(path: Path, payload: Any) -> None:
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _slots_from_people(people: dict) -> list[dict]:
    slots = []
    for sid, p in (people or {}).items():
        if not isinstance(p, dict):
            continue
        slots.append({
            "id": sid,
            "track": p.get("track") or p.get("strongest_fit") or "both",
            "label": p.get("label") or p.get("name") or p.get("title") or sid,
        })
    return slots


def _loaded_people(bench: dict) -> list[dict]:
    return [
        p for p in (bench.get("people") or {}).values()
        if isinstance(p, dict) and p.get("loaded")
    ]


def get_bench() -> dict:
    data = _load_json(BENCH_PATH, None)
    people: dict[str, dict] = {}
    updated = ""
    if isinstance(data, dict):
        updated = data.get("updated_at") or ""
        raw = data.get("people") or {}
        if isinstance(raw, dict):
            for sid, row in raw.items():
                if not isinstance(row, dict):
                    continue
                loaded = bool(
                    row.get("loaded")
                    or row.get("filename")
                    or row.get("name")
                    or row.get("summary")
                )
                if not loaded:
                    continue
                people[str(sid)] = {**row, "slot": str(sid), "loaded": True}
    return {
        "people": people,
        "updated_at": updated,
        "slots": _slots_from_people(people),
    }


def _ddg(query: str, max_results: int = 10, timelimit: Optional[str] = "d") -> list[dict]:
    rows: list[dict] = []
    kwargs = {"max_results": max_results}
    if timelimit:
        kwargs["timelimit"] = timelimit
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            try:
                rows = list(ddgs.text(query, **kwargs))
            except TypeError:
                rows = list(ddgs.text(query, max_results=max_results))
    except Exception as e1:
        print(f"[LiveJobs] ddgs '{query}': {e1}")
        try:
            from duckduckgo_search import DDGS as LegacyDDGS
            with LegacyDDGS() as ddgs:
                try:
                    rows = list(ddgs.text(query, **kwargs))
                except TypeError:
                    rows = list(ddgs.text(query, max_results=max_results))
        except Exception as e2:
            print(f"[LiveJobs] legacy DDG '{query}': {e2}")
            return []
    out = []
    for r in rows or []:
        url = (r.get("href") or r.get("link") or r.get("url") or "").strip()
        if not url:
            continue
        out.append({
            "title": (r.get("title") or "").strip(),
            "url": url,
            "snippet": (r.get("body") or r.get("snippet") or "").strip(),
        })
    return out


def _platform(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "linkedin.com" in host:
        return "LinkedIn"
    if "naukri.com" in host:
        return "Naukri"
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        return "Greenhouse"
    return ""


def _is_job_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    if JOB_URL_SKIP.search(url):
        return False
    return bool(JOB_URL_OK.search(url))


def _greenhouse_board_token(url: str) -> str:
    """Extract a Greenhouse public board token, not an arbitrary URL path."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().split(":", 1)[0]
    if host not in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        return ""
    parts = [part for part in (parsed.path or "").split("/") if part]
    if not parts:
        return ""
    # Both /{board} and /{board}/jobs/{id} are valid public board URLs.
    return parts[0] if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", parts[0]) else ""


def _greenhouse_request(url: str) -> Optional[dict]:
    try:
        response = requests.get(
            url,
            headers={**_headers(), "Accept": "application/json"},
            timeout=HTTP_TIMEOUT,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (requests.RequestException, ValueError) as exc:
        print(f"[LiveJobs] Greenhouse request failed: {exc}")
        return None


def _greenhouse_board_jobs(board_url: str) -> list[dict]:
    """Read published jobs from a supplied Greenhouse board and verify first_published."""
    token = _greenhouse_board_token(board_url)
    if not token:
        return []
    api_root = f"https://boards-api.greenhouse.io/v1/boards/{token}"
    listing = _greenhouse_request(f"{api_root}/jobs?content=true") or {}
    jobs = listing.get("jobs") or []
    if not isinstance(jobs, list):
        return []

    # The list API's updated_at is not the original posting date. Resolve each
    # detail record and use only its documented first_published value.
    candidates = [item for item in jobs[:40] if isinstance(item, dict) and item.get("id")]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_greenhouse_request, f"{api_root}/jobs/{item['id']}?content=true"): item
            for item in candidates
        }
        details = [(item, future.result() or {}) for future, item in futures.items()]
    for item, detail in details:
        published = detail.get("first_published")
        age = _iso_to_age_minutes(str(published or ""))
        if age is None:
            continue
        title = str(detail.get("title") or item.get("title") or "").strip()
        if not title:
            continue
        location_obj = detail.get("location") or item.get("location") or {}
        location = location_obj.get("name", "") if isinstance(location_obj, dict) else str(location_obj)
        description_html = str(detail.get("content") or item.get("content") or "")
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        company = str(detail.get("company_name") or "").strip()
        url = str(detail.get("absolute_url") or item.get("absolute_url") or "").strip()
        if not url or _platform(url) != "Greenhouse":
            # Some employers provide a custom absolute_url; retain the known
            # Greenhouse job URL so the source remains directly verifiable.
            url = f"https://boards.greenhouse.io/{token}/jobs/{item['id']}"
        rows.append({
            "title": title,
            "company": company,
            "url": url,
            "platform": "Greenhouse",
            "snippet": location,
            "description": description[:8000],
            "posted_minutes": age,
            "source": "greenhouse_public_board_api",
        })
    return rows


def _normalize_http_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw.lstrip("/")
    return raw


def _registrable_host(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _company_name_matches(card_company: str, target: str) -> bool:
    a = _norm_name(card_company)
    b = _norm_name(target)
    if not a or not b or len(b) < 3:
        return False
    if a == b or a.startswith(b) or b.startswith(a) or b in a or a in b:
        return True
    atoks = [t for t in a.split() if len(t) > 2]
    btoks = [t for t in b.split() if len(t) > 2]
    return bool(atoks and btoks and atoks[0] == btoks[0])


def _unix_to_age_minutes(raw: int, now: Optional[float] = None) -> Optional[int]:
    if raw > 10_000_000_000:
        raw = raw / 1000.0
    if raw < 1_000_000_000:
        return None
    age = int(((now or _now()) - raw) / 60)
    return max(0, age)


def _iso_to_age_minutes(value: str, now: Optional[float] = None) -> Optional[int]:
    raw = (value or "").strip()
    if not raw or len(raw) < 8:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                dt = datetime.strptime(raw[:10], "%Y-%m-%d")
                dt = dt.replace(tzinfo=timezone.utc)
                # Date-only is not precise enough for a 30-minute window.
                age = int(((now or _now()) - dt.timestamp()) / 60)
                return max(age, 24 * 60) if age >= 0 else None
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = int(((now or _now()) - dt.timestamp()) / 60)
    return max(0, age)


def extract_age_minutes(blob: str, now: Optional[float] = None) -> Optional[int]:
    """Return listing age in minutes when it can be parsed. Includes stale ages."""
    text = blob or ""
    if not text:
        return None
    ages = []
    for n in LISTED_AT_RE.findall(text):
        age = _unix_to_age_minutes(int(n), now)
        if age is not None:
            ages.append(age)
    for val in DATE_POSTED_RE.findall(text):
        age = _iso_to_age_minutes(val, now)
        if age is not None:
            ages.append(age)
    if ages:
        return min(ages)
    if JUST_NOW_RE.search(text):
        return 0
    if AN_HOUR_RE.search(text):
        return 60
    if YESTERDAY_RE.search(text):
        return 24 * 60
    if AN_WEEK_RE.search(text):
        return 7 * 24 * 60
    m = MINUTES_RE.search(text)
    if m:
        return max(0, int(m.group(1)))
    h = HOURS_RE.search(text)
    if h:
        return max(0, int(h.group(1))) * 60
    d = DAYS_RE.search(text)
    if d:
        return max(0, int(d.group(1))) * 24 * 60
    w = WEEKS_RE.search(text)
    if w:
        return max(0, int(w.group(1))) * 7 * 24 * 60
    mo = MONTHS_RE.search(text)
    if mo:
        return max(0, int(mo.group(1))) * 30 * 24 * 60
    y = YEARS_RE.search(text)
    if y:
        return max(0, int(y.group(1))) * 365 * 24 * 60
    return None


def parse_posted_minutes(text: str) -> Optional[int]:
    return extract_age_minutes(text)


def in_posted_window(age_minutes: Optional[int], window: int) -> bool:
    return age_minutes is not None and 0 <= age_minutes <= window


def _is_junk_listing(title: str, snippet: str) -> bool:
    blob = f"{title} {snippet}"
    return bool(JUNK_LISTING_RE.search(blob))


def _role_track(text: str) -> Optional[str]:
    t = f" {re.sub(r'[^a-z0-9+.# ]', ' ', (text or '').lower())} "
    ai = any(term in t for term in AI_TERMS)
    sw = any(term in t for term in SOFTWARE_TERMS)
    if ai and sw:
        return "both"
    if ai:
        return "ai"
    if sw:
        return "software"
    return None


def _split_title(title: str) -> tuple[str, str]:
    raw = re.sub(r"\s+", " ", title or "").strip()
    raw = re.sub(r"\s*[|·•].*$", "", raw).strip()
    m = COMPANY_FROM_TITLE.match(raw)
    if m:
        return m.group("title").strip()[:140], m.group("company").strip()[:120]
    return raw[:140], ""


def _job_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode("utf-8")).hexdigest()[:20]


def _load_seen() -> dict:
    data = _load_json(SEEN_PATH, {})
    return data if isinstance(data, dict) else {}


def _prune_seen(seen: dict, keep_hours: int = 24) -> dict:
    cutoff = _now() - keep_hours * 3600
    out = {}
    for k, v in seen.items():
        if not isinstance(v, dict):
            continue
        try:
            first = float(v.get("first_seen") or 0)
        except (TypeError, ValueError):
            continue
        if first >= cutoff:
            out[k] = v
    return out


DEFAULT_SEARCH_QUERIES = (
    "software engineer",
    "machine learning engineer",
    "AI engineer",
    "python developer",
    "full stack developer",
    "data scientist",
    "backend engineer",
    "generative AI",
)


def _queries(sources: list[str], terms: Optional[list[str]] = None) -> list[str]:
    q = []
    if "naukri" not in sources:
        return q
    for t in (terms or [])[:8]:
        safe = re.sub(r'["\']', " ", str(t)).strip()
        if len(safe) < 3:
            continue
        # Keep title and skills as separate searchable terms; exact-quoting a
        # whole phrase such as "backend engineer Spring Boot Java" is too narrow.
        q.append(f"site:naukri.com/job-listings {safe}")
    return q


def _heuristic_search_queries(people: list[dict]) -> list[str]:
    """Build role + real resume-skill queries, fairly across the talent bench."""
    query_sets: list[list[str]] = []
    preferred_skills = {
        "mobile": ("kotlin", "android sdk", "jetpack compose", "flutter", "swift"),
        "fullstack": ("react", "node.js", "typescript", "next.js", "postgresql"),
        "backend": ("spring boot", "java", "python", "kafka", "postgresql"),
        "frontend": ("react", "typescript", "next.js", "javascript", "tailwind css"),
        "computer_vision": ("opencv", "pytorch", "computer vision", "tensorflow"),
        "ai": ("pytorch", "scikit-learn", "lightgbm", "mlops", "tensorflow"),
        "software": ("python", "java", "go", "javascript", "typescript"),
    }

    for person in people:
        title = re.sub(r"\s+", " ", str(person.get("title") or "").strip())
        raw_skills = person.get("skills") or []
        if isinstance(raw_skills, str):
            raw_skills = re.split(r"[,;|]", raw_skills)
        skills = [str(skill).strip() for skill in raw_skills if str(skill).strip()]
        skill_text = " ".join(skills).lower()
        profile_text = f"{title} {skill_text}".lower()

        if any(term in profile_text for term in ("computer vision", "opencv")):
            family, role = "computer_vision", "computer vision engineer"
        elif any(term in profile_text for term in ("mobile", "android", "ios", "kotlin", "flutter")):
            family, role = "mobile", "android developer" if "android" in profile_text else "mobile developer"
        elif any(term in profile_text for term in ("full stack", "full-stack", "fullstack")):
            family, role = "fullstack", "full stack developer"
        elif any(term in profile_text for term in ("front end", "frontend", "front-end")):
            family, role = "frontend", "frontend developer"
        elif any(term in profile_text for term in ("back end", "backend", "back-end")):
            family, role = "backend", "backend engineer"
        elif any(term in profile_text for term in ("machine learning", "ml engineer", "data scientist")):
            family, role = "ai", "machine learning engineer"
        elif any(term in profile_text for term in ("ai engineer", "artificial intelligence")):
            family, role = "ai", "AI engineer"
        else:
            family, role = "software", title or "software engineer"

        # Choose only technologies actually extracted from this resume. The
        # ordered preferences make each search concise and role-specific.
        normalized = {skill.lower(): skill for skill in skills}
        chosen = [normalized[key] for key in preferred_skills[family] if key in normalized]
        if not chosen:
            chosen = [skill for skill in skills if skill.lower() not in GENERIC_SKILLS][:2]
        variants = []
        if chosen:
            variants.append(" ".join([role, *chosen[:2]])[:100])
            if len(chosen) > 2:
                variants.append(" ".join([role, chosen[2]])[:100])
        else:
            variants.append(role[:100])
        query_sets.append(variants)

    # Round-robin means an 8-query search reaches 8 different resumes before
    # spending a second query on any one candidate.
    queries: list[str] = []
    seen: set[str] = set()
    max_depth = max((len(items) for items in query_sets), default=0)
    for depth in range(max_depth):
        for items in query_sets:
            if depth >= len(items):
                continue
            query = items[depth]
            key = query.lower()
            if query and key not in seen:
                seen.add(key)
                queries.append(query)
                if len(queries) >= 8:
                    return queries
    return queries


def search_queries_for_scan(bench: dict) -> list[str]:
    people = _loaded_people(bench)
    if not people:
        return []
    return _heuristic_search_queries(people)

NAUKRI_BLOCKED_NOTE = (
    "Naukri results currently come from public web-search discovery, not an authorized Naukri job-search API; "
    "coverage may be limited and undated listings are excluded."
)


def _clean_job_url(url: str) -> str:
    return (url or "").split("?")[0].split("#")[0].strip()


def _headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _age_from_linkedin_time(el) -> Optional[int]:
    if el is None:
        return None
    relative = extract_age_minutes(el.get_text(" ", strip=True) or "")
    if relative is not None:
        return relative
    dt = (el.get("datetime") or "").strip()
    if dt:
        return _iso_to_age_minutes(dt)
    return None


def _linkedin_guest_search(
    keyword: str = "",
    start: int = 0,
    tpr: str = TPR_PAST_HOUR,
    company_id: Optional[str] = None,
) -> list[dict]:
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params: dict[str, Any] = {"f_TPR": tpr or TPR_PAST_HOUR, "start": int(start or 0)}
    kw = (keyword or "").strip()
    if kw:
        params["keywords"] = kw
    if company_id:
        params["f_C"] = str(company_id)
    if not kw and not company_id:
        return []
    label = kw or f"f_C={company_id}"
    try:
        r = requests.get(
            url,
            params=params,
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code >= 400 or not (r.text or "").strip():
            print(f"[LiveJobs] LinkedIn guest {label!r} start={start} status={r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("div.base-card, div.job-search-card")
        out = []
        for card in cards:
            a = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
            href = _clean_job_url(a.get("href") if a else "")
            if not href or "/jobs/view/" not in href:
                continue
            title_el = card.select_one("h3.base-search-card__title") or card.select_one("h3")
            co_el = card.select_one("h4.base-search-card__subtitle") or card.select_one(".base-search-card__subtitle")
            loc_el = card.select_one(".job-search-card__location")
            snippet_el = (
                card.select_one(".job-search-card__snippet")
                or card.select_one(".base-search-card__snippet")
            )
            time_el = card.select_one("time")
            title = (title_el.get_text(" ", strip=True) if title_el else "").strip()
            company = (co_el.get_text(" ", strip=True) if co_el else "").strip()
            loc = (loc_el.get_text(" ", strip=True) if loc_el else "").strip()
            description = (snippet_el.get_text(" ", strip=True) if snippet_el else "").strip()
            age = _age_from_linkedin_time(time_el)
            rel = (time_el.get_text(" ", strip=True) if time_el else "").strip()
            if age is None and rel:
                age = extract_age_minutes(rel)
            track = _role_track(f"{title} {description} {kw}") or (
                "ai" if any(x in kw.lower() for x in ("ai", "machine", "data scientist", "generative")) else "software"
            )
            out.append({
                "title": title or kw or "Job listing",
                "company": company,
                "url": href,
                "platform": "LinkedIn",
                "track": track,
                "snippet": " · ".join(p for p in (description, loc, rel) if p)[:400]
                or " · ".join(p for p in (company, loc, rel) if p)[:400],
                "description": description[:400],
                "posted_minutes": age,
                "source": "linkedin_guest",
            })
        print(f"[LiveJobs] LinkedIn guest {label!r} start={start} tpr={params['f_TPR']} cards={len(out)}")
        return out
    except Exception as e:
        print(f"[LiveJobs] LinkedIn guest {label!r}: {e}")
        return []


def _collect_linkedin_live(keywords: Optional[list[str]] = None) -> list[dict]:
    jobs: list[dict] = []
    kws = [str(k).strip() for k in (keywords or []) if str(k).strip()][:8]
    if not kws:
        return jobs
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(_linkedin_guest_search, kw, 0) for kw in kws]
        if len(kws) <= 4:
            futs.extend(pool.submit(_linkedin_guest_search, kw, 10) for kw in kws)
        for fut in as_completed(futs):
            try:
                jobs.extend(fut.result() or [])
            except Exception as e:
                print(f"[LiveJobs] LinkedIn collect: {e}")
    return jobs


def _fetch_job_page(url: str) -> dict:
    empty = {"html": "", "text": "", "description": ""}
    try:
        r = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code >= 400:
            return empty
        html = r.text or ""
        if len(html) < 80:
            return empty
        low = html.lower()
        if "authwall" in low or "captcha" in low:
            return empty
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "html": html[:120000],
            "text": text[:8000],
            "description": _job_description_from_html(html[:120000])[:8000],
        }
    except Exception as e:
        print(f"[LiveJobs] fetch {url}: {e}")
        return empty


def _job_description_from_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []
    selectors = (
        ".show-more-less-html__markup",
        ".description__text",
        ".jobs-description__content",
        '[data-test-id="job-description"]',
    )
    for selector in selectors:
        for node in soup.select(selector):
            value = node.get_text(" ", strip=True)
            if len(value) >= 40:
                candidates.append(value)

    def collect_job_postings(value):
        if isinstance(value, list):
            for item in value:
                collect_job_postings(item)
            return
        if not isinstance(value, dict):
            return
        raw_type = value.get("@type") or []
        types = [raw_type] if isinstance(raw_type, str) else raw_type
        is_job_posting = any(str(item).lower() == "jobposting" for item in types)
        description = value.get("description")
        if is_job_posting and isinstance(description, str):
            cleaned = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
            if len(cleaned) >= 40:
                candidates.append(cleaned)
        for child in value.values():
            if isinstance(child, (dict, list)):
                collect_job_postings(child)

    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            collect_job_postings(json.loads(script.string or script.get_text()))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    return max(candidates, key=len, default="")[:8000]


def _fetch_job_text(url: str) -> str:
    return _fetch_job_page(url).get("text") or ""


def _enrich_linkedin_descriptions(jobs: list[dict]) -> None:
    targets = [
        job for job in jobs
        if job.get("platform") == "LinkedIn" and not job.get("description_source")
    ][:MAX_JOB_DETAIL_FETCH]
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        futures = {pool.submit(_fetch_job_page, job.get("url") or ""): job for job in targets}
        for future in as_completed(futures):
            job = futures[future]
            try:
                page = future.result() or {}
            except Exception as e:
                print(f"[LiveJobs] job detail fetch failed: {e}")
                continue
            description = (page.get("description") or "").strip()
            if len(description) >= 40:
                job["description"] = description
                job["description_source"] = "public_job_page"


def _emails_from(text: str) -> list[str]:
    found = re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", text or "", re.I)
    skip = ("example.com", "sentry.io", "wixpress", "cloudflare", "schema.org")
    out = []
    for e in found:
        el = e.lower()
        if any(s in el for s in skip):
            continue
        if el not in out:
            out.append(el)
        if len(out) >= 3:
            break
    return out


def _canonical_skill(value: str) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if normalized == "go":
        return "Golang"
    if normalized == "spark":
        return "Apache Spark"
    for name, aliases in SKILL_ALIASES.items():
        if normalized == name.lower() or normalized in aliases:
            return name
    return str(value or "").strip()


def _skill_is_mentioned(text: str, skill: str, aliases: tuple[str, ...]) -> bool:
    candidates = (skill, *aliases)
    for candidate in candidates:
        candidate = str(candidate or "").strip().lower()
        if not candidate or len(candidate) == 1:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(candidate)}(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def _person_skills(person: dict) -> set[str]:
    raw_skills = person.get("skills") or []
    if isinstance(raw_skills, str):
        raw_skills = re.split(r"[,;|]", raw_skills)
    skills = set()
    for raw in raw_skills:
        skill = str(raw or "").strip()
        if not skill or skill.lower() in GENERIC_SKILLS:
            continue
        normalized = skill.lower()
        recognized = {
            name for name, aliases in SKILL_ALIASES.items()
            if _skill_is_mentioned(normalized, name, aliases)
        }
        if recognized:
            skills.update(recognized)
        else:
            skills.add(_canonical_skill(skill))
    return skills


def _candidate_ref(person: dict, basis: str = "skills") -> dict:
    return {
        "slot": person.get("slot"),
        "name": person.get("name") or person.get("label") or person.get("title") or person.get("slot"),
        "title": person.get("title") or "",
        "track": person.get("track") or person.get("strongest_fit") or "",
        "basis": basis,
    }


def _role_alignment(job: dict, person: dict) -> int:
    job_track = job.get("track") or _role_track(str(job.get("title") or ""))
    person_track = str(person.get("track") or person.get("strongest_fit") or "").lower()
    if person_track not in ("ai", "software", "both"):
        person_track = _role_track(
            " ".join(str(person.get(key) or "") for key in ("title", "summary"))
        ) or ""
    if not job_track or not person_track:
        return 0
    if job_track == person_track:
        return 2
    if person_track == "both" or job_track == "both":
        return 1
    return 0


def _match_evidence(job: dict, bench: dict) -> dict:
    people = [
        person for person in (bench.get("people") or {}).values()
        if isinstance(person, dict) and person.get("loaded")
    ]
    if not people:
        return {
            "fit_level": "needs_resume",
            "candidate": None,
            "listing_skills": [],
            "matched_skills": [],
            "missing_skills": [],
            "reason": "Upload a resume to compare its skills with this listing.",
        }

    job_text = " ".join(str(job.get(key) or "") for key in ("title", "snippet", "description")).lower()
    catalog = {name: aliases for name, aliases in SKILL_ALIASES.items()}
    for person in people:
        raw_skills = person.get("skills") or []
        if isinstance(raw_skills, str):
            raw_skills = re.split(r"[,;|]", raw_skills)
        for raw in raw_skills:
            skill = str(raw or "").strip()
            if skill and skill.lower() not in GENERIC_SKILLS:
                catalog.setdefault(_canonical_skill(skill), (skill,))

    listing_skills = [
        name for name, aliases in catalog.items()
        if _skill_is_mentioned(job_text, name, aliases)
    ]
    if not listing_skills:
        job_track = job.get("track") or _role_track(str(job.get("title") or ""))
        role_candidates = [
            person for person in people if _role_alignment(job, person) > 0
        ]
        closest = max(
            role_candidates,
            key=lambda person: (_role_alignment(job, person), str(person.get("name") or person.get("label") or "")),
            default=None,
        )
        return {
            "fit_level": "no_strong_match",
            "candidate": _candidate_ref(closest, "role_only") if closest else None,
            "listing_skills": [],
            "matched_skills": [],
            "missing_skills": [],
            "reason": (
                f"The listing lacks enough skill detail to confirm a fit. "
                f"{closest.get('name') or closest.get('label') or closest.get('title') or 'No resume'} is the closest resume by role category only; "
                "open the post and review the full requirements."
                if closest and job_track else
                "The listing lacks enough recognizable skill detail to assess fit. Open the post and review the full requirements."
            ),
        }

    ranked = []
    for person in people:
        resume_skills = _person_skills(person)
        matched = [skill for skill in listing_skills if skill in resume_skills]
        coverage = len(matched) / len(listing_skills)
        ranked.append((coverage, len(matched), person, matched, resume_skills))
    coverage, _count, person, matched, resume_skills = max(
        ranked, key=lambda row: (row[0], row[1], _role_alignment(job, row[2]))
    )
    missing = [skill for skill in listing_skills if skill not in resume_skills] if matched else []

    if not matched:
        fit_level = "no_strong_match"
        reason = "None of the uploaded resumes lists a skill detected in this job listing."
    elif len(listing_skills) >= 3 and coverage >= 0.70:
        fit_level = "strong"
        reason = f"The resume includes {len(matched)} of {len(listing_skills)} skills found in the listing."
    elif matched and coverage >= 0.40:
        fit_level = "possible"
        reason = f"The resume includes {len(matched)} of {len(listing_skills)} skills found in the listing; review the full requirements."
    else:
        fit_level = "no_strong_match"
        reason = (
            f"The resume includes {len(matched)} of {len(listing_skills)} skills found in the listing; "
            "there is not enough overlap to call this a strong match."
        )

    candidate = _candidate_ref(person)
    return {
        "fit_level": fit_level,
        "candidate": candidate,
        "listing_skills": listing_skills,
        "matched_skills": matched,
        "missing_skills": missing,
        "reason": reason,
    }


def scan(
    minutes: int = WINDOW_MINUTES_DEFAULT,
    sources: Optional[list[str]] = None,
    include_unverified_recent: bool = False,
) -> dict:
    minutes = max(5, min(int(minutes or WINDOW_MINUTES_DEFAULT), 180))
    src = [s.lower().strip() for s in (sources or ["linkedin", "naukri"]) if s]
    src = [s for s in src if s in ("linkedin", "naukri")] or ["linkedin", "naukri"]
    bench = get_bench()
    resume_terms = search_queries_for_scan(bench)
    from_resumes = bool(resume_terms)
    search_terms = resume_terms or list(DEFAULT_SEARCH_QUERIES)

    queries = _queries(src, search_terms)
    hits: list[dict] = []
    errors: list[str] = []
    now = _now()
    jobs_map: dict[str, dict] = {}
    dropped = {"junk": 0, "not_role": 0, "stale_or_unknown": 0}

    if "linkedin" in src:
        for row in _collect_linkedin_live(search_terms):
            url = _clean_job_url(row.get("url") or "")
            if not url:
                continue
            title = row.get("title") or ""
            snippet = row.get("snippet") or ""
            if _is_junk_listing(title, snippet):
                dropped["junk"] += 1
                continue
            jid = _job_id(url)
            jobs_map[jid] = {
                "id": jid,
                "title": title[:140],
                "company": row.get("company") or "",
                "url": url,
                "platform": "LinkedIn",
                "track": row.get("track") or "software",
                "snippet": snippet[:400],
                "posted_minutes": row.get("posted_minutes"),
                "first_seen_minutes": 0,
                "recency": "pending_verify",
                "emails": [],
                "description": row.get("description") or snippet,
                "source": "linkedin_guest",
            }

    if "naukri" in src:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_ddg, q, 12, "d"): q for q in queries}
            for fut in as_completed(futs):
                q = futs[fut]
                try:
                    hits.extend(fut.result() or [])
                except Exception as e:
                    errors.append(f"{q}: {e}")
        for h in hits:
            url = _clean_job_url(h.get("url") or "")
            if not _is_job_url(url) or _platform(url) != "Naukri":
                continue
            title_raw = h.get("title") or ""
            snippet = h.get("snippet") or ""
            if _is_junk_listing(title_raw, snippet):
                dropped["junk"] += 1
                continue
            role, company = _split_title(title_raw)
            track = _role_track(f"{role} {title_raw} {snippet}") or "software"
            jid = _job_id(url)
            if jid in jobs_map:
                continue
            jobs_map[jid] = {
                "id": jid,
                "title": (role or title_raw)[:140],
                "company": company,
                "url": url,
                "platform": "Naukri",
                "track": track,
                "snippet": snippet[:400],
                "posted_minutes": extract_age_minutes(f"{title_raw} {snippet}", now),
                "first_seen_minutes": 0,
                "recency": "pending_verify",
                "emails": [],
                "description": "",
            }

    candidates = list(jobs_map.values())
    naukri_need_fetch = [j for j in candidates if j["platform"] == "Naukri"][:12]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(_fetch_job_page, j["url"]): j for j in naukri_need_fetch}
        for fut in as_completed(futs):
            job = futs[fut]
            page = fut.result() or {}
            html = page.get("html") or ""
            text = page.get("text") or ""
            description = (page.get("description") or text).strip()
            if description:
                job["description"] = description[:8000]
                job["description_source"] = (
                    "public_job_page" if page.get("description") else "fetched_page_text"
                )
                job["emails"] = _emails_from(text)
            age = extract_age_minutes(f"{html} {text} {job.get('snippet','')} {job.get('title','')}", now)
            if age is not None:
                job["posted_minutes"] = age

    print(f"[LiveJobs] candidates={len(candidates)} linkedin={sum(1 for j in candidates if j['platform']=='LinkedIn')}")

    fallback = FALLBACK_MINUTES
    jobs_primary = []
    jobs_fallback = []
    for job in candidates:
        age = job.get("posted_minutes")
        if age is None and job.get("platform") == "LinkedIn":
            # LinkedIn guest search is already f_TPR=r3600 (past hour).
            age = fallback
            job["posted_minutes"] = age
        if in_posted_window(age, minutes):
            job["recency"] = "posted_in_window"
            jobs_primary.append(job)
        elif in_posted_window(age, fallback):
            job["recency"] = "posted_in_fallback"
            jobs_fallback.append(job)
        else:
            dropped["stale_or_unknown"] += 1

    jobs_primary.sort(key=lambda j: j["posted_minutes"] if j["posted_minutes"] is not None else 9999)
    jobs_fallback.sort(key=lambda j: j["posted_minutes"] if j["posted_minutes"] is not None else 9999)

    jobs = jobs_primary[:]
    fallback_used = False
    if len(jobs) < 12:
        seen_ids = {j["id"] for j in jobs}
        extra = [j for j in jobs_fallback if j["id"] not in seen_ids]
        take = extra[: max(0, 20 - len(jobs))]
        if take:
            jobs.extend(take)
            fallback_used = True
    applied = minutes if jobs_primary and not fallback_used else (fallback if jobs else minutes)
    if jobs_primary and fallback_used:
        applied = fallback
    jobs = jobs[:MAX_JOBS]

    _enrich_linkedin_descriptions(jobs)

    for job in jobs:
        evidence = _match_evidence(job, bench)
        job["match_evidence"] = evidence
        job["matched_talent"] = evidence["candidate"]

    qnote = " Searched: " + ", ".join(search_terms[:8]) + "."
    if from_resumes:
        qnote += " Queries came from uploaded resume skills."
    else:
        qnote += " No resumes on the bench, so this used the default live AI/software search. Upload resumes to search by their skills."
    if fallback_used and jobs_primary:
        note = (
            f"Showing the freshest proven posts (last {minutes} min first), filled from the last "
            f"{fallback} minutes. Older than 1 hour is hidden."
        )
    elif fallback_used:
        note = (
            f"No listings proven within {minutes} minutes, so results are the last {fallback} minutes. "
            "Days/weeks/months-old JDs stay hidden."
        )
    elif jobs:
        note = f"Showing jobs proven posted in the last {minutes} minutes (freshest first)."
    else:
        note = (
            f"No matching jobs could be proven within {minutes} minutes or the {fallback}-minute fallback."
        )
    note = f"{note}{qnote} {NAUKRI_BLOCKED_NOTE}"
    return {
        "window_minutes": applied,
        "window_requested": minutes,
        "window_fallback": fallback,
        "fallback_used": fallback_used,
        "scanned_at": _iso(now),
        "sources": src,
        "job_count": len(jobs),
        "in_window_count": len(jobs),
        "dropped": dropped,
        "bench_loaded": sum(1 for p in (bench.get("people") or {}).values() if p.get("loaded")),
        "search_queries": search_terms,
        "jobs": jobs,
        "errors": errors,
        "_meta": {
            "note": note,
            "auto_send": False,
        },
    }


def _attach_talent(job: dict, bench: Optional[dict] = None) -> dict:
    bench = bench or get_bench()
    evidence = _match_evidence(job, bench)
    job["match_evidence"] = evidence
    job["matched_talent"] = evidence["candidate"]
    return job


def _linkedin_slug(url: str) -> str:
    path = (urlparse(url).path or "").strip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[0].lower() == "company":
        slug = parts[1].strip()
        if slug.lower() not in ("", "home", "about", "jobs", "life", "people", "posts"):
            return slug
    return ""


def _slug_to_company_name(slug: str) -> str:
    return re.sub(r"[-_]+", " ", (slug or "")).strip().title()


def _linkedin_company_id(url: str, slug: str = "") -> str:
    html_bits = []
    q = urlparse(url).query
    m = LINKEDIN_F_C_RE.search(url) or LINKEDIN_F_C_RE.search(q)
    if m:
        return m.group(1)
    slug = slug or _linkedin_slug(url)
    candidates = []
    if url:
        candidates.append(url)
    if slug:
        candidates.extend([
            f"https://www.linkedin.com/company/{slug}/",
            f"https://www.linkedin.com/company/{slug}/jobs/",
        ])
    seen = set()
    for href in candidates:
        if href in seen:
            continue
        seen.add(href)
        try:
            r = requests.get(href, headers=_headers(), timeout=HTTP_TIMEOUT, allow_redirects=True)
            html = r.text or ""
        except Exception as e:
            print(f"[LiveJobs] company page {href}: {e}")
            continue
        html_bits.append(html)
        urn = LINKEDIN_COMPANY_URN_RE.search(html)
        if urn:
            return urn.group(1)
        fc = LINKEDIN_F_C_RE.search(html)
        if fc:
            return fc.group(1)
    return ""


def _finalize_url_jobs(rows: list[dict], company: str, require_company: bool) -> list[dict]:
    bench = get_bench()
    seen = set()
    out = []
    for row in rows or []:
        href = _clean_job_url(row.get("url") or "")
        if not href or href in seen:
            continue
        seen.add(href)
        title = (row.get("title") or "").strip()
        snippet = (row.get("snippet") or "").strip()
        if _is_junk_listing(title, snippet):
            continue
        co = (row.get("company") or "").strip()
        if require_company and co and company and not _company_name_matches(co, company):
            continue
        age = row.get("posted_minutes")
        if age is None:
            age = extract_age_minutes(f"{title} {snippet} {row.get('description') or ''}")
        if not in_posted_window(age, URL_DISCOVER_MINUTES):
            continue
        job = {
            "id": _job_id(href),
            "title": (title or "Job listing")[:140],
            "company": co or company,
            "url": href,
            "platform": row.get("platform") or _platform(href) or "Web",
            "track": row.get("track") or _role_track(f"{title} {snippet}") or "software",
            "snippet": snippet[:400],
            "posted_minutes": age,
            "first_seen_minutes": 0,
            "recency": "posted_in_window",
            "emails": row.get("emails") or [],
            "description": (row.get("description") or snippet)[:8000],
            "source": row.get("source") or "",
            "matched_talent": None,
        }
        out.append(job)
        if len(out) >= MAX_URL_JOBS:
            break
    out.sort(key=lambda j: j["posted_minutes"] if j.get("posted_minutes") is not None else 99999)
    _enrich_linkedin_descriptions(out)
    for job in out:
        _attach_talent(job, bench)
    return out[:MAX_URL_JOBS]


def _collect_linkedin_company(company: str, company_id: str, tpr: str) -> list[dict]:
    rows: list[dict] = []
    starts = (0, 10, 20, 30)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = []
        if company_id:
            for start in starts:
                futs.append(pool.submit(_linkedin_guest_search, "", start, tpr, company_id))
        name_q = (company or "").strip()
        if name_q:
            for start in (0, 10):
                futs.append(pool.submit(_linkedin_guest_search, name_q, start, tpr, None))
        for fut in as_completed(futs):
            try:
                rows.extend(fut.result() or [])
            except Exception as e:
                print(f"[LiveJobs] company LinkedIn collect: {e}")
    return rows


def _naukri_company_jobs(company: str) -> list[dict]:
    if not company:
        return []
    safe = re.sub(r'["\']', " ", company).strip()
    queries = [
        f'site:naukri.com/job-listings "{safe}"',
        f'site:naukri.com "{safe}" job',
    ]
    hits: list[dict] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(_ddg, q, 12, "w") for q in queries]
        for fut in as_completed(futs):
            try:
                hits.extend(fut.result() or [])
            except Exception as e:
                print(f"[LiveJobs] Naukri DDG: {e}")
    rows = []
    seen = set()
    for h in hits:
        href = _clean_job_url(h.get("url") or "")
        if not href or "naukri.com" not in href.lower() or href in seen:
            continue
        if not _is_job_url(href) and "/job-listings" not in href.lower():
            continue
        seen.add(href)
        title_raw = h.get("title") or ""
        snippet = h.get("snippet") or ""
        role, co = _split_title(title_raw)
        age = extract_age_minutes(f"{title_raw} {snippet}")
        rows.append({
            "title": role or title_raw,
            "company": co or company,
            "url": href,
            "platform": "Naukri",
            "snippet": snippet,
            "posted_minutes": age,
            "source": "naukri_ddg",
            "description": "",
        })
    need = [r for r in rows if r.get("posted_minutes") is None][:8]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_fetch_job_page, r["url"]): r for r in need}
        for fut in as_completed(futs):
            job = futs[fut]
            page = fut.result() or {}
            html = page.get("html") or ""
            text = page.get("text") or ""
            if text:
                job["description"] = text[:2500]
            age = extract_age_minutes(f"{html} {text} {job.get('snippet','')} {job.get('title','')}")
            if age is not None:
                job["posted_minutes"] = age
    return rows


def _website_company_name(url: str) -> str:
    host = _registrable_host(url)
    if not host or host in SKIP_WEB_HOSTS or host.endswith(".linkedin.com"):
        return ""
    label = host.split(".")[0]
    return _slug_to_company_name(label)


def _classify_source_url(url: str) -> dict:
    host = _registrable_host(url)
    path = (urlparse(url).path or "").lower()
    if "linkedin.com" in host:
        if "/jobs/view/" in path:
            return {"kind": "job", "company": "", "company_id": "", "platform": "linkedin"}
        slug = _linkedin_slug(url)
        cid = _linkedin_company_id(url, slug)
        name = _slug_to_company_name(slug)
        if not name and cid:
            name = "This company"
        if slug or cid:
            return {"kind": "linkedin_company", "company": name, "company_id": cid, "platform": "linkedin"}
        raise ValueError(
            "That LinkedIn link is not a company page or a job post. "
            "Paste /company/name or /jobs/view/123."
        )
    if "naukri.com" in host:
        name = ""
        if "/job-listings" in path:
            # listing slug often includes company at the end; still search by tokens later
            bits = re.split(r"[-_/]+", path)
            skip = {"job", "listings", "jobs", "in", "www", "naukri", "com"}
            tokens = [b for b in bits if b and b not in skip and not b.isdigit() and len(b) > 2]
            if tokens:
                name = _slug_to_company_name(tokens[-1])
        else:
            parts = [p for p in path.split("/") if p and p not in ("jobs", "job")]
            if parts:
                name = _slug_to_company_name(parts[0].replace("-jobs", "").replace("-careers", ""))
        if not name:
            name = "this employer"
        return {"kind": "naukri", "company": name, "company_id": "", "platform": "naukri"}
    greenhouse_token = _greenhouse_board_token(url)
    if greenhouse_token:
        board = _greenhouse_request(
            f"https://boards-api.greenhouse.io/v1/boards/{greenhouse_token}"
        ) or {}
        company = str(board.get("name") or _slug_to_company_name(greenhouse_token)).strip()
        return {"kind": "greenhouse", "company": company, "company_id": greenhouse_token, "platform": "greenhouse"}
    if host in SKIP_WEB_HOSTS:
        raise ValueError("Paste a company website, LinkedIn/Naukri page, or Greenhouse job-board URL.")
    name = _website_company_name(url)
    if not name:
        raise ValueError("Could not read a company name from that website URL.")
    return {"kind": "website", "company": name, "company_id": "", "platform": "web"}


def _ingest_payload(mode: str, jobs: list[dict], *, url: str, company: str, note: str) -> dict:
    return {
        "mode": mode,
        "url": url,
        "company": company,
        "window_days": URL_DISCOVER_DAYS,
        "window_minutes": URL_DISCOVER_MINUTES,
        "job_count": len(jobs),
        "in_window_count": len(jobs),
        "jobs": jobs,
        "job": jobs[0] if jobs else None,
        "scanned_at": _iso(),
        "_meta": {
            "note": note,
            "auto_send": False,
        },
    }


def ingest_url(url: str, days: int = URL_DISCOVER_DAYS) -> dict:
    url = _normalize_http_url(url)
    if not url:
        raise ValueError("Paste a LinkedIn company page, job post, Naukri/Greenhouse board, or company website.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("That is not a valid http(s) URL.")
    days = max(7, min(int(days or URL_DISCOVER_DAYS), 14))
    if _is_job_url(url):
        job = _ingest_single_job(url)
        age = job.get("posted_minutes")
        if age is not None and age > days * 24 * 60:
            job["recency"] = "too_old_or_unknown"
        note = "Ingested that one public job post."
        if job.get("recency") == "too_old_or_unknown":
            note += " Posting date is older than 2 weeks or could not be verified."
        return _ingest_payload("job", [job], url=url, company=job.get("company") or "", note=note)

    info = _classify_source_url(url)
    company = info.get("company") or ""
    kind = info.get("kind")
    rows: list[dict] = []
    if kind in ("linkedin_company", "website"):
        cid = info.get("company_id") or ""
        if kind == "website" and not cid:
            cid = ""
        rows.extend(_collect_linkedin_company(company, cid, TPR_TWO_WEEKS))
    if kind in ("naukri", "website", "linkedin_company"):
        rows.extend(_naukri_company_jobs(company))
    if kind == "greenhouse":
        rows.extend(_greenhouse_board_jobs(url))

    require_name = not (kind == "linkedin_company" and info.get("company_id"))
    jobs = _finalize_url_jobs(rows, company, require_company=require_name)
    if kind == "linkedin_company":
        note = (
            f"Jobs at {company or 'this company'} on LinkedIn (and Naukri when dated) posted in the last "
            f"{days} days. Listings without a verifiable date stay hidden."
        )
    elif kind == "naukri":
        note = (
            f"Naukri listings for {company} posted in the last {days} days. "
            f"{NAUKRI_BLOCKED_NOTE} Undated results are dropped."
        )
    elif kind == "greenhouse":
        note = (
            f"Public Greenhouse postings for {company} from the board API. "
            f"Only jobs with a verified first-publication date inside the last {days} days are shown."
        )
    else:
        note = (
            f"Public jobs matching {company} from LinkedIn and Naukri in the last {days} days. "
            "Only rows with a verifiable posting date are shown."
        )
    if not jobs:
        note += " Nothing proven in that window — the company may have no dated public posts right now."
    return _ingest_payload(kind, jobs, url=url, company=company, note=note)


def _ingest_single_job(url: str) -> dict:
    page = _fetch_job_page(url)
    text = page.get("text") or ""
    html = page.get("html") or ""
    platform = _platform(url)
    description = (page.get("description") or "").strip()
    role, company = _split_title((text or "")[:180])
    posted = extract_age_minutes(f"{html} {text}", _now())
    if platform == "Greenhouse":
        token = _greenhouse_board_token(url)
        parts = [part for part in (urlparse(url).path or "").split("/") if part]
        job_id = next((part for part in parts[1:] if part.isdigit()), "")
        if token and job_id:
            detail = _greenhouse_request(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}?content=true"
            ) or {}
            if detail:
                role = str(detail.get("title") or role or "").strip()
                company = str(detail.get("company_name") or company or _slug_to_company_name(token)).strip()
                content = str(detail.get("content") or "")
                description = BeautifulSoup(content, "html.parser").get_text(" ", strip=True) or description
                posted = _iso_to_age_minutes(str(detail.get("first_published") or ""))
    if not role or role.startswith("http") or len(role) < 4:
        role, company = _split_title(url)
    snippet_source = description or ("" if platform == "LinkedIn" else text)
    snippet = snippet_source[:400]
    track = _role_track(f"{role} {description} {url}") or "software"
    job = {
        "id": _job_id(url),
        "title": role or "Job listing",
        "company": company,
        "url": url,
        "platform": platform,
        "track": track,
        "snippet": snippet,
        "posted_minutes": posted,
        "first_seen_minutes": 0,
        "recency": "posted_in_window" if in_posted_window(posted, URL_DISCOVER_MINUTES) else "too_old_or_unknown",
        "emails": _emails_from(text),
        "description": (description or (text if platform != "LinkedIn" else ""))[:8000],
        "description_source": "public_job_page" if description else "",
        "matched_talent": None,
    }
    return _attach_talent(job)


def _parse_resume_profile(raw_text: str, slot: dict) -> dict:
    excerpt = (raw_text or "").strip()[:12000]
    if not excerpt:
        raise ValueError("Could not read text from that resume.")
    fallback = {
        "name": "",
        "title": slot["label"],
        "skills": [],
        "years_experience": "",
        "summary": excerpt[:900],
        "strongest_fit": slot["track"],
    }
    prompt = f"""Extract a compact talent profile from this resume.
Return ONLY JSON:
{{"name":"","title":"","skills":["python"],"years_experience":"5","summary":"2-4 sentences of strengths","strongest_fit":"ai|software|both"}}
Use the actual job title and hard skills from the resume. strongest_fit is ai, software, or both.
RESUME:
{excerpt}
"""
    try:
        text = llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=700,
            json_mode=True,
            timeout=60.0,
            reasoning_effort="low",
            retry_empty=False,
        )
        data = json.loads(text)
        if not isinstance(data, dict):
            return fallback
        skills = data.get("skills") or []
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        fit = str(data.get("strongest_fit") or slot["track"]).lower()
        if fit not in ("ai", "software", "both"):
            fit = slot["track"]
        return {
            "name": str(data.get("name") or "")[:80],
            "title": str(data.get("title") or slot["label"])[:120],
            "skills": [str(s)[:40] for s in skills[:18] if str(s).strip()],
            "years_experience": str(data.get("years_experience") or "")[:20],
            "summary": str(data.get("summary") or excerpt[:900])[:1200],
            "strongest_fit": fit,
        }
    except Exception as e:
        print(f"[LiveJobs] resume LLM parse failed: {e}")
        return fallback


def save_resume(filename: str, data: bytes, slot_id: Optional[str] = None) -> dict:
    if not data:
        raise ValueError("Empty file.")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Resume exceeds 8MB.")
    bench = get_bench()
    people = dict(bench.get("people") or {})
    sid = (slot_id or "").strip()
    if sid and sid in people:
        pass
    else:
        if len(people) >= MAX_BENCH_RESUMES:
            raise ValueError(f"Talent bench is full ({MAX_BENCH_RESUMES} resumes). Remove one first.")
        sid = sid or f"talent_{uuid.uuid4().hex[:10]}"
    slot = {
        "id": sid,
        "track": "both",
        "label": Path(filename or "resume").stem.replace("_", " ")[:80] or "Talent",
    }
    raw, _, _kind = brochure_extract._extract_text(data, filename or "resume.pdf")
    profile = _parse_resume_profile(raw, slot)
    fit = str(profile.get("strongest_fit") or "both").lower()
    track = fit if fit in ("ai", "software", "both") else "both"
    people[sid] = {
        **profile,
        "slot": sid,
        "track": track,
        "label": profile.get("name") or profile.get("title") or slot["label"],
        "loaded": True,
        "filename": filename or "",
        "updated_at": _iso(),
    }
    updated = _iso()
    _save_json(BENCH_PATH, {"people": people, "updated_at": updated})
    return {"people": people, "updated_at": updated, "slots": _slots_from_people(people)}


def clear_resume(slot_id: str) -> dict:
    bench = get_bench()
    people = dict(bench.get("people") or {})
    if slot_id not in people:
        raise ValueError("Unknown resume on the talent bench.")
    people.pop(slot_id, None)
    updated = _iso()
    _save_json(BENCH_PATH, {"people": people, "updated_at": updated})
    return {"people": people, "updated_at": updated, "slots": _slots_from_people(people)}


