# Source Boundaries

Use this reference to explain what the live report can and cannot prove.

## Provider Results Are Advisory

Provider output is evidence, not a guarantee. Schedules, fares, baggage, ticketing rules, airport continuity, and availability can change before purchase. Treat the CLI report as a planning snapshot and carry forward its caveats.

An empty provider result is not proof that a route does not exist. It may mean the date is outside the provider horizon, the query used the wrong city/airport scope, a provider failed, a constraint was too strict, or the source has incomplete coverage.

## Horizon vs Coverage

Separate these cases in the answer:

- Horizon: the date is too far out, too near, or outside the provider's searchable window.
- Coverage: the source can search the date but does not return a useful option.
- Constraint mismatch: direct-only, carrier-only, cabin, time, baggage, or stop-policy filters removed options.
- Runtime failure: provider or sidecar errors reduced evidence quality.

When uncertainty matters, use targeted live probes for the same route/date or a nearby in-horizon control date, then state what the probe did and did not prove.

## City, Airport, and Same-Airport Boundaries

City codes and airport codes are not interchangeable evidence. Multi-airport cities can produce options that are operationally different from a named airport request.

For connections, distinguish:

- same-airport continuity;
- cross-airport transfer risk;
- airport changes hidden inside a city code;
- minimum connection time under the requested risk profile.

Do not merge options across airports unless the report or targeted probe explicitly supports that interpretation.

## Through-Fare and Purchase Verification

A combined itinerary in the report does not automatically prove a single ticket or single PNR. Use `through_fare_checks` for the current evidence level.

Before presenting a ticketing claim as firm, verify it on the purchase screen or state that the report only supports an advisory planning claim. Baggage, recheck, refund, and disruption protection depend on ticketing proof, not only segment timing.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, airline, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, airline labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

## Live Provider Policy and FLI MCP Boundary

The live provider policy chooses the current source mix for each segment. Read the policy and failures from `data.agent_report` instead of assuming a provider path.

FLI MCP is a sidecar/discovery boundary. It can expand live discovery when available, but the core CLI must still report provider failures and source limits clearly when the sidecar is unavailable or degraded.
