# flights CLI

Concise manual for the flight-search skill-owned CLI. The skill's Golden Path is
`search --request`; other commands support setup, metadata, or targeted
diagnostics. Paths in this manual are relative to the skill root: the directory
containing the parent `SKILL.md`.

## What It Automates

- Route/date/IATA normalization and bounded provider execution.
- Airport compatibility checks for same-airport and cross-airport connections.
- Candidate generation, scoring, one decision frontier, and result projection.
- Direct, carrier, aggregate, and coverage controls when the current provider policy calls for them.
- Static metadata lookup for city, airport, country/region, airline, alliance, and aircraft labels.
- A compact `flight_search_result.v8` with `route`, `evidence`, `frontier`, and the canonical `answer`.

The CLI does not book, buy, or write to agent runtime state.

## Install

Normal one-off runs do not need installation. If you are explicitly setting up
the runtime CLI entry point, resolve `cli/` from the active skill root, use it as
the command's working directory, and then check/report generated artifacts
(`*.egg-info`, caches):

```bash
python3 -m pip install -e .
```

For source-development checkouts, use the source root documented in `references/cli-maintenance.md`, then prove source/runtime provenance before claiming runtime behavior.

For one-off local runs without installation, execute from the same directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maint doctor
```

## Dependencies

Runtime dependency: `jsonschema>=4.22,<5` as declared in `pyproject.toml`. The package also uses Python standard-library modules and local CLI package modules.

## JSON Envelope

Use `--json` for agent work. Successful commands return a JSON envelope with command metadata and `data`. Errors return a JSON envelope with `ok: false` and structured error detail.

Stdout must stay JSON-clean in `--json` mode. Human diagnostics and provider logs belong on stderr or structured fields.

## Maint Doctor

Use doctor for environment readiness and degradation clues:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maint doctor
```

Doctor output is not a flight answer. Treat `ok: false` as an environment/readiness signal and inspect the structured issues.

## Maintenance Check

