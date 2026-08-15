---
name: travel-expense-spreadsheet-summary
description: "Use when the user sends an Excel/CSV travel-expense spreadsheet and asks to summarize aviation, rail, lodging, Unknown, booking counts, totals, and ambiguous rows."
version: 2.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [excel, spreadsheet, travel-expenses, aviation, rail, hotels, reporting, cli]
    category: travel
---

# Travel Expense Spreadsheet Summary

## Goal
Summarize a travel-expense Excel/CSV file by **Авиа**, **ЖД**, **Проживание в отелях**, **Unknown**, and total. One booking is one real source row after excluding blank/service/total rows.

## Use When
Use only for travel-expense category summaries, not as a generic Excel skill. Files may use different column names such as `Дата`, `Дата покупки`, `Перевозчик`, `Поставщик`, `Детали`, `Описание`, `Сумма`, `Стоимость`.

## Run
Prefer the bundled deterministic CLI:

Treat the directory containing this `SKILL.md` as `<skill-root>` and resolve
every bundled path relative to it.
Use `"${HERMES_SKILLS_PYTHON:-python3}"` as the Python interpreter for bundled
commands. When `HERMES_SKILLS_PYTHON` is set, use that exact executable;
otherwise use `python3`.

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/travel_expense_summary.py" \
  /path/to/report.xlsx \
  --format json
```

For a user-facing table:

```bash
"${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/travel_expense_summary.py" \
  /path/to/report.xlsx \
  --format markdown \
  --show-review
```

Excel dependencies: `.xlsx/.xlsm` need `pandas openpyxl`; `.xls` needs `pandas xlrd`; `.csv` uses the Python standard library.

## Agent Workflow
1. Run JSON mode.
2. Check `summary`, `verification`, `unknown_rows`, `review_rows`, and `warnings`.
3. If there are `Unknown`/review rows, group similar rows and ask the user. Do not guess silently.
4. Use `--overrides` only for narrow reusable pattern rules by carrier/details. Do not create one-off row-hash corrections.
5. Report final totals and any unresolved `Unknown` or reconciliation mismatch.

## CLI

```text
--format json|markdown
--sheet NAME_OR_INDEX
--overrides overrides.json
--output result.json
--show-review
--strict
--date-col NAME
--carrier-col NAME
--details-col NAME
--amount-col NAME
```

`--strict` returns exit code `3` when review is needed and `2` when reconciliation fails.

## Rules
The classifier is conservative and field-aware: schema detection first, row-kind detection second, category decision third. Mixed-service vendors such as `Trip.com`, `Яндекс`, `ВАЙТ ТРЕВЕЛ`, and `ДубльГис` are classified by row details, not by vendor name alone. Rows without reliable positive evidence remain `Unknown`.

See `references/classification-contract.md` and `references/overrides.md`.
