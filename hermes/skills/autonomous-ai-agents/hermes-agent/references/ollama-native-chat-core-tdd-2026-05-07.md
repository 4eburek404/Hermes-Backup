# Ollama native `/api/chat` core integration — TDD notes (2026-05-07)

Session learning from adding RED tests for a dedicated Hermes `api_mode: ollama_native_chat` path. Use this when implementing or reviewing a new non-OpenAI provider transport in Hermes core.

## Goal

Keep two Ollama paths separate:

- OpenAI-compatible Ollama provider, e.g. `ollama-local`:
  - endpoint: `/v1/chat/completions`
  - api_mode: `chat_completions`
  - response: `choices[0].message.content`
- Native Ollama provider, e.g. `ollama-native`:
  - endpoint: `/api/chat`
  - api_mode: `ollama_native_chat`
  - response: `message.content`

Do not silently repoint the existing `/v1` provider to native `/api/chat`; that risks breaking cron jobs, delegation, and any OpenAI-compatible assumptions.

## RED tests that caught the integration gaps

Add tests before implementation for all layers, not just payload construction:

1. Runtime provider parser/resolver keeps the new api_mode:
   - `_parse_api_mode("ollama_native_chat") == "ollama_native_chat"`
   - `_resolve_named_custom_runtime(requested_provider="ollama-native")` returns `provider: custom`, configured `base_url`, configured model, and `api_mode: ollama_native_chat`.
2. Existing providers do not regress:
   - `ollama-local` remains `chat_completions`.
   - `openai-codex` remains `codex_responses`.
3. Transport registry knows the mode:
   - `get_transport("ollama_native_chat") is not None`.
4. Native transport builds a native payload:
   - top-level `model`, `messages`, `stream: false`.
   - JSON output uses top-level `format: "json"`, not OpenAI `response_format`.
   - disabled reasoning uses top-level `think: false`, not OpenAI-compatible `extra_body.think`.
   - token budget maps to `options.num_predict`, not `max_tokens`.
   - no OpenAI-only `max_tokens`, `response_format`, or `extra_body` fields.
5. Native response normalization reads:
   - `response["message"]["content"]`.
   - `response["message"]["tool_calls"]` if present.
   - usage from `prompt_eval_count` and `eval_count`.
   - `done_reason == "length"` maps to finish reason `length`.

## Implementation checklist

1. Add the api_mode to every whitelist, not just one place:
   - `hermes_cli/runtime_provider.py` `_VALID_API_MODES`.
   - `run_agent.py` explicit api_mode accept set in `AIAgent.__init__`.
2. For new-style config providers, propagate both model keys:
   - `providers.<name>.default_model` and `providers.<name>.model` must both feed runtime `model`.
   - Regression test this with `resolve_runtime_provider(requested="ollama-native")`; otherwise provider-only resolution may return `api_mode`/`base_url` but no model.
3. Add a dedicated transport module, e.g. `agent/transports/ollama_native.py`, and register it:
   - `register_transport("ollama_native_chat", OllamaNativeChatTransport)`.
   - import it in `agent/transports/__init__.py` for auto-registration.
3. Implement actual dispatch separately from OpenAI SDK:
   - existing non-Codex/non-Anthropic/non-Bedrock flow may call `client.chat.completions.create(...)`.
   - Native Ollama cannot use that call; it needs HTTP `POST {base_url.rstrip("/")}/api/chat` with the native payload.
4. Keep iteration-limit summary and any direct summary paths in mind:
   - any direct `.chat.completions.create(...)` path will be wrong if the active agent api_mode is native.
   - either route it through the same api_mode dispatch helper or explicitly handle native there.
5. Preserve secret hygiene:
   - do not print full `~/.hermes/config.yaml` or env.
   - safe to report provider name, base URL, api_mode, and model tag.

## Implementation outcome lessons from GREEN pass

A minimal passing implementation used these concrete touch points:

- `agent/transports/ollama_native.py`
  - `api_mode == "ollama_native_chat"`.
  - `build_kwargs()` returns a native `/api/chat` payload plus internal `__ollama_native_url` dispatch metadata.
  - `response_format: {"type":"json_object"}` maps to top-level `format: "json"`.
  - `max_tokens` maps to `options.num_predict`; remove OpenAI-only `max_tokens`, `max_completion_tokens`, `response_format`, and `extra_body` from the native payload.
  - `reasoning_config` / explicit overrides map to top-level `think: false|true`.
  - Normalize content from `message.content`, tool calls from `message.tool_calls`, usage from `prompt_eval_count` + `eval_count`, and `done_reason` through `map_finish_reason()`.