Use `maint check` when auditing source/runtime provenance or debugging local route-quality maintenance state. It is offline-only and reports paths, Git state, version markers, source/runtime parity, reference counts, generated-artifact counts, and doctor status without emitting credential values.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maint check
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli maint check --runtime-path "<skill-root>"
```

Missing runtime paths are reported as structured status, not treated as fatal CLI errors.

## Static Catalog Metadata Commands

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Useful metadata commands:

```bash
python3 -m flights_cli --json maint catalog manifest
python3 -m flights_cli --json maint catalog refresh --dry-run
python3 -m flights_cli --json cities search Yekaterinburg
python3 -m flights_cli --json airports explain SVX MOW
```

Use these commands for normalization and airport/city boundaries, not for availability claims.

## Golden Path: search --request

Primary agent command:

```bash
cat > /tmp/flight-search-request.json <<'JSON'
{
  "schema_version": "flight_search_request.v2",
  "origin": "ORIGIN",
  "destination": "DEST",
  "depart_date": "YYYY-MM-DD",
  "currency": "RUB",
  "profile": "business",
  "ticketing": "separate",
  "provider_policy": "auto"
}
JSON
python3 -m flights_cli search --request /tmp/flight-search-request.json
```

Return this text stdout verbatim. With `--json`, the canonical serialized paths are:

- `answer.rendered_text`
- `answer.catalog.items`
- `frontier.option_ids`
- `evidence.coverage`
- `evidence.provider_failures`
- `evidence.source_boundaries`

Full graph/debug traces are excluded from default `search` output. Use
`diagnose trace --request` and inspect `data.plan`, `data.evidence`, and
`data.decision` when you need internal artifacts.

`search --request` searches and compares route options for the default scope of one adult in economy. It does not buy or book tickets, and final fare, baggage-through, refund/change conditions, disruption protection, and single-PNR claims require purchase-screen, airline/GDS, seller, or explicit upstream proof.

Common request fields:

- `return_date: "YYYY-MM-DD"`
- `profile: "business"` is the only production search profile; omit it to use the default
- `provider_policy: "auto"|"tutu"|"kupibilet"|"fli"`
- `route_options.stop_policy: "business-default"|"strict-direct-one-stop"|"allow-two-stop-fallback"|"debug-all"`
- `route_options.date_window_end: "YYYY-MM-DD"` for bounded one-way direct-only inventory; request-only, no CLI flag
- `filters.only_carriers: ["CODE"]`
- `route_options.coverage_mode: "standard"|"targeted"|"full"`
- `evidence.no_live_cache: true` for a fresh live probe when appropriate

## Ranking Profile

Production search uses one ranking profile: `business`. It prioritizes visible non-rejected options, requested-trip coverage, fewer connections, lower operational risk, shorter elapsed time, then price. Business output suppresses excessive connection waits unless they are late-arrival to next-morning overnight transfers. Unsafe transfers can still be rejected.

## Stop Policy and Reportability

- Direct and one-stop journeys are preferred.
- Two-stop journeys are fallback/reportable only when no viable direct/one-stop option exists or the report explicitly marks fallback/reportability.
- Three-or-more-connection itineraries are suppressed from normal recommendations.

## Provider Policy

`search --request` chooses a live source mix through `provider_policy`:

- `auto`: Tutu MCP runs first and, when available, stops fallback execution for the same logical probe.
- `tutu`, `kupibilet`, `fli`: explicit diagnostic/provider override modes.

Read provider failures, coverage diagnostics, and source boundaries from `data.evidence`. Text-mode search stdout is already the validated answer and must be returned verbatim.

Provider-aware airport priority is documented in `references/pipeline-reference.md`; use that contract for the active provider set, IST/LON/MOW airport priority, city-code post-validation, and dispatch boundaries. Do not duplicate those rules in CLI help or answer prose.

## Airport and Connection Risk

City codes and airport codes are not interchangeable evidence. Keep these boundaries explicit:

- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For city-code searches, display actual airport codes from normalized offers. A `MOW` request scope is not enough by itself: actual departure/arrival airports must validate against `SVO`/`DME`/`VKO` before an offer is accepted.

Default connection thresholds are maintained in `references/source-boundaries.md`. In short:

- protected/single-ticket international: MCT or at least 60 min, whichever is higher; label 60-89 min as tight unless airport evidence supports it;
- same airport, separate/virtual/self-transfer without checked baggage: 120 min minimum;
- same airport, separate/virtual/self-transfer with checked baggage: 180 min minimum, preferably 3-5h at high-friction airports;
- cross-airport or airport mismatch: 300 min default and label as ground-transfer risk;
- protected ticket claims require ticketing/protection proof, not just segment timing.

## Targeted Debug Probes

Use targeted probes only after the main assembled report leaves a specific uncertainty.
They are debug inputs, not alternate answer paths for agents.

Dry plan diagnostic:

```bash
python3 -m flights_cli --json diagnose plan --request /tmp/flight-search-request.json
```

Provider-port probe:

```bash
python3 -m flights_cli --json diagnose probe \
  --provider tutu \
  --request /tmp/probe.json
```

For source-boundary investigations, run `diagnose trace --request` and inspect
`data.evidence` and `data.decision`; use `diagnose probe` only for one explicit
provider probe. Keep ordinary search work on `search --request`.

Useful probe shapes:

- exact-airport direct-only;
- city-code direct-only when applicable;
- alternate airport for multi-airport cities;
- carrier-filtered direct or full-route probe;
- nearby in-horizon control date for horizon/coverage splits.

These probes are narrower evidence than the assembled report. Label the scope when using them in an answer.

## Price and Purchase Caveats

Fares and availability are advisory until checked on the purchase screen.
Through-fare, single-PNR, baggage, refund, and disruption-protection claims
require explicit booking-flow, airline, seller, or GDS proof.

## Supporting-File Distillation Policy

Do not delete supporting Markdown files merely because they contain obsolete provider names, dated route examples, or migration history. First distill any durable knowledge: workflow rules, route-family logic, airport/connection constraints, evidence boundaries, debug procedures, and maintenance invariants. Move those distilled rules into the appropriate active document or test. Delete the historical file only after the useful knowledge has been preserved elsewhere.
