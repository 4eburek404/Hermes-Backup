# Flight Calendar ICS skill architecture notes

Use this reference when maintaining or refactoring the skill itself, not during ordinary one-off `.ics` generation.

## Current disclosure shape

`SKILL.md` is the small-model operating contract, not the carrier playbook. Keep it progressive-disclosure oriented and short enough that loading the skill does not crowd out the user's ticket data:

- `SKILL.md`: trigger conditions, explicit agent contract, carrier/source command matrix, privacy rules, failure rules, and verification checklist. It should let an agent classify the source, run one command, parse the envelope, verify, and send the file.
- `references/agent-cli-contract.md`: full CLI JSON envelope contract, process traces, expected fields, command behavior.
- Carrier references: API/SPA details, redirect parsing, live frontend discovery, response mapping, TDD case notes, and maintenance/debug detail for each airline.
- `schemas/`: formal machine-readable contracts used by the CLI/tests.
- `templates/`: copyable examples only, with fictional data.

If a future update adds long carrier-specific troubleshooting, API field maps, route/date/airport examples, provider-specific notes, or case-study history to `SKILL.md`, move that detail to `references/` and leave only a short command pointer in the main file.

## Schema model

There are two distinct contracts that should not be conflated:

1. **CLI envelope schema** — `schemas/cli-envelope.v1.schema.json` describes the JSON response envelope emitted by `scripts/flight_calendar_ics.py --json`. It is reused across `doctor`, `validate`, `make`, `aeroflot`, `ural`, and `utair` commands.
2. **Unified itinerary input model** — the practical data model consumed by `make_flight_ics.py` and produced by carrier converters: top-level trip metadata plus `flights[]` segments with departure/arrival local times, airports, timezones, and optional booking details.

The unified itinerary model is formalized in `schemas/itinerary.v1.schema.json` and enforced by `scripts/itinerary_contract.py`. Manual `make/validate` inputs and carrier-converter outputs should validate against that schema, then pass semantic validation before ICS generation.

## Maintenance rule of thumb

Carrier-specific converters should normalize airline data into the shared itinerary model first. The ICS generator should remain carrier-agnostic. Tests should assert both layers:

- carrier/API fixture -> unified itinerary JSON;
- unified itinerary JSON -> valid `.ics` with one event per segment;
- every command emits the shared CLI envelope without leaking private identifiers in stdout/stderr.
