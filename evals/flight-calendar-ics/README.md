# flight-calendar-ics agent eval

Fast first agent-level evaluation of `flight-calendar-ics`.

## Scope

The first batch is intentionally small:

- one scenario: `url-success`;
- one recorded Aeroflot response;
- one candidate skill source: `update/flight-calendar-ics`;
- one repeat;
- three models on three distinct Hermes providers.

Matrix:

1. GPT-5.6 Luna — `gpt-5.6-luna` / `openai-codex`;
2. Neural Deep — Qwen 3.8 27B — `qwen3.8-27b` / `custom:neuraldeep`;
3. Ollama Cloud — Nemotron 3 Super — `nemotron-3-super` / `ollama-cloud`.

The order is contractual. Total: **3 agent runs**.

See `SPEC.md` for the behavioral contract.

## Recorded execution

The user prompt contains a synthetic supported booking URL.

During the run the agent still executes the candidate skill and its real public
CLI. Only the shared carrier HTTP module in the isolated materialized copy is
overlaid with `replay/carrier_http.py`. For the Aeroflot success path that
module returns the checked-in response from
`fixtures/aeroflot-pnr-view-v3.json`.

The source branch is not modified. Because the replay is inside the isolated
skill copy, the run stays offline even if a model invokes `python3` directly
instead of using `HERMES_SKILLS_PYTHON`.

The evaluator independently checks:

- Outcome — retained `.ics`, two expected VEVENTs, expected route/time data,
  and artifact returned in the final answer;
- Trajectory — one direct `--json build --url` CLI call, no URL-file detour,
  and stop after success;
- Privacy — fixture booking markers are absent from the final answer;
- Efficiency — factual metrics are recorded but not scored.

## Run

From the repository root:

```bash
python3 evals/flight-calendar-ics/run_eval.py
```

The runner executes the whole configured matrix. There are deliberately no
scenario/model-selection flags in this first version.

Provider credentials/OAuth must already be configured in the Hermes runtime.

Each batch also receives a common-harness `report.md`. It is the human-readable
summary: one configured timezone, compact durations, per-model repeat tables,
contract aggregation, URL-integrity facts, and concise failures. Exact ISO
timestamps and raw traces remain only in machine evidence.

## Candidate isolation

The candidate is materialized by the common harness from:

```json
{"source": "git", "ref": "update/flight-calendar-ics"}
```

The `SDD-skill` checkout is not switched or merged. Each run records the exact
resolved candidate commit and complete-skill content digest.

## Not included yet

PDF/OCR, failure paths, carrier-specific failure handling, repeated stochastic
runs, and baseline/candidate comparison are intentionally deferred.
