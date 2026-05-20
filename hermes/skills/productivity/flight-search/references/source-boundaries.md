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

Use exact Minimum Connection Time evidence before generic buffers when the connection is decision-critical. Practical lookup order:

1. airline/GDS/IATA MCT data when available;
2. airport-specific public MCT references such as `https://minimumconnectiontime.com/airport/IATA`;
3. the conservative generic thresholds below when exact data is unavailable or the source is uncertain.

MCT is a technical/legal floor for a sellable connection and baggage transfer, not the recommended business buffer. A connection can be legal but still unattractive because of terminal size, passport/security, baggage, low-cost/remote gates, delays, or a seller-side virtual/self-transfer construction.

Generic fallback thresholds:

- Same airport, protected/single-ticket international connection: MCT or at least 60 min, whichever is higher; label 60-89 min as tight unless airport evidence supports it.
- Same airport, separate/virtual/self-transfer without baggage: 120 min minimum acceptable.
- Same airport, separate/virtual/self-transfer with checked baggage: 180 min minimum acceptable; prefer 3-5h for low-cost or high-friction airports.
- Cross-airport or airport mismatch: 300 min default and label as ground-transfer risk.
- Same-airport 90-119 min: label tight when ticketing/protection is not proven.
- Ordinary overnight waits can be acceptable only if they support a deliberate airport-hotel pattern; label hotel/visa/landside-baggage implications.
- Very long waits (about 18h+; e.g. 23h) are not quality or reliability options by themselves. Treat them as forced stopover/fallback choices unless the user explicitly wants a stopover or every shorter option has materially worse ticketing/safety risk.

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons, but duration still changes recommendation class. Keep comfort trade-offs separate from real risk: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Through-Fare and Purchase Verification

A combined itinerary in the report does not automatically prove a single ticket or single PNR. Use `through_fare_checks` for the current evidence level.

For ticketing/protection follow-ups, distinguish evidence tiers explicitly:

- Segment-assembled route: summed separate legs by the CLI; assume separate/self-transfer unless purchase evidence says otherwise.
- Provider aggregate variant: one live seller offer when the upstream returns one `variant`/offer id, one total price, and one outbound `segments[]` item containing multiple flight ids. Treat this as a combined seller offer / likely single checkout, not merely our manual segment sum.
- Provider aggregate with `virtual_connection` / virtual-interline signal: treat as seller-side smart routing or self-connect risk until proven otherwise. Even same-carrier legs can be sold virtually by an OTA; do not infer airline responsibility from same carrier alone.
- Airline/GDS through fare or single PNR: only proven by airline/GDS/seller booking screen, fare rules, ticketing details, or explicit upstream fields. Provider aggregate shape alone does not prove one PNR, baggage-through, reissue protection, or missed-connection responsibility.

Before presenting a ticketing claim as firm, verify it on the purchase screen or state exactly which tier the report supports. Baggage, recheck, refund, and disruption protection depend on ticketing proof, not only segment timing.

For same-carrier or requested-carrier routes, filter by marketing or operating carrier when the CLI supports it. A same-carrier route can be valid as a protected ticket, unavailable as a protected ticket, cheaper as separate segments, or more expensive as a through fare.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, country/region scope, airline labels, alliance labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

## Live Provider Policy and Sidecar Boundary

The live provider policy chooses the current source mix for each segment. Read policy, failures, coverage diagnostics, and source limits from `data.agent_report` instead of assuming a provider path.

The sidecar is a discovery boundary. It can expand live discovery when available, but the core CLI must still report provider failures and source limits clearly when the sidecar is unavailable or degraded.
