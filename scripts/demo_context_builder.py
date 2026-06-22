"""
Demo: Context Builder — many memories in, bounded relevant context out.

Shows that agent.recall() returns only the most relevant memories within
a token budget, rather than dumping the entire stream history.

Usage::

    $env:WALRUSOS_USE_MOCKS = "1"
    python scripts/demo_context_builder.py
"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")


async def main() -> None:
    from walrusos import WalrusOS
    from walrusos.engine.token_budget import estimate_tokens

    runtime = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("my-research-project")
    agent = workspace.agent("Research")
    stream = agent.stream("context-demo")

    print("=" * 60)
    print("  WalrusOS Context Builder")
    print("  Many memories in. Bounded relevant context out.")
    print("=" * 60)
    print()

    # Publish a spread of memories on different topics
    print("[1] Publishing 12 memories across multiple topics...")
    memories = [
        ("OAuth 2.0 uses authorization code flow with PKCE", ["auth"]),
        ("JWT tokens should be short-lived, 15 min max", ["auth"]),
        ("The database uses PostgreSQL 16 with connection pooling", ["db"]),
        ("Redis caches session data with 1 hour TTL", ["db"]),
        ("Frontend is React 19 with server components", ["frontend"]),
        ("Decided to use refresh token rotation for security", ["auth", "decision"]),
        ("API rate limiting set to 100 req/min per user", ["api"]),
        ("Tailwind v4 for styling, no custom CSS", ["frontend"]),
        ("Bug: token refresh fails on concurrent requests", ["auth", "bug"]),
        ("Fixed concurrent refresh with optimistic locking", ["auth", "decision"]),
        ("Deployment uses Docker on AWS ECS", ["devops"]),
        ("Monitoring via Datadog with custom dashboards", ["devops"]),
    ]
    for content, tags in memories:
        await stream.append({"content": content}, tags=tags)
    print(f"  Published {len(memories)} memories")
    print()

    # Full timeline token count for comparison
    full_tl = await stream.timeline()
    full_tokens = sum(
        estimate_tokens(" ".join(str(v) for v in payload.values() if isinstance(v, str)))
        for _, payload in full_tl
    )
    print(f"  Full timeline: {len(full_tl)} events, ~{full_tokens} tokens total")
    print()

    # Now recall ONLY auth-related context
    print("[2] Query: 'what is our authentication and token strategy?'")
    print()
    detailed = await agent.recall_detailed(
        stream,
        "what is our authentication and token strategy?",
        max_tokens=400,
    )
    print(f"  Events considered: {detailed['events_considered']}")
    print(f"  Events included:   {detailed['events_included']}")
    print(f"  Token estimate:    ~{detailed['token_estimate']}")
    print(f"  Reduction:         {full_tokens} -> {detailed['token_estimate']} tokens"
          f" ({100 - detailed['token_estimate'] * 100 // max(full_tokens, 1)}% smaller)")
    print()
    print("  Assembled context:")
    print("  " + "-" * 56)
    for line in detailed["context"].split("\n\n"):
        print(f"  {line}")
    print()
    print("[3] Query: 'what is the database and caching setup?'")
    print()
    db_detail = await agent.recall_detailed(
        stream,
        "what is the database and caching setup?",
        max_tokens=400,
    )
    print(f"  Events included:   {db_detail['events_included']}")
    print(f"  Token estimate:    ~{db_detail['token_estimate']}")
    print()
    print("  Assembled context:")
    print("  " + "-" * 56)
    for line in db_detail["context"].split("\n\n"):
        print(f"  {line}")
    print()
    print("  Note: different queries surface different memories from the")
    print("  same stream. Auth vs DB queries return different context.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
