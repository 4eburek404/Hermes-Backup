# R7D — ChatCompletions Payload Validation Boundary & Dump

## R7D-1: Offline Boundary Discovery

**Goal:** Determine whether the real ChatCompletionsTransport helper can be called offline on synthetic messages without network/API/runtime state.

**Finding:** ✅ Yes. Both `ChatCompletionsTransport.convert_messages()` and `build_kwargs()` are pure functions — no network calls, no API client, no credentials, no `~/.hermes` access, no runtime state. They transform dict → dict only.

**Proof:** `tests/test_tool_output_compaction_chat_payload_boundary.py` (7 tests, commit `b97035e3`).

### Key insights

1. `convert_messages()` strips Codex Responses API fields (`codex_reasoning_items`, `codex_message_items`, `call_id`, `response_item_id`) via `copy.deepcopy` + `pop`. Returns the same list object (identity) when no sanitization needed; returns a new list when cleanup is required.

2. `build_kwargs()` calls `convert_messages()` internally, then assembles the full `client.chat.completions.create()` kwargs dict: model, messages, tools, max_tokens, extra_body, reasoning_config, provider preferences, etc.

3. The analyzer's `sanitize_message_for_standard_provider()` is a **separate mirror** of the transport's sanitization logic. It handles `unknown` roles (dropped) and strips more fields. R7C tests the analyzer mirror; R7D tests the real transport.

4. Provider profiles (`ProviderProfile`) add provider-specific kwargs via `build_api_kwargs_extras()` and `build_extra_body()`. These are also pure data transformations.

### What the R7D-1 test covers

| Test | What it proves |
|------|---------------|
| `test_convert_messages_callable_offline_with_compacted_output` | Transport convert_messages works on synthetic messages without network |
| `test_convert_messages_strips_codex_fields_offline` | Codex fields stripped, tool content preserved, original untouched |
| `test_build_kwargs_callable_offline_with_compacted_output` | Full build_kwargs works offline, tool content is compacted summary |
| `test_build_kwargs_raw_vs_compacted_payload_size` | Compacted content shorter than raw |
| `test_build_kwargs_strips_codex_fields_from_payload` | build_kwargs internally strips codex fields |
| `test_payload_structure_matches_chat_completions_format` | Output has model, messages, tools, max_tokens; valid roles |
| `test_compacted_content_preserved_through_full_payload_path` | convert_messages → build_kwargs pipeline preserves compacted content |

---

## R7D-2: Payload Dump Validation

**Goal:** Validate that synthetic compacted/blocked provider-bound messages, when fed through the full `_maybe_compact_tool_output()` → `convert_messages()` → `build_kwargs()` → `json.dumps()` pipeline, meet serialization guarantees.

**Proof:** `tests/test_tool_output_compaction_chat_payload_dump.py` (7 tests, commit `ab93b6b5`).

### Full pipeline exercised

```
_maybe_compact_tool_output(real) → synthetic tool message
→ ChatCompletionsTransport.convert_messages(sanitization)
→ ChatCompletionsTransport.build_kwargs(payload assembly)
→ json.dumps(serialization)
```

This is the complete path from compaction to what would be sent over the wire — but entirely offline.

### Scenarios validated

| Scenario | What it proves |
|----------|---------------|
| 1. Compacted terminal output | Serialized payload contains compacted summary, raw large output absent, tool structure preserved, restore pointer present |
| 2. Disabled baseline | Original output passes through verbatim; verified via `json.loads()` (not substring, since JSON escapes newlines) |
| 3. Blocked secret-heavy | BLOCKED summary in payload, raw secrets absent from entire serialized JSON |
| 4. Codex/storage-level fields | `codex_reasoning_items`, `codex_message_items`, `call_id`, `response_item_id` absent from both kwargs dict and JSON string |
| 5. Serialized payload size | Compacted < raw baseline, >2x reduction for 240-line output |

### Key pitfall discovered

**JSON newline escaping in assertions.** When asserting `LARGE_TERMINAL_OUTPUT in json_str`, the assertion fails because `json.dumps()` escapes `\n` to `\\n`. The multi-line raw output is not present as a substring in the JSON string. Fix: assert on the deserialized form instead (`json.loads(json_str)`) or assert on the kwargs dict directly. For "absent" checks (raw output NOT in JSON), the check works because `\n` in JSON doesn't match the literal `\n` in the source string either way — both directions are consistent.

### Code patterns

```python
# Correct: assert on dict content
kw, json_str = _build_payload(transport, messages)
tool_msgs = [m for m in kw["messages"] if m.get("role") == "tool"]
assert tool_msgs[0]["content"] == RAW_OUTPUT

# Correct: assert on deserialized JSON
reloaded = json.loads(json_str)
reloaded_tool_msgs = [m for m in reloaded["messages"] if m.get("role") == "tool"]
assert reloaded_tool_msgs[0]["content"] == RAW_OUTPUT

# Wrong: substring search for multi-line content in JSON
assert RAW_OUTPUT in json_str  # FAILS — newlines are escaped
```

```python
# Absent checks work both ways (escaped or not, substring won't match)
assert "secret-value" not in json_str  # OK — single-line values survive JSON
assert LARGE_OUTPUT not in json_str    # OK — multi-line absent for different reason
```

### Helper pattern

```python
def _build_payload(transport, messages, *, tools=None):
    """Full pipeline: convert_messages → build_kwargs → json.dumps."""
    sanitized = transport.convert_messages(messages)
    kw = transport.build_kwargs(
        model="gpt-4o", messages=sanitized, tools=tools,
        max_tokens=4096, max_tokens_param_fn=lambda n: {"max_tokens": n},
    )
    json_str = json.dumps(kw, ensure_ascii=False, sort_keys=True)
    return kw, json_str
```