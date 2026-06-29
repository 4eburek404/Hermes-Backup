# Travel Expense Spreadsheet Summary skill update

This package replaces the monolithic script with a small modular pipeline:

- `scripts/travel_expense_summary.py` — CLI entrypoint;
- `scripts/travel_expense/io.py` — CSV/Excel loading;
- `scripts/travel_expense/schema.py` — header and column detection;
- `scripts/travel_expense/row_types.py` — booking/total/service row detection;
- `scripts/travel_expense/classifier.py` — deterministic category decisions;
- `scripts/travel_expense/overrides.py` — manual exception loading;
- `scripts/travel_expense/summary.py` — orchestration and reconciliation;
- `scripts/travel_expense/render.py` — JSON/Markdown output.

Run tests from this directory with:

```bash
PYTHONPATH=scripts python3 -m pytest tests -q
```
