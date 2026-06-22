"""
walrusos init — Initialise WalrusOS in the current project.
"""
from __future__ import annotations

import typer
from rich.panel import Panel

from walrusos.cli._state import console, save_config, CONFIG_DIR

app = typer.Typer(help="Initialise WalrusOS in the current project.")


@app.callback(invoke_without_command=True)
def init(
    workspace: str = typer.Option("default", "--workspace", "-w", help="Default workspace name"),
    network:   str = typer.Option("testnet",  "--network",   "-n", help="Sui network: testnet | mainnet | devnet"),
) -> None:
    """
    Scaffold a .walrusos/ config directory and write initial settings.
    """
    console.print(Panel.fit(
        "[accent]WalrusOS[/] — Initialising project",
        border_style="magenta",
    ))

    config = {
        "workspace":    workspace,
        "network":      network,
        "publisher_url": f"https://publisher.walrus-{network}.walrus.space" if network != "mainnet" else "https://publisher.walrus.space",
        "aggregator_url": f"https://aggregator.walrus-{network}.walrus.space" if network != "mainnet" else "https://aggregator.walrus.space",
        "sui_rpc":      f"https://fullnode.{network}.sui.io:443",
    }
    save_config(config)

    console.print(f"[success]✓[/] Config written to [muted]{CONFIG_DIR}/config.json[/]")
    console.print(f"[success]✓[/] Workspace  : [stream]{workspace}[/]")
    console.print(f"[success]✓[/] Network    : [info]{network}[/]")
    console.print()
    console.print("Next steps:")
    console.print("  1. Run [accent]walrusos demo[/] to verify your installation.")
    console.print("  2. Run [accent]walrusos login[/] to connect a Sui wallet (optional).")
    console.print("  3. Set [accent]WALRUSOS_KEY_PASSWORD[/] for production encryption.")
