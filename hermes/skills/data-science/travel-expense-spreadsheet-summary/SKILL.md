---
name: travel-expense-spreadsheet-summary
description: "Use when the user sends an Excel/CSV travel-expense spreadsheet and asks to summarize aviation, rail, hotel/lodging spend, booking counts, totals, and ambiguous rows."
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [excel, spreadsheet, travel-expenses, aviation, rail, hotels, reporting, cli]
    category: data-science
---

# Travel Expense Spreadsheet Summary

## Goal
Summarize a travel-expense Excel/CSV file by **Авиа**, **ЖД**, **Проживание в отелях**, **Unknown**, and total. Count one booking as one real source row after excluding blank/service/total rows.

## Use When
Use this skill only for travel-expense category summaries, not as a generic Excel skill. Input files may have slightly different column names such as `Дата`, `Дата покупки`, `Перевозчик`, `Поставщик`, `Детали`, `Описание`, `Сумма`, `Стоимость`.

## Run
Prefer the bundled deterministic CLI:

```bash
python3 hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/report.xlsx \
  --format json
```

For a user-facing table:

```bash
python3 hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/report.xlsx \
  --format markdown \
  --show-review
```

Excel dependencies: `.xlsx/.xlsm` need `pandas openpyxl`; `.xls` needs `pandas xlrd`; `.csv` uses the Python standard library.

## Agent Workflow
1. Run the script in JSON mode.
2. Read `summary`, `verification`, `unknown_rows`, `review_rows`, and `warnings`.
3. If `unknown_rows` or `review_rows` are non-empty, group similar rows and ask the user to classify them. Do not guess silently.
4. Save confirmed exceptions to an overrides JSON file, then rerun with `--overrides`.
5. Report the final totals and mention unresolved `Unknown` rows or verification mismatches.

## CLI

```bash
python3 scripts/travel_expense_summary.py FILE [options]
```

Key options:

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

`--strict` returns exit code `3` when user review is needed and `2` when reconciliation fails.

## Rules
Classification is deterministic and explainable. It first detects table schema, then row kind, then category. Mixed-service vendors such as `Trip.com`, `Яндекс`, `ВАЙТ ТРЕВЕЛ`, and `ДубльГис` are classified by row details, not by vendor name alone. Rows without reliable positive evidence remain `Unknown`.

See `references/classification-contract.md` and `references/overrides.md`.
