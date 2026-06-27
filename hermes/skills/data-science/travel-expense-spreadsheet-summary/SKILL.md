---
name: travel-expense-spreadsheet-summary
description: "Use when the user sends an Excel/CSV travel-expense spreadsheet and asks to summarize aviation, rail, hotel/lodging spend, booking counts, and total."
version: 1.1.0
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

Посчитать по пользовательскому Excel/CSV-файлу командировочных расходов:

- расходы и количество бронирований по **авиа**;
- расходы и количество бронирований по **ЖД**;
- расходы и количество бронирований по **проживанию в отелях**;
- общий **ИТОГО**;
- сверку с итоговой строкой файла, если она есть.

Главное правило: **одно бронирование = одна строка исходной таблицы после удаления итоговых/служебных строк**, если пользователь не сказал иначе.

## When to Use

Use this skill when:

- пользователь прислал `.xls`, `.xlsx`, `.xlsm` или `.csv` со статистикой/расходами по поездкам;
- просит посчитать авиа / ЖД / отели / количество бронирований / общий итог;
- в таблице есть колонки вроде `Дата`, `Сотрудник`, `Перевозчик`, `Номер билета`, `Детали`, `Сумма`;
- поставщики могут быть смешанными: `Trip.com`, `Яндекс`, `ДубльГис`, `Комфорт Букинг`, `РЖД`, авиакомпании и т.п.

Do **not** use this as a generic Excel skill. It is specifically for travel-expense category summaries.

## Primary Workflow

### 1. Run the bundled script

Prefer the deterministic script over rebuilding ad-hoc pandas code from memory:

```bash
python3 hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/file.xls \
  --format json
```

For old `.xls` files, the active Python environment needs `pandas` + `xlrd`; for `.xlsx`/`.xlsm`, it needs `pandas` + `openpyxl`. In PEP 668 environments, use a temporary venv rather than installing globally:

```bash
python3 -m venv /tmp/excelenv
/tmp/excelenv/bin/python -m pip install -q --upgrade pip
/tmp/excelenv/bin/python -m pip install -q pandas xlrd openpyxl
/tmp/excelenv/bin/python hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/file.xls \
  --format json
```

For CSV files, the script uses the Python standard library and does not need pandas.

Completion criterion: the script exits `0` and returns JSON or Markdown.

### 2. Inspect verification and warnings

In JSON output, check:

- `verification.clean_rows` — count of real booking rows after removing `Итог`/`Total`;
- `verification.category_rows` — sum of rows assigned to categories;
- `verification.category_sum` — sum of all categories;
- `verification.source_total_present` — whether a workbook total row was found;
- `verification.source_total_sum` / `source_total_count` — source control values;
- `verification.matches_source_total` — final reconciliation result.

Also inspect `warnings` before answering. Warnings are not automatic failures; they are rows the agent should be aware of when writing assumptions:

| Warning | Meaning |
|---|---|
| `mixed_service_vendor` | A platform such as `Trip.com` can contain multiple service types; classification came from row details. |
| `missing_carrier_air_route` | Carrier is empty, but the row fell into aviation by route/default logic. |
| `hotel_vendor_without_lodging_marker` | Vendor looks hotel-related, but details did not contain `прожив`; verify before final answer. |

Completion criterion: totals reconcile, or the mismatch/warning is understood and can be explained.

### 3. Report the result first

Use the script's Markdown output when possible:

```bash
python3 hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/file.xls \
  --format markdown
```

Expected user-facing format:

```markdown
Посчитал по файлу `<имя файла>`. Строку `Итог` не включал как бронирование, использовал её для сверки.

| Категория | Бронирований | Сумма |
|---|---:|---:|
| **Авиа** | N | X ₽ |
| **ЖД** | N | X ₽ |
| **Проживание в отелях** | N | X ₽ |
| **ИТОГО** | N | X ₽ |

Сверка: сумма по категориям совпадает с итоговой строкой файла — X ₽.
Примечание: `Аэроэкспресс` включён в ЖД; строки без перевозчика с авиамаршрутом отнесены к авиа.
```

Keep the final answer compact unless the user explicitly asks for methodology.

## Classification Contract

The script applies this precedence, top-to-bottom:

1. **Проживание в отелях** — `Детали` contains `прожив...`.
2. **ЖД** — combined carrier/details text contains `ржд`, `жд`, `ж/д`, `гранд сервис`, `аэроэкспресс`, or common misspelling `аэроэскпресс`.
3. **Авиа** — everything not classified as lodging or rail, including airline carriers and missing-carrier rows with flight-style routes.

Important consequences:

- `Аэроэкспресс` is counted as **ЖД/rail transfer**, not aviation, unless the user asks for a separate ground-transport category.
- `Trip.com` is classified per row details: `ЖД...` rows go to **ЖД**, `проживание...` rows go to **Проживание**.
- Airline rows containing a hotel name only as a trip note are still **Авиа** unless the details explicitly say `прожив...`.

## CLI Reference

```bash
python3 scripts/travel_expense_summary.py FILE [options]
```

Options:

| Option | Purpose |
|---|---|
| `--format json` / `--format markdown` | Machine-readable output for agent checks or ready-to-send table. |
| `--sheet NAME_OR_INDEX` | Excel sheet; default is the first sheet. |
| `--amount-col Сумма` | Override amount column. |
| `--carrier-col Перевозчик` | Override carrier/vendor column. |
| `--details-col Детали` | Override details/route/lodging column. |
| `--date-col Дата` | Override date/first-column total-row detection. |
| `--show-warnings` | Append warning rows to Markdown output. |

## Test / Maintenance Workflow

Tests live next to the script:

```text
scripts/travel_expense_summary.py
scripts/test_travel_expense_summary.py
```

Run targeted tests after any script or classification change:

```bash
python3 -m pytest hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/test_travel_expense_summary.py -q
```

For behavior changes, follow TDD: update/add the test first, watch it fail, then update the script.

## Common Pitfalls

1. **Задвоить итоговую строку.** The script excludes `Итог`/`Total` rows from booking counts and uses them only for reconciliation.
2. **Считать только по перевозчику.** Mixed platforms such as `Trip.com` can include rail and hotel rows; classification must use row details.
3. **Отнести Аэроэкспресс к авиа.** Count it as ЖД/rail transfer for this three-category report unless the user says otherwise.
4. **Потерять строки без перевозчика.** Missing carrier rows can still be aviation if details show a flight route.
5. **Считать сегменты маршрута как отдельные бронирования.** By default, booking count is row count, not route segment count.
6. **Отчитаться без сверки.** Do not present totals as final until category sums match cleaned rows and, when present, the source total row.

## Verification Checklist

- [ ] Script ran successfully on the supplied file.
- [ ] `verification.category_rows == verification.clean_rows`.
- [ ] Category summary contains `Авиа`, `ЖД`, `Проживание в отелях`, and `ИТОГО`.
- [ ] If source total row exists, `verification.matches_source_total` is `true`; otherwise mismatch is explained.
- [ ] `warnings` were inspected and relevant assumptions are mentioned in the final answer.
- [ ] If code changed, targeted tests passed.
