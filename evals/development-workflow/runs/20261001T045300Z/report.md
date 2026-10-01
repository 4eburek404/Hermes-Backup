# EVAL REPORT

## STATUS

Result: FAIL
Runs: 0/3 PASS
Period: 01.10.2026, 04:53–04:56
Duration: 2 мин 38 сек
Timezone: UTC

## BASELINE

Consumer: `development-workflow`
Mode: `recorded-local-fixture`

Expected runs: 3
Executed runs: 3

## RESULTS

| Model | feature-shout | bug-boundary | refactor-preserve |
|---|---|---|---|
| gpt-5.6-luna | PARTIAL · 1 мин 7 сек | PARTIAL · 43.7 сек | PARTIAL · 43.6 сек |

## FACTS

No additional domain facts.

## CONTRACT CHECKS

| Model | Outcome | Trajectory | Privacy |
|---|---|---|---|
| gpt-5.6-luna | 3/3 | 3/3 | 0/3 |

## FINDINGS

### gpt-5.6-luna / feature-shout
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / bug-boundary
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / refactor-preserve
- Privacy: UNDEFINED — no privacy contract in this fixture

## ARTIFACTS

Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.

## GIT

Git state is recorded by the launcher when available.
