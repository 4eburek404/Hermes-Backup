# Plan: Native Ollama provider models + distillation worker contract

## Goal
Implement a first-class native Ollama provider/model path in Hermes and rework the daily knowledge-distillation worker contract so Ollama-native thinking/JSON models are configured by endpoint, prompt contract, token budget, and validation instead of being judged through the wrong compatibility path.

## Context
- This plan intentionally combines two related follow-ups in one file:
  1. finish native Ollama provider/model support in Hermes core;
  2. redesign the distillation worker contract around compact, model/endpoint-specific JSON extraction.
- Step 1 already exists at worker level, not core-provider level:
  - repo branch: `fix/deepseek-native-distillation-worker`;
  - commit: `9e7a2b8 fix: add native ollama path for deepseek distillation`;
  - worker has a manual native branch for `deepseek-v4-pro:cloud` using `/api/chat`, `format:"json"`, `think:false`, `options.num_predict`, parse `message.content`;
  - DeepSeek was not added back to production `WORKER_MODELS`.
- Verified benchmark lesson from 2026-05-07:
  - previous DeepSeek failures were settings/endpoint/prompt/output-contract mismatch, not model-quality evidence;
  - legacy `/v1/chat/completions` can spend budget on hidden reasoning and return empty/truncated visible JSON;
  - native `/api/chat` with `think:false` removes hidden reasoning, but verbose output can still truncate JSON;
  - tuned output contract (`max 10 candidates`, concise claim/reason) made DeepSeek native pass repeated production-shaped JSON benchmarks.
- Latest tuned benchmark evidence on a `10151` char production-shaped payload:
  - DeepSeek native, `num_predict=6000`: 5/5 HTTP OK, 5/5 JSON parse OK, 5/5 valid candidates, 9–10 candidates, mean latency 20.5s;
  - budget matrix with tuned prompt: `num_predict=2000`, `3000`, `6000` all passed 3/3 parse+valid runs;
  - conclusion: prompt/output contract is the main fix; `6000` is a safety cap, not the core requirement.
- Relevant source/reference paths:
  - Hermes runtime source: `/home/konstantin/.hermes/hermes-agent/`;
  - backup/overlay repo: `/home/konstantin/code/Hermes/`;
  - worker script in repo: `/home/konstantin/code/Hermes/hermes/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py`;
  - installed worker script: `/home/konstantin/.hermes/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py`;
  - provider split reference: `hermes-agent` skill → `references/ollama-native-provider-split-2026-05-07.md`;
  - distillation reference: `knowledge-architecture` skill → `references/distillation.md`;
  - benchmark reference: `knowledge-architecture` skill → `references/deepseek-native-distillation-benchmark-2026-05-07.md`.

## Non-goals
- Do not silently repoint existing `ollama-local` from `/v1` to native `/api/chat`.
- Do not change `openai-codex`; it stays on its current `codex_responses` path.
- Do not add DeepSeek to production `WORKER_MODELS` without explicit user approval after fresh task-shaped benchmark under the intended config.
- Do not use `ollama run` / `ollama pull` for `:cloud` models.
- Do not store secrets, API keys, raw config values, full logs, or raw transcripts in the plan/docs/tests.
- Do not treat benchmark success as a universal model ranking; it is evidence for the tested endpoint/prompt/budget/task shape.

## Decisions to preserve
- Keep two Ollama paths explicit:
  - `ollama-local` / `http://127.0.0.1:11434/v1` / `chat_completions` = compatibility path;
  - `ollama-native` / `http://127.0.0.1:11434` / `ollama_native_chat` = native path.
- Native Ollama request mapping:
  - `response_format: {type:"json_object"}` intent → top-level `format:"json"`;
  - `max_tokens` / `max_completion_tokens` → `options.num_predict`;
  - thinking control → top-level `think:false|true`;
  - response text → `data["message"]["content"]`;
  - thinking text, if enabled/returned → `data["message"].get("thinking")` or version-specific field;
  - usage → Ollama prompt/eval counts/durations, not OpenAI `usage`.
- Distillation worker output contract should be compact and explicit:
  - strict JSON only;
  - at most 10 candidates;
  - prioritize durable high-signal facts/corrections/settings;
  - concise `claim` and concise `reason`;
  - no raw logs/secrets/temp progress;
  - deduplicate before returning.

## Steps
- [x] Start from a clean implementation branch for Hermes core/provider work.
  - Checked current branch/status in `/home/konstantin/.hermes/hermes-agent/` and `/home/konstantin/code/Hermes/`.
  - Chosen active implementation repo: `/home/konstantin/.hermes/hermes-agent/`.
  - Created/used branch: `fix/ollama-native-chat-provider`.
  - Preserved current worker Step 1 branch/commit reference: `fix/deepseek-native-distillation-worker`, commit `9e7a2b8 fix: add native ollama path for deepseek distillation`.
