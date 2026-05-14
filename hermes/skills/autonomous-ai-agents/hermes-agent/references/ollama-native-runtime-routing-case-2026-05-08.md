# Ollama native runtime routing case (2026-05-08)

Use this as a compact case note when debugging whether a Telegram `/model ... --provider ollama-native` turn is actually using the native Ollama route.

## Verified facts from the session

Runtime resolver split was verified from `/home/konstantin/.hermes/hermes-agent`:

```text
ollama-native: provider='custom', api_mode='ollama_native_chat', base_url='http://127.0.0.1:11434'
ollama-local:  provider='custom', api_mode='chat_completions',   base_url='http://127.0.0.1:11434/v1'
```

Interpretation:

- `ollama-native` is configured for native `/api/chat`.
- `ollama-local` is configured for OpenAI-compatible `/v1/chat/completions`.
- Resolver evidence alone proves provider configuration, not the final per-turn Telegram runtime path.

## Important distinction

Do not answer “yes, native route” for a specific gateway turn from resolver output alone. For Telegram/model-switch cases, verify the full chain:

1. `/model` command produced a `ModelSwitchResult` with `api_mode == "ollama_native_chat"`.
2. `gateway/run.py` stored the session override with `model`, `provider`, `api_key`, `base_url`, and `api_mode`.
3. Cached agent was either switched in-place correctly or evicted/recreated with the override.
4. `run_agent.py::AIAgent.switch_model()` or constructor entered the `api_mode == "ollama_native_chat"` branch.
5. Dispatch bypassed the OpenAI SDK and used `agent/transports/ollama_native.py`.
6. Logs/smoke confirm `/api/chat`; no fallback or auxiliary OpenAI-compatible route handled the visible turn.

## Suspect layers when resolver is correct but behavior is wrong

- Session override lost or stale after `/model` picker/direct command.
- Cached agent signature/runtime not refreshed after model switch.
- Fallback activation changed model/provider after timeout or provider error.
- Auxiliary/title-generation path used OpenAI SDK despite main runtime being native.
- `model_switch.py` direct alias or `determine_api_mode()` cleared/overrode `api_mode` after resolving named custom provider.

## Minimal regression target

A good regression should not require real credentials or live Ollama. Prefer a gateway/model-switch unit test that asserts:

- switching to `deepseek-v4-pro:cloud` with provider `ollama-native` stores `api_mode == "ollama_native_chat"` in `_session_model_overrides`;
- the next resolved turn config returns runtime `api_mode == "ollama_native_chat"` and `base_url == "http://127.0.0.1:11434"`;
- an existing cached agent is evicted or has its transport cache cleared so the OpenAI SDK path cannot survive the switch.

## Safe smoke commands

Resolver smoke:

```bash
cd /home/konstantin/.hermes/hermes-agent
venv/bin/python - <<'PY'
from hermes_cli.runtime_provider import resolve_runtime_provider
for name in ['ollama-native', 'ollama-local']:
    r = resolve_runtime_provider(requested=name)
    print(name, r.get('api_mode'), r.get('base_url'), r.get('model'))
PY
```

Live endpoint smoke, only when local Ollama is expected to be reachable and no secrets are printed:

```bash
python - <<'PY'
import httpx
for path in ['/api/tags', '/v1/models']:
    url = 'http://127.0.0.1:11434' + path
    try:
        r = httpx.get(url, timeout=5)
        print(path, r.status_code, r.text[:120].replace('\n', ' '))
    except Exception as e:
        print(path, type(e).__name__, str(e)[:120])
PY
```

## Reporting rule

Separate these three claims:

- “Resolver/config is native” — backed by `resolve_runtime_provider` output.
- “This specific Telegram turn used native” — backed by session override + dispatch/log/smoke evidence.
- “Fixed” — backed by a failing regression that now passes plus runtime smoke.
