---
name: flight-search
version: 0.8.6
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find, compare, or diagnose live flights via the bundled CLI. One adult, economy. Never books.

## Run

1. Normalize route/date/scope: exact airports vs city, carrier, direct-only, return date, ticketing intent, profile (`business` default).
2. Write a `flight_search_request.v1` (template below; full schema in `cli/`).
3. Run the canonical path — do not provider-probe first:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search --request /tmp/flight-search-request.json
```

4. Answer only from `data.agent_report.user_answer.rendered_text`. Read order, fields, renderer contract: `references/report-contract.md`.

```json
{"schema_version":"flight_search_request.v1","origin":"ORIGIN","destination":"DEST","depart_date":"YYYY-MM-DD","profile":"business"}
```

Direct-only: add `"route_options":{"max_connections":0}`. Date window: add request-only `"route_options":{"max_connections":0,"tier2_max_connections":0,"date_window_end":"YYYY-MM-DD"}` and omit `return_date`; there is no `--date-window-end` flag. Carrier scope: `"filters":{"only_carriers":[...]}`. Return: `"return_date":"YYYY-MM-DD"`. Currency, ticketing, provider_policy, and agent_brief default in the CLI.

## Invariants

Apply to every reply. Full evidence/absence taxonomy: `references/source-boundaries.md`.

1. Provider output is shopping evidence, not booking proof. Single PNR, through-baggage, protection, fare rules, refund/exchange, and terminal certainty are **unproven** unless purchase-screen / airline-GDS / seller / explicit upstream proof says otherwise.
2. Empty provider output is not "no flights" unless targeted controls or structural route evidence support it.
3. Metadata never proves availability — static catalogs, cached fare helpers, maintenance diagnostics, and `data.catalog_auto_refresh` describe metadata only.
4. Named airports are not city scope. If you broaden ORIGIN/DEST, say so and why.
5. Take freshness, controls, provider failures, and missing evidence from report fields, not your own reasoning. Never re-rank, rewrite, or paste raw diagnostic JSON.
6. Short direct set? When direct exists the report shows all direct and suppresses connected (per-direction on round-trips). If fewer than expected, run `diagnose kb-search ORIGIN DEST --direct-only --limit 20` before blaming the provider — truncation is usually in the display pipeline. Current mechanism and debug route are mapped in `references/index.md`.

## Beyond the happy path

When the happy path is not enough — missing evidence, narrower proof (date-window, carrier/exact-airport, PNR/baggage), market controls (RU-domestic, RU-touching, global non-RU), train comparison, or any maintenance/debug/refactor — `references/index.md` is the canonical reference owner map and routes you to the right file. Never expose maintenance output as the traveler answer.
