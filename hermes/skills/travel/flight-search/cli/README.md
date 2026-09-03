# flights CLI

Concise manual for the flight-search skill-owned CLI. The skill's Golden Path
is `search --request`; the other commands cover setup and metadata. Paths in
this manual are relative to the skill root: the directory containing the parent
`SKILL.md`.

## What It Automates

- Route/date/IATA normalization and bounded provider execution.
- Same-airport continuity checks; cross-airport connections are rejected.
- Candidate generation, scoring, one decision frontier, and result projection.
- One broad provider query per compatible provider, narrowed to direct-only for
  a direct-only request or a date window.
- Static metadata lookup for city, airport, country/region, airline, alliance, and aircraft labels.
- A `flight_search_result.v1` of six keys: `schema_version`, `request`,
  `route`, `options`, `evidence`, `rendered_text`.

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

Runtime dependencies are `httpx2==2.9.1`, `jsonschema>=4.22,<5`, and
`mcp==2.0.0`, as declared in `pyproject.toml`. The package also uses Python
standard-library modules and local CLI package modules.

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
echo '{"origin":"SVX","destination":"LED","depart_date":"2026-10-28"}' |
  python3 -m flights_cli search --request -
```

Three fields are the whole request; `--request` also takes a file path, and
`schema_version` is filled in when omitted.

Return this text stdout verbatim. With `--json`, the whole answer is `data`,
and the paths that matter are:

- `data.rendered_text` — the canonical text, identical to text-mode stdout;
- `data.options` — one entry per buyable option, in answer order;
- `data.evidence` — `providers_searched`, `provider_failures`, `complete`.

There is no plan, decision, or trace in the envelope. Internal artifacts are
not published: a narrowed `search --request` is the diagnostic.

`search --request` searches and compares route options for the default scope of one adult in economy. It does not buy or book tickets, and final fare, baggage-through, refund/change conditions, disruption protection, and single-PNR claims require purchase-screen, airline/GDS, seller, or explicit upstream proof.

Common request fields:

- `return_date: "YYYY-MM-DD"`
- `provider_policy: "auto"` or one registry-validated provider name (currently
  `tutu` and `kupibilet`)
- `date_window_end: "YYYY-MM-DD"` for bounded one-way direct-only inventory
- `only_carriers: ["CODE"]`
- `max_connections: 0` for direct only — a hard ceiling; `preferred_connections` is the softer one
- `origin_airports` / `destination_airports` to pin exact airports
- `limit: N` for how many options to return

Execution budgets are not request fields. They are CLI flags on `search`:
`--timeout`, `--max-searches`, `--segment-limit`, `--live-cache-ttl`,
`--no-live-cache`, `--fail-fast`.

## Ranking and Stop Policy

Production search uses one ranking profile, `business`: valid options first,
then trip coverage, fewer connections, connection comfort, ticketing risk,
source confidence, elapsed time, and price. Each option's `rank_reason` names
the first component that put it below the option above it.

- A direct flight, when one exists, is the whole answer: connecting options are
  not shown beside it.
- Otherwise one-stop journeys are preferred; two-stop ones appear only when no
  one-stop option is available.
- Itineraries above `max_connections` are rejected before ranking.

What the frontier drops before the answer is described in
`references/report-contract.md`.

## Provider Policy

`search --request` chooses a live source mix through `provider_policy`:

- `auto`: every compatible provider is queried. Their offers enter one graph,
  are deduplicated by physical itinerary, and then share one ranking and one
  output limit, so no provider can hide another's cheaper itinerary.
- any registered provider name: explicit single-provider mode.

A provider that cannot serve the query — a round trip for a provider without
`supports_round_trip`, say — is left out of the plan, and `providers_searched`
in the answer shows who was actually asked. Read failures from
`data.evidence.provider_failures`. Text-mode stdout is already the validated
answer and must be returned verbatim.

Both providers receive the same normalized airport scope, and accepted offers
are checked against their actual first and last segment airports.

## Airport and Connection Boundaries

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
- cross-airport or airport mismatch: invalid and rejected before ranking, whatever the layover;
- protected ticket claims require ticketing/protection proof, not just segment timing.

## Targeted Debug Probes

Use targeted probes only after the main assembled report leaves a specific uncertainty.
They are debug inputs, not alternate answer paths for agents. Every probe is a
`search --request` run with a narrowed request; there is no separate probe command.

Useful probe shapes:

- exact-airport direct-only;
- city-code direct-only when applicable;
- alternate airport for multi-airport cities;
- carrier-filtered direct or full-route probe;
- nearby in-horizon comparison date for horizon/coverage splits.

These probes are narrower evidence than the assembled report. Label the scope when using them in an answer.

## Price and Purchase Caveats

Fares and availability are advisory until checked on the purchase screen.
Through-fare, single-PNR, baggage, refund, and disruption-protection claims
require explicit booking-flow, airline, seller, or GDS proof.

## Supporting-File Distillation Policy

Do not delete supporting Markdown files merely because they contain obsolete provider names, dated route examples, or migration history. First distill any durable knowledge: workflow rules, route-family logic, airport/connection constraints, evidence boundaries, debug procedures, and maintenance invariants. Move those distilled rules into the appropriate active document or test. Delete the historical file only after the useful knowledge has been preserved elsewhere.
