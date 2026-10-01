# EVAL REPORT

## STATUS

Result: FAIL
Runs: 0/3 PASS
Period: 01.10.2026, 07:41–07:46
Duration: 3 мин 17 сек
Timezone: UTC

## BASELINE

Consumer: `development-workflow`
Mode: `skill-behavior`

Expected runs: 3
Executed runs: 3

## RESULTS

| Model | feature-shout | bug-boundary | refactor-preserve |
|---|---|---|---|
| gpt-5.6-luna | FAIL · 1 мин 14 сек | FAIL · 52.3 сек | FAIL · 1 мин 7 сек |

## FACTS

No additional domain facts.

## CONTRACT CHECKS

| Model | Outcome | Trajectory | Privacy |
|---|---|---|---|
| gpt-5.6-luna | 3/3 | 0/3 | 0/3 |

## FINDINGS

### gpt-5.6-luna / feature-shout
- Trajectory: FAIL — current observable behavior is UNCONFIRMED; required preserved behavior is UNCONFIRMED after production change
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / bug-boundary
- Trajectory: FAIL — current observable behavior is UNCONFIRMED; target check RED before production change is UNCONFIRMED; required preserved behavior is UNCONFIRMED after production change
- Privacy: UNDEFINED — no privacy contract in this fixture
### gpt-5.6-luna / refactor-preserve
- Trajectory: FAIL — current observable behavior is UNCONFIRMED; required preserved behavior is UNCONFIRMED after production change
- Privacy: UNDEFINED — no privacy contract in this fixture

## ARTIFACTS

Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.

## GIT

Git state is recorded by the launcher when available.
