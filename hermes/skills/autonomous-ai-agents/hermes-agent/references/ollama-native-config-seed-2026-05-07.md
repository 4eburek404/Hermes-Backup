# Ollama native config seed notes (2026-05-07)

## Session learning

Konstantin asked to add a new `ollama-native` provider in `~/.hermes/config.yaml` with all available Ollama cloud models, without changing the active provider.

Safe config-seeding workflow used:

1. Load `hermes-agent` and plan-governance context before touching Hermes config.
2. Inspect current `~/.hermes/config.yaml` without printing secrets.
3. Discover cloud tags with `ollama show <model>:<tag>-cloud`; do not use `ollama run` or `ollama pull` for cloud tags.
4. Create a timestamped backup before mutation:
   ```bash
   cp -p ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d-%H%M%S)
   ```
5. Add a separate provider instead of changing `ollama-local`:
   ```yaml
   providers:
     ollama-native:
       name: ollama-native
       base_url: http://127.0.0.1:11434
       api_mode: ollama_native_chat
       model: glm-5.1:cloud
       models:
         deepseek-v4-pro:cloud: {}
         glm-5.1:cloud: {}
         # ...verified tags only
   ```
6. Verify YAML parses, provider exists, active `model.provider`/`model.default` stayed unchanged, and no secrets were printed.
7. Verify runtime separately, not only config shape:
   ```bash
   cd ~/.hermes/hermes-agent
   venv/bin/python - <<'PY'
   from hermes_cli.runtime_provider import resolve_runtime_provider
   for requested in ['ollama-local','ollama-native','openai-codex']:
       rt = resolve_runtime_provider(requested=requested)
       print(requested, {k: rt.get(k) for k in ['provider','api_mode','base_url','source','model']})
   PY
   ```
8. Update the active durable plan with exact remaining implementation boundaries.

## Important result

A config entry can store `api_mode: ollama_native_chat`, but current Hermes runtime does not necessarily honor it. In the checked install, `_VALID_API_MODES` only accepted `chat_completions`, `codex_responses`, `anthropic_messages`, and `bedrock_converse`, so `ollama_native_chat` was ignored by `_parse_api_mode()` and `resolve_runtime_provider(requested='ollama-native')` resolved to:

```text
provider=custom
api_mode=chat_completions
base_url=http://127.0.0.1:11434
```

Therefore: config seeding is not proof of native `/api/chat` support. Report this boundary explicitly and keep the core-provider implementation plan open until runtime resolver, transport, dispatch, tests, cron, and delegation paths actually support `ollama_native_chat`.

## Cloud tag correction

Live `ollama show qwen3:480b-cloud` returned model-not-found in this session, so do not keep it in a verified list unless a future live check succeeds. Skill/docs should distinguish historical candidate lists from verified current tags.
