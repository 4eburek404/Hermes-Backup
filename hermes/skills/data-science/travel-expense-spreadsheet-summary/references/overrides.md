# Pattern overrides

Overrides are user-confirmed **pattern rules** for future similar rows.
They are stored outside the code so mixed-service vendors are not hardcoded as always aviation, rail, or lodging.

Use them when the script returns `Unknown` or `needs_review=true` and the user confirms a reusable rule such as:

```text
ВАЙТ ТРЕВЕЛ + маршрут Шэньчжэнь-Сиань → Авиа
ВАЙТ ТРЕВЕЛ + маршрут Москва-Санкт-Петербург → ЖД
```

## Format

```json
{
  "version": 2,
  "pattern_overrides": [
    {
      "name": "white-travel-shenzhen-xian-air",
      "carrier_contains": "ВАЙТ ТРЕВЕЛ",
      "details_regex": "Шэньчжэнь\\s*[-–—]\\s*Сиань",
      "category": "Авиа",
      "reason": "Пользователь подтвердил: направление Шэньчжэнь-Сиань было авиаперелётом"
    }
  ]
}
```

Supported conditions:

```text
carrier_contains — string or list of strings; all must be present in carrier
carrier_regex    — regular expression against carrier
details_contains — string or list of strings; all must be present in details
details_regex    — regular expression against details
```

A rule matches only when **all specified conditions** are true.
At least one `details_contains` or `details_regex` condition is required. This intentionally blocks broad rules like “entire vendor = category”.

## Good rule

```json
{
  "carrier_contains": "ВАЙТ ТРЕВЕЛ",
  "details_regex": "Шэньчжэнь\\s*[-–—]\\s*Сиань",
  "category": "Авиа"
}
```

This is narrow enough to be reused in later months.

## Bad rule

```json
{
  "carrier_contains": "ВАЙТ ТРЕВЕЛ",
  "category": "Авиа"
}
```

This is too broad because `ВАЙТ ТРЕВЕЛ` can sell aviation, rail, lodging, transfers, and other services.

## Agent behavior

When the user confirms an ambiguous row, prefer saving a narrow pattern rule, not a one-off correction.
If no safe reusable rule can be made, leave the row as `Unknown` for that run and mention it in the report.
