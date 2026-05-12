# Compaction Wrapper Reference

## Module: `scripts/tool_output_compaction.py`

Isolated wrapper that links the summarizer (`tool_output_summarizer.py`) with artifact storage (`tool_output_artifacts.py`). Single entry point: `compact_tool_output_with_artifact()`.

No Hermes runtime imports. No writes to `~/.hermes`.

## Pipeline

```
raw_output
  → dedup check (previous_hashes)
  → secret scanning (redact_or_block)
  → blocked? → CompactionResult(blocked, no artifact)
  → short clean? → CompactionResult(clean, no artifact, summary=verbatim)
  → write_artifact (clean or redacted body)
  → summarize_tool_output (compact summary)
  → merge summary + artifact_ref + restore_command
  → CompactionResult
```

## API: `compact_tool_output_with_artifact()`

```python
result: CompactionResult = compact_tool_output_with_artifact(
    raw_output: str,
    *,
    session_id: str,
    message_index: int,
    tool_call_id: str,
    tool_name: str = "",
    output_kind: str = "unknown",
    metadata: ToolMetadata | None = None,   # forward to summarizer
    artifact_root: Path | None = None,       # default: /tmp/hermes/artifacts
    previous_hashes: dict[str, str] | None = None,  # sha256 → artifact_ref
)
```

### `CompactionResult` dataclass

| Field              | Type             | Description                                       |
|--------------------|------------------|---------------------------------------------------|
| `compact_summary`  | `str`            | Combined summary text with artifact ref + restore |
| `artifact_ref`     | `str \| None`    | `hermes-artifact://...` URI or `None` (blocked/short/dedup) |
| `artifact_path`    | `str \| None`    | Disk path or `None`                               |
| `sha256`           | `str`            | SHA-256 of raw output (always computed)           |
| `redaction_status` | `str`            | `"clean"` / `"redacted"` / `"blocked"`            |
| `size`             | `int`            | Byte length of raw output                         |
| `line_count`       | `int`            | Line count of raw output                          |
| `restore_command`  | `str \| None`     | `hermes artifact restore <URI>` or `None`         |
| `dedup_ref`        | `str \| None`     | Previous artifact_ref if dedup, else `None`       |

Properties: `is_blocked → bool`, `has_artifact → bool`.

## Behavior by Tier

### Clean (0 secrets, output ≥ 200 chars)

- Artifact: written with raw body, `redaction_status: clean`
- Summary: summarizer output + `Restore: hermes artifact restore <URI>`
- `artifact_ref`: present

### Clean short (0 secrets, output < 200 chars)

- Artifact: **not written** (overhead exceeds content size)
- Summary: summarizer output + `(Output short enough — no artifact stored)`
- `artifact_ref`: `None`

### Redacted (1–5 secrets)

- Artifact: written with `[REDACTED]` body, `redaction_status: redacted`
- Summary: `⚠️ Output contains N redacted secret(s).` + summarizer output + Restore line
- `artifact_ref`: present
- Header: `redaction_status: redacted`

### Blocked (≥6 secrets)

- Artifact: **not written**
- Summary: `BLOCKED: Output contains N secret matches (threshold=6). Artifact not written.`
- `artifact_ref`: `None`, `path`: `None`, `restore_command`: `None`
- sha256: still computed on raw output (for audit logging)

### Dedup (same sha256 in previous_hashes)

- Artifact: **not written** (original already stored)
- Summary: `Repeated output (identical to <ref>). See original artifact for full content.`
- `dedup_ref`: the previous `artifact_ref`
- `artifact_ref`: `None`

## Short Output Threshold

`SHORT_OUTPUT_SKIP_ARTIFACT_CHARS = 200`. Outputs below this threshold skip artifact creation unless they contain secrets (which always require an artifact for the redacted version).

## Path Traversal Defense

`session_id` and `tool_call_id` are validated early in `compact_tool_output_with_artifact()` via `_sanitize_path_component()` before reaching artifact storage. Invalid values raise `ValueError` immediately — even for blocked outputs that would never write a file.

## Test Patterns

### Clean long terminal output

```python
result = compact_tool_output_with_artifact(
    LONG_OUTPUT, session_id="sess-001", message_index=5,
    tool_call_id="call-1", tool_name="terminal",
    metadata={"tool_name": "terminal", "session_id": "sess-001",
              "message_index": 5, "tool_call_id": "call-1",
              "exit_code": 0, "file_path": None, "line_range": None,
              "command": "ls -la"},
    artifact_root=tmp_path,
)
assert result.redaction_status == "clean"
assert result.artifact_ref is not None
assert result.has_artifact is True
```

### Blocked output

```python
# Use patterns that actually match SECRET_PATTERNS, e.g. "password=..."
blocked_raw = "\n".join(
    f"password=verysecretvalue_{i}_extracharshere"
    for i in range(7)  # > SECRET_BLOCK_THRESHOLD (6)
)
result = compact_tool_output_with_artifact(
    blocked_raw, session_id="sess-blk", message_index=0,
    tool_call_id="call-blk", tool_name="terminal",
    artifact_root=tmp_path,
)
assert result.is_blocked
assert list(tmp_path.rglob("*.raw")) == []
```

### Dedup

```python
first = compact_tool_output_with_artifact(LONG_OUTPUT, ...)
previous_hashes = {first.sha256: first.artifact_ref}
second = compact_tool_output_with_artifact(
    LONG_OUTPUT, ..., previous_hashes=previous_hashes,
)
assert second.dedup_ref is not None
assert "Repeated" in second.compact_summary
```

## Pitfalls

1. **"SECRET_N=value_N" doesn't match SECRET_PATTERNS.** The patterns target `password`, `api_key`, `Bearer`, `postgres://`, etc. — not generic `SECRET_` assignments. For blocked fixtures, use patterns that actually trigger matches: `password=longvaluehere`, `API_KEY=sk-...`, etc.

2. **`redaction_status` must be computed before `is_short_clean` check.** The variable is derived from `redacted_ranges` (not `is_blocked`) and must be assigned before `is_short_clean` references it. Otherwise: `UnboundLocalError`.

3. **Path validation must happen before blocked return.** Even though blocked outputs never write files, the `session_id` and `tool_call_id` should be validated early (before the blocked return) so that callers get consistent `ValueError` on bad inputs regardless of tier.

4. **Metadata dict is mutated by `setdefault`.** `compact_tool_output_with_artifact` calls `metadata.setdefault()` on the caller's dict. If the caller reuses the dict across calls, stale defaults from a previous call may persist. This matches the summarizer's behavior but is worth noting.

## Implementation Checklist

- [ ] Call `_sanitize_path_component()` on `session_id` and `tool_call_id` early
- [ ] Compute `redaction_status` from `redacted_ranges` before `is_short_clean`
- [ ] For blocked: return CompactionResult without calling `write_artifact` or `summarize_tool_output`
- [ ] For short clean: return CompactionResult with `artifact_ref=None`, no `write_artifact` call
- [ ] For dedup: return CompactionResult with `dedup_ref`, no `write_artifact` call
- [ ] For clean/redacted: write artifact, then generate summary, merge both
- [ ] Use `tmp_path` in tests, never `~/.hermes` or `/tmp/hermes/artifacts`