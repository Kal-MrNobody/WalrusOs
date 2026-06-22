"""
walrusos logs — View and tail the local WalrusOS log file.
"""
from __future__ import annotations

import typer
from rich.syntax import Syntax

from walrusos.cli._state import console, LOG_FILE

app = typer.Typer(help="View the local WalrusOS CLI log.")


@app.callback(invoke_without_command=True)
def logs(
    lines:  int  = typer.Option(50, "--lines", "-n", help="Number of recent log lines"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log in real-time"),
    clear:  bool = typer.Option(False, "--clear", help="Clear the log file"),
) -> None:
    """
    Display recent entries from the WalrusOS local log file.
    """
    if clear:
        if LOG_FILE.exists():
            LOG_FILE.write_text("")
        console.print("[success]✓[/] Log cleared.")
        return

    if not LOG_FILE.exists():
        console.print(f"[muted]No log file found at {LOG_FILE}. Run some commands first.[/]")
        return

    if follow:
        import time
        console.print(f"[info]Tailing[/] [muted]{LOG_FILE}[/]  (Ctrl+C to stop)\n")
        try:
            with LOG_FILE.open("r") as f:
                f.seek(0, 2)  # seek to end
                while True:
                    line = f.readline()
                    if line:
                        console.print(line.rstrip())
                    else:
                        time.sleep(0.3)
        except KeyboardInterrupt:
            console.print("\n[muted]Stopped.[/]")
        return

    all_lines = LOG_FILE.read_text().splitlines()
    recent    = all_lines[-lines:]

    if not recent:
        console.print("[muted]Log is empty.[/]")
        return

    console.print(f"[dim]── {LOG_FILE} (last {len(recent)} lines) ──[/]\n")
    for line in recent:
        console.print(line)
