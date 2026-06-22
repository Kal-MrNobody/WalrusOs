"""
Example 3: Algorithmic Trading Team
=====================================
WalrusOS Capability Demonstrated: REAL-TIME PUB/SUB

Research publishes market signals to a shared stream.
Risk monitors the stream and blocks dangerous signals via callback.
Execution subscribes and fires orders only if Risk clears them.

Key concepts:
  - agent.subscribe(stream, callback) : reactive async polling
  - agent.publish(stream, {...})      : real-time signal emission
  - asyncio.Task                      : background subscription loops
"""
from __future__ import annotations

import asyncio
import random
from typing import Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from walrusos import WalrusOS

console = Console()

runtime   = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python main.py
workspace = runtime.workspace("trading_desk")

research  = workspace.agent("Research")
risk      = workspace.agent("Risk")
execution = workspace.agent("Execution")

signal_stream = workspace.stream("market_signals")
order_stream  = workspace.stream("live_orders")

# Shared state for risk gate
_risk_cleared: dict[str, bool] = {}
_orders_fired: list[dict]      = []

# ── Callbacks ─────────────────────────────────────────────────────────────────

async def risk_monitor(payload: Dict[str, Any]) -> None:
    """Risk agent evaluates each signal and publishes a verdict."""
    if payload.get("action") != "signal":
        return
    signal = payload
    symbol     = signal.get("symbol", "UNKNOWN")
    confidence = signal.get("confidence", 0)
    direction  = signal.get("direction", "NEUTRAL")

    # Risk rules
    if confidence < 0.70:
        verdict = "BLOCKED"
        reason  = f"Confidence {confidence:.0%} below threshold 70%"
    elif direction == "SHORT" and symbol.startswith("BTC"):
        verdict = "BLOCKED"
        reason  = "No short positions on BTC per risk policy"
    else:
        verdict = "CLEARED"
        reason  = f"Signal passed all risk checks. Confidence: {confidence:.0%}"

    _risk_cleared[symbol] = verdict == "CLEARED"

    color = "green" if verdict == "CLEARED" else "red"
    console.print(f"  [yellow]Risk[/] [{color}]{verdict:<8}[/{color}] {symbol} — {reason}")

    await risk.publish(signal_stream, {
        "action":  "risk_verdict",
        "symbol":  symbol,
        "verdict": verdict,
        "reason":  reason,
    })

async def execution_monitor(payload: Dict[str, Any]) -> None:
    """Execution fires an order only when Risk has cleared the signal."""
    if payload.get("action") != "signal":
        return
    symbol    = payload.get("symbol", "")
    direction = payload.get("direction", "LONG")
    quantity  = payload.get("quantity", 0)

    await asyncio.sleep(0.4)  # Wait for risk verdict

    if _risk_cleared.get(symbol):
        price = round(random.uniform(40000, 72000) if "BTC" in symbol else random.uniform(2000, 4000), 2)
        order = {
            "action":    "order_filled",
            "symbol":    symbol,
            "direction": direction,
            "quantity":  quantity,
            "price":     price,
            "notional":  round(price * quantity, 2),
        }
        _orders_fired.append(order)
        await execution.publish(order_stream, order)
        console.print(f"  [magenta]Exec[/] [green]ORDER FILLED[/] {direction} {quantity}x {symbol} @ ${price:,.2f}")
    else:
        console.print(f"  [magenta]Exec[/] [red]BLOCKED[/]     {symbol} — risk gate closed")

async def research_signal_loop() -> None:
    """Research agent publishes a series of trading signals."""
    await asyncio.sleep(0.5)  # Let subscribers attach first
    console.print("\n[bold cyan]◆ Research[/] publishing market signals...\n")

    signals = [
        {"symbol": "BTC-USDT", "direction": "LONG",  "confidence": 0.91, "quantity": 0.5,  "model": "LSTM-v3"},
        {"symbol": "ETH-USDT", "direction": "LONG",  "confidence": 0.85, "quantity": 2.0,  "model": "Transformer-v2"},
        {"symbol": "SOL-USDT", "direction": "SHORT", "confidence": 0.65, "quantity": 10.0, "model": "GRU-v1"},
        {"symbol": "BTC-USDT", "direction": "SHORT", "confidence": 0.88, "quantity": 0.25, "model": "Ensemble"},
        {"symbol": "ARB-USDT", "direction": "LONG",  "confidence": 0.78, "quantity": 500,  "model": "MeanReversion"},
        {"symbol": "ETH-USDT", "direction": "LONG",  "confidence": 0.93, "quantity": 1.5,  "model": "Momentum-v4"},
    ]

    for sig in signals:
        await asyncio.sleep(0.7)
        await research.publish(signal_stream, {"action": "signal", **sig})
        console.print(f"  [cyan]Signal[/]  {sig['direction']:<5} {sig['symbol']:<12} conf={sig['confidence']:.0%}")

async def main() -> None:
    console.print(Panel.fit(
        "[bold]Example 3: Algorithmic Trading Team[/]\n"
        "[dim]Capability: Real-Time Pub/Sub[/]\n\n"
        "Research emits market signals. Risk validates in real-time.\n"
        "Execution fires orders only when Risk clears them.",
        border_style="yellow",
        title="[bold magenta]WalrusOS[/]",
    ))

    # Subscribe Risk and Execution to the signals stream
    risk_task = await risk.subscribe(signal_stream, risk_monitor)
    exec_task = await execution.subscribe(signal_stream, execution_monitor)

    # Research publishes signals
    await research_signal_loop()
    await asyncio.sleep(2.0)  # Allow callbacks to flush

    # Cancel background pollers
    risk_task.cancel()
    exec_task.cancel()

    # Final P&L table
    table = Table(
        title="📊 Execution Report — Orders Filled",
        border_style="dim",
        header_style="bold magenta",
        box=box.ROUNDED,
    )
    table.add_column("Symbol",    style="cyan")
    table.add_column("Direction", style="bold")
    table.add_column("Qty",       justify="right")
    table.add_column("Price",     justify="right", style="green")
    table.add_column("Notional",  justify="right", style="bold green")

    for o in _orders_fired:
        table.add_row(
            o["symbol"], o["direction"],
            str(o["quantity"]),
            f"${o['price']:>10,.2f}",
            f"${o['notional']:>12,.2f}",
        )
    console.print()
    console.print(table)

    console.print(Panel.fit(
        f"[green]✓ Trading session complete![/]\n\n"
        f"{len(_orders_fired)} orders filled out of 6 signals.\n"
        "All risk gates enforced. Every decision is on-chain.",
        border_style="green",
    ))

if __name__ == "__main__":
    asyncio.run(main())
