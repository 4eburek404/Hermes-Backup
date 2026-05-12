# Tool-Output Insertion Points for compact_tool_output_with_artifact()

**Created:** 2025-05-11 | **Branch:** context-input-baseline | **Commit:** 301af4ca
**Status:** R1 — Insertion-point documentation only. No runtime changes.

Full document lives in the repo at `docs/context-tool-output-insertion-points.md`.

## Purpose

Pinpoints the exact locations in `run_agent.py` where `compact_tool_output_with_artifact()` should be
called in future tasks R2/R3. This is the authoritative reference for what data is available, what's
missing, and why insertion before `maybe_persist_tool_result()` is preferred.

## Flow Summary

```
LLM response with tool_calls
  │
  ▼
_execute_tool_calls()                          ← dispatcher (L9676)
  │
  ├── _execute_tool_calls_concurrent()          ← parallel path (L9828)
  │     │
  │     ├── per-tool: _invoke_tool() → function_result
  │     │     │
  │     │     ├── guardrail observation
  │     │     ├── logging / callbacks
  │     │     │
  │     │     ▼
  │     │   ★ INSERTION POINT A (L10170–10178) ★
  │     │   maybe_persist_tool_result(function_result, ...)
  │     │     │
  │     │     ▼
  │     │   subdir_hints append
  │     │   tool_msg = {"role":"tool", "content": function_result}
  │     │   messages.append(tool_msg)
  │     │   _apply_pending_steer_to_tool_results(messages, 1)
  │     │
  │     └── (loop over all tool_calls)
  │            │
  │            ▼
  │     enforce_turn_budget(messages[-N:])           ← L10194
  │     _apply_pending_steer_to_tool_results(messages, N)  ← L10200
  │
  └── _execute_tool_calls_sequential()           ← serial path (L10209)
        │
        ├── per-tool: handle_function_call() → function_result
        │     │
        │     ├── guardrail observation
        │     ├── logging / callbacks
        │     │
        │     ▼
        │   ★ INSERTION POINT B (L10558–10572) ★
        │   maybe_persist_tool_result(function_result, ...)
        │     │
        │     ▼
        │   subdir_hints append
        │   tool_msg = {"role":"tool", "content": function_result}
        │   messages.append(tool_msg)
        │   _apply_pending_steer_to_tool_results(messages, 1)
        │
        └── (loop over all tool_calls)
               │
               ▼
        enforce_turn_budget(messages[-N:])            ← L10614
        _apply_pending_steer_to_tool_results(messages, N)  ← L10620
```

## Insertion Point A — Concurrent Path

**File:** `run_agent.py`
**Method:** `_execute_tool_calls_concurrent()`
**Line range:** 10170–10178 (as of commit 301af4ca)

### Current code

```python
# L10170–10178
function_result = maybe_persist_tool_result(
    content=function_result,
    tool_name=name,
    tool_use_id=tc.id,
    env=get_active_env(effective_task_id),
)

subdir_hints = self._subdirectory_hints.check_tool_call(name, args)
if subdir_hints:
    function_result += subdir_hints

tool_msg = {
    "role": "tool",
    "name": name,
    "content": function_result,
    "tool_call_id": tc.id,
}
messages.append(tool_msg)
```

### Available data

| Variable | Type | Source | Notes |
|---|---|---|---|
| `function_result` | `str` | Tool execution return | Raw tool output — this is what we compact |
| `name` | `str` | `tc.function.name` | Tool name (e.g., "terminal", "read_file") |
| `tc.id` | `str` | OpenAI tool_call ID | Unique per-call identifier |
| `args` | `dict` | Parsed `tc.function.arguments` | Tool arguments — has `command`, `path`, etc. |
| `effective_task_id` | `str` | Method parameter | Task/session identifier |
| `self.session_id` | `str` | Agent attribute | Session ID — maps to `session_id` in CompactionResult |
| `messages` | `list[dict]` | In-flight message list | `len(messages)` ≈ `message_index` |
| `tool_duration` | `float` | Timed execution | Duration of tool call |
| `is_error` | `bool` | Failure detection | Whether the tool errored |
| `blocked` | `bool` | Guardrail result | Whether tool was blocked |
| `env` | `BaseEnvironment` | `get_active_env()` | Sandbox environment (for persistence) |

## Insertion Point B — Sequential Path

**File:** `run_agent.py`
**Method:** `_execute_tool_calls_sequential()`
**Line range:** 10558–10572 (as of commit 301af4ca)

### Current code

```python
# L10558–10572
function_result = maybe_persist_tool_result(
    content=function_result,
    tool_name=function_name,
    tool_use_id=tool_call.id,
    env=get_active_env(effective_task_id),
)

subdir_hints = self._subdirectory_hints.check_tool_call(function_name, function_args)
if subdir_hints:
    function_result += subdir_hints

tool_msg = {
    "role": "tool",
    "name": function_name,
    "content": function_result,
    "tool_call_id": tool_call.id
}
messages.append(tool_msg)
```

### Available data

