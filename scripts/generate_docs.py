"""
generate_docs.py — Automatically generate Markdown API reference for WalrusOS SDK.
"""
import inspect
import sys
import os

from walrusos.client import WalrusOS
from walrusos.sdk.workspace import WorkspaceClient
from walrusos.sdk.agent import AgentClient
from walrusos.sdk.stream import StreamClient
from walrusos.sdk.exceptions import WalrusOSError, AgentNotFoundError, CryptographicVerificationError, CapabilityRevokedError

def generate_markdown() -> str:
    classes_to_document = [
        WalrusOS,
        WorkspaceClient,
        AgentClient,
        StreamClient,
        WalrusOSError,
        AgentNotFoundError,
        CryptographicVerificationError,
        CapabilityRevokedError
    ]

    lines = ["# WalrusOS SDK API Reference", "", "This document is auto-generated from the Python source code.", ""]

    for cls in classes_to_document:
        lines.append(f"## class `{cls.__name__}`")
        if cls.__doc__:
            lines.append(inspect.cleandoc(cls.__doc__))
            lines.append("")

        # Get methods
        for name, func in inspect.getmembers(cls, inspect.isfunction):
            if name.startswith("_") and name != "__init__":
                continue
            
            sig = inspect.signature(func)
            lines.append(f"### `def {name}{sig}`")
            if func.__doc__:
                lines.append(inspect.cleandoc(func.__doc__))
                lines.append("")
        
        # Get properties
        for name, prop in inspect.getmembers(cls, lambda o: isinstance(o, property)):
            if name.startswith("_"):
                continue
            lines.append(f"### `@property {name}`")
            if prop.__doc__:
                lines.append(inspect.cleandoc(prop.__doc__))
                lines.append("")
                
        lines.append("---")
        lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    md = generate_markdown()
    os.makedirs("docs", exist_ok=True)
    with open("docs/api_reference.md", "w") as f:
        f.write(md)
    print("Generated docs/api_reference.md")
