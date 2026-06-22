"""
walrusos login — Authenticate with a Sui wallet.
"""
from __future__ import annotations

import typer
from rich.panel import Panel

from walrusos.cli._state import console, load_config, save_config

app = typer.Typer(help="Authenticate with a Sui wallet.")


@app.callback(invoke_without_command=True)
def login(
    address: str = typer.Option(None, "--address", "-a", help="Sui wallet address (0x…)"),
) -> None:
    """
    Authenticate the CLI with a Sui Ed25519 address.
    If --address is omitted, attempts to load from the local pysui config.
    """
    if address is None:
        try:
            from pysui import SuiConfig  # type: ignore
            cfg = SuiConfig.default_config()
            address = cfg.active_address.address
            console.print(f"[info]Auto-detected wallet from pysui config:[/] [accent]{address}[/]")
        except Exception:
            console.print("[error]Could not auto-detect wallet.[/] Provide [accent]--address[/] manually.")
            raise typer.Exit(1)

    if not address.startswith("0x") or len(address) != 66:
        console.print("[error]Invalid Sui address.[/] Must start with 0x and be 66 characters.")
        raise typer.Exit(1)

    cfg = load_config()
    cfg["sui_address"] = address
    save_config(cfg)

    console.print(Panel.fit(
        f"[success]✓ Logged in[/]\n\nAddress: [accent]{address}[/]",
        border_style="green",
        title="WalrusOS Auth",
    ))
