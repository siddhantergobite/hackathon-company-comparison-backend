"""
Shared LLM client — Azure OpenAI (primary) for all backend chat.
Falls back to Groq, then Gemini, only if Azure is unset/fails.

CRITICAL: Always load keys from this project's `.env` by absolute path,
so changing cwd / start scripts / stale OS env cannot keep an old Groq key.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# backend/services/llm.py → project root (hackathon-company-comparison-backend)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from .env (handles quotes / UTF-8 BOM)."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    raw = path.read_text(encoding="utf-8-sig")
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        out[key] = val
    return out


def _load_project_env() -> dict[str, str]:
    """
    Force-load project `.env` into os.environ (override=True),
    then return values parsed directly from the file (source of truth).
    """
    # 1) dotenv into process env (absolute path — never depends on cwd)
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH, override=True)
    else:
        load_dotenv(override=True)  # last-resort cwd fallback
    # 2) file parse wins for our keys (immune to stale OS env leftovers)
    return _parse_env_file(_ENV_PATH)


_file_vals = _load_project_env()
_PARENT_ENV = _PROJECT_ROOT.parent / ".env"


def _coalesce(*vals: str) -> str:
    for v in vals:
        s = (v or "").strip()
        if s and "YOUR." not in s.upper() and s.lower() not in ("your", "changeme", "xxx"):
            return s
    return ""


def _azure_from_fallbacks(vals: dict[str, str]) -> tuple[str, str, str]:
    """Project .env first; if blank, parent Hackathon/.env then OS env."""
    parent_vals = _parse_env_file(_PARENT_ENV) if _PARENT_ENV.is_file() else {}
    endpoint = _coalesce(
        vals.get("AZURE_OPENAI_ENDPOINT", ""),
        parent_vals.get("AZURE_OPENAI_ENDPOINT", ""),
        os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        "https://abhishekazureopenaitest.openai.azure.com/openai/v1",
    ).rstrip("/")
    key = _coalesce(
        vals.get("AZURE_OPENAI_API_KEY", ""),
        parent_vals.get("AZURE_OPENAI_API_KEY", ""),
        os.getenv("AZURE_OPENAI_API_KEY", ""),
    )
    model = _coalesce(
        vals.get("AZURE_OPENAI_MODEL", ""),
        parent_vals.get("AZURE_OPENAI_MODEL", ""),
        os.getenv("AZURE_OPENAI_MODEL", ""),
        "gpt-5-mini",
    )
    return endpoint, key, model


AZURE_ENDPOINT, AZURE_KEY, AZURE_MODEL = _azure_from_fallbacks(_file_vals)

GROQ_KEY = (_file_vals.get("GROQ_API_KEY") or "").strip()
GEMINI_KEY = (_file_vals.get("GEMINI_API_KEY") or "").strip()
GROQ_MODEL = _file_vals.get("GROQ_MODEL") or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Default OFF — Azure OpenAI is primary (avoid Groq TPD rate limits)
RESEARCH_USE_GROQ = (
    _file_vals.get("RESEARCH_USE_GROQ")
    or os.getenv("RESEARCH_USE_GROQ", "0")
).strip().lower() in ("1", "true", "yes", "on")

ACTIVE_MODEL_LABEL = f"Azure OpenAI ({AZURE_MODEL})" if AZURE_KEY else (
    f"Groq ({GROQ_MODEL})" if GROQ_KEY else "Gemini"
)

_KEY_SUFFIX_RE = re.compile(r"[A-Za-z0-9]{4}$")


def _mask_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) < 12:
        return "(missing)"
    return f"{k[:4]}…{k[-4:]} (len={len(k)})"


def _refresh_keys() -> None:
    """Re-read project `.env` on every call so key edits apply immediately."""
    global AZURE_KEY, GROQ_KEY, GEMINI_KEY, GROQ_MODEL, AZURE_MODEL, AZURE_ENDPOINT, ACTIVE_MODEL_LABEL, RESEARCH_USE_GROQ
    vals = _load_project_env()
    AZURE_ENDPOINT, AZURE_KEY, AZURE_MODEL = _azure_from_fallbacks(vals)
    GROQ_KEY = (vals.get("GROQ_API_KEY") or "").strip()
    GEMINI_KEY = (vals.get("GEMINI_API_KEY") or "").strip()
    GROQ_MODEL = vals.get("GROQ_MODEL") or "openai/gpt-oss-120b"
    RESEARCH_USE_GROQ = (
        vals.get("RESEARCH_USE_GROQ") or os.getenv("RESEARCH_USE_GROQ", "0")
    ).strip().lower() in ("1", "true", "yes", "on")
    ACTIVE_MODEL_LABEL = f"Azure OpenAI ({AZURE_MODEL})" if AZURE_KEY else (
        f"Groq ({GROQ_MODEL})" if GROQ_KEY else "Gemini"
    )


def azure_configured() -> bool:
    _refresh_keys()
    # Require a real key; ignore placeholder endpoint-only "config"
    if not AZURE_KEY or AZURE_KEY.lower() in ("your", "changeme", "xxx"):
        return False
    if "YOUR" in (AZURE_ENDPOINT or "").upper():
        return False
    return bool(AZURE_ENDPOINT)


def groq_configured() -> bool:
    _refresh_keys()
    return bool(GROQ_KEY) and GROQ_KEY.startswith("gsk_")


def llm_status() -> dict[str, Any]:
    """Safe diagnostics for /health — never returns the full secret."""
    _refresh_keys()
    return {
        "env_path": str(_ENV_PATH),
        "env_exists": _ENV_PATH.is_file(),
        "active_model": ACTIVE_MODEL_LABEL,
        "azure_configured": azure_configured(),
        "azure_key_mask": _mask_key(AZURE_KEY),
        "groq_configured": groq_configured(),
        "groq_model": GROQ_MODEL,
        "groq_key_mask": _mask_key(GROQ_KEY),
        "research_use_groq": RESEARCH_USE_GROQ,
    }


def probe_groq() -> dict[str, Any]:
    """Tiny live check — confirms the key currently in project `.env` works."""
    _refresh_keys()
    status = llm_status()
    if not GROQ_KEY:
        return {**status, "groq_ok": False, "error": "GROQ_API_KEY missing in project .env"}
    try:
        text = chat_groq(
            [{"role": "user", "content": 'Reply with exactly: {"ok":true}'}],
            temperature=0,
            max_tokens=30,
            json_mode=False,
            timeout=30.0,
        )
        return {**status, "groq_ok": True, "sample_chars": len(text or "")}
    except Exception as e:
        return {**status, "groq_ok": False, "error": str(e)[:300]}


def _azure_client():
    from openai import OpenAI
    return OpenAI(api_key=AZURE_KEY, base_url=AZURE_ENDPOINT)


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").lower()
    return any(x in m for x in ("gpt-5", "o1", "o3", "o4"))


def chat_groq(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    json_mode: bool = False,
    timeout: float = 90.0,
) -> str:
    """
    Groq-only chat — used for research analysis + LLM-as-judge (fast path).
    """
    _refresh_keys()
    if not GROQ_KEY:
        raise RuntimeError(
            f"GROQ_API_KEY not configured in {_ENV_PATH}. "
            "Save the key in that file (Ctrl+S), then retry."
        )
    from groq import Groq
    client = Groq(api_key=GROQ_KEY)
    use_model = model or GROQ_MODEL
    # gpt-oss models on Groq often break with response_format=json_object — prefer plain JSON text
    force_plain = json_mode and ("gpt-oss" in use_model or "qwen" in use_model)
    kwargs: dict[str, Any] = {
        "model": use_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    if json_mode and not force_plain:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e1:
        err = str(e1)
        if "invalid_api_key" in err.lower() or "401" in err:
            raise RuntimeError(
                f"Groq rejected the key in {_ENV_PATH} ({_mask_key(GROQ_KEY)}). "
                "Create a new key at https://console.groq.com/keys , paste it into that .env, "
                "SAVE the file, then open /api/llm-status?probe=1 to verify."
            ) from e1
        if json_mode:
            print(f"[Groq] json_mode failed ({e1}); retrying plain")
            kwargs.pop("response_format", None)
            kwargs["max_tokens"] = max(max_tokens, 1200)
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception:
                raise e1
        else:
            raise
    text = (resp.choices[0].message.content or "").strip()
    # Some groq reasoning models put text elsewhere or return blank content
    if not text:
        msg = resp.choices[0].message
        text = (
            getattr(msg, "reasoning", None)
            or getattr(msg, "reasoning_content", None)
            or ""
        )
        if isinstance(text, str):
            text = text.strip()
        else:
            text = ""
    # Fall back across stable Groq models if still empty / inaccessible
    if not text:
        for fallback_model in (
            "openai/gpt-oss-20b",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
        ):
            if fallback_model == use_model:
                continue
            print(f"[Groq] empty/unavailable from {use_model}; retrying {fallback_model}")
            try:
                fb = dict(kwargs)
                fb["model"] = fallback_model
                fb.pop("response_format", None)
                fb["max_tokens"] = max(max_tokens, 800)
                resp = client.chat.completions.create(**fb)
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    use_model = fallback_model
                    break
            except Exception as e_fb:
                print(f"[Groq] fallback {fallback_model} failed: {e_fb}")
                continue
    if not text:
        raise RuntimeError("Groq returned empty content")
    print(f"[Groq] OK model={use_model} key={_mask_key(GROQ_KEY)} chars={len(text)}")
    return text


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
    Chat completion — Azure OpenAI first (production default).
    Groq only if RESEARCH_USE_GROQ=1 or Azure is unavailable.
    """
    _refresh_keys()
    errors: list[str] = []
    use_model = model or AZURE_MODEL

    # 1) Azure OpenAI — primary
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

    # 2) Groq only when explicitly enabled (avoid daily rate-limit outages)
    if RESEARCH_USE_GROQ and GROQ_KEY:
        try:
            return chat_groq(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
                timeout=min(timeout, 120.0),
            )
        except Exception as e:
            errors.append(f"Groq: {e}")
            print(f"[Groq] failed: {e}")

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


# Log once at import which provider is active (never full secret)
print(
    f"[LLM] env={_ENV_PATH} azure={_mask_key(AZURE_KEY)} "
    f"groq_enabled={RESEARCH_USE_GROQ} model={AZURE_MODEL if AZURE_KEY else GROQ_MODEL}"
)
