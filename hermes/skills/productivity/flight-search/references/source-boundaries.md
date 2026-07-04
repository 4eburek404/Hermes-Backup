# Source Boundaries and Ticketing Evidence

Use this reference to classify what the live report can prove. Source boundaries are reasoning inputs; print only the caveats that change the traveler's decision.

## Evidence Classes

- Live provider report: current shopping/discovery evidence for the requested route/date, subject to provider coverage, runtime failures, cache state, and booking-screen changes.
- Targeted live control: a narrow probe for a direct flight, exact airport, city code, carrier, alternate airport, round-trip checkout, or in-horizon control date.
- Static catalog metadata: city, airport, country/region, airline, alliance, and aircraft labels used for normalization and scope only.
- Structural route constraint: stable route-level or market-level facts that make a service practically unavailable in normal booking channels.
- Purchase proof: booking-screen, airline, GDS, or seller evidence for final fare, seat, baggage, single PNR, missed-connection protection, refund, exchange, and fare rules.

Empty provider output is not proof of absence by itself. Use it to choose probes and confidence language; do not turn it into a generic caveat when a stronger route-level conclusion is available.

## Absence Taxonomy

- Provider/horizon uncertainty: date is too far out, too near, or outside a searchable window.
- Provider coverage gap: the source can search the date but has weak coverage for the route, airport, carrier, or market.
- Constraint mismatch: direct-only, carrier-only, cabin, timing, baggage, airport, or stop-policy filters removed otherwise viable options.
- Runtime/provider failure: provider, network, parser, JSON, or dependency errors reduced evidence quality.
- Structural unavailability: regular service is unavailable in normal booking channels.
- Ticketing/protection uncertainty: segments may exist, but single PNR, through-fare, baggage-through, recheck, or disruption protection is unproven.

When a market is structurally constrained, do not phrase the answer as “the provider did not prove absence.” State the practical booking-channel conclusion, then show viable connecting options and purchase checks.

## Airport and City Boundaries

Use airport codes, not city labels, when continuity matters. Airports within the same city are not interchangeable for itinerary continuity; see `references/provider-aware-airport-priority.md` for the full city/airport dispatch policy and priority tiers.

For separate tickets, same-airport continuity is required by default. Cross-airport options must be rejected or explicitly labeled as ground-transfer risk.

City-scope boundary:

- Exact airport requests stay exact unless the user allows city scope.
- City-code requests must still display the actual airport codes returned by normalized offers.
- Cross-airport options require explicit ground-transfer risk labels.

Provider-specific airport priority, city-code expansion, and dispatch semantics live in `references/provider-aware-airport-priority.md`; do not duplicate those rules here.

## Connection Thresholds

Use exact Minimum Connection Time evidence before generic buffers when the connection is decision-critical. Practical lookup order:

1. airline/GDS/IATA MCT data when available;
2. airport-specific public MCT references such as `https://minimumconnectiontime.com/airport/IATA`;
3. the conservative generic thresholds below when exact data is unavailable or uncertain.

MCT is a technical/legal floor for a sellable connection and baggage transfer, not the recommended business buffer. A connection can be legal but still unattractive because of terminal size, passport/security, baggage, low-cost/remote gates, delays, or seller-side virtual/self-transfer construction.

Generic connection time thresholds:

- Same airport, protected/single-ticket international connection: MCT or at least 60 min, whichever is higher; label 60-89 min as tight unless airport evidence supports it.
- Same airport, separate/virtual/self-transfer without baggage: 120 min minimum acceptable.
- Same airport, separate/virtual/self-transfer with checked baggage: 180 min minimum acceptable; prefer 3-5h for high-friction airports.
- Cross-airport or airport mismatch: 300 min default and label as ground-transfer risk.
- Same-airport 90-119 min: label tight when ticketing/protection is not proven.
- Ordinary overnight waits can be acceptable only if they support a deliberate airport-hotel pattern; label hotel/visa/landside-baggage implications.
- Very long waits (~18h+) are forced stopover/last-resort choices unless the user explicitly wants a stopover or every shorter option has materially worse ticketing/safety risk.

`long_wait` and `overnight_wait` are visibility labels, not automatic rejection reasons. Keep comfort trade-offs separate from real risk: too-short buffers, cross-airport transfers, visa/self-transfer exposure, missing times, low-cost/leisure carrier risk, and unprotected ticketing.

## Ticketing Evidence Hierarchy

A combined itinerary in the report does not automatically prove a single ticket or single PNR. Use `through_fare_checks` for the current evidence level.

Hierarchy:

