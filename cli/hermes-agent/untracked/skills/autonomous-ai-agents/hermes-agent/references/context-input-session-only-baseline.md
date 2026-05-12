# Session-only input-context baseline (phase 1)

This note captures the safest first pass for diagnosing Hermes input-context overhead.

## Purpose
- Produce a read-only baseline without touching runtime behavior.
- Keep the pass offline and reversible.
- Measure coverage and aggregate token cost before attempting deeper attribution.

## Minimal source
- `~/.hermes/sessions/sessions.json` only.
- Do not require `state.db`, `session_*.json`, `session_*.jsonl`, or `request_dump_*.json` for the first baseline.
- Treat `request_dump_*.json` as optional/debug-only; absence is normal.

## What this first pass can report
- total input/output tokens
- cache read/write fields when present
- average input/output per session
- by-model and by-platform rollups when those fields exist
- warnings for missing optional fields

## What it cannot attribute yet
- system prompt vs tools schema vs conversation history
- tool outputs vs memory / hindsight injections
- compression summaries vs normal message history

## Practical lessons from the first implementation
- If `model` is absent in all indexed sessions, the analyzer should warn and continue.
- A real `sessions.json` may contain only aggregate rows and zero token totals; that is still a valid baseline.
- Keep the script strictly read-only and avoid importing runtime code.
- If the first pass proves the index is sparse, escalate later in a separate read-only tool to richer sources.

## Safety reminders
- No network calls.
- No writes under `~/.hermes`.
- No deletion or redaction of logs/sessions/dumps.
- Do not commit secrets or private dumps.
