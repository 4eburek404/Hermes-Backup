# github-code-review migration to common eval harness

## Scope

This migration moves orchestration from the one-off
`evals/github-code-review/run_eval.py` into `evals/harness/core.py`.

The github-code-review consumer retains only domain-specific behavior:

- materializing the local Git fixture;
- constructing the isolated Hermes home;
- invoking Hermes;
- capturing review-specific raw evidence;
- deterministic trajectory evaluation.

Skill-source materialization is now common harness behavior in
`evals/harness/skill_source.py`. The consumer supplies the configured skill
path and version source but does not implement Git-ref/working-tree selection.

## Preserved evidence

The migrated consumer retains the previous per-run evidence:

- exact `prompt.txt`;
- `raw_stream.jsonl`;
- `raw_stderr.txt`;
- `raw_final_answer.txt`;
- `metadata.json`;
- fixture pre/post/restored snapshots;
- mutation evidence;
- skill hash and version identity;
- model/provider/runtime identity;
- execution command, timestamps, duration and exit code.

The common harness adds:

- `evidence.json`;
- `score.json`;
- expected/executed run identities;
- repeat identity;
- explicit controlled-comparison metadata.

## H1-H12 after migration

- H1 matrix — implemented by common harness; models and versions are data-driven.
- H2 isolation — preserved by fresh fixture and isolated Hermes home per run.
- H3 failed run continuation — common harness records per-run failure and continues.
- H4 fixture drift — recorded as non-comparable fixture failure.
- H5/H6 independent dimensions — implemented by common harness.
- H7 privacy dimension — supported by common harness/consumer rules; no privacy markers are currently configured for this review eval.
- H8 repeats — supported through manifest/default plus `--repeat`.
- H9 re-evaluation — supported from retained `evidence.json`.
- H10 baseline/candidate comparison — common harness verifies controlled material conditions.
- H11 evaluator failure — represented as ERROR/UNDEFINED independently of agent execution.
- H12 new consumer — orchestration is no longer specific to github-code-review.
- H13 skill source — full skill directories can come from a Git ref or working tree without changing the harness checkout; source identity records the resolved commit and content digest.

## Deterministic migration check

`tests/contract/test_github_code_review_eval_consumer.py` uses:

- a synthetic Git repository;
- a synthetic patch and prompt;
- a fake Hermes process producing stream-json;
- no model call;
- no live GitHub/API dependency.

It checks:

1. preservation of the raw evidence contract;
2. separation and controlled comparison of baseline/candidate runs;
3. propagation of common skill-source identity into run metadata.

`tests/contract/test_eval_harness_skill_source_contract.py` independently
checks Git-ref and working-tree materialization, complete-skill copying, and
checkout preservation.

## Deliberate limitation

`Outcome` for github-code-review remains `UNDEFINED`.

The historical outcome analysis required semantic interpretation of review findings.
This migration does not replace that with brittle keyword matching solely to
manufacture a PASS/FAIL signal.

`Trajectory` is deterministic for the currently configured mutation and
forbidden-command rules.

The next consumer, flight-calendar-ics, can use deterministic semantic artifact
checks for Outcome because flight events and generated ICS data have structured
oracles.
