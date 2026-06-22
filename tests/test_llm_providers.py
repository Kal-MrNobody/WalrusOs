"""
Tests for Sprint 5 — LLM Provider abstraction.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_llm_providers.py -v
"""
from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")
# Make sure no real API keys bleed in during tests
os.environ.pop("GEMINI_API_KEY",    None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from walrusos.runtime.llm import (
    AnthropicProvider,
    GeminiProvider,
    LLMProvider,
    StubProvider,
    get_provider,
)


# ── StubProvider ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stub_provider_returns_string() -> None:
    """StubProvider.generate() always returns a non-empty string."""
    stub = StubProvider()
    result = await stub.generate("Some prompt")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_stub_provider_extracts_agent_name() -> None:
    """StubProvider includes the agent name extracted from the prompt."""
    stub = StubProvider()
    prompt = "You are Alice.\n\nGoal: Write unit tests.\n\nYour contribution:"
    result = await stub.generate(prompt)
    assert "Alice" in result


# ── get_provider factory ─────────────────────────────────────────────────────

def test_get_provider_stub() -> None:
    """get_provider('stub') always returns a StubProvider."""
    provider = get_provider("stub")
    assert isinstance(provider, StubProvider)


def test_get_provider_auto_no_keys() -> None:
    """get_provider('auto') falls back to StubProvider when no API keys are set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GEMINI_API_KEY",    None)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        provider = get_provider("auto")
    assert isinstance(provider, StubProvider)


def test_get_provider_auto_with_gemini_key() -> None:
    """get_provider('auto') selects GeminiProvider when GEMINI_API_KEY is set."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-gemini-key"}):
        provider = get_provider("auto")
    assert isinstance(provider, GeminiProvider)


def test_gemini_provider_requires_key() -> None:
    """GeminiProvider raises ValueError when no API key is available."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GEMINI_API_KEY", None)
        with pytest.raises(ValueError, match="Gemini API key required"):
            GeminiProvider()


def test_anthropic_provider_requires_key() -> None:
    """AnthropicProvider raises ValueError when no API key is available."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with pytest.raises(ValueError, match="Anthropic API key required"):
            AnthropicProvider()


def test_get_provider_unknown() -> None:
    """get_provider() raises ValueError for unknown provider names."""
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("openai-gpt-99")


# ── LLMProvider Protocol ─────────────────────────────────────────────────────

def test_stub_satisfies_protocol() -> None:
    """StubProvider satisfies the LLMProvider structural protocol."""
    stub = StubProvider()
    assert isinstance(stub, LLMProvider)


# ── Integration with workspace.run() ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_workspace_run_with_llm_provider() -> None:
    """workspace.run() with a StubProvider writes events and returns RunResult."""
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("test-llm-run")
    alice     = workspace.agent("Alice")
    bob       = workspace.agent("Bob")

    stub = StubProvider()
    result = await workspace.run(
        goal="Summarise the key ideas in the WalrusOS whitepaper.",
        agents=[alice, bob],
        max_rounds=1,
        llm=stub,
    )

    assert result.goal.startswith("Summarise")
    assert result.rounds_completed >= 1
    assert len(result.events) >= 1
    assert isinstance(result.final_summary, str)


@pytest.mark.asyncio
async def test_workspace_run_llm_overrides_stub() -> None:
    """A custom LLM provider's response appears in final_summary."""
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("test-custom-llm")
    agent     = workspace.agent("TestAgent")

    class CustomLLM:
        async def generate(self, prompt: str, max_tokens: int = 500) -> str:
            return "CUSTOM LLM RESPONSE"

    result = await workspace.run(
        goal="Test custom LLM.",
        agents=[agent],
        max_rounds=1,
        llm=CustomLLM(),
    )

    assert "CUSTOM LLM RESPONSE" in result.final_summary


@pytest.mark.asyncio
async def test_workspace_run_on_event_overrides_llm() -> None:
    """on_event callback takes priority over llm when both are provided."""
    from walrusos import WalrusOS

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("test-priority")
    agent     = workspace.agent("PriorityAgent")

    class ShouldNotBeCalled:
        async def generate(self, prompt: str, max_tokens: int = 500) -> str:
            raise AssertionError("LLM was called but on_event should have priority")

    callback_called = {"count": 0}

    def my_callback(agt: Any, prompt: str, context: str) -> str:
        callback_called["count"] += 1
        return "ON_EVENT_RESPONSE"

    result = await workspace.run(
        goal="Priority test.",
        agents=[agent],
        max_rounds=1,
        on_event=my_callback,
        llm=ShouldNotBeCalled(),
    )

    assert callback_called["count"] >= 1
    assert "ON_EVENT_RESPONSE" in result.final_summary
