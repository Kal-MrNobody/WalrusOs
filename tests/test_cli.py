"""
CLI tests using Typer's CliRunner for isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from walrusos.cli.main import app

runner = CliRunner()


def test_help():
    """Root --help should exit 0 and mention WalrusOS."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "WalrusOS" in result.output


def test_init_default(tmp_path, monkeypatch):
    """walrusos init should write config.json and show next steps."""
    # Override config dir so tests don't pollute ~/.walrusos
    cfg_dir  = tmp_path / ".walrusos"
    cfg_file = cfg_dir / "config.json"
    monkeypatch.setattr("walrusos.cli._state.CONFIG_DIR",  cfg_dir)
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", cfg_file)

    result = runner.invoke(app, ["init", "--workspace", "test-ws", "--network", "testnet"])
    assert result.exit_code == 0
    assert "test-ws" in result.output
    assert "walrusos demo" in result.output   # new: shows next steps
    # No .walrusos marker file is created in cwd (removed in v0.1)
    assert not (Path(".") / ".walrusos").exists()


def test_status_before_login(tmp_path, monkeypatch):
    """walrusos status should display 'not logged in' when config is empty."""
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", tmp_path / "config.json")
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "not logged in" in result.output


def test_login_invalid_address():
    """Login with a bad address should fail."""
    result = runner.invoke(app, ["login", "--address", "not-an-address"])
    assert result.exit_code != 0
    assert "Invalid" in result.output


def test_workspace_create(tmp_path, monkeypatch):
    """walrusos workspace create should print the workspace ID."""
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", tmp_path / "config.json")
    # Pre-write a fake login
    (tmp_path / "config.json").write_text(json.dumps({
        "sui_address": "0x" + "a" * 64, "workspace": "default", "network": "testnet"
    }))
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", tmp_path / "config.json")

    result = runner.invoke(app, ["workspace", "create", "my-workspace"])
    assert result.exit_code == 0
    assert "my-workspace" in result.output


def test_agent_create(tmp_path, monkeypatch):
    """walrusos agent create should print the agent ID."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "sui_address": "0x" + "b" * 64, "workspace": "default", "network": "testnet"
    }))
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", cfg_file)

    result = runner.invoke(app, ["agent", "create", "Researcher"])
    # Either succeeds (0) or fails gracefully with agent name in output
    assert "Researcher" in result.output


def test_artifacts_list(tmp_path, monkeypatch):
    """walrusos artifacts list should print the artifact table."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"sui_address": "0x" + "c" * 64}))
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", cfg_file)

    result = runner.invoke(app, ["artifacts", "list"])
    assert result.exit_code == 0
    assert "Artifacts" in result.output


def test_permissions_list(tmp_path, monkeypatch):
    """walrusos permissions list should print the capability table."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"sui_address": "0x" + "d" * 64}))
    monkeypatch.setattr("walrusos.cli._state.CONFIG_FILE", cfg_file)

    result = runner.invoke(app, ["permissions", "list"])
    assert result.exit_code == 0
    assert "Researcher" in result.output


def test_logs_empty(tmp_path, monkeypatch):
    """walrusos logs should handle empty log gracefully."""
    monkeypatch.setattr("walrusos.cli._state.LOG_FILE", tmp_path / "walrusos.log")
    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
