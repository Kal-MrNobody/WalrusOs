"""
MCP Configuration for WalrusOS.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel

from walrusos import WalrusOS

class MCPConfig(BaseModel):
    workspace_id: str = "default"
    network: str = "testnet"
    
    @classmethod
    def load(cls) -> "MCPConfig":
        """Load from ~/.walrusos/config.json"""
        config_path = Path.home() / ".walrusos" / "config.json"
        
        data = {}
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                pass
                
        # Also check env var WALRUSOS_WORKSPACE
        workspace_id = os.environ.get("WALRUSOS_WORKSPACE", data.get("workspace", "default"))
        network = os.environ.get("WALRUSOS_NETWORK", data.get("network", "testnet"))
        
        return cls(workspace_id=workspace_id, network=network)

    def get_runtime(self) -> WalrusOS:
        """Create and return a configured WalrusOS instance."""
        use_mocks = os.environ.get("WALRUSOS_USE_MOCKS", "0") == "1"
        runtime = WalrusOS(use_mocks=use_mocks)
        
        # In a real scenario we'd do:
        # runtime.login() 
        # But for MCP we assume it picks up the default keychain or mock.
        return runtime
