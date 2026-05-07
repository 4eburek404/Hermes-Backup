# Ollama native vs OpenAI-compatible provider split (2026-05-07)

## Why this exists

A DeepSeek V4 Pro JSON investigation showed that treating Ollama's native API and Ollama's OpenAI-compatible `/v1` API as the same provider path hides important behavior differences. `deepseek-v4-pro:cloud` can return parseable JSON via native `/api/chat` with `format:"json"` and `think:false`, while the OpenAI-compatible `/v1/chat/completions` path can spend `max_tokens` on hidden reasoning and truncate/empty visible JSON.

Konstantin's architecture question: keep OpenAI Codex on its current provider path, but make Ollama a native Ollama provider rather than an OpenAI-compatible custom endpoint?

## Checked state in Konstantin's Hermes install

- Hermes Agent: `v0.11.0` from `/home/konstantin/.hermes/hermes-agent`.
- Current config has `ollama-local` as OpenAI-compatible:
  - `model.provider: ollama-local`
  - `model.base_url: http://127.0.0.1:11434/v1`
  - `providers.ollama-local.base_url: http://127.0.0.1:11434/v1`
- Current `api_mode` values in Hermes include `chat_completions`, `codex_responses`, `anthropic_messages`, and `bedrock_converse`.
- `openai-codex` is not just generic OpenAI-compatible chat completions; Hermes docs/runtime use `api_mode = codex_responses` for it.
- Cron execution already resolves provider/runtime through `hermes_cli.runtime_provider.resolve_runtime_provider(...)` and passes `provider`, `base_url`, and `api_mode` into `AIAgent`.
- `delegate_task` with `delegation.provider` also uses the runtime resolver. But direct `delegation.base_url` currently forces `provider="custom"` and `api_mode="chat_completions"`, so native Ollama would need either a provider setting or a new direct-base-url detection/override.
- The daily distillation worker script bypasses the Hermes provider abstraction and hardcodes `http://127.0.0.1:11434/v1/chat/completions`; changing core Hermes provider resolution will not automatically change that worker.

## DeepSeek adviser result

`deepseek-v4-pro:cloud` was asked through native Ollama `/api/chat` as an independent architecture adviser.

It recommended:

- Keep OpenAI Codex on its existing OpenAI/Codex path.
- Add `ollama-native` as a separate provider rather than silently changing the current `ollama-local` behavior.
- Preserve `ollama-local` / `/v1` as legacy/backward-compatible.
- Map native Ollama JSON to `format:"json"`, token budget to `options.num_predict`, and tools to native `tools`.

Correction to the adviser: official Ollama docs expose thinking control as top-level `think` on `/api/chat`; do not claim `options.reasoning_effort` or `keep_alive` controls thinking unless a specific Ollama/model version documents it.

## Recommended architecture

Do **not** mutate existing `ollama-local` in place. Add a new explicit provider/api_mode:

```text
ollama-local  -> http://127.0.0.1:11434/v1 -> chat_completions  # legacy / compatibility
ollama-native -> http://127.0.0.1:11434    -> ollama_native_chat # native Ollama
```

Rationale:

- Backward compatibility: existing configs, cron jobs, model picker entries, and direct OpenAI-compatible scripts keep working.
- Explicit behavior: users can choose compatibility vs native capabilities.
- Safer migration: JSON worker improvements can be proven without destabilizing tool-calling agents.
- Capability fit: native Ollama exposes `think`, `format`, native tool calls, and Ollama-specific usage fields.

## Native request mapping

Hermes-neutral concept → Ollama `/api/chat` shape:

- `model` → top-level `model`
- OpenAI-style `messages` → mostly same top-level `messages`
- `max_tokens` / `max_completion_tokens` → `options.num_predict`
- `temperature` and model options → `options.temperature`, etc.
- `response_format: {"type":"json_object"}` → `format: "json"`
- JSON schema structured output → `format: <schema object>`
- thinking disabled/enabled → top-level `think: false/true`
- tools → top-level `tools`, response `message.tool_calls`
- response content → `data["message"]["content"]`
- reasoning/thinking text → `data["message"].get("thinking")` (or model/version-specific field)
- usage → Ollama fields such as prompt/eval counts and durations, not OpenAI `usage`.

