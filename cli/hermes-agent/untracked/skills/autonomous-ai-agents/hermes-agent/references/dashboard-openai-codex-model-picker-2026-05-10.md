# Dashboard OpenAI Codex model picker: curated + live model merge

Session case: 2026-05-10. Dashboard model picker showed 7 OpenAI Codex models while `config.yaml` contained 10.

## Symptom

- `GET /api/model/options` returned `openai-codex.total_models = 7`.
- Dashboard UI therefore showed only 7 options; the frontend was not the root cause because the API payload was already truncated.
- After the fix and dashboard restart, the same endpoint returned `openai-codex.total_models = 10`.

## Root cause pattern

1. `codex_models.get_codex_model_ids(access_token=...)` treated the live ChatGPT/Codex API discovery response as authoritative and replaced curated defaults.
2. The live endpoint can be incomplete for picker purposes: in this case it exposed only 7 rows, with some slugs filtered by metadata such as `supported_in_api=false` or `visibility=hide`.
3. `list_authenticated_providers()` could return a built-in/overlay provider row before the explicit `providers.openai-codex.models` row from `config.yaml`, shadowing the user's configured model list.

## Durable fix pattern

- Keep a curated `DEFAULT_CODEX_MODELS` list for known-good picker choices.
- Merge live API discoveries with curated defaults instead of replacing the curated list.
- Route OpenAI Codex picker data through `provider_model_ids("openai-codex")`.
- When constructing authenticated provider rows, merge explicit `providers.<slug>.models` from `config.yaml` into built-in/overlay rows so config cannot be shadowed.

## Verification recipe

Check the API source before blaming the UI:

```bash
curl -s http://127.0.0.1:9119/api/model/options | jq '.providers[] | select(.slug=="openai-codex") | {total_models, models}'
```

Check direct Python runtime after patch:

```bash
python3 - <<'PY'
from hermes_cli.model_switch import provider_model_ids
print(len(provider_model_ids('openai-codex')))
print(provider_model_ids('openai-codex'))
PY
```

Restart the dashboard process before rechecking `/api/model/options`; stale imports in the running FastAPI process can preserve the old model catalog.

## Regression tests to add

- `get_codex_model_ids(access_token=...)` preserves curated defaults when live discovery returns a shorter list.
- `provider_model_ids('openai-codex')` returns the merged expected set.
- `list_authenticated_providers()` keeps explicit `config.yaml` models when a built-in/overlay provider row exists.

## Pitfalls

- Do not remove or edit OAuth tokens/secrets to hide providers or change picker behavior. Fix provider selection via non-secret config/code.
- Browser visual verification is secondary here; `/api/model/options` is the picker's data source.
- If the dashboard was already running, restart it before claiming the UI is fixed.
