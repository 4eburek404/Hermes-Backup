# Architecture and Data Flow

This file owns the durable architecture of `flight-calendar-ics`: data layers, module boundaries, and responsibility split. It does not own CLI JSON details, carrier API details, event wording, timezone catalog maintenance, or source/runtime sync.

## Scope

The skill converts flight booking evidence into an importable `.ics` file. It does not search flights, compare fares, or book tickets.

Primary invariant: one normalized `flights[]` segment becomes one `VEVENT`; local ticket times are converted to UTC `DTSTART`/`DTEND`; private booking identifiers stay out of stdout/chat and are allowed only in private artifacts when needed for the deliverable.

## High-level flow

```text
source evidence
  -> source classification
  -> one CLI command with --json
  -> source parsing / input loading
  -> optional carrier fetch
  -> canonical itinerary JSON
  -> schema validation
  -> semantic validation
  -> ICS build
  -> ICS validation
  -> private artifact write
  -> redacted CLI envelope
  -> agent verification
  -> Telegram delivery
```

## Data layers

1. **Source evidence layer**
   - Examples: carrier manage-booking URL, ticket PDF, email text, screenshot, pasted segment list, or existing canonical itinerary JSON.
   - May contain private values: PNR, access keys, passenger names, ticket numbers, full booking URLs.
   - Owner: agent for classification; carrier adapter or manual normalization for extraction.

2. **Carrier/raw source layer**
   - Examples: Aeroflot PNR API response, Ural reservation response, Utair order response, Red Wings/Websky order response.
   - Provider-specific and potentially private.
   - Owner: carrier helper module and carrier reference.
   - Boundary: raw fields must not leak into the shared canonical contract except through intentionally mapped common fields or `extensions` when unavoidable and non-sensitive.

3. **Timezone support layer**
   - Input: airport IATA codes from carrier/raw data or manual JSON.
   - Main source: `assets/travelpayouts/airport_timezones.json`.
   - Override: repeated `--tz CODE=Area/City`; overrides win over the bundled asset.
   - Diagnostic: carrier commands expose `process[].step=load_timezone_map` with catalog/override counts.

4. **Canonical itinerary layer**
   - Schema: `schemas/itinerary.v1.schema.json`.
   - Runtime validation: `scripts/itinerary_contract.py`.
   - Meaning: one `flights[]` item is one flight segment and one generated calendar event.

5. **Calendar layer**
   - Builder: `scripts/make_flight_ics.py`.
   - Output: RFC 5545 `.ics` text with `BEGIN:VCALENDAR` and one `BEGIN:VEVENT` per segment.
   - Time handling: parse local departure/arrival datetimes with IANA timezones, then emit UTC `DTSTART`/`DTEND` ending in `Z`.
   - Event content owner: `core/calendar-event-format.md`.

6. **Artifact layer**
   - Carrier commands write normalized private `itinerary.json` and optionally private `flights.ics`.
   - `make` writes private `flights.ics` from canonical JSON.
   - `validate` writes nothing.
   - Private artifacts must be mode `0600`; output directories are created before write.

7. **CLI envelope layer**
   - Schema: `schemas/cli-envelope.v1.schema.json`.
   - Emitter: `scripts/flight_calendar_ics.py --json`.
   - Contains: `schema_version`, `ok`, `command`, ordered `process[]`, and either safe `data` or redacted `error`.
   - Does not contain: PNR keys, access keys, passenger names, ticket numbers, bearer tokens, full manage-booking URLs.

8. **Agent delivery layer**
   - Agent saves stdout as `envelope.json`, parses it, verifies required fields and artifacts, then sends `MEDIA:/absolute/path/flights.ics`.
   - Chat summary stays operational and redacted: segment count, route/timing summary, and import instructions only.

## Module ownership

- `../../SKILL.md` — compact operating contract: triggers, one-command normal path, privacy boundary, failure gates, and verification checklist.
- `scripts/flight_calendar_ics.py` — single agent-facing CLI orchestrator and JSON-envelope owner.
- `scripts/aeroflot_pnr_to_itinerary.py` — Aeroflot source parser, fetcher, and adapter.
- `scripts/ural_airlines_to_itinerary.py` — Ural source parser, frontend/runtime API handling, fetcher, and adapter.
- `scripts/utair_to_itinerary.py` — Utair source parser, token/order fetcher, and adapter.
- `scripts/redwings_to_itinerary.py` — Red Wings/Websky source parser, order fetcher, and adapter.
- `scripts/itinerary_contract.py` — canonical itinerary normalization, JSON Schema validation, and semantic validation.
- `scripts/make_flight_ics.py` — carrier-agnostic calendar builder and ICS validator; also retained as a compatibility helper.
- `scripts/travelpayouts_airport_catalog.py` — builder/inspector/loader for bundled airport timezone asset.
- `schemas/cli-envelope.v1.schema.json` — machine-readable contract for the CLI envelope.
- `schemas/itinerary.v1.schema.json` — machine-readable contract for normalized itinerary input.
- `templates/` — fictional, reusable examples only.
- `assets/travelpayouts/airport_timezones.json` — bundled provider-neutral IATA → IANA timezone map.
- `references/` — progressive-disclosure maintenance and carrier-specific details, organized by `registry.md`.
- `tests/test_flight_calendar_ics_cli.py` — contract tests for CLI, schemas, permissions, redaction, adapters, and compatibility helpers.

## Agent responsibility boundary

A future agent should only:

1. Load the skill and set `SKILL_DIR` plus a private temporary `OUT_DIR`.
2. Classify the source from explicit evidence.
3. Pick exactly one command path from `doctor.data.agent_contract`.
4. Run `python "$SKILL_DIR/scripts/flight_calendar_ics.py" --json <command> ...`.
5. Save stdout as `envelope.json`.
6. Parse and verify the envelope.
7. Verify `.ics` existence, permissions, event count, UTC timestamps, and absence of placeholders.
8. Deliver only the `.ics` file and a safe summary.
9. If source evidence is insufficient, ask for the missing source rather than trying random fallback carriers.

The agent should not directly reason through airline APIs, scrape static HTML, scrape helper stdout, infer access secrets, or leak private booking values in chat.

## Maintenance boundaries

Keep these boundaries stable during refactors:

1. Classifier/contract surface stays in `../../SKILL.md` and `doctor`; it should remain compact.
2. Provider acquisition stays in carrier adapter modules and carrier references.
3. Provider-to-canonical mapping stays in adapters and must output itinerary v1.
4. Canonical validation stays in `itinerary_contract.py` and schema files.
5. Calendar generation stays in `make_flight_ics.py` and remains carrier-agnostic.
6. Envelope/redaction/security stays in the single CLI and contract tests.
7. Operational maintenance knowledge stays in references, not in the normal user-facing path.

This separation is the guardrail against making the agent reason about carrier APIs or handle private booking data outside the CLI/artifact boundary.
