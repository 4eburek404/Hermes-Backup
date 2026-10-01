# EVAL REPORT

## STATUS

Result: PARTIAL
Runs: 1/3 PASS
Period: 01.10.2026, 07:53–07:57
Duration: 3 мин 18 сек
Timezone: UTC

## BASELINE

Consumer: `development-workflow`
Mode: `skill-behavior`

Expected runs: 3
Executed runs: 3

## RESULTS

| Model | feature-shout | bug-boundary | refactor-preserve |
|---|---|---|---|
| gpt-5.6-luna | FAIL · 1 мин 6 сек | FAIL · 1 мин 0 сек | PASS · 1 мин 8 сек |

## FACTS

No additional domain facts.

## CONTRACT CHECKS

| Model | Outcome | Trajectory | Privacy |
|---|---|---|---|
| gpt-5.6-luna | 3/3 | 1/3 | 0/3 |

## FINDINGS

### gpt-5.6-luna / feature-shout
- Trajectory: FAIL — target check RED before production change is UNCONFIRMED
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / bug-boundary
- Trajectory: FAIL — target check RED before production change is UNCONFIRMED
- Privacy: UNDEFINED — no privacy contract in this fixture

## ARTIFACTS

Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.

## GIT

Git state is recorded by the launcher when available.
