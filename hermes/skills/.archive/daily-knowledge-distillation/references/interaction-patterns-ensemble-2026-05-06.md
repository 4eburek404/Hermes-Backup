# Interaction-pattern retrospective ensemble — 2026-05-06

## Context

Konstantin asked for a deep analysis of his interaction history with the agent and explicitly requested a raw JSON artifact plus an ensemble of GLM 5.1, DeepSeek V4 Pro, and Gemma. The task was not routine daily distillation: the goal was analysis and behavioral conclusions, not automatic writes to docs/memory.

## Workflow that worked

1. Create/close a task-control plan when edits are allowed and the task is multi-step.
2. Gather evidence from `docs/`, `fact_store`, and targeted `session_search` queries. Use summaries/snippets, not full raw transcripts.
3. Build a safe JSON evidence packet under `/tmp` with no credential values, no credential paths, and no full raw transcripts.
4. Run all requested models on the same JSON packet through the Ollama-compatible HTTP endpoint, not `ollama run`/`ollama pull`:

```text
http://127.0.0.1:11434/v1/chat/completions
```

5. Ask models for analysis/conclusions, not summaries. Require parseable JSON.
6. Save both:
   - a full raw artifact containing model raw responses/content;
   - a compact synthesis artifact for final reporting.
7. Run a secret scan over evidence/full/synthesis artifacts before reporting paths.
8. Report facts first: model tags, parse status, artifact paths, scan result, limitations.

## Model notes from this run

- `glm-5.1:cloud`: returned parseable JSON; useful for operational guardrails and knowledge-routing analysis.
- `deepseek-v4-pro:cloud`: returned parseable JSON in this ad-hoc retrospective when given a larger budget (`max_tokens` around 8000). This does **not** contradict its exclusion from cron-shaped daily distillation workers at `max_tokens=3000`, where hidden reasoning consumed the budget and content JSON truncated.
- `gemma4b` in the user's wording was mapped to the available tag `gemma4:31b-cloud`; report this mapping explicitly as an assumption/limitation.

## Reusable output shape

For final reports to Konstantin:

```text
Сделал / verified:
- sources and model tags
- artifact paths
- parse/secret-scan status

Главный вывод:
- one operational thesis

Что работает:
- evidence/action loop
- live-state verification
- raw outputs → analysis → conclusion
- correct knowledge routing

Что ломает взаимодействие:
- overconfident inference before tools
- solving the wrong pain
- scope violations
- stale provider/config/cache/timezone assumptions
- credential metadata leakage

Guardrails:
- P0/P1/P2 rules with concrete triggers

Ограничения:
- summaries/snippets, not full transcripts
- model tag mappings
- no raw transcripts or secrets included
```

## Guardrail extracted

Do not generalize cron-worker model failures to all ad-hoc model analyses. A model can be unsuitable for scheduled extraction under a small token budget and still be useful for a one-off retrospective with a larger budget and saved raw artifacts. State the exact prompt shape, endpoint, token budget, and limitation.
