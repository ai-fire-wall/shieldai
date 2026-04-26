"""
LLM integration — thin async wrappers around each provider's API.
Swap providers without changing firewall.py.
"""

from __future__ import annotations

import asyncio
import httpx
from dataclasses import dataclass
from typing import Optional

from app.models.schemas import LLMProvider
from app.utils.config import get_settings
from app.utils.logger import get_logger

logger = get_logger("llm")
settings = get_settings()


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


# ── Provider implementations ──────────────────────────────────────────────────

async def _call_openai(
    prompt: str,
    model: str,
    system_prompt: Optional[str],
) -> LLMResponse:
    model = model or "gpt-4o-mini"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={"model": model, "messages": messages},
        )
        r.raise_for_status()
        data = r.json()

    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResponse(
        text=choice,
        model=model,
        provider="openai",
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
    )


async def _call_anthropic(
    prompt: str,
    model: str,
    system_prompt: Optional[str],
) -> LLMResponse:
    model = model or "claude-3-haiku-20240307"
    body: dict = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        body["system"] = system_prompt

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json=body,
        )
        r.raise_for_status()
        data = r.json()

    text = data["content"][0]["text"]
    usage = data.get("usage", {})
    return LLMResponse(
        text=text,
        model=model,
        provider="anthropic",
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )


async def _call_mock(
    prompt: str,
    model: str,
    system_prompt: Optional[str],
) -> LLMResponse:
    """
    Mock provider — returns a canned response without hitting any API.
    Useful for unit tests and demo environments.
    """
    await asyncio.sleep(0.05)   # simulate network latency
    return LLMResponse(
        text=(
            f"[MOCK RESPONSE] You said: '{prompt[:80]}'. "
            "This is a safe, sanitised reply from the mock LLM provider."
        ),
        model="mock-1.0",
        provider="mock",
        input_tokens=len(prompt.split()),
        output_tokens=20,
    )


# ── Public API ────────────────────────────────────────────────────────────────

_DISPATCH = {
    LLMProvider.OPENAI:    _call_openai,
    LLMProvider.ANTHROPIC: _call_anthropic,
    LLMProvider.MOCK:      _call_mock,
}


async def call_llm(
    *,
    prompt: str,
    provider: LLMProvider,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> LLMResponse:
    """
    Route a prompt to the requested LLM provider and return its response.
    Raises httpx.HTTPStatusError on provider API errors.
    """
    handler = _DISPATCH[provider]
    logger.debug(f"Calling {provider} with model={model or 'default'}")
    return await handler(prompt, model or "", system_prompt)
