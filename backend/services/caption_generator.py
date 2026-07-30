"""
Caption Generator
==================
Model: Azure OpenAI (primary) via shared LLM client
Generates 3 platform-tuned caption variants with emojis and CTAs.
"""
from backend.services import llm as llm_client

TONE_PROMPTS = {
    "Friendly":      "warm, conversational, approachable, like talking to a friend",
    "Witty":         "clever, humorous, punchy one-liners, makes people smile",
    "Professional":  "polished, authoritative, business-appropriate, builds credibility",
    "Inspirational": "motivating, uplifting, emotional, drives people to take action",
    "Bold":          "direct, confident, strong statements, no fluff",
}

LENGTH_TOKENS = {
    "Short":  "1-2 sentences, punchy and direct",
    "Medium": "3-4 sentences, balanced detail and engagement",
    "Long":   "5-6 sentences, storytelling style with full context",
}

PLATFORM_GUIDES = {
    "Instagram": "Include 3-5 emojis, strong hook first line, CTA at end, conversational",
    "LinkedIn":  "Professional tone, add value/insight, no excessive emojis, thought leadership",
    "Twitter/X": "Under 280 chars each, punchy, hook-driven, spark debate or curiosity",
    "TikTok":    "Very casual, trending language, Gen-Z style, hype and energy",
    "Facebook":  "Community-focused, ask a question, encourage comments and shares",
    "Pinterest": "Inspirational, descriptive, keyword-rich, timeless content",
}


SYSTEM_PROMPT = """You are an expert social media copywriter for top brands.
You write captions that stop the scroll, drive engagement, and convert followers to customers.
Always write exactly 3 distinct caption variants numbered 1, 2, 3.
Each variant must be complete and ready to post.
Never add any explanation outside the 3 variants.
Format exactly as:
1. [Caption text here]

2. [Caption text here]

3. [Caption text here]"""


def run(topic: str, tone: str = "Friendly", length: str = "Medium",
        platform: str = "Instagram") -> str:
    """Returns 3 caption variants as a single string."""
    tone_desc     = TONE_PROMPTS.get(tone, TONE_PROMPTS["Friendly"])
    length_desc   = LENGTH_TOKENS.get(length, LENGTH_TOKENS["Medium"])
    platform_desc = PLATFORM_GUIDES.get(platform, PLATFORM_GUIDES["Instagram"])

    user_prompt = (
        f"Topic/Post idea: {topic}\n"
        f"Platform: {platform} — {platform_desc}\n"
        f"Tone: {tone} — {tone_desc}\n"
        f"Length: {length} — {length_desc}\n\n"
        f"Write 3 unique, high-performing {platform} captions for this topic."
    )

    result = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=800,
    )
    print(f"[Caption] LLM OK -> {len(result)} chars")
    return result