| Variable | Type | Source | Notes |
|---|---|---|---|
| `function_result` | `str` | Tool execution return | Raw tool output |
| `function_name` | `str` | `tool_call.function.name` | Tool name |
| `tool_call.id` | `str` | OpenAI tool_call ID | Unique per-call identifier |
| `function_args` | `dict` | Parsed `tool_call.function.arguments` | Tool arguments |
| `effective_task_id` | `str` | Method parameter | Task/session identifier |
| `self.session_id` | `str` | Agent attribute | Session identifier |
| `messages` | `list[dict]` | In-flight message list | `len(messages)` ≈ `message_index` |
| `tool_duration` | `float` | Timed execution | Duration |
| `_is_error_result` | `bool` | Failure detection | Whether tool errored |
| `_execution_blocked` | `bool` | Guardrail result | Whether tool was blocked |
| `env` | `BaseEnvironment` | `get_active_env()` | Sandbox environment |

## Variable Name Mapping Between Paths

| Insertion Point A (concurrent) | Insertion Point B (sequential) |
|---|---|
| `name` | `function_name` |
| `tc.id` | `tool_call.id` |
| `args` | `function_args` |
| `blocked` | `_execution_blocked` |

This is critical for R3 implementation — the same compaction call must use the correct
variable name depending on which path it's in.

## Data That Needs Derivation

| Field | Derivation | Notes |
|---|---|---|
| `output_kind` | `_classify_output(tool_name, args)` | New helper — maps tool name to `terminal`/`file_read`/`other`. Must be introduced. |
| `exit_code` | Parse from `function_result` or pass from tool | Terminal tool includes exit code in structured output but not as a separate field. |
| `file_path` | `function_args.get("path")` | Available for `read_file`, `search_files`. Missing for terminal. |
| `command` | `function_args.get("command")` | Available for `terminal`. Missing for file tools. |

## Data NOT Available at Insertion Points

| Field | Why missing | Impact |
|---|---|---|
| Exact `message_index` before append | `len(messages)` is approximate (steer injections, etc. may change count between tool calls) | Low — `tool_call_id` provides uniqueness |
| `line_range` | Not produced by tools | Low — optional field in ToolMetadata, defaults to None |
| `previous_hashes` | Not tracked in AIAgent currently | Medium — must be added as `self._compaction_hashes: Dict[str, str]` in R3 |

## Proposed _classify_output Helper

```python
_TERMINAL_TOOLS = frozenset({
    "terminal", "execute_code", "shell", "bash",
})
_FILE_TOOLS = frozenset({
    "read_file", "search_files", "write_file", "patch",
})

def _classify_output(tool_name: str, tool_args: dict) -> str:
    if tool_name in _TERMINAL_TOOLS:
        return "terminal"
    if tool_name in _FILE_TOOLS:
        return "file_read"
    return "other"
```

This differs from `classify_output_kind()` in `tool_output_summarizer.py` which uses
content heuristics (exit_code, file_path). The runtime version maps by tool name,
which is deterministic and doesn't require parsing the result.

## Why Before maybe_persist_tool_result()

1. **Security:** Secrets are scanned BEFORE entering message history or being persisted to sandbox disk
2. **Composability:** Compaction → summary (short) → `maybe_persist_tool_result()` on summary is usually a no-op; persistence is a safety net for unusually long summaries
3. **Zero impact when disabled:** `enabled=False` means `function_result` passes through unchanged

## Why Not ContextCompressor

1. **Too late:** Secrets already in message history for multiple turns
2. **Different purpose:** Compressor handles token budget; compaction handles secret protection + size reduction
3. **Non-deterministic:** Compressor runs only near capacity — some outputs compacted, others not
4. **No artifact lifecycle:** Compressor has no concept of disk artifacts or restore pointers
5. **Risk of dangling pointers:** Compressor might trim a tool-result message containing an artifact reference

Future: Compressor should be made **aware** of artifact pointers (never trim messages with `artifact_ref`).

## Session Snapshot Considerations

- Tool results stored in message list are flushed to SessionDB via `_flush_session_db()` (~L4034)
- After compaction, SessionDB will contain **summaries** (not raw outputs)
- Artifacts in `/tmp/hermes/artifacts/` are ephemeral (OS temp cleanup)
- On session resume, agent sees summaries and can retrieve full content via `read_file`

## Source Locations (as of commit 301af4ca)

| Component | File | Line Range |
|-----------|------|------------|
| Tool result persistence (concurrent) | `run_agent.py` | L10170–10178 |
| Tool result persistence (sequential) | `run_agent.py` | L10558–10572 |
| `maybe_persist_tool_result()` | `tools/tool_result_storage.py` | L116 |
| `enforce_turn_budget()` | `tools/tool_result_storage.py` | L175 |
| BudgetConfig | `tools/budget_config.py` | L24 |
| `_execute_tool_calls_concurrent()` | `run_agent.py` | L9828 |
| `_execute_tool_calls_sequential()` | `run_agent.py` | L10209 |
| `_execute_tool_calls()` (dispatcher) | `run_agent.py` | L9676 |