# R7A — Runtime-Path Mock Harness

## What R7A Adds Beyond R6B

R6B tests the return value of `_maybe_compact_tool_output()`. R7A tests
the **injected message content** in the `messages` list — what the LLM
actually sees on the next API iteration.

The helper `_simulate_runtime_tool_path()` reproduces the full runtime
code path from `run_conversation()`:

```
_maybe_compact_tool_output(function_result, ...)
→ maybe_persist_tool_result(content, ...)   # stubbed (offline passthrough)
→ tool_msg = {"role": "tool", "name": ..., "content": ..., "tool_call_id": ...}
→ messages.append(tool_msg)
```

Asserting on `messages[0]["content"]` proves the compacted/blocked/passthrough
content reaches the conversation correctly — not just that the compaction
method returns the right value.

## maybe_persist_tool_result Stubbing

The real `maybe_persist_tool_result()` requires `env.execute()` for
sandbox writes, which isn't available in unit tests. The stub:

```python
persisted = compacted  # stub: no env available, content passes through
```

This is correct because `maybe_persist_tool_result` only activates for
outputs exceeding its threshold, and compaction summaries are usually
short enough to be a no-op under that threshold. To test the persist step
itself (preview + file path reference), one would need a `tmp_path`-backed
`env` mock — that's R7B territory.

## Bare-Agent Factory

Same `object.__new__(AIAgent)` pattern as R6A/R6B, with the same minimal
attribute set:

```python
agent = object.__new__(AIAgent)
agent.tool_output_compaction = ToolOutputCompactionConfig(
    enabled=..., artifact_root=str(tmp_path / "r7a-artifacts"),
    enabled_output_kinds=("terminal", "file_read"),
    rollout_platforms=("cli",),
)
agent._compaction_hashes = {}
agent.session_id = "r7a-runtime-path-mock"
agent.platform = platform
```

## Test Scenarios

| # | Scenario | Assertions |
|---|----------|------------|
| 1 | `enabled=false` | `tool_msg["content"] == raw_output`, no artifact, no hashes |
| 2 | `enabled=true` | `tool_msg["content"] != raw_output`, `"Restore:"` in content, artifact in `tmp_path`, hashes recorded |
| 3 | Blocked secret-heavy | `"BLOCKED"` in content, no raw secrets in `messages[0]["content"]`, no artifact |
| 4 | Non-terminal output | `tool_msg["content"] == raw_output`, no artifact |
| 5 | Platform rollout gate | Wrong platform → `tool_msg["content"] == raw_output`, correct platform → compacted |

Additional coverage:
- `compact_tool_output_with_artifact` never imported when disabled
- Multiple sequential tool calls → independent artifacts + separate message entries
- Blocked + clean sequence → messages preserve order, blocked stays blocked, clean gets compacted
- Structural source guarantee: `_maybe_compact_tool_output` precedes `maybe_persist_tool_result` precedes `"tool_call_id"` in source

## Key Insight: Assert on Message Dict, Not Return Value

R6B pattern:
```python
result = agent._maybe_compact_tool_output(...)
assert "Restore:" in result
```

R7A pattern:
```python
tool_msg = _simulate_runtime_tool_path(agent, messages, ...)
assert "Restore:" in tool_msg["content"]
assert "Restore:" in messages[0]["content"]  # same thing, via list
```

The message-dict assertion catches bugs where the return value is correct
but the message construction or list injection is wrong (wrong key, wrong
field, accidental mutation, etc.).

## File

`tests/test_tool_output_compaction_runtime_path_mock.py`