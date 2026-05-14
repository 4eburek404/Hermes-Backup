# Artifact Storage Utility Reference

## Module: `scripts/tool_output_artifacts.py`

Isolated utility for writing tool output artifacts to disk. No Hermes runtime imports.

## Path & URI Scheme

```
disk:  {root}/{session_id}/msg_{message_index:04d}_{tool_call_id}.raw
URI:   hermes-artifact://tool-output/{session_id}/{message_index}
default root: /tmp/hermes/artifacts
```

## File Format

```
version: 1
session_id: 20260510_213725_5c2af7
message_index: 42
tool_call_id: call_abc123
tool_name: terminal
output_kind: terminal
sha256: f5bb1432ffa3...
raw_size_bytes: 12345
created_at: 2026-05-11T00:30:00+00:00
redaction_status: clean|redacted|blocked
restore_command: hermes artifact restore hermes-artifact://tool-output/...
---
<body here>
```

## Write Behavior by Tier

| Tier        | Body written               | `artifact_ref` | File created |
|-------------|---------------------------|----------------|-------------|
| clean       | Raw output verbatim        | URI            | Yes         |
| redacted    | `redacted_output` parameter | URI            | Yes         |
| blocked     | Nothing                    | `None`         | No          |

For redacted tier: if `redacted_output` is not provided, raw output is written (fallback).

## Security

### Path Traversal Defense

`_sanitize_path_component()` validates all user-provided path components (session_id, tool_call_id):
- Rejects `..`, null bytes (`\x00`), empty strings, whitespace-only, `.`-only
- Strips leading/trailing slashes
- Raises `ValueError` on unsafe input

### Atomic Write Pattern

1. Write to `{path}.tmp`
2. `f.flush()` + `os.fsync(f.fileno())`
3. `os.replace(tmp_path, path)`
4. Cleanup `.tmp` on any exception

### Permissions

- Directories: `0o700` (owner rwx only)
- Files: `0o600` (owner rw only)
- `os.chmod()` after replace; non-fatal if it fails (e.g., read-only FS)

## API

### `write_artifact()`

```python
result: ArtifactResult = write_artifact(
    raw_output: str,
    *,
    session_id: str,          # validated for traversal
    message_index: int,
    tool_call_id: str,        # validated for traversal
    tool_name: str = "",
    output_kind: str = "unknown",
    redaction_status: str = "clean",  # "clean" | "redacted" | "blocked"
    redacted_output: str | None = None,  # only for "redacted"
    root: Path | None = None,  # default: /tmp/hermes/artifacts
)
```

Returns `ArtifactResult` dataclass:
- `artifact_ref`: URI or `None` (blocked)
- `path`: filesystem path or `None` (blocked)
- `sha256`: hex digest of raw output (always computed)
- `status`: "clean" | "redacted" | "blocked"
- `raw_size_bytes`: byte length of raw output
- `restore_command`: CLI restore string or `None` (blocked)

### `read_artifact_header()`

```python
header: dict = read_artifact_header(path: Path | str)
# Returns: {"version": "1", "session_id": ..., "message_index": int, ...}
```

Auto-converts `message_index` and `raw_size_bytes` to `int`.

### `read_artifact_body()`

```python
body: str = read_artifact_body(path: Path | str)
# Returns raw output text with leading \n stripped after --- separator
```

**Important:** splits on first `---` and strips exactly one leading `\n` after it. This matches the format produced by `_build_header()` + `f"{header}\n---\n{body}"`.

## Test Patterns

### Using `tmp_path` as artifact root

```python
def test_something(tmp_path):
    result = write_artifact("content", session_id="s1", message_index=0,
                            tool_call_id="c1", redaction_status="clean",
                            root=tmp_path)
    assert result.artifact_ref is not None
    assert Path(result.path).exists()
```

### Path traversal rejection

```python
def test_traversal(tmp_path):
    with pytest.raises(ValueError, match="[Uu]nsafe"):
        write_artifact("data", session_id="../../etc", ...)
```

**Note:** `match="unsafe"` fails because error messages use title case (`Unsafe`). Use `[Uu]nsafe` or a case-insensitive pattern.

### Blocked tier writes nothing

```python
result = write_artifact(raw_secrets, session_id="s", message_index=0,
                        tool_call_id="c", redaction_status="blocked",
                        root=tmp_path)
assert result.artifact_ref is None
assert result.path is None
assert list(tmp_path.rglob("*.raw")) == []
```

## Implementation Checklist

- [ ] Path traversal validation on session_id and tool_call_id
- [ ] Atomic write with fsync + os.replace
- [ ] Permission enforcement (0700 dir, 0600 file)
- [ ] Blocked tier: no file, artifact_ref=None
- [ ] Redacted tier: write redacted_output, not raw
- [ ] Clean tier: write raw output
- [ ] Leading newline strip in read_artifact_body
- [ ] test fixtures use `tmp_path` as root, never `~/.hermes`