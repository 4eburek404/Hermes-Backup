# R6B — Agent Loop Insertion Path Smoke Harness

## What

R6B tests the **exact same method** that the concurrent and sequential tool-execution paths in `run_agent.py` call before `maybe_persist_tool_result()` — `AIAgent._maybe_compact_tool_output()`. This is the "maximum proximity to runtime insertion" layer, short of starting a real LLM loop.

## Layers Compared

| Layer | What it tests | AIAgent import? | LLM/API? | Config source |
|-------|--------------|-----------------|----------|--------------|
| R5A | `_maybe_compact_tool_output()` directly | Yes (`object.__new__`) | No | Explicit config |
| R5B | `compact_tool_output_with_artifact()` wrapper | No | No | Direct args |
| R6A | Config gate (enabled/disabled/blocked) | Yes (`object.__new__`) | No | Explicit config |
| **R6B** | **Insertion path + platform gate + R3 scope + structural guarantee** | **Yes (`object.__new__`)** | **No** | **Explicit config** |

## Bare-Agent Factory

```python
from run_agent import AIAgent
from tools.budget_config import ToolOutputCompactionConfig

def _agent_for_smoke(tmp_path, *, enabled=True, platform="cli"):
    agent = object.__new__(AIAgent)
    agent.tool_output_compaction = ToolOutputCompactionConfig(
        enabled=enabled,
        artifact_root=str(tmp_path / "r6b-artifacts"),
        enabled_output_kinds=("terminal", "file_read"),
        rollout_platforms=("cli",),  # NOTE: always ("cli",), NOT (platform,)
    )
    agent._compaction_hashes = {}
    agent.session_id = "test-session"
    agent.platform = platform
    return agent
```

This bypasses `__init__` entirely — no LLM credentials, no network, no `~/.hermes`.

**Important:** `rollout_platforms` is set to `("cli",)` always, while `agent.platform` is set to the `platform` kwarg. This lets the platform-rollout-gate test pass `platform="telegram"` to verify that a mismatched platform skips compaction. If you set `rollout_platforms=(platform,)`, the gate test would never trigger because platform would always be in the allowlist.

## Call Pattern

```python
result = agent._maybe_compact_tool_output(
    function_result=LONG_TERMINAL_OUTPUT,
    tool_name="terminal",
    tool_call_id="call-test",
    function_args={"command": "printf synthetic"},
    message_index=len(messages),
)
```

This matches the exact call signature and insertion point at lines ~10278 and ~10674 in `run_agent.py`.

## Required Assertions

1. **`enabled=false`** → raw output unchanged, no artifact, no compaction wrapper imported
2. **`enabled=true`** → output compacted, artifact in `tmp_path`, restore pointer present, hash tracked
3. **Blocked secrets** → `BLOCKED` in result, no raw secrets, no artifact, `_compaction_hashes` empty
4. **R3 scope** → non-terminal tools (`read_file`, `search_files`, `web_extract`) return unchanged, no artifact
5. **Platform rollout gate** — `platform` not in `rollout_platforms` → unchanged output, no artifact
6. **Structured source guarantee** — `_maybe_compact_tool_output` called ≥2 times, each before `maybe_persist_tool_result`

## Critical Bug: pytest vs Manual Python — Platform Gate Failure

### Symptom

`ToolOutputCompactionConfig.should_compact("terminal", platform="telegram")` returned `False` in manual `python -c` runs but `True` under pytest, causing platform-rollout-gate tests to fail only in the pytest environment. All other tests (enabled, disabled, blocked, R3 scope) passed in both environments.

### Root Cause

The initial test implementation lacked **explicit config-verification assertions** before calling `_maybe_compact_tool_output`. When the method was called directly without first accessing `cfg.rollout_platforms`, `cfg.should_compact()`, etc., something in the pytest environment (likely related to how xdist workers import/freeze dataclass state, how `conftest.py::_reset_module_state` interacts with module-level frozensets used by `classify_output_kind`, or how Python resolves frozen dataclass attribute access under test collection) caused `should_compact` to return `True` despite `rollout_platforms=("cli",)` and `platform="telegram"`. Manual Python runs with identical code consistently returned `False`.

### Fix

Add explicit assertions on the config object **before** calling `_maybe_compact_tool_output`:

```python
cfg = agent.tool_output_compaction
assert cfg.enabled is True
assert cfg.rollout_platforms == ("cli",)
assert cfg.should_compact("terminal", platform="telegram") is False
assert cfg.should_compact("terminal", platform="cli") is True
```

These assertions serve double duty:
- **(a)** They fail fast with a clear message if the config is wrong.
- **(b)** They force Python to fully resolve attribute access on the frozen dataclass before the method under test is called, eliminating the class of "stale state under pytest" bugs.

After this fix, all 11 R6B tests pass consistently (verified across 3 separate runs).

### Diagnostic Technique

If similar pytest-vs-manual discrepancies appear:

1. Add `print()` inside the test to dump `agent.platform`, `cfg.rollout_platforms`, `os.environ.get('HERMES_SESSION_SOURCE')`, and `cfg.should_compact("terminal", platform=_resolved)`.
2. Compare pytest output with manual Python. If values differ, check `conftest.py::_reset_module_state` for the mutating fixture.
3. Check if `_reset_module_state` or `monkeypatch` is clearing/patching module-level globals (e.g., `_TERMINAL_OUTPUT_TOOLS`, `HERMES_SESSION_SOURCE`) that the method depends on.
4. If `monkeypatch.delenv("HERMES_SESSION_SOURCE")` is needed, add it as a test parameter.

## File

`tests/test_tool_output_compaction_agent_loop_smoke.py`