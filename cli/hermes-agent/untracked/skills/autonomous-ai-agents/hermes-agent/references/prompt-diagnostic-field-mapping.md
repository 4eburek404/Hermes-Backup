# Diagnostic Field Mapping: Snapshot vs Provider Input

When auditing system snapshots (`session_*.json`), fields must be categorized based on whether they enter the LLM's context window or stay in local storage/transcripts.

## Token Estimation Rule
- **Primary**: `ceil(len(serialized_text) / 4)` (conservative surrogate for BPE).
- **Tool Outputs**: Must include the meta-envelope tokens (role, tool_call_id) as these are always sent.

## Logic Invariants

| Component | Snapshot Sizing Category | Provider Input Category | Notes |
| :--- | :--- | :--- | :--- |
| `system_prompt` | Included | Included | Primary instructions. |
| `tools` schema | Included | Included | Functional capabilities. |
| `messages[].content` | Included | Included | User/Assistant text. |
| `messages[].tool_calls` | Included | Included | Functional call structure. |
| `reasoning_details` | Included | Included | Used for Anthropic/Gemini continuity. |
| `reasoning_content` | Included | Included | DeepSeek/R1 thinking block. |
| `codex_reasoning_items` | **Included** | **Excluded** | Stripped by standard `chat_completions` transport. |
| `codex_message_items` | **Included** | **Excluded** | Stripped by standard `chat_completions` transport. |

## Script Implementation Note (Python)

To ensure the invariant `SnapshotTotal = ProviderTotal + StorageTotal`:

```python
# 1. Calculate base message envelope tokens (role, name, call_id etc)
envelope_tokens = estimate_payload_tokens(envelope_fields)

# 2. Calculate specialized fields
content_tokens = estimate_payload_tokens(message.get("content"))
t_calls_tokens = estimate_payload_tokens(message.get("tool_calls"))
storage_fields_tokens = estimate_payload_tokens(message.get("codex_reasoning_items")) + ...

# 3. Summation
msg_provider_total = envelope_tokens + content_tokens + t_calls_tokens + reasoning_fields_tokens
msg_storage_total = storage_fields_tokens
msg_snapshot_total = msg_provider_total + msg_storage_total
```
