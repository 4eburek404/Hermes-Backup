# Cron fact_store + DeepSeek root-cause

## Goal
Add `fact_store` availability to the daily knowledge distillation cron and find why DeepSeek appears again as a worker despite prior concerns.

## Scope
- Main Hermes instance only: `/home/konstantin/.hermes/`.
- Do not touch Docker guest instance or `~/hermes-instances/guest/`.
- Do not work on hh.ru now.

## Steps
1. Audit current daily knowledge distillation cron metadata, full prompt, attached skill, toolsets, and recent outputs.
2. Identify all references to DeepSeek in cron metadata/prompt/skill/scripts/docs/config.
3. Determine whether DeepSeek is present because of stale embedded prompt, attached skill instructions, docs drift, or runtime/default/delegation config.
4. Update only the intended cron/toolset configuration to make `fact_store` available.
5. Verify cron metadata after update and record root cause in chat.

## Verification
- `cronjob list` shows expected toolsets including the memory/fact-store capability.
- Search confirms no accidental changes under Docker guest paths.
- Root-cause statement separates facts from hypotheses.

## Status
Current status: done

## Result
- Cron `62e7a25f4e15` now has toolset `memory`, which provides `fact_store` / `fact_feedback`.
- Root cause: cron-shaped DeepSeek repro completed but failed semantically. With the same worker HTTP call (`json_object`, English system prompt, 12k snippets, `max_tokens=3000`, `timeout=200`), `deepseek-v4-pro:cloud` exited in 92.6–113s while consuming the full 3000 completion-token budget mostly in hidden `message.reasoning` (~12.7k chars) and returning only 127 chars of incomplete JSON. The previous worker code reported non-parseable content as `ok` with 0 candidates, hiding the failure mode.
- Guardrail added: `distillation_worker.py` now returns `parse_error` for non-parseable JSON and records `finish_reason`, `completion_tokens`, `content_chars`, `reasoning_chars`, and a content preview; enum/field failures return `validation_error`, not `ok`.
- Corrected main-instance layers: cron embedded prompt, `daily-knowledge-distillation` skill, worker script, benchmark reference note, `infrastructure.md`, `runbooks.md`, and fact_store fact #34.
- Docker guest instance was not edited; observed recent guest log/lock mtimes are from its own running services, not this change.
