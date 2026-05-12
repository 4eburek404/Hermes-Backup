# Tool-Output Compaction Runtime Integration (R1–R3)

Use this reference when integrating `compact_tool_output_with_artifact()` into the Hermes runtime.
The work proceeds in stages: R1 (insertion-point docs), R2 (config parsing), R3 (integration behind flag).

## Architecture

Compaction sits **before** `maybe_persist_tool_result()` in both tool-result insertion paths:

```
handle_function_call() → function_result
  ↓
compact_tool_output_with_artifact(function_result, ...)  ← NEW (R3)
  ↓
maybe_persist_tool_result(compact_summary, ...)          ← EXISTING
  ↓
tool_msg = {"role": "tool", "content": compact_summary}
messages.append(tool_msg)
```

### Insertion Point A — Concurrent path

**File:** `run_agent.py`
**Method:** `_execute_tool_calls_concurrent()`
**Line:** ~L10172 (before `maybe_persist_tool_result`)

Variables available: `function_result`, `name`, `tc.id`, `args`, `self.session_id`, `len(messages)`, `env`

### Insertion Point B — Sequential path

**File:** `run_agent.py`
**Method:** `_execute_tool_calls_sequential()`
**Line:** ~L10560 (before `maybe_persist_tool_result`)

Variables available: `function_result`, `function_name`, `tool_call.id`, `function_args`, `self.session_id`, `len(messages)`, `env`

### Variable name mapping between paths

| Concurrent (A)   | Sequential (B)    |
|-------------------|-------------------|
| `name`            | `function_name`   |
| `tc.id`           | `tool_call.id`    |
| `args`            | `function_args`   |

## Config — R2 (complete)

**Dataclass:** `tools/budget_config.py` → `ToolOutputCompactionConfig`

```python
@dataclass(frozen=True)
class ToolOutputCompactionConfig:
    enabled: bool = False                                      # Master switch
    artifact_root: str = "/tmp/hermes/artifacts"               # Artifact storage root
    short_output_threshold: int = 200                          # Skip compaction below this
    secret_policy: str = "redact_or_block"                      # redact_or_block | block_only | allow
    enabled_output_kinds: tuple[str, ...] = ("terminal", "file_read")
    rollout_platforms: tuple[str, ...] = ("cli",)              # Platform allowlist
```

### DEFAULT_CONFIG section (hermes_cli/config.py)

```yaml
tool_output_compaction:
  enabled: false
  artifact_root: /tmp/hermes/artifacts
  short_output_threshold: 200
  secret_policy: redact_or_block
  enabled_output_kinds:
    - terminal
    - file_read
  rollout_platforms:
    - cli
```

### AIAgent storage (run_agent.py)

```python
self.tool_output_compaction = ToolOutputCompactionConfig.from_mapping(
    _agent_cfg.get("tool_output_compaction", {})
)
self._compaction_hashes: dict[str, str] = {}
```

### Helper: `classify_output_kind(tool_name)` → "terminal" | "file_read" | "other"

Defined in `tools/budget_config.py`. Maps known tool names to output kinds.

### Gate method: `should_compact(tool_name, platform="cli")`

Returns `True` only when all three gates pass: enabled=True, platform in rollout_platforms, output-kind in enabled_output_kinds.

## Why before maybe_persist_tool_result

1. **Security:** Secrets are scanned before they enter message history. Blocked outputs (≥3 secrets) never reach `messages`.
2. **Composability:** Summary is short → `maybe_persist_tool_result()` almost always no-ops. If summary is still too large, existing persistence works as safety net.
3. **Zero impact when disabled:** `enabled=False` → `should_compact()` returns `False` → no compaction called, no behavior change.

## Why not ContextCompressor

1. Too late — secrets already in history for multiple turns.
2. Different purpose — compressor trims for token budget; compaction replaces specific outputs with artifacts.
3. No artifact lifecycle — compressor has no disk-write or restore-pointer concept.

