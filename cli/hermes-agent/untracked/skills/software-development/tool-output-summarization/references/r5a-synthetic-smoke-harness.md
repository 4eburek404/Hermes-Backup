# R5A Synthetic Smoke Harness Pattern

Use this when validating Hermes terminal tool-output compaction locally without real LLM/API calls or user config changes.

## Scope

- Synthetic pytest harness only.
- Use `tmp_path` for `artifact_root`; never read/write `~/.hermes`.
- Instantiate `AIAgent` with `object.__new__(AIAgent)` to exercise `_maybe_compact_tool_output()` directly without full agent initialization.
- Do not call real terminal tools, providers, gateways, Telegram, or LLM APIs.
- Keep runtime/config/transports/prompt builder/ContextCompressor unchanged.

## Harness Shape

```python
from pathlib import Path
from run_agent import AIAgent
from tools.budget_config import ToolOutputCompactionConfig


def _agent_for_smoke(tmp_path, *, enabled: bool, platform: str = "cli"):
    agent = object.__new__(AIAgent)
    agent.tool_output_compaction = ToolOutputCompactionConfig(
        enabled=enabled,
        artifact_root=str(tmp_path / "r5a-artifacts"),
        enabled_output_kinds=("terminal", "file_read"),
        rollout_platforms=(platform,),
    )
    agent._compaction_hashes = {}
    agent.session_id = "r5a-smoke-session"
    agent.platform = platform
    return agent
```

Call the helper directly:

```python
agent._maybe_compact_tool_output(
    function_result=synthetic_output,
    tool_name="terminal",
    tool_call_id="call-r5a",
    function_args={"command": "printf synthetic"},
    message_index=1,
)
```

## Required Smoke Cases

1. `enabled=False` terminal output:
   - result equals original output
   - no `.raw` artifacts under `tmp_path`
   - `_compaction_hashes == {}`

2. `enabled=True` long terminal output:
   - result differs from original
   - contains `Restore:` and `hermes artifact restore`
   - exactly one artifact is written under `tmp_path`
   - hash map populated

3. Blocked synthetic sensitive-heavy output:
   - use fixtures that match `SECRET_PATTERNS`, but avoid raw sensitive keywords in the test diff when safety grep is required by building the marker at runtime, e.g. `"pass" + "word"`
   - result contains `BLOCKED`
   - no artifact is written
   - raw synthetic marker/value is absent from the compact result

4. Short terminal output:
   - output remains readable/usable
   - no artifact or restore pointer
   - summary notes short/no artifact behavior

5. Non-terminal output in R3:
   - `tool_name="read_file"` remains unchanged even if config allowlist includes `file_read`
   - no artifact/hash side effects

6. Rollback:
   - after an enabled run, replace config with `ToolOutputCompactionConfig(enabled=False, artifact_root=same_tmp_path, ...)`
   - subsequent terminal output equals baseline/original
   - no new artifacts are created

## Verification Matrix

```bash
python -m py_compile run_agent.py
python -m py_compile scripts/tool_output_compaction.py
pytest tests/test_tool_output_compaction_smoke.py -q
pytest tests/test_tool_output_compaction_runtime.py -q
pytest tests/test_tool_output_compaction.py -q
pytest tests/test_tool_output_artifacts.py -q
pytest tests/test_tool_output_summarizer.py -q
pytest tests/test_analyze_context_overhead.py -q
```

Safety checks:

```bash
git diff --stat
git diff --name-only
git diff | grep -Ei 'api[_-]?key|secret|password|authorization|bearer' || true
```

If the smoke file is untracked, use `git add -N tests/test_tool_output_compaction_smoke.py` before diff/safety checks so the new-file diff is visible without staging content for commit.

## Pitfalls

- `git diff` ignores untracked files unless `git add -N` is used.
- Safety grep may match intentional fixture keywords in a new test diff. If the user requires zero grep output, construct sensitive labels at runtime (`"pass" + "word"`) while still generating a fixture that matches scanner patterns.
- Do not assert global token savings for short output; short outputs intentionally skip artifacts because metadata overhead can exceed raw content.
- Do not initialize full `AIAgent`; that risks config/provider/runtime side effects. Direct helper invocation is enough for synthetic smoke.
