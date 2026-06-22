"""
demo_full_workflow.py — END-TO-END MULTI-AGENT WORKFLOW

Four Gemini-backed agents autonomously coordinate on one developer goal,
writing real signed memory events to Walrus and anchoring them on Sui
testnet. Each event is independently verifiable by pasting its blob ID
into the Walrus aggregator and its transaction digest into Sui Explorer.

The four agents:
  Research  — research, analysis, summarization
  Trading   — market_analysis, risk_assessment  (ANALYSIS ONLY — see below)
  Coding    — code_generation, code_review, debugging
  Chief     — planning, synthesis, decision_making

═══════════════════════════════════════════════════════════════════════
TRADING AGENT SAFETY — ANALYSIS-ONLY, NEVER EXECUTES
═══════════════════════════════════════════════════════════════════════
The Trading Agent in this demo is a SIMULATED RISK ANALYST. It produces
WRITTEN ANALYSIS stored as memory events. It is wired with:
  - capabilities limited to market_analysis and risk_assessment
  - an EMPTY tools list — no exchange clients, no order APIs, no transfer
  - a hardcoded prompt frame that asks for "hypothetical analysis for
    discussion only — do not produce actionable trade instructions"
It does NOT and CANNOT:
  - call an exchange
  - place an order
  - move funds
  - emit actionable trade instructions
Its only output is written analysis. Even if a future change widened its
capabilities, the empty tools list and the prompt frame are belt-and-
suspenders. See tests/test_full_workflow.py::test_trading_agent_is_
analysis_only for the enforced constraint.
═══════════════════════════════════════════════════════════════════════

RUN INSTRUCTIONS

  # Terminal 1 — bridge (real mode):
  #   $env:WALRUSOS_USE_MOCKS="0"
  #   python -m uvicorn dashboard.walrusos_bridge:app --port 8787
  # Terminal 2 — dashboard:
  #   cd dashboard ; npm run dev
  # Terminal 3 — the workflow (real Gemini, real Walrus, real Sui):
  #   $env:WALRUSOS_USE_MOCKS="0"
  #   # GEMINI_API_KEY is loaded from .env via python-dotenv
  #   python scripts/demo_full_workflow.py
  # Open http://localhost:3000 and watch all 5 agents work:
  #   - the 4 Gemini agents from this script
  #   - the live Claude Desktop MCP agent (if connected)

The 4 workflow agents register on workspace_name="workflow-proof" — a
DIFFERENT workspace from the live Claude Desktop session ("default") so
this script CANNOT collide with the live MCP session. They report to
the same bridge on :8787 so both appear in the dashboard's Connected
Agents panel.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

# Belt-and-suspenders dotenv load — explicit path, override=True so any
# prior shell env doesn't mask the .env on the user's machine.
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# Hypothetical-analysis frame for the Trading agent's prompt (see safety
# section in the module docstring). This is a defence-in-depth measure on
# top of the empty tools list + capability whitelist.
TRADING_HYPOTHETICAL_FRAME = (
    "IMPORTANT: This is HYPOTHETICAL analysis for discussion only. "
    "Do not produce actionable trade instructions, do not name specific "
    "tickers to buy or sell, and do not recommend moving funds. Frame your "
    "output as written risk analysis a human reviewer would weigh."
)

WORKSPACE_NAME = "workflow-proof"
BRIDGE_URL     = os.environ.get("WALRUSOS_BRIDGE_URL", "http://localhost:8787")


async def _bridge_running() -> bool:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{BRIDGE_URL}/agent/presence")
            return r.status_code == 200
    except Exception:
        return False


async def _connect_team(workspace) -> dict:
    """Spin up the 4-agent team. Returns a name→AgentClient map."""
    research = workspace.agent("Research")
    trading  = workspace.agent("Trading")
    coding   = workspace.agent("Coding")
    chief    = workspace.agent("Chief")

    print("[connect] Research  (gemini) — research, analysis, summarization")
    await research.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[
            {"name": "research"},
            {"name": "analysis"},
            {"name": "summarization"},
        ],
    )

    print("[connect] Trading   (gemini) — market_analysis, risk_assessment  "
          "[ANALYSIS-ONLY, no execution]")
    await trading.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[
            {"name": "market_analysis"},
            {"name": "risk_assessment"},
        ],
        tools=[],  # SAFETY: empty tools list — no exchange API, no orders
    )

    print("[connect] Coding    (gemini) — code_generation, code_review, debugging")
    await coding.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[
            {"name": "code_generation"},
            {"name": "code_review"},
            {"name": "debugging"},
        ],
    )

    print("[connect] Chief     (gemini) — planning, synthesis, decision_making")
    await chief.go_online(
        framework="gemini",
        bridge_url=BRIDGE_URL,
        capabilities=[
            {"name": "planning"},
            {"name": "synthesis"},
            {"name": "decision_making"},
        ],
    )

    return {
        "Research": research,
        "Trading":  trading,
        "Coding":   coding,
        "Chief":    chief,
    }


async def main() -> None:
    from walrusos import WalrusOS
    from walrusos.runtime.llm import GeminiProvider, get_provider

    print("=" * 70)
    print("  WalrusOS — End-to-End Multi-Agent Workflow")
    print("  Four Gemini agents + live Claude Desktop on one dashboard.")
    print("  No demo, all real proofs.")
    print("=" * 70)
    print()

    # ── Pre-flight ───────────────────────────────────────────────────────────
    use_mocks = os.environ.get("WALRUSOS_USE_MOCKS", "0") == "1"
    print(f"[pre-flight] WALRUSOS_USE_MOCKS = {use_mocks}")
    print(f"[pre-flight] Bridge:             {BRIDGE_URL}")
    print(f"[pre-flight] Workspace:          {WORKSPACE_NAME}")

    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        # mask the key — show first 6 chars only
        print(f"[pre-flight] GEMINI_API_KEY:    set ({api_key[:6]}…)")
    else:
        print("[pre-flight] GEMINI_API_KEY:    NOT set — will use StubProvider")

    bridge_ok = await _bridge_running()
    print(f"[pre-flight] Bridge reachable:   {bridge_ok}")
    if not bridge_ok:
        print("             (4 agents will register in-process; dashboard "
              "presence will NOT update — start the bridge to see it live.)")
    print()

    # ── Runtime + workspace ──────────────────────────────────────────────────
    runtime   = WalrusOS(use_mocks=use_mocks)
    workspace = runtime.workspace(WORKSPACE_NAME)
    print(f"[workspace] {WORKSPACE_NAME!r}  id={workspace.workspace_id}")
    print()

    # ── 1) Connect 4 agents ──────────────────────────────────────────────────
    print("[1/8] Connecting 4 Gemini agents with distinct capabilities…")
    team = await _connect_team(workspace)
    print()

    # ── 2) Online roster ─────────────────────────────────────────────────────
    print("[2/8] Online roster via workspace.online_agents():")
    online = await workspace.online_agents(bridge_url=BRIDGE_URL)
    if online:
        for s in online:
            print(f"      • {s.get('agent_name'):10} ({s.get('framework'):12}) "
                  f"status={s.get('status'):8} workspace={s.get('workspace_id', '')[:8]}…")
    else:
        print("      (no presence — bridge offline or no online agents)")
    print()

    # ── 3) Capability discovery ──────────────────────────────────────────────
    print("[3/8] Capability discovery via workspace.discover():")
    for cap in ["research", "risk_assessment", "code_generation", "synthesis"]:
        found = await workspace.discover(capability=cap, bridge_url=BRIDGE_URL)
        names = [a.get("agent_name") for a in found]
        print(f"      capability={cap:18}  → {names}")
    print()

    # ── 4) Coordinate ────────────────────────────────────────────────────────
    print("[4/8] Selecting LLM…")
    if api_key:
        llm = GeminiProvider(api_key=api_key, model="gemini-2.5-flash")
        print("      → GeminiProvider(gemini-2.5-flash) — real API calls")
    else:
        llm = get_provider("stub")
        print("      → StubProvider — no GEMINI_API_KEY set")
    print()

    goal = (
        "Produce a research brief on building a decentralized data-storage "
        "startup: research the market landscape, write a HYPOTHETICAL "
        "risk/opportunity analysis (for written discussion only — no "
        "actionable trade instructions), outline a technical implementation "
        "approach, and synthesize a final go/no-go recommendation. "
        + TRADING_HYPOTHETICAL_FRAME
    )

    print(f"[5/8] GOAL: {goal[:120]}…")
    print()
    print("[6/8] Coordinator decomposing + routing tasks…")
    print()

    def on_task(task) -> None:
        agent_name = task.assigned_to_name or "?"
        print(f"      [{agent_name:10}] completed: {task.title[:60]}")

    t_start = time.time()
    result  = await workspace.coordinate(
        goal=goal,
        llm=llm,
        on_task_complete=on_task,
    )
    t_total = time.time() - t_start

    # ── 5) Plan visibility ───────────────────────────────────────────────────
    print()
    print(f"[7/8] Execution plan (auto-generated by coordinator, {t_total:.1f}s):")
    for i, task in enumerate(result.plan.tasks, 1):
        deps = f" deps={len(task.depends_on)}" if task.depends_on else ""
        agent_name = task.assigned_to_name or "?"
        print(f"      {i}. [{task.status:8}] {task.title[:55]}")
        print(f"           cap={task.required_capability:18}  → {agent_name}{deps}")
    print()

    print("      Final synthesized recommendation:")
    print("      " + "-" * 62)
    for line in (result.final_summary or "").splitlines():
        print(f"      {line}")
    print("      " + "-" * 62)
    print()

    # ── 6) PROOF — blob IDs and Sui anchors ─────────────────────────────────
    print(f"[8/8] PROOF — on-chain artifacts ({len(result.events)} events):")
    proof_lines: list[str] = []
    proof_lines.append("=" * 70)
    proof_lines.append("  WALRUSOS WORKFLOW PROOF")
    proof_lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    proof_lines.append(f"  Goal: {goal}")
    proof_lines.append(f"  Workspace: {WORKSPACE_NAME} ({workspace.workspace_id})")
    proof_lines.append(f"  Duration: {t_total:.2f}s")
    proof_lines.append(f"  Tasks: {result.tasks_completed} completed, {result.tasks_failed} failed")
    proof_lines.append("=" * 70)
    proof_lines.append("")

    for i, ev in enumerate(result.events, 1):
        blob_id   = getattr(ev, "blob_id", None) or getattr(ev, "content_blob_id", None) or "?"
        tx_digest = getattr(ev, "transaction_digest", "") or ""
        event_id  = getattr(ev, "event_id", "") or getattr(ev, "id", "")
        agent_id  = getattr(ev, "agent_id", "?")

        walrus_url = (
            f"https://aggregator.walrus-testnet.walrus.space/v1/blobs/{blob_id}"
            if blob_id and blob_id != "?" else "(no blob)"
        )
        sui_url = (
            f"https://suiscan.xyz/testnet/tx/{tx_digest}"
            if tx_digest else "(no anchor)"
        )

        print(f"      Event {i}:")
        print(f"        agent:   {agent_id}")
        print(f"        blob:    {walrus_url}")
        print(f"        anchor:  {sui_url}")

        proof_lines.append(f"Event {i}:")
        proof_lines.append(f"  event_id:           {event_id}")
        proof_lines.append(f"  agent_id:           {agent_id}")
        proof_lines.append(f"  walrus_blob_id:     {blob_id}")
        proof_lines.append(f"  walrus_url:         {walrus_url}")
        proof_lines.append(f"  sui_tx_digest:      {tx_digest or '(none)'}")
        proof_lines.append(f"  sui_url:            {sui_url}")
        proof_lines.append("")

    proof_lines.append("-" * 70)
    proof_lines.append("Verification:")
    proof_lines.append("  Paste each walrus_url into a browser to fetch the blob.")
    proof_lines.append("  Paste each sui_url to verify the anchor on Sui Explorer.")
    proof_lines.append("=" * 70)

    proof_path = Path(__file__).parent / "last_workflow_proof.txt"
    proof_path.write_text("\n".join(proof_lines))
    print()
    print(f"      Proof file saved: {proof_path}")
    print()

    # ── 7) Keep online for the dashboard ────────────────────────────────────
    print("[done] Keeping agents online for 60s so the dashboard can capture them…")
    print("       (Ctrl+C to skip the hold and disconnect immediately.)")
    try:
        await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("       Skip requested.")
    print()

    # ── 8) Clean shutdown ────────────────────────────────────────────────────
    print("[shutdown] Disconnecting team…")
    for name, agent in team.items():
        try:
            await agent.go_offline()
            print(f"           {name} offline.")
        except Exception as exc:
            print(f"           {name} offline (err: {exc.__class__.__name__})")

    print()
    print("=" * 70)
    print(f"  Done. {result.tasks_completed} tasks completed by "
          f"{len(result.agents_used)} agents in {t_total:.1f}s.")
    print(f"  Walrus blobs: {len(result.blob_ids)}  •  Sui anchors: {len(result.sui_anchors)}")
    print(f"  On-chain proof: {proof_path.name}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[stop] interrupted")
