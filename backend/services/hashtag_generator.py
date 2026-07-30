"""
Hashtag Generator
==================
Model: Azure OpenAI (primary) via shared LLM client
Generates 30 hashtags in 3 tiers: Niche, Mid-tier, Broad.
"""
from backend.services import llm as llm_client

PLATFORM_RULES = {
    "Instagram": "Instagram allows up to 30 hashtags. Mix niche (10), medium (10), and broad (10).",
    "TikTok":    "TikTok: 3-5 highly relevant trending hashtags work best. Add 2 broad ones.",
    "Twitter/X": "Twitter: use 1-2 hashtags max per tweet. Make them trending and relevant.",
    "LinkedIn":  "LinkedIn: 3-5 professional industry hashtags. No # spam.",
    "Pinterest": "Pinterest: keyword-rich hashtags, 5-10, descriptive and searchable.",
    "Facebook":  "Facebook: 3-5 hashtags max, topic-focused.",
    "YouTube":   "YouTube: 3 hashtags in description, high-search-volume keywords.",
}

REACH_GUIDES = {
    "Niche":    "Focus on ultra-specific hashtags (under 500K posts) for a highly engaged audience.",
    "Balanced": "Mix of niche (small), mid-tier (100K-1M posts), and a few broad hashtags.",
    "Broad":    "Include high-volume hashtags (1M+ posts) for maximum reach and discoverability.",
}

SYSTEM_PROMPT = """You are a professional social media strategist and hashtag expert.
Generate hashtags that are:
- Relevant, trending, and high-performing for the platform
- Grouped into 3 clear tiers: Niche, Mid-tier, Broad
- Each hashtag starts with #
- No explanation, no numbering, just the hashtags grouped under these exact headers:

### Niche Hashtags (High Engagement)
[10 hashtags]

### Mid-tier Hashtags (Balanced)
[10 hashtags]

### Broad Hashtags (Maximum Reach)
[10 hashtags]

### Quick Copy (All 30)
[all 30 on one line separated by spaces]"""


def run(topic: str, platform: str = "Instagram", reach: str = "Balanced") -> str:
    """Returns formatted hashtag sets."""
    platform_rule = PLATFORM_RULES.get(platform, PLATFORM_RULES["Instagram"])
    reach_guide   = REACH_GUIDES.get(reach, REACH_GUIDES["Balanced"])

    user_prompt = (
        f"Topic/Caption: {topic}\n"
        f"Platform: {platform} — {platform_rule}\n"
        f"Strategy: {reach} — {reach_guide}\n\n"
        f"Generate 30 high-performing hashtags for {platform} about this topic."
    )

    result = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=700,
    )
    print(f"[Hashtag] LLM OK -> {result.count('#')} hashtags")
    return result
