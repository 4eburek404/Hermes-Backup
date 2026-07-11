---
name: flight-search
version: 0.11.1
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

Request shaping:

- For one requested origin-to-destination journey, run one search request first. Do not replace it with manual leg searches; the CLI owns connected and gateway assembly.
- For a true multi-city or open-jaw trip, run one request per independent leg and group the canonical outputs. Do not invent a through fare, protected connection, single PNR, or price for an unsearched surface sector.
- Preserve an exact airport request. Use a city code only when the user asks for city scope; airports in the same city are not interchangeable for connection continuity.

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
  -> flight_search_user_answer.v9
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

When wave-0 primary evidence proves viable direct flights, the direct-first gate suppresses connected candidates and planned gateway probes for that direction. If no acceptable direct candidate survives, one bounded fallback wave may run.

## Gateway Assembly

`gateway_discovery_mode` is an internal route-access decision, not a request field:

- `required` applies to configured restricted-access RU markets. Gateway coverage is planned independently of provider failure, while viable direct evidence may still stop unnecessary gateway probes.
- `optional_after_provider_failure` applies to normal RU-touching and global markets. Conditional gateway probes run only when primary evidence is unavailable, unsupported, failed, or unusable.
- Gateway candidates come from configured priors and live provider signals; do not hardcode a route-specific hub in the agent answer.

Gateway continuation is not limited to a direct second leg. The planner searches the requested day and next day and allows provider-returned intermediate hubs, such as `GATEWAY→HUB→DESTINATION`. Overnight connections are allowed when valid and decision-useful.

Every adjacent segment must be airport-contiguous. Never propose a connection that changes airports; same-city airport codes are still different airports.

## Filters

Carrier filters are provider-query inputs:

- `filters.only_carriers` narrows provider/search queries to the requested carriers where supported.
- `filters.prefer_carriers` is a provider-query preference and RU-priority seed; it is not a hidden scorer gate.
- Carrier matching uses normalized codes and raw provider names.

Do not reintroduce request `constraints`; route shape belongs in `route_options`, carrier scope belongs in `filters`, and final selection belongs in the decision frontier.

## Connection and Ticketing Assessment

Keep connection feasibility separate from ticket protection:

- Separate tickets, self-transfer, or an unproven single PNR require a clear warning, but do not automatically make an otherwise valid connection `high risk`.
- Never classify a connection from one fixed layover threshold such as four hours. Use `connection_assessment`, airport continuity, timestamps, terminals, baggage/visa friction, and exact MCT evidence when available.
- `risk.grade=unknown` means the evidence does not support a numeric risk grade; it does not mean `high`.
- `long_wait` and `overnight_wait` are comfort/visibility labels, not automatic rejection reasons. Suppress only options that violate hard feasibility or the active business stop policy.
- Do not claim protected transfer, through baggage, single ticket, or single PNR unless provider or booking-screen evidence proves it.

## Evidence Boundaries

Use result fields for evidence and absence language:

- Provider offers are shopping evidence, not booking proof.
- Empty provider output is not proof that no flight exists outside executed probes.
- Static catalogs, cached metadata, and diagnostics do not prove availability.
- Named airports are not city scope unless the request or report explicitly broadens scope.
- For round trips, frontier options are outbound+return pairs; unpaired directional evidence stays in route diagnostics, not in the public answer.

Read `references/report-contract.md` for answer fields, `references/source-boundaries.md` for MCT/ticketing/risk wording, and `references/pipeline-reference.md` for gateway/provider mechanics.

## Diagnostics

Use diagnostics to inspect the pipeline, not as traveler-facing answers:

```bash
python3 -m flights_cli --json diagnose plan --request "$HOME/flight-search-request.json"
python3 -m flights_cli --json diagnose probe --provider tutu --request "$HOME/probe.json"
python3 -m flights_cli --json diagnose render --input "$HOME/flight-search-result.json"
python3 -m flights_cli --json diagnose trace --request "$HOME/flight-search-request.json"
```

Provider-specific raw-search commands are intentionally absent from the agent surface. For a normal traveler request, use `search --request` and return text stdout without summarizing or reformatting it. Use diagnostics only to inspect plan, provider, validation, evidence, or decision artifacts.

For conditional reference loading and ownership, start from `references/index.md`.
