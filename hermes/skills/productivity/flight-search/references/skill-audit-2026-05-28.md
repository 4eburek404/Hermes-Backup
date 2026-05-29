# Flight-search Skill Audit Notes — 2026-05-28

Use this reference when maintaining or re-auditing the flight-search skill. It captures durable findings from a read-only audit; it is not a route-search procedure.

## Audit contract

- Start audit reports by naming the active skill version.
- Verify runtime skill path and CLI version before drawing conclusions.
- Distinguish operational runtime skill state from source checkout / published GitHub state; source/runtime drift is a first-class audit finding, not a footnote.
- Keep edits out of read-only audits; report findings and proposed priorities only.

## Durable findings to check in future audits

1. **Source/runtime drift** — compare active runtime `SKILL.md`, runtime CLI `python -m flights_cli --version`, and the local source checkout before saying which version is current.
2. **Connection-threshold consistency** — keep one canonical policy for protected connections, separate/self-transfer, checked baggage, cross-airport moves, and business-comfort recommendations. If `source-boundaries.md` and `cli/README.md` differ, classify it as a high-priority contradiction.
3. **Golden Path vs exception probes** — `route live-assemble --agent-brief` remains the normal route-search path, but `kb-roundtrip`, carrier-specific `kb-search`, and other narrow probes need explicit rules for when they become primary evidence and how they are merged into the final answer.
4. **Traveler mode vs maintenance mode** — keep the top-level skill traveler-first. Maintenance/debug/history material should stay behind explicit gates and in references.
5. **Missing workflow coverage** — re-check whether the skill clearly handles relative dates/timezones, flexible date windows, non-default passengers/cabins, cache freshness, baggage variants, booking-screen proof, and compact answer templates for direct-service absence, carrier-specific, exact-airport, and degraded-evidence cases.
6. **Prompt-surface hygiene** — avoid duplicating provider/airport policy, single-PNR proof boundaries, static-advisory warnings, and renderer-contract rules across many files without a clear canonical source.

## Reporting shape

For read-only audits, a useful report shape is:

1. Active version and provenance.
2. Short verdict.
3. What confuses or conflicts.
4. What is missing.
5. Prioritized fix list.

Do not include raw diffs or long logs unless the user asks for evidence detail.
