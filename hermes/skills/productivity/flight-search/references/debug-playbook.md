# Debug Playbook

Use this playbook only to validate current live report behavior. Debugging should narrow uncertainty around the Golden Path, not replace it.

## When To Debug

Debug when the report is internally inconsistent, too sparse for the user's constraint, affected by provider failures, or surprising relative to geography, schedule logic, route family, or airport continuity.

Common triggers:

- recommended options conflict with `source_boundaries`;
- `provider_failures` changes the evidence quality;
- a city/airport mismatch is plausible;
- a date may be outside provider horizon;
- a risk profile may hide a physically possible option;
- an overnight connection appears when the user prefers same-day travel;
- `priority_options` is missing for an explicitly requested carrier, hub, direct flight, or airport;
- a cheapest, fastest, direct, carrier, or Moscow-control option is referenced without segment details.

## Runtime Provenance

Before declaring a provider root cause or patching behavior, prove which runtime is active:

```bash
command -v flights || true
python3 -m flights_cli --version
python3 - <<'PY'
import flights_cli, pathlib
print(pathlib.Path(flights_cli.__file__).resolve())
PY
python3 -m flights_cli route live-assemble --help
```

Record:

- repository path, branch, and HEAD when debugging source behavior;
- executable path when available;
- imported `flights_cli.__file__`;
- CLI version;
- live `--help`;
- source/runtime parity when the runtime skill tree matters;
- request normalization: dates, IATA/city, cabin, profile, passengers, filters, provider policy, and stop policy;
- whether the output came from `data.agent_report`.

Use only flags shown by the live `--help`. Temp editable checkouts under `/tmp` can shadow the permanent skill CLI; do not generalize traces until executable path, imported module path, package metadata, and source checkout are known.

Use `doctor` for environment readiness and degradation clues, not as flight evidence.

## Targeted Absence Probes

Start with the Golden Path report. If a specific uncertainty remains, run the narrowest live probe that answers it.

Main report:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile PROFILE \
  --agent-brief
```

Direct and carrier controls:

```bash
python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20

python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --only-carrier CARRIER \
  --limit 20

python3 -m flights_cli --json fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20
```

Use these probe shapes as applicable:

- exact-airport direct-only;
- city-code direct-only when the CLI/provider supports city scope and the user did not name one airport;
- alternate airport when the city has multiple airports and the user allows city-wide search;
- carrier-specific direct or aggregate control for carrier questions;
- nearby in-horizon control date to split horizon uncertainty from coverage gap.

Label probe results as narrower evidence than the assembled report. Do not use targeted probes to replace the report's final ranking unless the report is demonstrably missing a decision-critical control.

## Execution Semantics vs Live Availability

- Mocked or offline runtime execution can prove dispatch, skip, fallback, post-validation, and report-projection semantics; it is not proof of live provider availability.
- For fan-out or fallback bugs, inspect actual executed calls and skipped calls with reasons. Planned candidates alone do not prove the runtime executed or suppressed the right probes.
- When the question is provider-call suppression, fallback order, airport post-validation, or compact report projection, prefer mocked/offline execution proof over broad live provider fan-out.
- Use targeted live smoke only for provider capability, credential/config readiness, or current upstream availability. Keep live probes narrow and date-current.

## JSON Extraction

Read only the JSON payload for decisions. For command output that includes logs, extract the JSON envelope first and then inspect `data.agent_report`.

Decision fields:

- `display`;
- `answer_lines`;
- `recommended_options`;
- `priority_options`;
- `through_fare_checks`;
- `provider_failures`;
- `source_boundaries`.

If parsing fails, report the parse layer and rerun with JSON-clean stdout/stderr settings before making a travel claim.

## Internal Fields

Use internal fields to diagnose, not to overrule the report:

- `segment_searches` for per-segment evidence and provider failures;
- `coverage_diagnostics` for horizon/coverage/control completeness;
- `hub_viability` for connection feasibility;
- `rejected_pair_warnings` for airport mismatch and connection filters;
- `stop_policy` and diagnostics for constraint effects;
- `omitted_counts` for truncation awareness.

If preferred options are missing while segment evidence exists, inspect generation diagnostics. Do not compensate by increasing `candidate_pool_limit` in normal flow; fix the generation contract or reproduce with a focused synthetic case.

## Common Diagnostic Splits

### Horizon vs Coverage

If a date has no useful result, test whether the date is outside the searchable horizon before calling it a route gap. A nearby in-horizon control date can show whether the route shape is discoverable at all.

### Overnight Avoidance

If the recommended option has an overnight connection, test whether same-day options were filtered by connection windows, airport continuity, provider failures, or ranking limits. Do not assume the overnight is physically required unless targeted evidence supports it.

### Ranking Profile Bias vs Physical Possibility

A safe, business, or balanced profile can demote short, cross-airport, late-night, low-confidence, or baggage-risk options. When the user asks whether something is possible, distinguish physical possibility from operational recommendation and explain which profile or field caused the ranking.

## Debug Outcome

If the compact report clipped a decision-critical cheapest, fastest, direct, carrier, or Moscow option, fix or file against the report contract. The durable rule is: compute recommendations and controls from the full ranked list, then retain full details for selected best/cheapest/fastest/direct/carrier/Moscow-control options.

Old route-specific notes and dated audit logs are regression history, not runtime skill context. Distill durable rules into the contract, boundaries, maintenance reference, README, or tests; do not keep session artifacts in active references.
