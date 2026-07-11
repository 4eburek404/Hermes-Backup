---
name: flight-search
version: 0.11.2
description: Use when finding, comparing, assembling, or diagnosing live flight options with the bundled flights CLI, including direct, round-trip, open-jaw leg, and RU-gateway searches; assumes one adult in economy and never books tickets.
metadata:
  hermes:
    category: productivity
    tags: [flights, travel, routing]
    requires_toolsets: [terminal]
---

# Flight Search

Find, compare, or diagnose live flight options through the bundled CLI. One adult, economy. Never books or claims final fare, baggage, protected transfer, or single PNR unless the provider/booking screen proves it.

## Golden Path

Write a `flight_search_request.v1` JSON file and run:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli search --request "$HOME/flight-search-request.json"
```

For a normal traveler request, return text-mode CLI stdout to the user verbatim.
Do not summarize, reformat, reorder, annotate, correct, or otherwise improve it.
In JSON mode, return `data.answer.rendered_text` verbatim.

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

Request shaping:

- For one requested origin-to-destination journey, run one search request first. Do not replace it with manual leg searches; the CLI owns connected and gateway assembly.
- For a true multi-city or open-jaw trip, run one request per independent leg and group the canonical outputs. Do not invent a through fare, protected connection, single PNR, or price for an unsearched surface sector.
- Preserve an exact airport request. Use a city code only when the user asks for city scope; airports in the same city are not interchangeable for connection continuity.
- Do not manually assemble, supplement, remove, rerank, or rewrite connected or gateway options. Same-day, overnight, and multi-hop gateway discovery belong to the CLI.
- An adjacent cross-airport connection is invalid. If the CLI emits one, do not silently repair or present it as valid; run diagnostics and report the pipeline defect.

## Failure and Diagnostics

If canonical search fails or produces no traveler answer, report that failure instead of fabricating or manually reconstructing an itinerary. Diagnostics may explain the failure, but diagnostic JSON and probe logs are not traveler-facing answers.

Read `references/debug-playbook.md` for `diagnose plan`, `probe`, `render`, and `trace` commands.

## Reference Routing

- Read `references/report-contract.md` when inspecting answer fields, frontier order, or renderer behavior.
- Read `references/pipeline-reference.md` for provider dispatch, direct-first, gateway modes, next-day/multi-hop assembly, and filter mechanics.
- Read `references/source-boundaries.md` for availability, airport continuity, MCT, ticketing, protection, and risk claims.
- Read `references/cli-maintenance.md` only for source, schema, version, test, or release work.
- Start from `references/index.md` when ownership is unclear.
