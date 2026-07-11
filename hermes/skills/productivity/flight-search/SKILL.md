---
name: flight-search
version: 0.11.0
description: Use when finding, comparing, or diagnosing live flight route options with the bundled flights CLI; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find, compare, or diagnose live flight options through the bundled CLI. One adult, economy. Never books or claims final fare, baggage, protected transfer, or single PNR unless the provider/booking screen proves it.

## Canonical Run

Write a `flight_search_request.v1` JSON file and run:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli search --request "$HOME/flight-search-request.json"
```

Return text-mode CLI stdout verbatim. In JSON mode the same canonical text is
`data.answer.rendered_text`; do not rewrite it from provider payloads.

Minimal request:

```json
{"schema_version":"flight_search_request.v1","origin":"ORIGIN","destination":"DEST","depart_date":"YYYY-MM-DD","profile":"business"}
```

Common options:

- Direct only: `"route_options":{"max_connections":0,"tier2_max_connections":0}`
- Date window: add `"date_window_end":"YYYY-MM-DD"` inside `route_options`; omit `return_date`.
- Return trip: `"return_date":"YYYY-MM-DD"`
- Carrier filters: `"filters":{"only_carriers":["KL"],"prefer_carriers":["KL"]}`
- Provider override only when needed: `"provider_policy":"tutu"`, `"kupibilet"`, or `"fli"`

## Pipeline

Runtime flow:

```text
raw JSON
  -> SearchRequest
  -> SearchPlan
  -> SearchExecutor
  -> SearchEvidence
  -> SearchDecision
  -> flight_search_result.v7
  -> pure render
  -> stdout
```

There is no legacy assembly or reporting fallback: the decision frontier is the
only source of traveler-visible options.

## Providers

Provider routing is per probe, not per whole search.

- `tutu` is the default primary provider.
- In `auto`, a successful Tutu MCP probe stops fallback execution for the same logical probe.
- `kupibilet` is fallback only when Tutu is unavailable, fails, or does not support the probe and KupiBilet capability/market fit it.
- `fli` is fallback only for non-RU probes when Tutu is unavailable, fails, or does not support the probe.
- `provider_policy=both` is invalid.

Tutu returns shopping evidence. It can return connected offers and supports pagination through the adapter. Carrier names are resolved through localized airline catalogs into canonical carrier codes, not route-specific code.

When wave-0 primary offers prove direct flights for a direction, the direct-first gate suppresses connected options for that direction unless route options explicitly allow connected alternatives.

## Filters

Carrier filters are provider-query inputs:

- `filters.only_carriers` narrows provider/search queries to the requested carriers where supported.
- `filters.prefer_carriers` is a provider-query preference and RU-priority seed; it is not a hidden scorer gate.
- Carrier matching uses normalized codes and raw provider names.

Do not reintroduce request `constraints`; route shape belongs in `route_options`, carrier scope belongs in `filters`, and final selection belongs in the decision frontier.

## Evidence Boundaries

Use result fields for evidence and absence language:

- Provider offers are shopping evidence, not booking proof.
- Empty provider output is not proof that no flight exists outside executed probes.
- Static catalogs, cached metadata, and diagnostics do not prove availability.
- Named airports are not city scope unless the request or report explicitly broadens scope.
- For round trips, frontier options are outbound+return pairs; unpaired directional evidence stays in route diagnostics, not in the public answer.

Details: `references/report-contract.md`, `references/source-boundaries.md`, and `references/pipeline-reference.md`.

## Diagnostics

Use diagnostics to inspect the pipeline, not as traveler-facing answers:

```bash
python3 -m flights_cli --json diagnose plan --request "$HOME/flight-search-request.json"
python3 -m flights_cli --json diagnose probe --provider tutu --request "$HOME/probe.json"
python3 -m flights_cli --json diagnose trace --request "$HOME/flight-search-request.json"
```

Provider-specific raw-search commands are intentionally absent from the agent
surface. Use `search --request` and read
`data.answer.rendered_text`. For a normal traveler request, return text-mode
stdout without summarizing or reformatting it. Use `diagnose trace` only when
you need the internal plan/evidence/decision artifacts.

For CLI/debug ownership and source boundaries, start from `references/index.md`.
