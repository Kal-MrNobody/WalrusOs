# WalrusOS Official Demonstration - Video Script

**Title**: WalrusOS: The Operating System for Agentic Collaboration
**Target Length**: 3 Minutes

## Scene 1: The Setup
**Visual**: Fast-paced terminal text. We see three agents spinning up: Research Agent, Reviewer Agent, and Writer Agent.
**Voiceover**: "Welcome to WalrusOS. Today, we're watching three independent AI agents collaborate on a complex report. But unlike traditional systems, they aren't passing stateless messages. They are communicating over a cryptographic ledger anchored to the Sui blockchain."

## Scene 2: Shared Memory & Capabilities
**Visual**: The terminal splits into three panes. The Research Agent publishes findings to a shared stream. The Reviewer Agent attempts to publish but is rejected. The screen flashes red with a `CapabilityDeniedError`.
**Voiceover**: "Every action in WalrusOS requires a Move Capability. Here, the Reviewer Agent attempts to write to the shared memory stream, but its transaction is instantly rejected. The agent simply doesn't have the permission."
**Visual**: An Admin script runs, granting the `AppendCapability`. The Reviewer Agent tries again, and this time, the event is appended and signed with Ed25519.

## Scene 3: Branching & The Trust Graph
**Visual**: A colorful dashboard showing a Git-like branch structure. The Writer Agent forks the timeline to create a "Creative Draft." A side panel shows the Trust Graph scores ticking up as agents successfully verify each other's signatures.
**Voiceover**: "Because WalrusOS uses Event Sourcing, agents can fork and branch their memories, just like Git. As they collaborate, their cryptographic signatures build a deterministic Trust Graph. Agents can see exactly who wrote what, and trust the history mathematically."

## Scene 4: Cryptographic Verification
**Visual**: We show a hex editor or Python script deliberately corrupting a single byte in the local SQLite database.
**Voiceover**: "What happens if local data is corrupted or maliciously altered? Let's mutate a single byte of memory."
**Visual**: The script attempts to read the stream. It fails immediately with a `CryptographicVerificationError`.
**Voiceover**: "WalrusOS catches the tampered data instantly. You can't fake memory here."

## Scene 5: Disaster Recovery (The Catastrophe)
**Visual**: `rm -rf .walrusos/` is executed. The terminal goes blank. 
**Voiceover**: "Now for the ultimate test. We've just deleted the entire local database, the search indices, and the configuration. Everything is gone."
**Visual**: The script runs `runtime.recover()`. The screen floods with data streaming in from the Walrus Decentralized Storage Network. Within seconds, the exact timeline, signatures, and capabilities are restored perfectly.
**Voiceover**: "By pulling from Walrus and Sui, the agent reconstitutes its entire identity and memory state. No central server. No backups. Just pure cryptographic recovery."

## Scene 6: Outro
**Visual**: The WalrusOS logo, overlaid on a rotating 3D Trust Graph.
**Voiceover**: "Persistent. Cryptographic. Unstoppable. This is WalrusOS. Build the future of agentic AI today."
