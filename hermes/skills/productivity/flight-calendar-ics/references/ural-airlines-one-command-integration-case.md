# Ural Airlines one-command integration case

Use this reference when extending or repairing the `flight-calendar-ics` workflow for carrier booking sites implemented as JavaScript SPAs with private-looking but frontend-derived API headers.

## Reusable pattern

1. Start from the user's manage-booking URL or tracking redirect. Decode redirect parameters such as `u=` before parsing `pnr` / `lastName`.
2. Treat the initial HTML as a shell only. Fetch the live frontend config/assets instead of scraping visible page text.
3. Prefer the carrier's current public frontend config over local `.env` / copied `env.json` files. Local cached env files are debug artifacts, not the normal agent path.
4. Generate frontend-derived headers by executing the current frontend helper in an isolated subprocess (Node.js for Ural Airlines), rather than hard-coding obfuscated values.
5. Fetch reservation data, convert it to the standard itinerary JSON, save that JSON to a private path, then generate `.ics` from the saved JSON.
6. Write all booking artifacts containing PNR/passenger/ticket/link data with owner-only mode `0600`.
7. Parse the CLI JSON envelope and verify `ok=true`, command/process shape, segment count, UTC timestamps, no placeholders, and no private identifiers in stdout/stderr.

## Privacy contract

Do not print or store raw values in chat/log summaries for:

- PNR or locator;
- last name / passenger names;
- full manage-booking URL or tracking redirect;
- session keys or API headers;
- document/contact/ticket/fare/payment data.

The private `.ics` may include operational booking details when they are useful after import; chat summaries should use counts, routes, and non-sensitive timing only.

## TDD contract shape

When adding another carrier-SPA workflow, add tests before implementation for:

- redirect URL parsing without requiring local env files;
- refusal to depend on local `.env` / copied `env.json` in the default path;
- safe JSON envelope fields and process order;
- owner-only output permissions for both intermediate itinerary JSON and final `.ics`;
- redaction of private identifiers from stdout/stderr;
- smoke-level validation of event count, UTC timestamps, and placeholder absence.

## Completion proof

A future agent should be able to report:

- command used: `scripts/flight_calendar_ics.py --json ural --url ... --output-json ... --output-ics ...`;
- standard itinerary JSON path, mode `0600`, bytes/hash if needed;
- `.ics` path, mode `0600`, VEVENT count;
- tests or smoke checks run;
- explicit note that no local `.env` / copied `env.json` was required for the normal path.
