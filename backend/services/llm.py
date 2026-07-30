"""
Shared LLM client — Azure OpenAI (primary) for all backend chat.
Falls back to Groq, then Gemini, only if Azure is unset/fails.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

AZURE_ENDPOINT = (
    os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    or "https://abhishekazureopenaitest.openai.azure.com/openai/v1"
)
AZURE_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-5-mini")

GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

ACTIVE_MODEL_LABEL = f"Azure OpenAI ({AZURE_MODEL})" if AZURE_KEY else "Groq / Gemini"


def azure_configured() -> bool:
    return bool(AZURE_KEY and AZURE_ENDPOINT)


def _azure_client():
    from openai import OpenAI
    return OpenAI(api_key=AZURE_KEY, base_url=AZURE_ENDPOINT)


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(x in m for x in ("gpt-5", "o1", "o3", "o4"))


def chat(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    json_mode: bool = False,
    timeout: float = 180.0,
) -> str:
    """
    Chat completion — Azure OpenAI first, then Groq, then Gemini text.
    Returns assistant message text (stripped).
    """
    errors: list[str] = []
    use_model = model or AZURE_MODEL

    # 1) Azure OpenAI
    if azure_configured():
        try:
            client = _azure_client()

            def _azure_call(use_json: bool) -> str:
                kwargs: dict[str, Any] = {
                    "model": use_model,
                    "messages": messages,
                    "timeout": timeout,
                }
                if _is_reasoning_model(use_model):
                    # reasoning models burn tokens on thinking — pad, but cap for latency
                    kwargs["max_completion_tokens"] = min(max(max_tokens + 800, 512), 6000)
                else:
                    kwargs["max_tokens"] = max_tokens
                    kwargs["temperature"] = temperature
                if use_json:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = client.chat.completions.create(**kwargs)
                return (resp.choices[0].message.content or "").strip()

            text = ""
            try:
                text = _azure_call(json_mode)
            except Exception as e1:
                if json_mode:
                    print(f"[Azure OpenAI] json_mode failed ({e1}); retrying plain")
                    text = _azure_call(False)
                else:
                    raise
            if text:
                print(f"[Azure OpenAI] OK model={use_model} chars={len(text)}")
                return text
            errors.append("Azure returned empty content")
        except Exception as e:
            errors.append(f"Azure: {e}")
            print(f"[Azure OpenAI] failed: {e}")

    # 2) Groq fallback
    if GROQ_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_KEY)
            kwargs = {
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            if text:
                print(f"[Groq fallback] OK chars={len(text)}")
                return text
        except Exception as e:
            errors.append(f"Groq: {e}")
            print(f"[Groq fallback] failed: {e}")

    # 3) Gemini text fallback
    if GEMINI_KEY:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_KEY)
            system = "\n".join(
                m["content"] for m in messages
                if m.get("role") == "system" and isinstance(m.get("content"), str)
            )
            user_parts = []
            for m in messages:
                if m.get("role") == "user":
                    c = m.get("content")
                    if isinstance(c, str):
                        user_parts.append(c)
                    elif isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "text":
                                user_parts.append(part.get("text", ""))
            cfg = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            if system:
                cfg.system_instruction = system
            resp = client.models.generate_content(
                model="gemini-2.0-flash",
                contents="\n".join(user_parts) or "Hello",
                config=cfg,
            )
            text = (resp.text or "").strip()
            if text:
                print(f"[Gemini fallback] OK chars={len(text)}")
                return text
        except Exception as e:
            errors.append(f"Gemini: {e}")
            print(f"[Gemini fallback] failed: {e}")

    raise RuntimeError(
        "All LLM providers failed: " + " | ".join(errors)
        if errors else "No API keys configured"
    )


def chat_vision(
    prompt: str,
    image_b64_jpeg: str,
    *,
    max_tokens: int = 400,
    model: Optional[str] = None,
) -> str:
    """Vision chat via Azure OpenAI first."""
    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64_jpeg}"}},
            {"type": "text", "text": prompt},
        ],
    }]
    return chat(messages, temperature=0.4, max_tokens=max_tokens, model=model or AZURE_MODEL)
