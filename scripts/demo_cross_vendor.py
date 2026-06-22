"""
demo_cross_vendor.py — CROSS-VENDOR AGENT COLLABORATION

The flagship: Anthropic's Claude Desktop (via live MCP) and Google's Gemini
(two agents) collaborate on ONE shared memory stream. Each side reads what
the other has written and explicitly builds on it. Every contribution is
signed, anchored on Sui testnet, and stored on Walrus.

═══════════════════════════════════════════════════════════════════════
WORKSPACE NOTE
═══════════════════════════════════════════════════════════════════════
The live Claude Desktop MCP session runs on workspace "default". For this
demo to share a stream with Claude Desktop, the two Gemini agents MUST
also use workspace_name="default". The shared stream is
"cross-vendor-collab".

This is the intentional opposite of demo_full_workflow.py, which uses
workspace "workflow-proof" specifically to ISOLATE its agents from the
live MCP session. There, isolation prevents collision. Here, sharing IS
the point — we want both vendors writing to the same surface.
═══════════════════════════════════════════════════════════════════════

USAGE

  Bridge + dashboard up first:
    Terminal 1: $env:WALRUSOS_USE_MOCKS="0"
                python -m uvicorn dashboard.walrusos_bridge:app --port 8787
    Terminal 2: cd dashboard ; npm run dev
    Open http://localhost:3000

  Auto mode (no human needed — script seeds the chain):
    $env:WALRUSOS_USE_MOCKS="0"
    python scripts/demo_cross_vendor.py --auto

  Live mode (real cross-vendor — Claude Desktop kicks off the chain):
    $env:WALRUSOS_USE_MOCKS="0"
    python scripts/demo_cross_vendor.py --live
    Then in Claude Desktop, ask it to call memory_append with stream
    "cross-vendor-collab".

FLOW

  1. Connect Gemini Analyst (capabilities: analysis, research) and
     Gemini Critic (capabilities: review, critique) on workspace "default".
  2. Both subscribe to the "cross-vendor-collab" stream.
  3. Seed:
       --auto: a third agent ("Coordinator") writes the kickoff memory.
       --live: the script waits for Claude Desktop to write the kickoff.
  4. Analyst's subscription fires. Analyst recalls the stream, reads the
     seed, and writes an analysis that explicitly references it.
  5. Analyst's write fires Critic's subscription. Critic recalls, reads
     Analyst's analysis, and writes a critique that explicitly references it.
  6. Print the full chain (who wrote, what they read, what they added).
  7. Save scripts/last_cross_vendor_proof.txt with blob IDs + Sui digests.
  8. Hold agents online 60s so the dashboard captures them.

The interleaved Live Activity feed on the dashboard — claude-code and gemini
badges alternating on one stream — is the visible proof.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Surface anchor failures (and other warnings) on stderr. Without this, the
# WARNING / INFO logger calls inside the adapter are silenced by Python's
# default "WARNING-on-root-without-handler" behaviour, which makes a broken
# anchor path look like silent success.
import logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
# Quiet down the noisy clients
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


WORKSPACE_NAME = "default"  # MUST match Claude Desktop's MCP workspace
STREAM_NAME    = "cross-vendor-collab"
BRIDGE_URL     = os.environ.get("WALRUSOS_BRIDGE_URL", "http://localhost:8787")

# Reaction caps to terminate the chain cleanly
CHAIN_TIMEOUT_SECONDS = 180
LIVE_POLL_INTERVAL    = 2.0
LIVE_TRIGGER_TIMEOUT  = 240


async def _bridge_running() -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{BRIDGE_URL}/agent/presence")
            return r.status_code == 200
    except Exception:
        return False


async def _react_as(
    reactor,
    stream,
    triggering_event,
    triggering_payload,
    role_description: str,
    role_directive: str,
    llm,
) -> tuple[Any, dict, str]:
    """Common reaction path: recall, generate, write. Returns (event, recall_result, response_text).

    The reacting agent ALWAYS calls recall_detailed first so its output is
    grounded in everything the team has written so far — including the prior
    vendor's contribution.
    """
    triggering_author  = triggering_payload.get("author") or "the other agent"
    triggering_content = (
        triggering_payload.get("content")
        or triggering_payload.get("text")
        or str(triggering_payload)
    )[:600]

    recall_query = f"{role_description} {triggering_content}".strip()
    recall_result = await reactor.recall_detailed(
        stream, recall_query, max_tokens=1200,
    )

    prompt = (
        f"You are {reactor.agent_name}, the {role_description}.\n\n"
        f"You just received this memory written by {triggering_author}:\n"
        f"  {triggering_content}\n\n"
        f"Relevant prior team memory (recalled from the shared stream):\n"
        f"{recall_result.get('context', '') or '(no prior memory found — this is an early write)'}\n\n"
        f"{role_directive}\n"
        f"Explicitly reference {triggering_author}'s contribution in your "
        f"response so a reader can see you built on it."
    )

    if llm is not None:
        try:
            response = await llm.generate(prompt, max_tokens=400)
        except Exception as exc:
            response = (
                f"[{reactor.agent_name}] (LLM error: {exc.__class__.__name__}) "
                f"Building on {triggering_author}: would normally analyze the prior memory here."
            )
    else:
        response = (
            f"[{reactor.agent_name}] {role_description}: building on "
            f"{triggering_author}'s contribution about "
            f"{triggering_content[:80]}…"
        )

    event = await stream.append(
        {
            "content":     response,
            "reacted_to":  getattr(triggering_event, "event_id", ""),
            "reactor":     reactor.agent_name,
            "role":        role_description,
        },
        memory_type="observation",
        tags=["cross-vendor", role_description.split()[0].lower()],
        importance=0.8,
    )
    return event, recall_result, response


def _print_chain_step(step_num: int, agent_name: str, framework: str,
                       recall: dict, response: str) -> None:
    print()
    print(f"  ── Step {step_num}: {agent_name} ({framework}) ──")
    print(f"     Recalled {recall.get('events_included', 0)} of "
          f"{recall.get('events_considered', 0)} memories "
          f"(~{recall.get('token_estimate', 0)} tokens)")
    if recall.get("context"):
        ctx_preview = recall["context"].replace("\n", " ")[:140]
        print(f"     Recall preview: {ctx_preview}…")
    snippet = response.replace("\n", " ")[:240]
    print(f"     Contribution: {snippet}…")


async def _save_proof(stream, agents_in_chain: list[Any], goal: str,
                       since_iso: Optional[str] = None) -> Path:
    """Build last_cross_vendor_proof.txt from the shared stream's timeline.

    Joins each timeline event against the protocol_events SQLite table to
    recover the real `transaction_digest` — the SDK's MemoryEvent projection
    used by stream.timeline() does NOT carry the digest (which lives only on
    the ProtocolEvent / protocol_events row). Without this join the proof
    file shows blob URLs but `(no anchor)` for every event even when anchors
    landed.

    `since_iso`: when given, only events written at or after this timestamp
    appear in the proof. Lets the demo emit a clean "just this run" file
    instead of every event ever written to the shared stream.
    """
    timeline = await stream.timeline(include_metadata=True)
    proof_path = Path(__file__).parent / "last_cross_vendor_proof.txt"

    # ── Join against protocol_events for the real tx_digest AND real
    #    persisted timestamp. MemoryEvent.timestamp is a synthetic property
    #    that returns datetime.now() on every read, so it can't be used to
    #    filter to a particular run.
    digests_by_event_id: dict[str, str] = {}
    timestamps_by_event_id: dict[str, str] = {}
    try:
        import sqlite3 as _sql
        db = Path.home() / ".walrusos" / "walrusos.db"
        if db.exists():
            con = _sql.connect(str(db))
            con.row_factory = _sql.Row
            event_ids = [getattr(ev, "event_id", "") or getattr(ev, "id", "")
                         for ev, _ in timeline]
            event_ids = [eid for eid in event_ids if eid]
            if event_ids:
                placeholders = ",".join("?" * len(event_ids))
                rows = con.execute(
                    f"SELECT event_id, transaction_digest, timestamp "
                    f"FROM protocol_events WHERE event_id IN ({placeholders})",
                    event_ids,
                ).fetchall()
                for r in rows:
                    if r["transaction_digest"]:
                        digests_by_event_id[r["event_id"]] = r["transaction_digest"]
                    if r["timestamp"]:
                        timestamps_by_event_id[r["event_id"]] = r["timestamp"]
            con.close()
    except Exception as exc:
        # Don't kill proof generation if the lookup fails — just show "(no anchor)"
        print(f"[proof] protocol_events lookup failed: {exc.__class__.__name__}: {exc}")

    # ── Filter to "since" if requested, using the PERSISTED timestamp from
    #    protocol_events (MemoryEvent.timestamp is synthetic = now()).
    if since_iso:
        def _real_ts(pair) -> str:
            ev, _ = pair
            eid = getattr(ev, "event_id", "") or getattr(ev, "id", "")
            return timestamps_by_event_id.get(eid, "")
        timeline = [pair for pair in timeline if _real_ts(pair) >= since_iso]

    lines = ["=" * 72]
    lines.append("  WALRUSOS CROSS-VENDOR COLLABORATION PROOF")
    lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"  Workspace: {WORKSPACE_NAME} (shared with Claude Desktop MCP)")
    lines.append(f"  Stream:    {STREAM_NAME}")
    lines.append(f"  Goal:      {goal}")
    if since_iso:
        lines.append(f"  Filter:    only events written since {since_iso}")
    lines.append("=" * 72)
    lines.append("")

    anchored = 0
    for i, (ev, payload) in enumerate(timeline, 1):
        blob_id   = getattr(ev, "content_blob_id", "") or getattr(ev, "blob_id", "")
        event_id  = getattr(ev, "event_id", "") or getattr(ev, "id", "")
        # Prefer the persisted tx_digest from protocol_events; fall back to
        # whatever the SDK event carried (kept for safety; usually empty).
        tx_digest = (
            digests_by_event_id.get(event_id, "")
            or (getattr(ev, "transaction_digest", "") or "")
        )
        if tx_digest:
            anchored += 1
        agent_id  = getattr(ev, "agent_id", "")
        author    = payload.get("author") or agent_id
        walrus = (f"https://aggregator.walrus-testnet.walrus.space/v1/blobs/{blob_id}"
                  if blob_id else "(no blob)")
        sui    = (f"https://suiscan.xyz/testnet/tx/{tx_digest}"
                  if tx_digest else "(no anchor)")
        lines.append(f"Event {i}: {author}")
        lines.append(f"  event_id:        {event_id}")
        lines.append(f"  agent_id:        {agent_id}")
        lines.append(f"  walrus_blob:     {blob_id or '(none)'}")
        lines.append(f"  walrus_url:      {walrus}")
        lines.append(f"  sui_tx_digest:   {tx_digest or '(none)'}")
        lines.append(f"  sui_url:         {sui}")
        lines.append("")

    lines.append("-" * 72)
    lines.append(f"Events shown:  {len(timeline)}")
    lines.append(f"Anchored on Sui: {anchored} of {len(timeline)}")
    lines.append("Verification: paste each walrus_url + sui_url to verify on-chain.")
    lines.append("=" * 72)
    proof_path.write_text("\n".join(lines), encoding="utf-8")
    return proof_path


async def main(mode: str) -> None:
    from walrusos import WalrusOS
    from walrusos.runtime.llm import GeminiProvider, get_provider

    print("=" * 72)
    print("  WalrusOS — Cross-Vendor Agent Collaboration")
    print("  Anthropic (Claude Desktop) + Google (Gemini) sharing memory.")
    print(f"  Mode: {mode.upper()}")
    print("=" * 72)
    print()

    use_mocks = os.environ.get("WALRUSOS_USE_MOCKS", "0") == "1"
    api_key   = os.environ.get("GEMINI_API_KEY")

    print(f"[pre-flight] WALRUSOS_USE_MOCKS = {use_mocks}")
    print(f"[pre-flight] Workspace:          {WORKSPACE_NAME!r} (shared with Claude Desktop)")
    print(f"[pre-flight] Stream:             {STREAM_NAME!r}")
    print(f"[pre-flight] Bridge:             {BRIDGE_URL}")
    bridge_ok = await _bridge_running()
    print(f"[pre-flight] Bridge reachable:   {bridge_ok}")
    if api_key:
        print(f"[pre-flight] GEMINI_API_KEY:    set ({api_key[:6]}…)")
    else:
        print("[pre-flight] GEMINI_API_KEY:    NOT set — will use StubProvider")
    print()

    runtime   = WalrusOS(use_mocks=use_mocks)
    workspace = runtime.workspace(WORKSPACE_NAME)
    print(f"[workspace] {WORKSPACE_NAME!r}  id={workspace.workspace_id}")
    print()

    # ── Connect the two Gemini agents ────────────────────────────────────────
    analyst = workspace.agent("Gemini Analyst")
    critic  = workspace.agent("Gemini Critic")

    print("[connect] Gemini Analyst — analysis, research")
    await analyst.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[{"name": "analysis"}, {"name": "research"}],
    )
    print("[connect] Gemini Critic  — review, critique")
    await critic.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[{"name": "review"}, {"name": "critique"}],
    )
    print()

    # ── Per-agent stream bindings — same stream_id, different `_bound_agent`
    # Stream IDs are deterministic from workspace+name, so both bindings target
    # the SAME on-chain stream — but each agent writes via its OWN identity. If
    # we shared one binding, every reactor's append() would be attributed to
    # whichever agent created the binding, and the proof file would list one
    # author for every event.
    analyst_stream = analyst.stream(STREAM_NAME)
    critic_stream  = critic.stream(STREAM_NAME)
    stream         = analyst_stream  # read view used by _save_proof + recall
    assert analyst_stream.stream_id == critic_stream.stream_id
    print(f"[stream]   {STREAM_NAME!r}  id={stream.stream_id}")
    print()

    # ── LLM ─────────────────────────────────────────────────────────────────
    if api_key:
        llm = GeminiProvider(api_key=api_key, model="gemini-2.5-flash")
        print(f"[llm] GeminiProvider(gemini-2.5-flash) — real API calls")
    else:
        llm = get_provider("stub")
        print(f"[llm] StubProvider — set GEMINI_API_KEY for real Gemini calls")
    print()

    # ── Reactive subscriptions ──────────────────────────────────────────────
    # Each callback skips self-writes (to avoid infinite loops) and gates on a
    # reaction cap. The chain terminates after Analyst → Critic.
    analyst_done = asyncio.Event()
    critic_done  = asyncio.Event()
    chain: list[dict] = []

    async def analyst_callback(event) -> None:
        if analyst_done.is_set():
            return
        if str(getattr(event, "agent_id", "")) == analyst._agent_id_str:
            return  # skip own writes (prevent loop)
        if str(getattr(event, "agent_id", "")) == critic._agent_id_str:
            return  # don't react backwards to the critic
        try:
            # Read the triggering payload from the stream
            payload = {}
            try:
                if hasattr(stream._memory, "read"):
                    payload = await stream._memory.read(event.event_id) or {}
            except Exception:
                payload = {}

            print()
            print(f"[event] Analyst received memory from "
                  f"agent_id={getattr(event, 'agent_id', '?')[:8]}…")
            await analyst.set_status("thinking")

            event2, recall, response = await _react_as(
                analyst, analyst_stream, event, payload,
                role_description="research analyst",
                role_directive=(
                    "Write a 2-4 sentence analysis of the new memory, drawing on "
                    "any related prior memory."
                ),
                llm=llm,
            )
            await analyst.set_status("idle")
            chain.append({
                "agent_name":   analyst.agent_name,
                "framework":    "gemini",
                "recall":       recall,
                "response":     response,
                "event_id":     getattr(event2, "event_id", ""),
                "triggered_by": getattr(event, "event_id", ""),
            })
            analyst_done.set()
        except Exception as exc:
            print(f"[error] analyst_callback: {exc.__class__.__name__}: {exc}")

    async def critic_callback(event) -> None:
        if critic_done.is_set():
            return
        if str(getattr(event, "agent_id", "")) == critic._agent_id_str:
            return  # skip own writes
        # Critic reacts ONLY to the Analyst's writes — keeps the chain linear.
        if str(getattr(event, "agent_id", "")) != analyst._agent_id_str:
            return
        try:
            payload = {}
            try:
                if hasattr(stream._memory, "read"):
                    payload = await stream._memory.read(event.event_id) or {}
            except Exception:
                payload = {}

            print()
            print(f"[event] Critic received Analyst's write — reacting…")
            await critic.set_status("thinking")

            event2, recall, response = await _react_as(
                critic, critic_stream, event, payload,
                role_description="critical reviewer",
                role_directive=(
                    "Write a 2-4 sentence critique or refinement of the Analyst's "
                    "contribution. Identify one specific assumption to test or "
                    "one specific risk to flag."
                ),
                llm=llm,
            )
            await critic.set_status("idle")
            chain.append({
                "agent_name":   critic.agent_name,
                "framework":    "gemini",
                "recall":       recall,
                "response":     response,
                "event_id":     getattr(event2, "event_id", ""),
                "triggered_by": getattr(event, "event_id", ""),
            })
            critic_done.set()
        except Exception as exc:
            print(f"[error] critic_callback: {exc.__class__.__name__}: {exc}")

    # Pin the run-start timestamp now so the proof file can filter to events
    # written during THIS demo run. The shared stream "cross-vendor-collab"
    # also holds writes from prior runs + any concurrent Claude Desktop writes;
    # without the filter the proof file would mix old (pre-fix, no-anchor)
    # rows with this run's actual artifacts.
    run_start_iso = datetime.now(timezone.utc).isoformat()
    print(f"[run-start] {run_start_iso}  (proof file will filter to events ≥ this)")

    print("[subscribe] Analyst and Critic both subscribing to the stream…")
    await analyst.subscribe(analyst_stream, analyst_callback)
    await critic.subscribe(critic_stream, critic_callback)
    print()

    # ── Kickoff path: --auto seeds; --live waits for Claude Desktop ─────────
    goal: str = ""
    if mode == "auto":
        coordinator = workspace.agent("Coordinator")
        # Coordinator goes online briefly just to write the seed
        await coordinator.go_online(
            framework="custom",
            bridge_url=BRIDGE_URL,
            capabilities=[{"name": "planning"}],
        )
        seed_stream = coordinator.stream(STREAM_NAME)
        goal = (
            "Evaluate whether end-to-end encrypted memory streams can scale "
            "to support 10k+ concurrent AI agents while preserving auditability."
        )
        print(f"[seed] Coordinator writing the kickoff memory to {STREAM_NAME!r}…")
        seed_event = await seed_stream.append(
            {
                "content": (
                    "Kickoff: " + goal + " "
                    "Initial concern: end-to-end encryption may conflict with "
                    "the auditability requirement. Please analyse and critique."
                ),
                "role": "seed",
            },
            memory_type="observation",
            tags=["cross-vendor", "seed"],
            importance=0.9,
        )
        print(f"        seed event id: {getattr(seed_event, 'event_id', '')[:16]}…")
        await coordinator.go_offline()

    elif mode == "live":
        print()
        print("[live] Waiting for Claude Desktop to call memory_append on stream")
        print(f"       {STREAM_NAME!r}.")
        print()
        print("       In Claude Desktop, ask it something like:")
        print(f'         "Use the walrusos memory_append tool to save to stream')
        print(f'          {STREAM_NAME!r}: <a finding to kick off cross-vendor discussion>"')
        print()
        print(f"       Polling every {LIVE_POLL_INTERVAL:.0f}s for up to "
              f"{LIVE_TRIGGER_TIMEOUT}s…")
        print()

        # Snapshot current timeline IDs so we only react to NEW writes
        initial_tl = await stream.timeline(include_metadata=True)
        seen_ids = {ev.event_id for ev, _ in initial_tl}
        print(f"       (current stream has {len(seen_ids)} prior events; "
              f"waiting for a new external write)")

        trigger_deadline = time.time() + LIVE_TRIGGER_TIMEOUT
        trigger_event = None
        trigger_payload: dict = {}
        while time.time() < trigger_deadline and trigger_event is None:
            await asyncio.sleep(LIVE_POLL_INTERVAL)
            tl = await stream.timeline(include_metadata=True)
            for ev, payload in tl:
                if ev.event_id in seen_ids:
                    continue
                seen_ids.add(ev.event_id)
                agent_id = getattr(ev, "agent_id", "") or payload.get("agent_id", "")
                # Skip our own Gemini agents — wait for a true external write
                if agent_id in (analyst._agent_id_str, critic._agent_id_str):
                    continue
                trigger_event   = ev
                trigger_payload = payload
                break

        if trigger_event is None:
            print(f"[live] Timed out after {LIVE_TRIGGER_TIMEOUT}s "
                  f"waiting for Claude Desktop. Try --auto for a script-driven run.")
            await analyst.go_offline()
            await critic.go_offline()
            return

        author_preview = trigger_payload.get("author") or getattr(trigger_event, "agent_id", "")
        print()
        print(f"[live] External write detected from {author_preview!r} — "
              f"firing Analyst…")
        # Manually invoke Analyst (cross-process subscriptions don't deliver here)
        await analyst_callback(trigger_event)
        goal = trigger_payload.get("content", "(triggered by external write)")
    else:
        raise SystemExit(f"Unknown mode: {mode}")

    # ── Wait for the chain to complete ───────────────────────────────────────
    try:
        await asyncio.wait_for(critic_done.wait(), timeout=CHAIN_TIMEOUT_SECONDS)
        print()
        print("[chain] Critic done. Cross-vendor chain complete.")
    except asyncio.TimeoutError:
        print()
        print(f"[chain] Timed out after {CHAIN_TIMEOUT_SECONDS}s waiting for chain "
              "to complete. Saving whatever was written so far.")

    # ── Print the chain ─────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  CHAIN SUMMARY")
    print("=" * 72)
    for i, step in enumerate(chain, 1):
        _print_chain_step(
            i, step["agent_name"], step["framework"], step["recall"], step["response"],
        )

    # ── Proof file (only this run's events) ─────────────────────────────────
    proof_path = await _save_proof(
        stream, [analyst, critic], goal, since_iso=run_start_iso,
    )
    print()
    print(f"[proof] Saved: {proof_path}")
    # Quick summary so the operator sees anchored counts at a glance
    try:
        lines = proof_path.read_text(encoding="utf-8").splitlines()
        for ln in lines:
            if ln.startswith(("Events shown:", "Anchored on Sui:")):
                print(f"        {ln}")
    except Exception:
        pass
    print()

    # ── Hold for dashboard ──────────────────────────────────────────────────
    print(f"[done] Keeping agents online for 60s for the dashboard…")
    print("       In Claude Desktop you can now call memory_search on the")
    print(f"       stream {STREAM_NAME!r} to see the Gemini contributions —")
    print("       bidirectional cross-vendor memory sharing.")
    try:
        await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("       Skip requested.")
    print()

    # ── Clean shutdown ───────────────────────────────────────────────────────
    print("[shutdown] Disconnecting…")
    try:
        await analyst.unsubscribe(analyst_stream)
    except Exception:
        pass
    try:
        await critic.unsubscribe(critic_stream)
    except Exception:
        pass
    await analyst.go_offline()
    await critic.go_offline()

    print()
    print("=" * 72)
    print(f"  Done. Chain steps: {len(chain)}")
    print(f"  Workspace: {WORKSPACE_NAME!r}  Stream: {STREAM_NAME!r}")
    print(f"  Proof file: {proof_path.name}")
    print("=" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cross-vendor agent collaboration demo (Anthropic + Google)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--auto", action="store_true",
                       help="Script seeds the first memory; no human needed.")
    group.add_argument("--live", action="store_true",
                       help="Wait for Claude Desktop (real Anthropic) to seed.")
    args = parser.parse_args()
    mode = "auto" if args.auto else "live"

    try:
        asyncio.run(main(mode))
    except KeyboardInterrupt:
        print("\n[stop] interrupted")
        sys.exit(0)
