# Analyzer Simulation Mode

## Purpose

The `analyze_context_overhead.py` script has a `--simulate-tool-output-summarization` flag that runs `summarize_tool_output()` on all tool-role messages in session snapshots in **read-only mode**. When combined with `--simulate-tool-output-artifacts-dir PATH`, it also invokes `compact_tool_output_with_artifact()` to write artifacts and collect artifact stats. It does NOT modify session files or touch the Hermes runtime.

## CLI Usage

**Dry-run (no artifacts):**
```bash
python3 scripts/analyze_context_overhead.py \
  --sessions-index tests/fixtures/context_overhead/sessions_index_minimal.json \
  --sessions-dir tests/fixtures/context_overhead \
  --simulate-tool-output-summarization \
  --out-md /tmp/hermes_summary_sim.md \
  --out-json /tmp/hermes_summary_sim.json
```

**With artifacts:**
```bash
python3 scripts/analyze_context_overhead.py \
  --sessions-index tests/fixtures/context_overhead/sessions_index_minimal.json \
  --sessions-dir tests/fixtures/context_overhead \
  --simulate-tool-output-summarization \
  --simulate-tool-output-artifacts-dir /tmp/hermes_summary_sim_artifacts \
  --out-md /tmp/hermes_summary_sim_artifacts.md \
  --out-json /tmp/hermes_summary_sim_artifacts.json
```

For real session data:
```bash
python3 scripts/analyze_context_overhead.py \
  --sessions-index ~/.hermes/sessions/sessions.json \
  --sessions-dir ~/.hermes/sessions \
  --limit 20 \
  --simulate-tool-output-summarization \
  --simulate-tool-output-artifacts-dir /tmp/hermes_summary_sim_artifacts \
  --out-md /tmp/hermes_summary_sim_artifacts.md \
  --out-json /tmp/hermes_summary_sim_artifacts.json
```

## CLI Flags

| Flag | Type | Default | Purpose |
|------|------|---------|---------|
| `--simulate-tool-output-summarization` | store_true | False | Run read-only summarization on tool messages |
| `--simulate-tool-output-artifacts-dir` | Path | None | When set, write artifacts via `compact_tool_output_with_artifact()` |

**Behavior matrix:**

| `--simulate-tool-output-summarization` | `--simulate-tool-output-artifacts-dir` | Behavior |
|---------|---------|----------|
| ❌ | — | No simulation section in report |
| ✅ | — | Simulation stats only; `artifacts.enabled=False`, no files written |
| ✅ | PATH | Full simulation; `artifacts.enabled=True`, artifacts written to PATH |

**No default artifact directory** — `artifact_root` is `None` unless explicitly provided. The `/tmp/hermes/artifacts` default from `tool_output_artifacts.py` is never used in simulation mode.

## JSON Report Structure

The `tool_output_summarization_simulation` key contains:

```json
{
  "available": true,
  "tool_message_count": 1857,
  "raw_tokens": 782216,
  "compact_tokens": 286783,
  "savings_tokens": 495433,
  "savings_percent": 63.34,
  "secret_scan_counts": { "clean": 1787, "redacted": 49, "blocked": 21 },
  "output_kind_counts": { "file_read": 259, "short_output": 374, "terminal": 571 },
  "dedup_candidate_count": 1332,
  "top_predicted_savings": [ ... ],
  "artifacts": {
    "enabled": true,
    "root": "/tmp/hermes_summary_sim_artifacts",
    "written_count": 314,
    "redacted_count": 49,
    "blocked_count": 21,
    "dedup_count": 1332,
    "skipped_short_count": 190,
    "total_artifact_bytes": 1072369,
    "sample_artifact_refs": [
      "hermes-artifact://tool-output/session-id/2",
      ...
    ]
  }
}
```

If `tool_output_summarizer` module is not importable, `available` is `false` with an `error` message. If `compact_tool_output_with_artifact` is not importable but `--simulate-tool-output-artifacts-dir` is set, `artifacts.enabled` will be `false` and a note will appear in the report.

