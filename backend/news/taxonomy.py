"""Default categories, topic lexicon and entity lexicon.

These are STARTING POINTS. Categories live in the `news_categories` collection (seeded from
here, editable by an admin, new ones can be added at any time), so the taxonomy is extensible
without code changes. Topics and entities are lexicons the rule-based processors use; the LLM
enrichment adds to them.
"""
from __future__ import annotations

import re

# Virtual categories (not stored on articles):
#   all      -> no category filter
#   breaking -> articles/stories flagged is_breaking
VIRTUAL_CATEGORIES = [
    {"slug": "all", "name": "All", "icon": "🗞️", "order": 0, "virtual": True},
    {"slug": "breaking", "name": "Breaking News", "icon": "🚨", "order": 1, "virtual": True},
]

# order, slug, name, icon, keywords (lower-case; matched on word boundaries; title hits weigh 3x)
_CATEGORIES = [
    (10, "ai", "AI", "🤖", ["artificial intelligence", "ai", "a.i.", "openai", "anthropic", "deepmind", "chatgpt", "gpt", "llm", "llms", "large language model", "generative ai", "genai", "machine learning", "deep learning", "neural network", "ai agent", "ai agents", "copilot", "gemini", "claude", "llama", "midjourney", "nvidia", "robotics", "humanoid"]),
    (20, "technology", "Technology", "💻", ["technology", "tech", "software", "hardware", "app", "apps", "smartphone", "iphone", "android", "chip", "chips", "semiconductor", "cloud", "gadget", "internet", "startup", "platform", "developer", "developers", "open source", "linux", "microsoft", "apple", "google", "amazon", "meta", "samsung", "intel", "amd", "tesla", "5g", "wifi", "browser", "computing", "quantum"]),
    (30, "world", "World", "🌍", ["war", "ceasefire", "conflict", "united nations", "nato", "embassy", "refugees", "diplomat", "summit", "sanctions", "border", "gaza", "ukraine", "russia", "china", "israel", "iran", "europe", "africa", "middle east", "asia", "protest", "earthquake", "flood", "wildfire", "hurricane", "cyclone", "attack"]),
    (40, "india", "India", "🇮🇳", ["india", "indian", "delhi", "mumbai", "bengaluru", "bangalore", "chennai", "hyderabad", "kolkata", "pune", "modi", "lok sabha", "rajya sabha", "bjp", "congress party", "rupee", "sensex", "nifty", "rbi", "isro", "supreme court of india", "kerala", "gujarat", "maharashtra", "tamil nadu", "uttar pradesh", "bcci", "ipl", "aadhaar", "upi"]),
    (50, "business", "Business", "🏢", ["business", "company", "companies", "ceo", "earnings", "revenue", "profit", "merger", "acquisition", "acquires", "layoffs", "supply chain", "retail", "brand", "customers", "industry", "manufacturing", "airline", "carmaker", "consumer", "deal", "lawsuit", "antitrust"]),
    (60, "finance", "Finance", "💹", ["stock", "stocks", "shares", "market", "markets", "wall street", "nasdaq", "dow jones", "s&p 500", "sensex", "nifty", "investors", "bond", "yield", "ipo", "hedge fund", "bitcoin", "crypto", "cryptocurrency", "ethereum", "banking", "bank", "fund", "dividend", "forex", "currency", "dollar", "rupee", "commodities", "gold", "oil prices"]),
    (70, "startups", "Startups", "🚀", ["startup", "startups", "founder", "founders", "funding round", "raises", "raised", "series a", "series b", "series c", "seed round", "venture capital", "unicorn", "accelerator", "y combinator", "valuation"]),
    (80, "science", "Science", "🔬", ["science", "scientists", "researchers", "study", "discovery", "physics", "chemistry", "biology", "genome", "fossil", "species", "experiment", "laboratory", "nature journal", "peer-reviewed", "astronomers", "dna", "neuroscience"]),
    (90, "space", "Space", "🛰️", ["space", "nasa", "spacex", "isro", "esa", "rocket", "satellite", "astronaut", "moon", "mars", "orbit", "telescope", "launch pad", "starship", "artemis", "james webb", "iss", "cosmos", "galaxy"]),
    (100, "cybersecurity", "Cybersecurity", "🛡️", ["cybersecurity", "cyber", "ransomware", "malware", "phishing", "data breach", "hackers", "hacker", "vulnerability", "zero-day", "exploit", "botnet", "cyberattack", "infosec", "ddos", "spyware", "encryption", "cve"]),
    (110, "politics", "Politics", "🏛️", ["election", "elections", "president", "prime minister", "parliament", "senate", "congress", "minister", "government", "opposition", "campaign", "vote", "voters", "policy", "legislation", "bill", "trump", "biden", "white house", "democrats", "republicans", "labour", "tory"]),
    (120, "economy", "Economy", "📈", ["economy", "economic", "inflation", "gdp", "recession", "interest rate", "interest rates", "central bank", "federal reserve", "unemployment", "tariff", "tariffs", "trade war", "budget", "fiscal", "imf", "world bank", "growth forecast", "cost of living", "jobs report"]),
    (130, "health", "Health", "🩺", ["health", "hospital", "vaccine", "disease", "cancer", "drug", "clinical trial", "patients", "doctors", "medical", "mental health", "who", "outbreak", "virus", "pandemic", "nhs", "fda", "obesity", "diabetes", "surgery"]),
    (140, "climate", "Climate", "🌡️", ["climate", "climate change", "global warming", "emissions", "carbon", "renewable", "solar", "wind power", "net zero", "cop", "fossil fuels", "biodiversity", "deforestation", "heatwave", "sea level", "glacier", "electric vehicle", "ev"]),
    (150, "sports", "Sports", "🏅", ["football", "soccer", "cricket", "tennis", "olympics", "olympic", "fifa", "nba", "nfl", "premier league", "champions league", "formula 1", "f1", "grand slam", "world cup", "match", "tournament", "coach", "goal", "wicket", "ipl", "athlete", "medal", "league"]),
    (160, "entertainment", "Entertainment", "🎬", ["film", "movie", "movies", "actor", "actress", "netflix", "disney", "box office", "album", "singer", "music", "concert", "celebrity", "oscars", "grammys", "bollywood", "hollywood", "tv series", "streaming", "festival", "director", "trailer"]),
    (170, "education", "Education", "🎓", ["education", "school", "schools", "university", "universities", "students", "student", "teachers", "exam", "exams", "curriculum", "tuition", "college", "campus", "scholarship", "graduate", "nep", "cbse", "jee", "neet"]),
    (180, "travel", "Travel", "✈️", ["travel", "tourism", "tourists", "flight", "flights", "airline", "airport", "hotel", "holiday", "vacation", "destination", "cruise", "visa", "passport", "itinerary", "resort", "backpacking"]),
]

