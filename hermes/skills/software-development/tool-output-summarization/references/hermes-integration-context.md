# Hermes Runtime Integration Context

Audited 2025-05-11 on `context-input-baseline` branch, commit `5b5abcda`.

## Key Runtime Components

### 1. `tools/tool_result_storage.py` — 3-Layer Output Defense

| Layer | Function | Behavior |
|-------|----------|----------|
| Per-tool cap | Inside each tool | `search_files` etc. pre-truncate their own output |
| Per-result persistence | `maybe_persist_tool_result()` | If output exceeds threshold → write to `/tmp/hermes-results/{tool_use_id}.txt`, replace in-context with preview + file path |
| Per-turn budget | `enforce_turn_budget()` | After all tool results in a turn, if sum > 200K chars → spill largest to disk |

### 2. `agent/context_compressor.py` — Compression at Token Limit

- `_prune_old_tool_results(messages, protect_tail_count)` walks backward from tail, replaces old large tool outputs with 1-line summaries via `_summarize_tool_result()`.
- `_summarize_tool_result(tool_name, tool_args, tool_content)` produces strings like `[terminal] ran npm test -> exit 0, 47 lines output`.
- `ContextCompressor.compress(messages, current_tokens)` is the main entry.
- Deduplication already exists: `content_hashes` dict tracks MD5 of tool results > 200 chars, older duplicates → `[Duplicate tool output — same content as a more recent call]`.

### 3. Provider Adapters

Each adapter translates messages for its provider API:
- `agent/anthropic_adapter.py` — Claude-style `tool_use`/`tool_result` blocks
- `agent/gemini_native_adapter.py` — Gemini `functionCall`/`functionResponse`
- `agent/bedrock_adapter.py` — AWS Bedrock `toolUse`/`toolResult`
- `agent/gemini_cloudcode_adapter.py` — variant Gemini adapter

Each has its own `_translate_tool_result_to_*()` function. Point B integration would require changes in every adapter — undesirable.

### 4. `tools/budget_config.py` — Configurable Limits

- `DEFAULT_PREVIEW_SIZE_CHARS = 3000`
- `DEFAULT_MAX_TURN_BUDGET_CHARS = 200_000`
- `tool_output:` section in `config.yaml`

The compaction config (`ToolOutputCompactionConfig`) should eventually live alongside these.

## Integration Point A: Before `maybe_persist_tool_result()`

**Updated design (2025-05-11):** Compaction runs on raw `function_result` **before** `maybe_persist_tool_result()`. The summary replaces `function_result`. Then `maybe_persist_tool_result()` operates on the (now short) summary — usually a no-op, but still serves as a safety net for unusually long summaries.

This is a correction from the earlier plan which had compaction running **after** persistence. Running before persistence is simpler (one step, not two), and `maybe_persist_tool_result()` on the summary is naturally a passthrough for most outputs.

### Call Sites (two, both in `run_agent.py`, commit 5b5abcda)

**Concurrent path** `_execute_tool_calls_concurrent()` (~L10172):
```python
# BEFORE (existing):
function_result = maybe_persist_tool_result(
    content=function_result,
    tool_name=name,
    tool_use_id=tc.id,
    env=get_active_env(effective_task_id),
)

# AFTER (with compaction, behind flag):
if self._should_compact(name):
    compact_result = compact_tool_output_with_artifact(
        raw_output=function_result,
        tool_name=name,
        tool_use_id=tc.id,
        output_kind=_classify_output(name),
        config=self.tool_output_compaction,
        previous_hashes=self._compaction_hashes,
    )
    function_result = compact_result.compact_summary

function_result = maybe_persist_tool_result(
    content=function_result,
    tool_name=name,
    tool_use_id=tc.id,
    env=get_active_env(effective_task_id),
)
```

**Sequential path** `_execute_tool_calls_sequential()` (~L10560):
Same pattern with `function_name` and `tool_call.id` substituted for `name` and `tc.id`.

### Helper Methods

```python
def _should_compact(self, tool_name: str) -> bool:
    """Check if compaction is enabled and the tool is in enabled_output_kinds."""
    if not self.tool_output_compaction.enabled:
        return False
    kind = _classify_output(tool_name)
    return kind in self.tool_output_compaction.enabled_output_kinds

def _classify_output(tool_name: str) -> str:
    """Map tool name to output kind for compaction."""
    terminal_tools = {"terminal", "execute_code", "shell", "bash"}
    file_tools = {"read_file", "search_files", "file"}
    if tool_name in terminal_tools:
        return "terminal"
    if tool_name in file_tools:
        return "file_read"
    return "other"
```

## Source Locations (as of commit 5b5abcda)

| Component | File | Key Line |
|-----------|------|----------|
| Tool result persistence call (concurrent) | `run_agent.py` | ~L10172 |
| Tool result persistence call (sequential) | `run_agent.py` | ~L10560 |
| `maybe_persist_tool_result()` | `tools/tool_result_storage.py` | L116 |
| `enforce_turn_budget()` | `tools/tool_result_storage.py` | ~L175 |
| `_prune_old_tool_results()` | `agent/context_compressor.py` | L494 |
| `_summarize_tool_result()` | `agent/context_compressor.py` | L199 |
| `ContextCompressor.compress()` | `agent/context_compressor.py` | L1278 |
| Budget config | `tools/budget_config.py` | L16-17 |
| Tool output limits | `tools/tool_output_limits.py` | L55 |