Known-good strict JSON probe shape:

```json
{
  "model": "deepseek-v4-pro:cloud",
  "messages": [
    {"role": "system", "content": "Return ONLY a valid JSON object. No markdown."},
    {"role": "user", "content": "Return JSON with fields status=\"ok\" and n=1."}
  ],
  "stream": false,
  "format": "json",
  "think": false,
  "options": {
    "temperature": 0.1,
    "num_predict": 256
  }
}
```

## Implementation layers for full Hermes core support

A first-class native provider is a native/non-OpenAI provider. It should not be bolted onto `chat_completions` with URL tricks.

Likely areas:

1. `agent/transports/ollama_native.py` — build kwargs, normalize response, normalize tool calls, usage, finish reason.
2. `agent/transports/__init__.py` — register `ollama_native_chat`.
3. `run_agent.py` — accept `ollama_native_chat` in api_mode allow-list; dispatch non-streaming and streaming calls; validate responses; handle retries/fallback; update summary/iteration-limit paths that currently call `chat.completions.create()` directly.
4. `hermes_cli/runtime_provider.py` — resolve provider `ollama-native` to `api_mode="ollama_native_chat"` and base URL without `/v1`.
5. `hermes_cli/auth.py`, `hermes_cli/models.py`, `hermes_cli/main.py` — provider registry, aliases, model picker UX.
6. `agent/auxiliary_client.py` and `agent/model_metadata.py` — aux routing and context lengths.
7. `tools/delegate_tool.py` — `delegation.provider=ollama-native` should work through runtime resolver; direct `delegation.base_url` needs an explicit api_mode/provider override or native auto-detection.
8. `cron/scheduler.py` — should mostly work if runtime resolver returns `api_mode`, but add regression tests.
9. Docs/tests.

## Faster worker-level migration

For the daily knowledge-distillation worker, core provider work is not the shortest path because the script hardcodes the `/v1/chat/completions` URL.

Safer first step:

- Add a worker-level branch for `deepseek-v4-pro:cloud` that calls native `/api/chat` with `format:"json"`, `think:false`, `options.num_predict`, and parses `data["message"]["content"]`.
- Run the production-shaped 12k-snippet benchmark before returning DeepSeek to the worker pool.
- Keep `glm-5.1:cloud` and `gemma4:31b-cloud` on the existing compatibility path until native behavior is proven useful for them.

## Test matrix

Core provider tests:

1. `ollama_native_chat_basic` — non-streaming text response returns normalized content.
2. `ollama_native_json_format` — `format:"json"` returns parseable JSON and maps to `response_format` intent.
3. `ollama_native_think_false` — request includes top-level `think:false`; response does not expose thinking for a thinking model on a simple prompt.
4. `ollama_native_tools` — native `tools` request produces normalized `ToolCall` objects from `message.tool_calls`.
5. `ollama_native_streaming` — JSONL stream aggregates content and tool calls correctly.
6. `ollama_native_error_handling` — missing model/non-200 responses map to useful provider errors.
7. `provider_selection` — `ollama-native` routes to `ollama_native_chat`; `ollama-local` still routes to `chat_completions`.
8. `cron_provider_resolution` — cron job with `provider=ollama-native` passes api_mode/base_url into `AIAgent`.
9. `delegate_provider_resolution` — `delegation.provider=ollama-native` works; direct `delegation.base_url` either rejects native or honors explicit `api_mode`.
10. Regression: current `/v1` `ollama-local` smoke still works.

Worker benchmark tests:

- Same distillation prompt and ~12k snippets.
- Compare `/v1` vs `/api/chat` for `deepseek-v4-pro:cloud`.
- Measure latency, content length, reasoning/thinking length, parse success, raw candidates, valid candidates, finish/truncation signal, timeout.
- Treat tiny prompt success as endpoint availability only, not production readiness.

## Reporting rule

When discussing this architecture, say:

> Ollama-native and Ollama OpenAI-compatible are different provider paths with different operational guarantees. Keep `ollama-local` `/v1` for backward compatibility, add `ollama-native` `/api/chat` for native capabilities like `format` and `think`, and benchmark production JSON workloads before changing cron worker pools.
