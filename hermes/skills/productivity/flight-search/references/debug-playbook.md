# Debug Playbook

Use this only when the compact `agent_report` is missing, contradictory, or insufficient.

## When To Debug

Debug if:

- `recommended_options` is empty but viable routes are expected;
- `priority_options` is missing for an explicitly requested carrier, hub, direct flight, or airport;
- a cheaper/faster/control option is referenced without segment details;
- sources conflict;
- the user challenges a missed route;
- you are changing CLI behavior or writing tests.

## Runtime Provenance

Before declaring a provider root cause or patching behavior, prove which runtime is active:

```bash
command -v flights || true
python3 - <<'PY'
import flights_cli, pathlib
print(pathlib.Path(flights_cli.__file__).resolve())
PY
flights route live-assemble --help | sed -n '1,160p'
```

Use only flags shown by the live `--help`. `--agent-brief` is normal compact-report mode; treat undocumented flags such as `--agent-mode` as stale unless the installed CLI lists them.

Temp editable checkouts under `/tmp` can shadow the permanent skill CLI. Do not generalize traces until executable path, imported module path, package metadata, and source checkout are known.

## Safe Debug Runs

Rerun without `--agent-brief` when deeper JSON is needed:

```bash
flights --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business
```

Use targeted includes before raw dumps:

```bash
--include-ranked-candidates 10
--include-rejected-pairs 10
--include-segment-results 5
```

Avoid `--include-candidates` unless diagnosing assembly internals; it can create multi-megabyte JSON.

Use direct/carrier probes before concluding absence:

```bash
python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --only-carrier SU \
  --limit 20

python3 -m flights_cli --json fli-search IST LHR \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 20
```

## JSON Extraction

Keep stdout JSON-clean. Piping CLI output with `2>&1` into a parser is fragile because warnings or provider notices can precede JSON.

Prefer:

```bash
python3 -m flights_cli --json route live-assemble ... 2>/dev/null
```

If mixed output is unavoidable, parse from the first JSON envelope marker:

```python
import json, sys
raw = sys.stdin.read()
idx = raw.find('{"command"')
if idx == -1:
    raise ValueError("No JSON found in output")
data = json.loads(raw[idx:])
```

If this still fails, stop retrying the same pipe pattern. Capture the raw output, then read `data.agent_report` directly.

## Internal Fields

Use these only in debug:

- `ranked` - ranked summaries.
- `ranked_candidates` - full bodies for retained summaries.
- `candidates` - raw candidate sample; do not recommend from it.
- `assembly.candidate_generation_mode` and `assembly.fallback_used` - whether the pool was generated from preferred direct/one-stop journeys or fallback journeys.
- `segment_results` - normalized provider leg results.
- `live_search.segment_searches` - provider calls, skips, and offer counts.
- `rejected_pairs` - airport mismatch or connection rejection diagnostics.

If preferred options are missing while segment evidence exists, inspect `assembly.preferred_*_journey_count`, `fallback_*_journey_count`, `candidate_pool_truncated`, and `stop_policy_diagnostics`. Do not compensate by increasing `candidate_pool_limit` in normal flow; fix the generation contract or reproduce with a focused synthetic case.

FLI airport-name normalization uses the airport catalog, not naive first-three-letter codes. Generic provider names such as `Barcelona International Airport` can match multiple flightable codes; debug this as query-context disambiguation.

## Debug Outcomes

When debug finds that the compact report clipped a decision-critical option, fix or file against the report contract. The durable rule is: compute recommendations/controls from the full ranked list, then retain full details for selected best/cheapest/fastest/direct/SU/Moscow-control options.

Old route-specific notes and dated audit logs are regression history, not runtime skill context. Distill durable rules into the contract, boundaries, or maintenance reference; do not keep session artifacts in `references/`.
