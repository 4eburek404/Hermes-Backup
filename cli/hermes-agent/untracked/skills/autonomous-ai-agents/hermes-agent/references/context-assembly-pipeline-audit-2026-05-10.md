# Hermes Prompt Assembly & Transport Audit (2026-05-10)

## Overview
This audit was performed to establish a vertical mapping from source code to provider-bound payload. It identifies where context is added, how it is managed (compressed/pruned), and where it is sanitized before leaving the agent.

## System Prompt Assembly Layers
The `AIAgent._build_system_prompt` method (in `run_agent.py`) assembles the `system_prompt` in the following stable order:

1.  **Identity**: \`SOUL.md\` (if load_soul_identity is True) or \`DEFAULT_AGENT_IDENTITY\`.
2.  **Tool Guidance**: One-line descriptions of core behavioral capabilities (\`MEMORY_GUIDANCE\`, \`SESSION_SEARCH_GUIDANCE\`, \`SKILLS_GUIDANCE\`).
3.  **Tool Enforcement**: \`TOOL_USE_ENFORCEMENT_GUIDANCE\` (if enabled via config/model match) + Provider-specific behavior (e.g., \`GOOGLE_MODEL_OPERATIONAL_GUIDANCE\`).
4.  **Custom Message**: User-provided \`system_message\` (additive).
5.  **Memory**: Content from \`MEMORY.md\` (via \`MemoryStore\`).
6.  **User Profile**: Preference blocks from \`USER.md\`.
7.  **External Memory**: Optional plugins (Mem0, etc.).
8.  **Skills Index**: Detailed tool/category mapping (\`build_skills_system_prompt\`).
9.  **Context Files**: Project-level instructions (\`AGENTS.md\`, \`.cursorrules\`).
10. **Runtime Metadata**: Start time, Model, Provider, Session ID.
11. **Environment Hints**: OS/Environment details (\`build_environment_hints\`).
12. **Platform Hints**: UI-specific behavioral hints (e.g. Telegram/Discord formatting).

## The Transport "Last Mile" (Sanitization)
Crucial for accurate token estimation: \`ChatCompletionsTransport\` (and others) performs a clean-up of internal fields that are kept for storage/snapshotting but are rejected by standard OpenAI-compatible providers.

### Fields Stripped by Transports:
-   \`codex_reasoning_items\`: Tokens for internal reasoning in Codex mode.
-   \`codex_message_items\`: Internal items.
-   \`tool_calls[*].call_id\`: Internal IDs.
-   \`tool_calls[*].response_item_id\`: Internal response links.

**Implication**: An analyzer tool reading \`session_*.json\` snapshots will see these fields. To estimate the **actual provider cost/input**, the analyzer must simulate this stripping logic.

## Tools Schema Selection
1.  **Global Registry**: \`tools/registry.py\`.
2.  **Filtering**: \`AIAgent.__init__\` calls \`get_tool_definitions\` with \`enabled_toolsets\` / \`disabled_toolsets\`.
3.  **Stability**: Tools remain fixed during a conversation loop. A \`/reset\` or new session is required to change schemas (preserving prompt caching).

## Message Pipeline & Compression
-   **Trigger**: \`_compress_context\` fires when \`ContextCompressor\` detects a threshold breach.
-   **Output**: Produces a (compressed_messages, new_system_prompt) tuple.
-   **New System Prompt**: Compression triggers a mandatory \`_invalidate_system_prompt() \- \`_build_system_prompt()\` cycle to fix current context references (like conversation summaries).
