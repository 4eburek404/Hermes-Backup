# Secret Scanning Pitfalls

Lessons learned from implementing `scan_secrets()` in `tool_output_summarizer.py`.

## 1. Word Boundary `\b` Blocks on Suffixes

**Problem:** `\b(?:API[_-]?KEY)\b` won't match `API_KEY_0` because `_0` after `KEY` is a word character, so `\b` at that position requires a non-word boundary.

**Fix:** Use `\b(?:API[_-]?KEY)\w*` to absorb suffixes like `_0`, `_ABC`, etc. This matches the full identifier before the `=` or `:` separator.

**Pattern that works:**
```python
r"\b(?:API[_-]?KEY|OPENAI_API_KEY|HASS_TOKEN)\w*[\s:=]+\S{4,}"
```

## 2. Overlapping/Nested Span Inflation

**Problem:** `DATABASE_URL=postgres://admin:secretpass@db.example.com:5432/mydb` matches:
- Pattern 1 (key=value): entire line, span (0, 60)
- Pattern 3 (postgres://): URL portion, span (12, 60)

Counting both = 2 matches for 1 secret value. With 5 such lines, you'd hit the block threshold (6) incorrectly.

**Fix:** Merge overlapping/nested spans before counting. Each merged span = 1 secret match.

```python
def _merge_spans(spans):
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s[0], s[1]))
    merged = [sorted_spans[0]]
    for start, end in sorted_spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
```

## 3. Greedy Value Matching

**Problem:** `[^\\s\\n]{10,}` in the value part can match more than intended, swallowing newlines from the next key-value pair.

**Fix:** Use `\S{4,}` or `[^\s\n]{4,}` for the value part, keeping a minimum length but not being overly greedy. Alternatively, match to end-of-line: `[^\n]{4,}`.

## 4. Fixture Isolation Per Contract Tier

| Tier | Match Count | Fixture Should Contain | Assertion |
|------|------------|----------------------|-----------|
| Clean | 0 | No secrets at all | `not is_blocked`, no `[REDACTED]` |
| Redacted | 1-5 | Exactly 3-5 unambiguous secrets | `not is_blocked`, `[REDACTED]` present |
| Blocked | ≥6 | 10+ distinct secrets | `is_blocked`, empty redacted string |

Never reuse the same fixture for redacted AND blocked tests. Secret count near the threshold (5-6) is ambiguous and fragile.

## 5. Test Fixture Format

Use synthetic values only. Never put real API keys, passwords, or tokens in test fixtures, even in regex patterns. Examples of safe synthetic values:

```
API_KEY=sk_test_abcdef1234567890abcdef
password=hunter2pass
DATABASE_URL=postgres://admin:secretpass@db.example.com:5432/mydb
```

These are clearly fake and will never authenticate anywhere.

## 6. pytest + xdist + PYTHONPATH

**Problem:** When `pyproject.toml` sets `addopts = "-n auto"` (xdist), running `pytest tests/test_file.py -q` may show "no tests ran" or `ModuleNotFoundError` because xdist workers start before module collection. `pytest tests/test_file.py` with `-n auto` via `LoadScheduling` distributes to workers that can't find the module.

**Fix:** Either:
- `python3 -m pytest tests/test_file.py -o addopts=""` (overrides addopts for this run)
- `PYTHONPATH=/repo/root pytest tests/test_file.py -q` (explicit PYTHONPATH)
- Use `python -m pytest` instead of bare `pytest` (module discovery differs)

Always verify the test path is inside the repo root and the import uses the repo's package structure.

## 7. write_file Path vs Repo Root

**Problem:** The `write_file` tool resolves paths relative to a default directory (often `~/`), not the git repo root. When working in a `/tmp/` checkout, `write_file` with a relative path puts files in the wrong location, outside the repo. Tests then fail with `ModuleNotFoundError` or "file not found" because the file isn't in the repo tree.

**Fix:** Always use the absolute repo path: `/tmp/hermes-fork-repo-name/scripts/file.py`, not `scripts/file.py`. After writing, verify with `ls -la /repo/path/file.py` and `git status --short` to confirm the file is tracked or at least in the working tree.

## 8. git Track vs write_file Path Divergence

**Problem:** If `write_file` creates or updates a file under `/home/konstantin/` instead of the repo root `/tmp/repo/`, `git status` shows the repo copy as deleted (` D`) because the actual working-tree file was overwritten with a different path. Running `git checkout HEAD -- path` restores the last-committed version, but any uncommitted changes are lost and must be re-applied.

**Fix:** After any `write_file` operation in a `/tmp/` repo, always run `ls -la /tmp/repo/path/file.py` and `git status --short` to confirm the file exists in the repo tree. If `git status` shows `D`, use `git checkout HEAD -- path` to restore, then re-apply your changes via patch or write_file with the correct absolute path.