# Provider-bound prompt audit (2026-05-10)

Investigation into which message fields from `session_*.json` snapshots are actually sent to LLM providers during API calls.

## Audit Workflow
1. **Identify high-volume fields** in snapshots (using `analyze_context_overhead.py`).
2. **Search `run_agent.py`** for message building and field preservation (look for `_persist_session`, `_build_assistant_message`).
3. **Trace `agent/transports/`** for message conversion logic (`convert_messages`, `build_kwargs`).
4. **Distinguish `chat_completions` vs `codex_responses`** modes.

## Field Status Results

| Field | Status | Detail |
| :--- | :--- | :--- |
| `codex_reasoning_items` | **Filtered** | Stripped by `ChatCompletionsTransport` to avoid 400 errors from standard providers. Only sent in `codex_responses` mode. |
| `codex_message_items` | **Filtered** | Same as above. |
| `reasoning_details` | **Preserved** | Passed through to messages for Anthropic/Gemini/OpenRouter continuity. |
| `reasoning_content` | **Preserved** | Native reasoning output for DeepSeek/R1. |
| `tool_calls` | **Sanitized** | Stripped of internal `call_id`/`response_item_id` in standard transport mode. |
| `tool outputs` | **Pruned** | Sent raw until `ContextCompressor` triggers deduplication/summarization. |

## Key Evidence Locations
- **Transport Filtering**: `agent/transports/chat_completions.py` → `convert_messages()`.
- **Field Replay**: `run_agent.py` → approx line 9130 where `codex_items` are attached to the message dict for turn-to-turn persistence.
- **Request Dumps**: `run_agent.py` → `_dump_api_request_debug()` captures the `api_kwargs` *after* transport-level sanitization but before the HTTP POST.

## Implications for Diagnostics
When measuring "input context overhead", a 1M+ token count for `codex_reasoning_items` is a **storage and snapshot performance metric**, not a transport/cost metric for standard chat-completions providers.
