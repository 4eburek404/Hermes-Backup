# Overrides

Overrides are manual decisions for ambiguous rows, stored outside the code.

Use them when the script returns `Unknown` or `needs_review=true` and the user confirms the category. This prevents repeated questions for the same row without hardcoding a mixed-service vendor as always aviation, rail, or lodging.

## Preferred format

```json
{
  "version": 1,
  "rows": {
    "ebc9500b4cc40fa7": {
      "category": "Авиа",
      "reason": "Пользователь подтвердил: Шэньчжэнь-Сиань был авиаперелётом"
    }
  }
}
```

The key is a fingerprint calculated from normalized date, carrier, details, and amount. It is safer than a row number because row numbers can shift when the source file changes.

## Simple compatible format

The script also accepts:

```json
{
  "ebc9500b4cc40fa7": "Авиа"
}
```

## Row-number fallback

The script can read row-number overrides, but they are brittle and should be used only for one-off processing:

```json
{
  "163": "ЖД"
}
```