DEFAULT_CATEGORIES = [
    {"slug": slug, "name": name, "icon": icon, "order": order, "keywords": kws, "enabled": True, "virtual": False}
    for order, slug, name, icon, kws in _CATEGORIES
]

# "What's happening now": stories grouped into these sections (category slugs feeding each).
WHATS_HAPPENING_GROUPS = [
    {"key": "global", "label": "Global", "icon": "🌎", "categories": ["world", "politics", "economy"]},
    {"key": "ai", "label": "AI", "icon": "🤖", "categories": ["ai"]},
    {"key": "technology", "label": "Technology", "icon": "💻", "categories": ["technology", "cybersecurity", "startups"]},
    {"key": "business", "label": "Business & Markets", "icon": "💹", "categories": ["business", "finance"]},
    {"key": "india", "label": "India", "icon": "🇮🇳", "categories": ["india"]},
    {"key": "science", "label": "Science & Planet", "icon": "🔬", "categories": ["science", "space", "climate", "health"]},
]

# How much each category matters when scoring importance (0-15).
CATEGORY_WEIGHT = {
    "world": 12, "politics": 11, "ai": 12, "economy": 10, "finance": 9, "business": 8, "technology": 8,
    "cybersecurity": 9, "india": 9, "science": 7, "space": 7, "health": 8, "climate": 8, "startups": 6,
    "education": 4, "travel": 3, "sports": 4, "entertainment": 3,
}

# ------------------------------------------------------------------------------------ topics
TOPICS: dict[str, list[str]] = {
    "AI Agents": ["ai agent", "ai agents", "agentic", "autonomous agent", "agent framework"],
    "LLMs": ["llm", "llms", "large language model", "chatgpt", "gpt-4", "gpt-5", "claude", "gemini", "llama", "mistral", "foundation model"],
    "Generative AI": ["generative ai", "genai", "text-to-image", "image generation", "video generation", "diffusion model", "sora", "midjourney"],
    "Robotics": ["robot", "robots", "robotics", "humanoid", "drone", "drones"],
    "Semiconductors": ["semiconductor", "semiconductors", "chip", "chips", "chipmaker", "tsmc", "foundry", "gpu", "gpus", "nvidia", "lithography"],
    "Cloud": ["cloud", "aws", "azure", "google cloud", "data center", "data centre", "data centers", "hyperscaler", "kubernetes"],
    "Cybersecurity": ["cyber", "ransomware", "malware", "phishing", "zero-day", "data breach", "hackers", "vulnerability", "cyberattack"],
    "Quantum Computing": ["quantum"],
    "Electric Vehicles": ["electric vehicle", "electric vehicles", "ev", "evs", "battery", "byd", "tesla", "charging network"],
    "Space Exploration": ["nasa", "spacex", "isro", "rocket", "satellite", "moon", "mars", "orbit", "astronaut", "starship", "artemis"],
    "Climate Change": ["climate change", "global warming", "emissions", "carbon", "net zero", "heatwave", "renewable"],
    "Cryptocurrency": ["bitcoin", "crypto", "cryptocurrency", "ethereum", "blockchain", "stablecoin"],
    "Stock Markets": ["stock market", "stocks", "shares", "sensex", "nifty", "nasdaq", "dow jones", "s&p 500", "wall street"],
    "Inflation & Rates": ["inflation", "interest rate", "interest rates", "rate cut", "rate hike", "central bank", "federal reserve", "rbi", "ecb"],
    "Elections": ["election", "elections", "voters", "ballot", "polling", "campaign trail"],
    "Regulation": ["regulation", "regulator", "regulators", "antitrust", "lawsuit", "sued", "fined", "compliance", "legislation"],
    "Healthcare": ["hospital", "vaccine", "clinical trial", "cancer", "disease", "outbreak", "patients"],
    "Startups & Funding": ["startup", "startups", "funding round", "raises", "series a", "series b", "venture capital", "unicorn", "ipo"],
    "Data Privacy": ["privacy", "gdpr", "data protection", "surveillance"],
    "Open Source": ["open source", "open-source", "github", "linux"],
    "Smartphones": ["iphone", "android", "pixel", "galaxy", "smartphone"],
    "Energy": ["oil prices", "opec", "solar", "wind power", "nuclear", "power grid", "natural gas"],
    "Trade & Tariffs": ["tariff", "tariffs", "trade war", "export controls", "sanctions"],
}