- `agent/transports/__init__.py`
  - Import the module during discovery so `get_transport("ollama_native_chat")` works without an explicit import in tests.
- `hermes_cli/runtime_provider.py`
  - Add `ollama_native_chat` to `_VALID_API_MODES`; otherwise the configured provider silently falls back to `chat_completions`.
- `run_agent.py`
  - Add an init/switch-provider branch that sets `client = None` and avoids creating an OpenAI SDK client for native Ollama.
  - Add an `_ollama_native_chat_create()` helper that performs `httpx.post(native_url, json=payload, timeout=...)`, captures rate-limit headers, raises HTTP errors, and returns raw JSON.
  - Add an `_interruptible_api_call()` branch before the generic OpenAI `client.chat.completions.create(...)` path.
  - Add `_build_api_kwargs()` support for native payload construction.
  - Force non-streaming for `ollama_native_chat` until a native streaming adapter exists; otherwise the stream path may route into OpenAI chat-completions assumptions.
  - When later usage accounting expects `.usage`, normalize the raw native JSON first rather than assuming OpenAI-shaped response objects.
- URL handling:
  - Normalize `/v1` to `/api/chat` only inside the explicit native transport; do not alter `ollama-local` or its `/v1` base URL.

## Verification sequence

Use targeted verification before broader tests:

```bash
cd /home/konstantin/.hermes/hermes-agent
venv/bin/python -m pytest tests/test_ollama_native_provider.py -q
venv/bin/python -m pytest tests/hermes_cli/test_runtime_provider_resolution.py tests/test_ollama_native_provider.py -q
venv/bin/python -m py_compile agent/transports/ollama_native.py agent/transports/__init__.py hermes_cli/runtime_provider.py run_agent.py tests/test_ollama_native_provider.py tests/hermes_cli/test_runtime_provider_resolution.py
```

Observed GREEN checkpoint from the implementation session:

```text
venv/bin/python -m pytest tests/test_ollama_native_provider.py tests/hermes_cli/test_runtime_provider_resolution.py -q
# 114 passed

venv/bin/python -m py_compile agent/transports/ollama_native.py agent/transports/__init__.py hermes_cli/runtime_provider.py run_agent.py tests/test_ollama_native_provider.py tests/hermes_cli/test_runtime_provider_resolution.py
# exit 0
```

Then run a config-resolution smoke that prints only non-secret fields: provider key, runtime provider, base_url, api_mode, and model. Verify that `resolve_runtime_provider(requested="ollama-native")` returns `model` (not just `api_mode` and `base_url`). If live Ollama is available, run a tiny `/api/chat` JSON smoke with `format:"json"`, `think:false`, `options.num_predict`, and `stream:false`; redact any credentials.

## Commit hygiene in dirty Hermes repos

Konstantin's Hermes checkout often contains unrelated dirty files. Before committing an Ollama native provider change, stage only the provider-path files, never `git add -A`:

```bash
git add agent/transports/ollama_native.py \
        agent/transports/__init__.py \
        hermes_cli/runtime_provider.py \
        run_agent.py \
        tests/test_ollama_native_provider.py

git diff --cached --stat
git diff --cached
```

Known unrelated dirty files from the implementation session included memory plugin files, tool guard changes, backup files, and unrelated protected-context tests. Treat any such files as out-of-scope unless the user explicitly broadens the task.

## Framing DeepSeek/Ollama results

Do not summarize failures as “DeepSeek is bad.” The root cause may be endpoint/settings/contract-specific:

- `/v1/chat/completions` uses OpenAI-compatible `response_format` and returns OpenAI-shaped responses; hidden reasoning can consume visible output budget.
- `/api/chat` uses native `format:"json"`, top-level `think:false`, `options.num_predict`, and native response shape.
- A model can think for a long time by design; latency/reasoning tokens are trade-off metrics, not quality labels. Judge by the exact task, endpoint, prompt, budget, and output contract.
