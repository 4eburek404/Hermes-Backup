# Factual reconstruction before evaluator changes

Baseline checkout at start: branch `SDD-skill`, HEAD `96ee449e5f956c37c467dde0aa31c80fb98e0731`. Existing unrelated untracked run directories and `evals/development-workflow/reevaluations/` were present and left untouched. No LLM runs were made for this reassessment.

Source of reconstruction: immutable published JSONL traces under `published-bdd-skill/runs/r{1,2,3}/raw_stream.jsonl`; scenario's original `fixture_files` in `source/manifest.json`; tool-read results and patch inputs in each trace. No historical command was executed. The baseline fixture has `app.py` with `name = argv[0] if argv else "World"`; `tests/test_app.py` contains only `test_regular_greeting_behavior`, asserting Alice's ordinary greeting. The test helper invokes the CLI and checks exit 0 and exact stdout.

## r1 — raw_stream.jsonl

- Events 8–13 read baseline `app.py`, the single regular-greeting test, and protected `notes.txt`.
- Event 16 ran, before any edits, `python3 app.py Alice && python3 app.py && python3 -m pytest -q`; event 17 records exit 0 and aggregate stdout containing the two greeting lines plus pytest `1 passed`. The baseline pytest confirms the existing regular test. Because stdout is compound, neither CLI greeting is assigned to a specific process by the evaluator.
- Event 18 adds shout and no-argument tests. Event 20–21 executes pytest on that exact post-patch test source: shout fails; output identifies `test_shout_greeting_behavior`; 2 tests pass. Given the exact three collected test functions (the previously read regular test and these two additions), the two preserved tests passed in the same run. This is expected RED for the new case while the preserved checks remain GREEN before production change.
- Event 22 changes `app.py`. Event 24–25 runs pytest plus all three CLI inputs; result exit 0, `3 passed`, correct shout, regular and default outputs. This confirms the added checks and CLI checks after change.
- No test-order violation is established for the preserved default case; both preserving tests were present in the RED run before the production edit.

## r2 — raw_stream.jsonl

- Events 6–12 read baseline `app.py`, the sole regular-greeting test, and notes. Event 14–15 runs ordinary and no-argument CLI before edits; exit 0 and aggregate stdout contain both expected greetings. Event 16–17 runs baseline pytest: `1 passed` (the existing regular test). As a compound command, it does not provide process-attributed CLI evidence.
- Event 20 adds shout and no-argument tests. Event 22–23 runs pytest on that exact file state before production change. The failing node is the shout test; summary is **`1 failed, 2 passed`**, not the old report's `1 failed, 1 passed`. The two passing tests are the existing regular test and the added default-name test.
- Event 24 changes `app.py`. Event 26–27 runs pytest and the three CLI calls; exit 0, `3 passed`, with expected outputs for shout, named regular, and default. This confirms RED → change → GREEN for new shout behavior and GREEN → change → GREEN for the preserved named and no-argument behavior.
- The previous report's claim that the no-argument test was added after production change was factually wrong. No BDD order violation is established in r2.

## r3 — raw_stream.jsonl

- Events 8–13 read baseline source and the sole regular-greeting test. Event 14–15 runs named and no-argument CLI before edits; both are in the same compound call with aggregate output. This does not establish per-process stdout attributions for either invocation. Event 16 adds the shout test only. Event 18–19 runs pytest before production change: shout fails and is identified; `1 passed` is the existing regular test.
- Event 20 changes production `app.py`. Event 22–23 adds a default-name pytest test after that edit. Event 24–25 runs all tests plus the three CLI invocations; exit 0 and `3 passed`, with correct outputs.
- The no-argument pytest test was introduced after implementation, so it cannot establish pre-change test coverage. The earlier no-argument CLI was invoked before implementation, but the compound command does not let the evaluator attribute its aggregate stdout to that invocation. Thus the pre-change default behavior remains UNCONFIRMED under the evidence contract. The late test alone is not proof of an order violation.

## Evaluator defect observed

The existing extractor declines every shell command with more than one parsed command (`consumer.py::_observed_invocations`, old line 303). Thus it drops the r1/r2/r3 compound pre/post invocation evidence regardless of their event-level commands and output. It also only recognizes a whole invocation as a test run and does not connect the test file state at that event to named pytest failures/pass counts. The old report separately mislabeled r2's RED count and alleged a late default test that the trace disproves, and it overrequired RED for preserved behavior.

This factual record was written before editing evaluator recognition. For current coverage, require new behavior RED before production and GREEN after; preserved cases require observed GREEN before and after. Preserve UNCONFIRMED when test collection/result cannot be unambiguously linked to a source snapshot. Never infer individual app stdout from aggregate command output.
