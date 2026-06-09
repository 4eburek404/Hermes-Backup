# Flight Calendar ICS Reference Registry

This registry is the ownership map for `flight-calendar-ics` references. Use it before adding, renaming, or expanding reference material.

## Principles

- One semantic owner per function. Neighboring files link instead of restating procedures.
- One airline, one reference file. Case notes are absorbed into the airline owner and then retired.
- CLI-deterministic behavior belongs in `scripts/`, `schemas/`, parser/help/errors, diagnostics/maint reports, and tests.
- References keep durable conceptual/operator material only.
- Keep `../SKILL.md` compact; keep troubleshooting and maintenance detail below this registry.
- Do not store concrete PNRs, passenger names, tokens, access keys, ticket numbers, contacts, document data, payment data, or full private booking URLs in references.

## Canonical owners

### Core

- `core/cli-contract.md` — stable CLI/envelope/doctor contract boundaries and verification owners.
- `core/architecture-and-data-flow.md` — conceptual layers, module ownership, agent boundary, and maintenance namespace boundary.
- `core/itinerary-and-event-format.md` — canonical itinerary role, semantic fields, validation layers, and safe calendar event text.
- `core/source-normalization.md` — PDF/email/screenshot/manual extraction into private canonical JSON.
- `core/timezone-catalog.md` — airport timezone catalog, diagnostics, and maintenance rules.
- `core/privacy-hardening.md` — sensitive data classes, redaction/bundle expectations, test pattern, and safe reporting.

### Carriers

- `carriers/aeroflot.md` — Aeroflot lookup/deep-link operator notes and Aeroflot-specific privacy.
- `carriers/redwings.md` — Red Wings/Websky direct find route, order lookup, and rejected already-opened order routes.
- `carriers/ural-airlines.md` — Ural manage-booking/tracker parsing, live frontend config, API-key helper, session/reservation flow.
- `carriers/utair.md` — Utair order-manage parsing, OAuth client-credentials flow, orders API, and response mapping.

### Maintenance

- `maintenance/operations.md` — layer boundary, read-only maint commands, source/runtime checks, cleanup rules, and TDD refactor sequence.
- `maintenance/evaluation.md` — model-evaluation, cross-model review, provider identity, shell pitfalls, and privacy-safe evidence rules.

## Absorbed legacy map

Legacy/case-note maps are intentionally summarized by owner instead of listing retired filenames that link scanners may confuse for active targets:

- CLI/process/architecture notes are absorbed by `core/cli-contract.md` and `core/architecture-and-data-flow.md`.
- Canonical itinerary and calendar event-format notes are absorbed by `core/itinerary-and-event-format.md`, schemas, renderer tests, and bundle verification.
- Manual/PDF/source extraction notes are absorbed by `core/source-normalization.md` and canonical-input tests.
- Timezone notes are absorbed by `core/timezone-catalog.md` and timezone diagnostics/tests.
- Privacy/bundle/route-dispatch rules are absorbed by `core/privacy-hardening.md`, `contracts.py`, `route_detection.py`, `bundle.py`, schema, and contract tests.
- Source/runtime, layer-boundary, cleanup, and refactor playbooks are absorbed by `maintenance/operations.md` and `maint ...` tests.
- Model-evaluation, provider, shell, and cross-model-review notes are absorbed by `maintenance/evaluation.md`.
- Carrier case notes are absorbed by their single airline owner under `carriers/`.

## Add/change rules

1. Name the behavior gap before adding material.
2. Choose an owner above; patch that file instead of creating another case note.
3. If the rule is deterministic and agent-facing, encode it in CLI `doctor`, schemas, scripts, parser/help/errors, or tests before adding prose.
4. If no owner fits, decide whether this is a new carrier, a new core responsibility, a template, a script/schema concern, or another skill's domain.
5. Adding a new airline requires exactly one owner file under `carriers/`, a CLI command or explicit manual fallback rule, tests, and registry/SKILL links.
6. After renaming/removing references, run `maint refs registry-check`, contract tests, and source/runtime parity verification when in scope.
