# Source Boundaries

Use this reference before explaining why sources disagree or why a result needs purchase-screen verification.

## Source Rules

- Kupibilet live aggregate is live shopping data, not the airline or a GDS.
- Segment assembly prices compatible direct legs and assumes separate/self-transfer unless protection is proven.
- FLI MCP is useful for non-Russian/global segments; it is a self-hosted wrapper, not an official Google Flights public API.
- FLI/Google-style checks are weak or empty for routes departing Russia; use Kupibilet/Travelpayouts/U6 sources for Russia-origin legs.
- FLI expects specific airports for multi-airport cities such as London; use `LHR`, `LGW`, `STN`, or `LTN`, not `LON`.
- Travelpayouts/Aviasales cached data is a late sanity layer only.
- Cached absence or `0 results` is never proof that a route, direct flight, round trip, or through fare does not exist.
- One-way cached or live probes can reveal options that round-trip queries miss. Treat round-trip emptiness as a source/query limitation.
- U6 calendar `price: null` means no sale signal for that date, not proof that the flight or seasonal route does not exist.

## Through-Fare Boundary

The CLI can assemble `SVX->SVO + SVO->DEL`, but it does not construct Aeroflot/GDS fare rules or guarantee one PNR. A same-carrier multi-leg route can be:
- cheaper as a through fare than the sum of segments;
- more expensive as a through fare;
- protected with baggage through-check;
- unavailable as a protected ticket even if segments exist separately.

When `through_fare_checks` is present, tell the user what to verify rather than pretending the CLI can settle it.

For Aeroflot:
- filter by marketing or operating carrier `SU`;
- SU-marketed Rossiya/FV-operated flights can be valid Aeroflot-sold options;
- do not reintroduce legacy cached `su-flights` behavior.

## Airport Boundary

Use actual airport codes, not city labels.

Hard examples:
- `IST != SAW`
- `SVO != DME != VKO`
- `DXB != DWC != SHJ`
- `LHR != LGW != STN != LTN`

For separate tickets, same-airport continuity is required by default. Cross-airport options must be rejected or explicitly marked as ground-transfer risk.

Connection thresholds for business routing:
- same airport, separate tickets: 90 min minimum acceptable;
- same airport, separate tickets: 120 min business-preferred;
- same-airport 90-119 min: label tight;
- cross-airport or airport mismatch: 300 min default;
- same airport, single protected ticket: 60 min can be acceptable only when protection is proven.

London policy:
- Prefer `LHR` for business when practical.
- `LGW`, `STN`, and `LTN` can be acceptable fallbacks, but label the trade-off.
- London airport changes across a stay are different from same-day self-transfer risk.

## Price Boundary

Every price is advisory until the booking screen confirms:
- final fare;
- availability;
- baggage;
- ticket protection/single PNR;
- fare rules and refund/change conditions.
