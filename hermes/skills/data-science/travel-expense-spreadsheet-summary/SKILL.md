---
name: travel-expense-spreadsheet-summary
description: "Use when the user sends an Excel/CSV travel-expense spreadsheet and asks to summarize aviation, rail, hotel/lodging spend, booking counts, and total."
version: 1.4.0
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
- **Unknown** — строки, не классифицированные точно (нет положительного совпадения по авиакомпании/ЖД/отелю). Перечислить пользователю и спросить классификацию — **не** относить к авиа автоматически;
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

For old `.xls` files, the active Python environment needs `pandas` + `xlrd`; for `.xlsx`/`.xlsm`, it needs `pandas` + `openpyxl`. For CSV files, the script uses the Python standard library and does not need pandas.

**On the user's Hermes Windows setup** the working Python is the Hermes venv at `C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Scripts\python` (Python 3.11). `pandas`, `xlrd`, and `openpyxl` are already installed there — just run the script directly:

```bash
python "C:/Users/user/AppData/Local/hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py" \
  /path/to/file.xls \
  --format json
```

If packages are missing from the Hermes venv, install them there directly (NOT in a temp venv — the user wants them permanent across sessions):

```bash
# pip may not be bootstrapped in the Hermes venv — fix with ensurepip first
python -m ensurepip --upgrade
python -m pip install pandas xlrd openpyxl
```

In PEP 668 environments (system Python on Linux), fall back to a temporary venv. On Windows, venv executables live under `Scripts/` not `bin/`:

```bash
python -m venv /tmp/excelenv
/tmp/excelenv/Scripts/python.exe -m pip install -q pandas xlrd openpyxl
/tmp/excelenv/Scripts/python.exe hermes/skills/data-science/travel-expense-spreadsheet-summary/scripts/travel_expense_summary.py \
  /path/to/file.xls \
  --format json
```

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
| `missing_carrier_air_route` | Carrier field is empty, but an airline marker was found in details. Rare after the Unknown category was introduced — most empty-carrier rows now go to Unknown instead. |
| `hotel_vendor_without_lodging_marker` | Vendor looks hotel-related, but details did not contain `прожив`, `апартамент`, or `поздний выезд`; verify before final answer. |
| `unknown_category` | Row did not match any known airline/rail/hotel marker. Agent must list these rows and ask the user to classify them. |

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
Примечание: `Аэроэкспресс` включён в ЖД; `апартаменты` отнесены к проживанию.
```

If `Unknown` has bookings, append a list of those rows and ask the user to classify them:

```markdown
**Unknown — нужно уточнить:**

