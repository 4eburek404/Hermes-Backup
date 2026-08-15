# Flight Search Result Contract

The public search boundary is `flight_search_result.v10`. It contains exactly:

```text
schema_version
request
route
evidence
frontier
answer
research_status
```

`flight_search_user_answer.v11` lives at `data.answer`. Its only prose field is
`rendered_text`; text-mode stdout is exactly that value plus one terminal
newline. Catalog items contain structured segments, layovers, price, baggage,
protection, risk, and caveat facts. They do not serialize display mirrors.

`frontier.option_ids` is the decision order. Catalog IDs must match it exactly;
projection and rendering cannot create, drop, or reorder options.

Provider failures, bounded coverage, source boundaries, date-window inventory,
and catalog-refresh metadata live under `evidence`. Static metadata and cache
status never prove live availability.

`flight_route_trace_diagnostic.v5` is diagnostic only. It serializes the
already-computed request, plan, evidence, decision, and answer; it does not run
providers, graph construction, scoring, or rendering a second time.
