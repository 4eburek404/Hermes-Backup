# General Eval Harness — Baseline Before Consumer Migration

Baseline branch: `SDD-skill`

Existing consumer: `evals/github-code-review/run_eval.py`

Saved evidence inspected: `evals/github-code-review/runs/20260919T115619Z/`

## Existing evidence contract

The current github-code-review runner already preserves useful raw execution evidence:

- exact prompt copy;
- `raw_stream.jsonl` from Hermes `stream-json`;
- `raw_stderr.txt`;
- `raw_final_answer.txt`;
- per-run `metadata.json`;
- fresh fixture repository per run;
- pre/post fixture snapshots in metadata;
- mutation evidence when a run changes the fixture;
- model/provider/runtime command metadata;
- skill hashes;
- baseline/candidate identity;
- batch manifest.

The saved batch also contains derived `analysis.json` and `report.md`, separate from the raw per-run evidence.

These properties must not be lost during migration to the common harness.

## H1-H12 baseline

### H1 — Evaluation matrix: PARTIAL

Current runner expands:

`scenario × skill_version`

It has one hard-coded model/provider and no repeat dimension.

### H2 — Run isolation: PRESENT

Each run materializes a fresh fixture repository and creates isolated temporary Hermes home/skill roots.

Fixture mutations are detected before cleanup/restoration.

### H3 — Failed run does not destroy batch: PARTIAL

A Hermes process returning a non-zero exit code is captured and the loop can continue.

Setup exceptions raised by runner code, including fixture SHA drift, can abort the batch instead of becoming an individual run result.

### H4 — Fixture drift: PARTIAL

Fixture base/review SHA drift is detected before Hermes execution.

The current behavior raises an exception instead of recording a non-comparable fixture/setup failure and continuing independent runs.

### H5 — Outcome/trajectory independence: NOT AUTOMATED

The runner records evidence required for later analysis, but it does not produce independent Outcome and Trajectory statuses.

The saved `analysis.json` was derived separately from raw execution.

### H6 — Wrong outcome with valid trajectory: NOT AUTOMATED

No reusable evaluator currently represents Outcome and Trajectory independently.

### H7 — Privacy evaluation: ABSENT

No deterministic privacy/leakage scorer is present in the runner.

### H8 — Repeats: ABSENT

One run exists for each scenario/version combination.

### H9 — Re-evaluation from saved evidence: NOT AUTOMATED

Raw evidence is retained, so re-analysis is possible, but there is no reusable command/path that re-scores a saved run without invoking Hermes.

### H10 — Controlled baseline/candidate comparison: PARTIAL

The existing manifest explicitly states controlled-comparison assumptions and per-run metadata records model, provider, fixture, prompt, runtime settings, and skill identity.

There is no generic comparability check shared by consumers.

### H11 — Evaluator failure state: ABSENT

The current runner does not execute a reusable evaluator and therefore has no explicit evaluator ERROR/UNDEFINED state.

### H12 — New consumer without orchestration changes: ABSENT

The runner is hard-coded to github-code-review:

- scenario identifiers;
- model;
- provider;
- skill path;
- baseline/candidate commits;
- fixture materialization;
- Hermes invocation settings.

A second skill would require copying/changing orchestration logic.

## Migration invariant

Migration is successful only if the common harness gains H1-H12 behavior without losing the existing github-code-review raw evidence listed above.
