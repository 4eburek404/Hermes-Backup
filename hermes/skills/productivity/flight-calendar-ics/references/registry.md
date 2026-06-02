# Flight Calendar ICS Reference Registry

This registry is the ownership map for `flight-calendar-ics` references. Use it before adding, renaming, or expanding reference material.

## Principles

- One semantic owner per function. Neighboring files link to each other instead of restating procedures.
- One airline, one reference file. Case notes are absorbed into the airline owner and then retired.
- CLI-deterministic behavior belongs in `scripts/`, `schemas/`, and tests; references explain contracts, boundaries, and maintenance.
- Historical cases are not architecture. Extract the rule, verification proof, and anti-path into the owner file.
- Keep active generation flow in `../SKILL.md` compact; keep maintenance/debug detail here.
- Do not store concrete PNRs, passenger names, tokens, access keys, ticket numbers, contacts, document data, or full personal booking URLs in references.

## Canonical owners

### Core

- `core/cli-contract.md` — single CLI entrypoint, `doctor.data.agent_contract`, JSON envelope, process traces, and CLI contract tests.
- `core/architecture-and-data-flow.md` — system layers, module ownership, boundaries, and high-level data movement.
- `core/canonical-itinerary.md` — provider-agnostic itinerary JSON, schema vs semantic validation, and adapter boundary.
- `core/calendar-event-format.md` — user-facing `.ics` event text: `SUMMARY`, `LOCATION`, `DESCRIPTION`, alarms, and renderer tests.
- `core/manual-source-extraction.md` — PDF/email/screenshot/manual extraction into canonical itinerary JSON.
- `core/timezone-catalog.md` — bundled Travelpayouts airport timezone asset, overrides, diagnostics, and regression rules.
- `core/privacy-hardening.md` — redaction, private artifact permissions, JSON-mode failures, helper compatibility, and hardening review checks.

### Carriers

- `carriers/aeroflot.md` — Aeroflot PNR/name lookup, `pnr_key` direct deep-link generation, and Aeroflot-specific privacy.
- `carriers/redwings.md` — Red Wings/Websky direct find route, GraphQL order lookup, and rejected already-opened order routes.
- `carriers/ural-airlines.md` — Ural manage-booking/tracker parsing, live frontend config, API-key helper, session/reservation flow.
- `carriers/utair.md` — Utair order-manage parsing, OAuth client-credentials token, orders API, and response mapping.

### Maintenance

- `maintenance/source-runtime-sync.md` — source ↔ runtime parity, deliberate sync, cleanup, and commit evidence for this skill.

## Absorbed legacy map

- `agent-cli-contract.md` → `core/cli-contract.md`.
- `process-and-data-flow.md` → `core/architecture-and-data-flow.md`, `core/cli-contract.md`, `core/canonical-itinerary.md`, `core/privacy-hardening.md`, `core/timezone-catalog.md`, and `core/calendar-event-format.md`.
- `agent-contract-distillation.md` → `core/architecture-and-data-flow.md` and `core/cli-contract.md`.
- `skill-architecture-notes.md` → `core/architecture-and-data-flow.md`.
- `canonical-itinerary-contract.md` + `canonical-itinerary-schema.md` → `core/canonical-itinerary.md`.
- `event-content-format.md` → `core/calendar-event-format.md`.
- `pdf-attachment-layout-extraction.md` → `core/manual-source-extraction.md`.
- `travelpayouts-airport-timezones.md` → `core/timezone-catalog.md`.
- `hardening-review-checks.md` → `core/privacy-hardening.md`.
- `source-runtime-sync.md` → `maintenance/source-runtime-sync.md`.
- `aeroflot-pnr-surname-deeplink.md` → `carriers/aeroflot.md`.
- `redwings-manage-booking.md` + `redwings-order-route-vs-email-link-case.md` → `carriers/redwings.md`.
- `ural-airlines-manage-booking.md` + `ural-airlines-live-frontend-flow.md` + `ural-airlines-one-command-integration-case.md` → `carriers/ural-airlines.md`.
- `utair-manage-booking.md` + `utair-one-command-integration-case.md` → `carriers/utair.md`.

## Add/change rules

1. Name the behavior gap before adding material.
2. Choose an owner above; patch that file instead of creating another case note.
3. If the rule is deterministic and agent-facing, encode it in CLI `doctor`, schemas, scripts, or tests before adding prose.
4. If no owner fits, decide whether this is a new carrier, a new core responsibility, a template, a script/schema concern, or another skill's domain.
5. Adding a new airline requires exactly one owner file under `carriers/`, a CLI command or explicit manual fallback rule, tests, and `../SKILL.md`/registry links.
6. After renaming/removing references, run a link scan, contract tests, and source/runtime parity verification.
