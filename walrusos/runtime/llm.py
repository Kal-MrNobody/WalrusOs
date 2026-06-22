"""
LLM Provider abstraction for WalrusOS autonomous runtime.

Providers:
  StubProvider      — deterministic, no API key (for testing)
  GeminiProvider    — Google Gemini via REST API
  AnthropicProvider — Anthropic Messages API

Usage::

    from walrusos.runtime.llm import get_provider

    llm = get_provider("gemini", api_key="...", model="gemini-2.5-flash")
    response = await llm.generate("Write a poem about walruses.")
"""
from __future__ import annotations

import os
import re
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface every LLM backend must implement."""

    async def generate(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str: ...


class StubProvider:
    """Deterministic provider for testing — never makes network calls."""

    async def generate(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        name_match = re.search(r"You are (.+?)\.", prompt)
        agent_name = name_match.group(1) if name_match else "Agent"

        goal_match = re.search(r"Goal: (.+)", prompt)
        goal = goal_match.group(1)[:60] if goal_match else prompt[:60]

        return f"[{agent_name}] Contributing to: {goal}"


class GeminiProvider:
    """Calls the Google Gemini generateContent REST endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Pass api_key= or set GEMINI_API_KEY env var."
            )
        self.model = model
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        import httpx

        url = f"{self._base_url}/models/{self.model}:generateContent"
        generation_config: dict = {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3 if json_mode else 0.7,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, params={"key": self.api_key})
            resp.raise_for_status()
            data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


class AnthropicProvider:
    """Calls the Anthropic Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Pass api_key= or set ANTHROPIC_API_KEY env var."
            )
        self.model = model

    async def generate(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        import httpx

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["content"][0]["text"]


def get_provider(
    provider: str = "auto",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMProvider:
    """
    Return an LLMProvider instance.

    provider:
      "auto"      — GEMINI_API_KEY → gemini, ANTHROPIC_API_KEY → anthropic, else stub
      "gemini"    — GeminiProvider
      "anthropic" — AnthropicProvider
      "stub"      — StubProvider (testing)
    """
    if provider == "stub":
        return StubProvider()

    if provider == "gemini":
        return GeminiProvider(api_key=api_key, model=model or "gemini-2.5-flash")

    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or "claude-sonnet-4-6")

    if provider == "auto":
        if os.environ.get("GEMINI_API_KEY") or api_key:
            return GeminiProvider(api_key=api_key, model=model or "gemini-2.5-flash")
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider(model=model or "claude-sonnet-4-6")
        return StubProvider()

    raise ValueError(
        f"Unknown provider {provider!r}. Choose: auto, gemini, anthropic, stub."
    )
