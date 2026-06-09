# Flight-Search Weakness Audit (June 2025)

Structural weaknesses identified during deep audit of the skill, CLI surface, references, and test suite. Each item includes the problem, evidence, recommended fix, and priority.

## 1. No Scenario Decision Map (now fixed in SKILL.md)

**Problem:** SKILL.md listed 17 CLI commands and vague "run probes when missing evidence" triggers, but did not map user intents to concrete command paths. Agent had to guess which command fits which scenario.

**Evidence:** Fli (upstream) has 3 commands, Amadeus has 2 endpoints. flights_cli previously had 17 unique entry points (22 with dedup). The old Golden Path named the provider-live route command directly but did not explain when follow-up probes were needed or why.

**Fix (applied):** Added "Scenario Decision Map" section to SKILL.md with two-level Golden Path: Level 1 = one command for 90% of tasks, Level 2 = specific user-intent triggers → specific follow-up commands. Added Profile Quick Reference table.

## 2. Airport Policy Duplication Across 3 Files

**Problem:** IST/SAW, London LHR/LGW/STN/LTN, Moscow MOW/SVO/DME/VBK rules appear in SKILL.md, `source-boundaries.md`, and `provider-aware-airport-priority.md`. Dubai (DXB/DWC/SHJ) only in `source-boundaries.md`. Risk of desync when rules change.

**Recommended fix:** Make `provider-aware-airport-priority.md` the SSOT for all airport-priority rules. Remove airport-priority detail from `source-boundaries.md` (leave only evidence-class context). Update `source-boundaries.md` to cross-reference SSOT. Mark in SKILL.md references list (done).

**Priority:** Medium (desync risk is real but changes are infrequent).

## 3. Dead Reference: `route direct-window` Not Implemented

**Problem:** `direct-date-window.md` documents a `route direct-window` command that does not exist in CLI. The "Proposed CLI Surface" section (lines ~55-80) describes expected semantics as if the command exists. Agent calling it gets an error.

**Recommended fix:** Rewrite `direct-date-window.md` to remove the proposed-command section. Current Golden Path = `search --request`; direct-window inventory still uses per-date `diagnose kb-search --direct-only` / `diagnose fli-search --direct-only`. If `route direct-window` is implemented later, add it back at that time. Note added to SKILL.md references list (done).

**Priority:** Medium (agent may attempt nonexistent command).

## 4. Retired route compatibility alias

**Problem:** The old command surface carried route compatibility aliases that duplicated provider-policy search behavior and confused the production/diagnostic split.

**Recommended fix:** Delete compatibility aliases from the public CLI surface; keep provider overrides in the canonical request contract or diagnostic probes.

**Priority:** Low (functional, but adds surface confusion).

## 5. `--agent-mode` Legacy Flag Without Deprecation Path

**Problem:** CLI has three agent flags: `--agent-mode` (legacy), `--agent-report`, `--agent-brief`. SKILL.md Golden Path uses only `--agent-brief`. `apply_agent_mode_defaults()` still runs in `main()`. No deprecation warning, no removal timeline.

**Recommended fix:** Add stderr deprecation warning when `--agent-mode` is used. Timeline: 2 release cycles, then remove. Test suite references to `--agent-mode` should be updated to `--agent-report` + explicit flags.

**Priority:** Low (does not break anything, but accumulates tech debt).

## 6. No `--no-cache` / Freshness Rule

**Problem:** CLI has `--cache-ttl-seconds` (default 30 min) and `--no-cache`. SKILL.md did not specify when `--no-cache` is required. For dynamic flight pricing, stale cache can mislead.

**Fix (applied):** Added "Cache Freshness and Output Trim Rules" section to SKILL.md with concrete triggers for `--no-cache`. Also documented `--agent-brief` trim semantics.

**Priority:** Done.

## 7. Weak v3 Catalog Semantic Test Coverage

**Problem:** `flight_search_user_answer.v3` has 14 required fields per catalog item. Semantic validation in `reporting/user_answer.py` checks contiguous numbering. But `test_catalog_answer_contract.py` had only 4 tests (one with `[1, 2]`). No negative tests for: gaps, zero-based numbering, duplicates, empty catalog, single-item catalog, 10+ items, `detail_status=missing` in catalog, round-trip item without return direction.

