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

- `gpt-5.6-luna` / `openai-codex`;
- `deepseek-v4-pro` / `deepseek`;
- `glm-5.1` / `zai`.

Total: **3 agent runs**.

See `SPEC.md` for the behavioral contract.

## Recorded execution

The user prompt contains a synthetic supported booking URL.

During the run the agent still executes the real candidate skill and its real
public CLI. Only the carrier HTTP boundary is replaced: `replay/` returns the
checked-in response from `fixtures/aeroflot-pnr-view-v3.json`.

No live airline request is needed.

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
