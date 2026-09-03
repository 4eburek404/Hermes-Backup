# Flight Search Result Contract

The public search boundary is `flight_search_result.v1`. It contains exactly:

```text
schema_version
request
route
options
evidence
rendered_text
```

`rendered_text` is the only prose field, and it sits beside the options rather
than inside a separate answer envelope. Text-mode stdout is exactly that value
plus one terminal newline.

## options

Each option is one thing a traveler can buy: `number`, `id`, `providers`,
`price`, `journey_scope`, `ticketing`, `directions`, `rank_reason`, `warnings`.
One fact lives in one field. There are no display mirrors, no badge list beside
the warning list, and no prose caveats beside the codes.

`directions.outbound` is always present; `directions.return` is a leg for a
round-trip request and `null` otherwise. A leg carries `segments`,
`duration_min`, and — only when it has more than one flight — `connections`.
Each connection is described once: airport, minutes, comfort, and the required
minimum where the policy knows it.

`ticketing.model` says whether this is one provider order or a route assembled
from separate offers. The three protection fields — `single_pnr`,
`through_baggage`, `self_transfer` — appear **only when the option has more
than one flight**. A single direct flight has nothing to come apart, so it
states no protection at all rather than reporting it unproven.

`rank_reason.code` says why the option sits where it does: it is read off the
ranking key by comparing the option with the one above it. The ranking key
itself never leaves the decision layer.

`warnings` are codes, not sentences. Rendering them is the reader's business.

## evidence

Three facts: `providers_searched`, `provider_failures`, `complete`. A provider
that cannot serve the query is filtered before a probe exists, so it never
appears in `providers_searched` — read that list before treating an empty
result as route absence. `date_window` rides along only for a date-window
search and gives per-date status and offer counts, not the offers themselves.

Static metadata and cache status never prove live availability.
