"""
Smart Scheduling via AI
========================
Model: Azure OpenAI (primary) via shared LLM client

Analyzes platforms, goals, and audience to recommend optimal posting times.
"""
import json

from backend.services import llm as llm_client

SYSTEM_PROMPT = """You are an expert social media growth strategist with deep knowledge of
platform algorithms, audience behavior patterns, and engagement optimization.

Analyze the given platforms and goals to create the PERFECT weekly posting schedule.

Return ONLY valid JSON in this exact format:
{
  "strategy_summary": "2-sentence overall strategy",
  "weekly_schedule": {
    "Monday": [
      {"platform": "Instagram", "time": "9:00 AM", "post_type": "Carousel", "reason": "Why this time"},
      ...
    ],
    "Tuesday": [...],
    ...
    "Sunday": [...]
  },
  "platform_insights": {
    "Instagram": {"best_days": "Tue, Wed, Fri", "peak_hours": "8-10AM, 7-9PM", "tip": "..."},
    ...
  },
  "optimization_tips": ["Tip 1", "Tip 2", "Tip 3", "Tip 4", "Tip 5"]
}

No markdown, no extra text, ONLY JSON."""


def _parse_json_safe(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def run(
    platforms: list,
    optimize_for: str = "Engagement",
    instructions: str = "",
) -> dict:
    """Returns smart schedule dict."""
    platform_str = ", ".join(platforms) if platforms else "Instagram"
    posts_per_week = max(len(platforms) * 3, 5)

    user_prompt = (
        f"Platforms: {platform_str}\n"
        f"Primary goal: Maximize {optimize_for}\n"
        f"Additional context: {instructions or 'General content brand, mixed audience'}\n"
        f"Posts per week target: ~{posts_per_week} posts\n\n"
        f"Create the optimal weekly posting schedule with platform-specific timing.\n"
        f"Include all 7 days. Explain WHY each time slot was chosen.\n"
        f"Return JSON only."
    )

    raw = llm_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.6,
        max_tokens=3500,
        json_mode=True,
    )
    data = _parse_json_safe(raw)
    print("[SmartSchedule] LLM OK")
    return data