## Test files

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_tool_output_compaction_config.py` | 74 | Config parsing, defaults, validation, should_compact gate, AIAgent storage |
| `tests/test_tool_output_compaction.py` | — | Compaction wrapper |
| `tests/test_tool_output_artifacts.py` | — | Artifact storage |
| `tests/test_tool_output_summarizer.py` | — | Secret scanning, summarization |
| `tests/test_tool_output_compaction_runtime.py` | 7 | R3 runtime helper: disabled no-op, terminal clean artifact+restore, blocked secret suppression, non-terminal no-op, exception fallback, both insertion points before persistence |
| `tests/test_tool_output_compaction_session_snapshot_roundtrip.py` | 5 | R7B synthetic snapshot roundtrip: compacted/blocked/passthrough tool messages persist to `tmp_path` session_*.json, reload unchanged, and remain analyzer-compatible |
| `tests/test_tool_output_compaction_provider_bound_messages.py` | 8 | R7C provider-bound message validation: compacted output reaches provider view compacted, raw large output absent, blocked secrets absent, codex_reasoning_items stripped, call_id/response_item_id stripped, size savings measurable via analyzer token estimate |
| `tests/test_tool_output_compaction_chat_payload_boundary.py` | 7 | R7D-1 ChatCompletions payload boundary: real transport convert_messages/build_kwargs callable fully offline on synthetic compacted messages, codex fields stripped from payload, compacted content survives full pipeline, payload structure matches ChatCompletions API format |

## R7B synthetic session snapshot roundtrip pattern

Use this pattern when validating persistence/reload consistency for tool-output compaction without touching real Hermes sessions:

1. Keep the test entirely synthetic and `tmp_path`-scoped: no `~/.hermes`, no network, no real LLM/API/tool calls, no default config changes, no rollout, no ContextCompressor.
2. Build OpenAI-shaped messages manually: system/user/assistant-with-tool_calls, then inject a tool message shaped as `{"role": "tool", "name": ..., "content": ..., "tool_call_id": ...}`.
3. Use a bare `AIAgent` via `object.__new__(AIAgent)` with only `tool_output_compaction`, `_compaction_hashes`, `session_id`, and `platform`; call `_maybe_compact_tool_output()` directly before constructing the synthetic tool message.
4. Persist the conversation to `tmp_path / "sessions" / f"session_{session_id}.json"` with fields accepted by `scripts/analyze_context_overhead.py`: `session_id`, `model`, `platform`, `system_prompt`, `tools`, `messages`.
5. Reload with `json.loads()` or analyzer `load_session_snapshot()` and assert structure/content invariants: role/name/tool_call_id preserved, compacted summary preserved, raw large terminal output absent from saved message, artifact paths remain under `tmp_path`, blocked secret-heavy output saves only BLOCKED summary and writes no artifact, and non-terminal output remains unchanged under R3 scope.
6. Analyzer compatibility check: compare `estimate_standard_provider_input(raw_messages)` vs reloaded compacted messages and require lower `estimated_tokens_total` plus lower `tool_output_tokens_sent_or_pruned_uncertain` for the compacted snapshot.

Pitfall: secret-heavy fixtures must match the scanner's actual patterns. Prefixing the key (for example `SYNTHETIC_API_KEY_0=...`) may not satisfy the `\bAPI_KEY` pattern; use explicit synthetic placeholders like `API_KEY_0=synthetic-secret-value-...` and assert those placeholders do not persist.

## R3 runtime integration pattern

Keep all runtime logic in one `AIAgent` helper and call it from both insertion points before `maybe_persist_tool_result()`:

```python
def _maybe_compact_tool_output(
    self,
    *,
    function_result: str,
    tool_name: str,
    tool_call_id: str,
    function_args: dict | None,
    message_index: int,
) -> str:
    compaction_cfg = getattr(self, "tool_output_compaction", None)
    if not compaction_cfg or not getattr(compaction_cfg, "enabled", False):
        return function_result  # disabled default: no import, no wrapper call, no artifact

    output_kind = classify_output_kind(tool_name)
    if output_kind != "terminal":
        return function_result  # R3 scope is terminal-only, even if config allows file_read

    platform = self.platform or os.environ.get("HERMES_SESSION_SOURCE", "cli") or "cli"
    if not compaction_cfg.should_compact(tool_name, platform=platform):
        return function_result

    metadata = {
        "tool_name": tool_name,
        "session_id": self.session_id or "unknown_session",
        "message_index": message_index,
        "tool_call_id": tool_call_id or "unknown_tool_call",
        "exit_code": parsed_exit_code_or_0,
        "file_path": None,
        "line_range": None,
        "command": function_args.get("command") if isinstance(function_args, dict) else None,
    }
    compact_result = compact_tool_output_with_artifact(
        function_result,
        session_id=metadata["session_id"],
        message_index=message_index,
        tool_call_id=metadata["tool_call_id"],
        tool_name=tool_name,
        output_kind="terminal",
        metadata=metadata,
        artifact_root=Path(compaction_cfg.artifact_root),
        previous_hashes=self._compaction_hashes,
    )
    if compact_result.has_artifact and compact_result.artifact_ref:
        self._compaction_hashes[compact_result.sha256] = compact_result.artifact_ref
    return compact_result.compact_summary
