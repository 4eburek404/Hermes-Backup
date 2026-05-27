# Round-trip ticketing evidence for carrier-specific searches

Use this when the user asks for *one ticket туда-обратно* on a specific carrier.

## Evidence hierarchy

1. Booking screen / airline-GDS fare / fare rules showing a single round-trip purchase.
2. `through_fare_checks` or explicit provider raw ticketing fields proving protected single-PNR/through-fare behavior.
3. Provider aggregate round-trip offer with one checkout price, but no protection proof yet.
4. Two separate one-way offers or CLI-summed segments.

## Common mistake

- Direct one-way offers on both directions do **not** prove that a round-trip ticket exists on that carrier.
- A `kb-search` result for one leg can confirm carrier presence on that leg, but it is not round-trip proof.

## Practical probe pattern

- Check outbound and return separately with carrier filters when the user cares about a specific airline.
- If the question is explicitly about one ticket / single PNR, require booking-screen-level evidence before saying "да".
- If only one-way offers are visible, answer that the carrier has separate one-way options and the single round-trip ticket is unproven.

## Traveler-facing wording

- Good: `U6 есть на обе стороны, но one-ticket round-trip не подтвержден.`
- Good: `single PNR/багаж не доказаны — проверить на booking screen.`
- Bad: `есть билет туда-обратно`, when only outbound/return one-way offers were observed.
