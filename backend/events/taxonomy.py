"""Canonical categories, audiences and synonym tables.

Categories are free-form strings on events; this list only provides canonical spellings
and aliases. New categories can be added at runtime (they are registered in the
`categories` collection automatically), so this file is a starting point, not a limit.
"""
from __future__ import annotations

import re

CATEGORIES: list[str] = [
    "Artificial Intelligence", "Machine Learning", "Technology", "Software", "SaaS",
    "Startups", "Finance", "FinTech", "Healthcare", "HealthTech", "Travel", "TravelTech",
    "E-commerce", "Marketing", "Sales", "Cybersecurity", "Cloud", "Data Science",
    "Blockchain", "Education", "Manufacturing", "Automotive", "Real Estate", "Logistics",
    "Energy", "Retail", "Human Resources", "Product Management", "Business",
    "Entrepreneurship", "Investment",
]

CATEGORY_ALIASES: dict[str, str] = {
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence",
    "genai": "Artificial Intelligence", "generative ai": "Artificial Intelligence",
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "tech": "Technology", "it": "Technology", "software development": "Software",
    "saas": "SaaS", "startup": "Startups", "startups": "Startups",
    "fin tech": "FinTech", "fintech": "FinTech", "finance": "Finance", "banking": "Finance",
    "health": "Healthcare", "healthcare": "Healthcare", "health care": "Healthcare",
    "healthtech": "HealthTech", "health tech": "HealthTech", "digital health": "HealthTech",
    "travel tech": "TravelTech", "traveltech": "TravelTech", "tourism": "Travel",
    "ecommerce": "E-commerce", "e-commerce": "E-commerce", "e commerce": "E-commerce",
    "infosec": "Cybersecurity", "security": "Cybersecurity", "cyber security": "Cybersecurity",
    "cloud computing": "Cloud", "devops": "Cloud",
    "data": "Data Science", "data science": "Data Science", "analytics": "Data Science",
    "crypto": "Blockchain", "web3": "Blockchain", "blockchain": "Blockchain",
    "edtech": "Education", "hr": "Human Resources", "human resources": "Human Resources",
    "product": "Product Management", "product management": "Product Management",
    "proptech": "Real Estate", "supply chain": "Logistics", "cleantech": "Energy",
    "renewable energy": "Energy", "vc": "Investment", "venture capital": "Investment",
    "entrepreneur": "Entrepreneurship", "entrepreneurship": "Entrepreneurship",
}

AUDIENCES: list[str] = [
    "Founders", "Entrepreneurs", "Investors", "Developers", "CTOs", "Product Managers",
    "Business Leaders", "Researchers", "Designers", "Marketers", "Sales Professionals",
    "Data Scientists", "Engineers", "Students", "HR Professionals", "Executives",
]


def slugify(text: str, max_len: int = 80) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].strip("-")


def canonical_category(name: str) -> str:
    """Map a category string (or alias) to its canonical spelling; unknown names pass through."""
    key = re.sub(r"\s+", " ", (name or "").strip()).lower()
    if not key:
        return ""
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    for cat in CATEGORIES:
        if cat.lower() == key:
            return cat
    return re.sub(r"\s+", " ", name.strip())