# --------------------------------------------------------------------------------- entities
ORGANIZATIONS = [
    "OpenAI", "Anthropic", "Google", "Alphabet", "DeepMind", "Google DeepMind", "Microsoft", "Apple", "Amazon", "AWS", "Meta",
    "Facebook", "NVIDIA", "Nvidia", "Tesla", "Intel", "AMD", "Qualcomm", "TSMC", "Samsung", "IBM", "Oracle", "Salesforce", "xAI",
    "Mistral", "Hugging Face", "Cohere", "Perplexity", "Stability AI", "SpaceX", "Blue Origin", "NASA", "ISRO", "ESA",
    "United Nations", "UN", "WHO", "NATO", "European Union", "EU", "IMF", "World Bank", "OPEC", "Federal Reserve",
    "Reserve Bank of India", "RBI", "SEBI", "Reliance", "Tata", "Infosys", "TCS", "Wipro", "Adani", "Flipkart", "Zomato", "Paytm",
    "BBC", "Reuters", "Netflix", "Disney", "Sony", "Huawei", "ByteDance", "TikTok", "Alibaba", "Tencent", "Baidu", "Uber",
    "Airbnb", "Stripe", "Palantir", "Cloudflare", "CrowdStrike", "Cisco", "Dell", "Boeing", "Airbus", "Pfizer", "Moderna",
    "Pentagon", "White House", "Kremlin", "Supreme Court", "BJP", "Congress", "Hamas", "Hezbollah", "FBI", "CIA", "FDA", "NHS",
]
PEOPLE = [
    "Elon Musk", "Sam Altman", "Satya Nadella", "Sundar Pichai", "Tim Cook", "Mark Zuckerberg", "Jensen Huang", "Jeff Bezos",
    "Bill Gates", "Narendra Modi", "Donald Trump", "Joe Biden", "Kamala Harris", "Vladimir Putin", "Volodymyr Zelensky",
    "Xi Jinping", "Keir Starmer", "Emmanuel Macron", "Rahul Gandhi", "Nirmala Sitharaman", "Dario Amodei", "Demis Hassabis",
    "Mustafa Suleyman", "Benjamin Netanyahu", "Jerome Powell", "Christine Lagarde", "Ratan Tata", "Mukesh Ambani",
]
PRODUCTS_TECH = [
    "ChatGPT", "GPT-4", "GPT-4o", "GPT-5", "Claude", "Gemini", "Llama", "Copilot", "Sora", "Grok", "Bitcoin", "Ethereum",
    "Kubernetes", "Linux", "Android", "iOS", "iPhone", "Windows", "5G", "Starlink", "Starship", "Falcon 9", "Chandrayaan",
    "Gaganyaan", "Vision Pro", "Pixel", "Galaxy", "PlayStation", "Xbox", "UPI",
]
LOCATION_EXTRAS = [
    "Silicon Valley", "Wall Street", "Gaza", "West Bank", "Kashmir", "Delhi", "Mumbai", "Bengaluru", "Bangalore", "Chennai",
    "Hyderabad", "Kolkata", "Pune", "Gujarat", "Kerala", "Maharashtra", "Tamil Nadu", "Uttar Pradesh", "London", "Paris",
    "Berlin", "Brussels", "Geneva", "Tokyo", "Beijing", "Shanghai", "Hong Kong", "Taipei", "Seoul", "Singapore", "Moscow",
    "Kyiv", "Washington", "New York", "California", "Texas", "Dubai", "Riyadh", "Tehran", "Jerusalem", "Tel Aviv", "Sydney",
    "Toronto", "Nairobi", "Lagos", "Cairo",
]
COUNTRY_ALIASES = {
    "US": "United States", "U.S.": "United States", "USA": "United States", "America": "United States", "UK": "United Kingdom",
    "Britain": "United Kingdom", "UAE": "United Arab Emirates", "Russia": "Russia", "Türkiye": "Turkey",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
