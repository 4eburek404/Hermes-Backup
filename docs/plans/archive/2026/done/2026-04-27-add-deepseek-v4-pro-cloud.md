# Plan: Add DeepSeek V4 Pro Cloud to Hermes model config

## Goal

Добавить проверенный Ollama cloud model tag `deepseek-v4-pro:cloud` в Hermes model picker configuration.

## Context

- Exact tag verified with `ollama show deepseek-v4-pro:cloud`.
- Current Hermes model list already includes `deepseek-v4-flash:cloud`, but not `deepseek-v4-pro:cloud`.
- Config path: `/home/konstantin/.hermes/config.yaml`.
- Stable docs should record the configured model if added successfully.

## Non-goals

- Не менять default model.
- Не pin'ить эту модель на cron jobs.
- Не делать benchmark качества сейчас.
- Не трогать credentials.

## Steps

- [x] Read current config model section.
- [x] Add `deepseek-v4-pro:cloud` under `providers.ollama-local.models` if missing.
- [x] Validate YAML and confirm model appears in configured list.
- [x] Update `infrastructure.md` configured models list.
- [x] Mark this plan done.

## Verification

- YAML parses.
- `deepseek-v4-pro:cloud` exists under `providers.ollama-local.models`.
- Existing default model unchanged.
- Infrastructure docs reflect the new configured model.

## Risks / pitfalls

- Exact tag matters; do not use `deepseek-v4pro` or `deepseek-v4:cloud`.
- Model may be slow/thinking-heavy; adding to picker does not mean pinning it anywhere.

## Status

Current status: done

## Notes

Keep final report short.