- [x] Survey current provider runtime before editing.
  - Inspected `agent/transports/base.py`, `agent/transports/chat_completions.py`, `agent/transports/types.py`, `agent/transports/__init__.py`.
  - Inspected `run_agent.py` call/streaming paths and direct `chat.completions.create()` assumptions.
  - Inspected `hermes_cli/runtime_provider.py`, provider/model registry, model picker/config handling.
  - Inspected cron and delegation paths: `cron/scheduler.py`, `tools/delegate_tool.py`.
- [x] Add native Ollama transport as a separate `api_mode`.
  - Create `agent/transports/ollama_native.py` or equivalent.
  - Register `ollama_native_chat` without mutating existing `chat_completions` behavior.
  - Normalize non-streaming content, finish reason, usage/eval counts, errors, and native tool calls.
  - Add streaming support or explicitly block/defer streaming with safe error handling if not ready.
- [x] Add provider/model configuration for `ollama-native`.
  - Runtime resolver maps provider `ollama-native` to base URL `http://127.0.0.1:11434` and `api_mode="ollama_native_chat"`.
  - Existing `ollama-local` remains `http://127.0.0.1:11434/v1` and `api_mode="chat_completions"`.
  - Model picker/config docs show exact cloud tags such as `deepseek-v4-pro:cloud`, not guessed aliases.
  - Document restart/reset requirements for gateway/session after provider changes.
- [x] Add tests for native provider semantics.
  - 2026-05-07 RED checkpoint completed: created `/home/konstantin/.hermes/hermes-agent/tests/test_ollama_native_provider.py` and confirmed failing tests before implementation.
  - Initial RED result: `venv/bin/python -m pytest tests/test_ollama_native_provider.py -q` → `4 failed, 1 passed`.
  - Verified failure causes: runtime provider discards explicit `ollama_native_chat` to `chat_completions`; transport registry has no `ollama_native_chat` transport.
  - Regression guard already passes for legacy modes: `ollama-local` remains `chat_completions`; `openai-codex` remains `codex_responses`.
  - Unit tests for request mapping: `format`, `think`, `options.num_predict`, messages, tools.
  - Unit tests for response normalization: `message.content`, native `tool_calls`, `done_reason=length`, eval counts.
  - 2026-05-07 provider GREEN result: `venv/bin/python -m pytest tests/test_ollama_native_provider.py tests/hermes_cli/test_runtime_provider_resolution.py -q` → `114 passed`.
  - Added regression coverage that `AIAgent` preserves explicit `api_mode="ollama_native_chat"` and that new-style `providers.<name>.model` propagates to runtime provider resolution.
  - Still pending/optional expansion: malformed/non-200 cases and cron/delegate provider-resolution tests.
- [ ] Redesign distillation worker contract separately from provider runtime.
  - Extract output-contract settings: `max_candidates`, `claim_max_chars`, `reason_max_chars`, temperature, token/eval budget.
  - Make model/endpoint profiles explicit instead of relying on one OpenAI-compatible path for all models.
  - Keep GLM/Gemma compatibility path until native path is proven better for them.
  - For DeepSeek profile: native `/api/chat`, `format:"json"`, `think:false`, compact output contract, candidate cap.
  - Strengthen parser/validator reporting: parse status, invalid candidates, enum violations, truncation signal, reasoning/thinking length if present.
- [ ] Turn the tuned benchmark into a repeatable verification harness.
  - Keep `/tmp` scratch for ad-hoc runs, but add a reusable script or documented command for task-shaped benchmarks.
  - Inputs: fixed production-shaped payload size target 8k–12k chars.
  - Outputs: JSON result with endpoint, model, prompt hash/size, budget, latency, parse success, valid candidate count, eval/completion counts, finish/done reason.
  - Compare at least current GLM/Gemma production pool and DeepSeek native under identical tuned prompt.
- [ ] Run verification before any production-pool decision.
  - Unit/static tests for provider and worker changes.
  - Live smoke for native Ollama `/api/chat` without secrets in output.
  - Production-shaped benchmark, repeated runs, intended timeout/budget/prompt.
  - Secret scan and `git diff --check` before commit.
- [ ] Decide production rollout explicitly.
  - If benchmarks pass, ask before adding DeepSeek to `WORKER_MODELS`.
  - If approved, update repo worker, installed skill copy, distillation references, cron prompt if affected, and relevant docs/facts.
  - If not approved, leave DeepSeek as benchmark/manual profile only.
- [ ] Closeout.
  - Commit implementation changes with clear messages.
  - Update `/home/konstantin/docs/infrastructure.md` or `/home/konstantin/docs/runbooks.md` if the provider architecture becomes operational fact/procedure.
  - Patch relevant skills/references if commands or pitfalls changed.
  - Archive this plan only after implementation, verification, and durable docs updates are complete.

## Verification
- Plan-level verification:
  - This file exists in `/home/konstantin/docs/plans/`.
  - `## Status` contains machine-readable `Current status: in_progress` while the provider milestone is complete and distillation/rollout work remains active.
  - Root `plans/` contains only active plans plus `README.md`.
