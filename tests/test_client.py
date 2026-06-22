"""
Tests for the WalrusOS client entrypoint.
"""
import pytest
from walrusos import WalrusOS
from walrusos.sdk.workspace import WorkspaceClient


def test_walrusos_initialization_mocks():
    """WalrusOS with use_mocks=True initialises without error."""
    rt = WalrusOS(use_mocks=True)
    assert rt is not None
    assert rt._event_store is not None   # internal engine (use_mocks only)


def test_walrusos_workspace_returns_client():
    """workspace() returns a WorkspaceClient."""
    rt = WalrusOS(use_mocks=True)
    ws = rt.workspace("test")
    assert isinstance(ws, WorkspaceClient)


def test_walrusos_multiple_workspaces():
    """Multiple independent workspace clients can be created."""
    rt = WalrusOS(use_mocks=True)
    ws1 = rt.workspace("alpha")
    ws2 = rt.workspace("beta")
    assert ws1.name == "alpha"
    assert ws2.name == "beta"
    assert ws1 is not ws2
