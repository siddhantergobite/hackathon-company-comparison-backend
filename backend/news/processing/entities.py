"""Rule-based entity + location extraction from a headline and teaser.

Uses curated lexicons (organisations, people, products, countries, cities): reliable, fast and
never invents a name. The LLM enrichment step can add more, but only names that literally
appear in the source text are kept (see ai.ground_entities).
"""
from __future__ import annotations

import re
from functools import lru_cache

from backend.news.taxonomy import (
    COUNTRY_ALIASES, LOCATION_EXTRAS, ORGANIZATIONS, PEOPLE, PRODUCTS_TECH,
)

_CANON = {"Nvidia": "NVIDIA", "UN": "United Nations", "EU": "European Union", "RBI": "Reserve Bank of India",
          "Google DeepMind": "DeepMind", "Alphabet": "Google", "Facebook": "Meta", "AWS": "Amazon Web Services"}
_AMBIGUOUS_COUNTRIES = {"Georgia", "Jordan", "Chad", "Niger", "Mali", "Guinea", "Turkey"}


def _alt(names) -> re.Pattern:
    ordered = sorted({n for n in names if n}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in ordered) + r")(?![\w])")


@lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern]:
    countries: list[str] = []
    try:
        import pycountry

        for c in pycountry.countries:
            for n in (getattr(c, "common_name", None), c.name):
                if n and n not in _AMBIGUOUS_COUNTRIES and len(n) > 3:
                    countries.append(n)
    except ImportError:  # pragma: no cover
        pass
    countries += list(COUNTRY_ALIASES) + ["India", "China", "Japan", "Iran", "Iraq", "Peru", "Cuba", "Oman", "Togo", "Laos"]
    return {
        "organizations": _alt(ORGANIZATIONS),
        "people": _alt(PEOPLE),
        "products": _alt(PRODUCTS_TECH),
        "countries": _alt(countries),
        "cities": _alt(LOCATION_EXTRAS),
    }


def _find(pattern: re.Pattern, text: str) -> list[str]:
    seen: list[str] = []
    for m in pattern.finditer(text):
        v = _CANON.get(m.group(1), m.group(1))
        if v not in seen:
            seen.append(v)
    return seen


def extract(title: str | None, description: str | None = None) -> dict:
    """Return {'organizations','people','products','locations','entities','location'} (ordered, unique)."""
    text = f"{title or ''}. {description or ''}"
    p = _patterns()
    orgs, people, products = _find(p["organizations"], text), _find(p["people"], text), _find(p["products"], text)
    countries = [COUNTRY_ALIASES.get(c, c) for c in _find(p["countries"], text)]
    cities = _find(p["cities"], text)
    locations = list(dict.fromkeys(countries + cities))
    # organisation names that are also product names (Google/Gemini) stay in both lists; flat list de-dupes
    flat = list(dict.fromkeys(people + orgs + products))[:12]
    return {
        "organizations": orgs, "people": people, "products": products, "locations": locations,
        "entities": flat, "location": locations[:6],
    }
