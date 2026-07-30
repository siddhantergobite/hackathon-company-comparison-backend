"""
Bulk Schedule via AI
======================
Model: Azure OpenAI (primary) via shared LLM client

Generates a complete content calendar (7 or 30 days) across multiple platforms.
"""
import json
from datetime import datetime, timedelta

from backend.services import llm as llm_client

SYSTEM_PROMPT = """You are a world-class social media strategist and content calendar expert.
Create a detailed, diverse content calendar.
Each post must be unique — vary post types: Carousel, Reel, Story, Static, Poll, Quote, Behind-the-scenes, Tutorial, Product, Testimonial, etc.
Use proven posting times optimized for each platform.
Mix educational, entertaining, promotional, and engagement content.

Return ONLY valid JSON — a list of post objects.
Each object must have exactly these fields:
{
  "day": 1,
  "date": "Mon Jul 22",
  "platform": "Instagram",
  "time": "9:00 AM",
  "post_type": "Carousel",
  "caption_preview": "First line of caption here...",
  "hashtags": "#tag1 #tag2 #tag3",
  "image_idea": "Brief visual description",
  "status": "Scheduled"
}

No markdown, no explanation, ONLY the JSON array."""


def _parse_json_safe(text: str) -> list:
    """Robustly extract JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    start = text.find("[")
    end   = text.rfind("]") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def run(
    instructions: str,
    platforms: list,
    time_range: str = "Next 7 days",
    tone: str = "Friendly",
) -> list:
    """Returns list of post dicts for the content calendar."""
    days = 7 if "7" in time_range else 30
    now  = datetime.now()

    platform_str = ", ".join(platforms) if platforms else "Instagram"
    posts_count  = len(platforms) * days

    user_prompt = (
        f"Brand/Instructions: {instructions or 'General social media brand'}\n"
        f"Platforms: {platform_str}\n"
        f"Time range: {days} days starting from {now.strftime('%a %b %d, %Y')}\n"
        f"Tone: {tone}\n"
        f"Generate {posts_count} posts total ({days} days x {len(platforms)} platforms).\n"
        f"Dates run from {now.strftime('%a %b %d')} to "
        f"{(now + timedelta(days=days-1)).strftime('%a %b %d')}.\n"
        f"Create a complete, diverse content calendar. Return JSON array only."
    )

    raw = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=4500,
    )
    posts = _parse_json_safe(raw)
    print(f"[BulkSchedule] LLM OK -> {len(posts)} posts")
    return posts
