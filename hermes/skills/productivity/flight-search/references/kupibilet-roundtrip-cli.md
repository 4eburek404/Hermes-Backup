# KupiBilet round-trip CLI notes

Session-derived maintenance note for the flight-search CLI after adding `kb-roundtrip`.

## When this matters

Use this reference when the user asks for a KupiBilet-style `туда-обратно одним заказом` / one-checkout round trip, especially carrier-specific direct searches such as `SVX ↔ BJS/PKX` on `U6`.

## Command shape

Run from the runtime CLI root:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli kb-roundtrip ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --direct-only \
  --limit 5
```

For machine-readable output add `--json` immediately after `flights_cli` or the installed `flights` entrypoint, according to the current CLI convention.

## Semantics

- `kb-roundtrip` sends a KupiBilet `frontend_search` payload with two `trips`: outbound `origin → destination` on `depart_date`, and return `destination → origin` on `return_date`.
- Treat matching variants as KupiBilet provider round-trip checkout offers: one seller order / checkout, but not automatically a proven airline single PNR.
- Do not replace this with summed one-way `kb-search` results when the user asks for one round-trip order and `kb-roundtrip` is available.
- Baggage variants can share the same flights with different total prices; preserve base and baggage-inclusive totals separately.

## Verification pattern after maintenance

Run focused and full tests from `cli/`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_kupibilet.py -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q
```

Run a live smoke only when external-provider access is allowed:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-roundtrip SVX BJS \
  --depart-date 2026-08-01 \
  --return-date 2026-08-08 \
  --only-carrier U6 \
  --direct-only \
  --limit 5
```

Check that the result includes both outbound and return flights, total price, currency, and baggage options. Clean generated artifacts (`__pycache__`, `.pytest_cache`, `*.pyc`) before source/runtime parity checks.
