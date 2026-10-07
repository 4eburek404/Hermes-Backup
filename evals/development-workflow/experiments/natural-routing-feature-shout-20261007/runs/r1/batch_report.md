# EVAL REPORT

## STATUS

Result: FAIL
Runs: 0/1 PASS
Period: 07.10.2026, 11:42–11:44
Duration: 1 мин 6 сек
Timezone: UTC

## BASELINE

Consumer: `development-workflow`
Mode: `natural-routing`

Expected runs: 1
Executed runs: 1

## RESULTS

| Model | feature-shout |
|---|---|
| gpt-6-luna | FAIL · 1 мин 6 сек |

## FACTS

No additional domain facts.

## CONTRACT CHECKS

| Model | Outcome | Trajectory | Privacy |
|---|---|---|---|
| gpt-6-luna | 1/1 | 0/1 | 0/1 |

## FINDINGS

### gpt-6-luna / feature-shout
- Trajectory: FAIL — current observable behavior is UNCONFIRMED; required preserved behavior is UNCONFIRMED after production change
- Privacy: UNDEFINED — no privacy contract in this fixture

## ARTIFACTS

Raw traces and detailed evidence remain in the batch/run artifacts. Human report timestamps are intentionally minute-readable.

## GIT

Git state is recorded by the launcher when available.

## NATURAL ROUTING

- `feature-shout--gpt-6-luna--openai-codex--candidate--r1`: skills read before first production change: behavior-driven-development
