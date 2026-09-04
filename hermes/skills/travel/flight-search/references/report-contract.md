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
plus one terminal newline. `request` is the canonical echo of the accepted
request, defaults included; `route` is the four fields the search actually ran
on.

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
from separate offers. The protection fields appear only where there is
something to protect. `through_baggage` and `self_transfer` are properties of a
transfer: without a connection inside a leg they are absent, not "unproven" —
nothing is carried through and there is no connection to miss. Counting flights
is not the test: an outbound and a return are two flights but not a connection.
`single_pnr` appears where there is a connection, and on an assembled route,
where the order really does come apart into several.

`rank_reason.code` says why the option sits where it does: it is read off the
ranking key by comparing the option with the one above it. The ranking key
itself never leaves the decision layer.

`warnings` are codes, not sentences. Rendering them is the reader's business.

`providers` is a list because offers from every queried provider enter one
graph and are deduplicated by physical itinerary before the shared output
limit. Two providers selling the same flights produce one option naming both,
not two options — and no provider can push another's cheaper itinerary out of
the answer.

## evidence

Three facts: `providers_searched`, `provider_failures`, `complete`. A provider
that cannot serve the query is filtered before a probe exists, so it never
appears in `providers_searched` — read that list before treating an empty
result as route absence. `date_window` rides along only for a date-window
search and gives per-date status and offer counts, not the offers themselves.

Static metadata and cache status never prove live availability.

## What the options are selected from

The answer is a decision frontier, not the provider's full output. Knowing what
was dropped keeps you from reading absence into it:

- an itinerary above `max_connections`, or with an invalid connection, is
  rejected before ranking and can never appear;
- **when a valid direct flight exists, only direct options are shown.** An
  empty-looking connecting set on such a route means "not needed", not "not
  found";
- otherwise, when anything meets `preferred_connections`, everything above it
  is dropped: a two-stop option surfaces only when no one-stop one exists;
- an option whose layover exceeds the preferred maximum survives only when no
  option stays inside it; an uncomfortable connection survives only when
  nothing through the same connection airports is comfortable;
- among what remains, an option beaten on every ranking component by another
  through the same connection airports is pruned, and only a few options per
  carrier chain are kept, so the list is varied rather than exhaustive;
- a round trip is one provider search carrying both dates and arrives as one
  atomic offer. Two one-way offers are never glued into a round trip.

Selection happens once, in the decision layer. Projection and rendering may not
call providers, rescore, or reorder.
