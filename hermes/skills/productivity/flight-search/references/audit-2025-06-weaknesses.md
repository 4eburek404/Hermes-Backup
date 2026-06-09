# Flight-Search Skill Weakness Audit (June 2026)

Historical audit distilled into current maintenance language. Keep this file as context for why the CLI surface was simplified; use canonical references for active procedures.

## Current durable findings

1. **Airport policy single source of truth.** Keep provider/airport dispatch rules in `provider-aware-airport-priority.md`; other docs should point there instead of duplicating IST/SAW, London, Moscow, or Dubai rules.
2. **Primary search path.** Production answers should go through `search --request`, `data.agent_report`, and `user_answer.rendered_text`. Provider probes are diagnostic follow-ups, not the default answer path.
3. **Maintenance namespace.** Source/runtime provenance, doctor checks, and static catalog refresh/manifest operations live under `maint ...` commands.
4. **Diagnostic namespace.** Provider-specific probes live under `diagnose ...`; they are narrower evidence and must be labeled as such when used.
5. **User-answer contract.** `flight_search_user_answer.v3` is built and semantically validated in `reporting/user_answer.py`. Schema validation alone is insufficient for traveler-facing truthfulness.
6. **Diagnostic mirror.** Human-answer diagnostic projections live under `reporting/projections/human_answer_mirror.py`; they must mirror `user_answer.rendered_text` and never become a second final-prose source.
7. **Agent brief semantics.** `agent_brief` trims output only. It must not silently change evidence budget or route completeness.
8. **Freshness.** Dynamic pricing requires explicit cache discipline; use no-cache controls when freshness matters.
9. **FLI resilience and round trips.** FLI transport should retry transient failures where safe. Non-RU round-trip evidence remains weaker unless a provider supplies one-checkout proof.
10. **RZD coverage gap.** Rail comparison docs need mock-driven tests before relying on live RZD parsing as a stable capability.

## Current test/doc expectations

- Contract tests should use canonical module names:
  - `test_user_answer_contract.py`
  - `test_human_answer_mirror.py`
  - `test_agent_report_projector.py`
- Public CLI tests should assert:
  - primary search: `search --request`;
  - maintenance: `maint check`, `maint doctor`, `maint catalog ...`;
  - diagnostics: `diagnose kb-search`, `diagnose kb-roundtrip`, `diagnose fli-search`, `diagnose fli-dates`.
- Temporary audit scans may check that removed compatibility aliases and old module filenames have not re-entered source, tests, or active docs.
