# Source Boundaries

Use this reference to explain what the live report can and cannot prove. Source boundaries are reasoning inputs; print only the caveats that change the traveler's decision.

## Evidence Classes

- Live provider report: current shopping/discovery evidence for the requested route/date, subject to source coverage, runtime failures, caching, and booking-screen changes.
- Targeted live control: a narrow probe for a direct flight, exact airport, city code, carrier, alternate airport, or in-horizon control date.
- Static catalog metadata: city, airport, country/region, airline, alliance, and aircraft labels used for normalization and scope.
- Structural route constraint: stable route-level or market-level facts that make a service practically unavailable in normal booking channels.
- Purchase proof: booking-screen, airline, GDS, or seller evidence for final fare, seat, baggage, single-PNR, protection, refund, and fare rules.

## Absence Taxonomy

- Provider/horizon uncertainty: the date is too far out, too near, or outside a searchable window.
- Provider coverage gap: the source can search the date but has incomplete or weak coverage for the route, airport, carrier, or market.
- Constraint mismatch: direct-only, carrier-only, cabin, timing, baggage, airport, or stop-policy filters removed otherwise viable options.
- Runtime/provider failure: provider, sidecar, network, parser, or JSON errors reduced evidence quality.
- Structural unavailability: stable route-level constraints make regular service unavailable in normal booking channels.
- Ticketing/protection uncertainty: segments may exist, but single-PNR, through-fare, baggage, recheck, or disruption protection is unproven.

Empty provider output is not proof of absence by itself. Use that internally when choosing probes and wording; do not turn it into a generic final-user caveat when a stronger route-level conclusion is available.

## Structural Route Constraints

When a market is structurally constrained, do not phrase the answer as "the provider did not prove absence." State the practical booking-channel conclusion, then show viable connecting options through third-country or available hubs.

Use current external or live evidence when available, but do not let a generic provider caveat dominate a stronger route-level conclusion. For example, if regular nonstop service is not available in normal booking channels, answer the direct question first and then discuss one-stop options, ticketing, baggage, and protection checks.

## Airport Boundaries

Use airport codes, not city labels, when continuity matters. These airports are not interchangeable:

- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For separate tickets, same-airport continuity is required by default. Cross-airport options must be rejected or explicitly labeled as ground-transfer risk.

## City Scope Rules

- Dubai: `DXB` is primary; `DWC` is secondary when relevant; include `SHJ` only when the user asks for Sharjah, a Sharjah-based carrier, cheapest UAE-wide options, or a provider returns it and it is labeled.
- Moscow: `SVO`, `DME`, and `VKO` are not interchangeable. Keep airport continuity explicit and label any ground transfer.
- London: prefer `LHR` for business travel when practical. `LGW`, `STN`, and `LTN` can be acceptable fallbacks, but label airport-quality and transfer trade-offs.

## Connection Thresholds

- Same airport, separate tickets: 90 min minimum acceptable.
- Same airport, separate tickets: 120 min business/comfort preferred.
- Same-airport 90-119 min: label tight.
- Cross-airport or airport mismatch: 300 min default.
- Protected ticket: 60 min can be acceptable only when protection is proven.

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons. Keep comfort trade-offs separate from real risk: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Through-Fare and Purchase Verification

A combined itinerary in the report does not automatically prove a single ticket or single PNR. Use `through_fare_checks` for the current evidence level.

Before presenting a ticketing claim as firm, verify it on the purchase screen or state that the report only supports an advisory planning claim. Baggage, recheck, refund, and disruption protection depend on ticketing proof, not only segment timing.

For same-carrier or requested-carrier routes, filter by marketing or operating carrier when the CLI supports it. A same-carrier route can be valid as a protected ticket, unavailable as a protected ticket, cheaper as separate segments, or more expensive as a through fare.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, country/region scope, airline labels, alliance labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

## Live Provider Policy and Sidecar Boundary

The live provider policy chooses the current source mix for each segment. Read policy, failures, coverage diagnostics, and source limits from `data.agent_report` instead of assuming a provider path.

The sidecar is a discovery boundary. It can expand live discovery when available, but the core CLI must still report provider failures and source limits clearly when the sidecar is unavailable or degraded.
