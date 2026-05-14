# Ollama native provider split (2026-05-07/08)

Use this reference when debugging or changing Hermes Agent routing for Ollama, Ollama Cloud, or local Ollama-compatible providers.

## Contract to preserve

- `ollama-local` is the OpenAI-compatible path:
  - `base_url = http://127.0.0.1:11434/v1`
  - `api_mode = chat_completions`
  - request path: `/v1/chat/completions`
- `ollama-native` is the native Ollama path:
  - `base_url = http://127.0.0.1:11434`
  - `api_mode = ollama_native_chat`
  - request path: `/api/chat`
- Do not silently repoint `ollama-local` to native `/api/chat`; keep both names explicit.
- Exact cloud tags matter (`deepseek-v4-pro:cloud`, `glm-5.1:cloud`, etc.). Do not guess aliases.

## Source paths

- Runtime/provider resolver: `hermes_cli/runtime_provider.py`
- Main agent native transport: `agent/transports/ollama_native.py`
- Main agent dispatch guard: `run_agent.py` (`api_mode == "ollama_native_chat"` bypasses OpenAI SDK)
- Auxiliary/title-generation routing: `agent/auxiliary_client.py`
- Provider tests: `tests/test_ollama_native_provider.py`, `tests/hermes_cli/test_runtime_provider_resolution.py`
- Auxiliary routing tests: `tests/agent/test_auxiliary_client.py::TestOllamaNativeAuxiliaryRouting`

## Known pitfall fixed 2026-05-08

After the core provider milestone, auxiliary auto-routing could still fail for title generation:

1. `title_generator.py` calls `call_llm(..., main_runtime=main_runtime)`.
2. `_resolve_auto()` correctly selected main provider `ollama-native`.
3. `resolve_provider_client()` recognized the named custom provider but treated `api_mode: ollama_native_chat` as an OpenAI SDK `chat.completions` client.
4. With base URL `http://127.0.0.1:11434`, the OpenAI SDK hit the wrong OpenAI-style path (`/chat/completions`), producing `404 page not found`.

Fix: `agent/auxiliary_client.py` must use `OllamaNativeAuxiliaryClient` / async wrapper for explicit/custom/named `api_mode == "ollama_native_chat"`, mapping:

- `response_format: {"type":"json_object"}` → top-level `format:"json"`
- `max_tokens` / `max_completion_tokens` → `options.num_predict`
- `extra_body.think` / `think` / disabled reasoning → top-level `think:false|true`
- native response `message.content` → OpenAI-like `.choices[0].message.content`

Relevant commit in Konstantin's runtime repo: `5cdf08a98 fix: route auxiliary Ollama native via api chat`.

## Related case notes

- `references/ollama-native-runtime-routing-case-2026-05-08.md` — Telegram `/model` switch investigation note: resolver split is necessary evidence, but per-turn native routing also requires checking session override, cached-agent refresh/eviction, fallback, auxiliary routes, and dispatch logs.

## Verification commands

```bash
cd ~/.hermes/hermes-agent
venv/bin/python -m py_compile agent/auxiliary_client.py tests/agent/test_auxiliary_client.py
venv/bin/python -m pytest tests/agent/test_auxiliary_client.py::TestOllamaNativeAuxiliaryRouting -q
venv/bin/python -m pytest tests/agent/test_auxiliary_client.py -q
venv/bin/python -m pytest tests/test_ollama_native_provider.py tests/hermes_cli/test_runtime_provider_resolution.py -q
```

Runtime resolver smoke:

```bash
cd ~/.hermes/hermes-agent
venv/bin/python - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
for name in ['ollama-native', 'ollama-local']:
    r = resolve_runtime_provider(requested=name)
    print(name, r.get('api_mode'), r.get('base_url'), r.get('model'))
PY
```

Expected split:

- `ollama-native ollama_native_chat http://127.0.0.1:11434 ...`
- `ollama-local chat_completions http://127.0.0.1:11434/v1 ...`
