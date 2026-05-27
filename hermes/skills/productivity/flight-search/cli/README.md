# flights CLI

Concise manual for the flight-search skill-owned CLI. The skill's Golden Path is `route live-assemble --agent-brief`; other commands support setup, metadata, or targeted diagnostics.

## What It Automates

- Route/date/IATA normalization and bounded live assembly.
- Airport compatibility checks for same-airport and cross-airport connections.
- Candidate generation, stop-policy filtering, ranking, and compact report projection.
- Direct, carrier, aggregate, and sidecar controls when the current provider policy calls for them.
- Static metadata lookup for city, airport, country/region, airline, alliance, and aircraft labels.
- A compact `data.agent_report` for agents, including display lines, recommended options, priority controls, provider failures, through-fare checks, and source boundaries.

The CLI does not book, buy, or write to Hermes runtime state.

## Install

Normal one-off runs do not need installation. If you are explicitly setting up the runtime CLI entry point, install from the active runtime skill CLI and then check/report generated artifacts (`*.egg-info`, caches):

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
python3 -m pip install -e .
```

For source-development checkouts, use the source root documented in `references/cli-maintenance.md`, then prove source/runtime provenance before claiming runtime behavior.

For one-off local runs without installation, execute from the same directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
```

## Dependencies

Runtime dependency: `jsonschema>=4.22,<5` as declared in `pyproject.toml`. The package also uses Python standard-library modules and local CLI package modules.

## JSON Envelope

Use `--json` for agent work. Successful commands return a JSON envelope with command metadata and `data`. Errors return a JSON envelope with `ok: false` and structured error detail.

Stdout must stay JSON-clean in `--json` mode. Human diagnostics and provider logs belong on stderr or structured fields.

## Doctor

Use doctor for environment readiness and degradation clues:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
```

Doctor output is not a flight answer. Treat `ok: false` as an environment/readiness signal and inspect the structured issues.

## Static Catalog Metadata Commands

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Useful metadata commands:

```bash
python3 -m flights_cli --json catalog manifest
python3 -m flights_cli --json catalog update --dry-run
python3 -m flights_cli --json cities search Yekaterinburg
python3 -m flights_cli --json airports explain SVX MOW
```

Use these commands for normalization and airport/city boundaries, not for availability claims.

## Golden Path: route live-assemble --agent-brief

Primary agent command:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile balanced \
  --agent-brief
```

Read only `data.agent_report` for the user answer. Use:

- `display`
- `answer_lines`
- `recommended_options`
- `priority_options`
- `through_fare_checks`
- `provider_failures`
- `source_boundaries`

`route live-assemble` searches and compares route options for the default scope of one adult in economy. It does not buy or book tickets, and final fare, baggage-through, refund/change conditions, disruption protection, and single-PNR claims require purchase-screen, airline/GDS, seller, or explicit upstream proof.

Common options:

- `--return-date YYYY-MM-DD`
- `--profile balanced|business|cheap|safe`
- `--provider-policy auto|kupibilet|fli|both`
- `--stop-policy business-default|strict-direct-one-stop|allow-two-stop-fallback|debug-all`
- `--aggregate-control-carrier CODE`
- `--coverage-mode standard|targeted|full`
- `--no-live-cache` for a fresh live probe when appropriate

## Risk Profiles

Profiles change ranking, not hard safety/proof rules.

| Profile | Use when |
|---|---|
| `business` | comfort, predictable same-airport travel, shorter elapsed time, and work-travel reliability matter |
| `safe` | connection quality and operational safety matter more than price |
| `balanced` | neutral trade-off between risk, price, and elapsed time |
| `cheap` | the user explicitly asks for cheapest or price-first options |

Unsafe transfers can still be rejected under any profile.

## Stop Policy and Reportability

- Direct and one-stop journeys are preferred.
- Two-stop journeys are fallback/reportable only when no viable direct/one-stop option exists or the report explicitly marks fallback/reportability.
- Three-or-more-connection itineraries are suppressed from normal recommendations.
- `candidate_pool_limit` is a safety/debug cap, not an answer-quality workaround.

## Provider Policy

`route live-assemble` chooses a live source mix through `--provider-policy`:

- `auto`: let the CLI choose the current source mix by segment.
- `kupibilet`, `fli`, `both`: explicit diagnostic or comparison modes.

Read provider policy, provider failures, coverage diagnostics, and source boundaries from `data.agent_report` before answering. Do not hardcode source assumptions outside what the report states.

Provider-aware airport priority is documented in `references/provider-aware-airport-priority.md`; use that contract for the active provider set, IST/LON/MOW airport priority, city-code post-validation, and dispatch boundaries. Do not duplicate those rules in CLI help or answer prose.

## Airport and Connection Risk

City codes and airport codes are not interchangeable evidence. Keep these boundaries explicit:

- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For city-code searches, display actual airport codes from normalized offers. A `MOW` request scope is not enough by itself: actual departure/arrival airports must validate against `SVO`/`DME`/`VKO` before an offer is accepted.

Default connection thresholds:

- same airport, separate tickets: 90 min minimum acceptable;
- same airport, separate tickets: 120 min business/comfort preferred;
- same-airport 90-119 min: label tight;
- cross-airport or airport mismatch: 300 min default;
- protected ticket: 60 min can be acceptable only when protection is proven.

## Targeted Debug Probes

Use targeted probes only after the main assembled report leaves a specific uncertainty.

Direct or carrier probe:

```bash
python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20

python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --only-carrier CODE \
  --limit 20

python3 -m flights_cli --json kb-roundtrip ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --only-carrier CODE \
  --direct-only \
  --limit 20
```

Sidecar segment probe:

```bash
python3 -m flights_cli --json fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20
```

Useful probe shapes:

- exact-airport direct-only;
- city-code direct-only when applicable;
- alternate airport for multi-airport cities;
- carrier-specific direct or aggregate control;
- nearby in-horizon control date for horizon/coverage splits.

These probes are narrower evidence than the assembled report. Label the scope when using them in an answer.

## Route Assemble and Rank

The CLI supports offline assembly/ranking for normalized segment-result JSON:

```bash
python3 -m flights_cli --json route assemble --profile balanced --input segment-results.json
python3 -m flights_cli --json route rank --profile balanced --input candidates.json
```

Use these for maintenance, fixtures, and controlled diagnostics. They are not the default answer path for live user requests.

## Price and Purchase Caveats

Fares and availability are advisory until checked on the purchase screen. Through-fare, single-PNR, baggage, refund, and disruption-protection claims require explicit proof from `through_fare_checks` or the booking flow.

## Supporting-File Distillation Policy

Do not delete supporting Markdown files merely because they contain obsolete provider names, dated route examples, or migration history. First distill any durable knowledge: workflow rules, route-family logic, airport/connection constraints, evidence boundaries, debug procedures, and maintenance invariants. Move those distilled rules into the appropriate active document or test. Delete the historical file only after the useful knowledge has been preserved elsewhere.
