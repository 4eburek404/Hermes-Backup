# EVAL REPORT

## STATUS

Result: FAIL
Runs: 0/3 PASS
Period: 01.10.2026, 04:46–04:50
Duration: 3 мин 4 сек
Timezone: UTC

## BASELINE

Consumer: `development-workflow`
Mode: `recorded-local-fixture`

Expected runs: 3
Executed runs: 3

## RESULTS

| Model | feature-shout | bug-boundary | refactor-preserve |
|---|---|---|---|
| gpt-5.6-luna | ERROR · 1 мин 7 сек | ERROR · 1 мин 2 сек | ERROR · 51.8 сек |

## FACTS

No additional domain facts.

## CONTRACT CHECKS

| Model | Outcome | Trajectory | Privacy |
|---|---|---|---|
| gpt-5.6-luna | 0/3 | 3/3 | 0/3 |

## FINDINGS

### gpt-5.6-luna / feature-shout
- Outcome: ERROR — behavior-equivalent evaluator fixture is invalid: normal-greeting: stdout mismatch; shout-greeting: stdout mismatch
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / bug-boundary
- Outcome: ERROR — behavior-equivalent evaluator fixture is invalid: below-boundary: stdout mismatch; boundary: stdout mismatch; above-boundary: stdout mismatch
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / refactor-preserve
- Outcome: ERROR — behavior-equivalent evaluator fixture is invalid: regular-small: stdout mismatch; regular-large: stdout mismatch; member-small: stdout mismatch; member-large: stdout mismatch
- Privacy: UNDEFINED — no privacy contract in this fixture

## ARTIFACTS

Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.

## GIT

Git state is recorded by the launcher when available.
