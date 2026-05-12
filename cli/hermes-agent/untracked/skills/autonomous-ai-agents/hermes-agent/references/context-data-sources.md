# Hermes input-context baseline data sources

Condensed inventory for read-only diagnostics that measure input-context overhead.

## Primary sources

### `~/.hermes/state.db`
Structured source of truth for sessions and messages.
Useful for:
- total `input_tokens` / `output_tokens`
- `cache_read_tokens` / `cache_write_tokens`
- `reasoning_tokens`
- `api_call_count`, `tool_call_count`, `message_count`
- session-level `model`, `system_prompt`, `parent_session_id`
- message-level `role`, `content`, `tool_calls`, `tool_name`, `token_count`, reasoning fields, `codex_*`

### `~/.hermes/sessions/session_*.json`
Full session snapshot.
Useful for:
- assembled `system_prompt`
- `tools` schema payload
- complete `messages` history
- `message_count`, `session_start`, `last_updated`, `model`, `base_url`, `platform`

### `~/.hermes/sessions/sessions.json`
Session index / aggregates keyed by `session_key`.
Useful for:
- quick rollups by session
- `input_tokens`, `output_tokens`, cache tokens, `total_tokens`
- `display_name`, `platform`, `cost_status`, freshness flags

## Legacy / optional sources

### `~/.hermes/sessions/session_*.jsonl`
Legacy transcript stream.
Useful for:
- event chronology
- fallback when JSON snapshots are incomplete
- spotting oversized assistant/tool payloads and reasoning blocks

### `~/.hermes/sessions/request_dump_*.json`
Debug-only request payload dumps.
Useful for:
- the closest view of the actual API payload
- request body inspection when available
- verifying what was sent after prompt assembly

Absence is normal. Do not treat missing request dumps as a failure.

## Baseline buckets to compute
- system prompt
- tools / schema payload
- skills / system-text sections
- user / assistant / tool messages
- tool outputs
- memory / hindsight injections
- compression summaries / markers
- cache fields when present

## Ordering guidance for analyzers
1. Prefer `state.db` for structured counters and message metadata.
2. Use `session_*.json` for assembled prompt reconstruction.
3. Use `sessions.json` for quick rollups / coverage.
4. Fall back to `session_*.jsonl` only when needed.
5. Use `request_dump_*.json` opportunistically; never require it.

## Safety
- Read-only only.
- No network calls.
- Do not rewrite or delete any session/log artifacts.
- Do not commit real dumps, logs, sessions, or secrets.
