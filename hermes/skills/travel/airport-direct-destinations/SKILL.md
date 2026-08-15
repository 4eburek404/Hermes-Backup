---
name: airport-direct-destinations
version: 1.0.0
description: Use when listing the undated direct-route network from an airport or generating bounded airport hypotheses for flight-search.
metadata:
  hermes:
    category: travel
    tags: [flights, airport, inventory, discovery]
    requires_toolsets: [terminal]
---

# Airport Direct Destinations

Answer route-network questions such as “where can I fly direct from airport X”.
This is undated schedule evidence, not proof that a ticket is saleable on a
specific date.

## Source order

1. Prefer the official airport or airline route map. Record its URL and
   verification date.
2. Use Wikipedia’s “Airlines and destinations” table as a stale-tolerant
   cross-check, never as sole proof when official sources disagree.
3. Use FlightConnections only as an optional bulk candidate generator. Its
   data may lag, and production reuse may require a license.

All fetching, redirects, anti-bot handling, and block detection belong to
`../../research/web-content-acquisition/SKILL.md`. Do not add another HTTP
client here. Save that skill’s `article --json read` output, then parse it:

```bash
export PATH="$HOME/.local/bin:$PATH"
article --json read "https://www.flightconnections.com/flights-from-{city-slug}-{IATA}" > /tmp/airport-routes.json
PYTHONDONTWRITEBYTECODE=1 "${HERMES_SKILLS_PYTHON:-python3}" "<skill-root>/scripts/airport_inventory.py" --iata {IATA} --input /tmp/airport-routes.json --source-url "https://www.flightconnections.com/flights-from-{city-slug}-{IATA}" --json
```

Resolve `<skill-root>` as the directory containing this `SKILL.md`. If the web
acquisition output reports a block page or lacks the destination text, use its
documented fallback instead of treating the page as an empty route network.

## Flight-search integration

Use this inventory only when `flight-search` reports
`data.research_status.needed=true`. Select at most five new exact-IATA airport
chains per round and submit them as `web_route_discovery` `route_hypotheses`.
The `flight-search` CLI validates every leg; never hand-assemble or present a
route-map hypothesis as a priced itinerary.

For a dated availability claim, run the canonical `flight-search` request.
For an undated route-network answer, cite the schedule source and verification
date and keep frequency or seasonality separate from ticket availability.
