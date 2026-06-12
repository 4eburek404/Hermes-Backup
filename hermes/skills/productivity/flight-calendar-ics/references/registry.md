# Reference Registry

Ownership map for `flight-calendar-ics` references. Rules for adding or changing references live in `maintenance/operations.md`.

## Canonical owners

### Core

- `core/architecture.md` — layers, module ownership, stable CLI/envelope contract, agent and maintenance boundaries.
- `core/itinerary.md` — canonical itinerary JSON: role, required fields, normalization from PDFs/emails/screenshots/manual sources.
- `core/privacy-hardening.md` — sensitive data classes, redaction expectations, and safe reporting (single owner of the class list).
- `core/timezone-catalog.md` — airport timezone catalog, diagnostics, and maintenance rules.

### Carriers

- `carriers.md` — operator notes for Aeroflot, Red Wings, Ural Airlines, and Utair; carrier-specific fixes only.

### Maintenance

- `maintenance/operations.md` — read-only maint commands, boundaries, TDD slice sequence, reference add/change rules.
- `maintenance/evaluation.md` — maintainers only: model-evaluation and cross-model review playbook.