## Markdown Report Sections

When `--simulate-tool-output-summarization` is set:

**Tool output summarization simulation:**
- Tool messages processed count
- Raw / compact / savings tokens and percent
- Secret scan breakdown (clean/redacted/blocked)
- Dedup candidate count
- Output kind distribution
- Top 10 outputs by predicted savings

**Artifact simulation** (always present when summarization is enabled):

When `artifacts.enabled=false`:
```
## Artifact simulation
- **Not enabled**: artifact simulation requires --simulate-tool-output-artifacts-dir
```

When `artifacts.enabled=true`:
```
## Artifact simulation
- **enabled**: `/path/to/artifacts`
- written: 314
- redacted: 49
- blocked: 21
- dedup: 1332
- skipped (short): 190
- total artifact bytes: 1,072,369

### Sample artifact refs
- `hermes-artifact://tool-output/session-id/2`
...

> **Note**: simulation only, no runtime integration
```

## Key Implementation Details

- **Function**: `simulate_tool_output_summarization(session_snapshots, *, artifact_root=None)` in `analyze_context_overhead.py`
- **Integration point**: Called from `summarize()` via `run_tool_output_summarization_sim=True` and `artifact_root=Path|None` kwargs
- **Import**: Lazy `from scripts.tool_output_summarizer import ...` — script works without it (returns `available: False`). Also lazy-imports `compact_tool_output_with_artifact` when `artifact_root` is provided.
- **`_ensure_scripts_importable()`**: Must be called before lazy imports when running as standalone subprocess. Adds `Path(__file__).resolve().parent.parent` to `sys.path` so `scripts.*` imports resolve. Without this, `python scripts/analyze_context_overhead.py` subprocess tests fail with `available: False`.
- **Dedup tracking**: `seen_hashes` dict accumulates `sha256 → tool_call_id` across all snapshots, so repeated outputs across sessions are detected.
- **Previous hashes ordering**: Artifact compaction (`compact_tool_output_with_artifact`) MUST run **before** the current hash is added to `seen_hashes`. Otherwise the current output's sha256 is already in the map, causing every output to be incorrectly marked as a dedup duplicate. Correct order: (1) `summarize_tool_output()` with `previous_hashes=seen_hashes.copy()`, (2) `compact_tool_output_with_artifact()` with `previous_hashes=seen_hashes`, (3) `seen_hashes[result.sha256] = tool_call_id`.
- **Tool name resolution**: Builds `tool_call_id → tool_name` map from assistant messages' `tool_calls` field, not just the `name` field on the result message.
- **artifact_root**: When `None` (default), no artifacts are written; `artifacts.enabled=False`. When a Path is given and the compaction module imports, artifacts are written to that directory; `artifacts.enabled=True`. No default path is ever used.

## Artifact Count Semantics

| Count | Meaning |
|-------|---------|
| `written_count` | Clean + redacted artifacts actually written to disk |
| `redacted_count` | Outputs where secrets were found and redacted (artifact written with redacted body) |
| `blocked_count` | Outputs blocked due to ≥6 secrets (no artifact written) |
| `dedup_count` | Outputs matching a previous sha256 in `previous_hashes` (no artifact written, dedup reference returned) |
| `skipped_short_count` | Clean outputs below `SHORT_OUTPUT_SKIP_ARTIFACT_CHARS` (200 chars) — no artifact written |
| `total_artifact_bytes` | Sum of `CompactionResult.size` for written artifacts only |
| `sample_artifact_refs` | Up to 10 `artifact_ref` URIs from written artifacts |

The totals: `written_count + blocked_count + dedup_count + skipped_short_count = tool_message_count` (when `redacted_count` is already included in `written_count`).

## Test Helpers for Analyzer Integration Tests

When testing `analyze_context_overhead.py` CLI flags with custom fixtures (not the static `sessions_index_minimal.json`), create session snapshots dynamically:

```python
def _make_session_snapshot(session_id="sess-art", tool_messages=None):
    """Build a minimal session snapshot dict with the given tool-role messages.
    Each tool_message dict: content, tool_call_id, tool_name."""
    messages = [
        {"role": "system", "content": "You are a test assistant."},
        {"role": "user", "content": "Do something"},
    ]
    for idx, tm in enumerate(tool_messages or []):
        tc_id = tm.get("tool_call_id", f"call_{idx}")
        messages.append({"role": "assistant", "content": "",
            "tool_calls": [{"id": tc_id, "type": "function",
                "function": {"name": tm.get("tool_name", "terminal"), "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": tc_id,
            "name": tm.get("tool_name", "terminal"), "content": tm.get("content", "")})
    messages.append({"role": "assistant", "content": "Done."})
    return {"session_id": session_id, "model": "test-model", "platform": "test", "messages": messages}

def _write_fixture(tmp_path, snapshot, index_entries=None):
    """Write sessions index + session snapshot JSON files, return (index_path, sessions_dir).
    Uses tmp_path for isolation — no ~/.hermes writes."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = sessions_dir / f"session_{snapshot['session_id']}.json"
    snapshot_file.write_text(json.dumps(snapshot), encoding="utf-8")
    if index_entries is None:
        index_entries = [{"session_key": f"test:{snapshot['session_id']}",
            "session_id": snapshot["session_id"], "model": "test-model",
            "platform": "test", "input_tokens": 100, "output_tokens": 20}]
    index = {e["session_key"]: e for e in index_entries}
    index_path = tmp_path / "sessions.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return index_path, sessions_dir
```

### Test fixture content for tier verification

| Tier | Content | Expected outcome |
|------|---------|-------------------|
| **Blocked** (≥6 secrets) | 6× `API_KEY_N=secret_value_N_here` (matches `SECRET_PATTERNS`) | `is_blocked=True`, no artifact written, `blocked_count++` |
| **Redacted** (1–5 secrets) | `aws_access_key_id=AKIA... aws_secret_access_key=wJalr...` | `redaction_status=redacted`, artifact written, `redacted_count++` |
| **Short clean** (<200 chars) | `"short output"` | `artifact_ref=None`, `skipped_short_count++` |
| **Long clean** (≥200 chars) | ~20 lines of `ls -la` output | `artifact_ref` set, `written_count++` |
| **Dedup** | Same content as prior call | `dedup_ref` set, no new artifact, `dedup_count++` |

### Key test cases (6 required for full coverage)

1. **dry-run no artifacts dir**: `--simulate-tool-output-summarization` without `--simulate-tool-output-artifacts-dir` → `artifacts.enabled=False`, no files written
2. **artifacts dir writes clean**: Long clean output → `written_count >= 1`, artifact file on disk
3. **blocked output no artifact**: 6+ secrets → `blocked_count >= 1`, `written_count == 0`
4. **redacted output artifact**: 1–5 secrets → `redacted_count >= 1`, `written_count >= 1`
5. **short output skips**: <200 chars → `skipped_short_count >= 1`, `written_count == 0`
6. **JSON and Markdown stats**: Mixed output → all required keys in JSON `artifacts` section, `## Artifact simulation` and `simulation only, no runtime integration` in Markdown

## Baseline Results (Real Session Data, 20 Sessions)

| Metric | Value |
|--------|-------|
| Tool messages | 1,857 |
| Raw tokens | 782,216 |
| Compact tokens | 286,783 |
| **Savings** | **495,433 (63.34%)** |
| Secrets clean | 1,787 |
| Secrets redacted | 49 |
| Secrets blocked | 21 |
| Dedup candidates | 1,332 |
| Artifacts written | 314 |
| Artifacts skipped (short) | 190 |
| Artifacts blocked | 21 |
| Total artifact bytes | 1,072,369 |
| Long tail | Short outputs have negative savings (metadata > content) |