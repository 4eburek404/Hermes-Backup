# Reference Registry

Ownership map for `flight-calendar-ics` references. Rules for adding or changing references live in `maintenance/operations.md`.

## Canonical owners

### Core
- `core/itinerary.md` — canonical itinerary JSON: role, required fields, normalization from PDFs/emails/screenshots/manual sources.
- `core/privacy-hardening.md` — sensitive data classes, redaction expectations, and safe reporting (single owner of the class list).
- `core/timezone-catalog.md` — airport timezone catalog, diagnostics, and maintenance rules.

### Architecture
- Layers, module ownership, CLI surfaces, envelope contract, and agent/maintenance boundaries are **code-owned**: see `scripts/flight_calendar/contracts.py`, `scripts/flight_calendar/parser.py`, and `schemas/cli-envelope.v1.schema.json`. Run `--json doctor` for the live contract surface.

### Diagnostics & Carriers
- `carriers.md` — operator notes for Aeroflot, Red Wings, Ural Airlines, and Utair; carrier-specific fixes only.

### Delivery
- `delivery-details.md` — Hermes delivery plugin plus send_message MEDIA: fallback pitfalls for .ics delivery, platform quirks, target format.

### Maintenance
- `maintenance/operations.md` — read-only maint commands, boundaries, TDD slice sequence, reference add/change rules.
- `maintenance/evaluation.md` — model evaluation, cross-model review, provider pitfalls, native tool-call smoke test, deterministic harness flow, causal model of redundant verification, golden-path principles. Single owner for all eval-related content.
