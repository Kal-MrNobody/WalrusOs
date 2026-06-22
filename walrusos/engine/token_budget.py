"""
Token budgeting — dependency-free estimation and allocation.
"""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token, conservative)."""
    return max(1, len(text) // 4)


class TokenBudget:
    """Track remaining token capacity and gate additions."""

    def __init__(self, max_tokens: int = 1500) -> None:
        self.max_tokens = max_tokens
        self.used = 0

    def can_fit(self, text: str) -> bool:
        return self.used + estimate_tokens(text) <= self.max_tokens

    def add(self, text: str) -> bool:
        cost = estimate_tokens(text)
        if self.used + cost <= self.max_tokens:
            self.used += cost
            return True
        return False

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used
