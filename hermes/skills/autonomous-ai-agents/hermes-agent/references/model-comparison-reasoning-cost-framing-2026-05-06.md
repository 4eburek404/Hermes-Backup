# Model comparison: reasoning/cost framing correction (2026-05-06)

## Context

During a user-requested ensemble analysis of interaction patterns, three Ollama cloud models were run on the same curated JSON evidence packet through the OpenAI-compatible endpoint:

- `glm-5.1:cloud`
- `deepseek-v4-pro:cloud`
- `gemma4:31b-cloud` (used for the user's shorthand `gemma4b`)

DeepSeek V4 Pro was slower than the others and used substantial hidden reasoning, but returned the broadest and most detailed synthesis for this deep analysis task. The user corrected the framing: calling DeepSeek “прожорливый” was misleading because the extra reasoning produced more useful information.

## Lesson

Reasoning tokens, hidden reasoning length, latency, and cost are trade-off metrics, not quality labels.

Correct framing:

- Report them as measured costs/constraints.
- Judge whether the extra cost bought more accuracy, coverage, useful distinctions, or better task fit.
- Avoid treating low reasoning or short latency as automatically better.
- Avoid treating high reasoning/cost as automatically worse.

## Task-shape caveat

This correction does **not** mean a model that succeeds on one task is suitable for every task.

Example from the same environment:

- DeepSeek V4 Pro succeeded on a deep analytical ensemble task with a larger token budget.
- A previous cron-shaped knowledge-distillation repro with `json_object`, 12k snippets, `max_tokens=3000`, and timeout around 200s failed by spending budget on hidden reasoning and returning incomplete JSON.

Therefore compare models by:

- exact task shape;
- endpoint/provider path;
- prompt and output contract;
- token budget;
- timeout;
- success criteria.

## Reporting pattern

When comparing models for Konstantin:

1. Show raw outputs/artifacts when requested.
2. Separate measured facts from interpretation.
3. Treat latency/cost/reasoning as trade-offs.
4. Explain whether the extra cost was worth it for this task.
5. Do not pin or recommend a model for a different task without a direct task-shaped benchmark.
