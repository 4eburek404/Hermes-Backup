# Standard chat-completions provider filtering for read-only analyzers

Use this when a diagnostic/reporting script must estimate what a standard OpenAI-style chat-completions provider would receive, without changing runtime behavior.

## Core rule

Separate *snapshot sizing* from *provider-bound input*:
- snapshot sizing = everything stored in the session snapshot
- provider input = what survives transport filtering and request assembly

Do **not** assume storage totals equal provider-visible totals.

## Filtering model to mirror

For standard chat-completions paths, sanitize away Codex/internal fields that strict providers do not accept:
- `codex_reasoning_items`
- `codex_message_items`
- internal transcript-only fields
- storage/debug-only fields
- raw internal tool-call IDs such as `call_id` and `response_item_id`

Keep provider-visible fields:
- `role`
- `content`
- `tool_calls`
- `reasoning_details`
- tool message content/output, but label it uncertain if pruning/compression state is unknown

## Uncertainty boundary

If the exact post-pruning payload is only knowable from assembled request data or a request dump, mark it as **uncertain** instead of pretending exactness.

Typical uncertain bucket:
- tool outputs after pruning/compression

## Validation pattern

For analyzer/report changes, verify in this order:
1. `python -m py_compile ...`
2. targeted `pytest ... --collect-only`
3. targeted `pytest ... -q`
4. CLI run against synthetic fixtures
5. if needed, CLI run against `~/.hermes` data without reading request dumps or mutating runtime state

## ChatCompletionsTransport offline boundary

`ChatCompletionsTransport.convert_messages()` and `build_kwargs()` are pure functions:
- no network calls
- no API client construction
- no credentials or runtime state
- pure data transformation: dict → filtered dict → kwargs dict

This means they can be validated completely offline with synthetic messages.
To exercise the full compaction → payload pipeline:

```python
from agent.transports import get_transport
transport = get_transport("chat_completions")
sanitized = transport.convert_messages(messages)
kw = transport.build_kwargs(model="gpt-4o", messages=sanitized)
```

No mock, no API key, no network needed.

## JSON serialization pitfall

When asserting against `json.dumps()` output, strings containing newlines are
escaped as `\n` in the JSON. A substring check like `assert raw_output in json_str`
will fail even when the content is correctly present. Use `json.loads()` to
deserialize and assert on the structured data instead:

```python
# WRONG — fails if raw_output contains newlines
assert raw_output in json_str

# RIGHT — deserialize and check structured content
reloaded = json.loads(json_str)
assert reloaded_tool_msgs[0]["content"] == raw_output
```

## Useful signals

When a report says "estimated provider input", check that the output explicitly lists:
- included fields
- excluded fields
- uncertain fields
- separate token buckets for reasoning, tool calls, codex-only exclusions, and tool outputs

This helps avoid mixing transport-visible input with session storage overhead.