- Provider verification:
  - `ollama-native` resolves to `api_mode="ollama_native_chat"` and base URL without `/v1`.
  - `ollama-local` still resolves to OpenAI-compatible `/v1` path.
  - `openai-codex` still resolves to `codex_responses`.
  - Native request sends top-level `format` and `think`, and maps budget to `options.num_predict`.
  - Native response parser reads `message.content` and exposes eval/done metrics.
  - Cron/delegate provider paths preserve/pass `api_mode` correctly.
- Distillation verification:
  - Worker emits compact JSON under the intended contract.
  - Repeated production-shaped benchmark passes parse+valid gates under the intended settings.
  - Reports separate verified metrics from interpretation and attribute failures to endpoint/prompt/budget/settings.
  - DeepSeek is not added to production pool without explicit approval.
- Safety verification:
  - No secrets/raw config values/log dumps saved.
  - No `ollama run`/`pull` used for cloud models.
  - Tests and diff checks pass before reporting implementation complete.

## Risks / pitfalls
- Changing `ollama-local` in place would break existing compatibility assumptions in cron, delegation, model picker, and custom provider configs.
- Native `/api/chat` is not a drop-in OpenAI response shape; request/response/tool/usage/streaming semantics differ.
- Direct `delegation.base_url` currently assumes `chat_completions`; native support needs explicit provider/api_mode path or a clear rejection.
- Gateway/session prompt caching means config/code changes may require restart/new session before they are active.
- `format:"json"` is endpoint-specific behavior, not universal strict schema compliance.
- A tiny smoke test only proves endpoint availability; production readiness requires task-shaped repeated benchmark.
- Increasing `num_predict` can mask a bad output contract; compact prompt/candidate cap is the real guardrail for distillation JSON.
- Reasoning/thinking metrics are trade-off signals, not model-quality labels.
- Provider/model tags must be exact; do not guess cloud tag names.

## Status
Current status: in_progress

## Notes
- Created 2026-05-07 after the tuned DeepSeek native benchmark proved the issue was settings/output contract, not DeepSeek quality.
- 2026-05-07 config seed completed: `/home/konstantin/.hermes/config.yaml` now has `providers.ollama-native` with base URL `http://127.0.0.1:11434`, `api_mode: ollama_native_chat`, default model `glm-5.1:cloud`, and 26 `ollama show`-verified cloud model tags. Backup: `/home/konstantin/.hermes/config.yaml.bak-20260507-015923`.
- Verification after config seed: YAML parses; top-level active model remains `ollama-local` / `glm-5.1:cloud` / `http://127.0.0.1:11434/v1`; `ollama-local` remains the `/v1` compatibility provider; `qwen3:480b-cloud` is intentionally absent because live `ollama show` returned model-not-found.
- 2026-05-07 02:14 CEST core implementation started in `/home/konstantin/.hermes/hermes-agent` on branch `fix/ollama-native-chat-provider`. Pre-existing unrelated dirty files were present before these edits (`plugins/memory/*`, `tools/approval.py`, `tools/file_tools.py`, `tools/memory_tool.py`, `hermes_state.py.bak.20260427202556`, `tests/tools/test_protected_context_file_guard.py`) and must not be included in the Ollama-native commit.
- 2026-05-07 02:31 CEST pause checkpoint: work intentionally paused by user because another urgent task takes priority. Current code state is RED-only: branch and survey complete; `/home/konstantin/.hermes/hermes-agent/tests/test_ollama_native_provider.py` is created and uncommitted; targeted pytest result is `4 failed, 1 passed` as expected before implementation. Next resume point: implement `ollama_native_chat` in `hermes_cli/runtime_provider.py`, `run_agent.py`, and new/registering `agent/transports/ollama_native.py`, then run targeted tests/py_compile/config smoke/live native smoke and commit. Do not include the pre-existing unrelated dirty files in the Ollama-native commit.
- 2026-05-07 15:54 UTC+5 provider milestone completed in `/home/konstantin/.hermes/hermes-agent` on branch `fix/ollama-native-chat-provider`.
  - Commit `764731bad feat: add native Ollama chat transport`: added `agent/transports/ollama_native.py`, registered `ollama_native_chat`, routed native non-streaming `/api/chat`, preserved `ollama-local` as `/v1` compatibility path, and added provider tests.
  - Commit `f76e76b5d fix: propagate named custom provider models`: fixed new-style `providers.<name>.model` propagation so `resolve_runtime_provider(requested="ollama-native")` returns `model="glm-5.1:cloud"`.
  - Verification: targeted provider/runtime tests `114 passed`; py_compile passed for touched modules/tests; live native smoke resolved `provider=custom`, `api_mode=ollama_native_chat`, `base_url=http://127.0.0.1:11434`, `model=glm-5.1:cloud`, response finish `stop`, content read from native `message.content`, usage counters normalized.
  - Scoped review/commit: staged commits included only Ollama-native/provider files; pre-existing unrelated dirty files remain outside the commits (`plugins/memory/*`, `tools/approval.py`, `tools/file_tools.py`, `tools/memory_tool.py`, `hermes_state.py.bak.20260427202556`, `tests/tools/test_protected_context_file_guard.py`).
  - Plan remains `in_progress` because the second half — distillation worker contract, repeatable benchmark harness, and any production rollout decision — is intentionally not complete.
