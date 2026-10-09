# Eval human report template

This template is owned by the common eval harness. Every batch and derived
reevaluation should produce `report.md` in this shape. Raw ISO timestamps remain
in machine evidence and must not be duplicated into the human report.

## Formatting rules

- Show one configured human timezone only.
- Date: `DD.MM.YYYY`.
- Batch period: `DD.MM.YYYY, HH:MM–HH:MM`; floor start to the minute and ceil end.
- Run duration below one minute: one decimal, for example `15.8 сек`.
- Longer duration: `3 мин 53 сек`; no raw fractional seconds.
- Never print microseconds or duplicate UTC/local timestamps in `report.md`.
- Keep all configured runs visible in the model/scenario matrix.
- Keep Outcome, Trajectory, and Privacy separate in CONTRACT CHECKS.
- Keep telemetry facts separate from diagnostics; facts are not failures.
- Findings contain only failed/partial runs and concise deterministic reasons.
- Do not expose URLs, names, PNRs, ticket numbers, raw fixture text, or JSON contents.

## Required sections

```text
# EVAL REPORT

## STATUS
Result / Runs / Period / Duration / Timezone

## BASELINE
Consumer / mode / evaluated skill source / expected and executed runs

## RESULTS
One compact matrix:
Model | scenario columns
Each cell: PASS/FAIL/RUNTIME_FAILURE · human duration

## FACTS
Source, AnyDoc calls, CLI calls, URL integrity, and similar telemetry only.

## CONTRACT CHECKS
Outcome / Trajectory / Privacy aggregation.
URL integrity only for URL scenarios.

## FINDINGS
Only failed/partial runs with dimension-specific diagnostics.

## ARTIFACTS
Point to raw evidence conceptually; do not dump machine timestamps.

## GIT
Only facts actually captured by launcher/evidence.
```