**Recommended fix:** Add 8-10 negative test cases to `test_catalog_answer_contract.py`: empty catalog (must fail), gaps `[1,3]` (must fail), zero-based `[0,1]` (must fail), duplicates `[1,1,2]` (must fail), single-item catalog (valid), `answer_mode=recommendation` with catalog (must fail), `detail_status=missing` in catalog items (must surface caveat), round-trip catalog item without `return` direction (must fail).

**Priority:** Medium (invalid answers can pass schema validation).

## 8. No RZD Test Coverage

**Problem:** `rail-rzd-live-pricing.md` describes pass.rzd.ru RID workflow and `cars[]`/`tp[]` parsing. 255 tests in suite, zero for RZD. API changes will break silently at runtime.

**Recommended fix:** Create `tests/test_rzd_pricing.py` with mock responses (initial RID, final timetable). Test station-code suggester format, `cars[]` parsing, `timeInWay`, `elReg` fields. Optional: periodic smoke test against real suggester endpoint (not timetable).

**Priority:** Medium (runtime-only failure detection).

## 9. FLI MCP: No Retry on Transient Errors

**Problem:** `fli_mcp.py` `fetch_fli_mcp_search` makes 1 HTTP request. No retry on 503, 429, connection reset. `call_fli_mcp_tool` likewise. KupiBilet has `cached_kupibilet_search` with retry logic; FLI has none. When MCP server is unavailable, FLI evidence disappears silently.

**Recommended fix:** Add exponential backoff (1-2 retries) for transient errors (503, 429, connection reset, timeout). Do not retry 4xx client errors.

**Priority:** High (single point of failure for all non-RU segments).

## 10. FLI: No Round-Trip Probe for Non-RU Routes

**Problem:** RU routes have `kb-roundtrip` for targeted round-trip evidence. Non-RU routes have `fli-search` (one-way only) and `fli-dates` (flexible dates, not round-trip checkout). Non-RU round-trip through-fare evidence is weaker.

**Recommended fix (short-term):** Document in SKILL.md: "For non-RU round-trip, run `fli-search` for outbound and return dates separately and label as separate one-way evidence with unproven through-fare." (Guidance, not new CLI.) Long-term: consider `fli-roundtrip` command or `--round-trip` flag on `fli-search`.

**Priority:** Medium (evidence gap, not a bug).

## 11. Profile Trade-offs Undocumented

**Problem:** CLI offers 4 profiles (`balanced`, `business`, `cheap`, `safe`) with different penalty weights and rank orders. SKILL.md did not explain when to use which or what the key differences are. Agent defaults to `balanced` without reasoning.

**Fix (applied):** Added Profile Quick Reference table to the Scenario Decision Map in SKILL.md.

**Priority:** Done.

## 12. Reference Bloat: 60% Maintenance, 40% Traveler

**Problem:** SKILL.md (114 lines) + references (997 lines) = 1111 lines. Of 997: `cli-maintenance.md` (227) + `debug-playbook.md` (197) + `report-contract.md` (162) = 586 lines maintenance/debug. Traveler-relevant = ~411 lines.

**Recommended fix:** (a) Trim `report-contract.md`: move retired surfaces, MCP outputSchema, renderer implementation ownership to `cli-maintenance.md`. (b) Trim `cli-maintenance.md`: move version-bump checklist, generated-artifact cleanup, markdown governance to a CONTRIBUTING.md at skill root. (c) Ensure SKILL.md maintenance gate clearly separates traveler mode from maintenance mode.

**Priority:** Low (does not break functionality, but adds cognitive load for agents loading the skill).

## Metrics Summary

| Metric | Value |
|---|---|
| Total unique CLI commands | 17 |
| Primary command (Golden Path) | `search --request` |
| Former provider-live route flags | 50 |
| Fli (upstream) commands | 3 |
| Amadeus API endpoints | 2 |
| SKILL.md + references total lines | ~1111 |
| Test suite tests | 255 |
| RZD tests | 0 |
| v3 catalog semantic tests | 4 |
| FLI MCP retry | No |
| `--agent-mode` deprecated | No |