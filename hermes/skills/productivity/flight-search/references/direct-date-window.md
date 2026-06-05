# Direct Date-Window Flight Inventory

Use this reference when the user asks for all direct/nonstop flights over a bounded date range, e.g. “все прямые на неделе 22.06–28.06”. This is an inventory task, not a route-recommendation task.

## Trigger

- “все прямые”, “только прямые”, “nonstop/direct only” plus a date range/window.
- User asks availability/schedule for a direct service across multiple days.
- User wants “all direct” rather than cheapest/best connected routing.

## Read-only workflow

1. Normalize origin/destination to exact airport/city scope and expand the date range into individual ISO dates.
2. Prefer the narrow direct-only live probe for each date. Use provider-policy semantics:
   - RU-touching routes: KupiBilet (`kb-search --direct-only`).
   - non-RU/global routes: FLI (`fli-search --direct-only`).
   - proposed-only interface, not active unless `flights_cli route --help` exposes it: a single `route direct-window` command that expands dates and dispatches to KupiBilet/FLI via `--provider-policy auto`.

KupiBilet example:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json kb-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 50
```

FLI example:

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$HERMES_HOME"/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json fli-search ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --direct-only \
  --limit 50
```

Use `--no-cache` when freshness matters or when validating the process.

3. If route-level `agent_report`/renderer evidence is needed, run `route live-assemble` in strict direct-only mode:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route live-assemble ORIGIN DEST \
  --depart-date YYYY-MM-DD \
  --max-connections 0 \
  --fallback-max-connections 0 \
  --agent-brief
```

Do not use ordinary `route live-assemble` output as the final answer for a direct-only inventory request; it may correctly return one-stop routes for route planning but that violates the user’s direct-only scope.

4. Summarize compactly by date:
   - dates with direct offers: flight number, carrier, local departure/arrival with `+1` when applicable, elapsed time, aircraft, price/currency if present;
   - dates with no direct live offers;
   - provider/source boundary and booking-screen checks.

5. Do **not** add airline-site, airport-site, schedule-aggregator, or external timetable checks by default. At the current stage, direct date-window inventory is a provider-live CLI scenario: use KupiBilet for RU-touching routes and FLI for non-RU/global routes. Only add external site checks if the user explicitly asks for corroboration or debugging outside the provider-live scope.

## Proposed CLI Surface, not Active Golden Path

A narrow command would be useful for this scenario, but it is not the current active path unless live CLI help exposes it:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json route direct-window ORIGIN DEST \
  --from-date YYYY-MM-DD \
  --to-date YYYY-MM-DD \
  --provider-policy auto \
  --currency RUB \
  --limit-per-date 100
```

Expected semantics:

- Expand the inclusive date window.
- Run direct-only provider probes per date.
- Dispatch providers with the existing policy: KupiBilet for RU-touching; FLI for non-RU/global; `both` only when explicitly requested/diagnostic.
- Do not plan hubs, assemble connecting routes, or call `route live-assemble`.
- Output a compact catalog: dates with direct offers, dates with no provider-live direct offers, provider failures, cache state, and rendered text.

## Pitfalls

- A date-window direct inventory is not a recommendation frontier. Do not lead with connecting routes unless the user asks for alternatives.
- Do not split the answer into schedule vs shopping/purchase layers by default. For this workflow, the operational source of truth is provider-live direct-only evidence from the CLI.
- `route live-assemble --agent-brief` alone is not direct-only. Use `--max-connections 0 --fallback-max-connections 0` or the direct-only `kb-search`/`fli-search` probe.
- Empty provider direct-only output means the selected live provider returned no direct offer for that date. State that boundary plainly; do not escalate to external schedule validation unless requested.
- Keep time zones explicit enough to avoid duration mistakes: calculate elapsed time from ISO offsets; show local airport times in the user answer.
- Raw batch JSON can be large/truncated. Reduce it to a compact per-date summary before reasoning or responding.
