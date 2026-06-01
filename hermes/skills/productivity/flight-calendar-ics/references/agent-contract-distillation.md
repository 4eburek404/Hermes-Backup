# Agent contract distillation notes

Use this reference when maintaining `flight-calendar-ics` for small/free models.

## Durable rule

Keep `SKILL.md` as a short command-selection contract. It should tell the agent which command to run, what artifact to check, and what to send back. It should not make the agent reason through carrier/API details.

## Preferred shape

1. Identify the carrier/source from the user input.
2. Run the corresponding single CLI command:
   - Aeroflot → `python scripts/flight_calendar_ics.py --json aeroflot ...`
   - Ural Airlines → `python scripts/flight_calendar_ics.py --json ural ...`
   - Utair → `python scripts/flight_calendar_ics.py --json utair ...`
   - Red Wings → `python scripts/flight_calendar_ics.py --json redwings ...` for direct `#/find/<PNR>/<ACCESS_KEY>/Submit` links; carriers without a live subcommand → normalize to canonical itinerary JSON, then `make`
   - Unknown/manual JSON → `python scripts/flight_calendar_ics.py --json make ...`
3. Parse the JSON envelope; require `ok=true` and expected artifact paths.
4. Verify private artifacts exist and are mode `0600`.
5. Send the `.ics` file to chat; summarize only redacted operational facts.

## What belongs in references

Move provider-specific detail out of `SKILL.md` into `references/`:

- API endpoints and GraphQL/query shapes.
- URL quirks, tracker redirects, and rejected URL classes.
- Mapping notes from provider payloads to itinerary v1.
- Privacy pitfalls and examples with placeholders.
- Historical comparison notes proving that compacting `SKILL.md` was distillation rather than knowledge loss.

## Anti-patterns

- Do not paste raw itinerary JSON into command examples; use `<PATH_TO_ITINERARY_JSON>`.
- Do not ask the model to infer access secrets from PNR/order ids/passenger surnames.
- Do not keep long provider workflows in `SKILL.md`; they overload small models.
- Do not report PNRs, access keys, passenger names, ticket numbers, contacts, or full manage-booking URLs in chat/log summaries.