```

Call shape:

```python
function_result = self._maybe_compact_tool_output(
    function_result=function_result,
    tool_name=name,                  # or function_name in sequential path
    tool_call_id=tc.id,              # or tool_call.id in sequential path
    function_args=args,              # or function_args in sequential path
    message_index=len(messages),
)
function_result = maybe_persist_tool_result(...)
```

### R3 pitfalls discovered

- `scripts.tool_output_summarizer.classify_output_kind(raw, metadata)` classifies terminal output by `metadata["exit_code"] is not None`. If `function_result` is a raw string rather than JSON with `exit_code`, set terminal `exit_code` to `0` in metadata, otherwise the summary becomes generic `Output:` and loses the `Command:`/`Exit Code:` header.
- Import `compact_tool_output_with_artifact` lazily inside the helper so `enabled=False` can be proven to make no wrapper call and no artifact write.
- Fail-open only for clean fallback: if the wrapper raises, run `scan_secrets(function_result)`; return original only when no secret matches. If the fallback scanner fails or detects anything, return a safe `BLOCKED` summary and suppress raw output.
- The R3 scope is stricter than config: only `output_kind == "terminal"` should compact. Do not apply to `file_read`, search, web, transports, prompt builder, analyzer, or `ContextCompressor`.
- Unit tests should instantiate `AIAgent` with `object.__new__(AIAgent)` and populate only `tool_output_compaction`, `_compaction_hashes`, `session_id`, and `platform`; use `tmp_path` for `artifact_root`; never write to real `~/.hermes` and never make real LLM/API calls.
- Safety-grep hits in these tests are expected for synthetic field names such as `API_KEY_...=synthetic_value...`, `scan_secrets`, and `password` callback names; real secret values must still stop the task.

## R7C provider-bound message validation pattern

Use this pattern when proving that compacted tool output reaches the provider-bound message stream correctly, without starting a real LLM/API provider or writing ~/.hermes:

1. Use `sanitize_message_for_standard_provider()` from `scripts/analyze_context_overhead.py` as the offline proxy for ChatCompletions transport filtering. This function strips `codex_reasoning_items`, `codex_message_items`, `type`, `tool_calls.call_id`, and `tool_calls.response_item_id` — exactly what the real transport does.
2. Build synthetic OpenAI-shaped messages, inject tool messages via `_maybe_compact_tool_output()` on a bare `AIAgent` (same pattern as R7B), then sanitize all messages through the provider-bound filter.
3. Assert on the **sanitized** messages: compacted tool content present, raw large terminal output absent, `BLOCKED` summary present for secret-heavy output, secrets absent from entire message stream, `codex_reasoning_items`/`codex_message_items`/`call_id`/`response_item_id` stripped from all message roles.
4. For size comparison: compute `estimate_standard_provider_input()` on both raw and compacted provider-bound views; require compacted `estimated_tokens_total` < raw, with savings from `tool_output_tokens_sent_or_pruned_uncertain`.
5. Validate that compacted content includes an artifact restore pointer (`"Restore:"` or `"hermes artifact restore"` in the tool message content).

This pattern complements R7B (snapshot roundtrip) by testing what the provider *receives*, not just what gets persisted. R7B tests storage/reload fidelity; R7C tests transport-layer filtering fidelity.

Pitfall: `sanitize_message_for_standard_provider()` returns `None` for messages without a valid role — filter those out before asserting content, as the real transport silently drops them.

## R7D-1 ChatCompletions payload boundary

The real `ChatCompletionsTransport` payload assembly path can be exercised **fully offline** — no network, API client, credentials, or runtime state needed. The transport does pure data transformation.

### Architecture: payload assembly path

```
messages (OpenAI-format dicts)
  ↓
