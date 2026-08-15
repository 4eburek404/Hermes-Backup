# Travel Expense Spreadsheet Summary skill update

This package is a modular replacement for the monolithic travel-expense summary script.

The main design choice is conservative classification: keep the old skill's reliable precedence, add schema/row-kind robustness, and avoid broad guesses for mixed-service vendors.

## Modules

- `scripts/travel_expense_summary.py` — CLI entrypoint;
- `scripts/travel_expense/io.py` — CSV/Excel loading;
- `scripts/travel_expense/schema.py` — header and column detection;
- `scripts/travel_expense/row_types.py` — booking/total/service row detection;
- `scripts/travel_expense/classifier.py` — deterministic category decisions;
- `scripts/travel_expense/overrides.py` — narrow reusable pattern rules;
- `scripts/travel_expense/summary.py` — orchestration and reconciliation;
- `scripts/travel_expense/render.py` — JSON/Markdown output.

## Run

```bash
PYTHONPATH=scripts python3 scripts/travel_expense_summary.py /path/to/report.xlsx --format markdown --show-review
```

## Test

```bash
PYTHONPATH=scripts python3 -m pytest tests -q
```
