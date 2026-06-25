# Legacy, Refactor, and Bug Fix TDD

Open this file for bug fixes, legacy code, missing tests, pure refactoring, or unclear existing behavior. The normal path stays in `SKILL.md`.

## Bug Fix Mode
1. Reproduce the bug with a failing regression test.
2. Confirm the test fails because of the bug, not because of setup or typo.
3. Make the smallest fix.
4. Confirm the regression test passes.
5. Run nearby tests and then the full suite when practical.

If an existing test already fails for the bug, use it. Do not add a duplicate test unless it captures a missing important case.

## Legacy Code Without Tests
When touching legacy code with weak coverage:
1. Identify the smallest observable behavior that must be preserved.
2. Add characterization tests around that behavior.
3. Run them and confirm they pass on current behavior.
4. Add the new failing test or regression test for the intended change.
5. Change code in small steps.

A characterization test documents current behavior. It is not proof that the current behavior is correct; it is a guardrail before change.

## Pure Refactoring
Pure refactoring means structure changes without behavior changes.

Required path:
1. Run relevant baseline tests before editing.
2. If coverage is weak, add characterization tests first.
3. Change structure in small steps.
4. Run relevant tests after each meaningful step.
5. Do not add behavior in the same refactor commit unless the user explicitly asked for it.

A new RED test is not required for pure refactoring when existing behavior is already covered.

## Existing Baseline Failures
If tests fail before your changes:
- record the exact failing command and failure summary;
- do not mix unrelated baseline failures with your change;
- run the narrowest tests that prove your change;
- state clearly what was already failing before edits.

Do not claim the full suite is clean if it was not.

## Spike / Exploration
A spike is allowed only to learn the shape of a solution.

Rules:
- keep spike changes separate from final production changes;
- do not commit spike code;
- after learning, implement the final change through tests;
- remove temporary scripts, print debugging, and hardcoded examples before completion.

## Ambiguous Behavior
If expected behavior is unclear:
- inspect existing tests, docs, issue text, and surrounding code;
- infer only when evidence is strong;
- otherwise stop and report the ambiguity.

Do not invent business rules, error semantics, date/time rules, pricing rules, security rules, or external API behavior.

## Large Changes
For large changes, split the work:
- one behavior per test cycle;
- one small implementation step per cycle;
- one refactor step after GREEN;
- commit only after a coherent verified change.

Avoid broad rewrites unless the task explicitly asks for them.