ChatCompletionsTransport.convert_messages(messages)
  ↓ strips codex_reasoning_items, codex_message_items, call_id, response_item_id
  ↓ returns messages list (identity when no sanitization needed, deep copy when any codex field present)
  ↓
ChatCompletionsTransport.build_kwargs(model, sanitized, tools, **params)
  ↓ developer role swap (GPT-5/Codex models)
  ↓ Moonshot tool schema sanitization
  ↓ max_tokens resolution (ephemeral > user > profile default)
  ↓ reasoning config, extra_body assembly, temperature, timeout, request overrides
  ↓
returns api_kwargs dict → passed to client.chat.completions.create(**api_kwargs)
```

### Offline-safe boundary proof (R7D-1)

Test file: `tests/test_tool_output_compaction_chat_payload_boundary.py` (7 tests)

Key findings:
1. `ChatCompletionsTransport` is importable standalone from `agent.transports` — no AIAgent initialization, no config, no credentials needed.
2. `convert_messages()` is a pure function: `list[dict] → list[dict]`. No side effects, no I/O, no API calls. Returns the same list object when no sanitization is needed (identity); returns a deep copy when any codex field triggers sanitization.
3. `build_kwargs()` is a pure function: `(model, messages, tools, **params) → dict`. Internally calls `convert_messages()`, then assembles the full kwargs dict. No side effects, no I/O, no API calls.
4. The tests prove: compacted tool output content survives both `convert_messages()` and `build_kwargs()` unchanged; codex fields are stripped; raw large output is absent from the final payload dict; payload structure matches expected ChatCompletions API shape (model, messages, tools, max_tokens, etc.).

### Difference from analyzer sanitize

`scripts/analyze_context_overhead.py:sanitize_message_for_standard_provider()` is a **separate implementation** that mirrors but does not directly call `ChatCompletionsTransport.convert_messages()`. The analyzer version is more aggressive (strips `type`, filters unknown roles to `None`). The transport version only strips Codex-specific fields (`codex_reasoning_items`, `codex_message_items`, `call_id`, `response_item_id`).

For R7C (provider-bound message validation), the analyzer function is used because it models the full standard-provider filtering including unknown-role drop. For R7D-1, the real transport is used directly because the goal is to prove the actual payload assembly path is offline-safe.

### Recommended next step: R7D-2

Build a synthetic offline payload dump utility that runs the full pipeline:
`_maybe_compact_tool_output()` → `convert_messages()` → `build_kwargs()`
and dumps the resulting kwargs dict (bytes, tokens, structure) for before/after comparison. This would measure the actual payload overhead reduction without needing a real API call.

## Rollback

Set `tool_output_compaction.enabled: false` in config. Or revert the R3 commit. No migration needed.