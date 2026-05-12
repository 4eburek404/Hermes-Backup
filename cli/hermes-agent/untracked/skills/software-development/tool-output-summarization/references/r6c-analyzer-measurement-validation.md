# R6C — Analyzer Measurement Validation

## Purpose

Validate that the read-only context-overhead analyzer correctly quantifies
input-context overhead and that simulated tool-output compaction produces
measurable savings — without importing AIAgent or any runtime code.

## Key Distinction from R5A/R5B/R6A/R6B

R6C tests **analyzer module functions** (`estimate_standard_provider_input`,
`estimate_standard_provider_message_tokens`, `sanitize_message_for_standard_provider`,
`simulate_tool_output_summarization`, `analyzer.main()`), NOT the runtime
compaction gate (`_maybe_compact_tool_output`) or the compaction wrapper
(`compact_tool_output_with_artifact`). The analyzer is imported via
`importlib.util.spec_from_file_location` — same pattern as
`test_analyze_context_overhead.py`.

## Five Measurement Contracts

### 1. Baseline vs Compacted — Provider Input Reduction

Build two message lists that differ only in the tool-role `content` field:
- **Baseline**: large terminal output (200 lines × ~100 chars each)
- **Compacted**: short compact summary (~5 lines with restore pointer)

Assert via `estimate_standard_provider_input()`:
- `compacted_total < baseline_total` (strict reduction)
- `compacted_tool_tokens < baseline_tool_tokens` (savings from tool output)
- `message_content_tokens`, `assistant_tool_calls_tokens`,
  `reasoning_details_tokens` unchanged (no collateral reduction)
- `savings > 0`

### 2. Full Analyzer Pipeline Simulation

Write synthetic session snapshots to `tmp_path` via `_write_fixture()`,
invoke `analyzer.main()` with `--simulate-tool-output-summarization`:
- `sim["available"] is True`
- `sim["raw_tokens"] > 0 and sim["compact_tokens"] > 0`
- `sim["compact_tokens"] < sim["raw_tokens"]` (for large output)
- `sim["savings_tokens"] > 0`

### 3. Artifact Isolation

With `--simulate-tool-output-artifacts-dir=<explicit_dir>`:
- `artifacts["enabled"] is True`
- `artifacts["root"] == str(explicit_dir)`
- `artifacts["written_count"] >= 1`
- All `.raw` files exist only under `explicit_dir`
- No `.raw` files in other `tmp_path` subtrees (e.g., `work/`)

### 4. Read-Only Without Artifacts Dir

Without `--simulate-tool-output-artifacts-dir`:
- `artifacts["enabled"] is False`
- `artifacts["root"] is None`
- `artifacts["written_count"] == 0`
- Zero `.raw` files anywhere under `tmp_path`
- Only `.md` and `.json` reports created

### 5. codex_reasoning_items Excluded from Provider Input

Via `estimate_standard_provider_input()` and
`estimate_standard_provider_message_tokens()`:
- `codex_reasoning_items` in `excluded_fields`
- `codex_message_items` in `excluded_fields`
- `excluded_codex_reasoning_items_tokens > 0` (when items present)
- `estimated_tokens_total == estimate_payload_tokens(sanitized_message)`
  where sanitized has these fields removed
- `reasoning_details` is in `included_fields` (provider-bound, not storage)

## Synthetic Data Builder Pattern

```python
def _make_baseline_messages(large_terminal_output: str) -> list[dict]:
    """Baseline session messages with large terminal + codex_reasoning_items."""
    return [
        {"role": "system", "content": "You are a test assistant."},
        {"role": "user", "content": "Run the diagnostics command."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{...}],
            "codex_reasoning_items": [
                {"kind": "step", "text": "reasoning text " * 20},
            ],
            "codex_message_items": [
                {"kind": "message", "text": "draft"},
            ],
            "reasoning_details": [
                {"kind": "reasoning", "text": "proceeding..."},
            ],
        },
        {"role": "tool", "tool_call_id": "call_term_1", "name": "terminal",
         "content": large_terminal_output},
        {"role": "assistant", "content": "Diagnostics complete."},
    ]
```

The compacted variant replaces only the tool-role `content` with a short
summary string — all other messages are identical.

For `analyzer.main()` tests, use `_write_synthetic_sessions_dir()` to write
session snapshots + index JSON to `tmp_path`, then call `analyzer.main()`
with the index path and sessions dir.

## Fixture Writing Helper

```python
def _write_synthetic_sessions_dir(tmp_path, sessions):
    """Write session snapshots + index to tmp_path.
    Returns (index_path, sessions_dir)."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    for snap in sessions:
        sid = snap["session_id"]
        (sessions_dir / f"session_{sid}.json").write_text(
            json.dumps(snap), encoding="utf-8")
        index[f"test:{sid}"] = {
            "session_key": f"test:{sid}",
            "session_id": sid,
            "model": snap.get("model", "test-model"),
            "platform": snap.get("platform", "cli"),
            "input_tokens": 500,
            "output_tokens": 50,
        }
    index_path = tmp_path / "sessions.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return index_path, sessions_dir
```

## Test Flow

1. `python -m py_compile tests/test_tool_output_compaction_analyzer_measurement.py`
2. `pytest tests/test_tool_output_compaction_analyzer_measurement.py -q`
3. Regression: `pytest tests/test_analyze_context_overhead.py tests/test_tool_output_compaction_configured_smoke.py -q`
4. Safety: `git diff | grep -iE 'api_key|secret|password|bearer'` (expect synthetic only)
5. Stage only the new file, verify with `git diff --cached --name-only`
6. Commit with message referencing R6C

## Key Analyzer Functions Used

| Function | Purpose |
|----------|---------|
| `estimate_standard_provider_input(messages)` | Aggregate per-message provider token estimate |
| `estimate_standard_provider_message_tokens(msg)` | Per-message breakdown: included/excluded/uncertain fields |
| `sanitize_message_for_standard_provider(msg)` | Strip codex fields, invalid roles, internal IDs |
| `estimate_payload_tokens(value)` | JSON-recursive 4-chars-per-token estimator |
| `simulate_tool_output_summarization(snapshots, artifact_root)` | Run summarizer on snapshots, optionally write artifacts |
| `analyzer.main(argv)` | CLI entry point for full pipeline |
| `resolve_message_role(msg)` | Role/type fallback for message classification |