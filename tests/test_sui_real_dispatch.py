"""
Tests for the sui_real adapter's call dispatcher.

The Sui CLI's ``client call --args`` greedily consumes following tokens but
rejects any value starting with ``-`` as an unknown flag. Walrus blob_ids are
base64url Blake2b hashes — ~3 in 64 start with ``-``. The adapter's ``_call``
dispatcher must:
  - Use the normal ``client call`` path when no arg starts with ``-``.
  - Route through PTB form (``client ptb --move-call``) when any arg does,
    because PTB accepts quoted string values containing leading dashes.

These tests mock subprocess.run so they exercise the dispatch logic without
hitting the live Sui CLI.
"""
from __future__ import annotations

import os

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import json
import pytest
from unittest.mock import MagicMock, patch


def _make_client():
    """Construct a RealSuiClient instance without touching real CLI/network."""
    from walrusos.adapters.sui_real import RealSuiClient
    # The constructor reads env to find the binary and addresses, but we don't
    # need a valid setup for dispatch-logic tests — just enough to instantiate.
    client = RealSuiClient.__new__(RealSuiClient)
    client.sui_binary       = "sui"
    client.package_id       = "0xPACKAGE"
    client.ledger_anchor_id = "0xLEDGER"
    client.network          = "testnet"
    return client


class TestDispatcherRoutesByHyphenPrefix:
    """`_call` must dispatch to `_run_call` (client call) or `_run_ptb_call`
    (ptb) based on whether any arg starts with `-`."""

    def test_no_hyphen_args_uses_client_call_path(self):
        client = _make_client()
        client._run_call     = MagicMock(return_value={"digest": "tx-call"})
        client._run_ptb_call = MagicMock(return_value={"digest": "tx-ptb"})
        result = client._call(
            module="protocol",
            function="anchor_event",
            args=["0xLEDGER", "abc123", "MemoryAppended", "ws", "agent",
                  "aYeG3g4utP7Ssi", "hash", "genesis", "genesis", "sig"],
        )
        client._run_call.assert_called_once()
        client._run_ptb_call.assert_not_called()
        assert result["digest"] == "tx-call"

    def test_hyphen_prefixed_arg_routes_to_ptb(self):
        """A Walrus blob_id starting with `-` must trigger the PTB form,
        because `sui client call --args` rejects it."""
        client = _make_client()
        client._run_call     = MagicMock(return_value={"digest": "tx-call"})
        client._run_ptb_call = MagicMock(return_value={"digest": "tx-ptb"})
        result = client._call(
            module="protocol",
            function="anchor_event",
            args=["0xLEDGER", "abc123", "AgentRegistered", "ws", "agent",
                  "-Nlo-l8E5a0e7FbpZu4lytG_BXOL4mjSusDOymLwlaw",  # leading dash
                  "hash", "genesis", "genesis", "sig"],
        )
        client._run_ptb_call.assert_called_once()
        client._run_call.assert_not_called()
        assert result["digest"] == "tx-ptb"

    def test_hyphen_anywhere_else_does_not_trigger_ptb(self):
        """Only LEADING `-` is a flag-parsing problem; embedded `-` is fine."""
        client = _make_client()
        client._run_call     = MagicMock(return_value={"digest": "tx-call"})
        client._run_ptb_call = MagicMock(return_value={"digest": "tx-ptb"})
        client._call(
            module="protocol",
            function="anchor_event",
            args=["0xLEDGER", "abc-with-dashes", "MemoryAppended", "ws",
                  "agent", "blob", "hash", "genesis", "genesis", "sig"],
        )
        client._run_call.assert_called_once()
        client._run_ptb_call.assert_not_called()


class TestPtbCommandConstruction:
    """`_run_ptb_call` must build the right command tokens:
       - `@<addr>` for hex addresses/ObjectIds
       - `"<value>"` for string values (including hyphen-prefixed)
       - target string `PACKAGE::MODULE::FUNCTION`
    """

    def test_ptb_builds_correct_command_tokens(self):
        client = _make_client()
        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = json.dumps({"digest": "tx-from-ptb"})
        ok_result.stderr = ""
        with patch("subprocess.run", return_value=ok_result) as mock_run:
            result = client._run_ptb_call(
                module="protocol",
                function="anchor_event",
                args=[
                    "0xLEDGER",
                    "event_id_hex",
                    "AgentRegistered",
                    "ws-uuid",
                    "agent-uuid",
                    "-Nlo-leading-dash-blob",
                    "blob_hash",
                    "genesis",
                    "genesis",
                    "sig",
                ],
            )
            assert result["digest"] == "tx-from-ptb"
            cmd = mock_run.call_args[0][0]
            # The move-call target should be PKG::MOD::FUNC
            mc_idx = cmd.index("--move-call")
            assert cmd[mc_idx + 1] == "0xPACKAGE::protocol::anchor_event"
            # First value after target is the LedgerAnchor — must be `@`-prefixed
            assert cmd[mc_idx + 2] == "@0xLEDGER"
            # Strings must be wrapped in quotes
            assert '"event_id_hex"' in cmd
            assert '"AgentRegistered"' in cmd
            assert '"-Nlo-leading-dash-blob"' in cmd
            assert '"genesis"' in cmd
            # Should not contain `--` end-of-options marker
            assert "--" not in cmd[mc_idx:mc_idx + 12]

    def test_ptb_returns_parsed_json_digest(self):
        client = _make_client()
        ok_result = MagicMock()
        ok_result.returncode = 0
        ok_result.stdout = json.dumps({"digest": "abcXYZ"})
        ok_result.stderr = ""
        with patch("subprocess.run", return_value=ok_result):
            data = client._run_ptb_call("protocol", "anchor_event", ["0xL", "x"])
        assert data == {"digest": "abcXYZ"}

    def test_ptb_surfaces_full_error_on_failure(self):
        """When the CLI fails, the raised error must include returncode, cmd,
        stderr and stdout — not just an empty truncated string."""
        from walrusos.adapters.sui_real import SuiTransactionError
        client = _make_client()
        fail = MagicMock()
        fail.returncode = 2
        fail.stdout = "some stdout content"
        fail.stderr = "Move call abort thingy"
        with patch("subprocess.run", return_value=fail):
            with pytest.raises(SuiTransactionError) as exc_info:
                client._run_ptb_call("protocol", "anchor_event", ["0xL", "evt"])
        msg = str(exc_info.value)
        assert "returncode: 2" in msg
        assert "Move call abort thingy" in msg
        assert "some stdout content" in msg
