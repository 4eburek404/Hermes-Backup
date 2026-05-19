---
name: flight-search
version: 0.10.0
description: Use when Codex needs to find, compare, plan, or diagnose flight options with the Hermes flights CLI, including airfare checks, route assembly, hub planning, IATA/date-window searches, Kupibilet live aggregate search, FLI MCP checks, or improvements to the flight-search workflow.
---

# Flight Search

## Purpose

Flight-search answers flight-search questions from one compact CLI report. The normal path is deliberately narrow: normalize the request, run `route live-assemble --agent-brief`, read `data.agent_report`, and answer with the best viable option plus required caveats.

Static catalogs are metadata only: city, airport, airline, and aircraft data. Flight options come from live provider assembly.

## Golden Path

1. Normalize request: dates, route, IATA/city, cabin/profile constraints.
2. Run `route live-assemble --agent-brief`.
3. Read only `data.agent_report`.
4. Answer from:
   - `display`
   - `answer_lines`
   - `recommended_options`
   - `priority_options`
   - `through_fare_checks`
   - `provider_failures`
   - `source_boundaries`

Command skeleton:

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --profile balanced \
  --agent-brief
```

Use `doctor` only when environment provenance looks suspect; it is not an answer source.

## Runtime Rules

- Provider results are advisory and must be framed with the report's caveats.
- Empty provider output is not proof that a route does not exist.
- Respect `source_boundaries` and `provider_failures` from `data.agent_report`.
- Static catalogs are metadata only: city, airport, airline, and aircraft data. Flight options come from live provider assembly.
- Current live provider policy chooses the source mix. Do not hardcode provider assumptions beyond what the report states.
- Through-fare and single-PNR claims require proof from `through_fare_checks` or the purchase screen.

## Error Handling

- If the CLI fails or JSON cannot be parsed, report the concrete failure layer and rerun only safe provenance commands.
- If a provider fails, read `provider_failures` and explain the degraded evidence.
- If a route or date appears unavailable, separate horizon, coverage, city/airport mismatch, provider failure, and through-fare proof limits.
- If a requested constraint is not satisfied by the report, say which field proves that and what targeted live probe would reduce uncertainty.

## Do Not

- Do not answer from static catalogs as flight availability.
- Do not treat empty provider output as route absence.
- Do not copy route-specific stories into answers.
- Do not add historical migration narratives to active Markdown.
- Do not use alternative data paths unless the user explicitly asks for a debug probe and you label it as such.

## References

- `references/report-contract.md` — how to read `data.agent_report` into a user answer.
- `references/source-boundaries.md` — source limits and proof boundaries.
- `references/debug-playbook.md` — targeted diagnostics for current live report behavior.
- `references/cli-maintenance.md` — maintenance invariants and validation checklist.
