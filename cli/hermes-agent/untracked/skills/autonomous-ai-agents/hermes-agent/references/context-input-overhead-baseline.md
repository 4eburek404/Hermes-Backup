# Read-only input-context overhead baseline

This note captures the low-risk diagnostic workflow for measuring what inflates Hermes input tokens **without changing runtime behavior**.

## Scope
- Read local session artifacts only.
- Do **not** change the context compressor, prompt builder, toolsets, skills loading, or user config.
- Do **not** fetch remote data or call network APIs from the diagnostic script.
- Do **not** delete or rewrite logs, sessions, or request dumps.

## File formats observed

### `~/.hermes/sessions/sessions.json`
Session index keyed by `session_key`.
Useful fields:
- `session_id`
- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `total_tokens`
- `updated_at`
- `platform`, `display_name`, `cost_status`

### `~/.hermes/sessions/session_*.json`
Full session snapshot. Common fields:
- `session_id`, `platform`, `model`, `base_url`
- `system_prompt` (already assembled final prompt text)
- `tools` (tool schemas as sent)
- `messages` (full conversational history)
- `message_count`, `last_updated`, `session_start`

### `~/.hermes/sessions/session_*.jsonl`
Event stream. Typical first row is `session_meta`, then user/assistant/tool rows.
Useful for reconstructing API-call chronology and spotting oversized tool outputs.
Common assistant keys:
- `tool_calls`
- `reasoning` / `reasoning_content`
- `codex_reasoning_items`

### `~/.hermes/sessions/request_dump_*.json`
Debug request payloads written by `run_agent.py` when request dumping is enabled.
Structure:
- `timestamp`, `session_id`, `reason`
- `request.method`, `request.url`
- `request.headers` (Authorization masked)
- `request.body` (the actual payload sent)
- optional `error`

Note: these dumps live next to the session files under `~/.hermes/sessions/`, not in the main logs directory. They are optional; absence is normal and should not be treated as an error.

## Overhead buckets to measure
- `system_prompt`
- tool schema payload size
- skills / system-text sections
- user / assistant / tool message bodies
- tool outputs
- memory / hindsight injections
- compression summaries / context markers
- cache fields, if present

## Useful markers
- `[CONTEXT SUMMARY]:`
- `END OF CONTEXT SUMMARY`
- `# Hindsight Memory`
- `MEMORY (`
- `USER PROFILE (`
- `## Skills (mandatory)`

## Output expectations
For a baseline report, prefer:
- **Snapshot sizing vs. Estimated provider input** distinction:
  - **Snapshot sizing**: Full volume of data in `session_*.json` (sizing of the storage artifact).
  - **Estimated provider input**: Evaluation of tokens actually sent to standard LLM providers (excluding metadata like `codex_reasoning_items`).
- Invariant to track: `Snapshot Total = Provider Input Total + Storage-only Total`.
- per-session and per-model rollups
- total and average input/output tokens
- top oversized messages / tool outputs / schemas
- explicit identification of compression-summary presence
- markdown + JSON output so results are diffable and machine-readable

## Pitfalls
- **Storage vs. Provider Input:** Not all fields in session snapshots (`session_*.json`) are sent to the provider. Large fields like `codex_reasoning_items` (~1M+ tokens in some sessions) are often **storage-only baggage** (transcripts/continuity) and are explicitly stripped by the `chat_completions` transport before the API call to prevent 402/400 errors.
- **Transport Filtering:** Always cross-reference snapshot fields with `agent/transports/` logic. For standard models, unknown fields (like `codex_*`) are popped during message conversion.
- **Dynamic Pruning:** Tool outputs in snapshots might be raw, while the actual prompt uses compressed/summarized versions if the session is near the context limit (see `agent/context_compressor.py`).
- **System Prompt Sizing:** The `system_prompt` field in snapshots is the *final* assembled text. Measure it directly rather than trying to re-calculate from sections.
- **Offline only:** Keep diagnostics read-only.
