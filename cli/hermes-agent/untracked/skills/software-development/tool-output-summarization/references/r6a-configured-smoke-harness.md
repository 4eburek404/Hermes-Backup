# R6A — Configured Smoke Harness (Feature Flag Gate Tests)

Validates that `AIAgent._maybe_compact_tool_output()` correctly respects `ToolOutputCompactionConfig` flags, scope rules, and artifact isolation.

## Scope

- Exercises the **runtime gate** directly (`_maybe_compact_tool_output` on a synthetic `AIAgent` shell)
- Uses `object.__new__(AIAgent)` with explicit attribute assignment — no real provider/model/API
- `artifact_root` = `tmp_path / "r6a-artifacts"` — never `~/.hermes` or repo root
- Deterministic and offline

## Agent Shell Pattern

```python
from run_agent import AIAgent
from tools.budget_config import ToolOutputCompactionConfig

def _make_agent(tmp_path, *, enabled: bool, platform: str = "cli"):
    agent = object.__new__(AIAgent)
    agent.tool_output_compaction = ToolOutputCompactionConfig(
        enabled=enabled,
        artifact_root=str(tmp_path / "r6a-artifacts"),
        enabled_output_kinds=("terminal", "file_read"),
        rollout_platforms=(platform,),
    )
    agent._compaction_hashes = {}
    agent.session_id = "r6a-smoke-session"
    agent.platform = platform
    return agent
```

## Required Test Cases

### 1. Default/off path (`enabled=False`)
- Terminal output returned unchanged
- No artifact files under `tmp_path`
- `_compaction_hashes` remains `{}`

### 2. Enabled path (`enabled=True`)
- Long terminal output is compacted (result ≠ raw)
- Summary contains `Restore:` and `hermes artifact restore`
- Exactly one `.raw` artifact file under `tmp_path`
- Artifact file content ends with raw output
- `_compaction_hashes` populated
- Artifact root stays inside `tmp_path` (not `~/.hermes`)
- Short clean output: no artifact written (below threshold)

### 3. Blocked secret-heavy path (`enabled=True`)
- Uses fixtures triggering ≥6 `SECRET_PATTERNS` matches
- Build marker at runtime: `"pass" + "word"` to avoid safety grep hits
- Result contains `BLOCKED`
- Raw secret values absent from result
- No artifact files on disk
- When `enabled=False`, even secret-heavy output passes through unchanged (gate never fires)

### 4. R3 scope — non-terminal tools (`enabled=True`)
Even with compaction enabled, non-terminal tool names bypass compaction:
- `tool_name="read_file"` → output unchanged, no artifact
- `tool_name="search_files"` → output unchanged, no artifact
- `tool_name="write_file"` → output unchanged, no artifact
- `tool_name="web_search"` → output unchanged, no artifact
- `tool_name="custom_unknown_tool"` → output unchanged, no artifact

This validates `classify_output_kind()` routing and the R3 scope guard in `_maybe_compact_tool_output`.

## Key Assertions

| Path | Output unchanged? | Artifact? | Summary marker |
|------|-------------------|-----------|-----------------|
| disabled | Yes (exact equality) | No | — |
| enabled + terminal | No (compacted) | Yes, inside tmp_path | `Restore:` |
| enabled + blocked | No | No | `BLOCKED` |
| enabled + non-terminal | Yes | No | — |

## Verification

```bash
python -m py_compile tests/test_tool_output_compaction_configured_smoke.py
python -m py_compile run_agent.py
python -m py_compile scripts/tool_output_compaction.py
pytest tests/test_tool_output_compaction_configured_smoke.py -q
pytest tests/test_tool_output_compaction_runtime.py -q
pytest tests/test_tool_output_compaction_smoke.py -q  # R5A
pytest tests/test_tool_output_compaction_smoke_script.py -q  # R5B
```

## Harness Layer Comparison

| Layer | File | Pattern | AIAgent import? | Tests |
|-------|------|---------|-----------------|-------|
| R5A | `test_tool_output_compaction_smoke.py` | `object.__new__` + `_maybe_compact_tool_output` | Yes | Runtime gate + wrapper |
| R5B | `smoke_tool_output_compaction.py` + subprocess test | `compact_tool_output_with_artifact()` directly | No | Wrapper only |
| R6A | `test_tool_output_compaction_configured_smoke.py` | `object.__new__` + `_maybe_compact_tool_output` with explicit config | Yes | Config flag, scope, artifact isolation |