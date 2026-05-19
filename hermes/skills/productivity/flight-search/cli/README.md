# flights CLI

Concise manual for the flight-search skill-owned CLI. The skill's Golden Path is `route live-assemble --agent-brief`; other commands support setup, metadata, or targeted diagnostics.

## Install

From the source checkout:

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
python3 -m pip install -e .
```

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

Static catalogs are metadata only: city, airport, airline, and aircraft data. Flight options come from live provider assembly.

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

Common options:

- `--return-date YYYY-MM-DD`
- `--profile safe|balanced|cheap`
- `--cabin-class ECONOMY|PREMIUM_ECONOMY|BUSINESS|FIRST`
- `--passengers N`
- `--provider-policy auto|kupibilet|fli|both`
- `--fli-mcp-url URL`
- `--no-cache` for a fresh live probe when appropriate

## Targeted Debug Probes

Use targeted probes only after the main assembled report leaves a specific uncertainty.

Kupibilet segment probe:

```bash
python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --limit 20
```

FLI MCP segment probe:

```bash
python3 -m flights_cli --json fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --limit 20
```

These probes are narrower evidence than the assembled report. Label the scope when using them in an answer.

## Route Assemble and Rank

The CLI still supports offline assembly/ranking for normalized segment-result JSON:

```bash
python3 -m flights_cli --json route assemble --profile balanced --input segment-results.json
python3 -m flights_cli --json route rank --profile balanced --input candidates.json
```

Use these for maintenance, fixtures, and controlled diagnostics. They are not the default answer path for live user requests.

## Provider Policy

`route live-assemble` chooses a live source mix through `--provider-policy`:

- `auto`: let the CLI choose the current source mix by segment.
- `kupibilet`, `fli`, `both`: explicit diagnostic or comparison modes.

When provider failures occur, read `provider_failures` and `source_boundaries` from `data.agent_report` before answering.

## Price and Purchase Caveats

Fares and availability are advisory until checked on the purchase screen. Through-fare, single-PNR, baggage, refund, and disruption-protection claims require explicit proof from `through_fare_checks` or the booking flow.
