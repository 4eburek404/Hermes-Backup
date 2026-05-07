# Debug Playbook

Use this only when the compact `agent_report` is missing, contradictory, or insufficient.

## When To Debug

Debug if:
- `recommended_options` is empty but viable routes are expected;
- `priority_options` is missing for an explicitly requested carrier/hub;
- source results conflict;
- the user challenges a missed route;
- you are improving CLI behavior or writing tests.

## Safe Debug Commands

Rerun without `--agent-brief` when you need deeper JSON:

```bash
python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --return-date YYYY-MM-DD \
  --profile business \
  --agent-mode
```

Use targeted includes only when needed:

```bash
--include-ranked-candidates 10
--include-rejected-pairs 10
--include-segment-results 5
```

Avoid `--include-candidates` unless diagnosing assembly internals.

Use targeted carrier or direct controls before raw dumps:

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

## Large JSON Trap

Multi-megabyte output is possible when raw candidates are included. A 1200-candidate round trip with `--include-candidates 1200` can exceed 4 MB. That is CLI debug output, not Kupibilet's raw provider response.

Normal agent output should stay compact. If it becomes large, the workflow is wrong.

## Internal Fields

Use these only in debug:
- `ranked` — ranked summaries.
- `ranked_candidates` — full bodies for ranked summaries.
- `candidates` — raw candidate sample; do not use for recommendations.
- `segment_results` — normalized provider leg results.
- `live_search.segment_searches` — provider calls, skips, and offer counts.
- `rejected_pairs` — airport mismatch or connection rejection diagnostics.

Never recommend from `candidates` directly. Recommend from the report or from `ranked` entries with `ok=true` after matching their full candidate body.

## File Disposition

Old route-specific notes such as SVX-London, SVX-CDG, Google Flights July 2026, and historical CLI sync audits are regression history, not normal skill context. Keep their durable rules in `report-contract.md` or `source-boundaries.md`; delete the session artifacts from the runtime skill.
