# Classification Contract

The skill uses a small deterministic decision pipeline instead of broad default assumptions.

## Pipeline

```text
read file → detect schema → normalize row → classify row kind → classify category → apply optional pattern rules → summarize
```

Only `booking` rows are counted. The script excludes or reports:

- `total` — explicit `Итог`/`ИТОГО` rows or safe bottom totals;
- `blank` — empty rows;
- `formula_error` — rows with `#NAME?`, `#VALUE!`, `#REF!`, `#DIV/0!`, `#N/A`;
- `non_numeric_amount` — rows where amount cannot be parsed.

## Category precedence

1. Strong lodging marker in `Детали`: `прожив`, `апартамент`, `поздний выезд`, `ранний заезд` → `Проживание в отелях`.
2. Airline in `Перевозчик` → `Авиа`. This runs before rail checks in details, so an airline ticket whose details contain an organization name with `РЖД` remains aviation.
3. Rail carrier marker in `Перевозчик` → `ЖД`.
4. Ground-transport marker such as `Аэроэкспресс`, `трансфер`, `автобус` → `ЖД` for legacy three-category reporting.
5. Rail marker in combined row text: `РЖД`, `ж/д`, `железнодорож`, `поезд`, `вагон`, `Гранд Сервис Экспресс` → `ЖД`.
6. Airline mentioned in details plus route-like structure → `Авиа`, with `needs_review=true`.
7. Probable lodging by structure: mixed/hotel-like vendor + date range + city/object pattern + not a city-to-city route → `Проживание в отелях`, with `needs_review=true`.
8. Soft hotel marker such as `отель`, `hotel`, `inn`, `apart` may classify lodging only when no airline/rail/ground marker matched; it remains `needs_review=true`.
9. Otherwise → `Unknown`.

## Mixed-service vendors

Do not classify these by vendor name alone:

```text
Trip.com, Trip, Яндекс, ДубльГис, ВАЙТ ТРЕВЕЛ
```

They can sell aviation, rail, lodging, transfers, and other services. If the details are not clear, keep `Unknown` and ask the user.

## English words in details

English may appear in hotel or airline names, for example `Hotel`, `Garden Inn`, `Turkish Airlines`, `FlyDubai`. English names may be supporting evidence, but generic English service phrases should not be required for Russian source tables.

## Fuzzy matching

Fuzzy matching is allowed only for `Перевозчик` against known airlines and with a high threshold. Do not fuzzy-match the whole `Детали` field.

## Pattern rules

Optional pattern rules are reusable carrier/details rules. One-off row-hash corrections are not supported because monthly reports rarely repeat identical rows. See `references/overrides.md`.
