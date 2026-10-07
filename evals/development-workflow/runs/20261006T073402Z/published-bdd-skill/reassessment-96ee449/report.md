# Reassessment: pytest-linked workflow evidence

**Branch:** `SDD-skill`
**Baseline:** `96ee449e5f956c37c467dde0aa31c80fb98e0731`
**No new model/Hermes runs:** all three assessments below were re-extracted offline from the published raw streams.

## Result

| Run | Outcome | Trajectory | Interpretation |
|---|---|---|---|
| r1 | PASS | PASS | Target RED and GREEN are linked to exact pytest snapshots; both preserved behaviors passed before and after the production change. |
| r2 | PASS | PASS | Same evidence pattern as r1. The default-name test was added before the production change, not after. |
| r3 | PASS | FAIL | Target RED/GREEN and final behavior are evidenced. Pre-change evidence for the no-argument preserved case is insufficient: its permanent pytest was added after the production edit, while the earlier no-argument CLI call shared a compound command whose stdout cannot be assigned to that process. This is an evidence gap, not a confirmed ordering violation. |

Privacy is `UNDEFINED` in all three runs because this scenario defines no privacy contract. Run durations are unchanged from original metadata: r1 **53.504 s**, r2 **82.527 s**, r3 **52.487 s**. No trustworthy cost is recorded; token counts remain in original evidence.

## Trace-backed timelines

Trace line references are one-based and point to the original immutable `raw_stream.jsonl`; event/result line pairs are also included in each new `runs/rN/event-refs.json`.

### r1

- Lines 16–17: baseline pytest invocation passes the existing regular-greeting test. Lines 18–19 add shout and default-name tests.
- Lines 20–21: full pytest run on that exact test-source snapshot reports `1 failed, 2 passed`; the failing node is the shout check. The regular and default-name checks pass in that same run before production changes.
- Lines 22–23: production `app.py` change.
- Lines 24–25: full suite reports `3 passed`; post-change tests for both preserved cases and the new target pass.
- Outcome PASS; Trajectory PASS. No RED is required for the already-working preserved behaviors.

### r2

- Lines 16–17: baseline regular-greeting test passes. Lines 20–21 (test-source patch and corresponding event pair in the published trace) add both shout and no-argument checks before the production change.
- Lines 22–23: pytest reports **`1 failed, 2 passed`**; the failed node is shout, while regular and default-name checks pass.
- Lines 24–25: production change. Lines 26–27: pytest and final CLI verification report `3 passed` and the expected results.
- Outcome PASS; Trajectory PASS. The earlier report was wrong to say that the no-argument test was added after production and wrong about the RED summary. There is no confirmed ordering violation in r2.

### r3

- Lines 18–19: on the then-current test source (regular + shout), pytest confirms regular GREEN and shout RED before production. The earlier command that also invoked the no-argument CLI was compound; its aggregate output is not attributed to individual programs.
- Lines 20–21: production change. The permanent default-name test is added afterward (see the subsequent test patch in the trace). Lines 24–25: final suite reports `3 passed`, including default and shout, and the final behavior is correct.
- Outcome PASS; Trajectory FAIL because the required two pre-change current-behavior observations are not both established by attributable checks. The late default test cannot prove pre-change behavior; nor does its lateness alone prove an order violation. The pre-change compound CLI call is not split into synthetic per-process results.

## Evaluator correction

The prior extractor did not connect the source of `tests/test_app.py` at each test run to pytest collection and its reported result. The corrected, deliberately narrow path replays recorded V4A `Update File` hunks against the fixture snapshot, hashes the resulting test source at each run, and recognizes only the full unfiltered `python[3] -m pytest -q` form with simple CLI tests that assert exit status and exact stdout. Failure summaries must identify failed test nodes and counts must reconcile with the reconstructed test set. Filtered, skipped/deselected/xfail, malformed, unmatched, or ambiguous cases remain unconfirmed. It never divides aggregate stdout among subprocesses.

Executable regression coverage includes source-hunk replay, RED/new behavior while retaining GREEN preserved checks, post-change tests not backdated, filtered/skipped or ambiguous tests not credited, and aggregate stdout not attributed to a particular program. The earlier test-run claim of 56 passing checks was intermediate; the latest full `tests/contract` run passed **129 tests** after the latest evaluator and test changes.

## Reproduction

From a clean checkout of this repository, run:

```bash
python3 evals/development-workflow/runs/20261006T073402Z/published-bdd-skill/reassessment-96ee449/reassess.py
```

The script re-reads the frozen scenario manifest, original evidence (only for non-workflow outcome inputs), and each original raw trace; it rebuilds the temporary fixture inside its own published directory, re-extracts workflow events, and recomputes the dimension scores. It invokes no Hermes command, model, API, or historical command. Outputs are written separately under `reassessment-96ee449/runs/rN/`; original traces, evidence, and scores remain unchanged. SHA-256 provenance, source test hashes, and line-addressable raw call/result references are stored in each output evidence and `event-refs.json`.

Published inputs are `../source/manifest.json` and `../runs/rN/{raw_stream.jsonl,evidence.json,score.json}`. Their hashes are checked by the script and recorded per run. The evaluator is the checked-in `evals/development-workflow/consumer.py`; its SHA-256 is recorded in each reassessment evidence file.
