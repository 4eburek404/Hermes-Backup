# Plan: flight search skill/CLI distillation

## Goal
Distill lessons from the SVX↔CDG 2026-08-15/2026-08-19 ticket search into the `flight-search-routing` skill and inspect whether the local `flights` CLI needs a workflow/code improvement for direct-segment hub assembly.

## Context
The search initially over-relied on aggregate one-stop/city-pair results. Konstantin corrected the workflow: for Russia↔Europe routes and hub-specific questions, search direct segments separately, then assemble compatible one-stop pairs with actual airport codes and realistic layover buffers. Relevant artifacts:

- `/home/konstantin/flight_search_artifacts/svx_cdg_2026-08-15_2026-08-19_separate_segments_kupibilet.json`
- `/home/konstantin/.hermes/skills/productivity/flight-search-routing/SKILL.md`
- `/home/konstantin/code/clis/flights/`

## Non-goals
- Do not buy tickets or claim final availability beyond cached/live search outputs.
- Do not introduce credentials, tokens, raw logs, or full aggregator responses into docs/skills.
- Do not rewrite the full flight CLI unless the analysis shows a small, verifiable improvement is justified.

## Steps
- [x] Reconstruct what went wrong/right in the SVX↔CDG search from saved artifacts and transcript context.
- [x] Update `flight-search-routing` core with the general rule, not a one-off incident.
- [x] Add or update a compact reference/regression note for the SVX↔CDG case if useful outside the core.
- [x] Inspect `flights` CLI branch/status and route/kb-search capabilities for direct-only hub assembly.
- [x] Decide whether CLI needs a code change now; if yes, implement a small tested change, otherwise record the gap as a concrete future CLI feature.
- [x] Validate changed skill/frontmatter/support files and check no secrets/raw logs were introduced.

## Verification
- Skill core contains a reusable rule requiring direct-only segment assembly for one-stop/hub-specific Russia↔Europe searches.
- Any session-specific details are in `references/` or `archive/`, not bloating the core.
- CLI analysis is grounded in live repo inspection (`git status`, help/source/tests), with explicit decision: changed or not changed.
- Markdown/frontmatter validation passes for touched skill files.
- Secret-risk scan over touched markdown/code files reports 0 hits.

## Risks / pitfalls
- Overfitting the skill to one SVX↔CDG date instead of the class of failure.
- Treating cached Travelpayouts/Kupibilet prices as purchase-ready facts.
- Modifying CLI without tests or without understanding existing route commands.
- Leaving completed plan in root instead of archiving it.

## Status
Current status: done

## Notes
- 2026-05-05: Started after Konstantin requested distillation of the ticket-search workflow and possible skill/CLI update.
- 2026-05-05: Root cause: the initial SVX↔CDG answer used aggregate city-pair/one-stop results before running the mandatory direct-only hub segment assembly that Konstantin expects for Russia↔Europe one-stop/hub-specific searches.
- 2026-05-05: Updated `flight-search-routing` to v2.2.0 with an explicit Russia↔Europe direct-segment assembly gate, `route kb-assemble` CLI quick-reference, pitfall, verification checklist item, and SVX↔CDG regression pointer.
- 2026-05-05: Updated `references/cli-reference.md` and `references/svx-cdg-live-aggregate-pattern-2026-05-05.md`; session-specific flight details stayed in the reference/artifact, not in the skill core.
- 2026-05-05: CLI gap confirmed: local `flights` had `kb-search` and `route assemble`, but no single command for live Kupibilet direct-only hub segment search plus assembly. Added `flights route kb-assemble`, bumped CLI to 0.8.0, and documented it in CLI README.
- 2026-05-05: CLI files changed: `/home/konstantin/code/clis/flights/flights_cli/__main__.py`, `flights_cli/__init__.py`, `tests/test_offline.py`, `README.md`, `pyproject.toml`. No git repo was present in `/home/konstantin/code/clis/flights` or checked parents, so changes were tracked manually here.
- 2026-05-05: Verification passed: `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py`; `python3 -m pytest -q` -> 32 passed, 4 subtests passed; `flights --version` and `python3 -m flights_cli --version` -> 0.8.0; `flights route kb-assemble --help` exposed the new command.
- 2026-05-05: Generated CLI `__pycache__` was removed after validation; final pyc count under `/home/konstantin/code/clis/flights` was 0.
- 2026-05-05: Secret scan over 9 changed markdown/code/plan files reported 0 hits; `flight-search-routing/SKILL.md` frontmatter validation passed. Regression artifact for new CLI gate: `/home/konstantin/flight_search_artifacts/svx_cdg_2026-08-15_2026-08-19_kb_assemble_cli_ayt.json` (`ok: true`, command `route kb-assemble`, 50 ranked candidates). Durable fact stored in fact_store as fact_id 134.
