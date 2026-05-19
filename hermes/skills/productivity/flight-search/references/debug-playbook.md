# Debug Playbook

Use this playbook only to validate current live report behavior. Debugging should narrow uncertainty around the Golden Path, not replace it.

## When To Debug

Debug when the report is internally inconsistent, too sparse for the user's constraint, affected by provider failures, or surprising relative to geography, schedule logic, or airport continuity.

Common triggers:

- recommended options conflict with `source_boundaries`;
- `provider_failures` changes the evidence quality;
- a city/airport mismatch is plausible;
- a date may be outside provider horizon;
- a risk profile may hide a physically possible option;
- an overnight connection appears when the user prefers same-day travel.

## Provenance First

Before interpreting results, record:

- repository path, branch, and HEAD if you are debugging source behavior;
- CLI version and command line;
- request normalization: dates, IATA/city, cabin, profile, passengers, and filters;
- provider policy from the report;
- whether the output came from `data.agent_report`.

Use `doctor` only for environment readiness and degradation clues.

## Targeted Live Probes

Start with the Golden Path report. If a specific uncertainty remains, run the narrowest live probe that answers it:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile balanced \
  --agent-brief
```

Use `kb-search` or `fli-search` only as targeted probes after the main report, for example to test one segment, carrier, date, or airport interpretation. Label probe results as narrower evidence than the assembled report.

## JSON Extraction

Read only the JSON payload for decisions. For command output that includes logs, extract the JSON envelope first and then inspect `data.agent_report`.

Decision fields:

- `display`
- `answer_lines`
- `recommended_options`
- `priority_options`
- `through_fare_checks`
- `provider_failures`
- `source_boundaries`

If parsing fails, report the parse layer and rerun with JSON-clean stdout/stderr settings before making a travel claim.

## Internal Fields

Use internal fields to diagnose, not to overrule the report:

- `segment_searches` for per-segment evidence and provider failures;
- `coverage_diagnostics` for horizon/coverage splits;
- `hub_viability` for connection feasibility;
- `rejected_pair_warnings` for airport mismatch and connection filters;
- `stop_policy` and diagnostics for constraint effects;
- `omitted_counts` for truncation awareness.

## Common Diagnostic Splits

### Horizon vs Coverage

If a date has no useful result, test whether the date is outside the searchable horizon before calling it a route gap. A nearby in-horizon control date can show whether the route shape is discoverable at all.

### Overnight Avoidance

If the recommended option has an overnight connection, test whether same-day options were filtered by connection windows, airport continuity, provider failures, or ranking limits. Do not assume the overnight is physically required unless targeted evidence supports it.

### Ranking Profile Bias vs Physical Possibility

A safe or balanced profile can demote short, cross-airport, late-night, or baggage-risk options. When the user asks whether something is possible, distinguish physical possibility from operational recommendation and explain which profile or field caused the ranking.
