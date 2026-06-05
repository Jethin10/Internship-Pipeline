"""Model- and gateway-agnostic LLM access.

The rest of the codebase calls `complete(...)` and never knows the provider.
Swap models/gateways purely via config (Settings.llm_model / llm_api_base).
Built on LiteLLM, which speaks Claude, OpenAI, Gemini, local servers, etc.
"""
from __future__ import annotations

import json
from typing import Any

from piperline.config import Settings, get_settings


def complete(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    model: str | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str:
    """Return the assistant's text for a chat completion.

    `messages` is the standard [{"role": "user"|"system"|"assistant",
    "content": ...}] list. Set json_mode=True to request a JSON object back.
    """
    # Imported lazily so the package imports even before deps are installed.
    from litellm import completion

    s = settings or get_settings()

    kwargs: dict[str, Any] = {
        "model": model or s.llm_model,
        "messages": messages,
        "temperature": s.llm_temperature if temperature is None else temperature,
    }
    if s.llm_api_key:
        kwargs["api_key"] = s.llm_api_key
    if s.llm_api_base:
        kwargs["api_base"] = s.llm_api_base
        # Some gateways mishandle gzip: they echo a Content-Encoding header but
        # send uncompressed bodies, causing httpx to fail on decompression.
        # Requesting identity avoids the issue.
        kwargs.setdefault("extra_headers", {})
        kwargs["extra_headers"]["Accept-Encoding"] = "identity"
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = completion(**kwargs)
    msg = resp["choices"][0]["message"]
    content = msg.get("content") or msg.get("reasoning") or ""
    return content


def complete_json(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Like complete() but parses a JSON object response. Raises on bad JSON."""
    text = complete(
        messages,
        settings=settings,
        model=model,
        temperature=temperature,
        json_mode=True,
    )
    return json.loads(text)
