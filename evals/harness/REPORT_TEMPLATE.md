# Eval human report template

This template is owned by the common eval harness. Every batch should produce
`report.md` in this shape. Raw ISO timestamps remain in machine evidence and
must not be duplicated into the human report.

## Formatting rules

- Show one configured human timezone only.
- Date: `DD.MM.YYYY`.
- Batch period: `DD.MM.YYYY, HH:MM–HH:MM`; floor start to the minute and ceil end.
- Run duration below one minute: one decimal, for example `15.8 сек`.
- Longer duration: `3 мин 53 сек`; no six-decimal raw seconds.
- Never print microseconds or duplicate UTC/local timestamps in `report.md`.
- Keep repeats visible; do not hide failed runs behind averages.
- Keep Outcome, Trajectory and Privacy separate.
- Domain-specific consumers may add compact facts such as CLI-call count,
  URL-integrity status and a short failure note, but must not expose secrets.

## Required sections

```text
# EVAL REPORT

## STATUS
Результат / Запуски / Успешно / Период / Общее время / Часовой пояс

## BASELINE
Consumer / mode / evaluated skill source / expected and executed runs

## RESULTS
One compact table per model/provider:
Scenario | Run | Result | Time | Tools | CLI | URL | Примечание

Then mean / median / range for that model.

## CONTRACT CHECKS
Outcome / Trajectory / Privacy aggregation.
Optional domain facts such as URL integrity.

## FINDINGS
Only failed/partial runs and concise factual causes.
Do not restate every successful run.

## ARTIFACTS
Point to raw evidence conceptually; do not dump machine timestamps.

## GIT
Only facts actually captured by launcher/evidence.
```
