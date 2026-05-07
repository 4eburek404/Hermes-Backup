# Plan: DeepSeek native Ollama branch for distillation worker

## Goal
Implement Step 1: add a worker-level native Ollama `/api/chat` branch for `deepseek-v4-pro:cloud` in the daily knowledge distillation worker, using `format:"json"` and `think:false`, while preserving the existing `/v1/chat/completions` path for other worker models.

## Context
- User explicitly asked: "делай шаг 1".
- Relevant worker: `/home/konstantin/code/Hermes/hermes/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py` and installed copy `/home/konstantin/.hermes/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py`.
- Existing worker path used Ollama OpenAI-compatible `/v1/chat/completions`, `response_format:{"type":"json_object"}`, and parsed `choices[0].message.content`.
- Prior endpoint-specific evidence: `deepseek-v4-pro:cloud` via native Ollama `/api/chat` with `format:"json"` + `think:false` returned parseable JSON on smoke; `/v1` can spend budget on hidden reasoning and truncate visible JSON.
- Work branch: `fix/deepseek-native-distillation-worker` in `/home/konstantin/code/Hermes`.

## Non-goals
- Do not implement full Hermes core `ollama-native` provider/api_mode in this step.
- Do not change production cron worker pool or re-enable DeepSeek in production without a task-shaped benchmark.
- Do not alter credentials/config or expose secrets.
- Do not change non-DeepSeek models off the existing OpenAI-compatible path.

## Steps
- [x] Check repository branch/status and switch off `main` before code changes.
- [x] Write a failing unit test proving `deepseek-v4-pro:cloud` uses native `/api/chat` request shape.
- [x] Write a regression unit test proving non-DeepSeek models still use `/v1/chat/completions` request shape.
- [x] Implement minimal worker adapter/branch for DeepSeek native Ollama.
- [x] Run targeted tests and syntax checks.
- [x] Run tiny native JSON smoke through the installed worker path.
- [x] Review diff for scope/secrets and update status.

## Verification
- RED observed: `python3 -m unittest tests.test_distillation_worker_native.DistillationWorkerNativeOllamaTests.test_deepseek_v4_pro_uses_native_ollama_json_without_thinking -v` failed before implementation with `status: error` instead of `ok`.
- Targeted tests passed: `python3 -m unittest tests.test_distillation_worker_native -v` — 2 tests OK.
- Existing knowledge CLI offline tests passed: `python3 cli/skill-clis/knowledge/tests/test_offline.py -v` — 5 tests OK.
- Syntax checks passed: `python3 -m py_compile` for repo and installed `distillation_worker.py`.
- Installed skill copy verified equal to repo copy for `scripts/distillation_worker.py` and `references/distillation.md`.
- Tiny live smoke via installed worker: native DeepSeek request shape used `/api/chat`, `format:"json"`, `think:false`, `stream:false`, `num_predict:512`; `deepseek_in_worker_models=False`; response `status: ok`, `valid_candidates: 1`.
- Secret scan over changed files: `secret_scan_findings=0`.
- Local git commit created: `9e7a2b8 fix: add native ollama path for deepseek distillation`.

## Risks / pitfalls
- `/api/chat` is not a drop-in replacement for `/v1/chat/completions`: request fields, token budget, JSON mode, thinking control, and response parsing differ.
- Tiny smoke success is not production readiness for 12k-snippet distillation payloads.
- DeepSeek remains excluded from production `WORKER_MODELS`; benchmark/explicit user approval is still required before production pool changes.
- The full Hermes core native provider/api_mode is not implemented in this step.

## Status
Current status: done

## Notes
- Implemented worker-level branch only: `deepseek-v4-pro:cloud` routes to native Ollama `/api/chat`; GLM/Gemma keep `/v1/chat/completions`.
- Updated the installed `knowledge-architecture` skill reference so future agents do not treat the manual native branch as production re-enablement.
- Durable fact_store fact_id 34 was updated with the current implementation boundary.
