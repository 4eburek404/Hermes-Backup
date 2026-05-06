# Layover and Airport Compatibility Rules

This reference is a human-readable mirror of the current `flights` CLI airport and connection rules. It is **not** an official IATA MCT source unless a later section explicitly cites one.

## Source status

Checked against local CLI source on 2026-05-04:

- CLI source: `/home/konstantin/code/clis/flights/flights_cli/__main__.py`
- Airport groups: `MULTI_AIRPORT_GROUPS`
- Connection rule function: `connection_rule(...)`
- Default route-plan flags observed in CLI:
  - `--ticketing separate`
  - `--min-same-airport-min 120`
  - `--min-cross-airport-min 300`
- Current skill policy for Konstantin business recommendations:
  - same-airport minimum acceptable: **90 min**
  - same-airport business preferred: **120 min**
  - use `--min-same-airport-min 90` when searching/ranking to surface tight-but-acceptable frontier candidates; label 90–119 min as tight.

## Skill connection thresholds

- Same airport, separate tickets: **90 min** minimum acceptable.
- Same airport, separate tickets, business-preferred: **120 min**.
- Same-airport 90–119 min: acceptable only as a clearly labeled **tight** option, not the default business recommendation when a comparable ≥120-min option exists.
- Cross-airport or airport mismatch, separate tickets: **300 min** default.
- Same airport, single ticket: **60 min** in `connection_rule`.
- Cross-airport, single ticket: still uses `--min-cross-airport-min` because it usually implies self-managed ground transfer risk.

These are safety heuristics for planning/ranking. They do not guarantee that the airline/airport will accept the connection.

## Multi-airport systems embedded in CLI

### Istanbul

- Airports: `IST`, `SAW`
- CLI `cross_transfer_min`: **90 min**
- CLI `min_cross_connection_min`: **300 min**
- Practical rule: treat IST↔SAW as high-risk on separate tickets; border, baggage, and ground transfer can break short connections.

### Moscow

- Airports: `SVO`, `DME`, `VKO`
- CLI `cross_transfer_min`: **90 min**
- CLI `min_cross_connection_min`: **300 min**
- Practical rule: avoid Moscow cross-airport self-transfers unless the itinerary intentionally includes a long buffer.

### London

- Airports: `LHR`, `LGW`, `STN`, `LTN`
- CLI `cross_transfer_min`: **75 min**
- CLI `min_cross_connection_min`: **300 min**
- Practical rule: acceptable as separate London stay/stopover, risky as same-day self-transfer. Query LON as specific airports for Travelpayouts/fli workflows.

## Single-airport / practical hub notes

- `AYT`: one airport, but leisure/charter schedules can produce marginal self-transfer windows.
- `GYD`: usually a single-airport hub for this workflow; still verify baggage and ticket protection.
- `DXB`: single-airport assumption for this workflow; reliable but often expensive.

## How to apply

1. Verify actual airport codes per segment; provider/cached APIs can return flights from a different airport than the queried city code.
2. For assembled itineraries, require previous `arrival_airport` to equal next `departure_airport`; otherwise flag/reject.
3. For self-transfer/separate tickets, use at least 90 min same-airport and 300 min cross-airport by default; classify 90–119 min as tight/minimum-acceptable and ≥120 min as business-preferred. Increase the buffer further only when concrete route risk justifies it.
4. Treat night transfers, visa-required transfers, low-cost carriers, and leisure hubs as risk multipliers, not binary blockers.
5. Always caveat cached prices and recheck before purchase.

## Drift guard

If CLI constants in `MULTI_AIRPORT_GROUPS` or `connection_rule(...)` change, update this file in the same change. Tests should check the most important constants where practical.