| Строка | Перевозчик | Детали | Сумма |
|---|---|---|---:|
| 163 | ООО «ВАЙТ ТРЕВЕЛ» Москва | Приказ 5434, 04.05.2026 Санкт-Петербург-Великие Луки | 2 024,00 ₽ |
```

Keep the final answer compact unless the user explicitly asks for methodology.

## Classification Contract

> **See also:** `references/carrier-classification.md` — full carrier inventory and decision log from real files.

The script applies this precedence, top-to-bottom:

1. **Проживание в отелях** — `Детали` contains `прожив...`, `апартамент...`, or `поздний выезд...`.
2. **Авиа (carrier match)** — `Перевозчик` alone matches a known airline marker. This check runs **before** ЖД so that an airline ticket to a company whose name contains «РЖД» (e.g. «Конструкторское бюро РЖД») is correctly classified as Авиа.
3. **ЖД** — combined carrier/details text contains `ржд`, `жд`, `ж/д`, `гранд сервис`, `аэроэкспресс`, or common misspelling `аэроэскпресс`.
4. **Авиа (details match)** — combined carrier/details text matches a known airline marker (for rows where carrier is empty but details mention the airline).
5. **Unknown** — everything not matching any of the above. Rows are **not** auto-classified as Авиа; they are listed for the user to classify manually.

Known airline markers: `аэрофлот`, `победа`, `air `, `airlines`, `airways`, `turkish`, `ютэйр`, `red wings`, `ред вингс`, `нордстар`, `nordstar`, `уральские`, `северсталь`, `belavia`, `indigo`, `hainan`, `tianjin`, `china eastern`, `china southern`, `china united`, `spring`, `s7`, `с7`, `emirates`, `etihad`, `fly dubai`, `flydubai`, `ювт аэро`, `ювтаэро`, `nordwind`, `нордвинд`, etc. See `references/carrier-classification.md` for the full list.

Important consequences:

- `Аэроэкспресс` is counted as **ЖД/rail transfer**, not aviation, unless the user asks for a separate ground-transport category.
- `ВАЙТ ТРЕВЕЛ` is a mixed-service vendor (like Trip.com) — classified per row details. Rows without a clear hotel/rail/airline marker go to **Unknown** for the user to classify.
- `Trip.com` is classified per row details: `ЖД...` rows go to **ЖД**, `проживание...` rows go to **Проживание**.
- Airline rows containing a hotel name only as a trip note are still **Авиа** unless the details explicitly say `прожив...`, `апартамент...`, or `поздний выезд...`.
- If `Перевозчик` is an airline (e.g. Аэрофлот), the row is **Авиа** even if the details contain `РЖД` as part of an organisation name (e.g. «Конструкторское бюро РЖД»). The carrier-field airline check runs before the ЖД marker check.
- `трансфер` as carrier (e.g. airport-to-hotel transfer) — user classified as **ЖД/наземный транспорт**. Not auto-classified; goes to Unknown for user confirmation.
- Rows with no carrier and no positive airline/rail/hotel marker go to **Unknown**, not Авиа. The agent must list them and ask the user to classify.
- `апартаменты` / `апартамент` in details is always **Проживание в отелях**, even when the vendor (e.g. `Яндекс`) is not a hotel-specific platform. The user confirmed: «апартаменты это проживание 100%».
- `поздний выезд` (late check-out surcharge) is always **Проживание в отелях**. User confirmed.

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
4. **Автоматически относить неизвестные строки к Авиа.** Строки без положительного совпадения по авиакомпании/ЖД/отелю идут в **Unknown**. Агент должен перечислить их пользователю и спросить классификацию.
5. **Считать сегменты маршрута как отдельные бронирования.** By default, booking count is row count, not route segment count.
6. **Отчитаться без сверки.** Do not present totals as final until category sums match cleaned rows and, when present, the source total row.
7. **Использовать temp venv вместо рабочего окружения.** On the user's Hermes setup, install pandas/xlrd/openpyxl into the Hermes venv directly (`python -m ensurepip --upgrade && python -m pip install …`) so they persist across sessions. A temp venv works but wastes time reinstalling every session. If the Hermes venv lacks pip, bootstrap with `ensurepip` first.
8. **Использовать Linux-пути к venv на Windows.** Windows venv executables are under `Scripts/` not `bin/` — use `venv/Scripts/python.exe`, not `venv/bin/python`.
9. **Отнести «апартаменты» к авиа.** If details contain `апартамент` (e.g. «Приказ, 16.03-17.03.2026, Екатеринбург, апартаменты»), the row is **Проживание в отелях** — even when the vendor is `Яндекс` and there is no `прожив` marker. The user confirmed: «апартаменты это проживание 100%». When in doubt, ask the user rather than silently classifying as авиа.
10. **Пропустить латинское написание авиакомпании.** Real files mix Cyrillic and Latin: `NordStar` alongside `НОРДСТАР`, `ЮВТАЭРО` without space alongside `ЮВТ АЭРО`, `Fly Dubai` / `flydubai`, `Emirates`, `Etihad`. When adding an airline to `AIRLINE_MARKERS`, add both scripts and no-space variants. See `references/carrier-classification.md` for the full list.
11. **Считать расхождение по количеству ошибкой скрипта.** Some source files have an incorrect booking count in the `Итог` row (e.g. count cell says 242, actual rows 244). When `matches_source_total` is `false` but `category_sum == source_total_sum`, the sum is verified — the count discrepancy is a source-file error, not a script bug.
12. **Пропустить итоговую строку с нестандартным расположением.** Some files put `ИТОГО:` in the `Детали` column with an empty date column, or use `Дата покупки` instead of `Дата` as the date column name. The script's `is_total_row` scans all column values for `ИТОГО`/`Total` labels, so both cases are handled. Additionally, some files have a total row with **no label at all** — just an empty date, empty carrier, a count number in `Детали`, and the total sum in `Сумма`. The script's fallback rule (empty date + empty carrier → total row) catches this. If a total row is still missed (`source_total_present` is false but the file clearly has one), check the total row's cell layout and update `is_total_row` if needed.
13. **Отнести авиабилет к ЖД из-за «РЖД» в названии организации.** If `Перевозчик` is an airline (e.g. Аэрофлот) but `Детали` contains «РЖД» as part of a company name (e.g. «Конструкторское бюро РЖД»), the row is **Авиа**. The script checks `AIRLINE_MARKERS` against the carrier field **before** checking `RAIL_MARKERS` against combined text. User explained: «в деталях РЖД - это командировка в компанию "Конструкторское бюро РЖД"».
14. **Опечатки в названии авиакомпании в исходном файле.** Source files contain typos like «Авивкомпания» instead of «Авиакомпания». When adding an airline marker, use a distinctive substring (e.g. `turkish` for Turkish Airlines) that works regardless of the typo in the surrounding text. Don't add `авиа` as a general marker for this — it's already in `AIRLINE_MARKERS` but can false-positive on non-airline text; airline-specific markers are more reliable.

## Verification Checklist

- [ ] Script ran successfully on the supplied file.
- [ ] `verification.category_rows == verification.clean_rows`.
- [ ] Category summary contains `Авиа`, `ЖД`, `Проживание в отелях`, `Unknown` (if non-empty), and `ИТОГО`.
- [ ] If `Unknown` has bookings, all `unknown_category` warnings are listed for the user to classify.
- [ ] If source total row exists, `verification.matches_source_total` is `true`; otherwise mismatch is explained (count mismatch = source-file error if sum matches).
- [ ] `warnings` were inspected and relevant assumptions are mentioned in the final answer.
- [ ] If code changed, targeted tests passed.
- [ ] If new airlines were added to `AIRLINE_MARKERS`, both Cyrillic and Latin variants are included.