1. Booking screen / airline-GDS fare / fare rules showing one protected purchase.
2. Explicit provider raw ticketing fields proving single-PNR/through-fare behavior.
3. Provider aggregate offer with one checkout price and one offer/variant id, but no protection proof yet.
4. Provider aggregate with virtual/smart-route signal: seller-side construction; protection depends on stated terms.
5. Two separate one-way offers or CLI-summed segments.

Before presenting a ticketing claim as firm, verify it on the purchase screen or state exactly which tier the report supports. Baggage, recheck, refund, and disruption protection depend on ticketing proof, not only segment timing.

Carrier-specific round trips need extra care:

- Direct one-way offers in both directions do **not** prove a round-trip ticket exists on that carrier.
- If the user asks for one ticket / single PNR, require booking-screen-level proof before saying “да”.
- If only one-way offers are visible, answer that the carrier has separate options and the protected round trip is unproven.

Useful wording:

- `U6 есть на обе стороны, но one-ticket round-trip не подтверждён.`
- `single PNR/багаж не доказаны — проверить на booking screen.`

## KupiBilet Operational Semantics

KupiBilet is useful as OTA discovery, price/checkout evidence, and smart-route discovery. It is not final airline/GDS proof by itself.

### API vs website mismatch

KupiBilet API evidence and KupiBilet website evidence can diverge on schedule times or whole offers. Treat this as a provider/source-boundary issue until proven otherwise, not as an immediate parser bug.

When the user reports a website-visible flight that the CLI did not find or time-shifted:
1. Reproduce with the narrow KupiBilet diagnostic or raw API check from `references/debug-playbook.md`.
2. If the API returns the same value the CLI normalized, report provider-side data drift or provider coverage gap.
3. If website evidence is more current for planning, use it as user-observed evidence and label the discrepancy.

For non-RU or foreign-carrier routes, KupiBilet API gaps are a known source limitation. Empty KupiBilet output alone does not prove absence; prefer the assembled `agent_report`, Tutu-first provider evidence, and targeted provider comparisons before making a negative route claim.

### Live provider alternatives

The CLI has three provider adapters: `tutu`, `kupibilet`, and `fli`.
- **Tutu MCP** is the default primary live source in `auto`. If a Tutu probe is searched successfully, fallback providers are not called for that logical probe.
- **KupiBilet** is a fallback source when Tutu is unavailable, fails, or does not support the probe; its API can have foreign-carrier coverage gaps.
- **FLI (Google Flights)** requires a self-hosted MCP server at `http://127.0.0.1:8000/mcp` and is fallback-only for non-RU probes when Tutu is unavailable, fails, or does not support the probe.
- For routes where all configured provider evidence is insufficient, the fallback is browser-based search on aggregators or asking the user to check a specific seller/airline surface directly.

### Terminal data availability

The raw KupiBilet API can return `arrival_terminal` and `departure_terminal` per flight. The CLI normalizes these into `segments[].departure_terminal` / `segments[].arrival_terminal`. When evaluating connection feasibility at major hubs, check terminal fields and do not assume same-terminal transfers.

Distinguish:

- one KupiBilet order/checkout;
- airline-responsible single PNR / through-fare;
- baggage-through;
- missed-connection responsibility;
- refund/exchange rules per ticket or per order.

Smart routes can be cheaper but may require new check-in, baggage reclaim/recheck, passport/visa formalities, and independent fare rules. Present smart routes as risk-bearing, not as protected connections, unless purchase-screen terms prove the protection.

Decision-critical public help-page facts must be treated as current-source evidence, not durable guarantees. The currently verified smart-route help page says smart routes are split tickets in one KupiBilet order; if a flight is cancelled or delayed due to the airline and the passenger contacts KupiBilet instead of self-buying/exchanging elsewhere, KupiBilet may cover the missed part of the route. It also says passengers may need to re-check in, reclaim/recheck baggage, hold transit documents/visas, and accept separate refund/exchange conditions per ticket.

Do not quote exact delay thresholds, refund percentages, deadlines, add-on terms, or payout rules from memory. Verify current checkout/help-page wording before presenting those as firm.

For business travel, use KupiBilet to discover candidates and price signals, then verify booking-screen/GDS/airline evidence for PNR, baggage, protection, terminals, and fare rules.

## Static Catalog Metadata

Static catalogs are metadata only: city, airport, country/region, airline, alliance, and aircraft data. Flight options come from live provider assembly.

Use catalog fields to normalize names, codes, airport geography, country/region scope, airline labels, alliance labels, and aircraft labels. Do not use catalog presence as schedule or availability evidence.

Catalog-dependent CLI commands refresh missing or older-than-2-weeks static metadata before planning unless disabled. This is runtime readiness, not live availability evidence.

## Live Provider Policy

The live provider policy chooses the current source mix for each segment. Read policy, failures, coverage diagnostics, and source limits from `data.agent_report` instead of assuming a provider path.
