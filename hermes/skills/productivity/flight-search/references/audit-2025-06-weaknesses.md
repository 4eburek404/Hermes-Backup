# Flight-Search Skill Weakness Audit (June 2026)

Audited SKILL.md, all 7 references, CLI surface (14K LOC, 255 tests), schemas, and test coverage.

## Findings and Recommended Actions

### 1. Airport policy duplication across 3 files
IST/SAW, London LHR/LGW/STN/LTN, Moscow MOW rules appear in SKILL.md, `source-boundaries.md`, and `provider-aware-airport-priority.md`. Dubai (DXB/DWC/SHJ) only in `source-boundaries.md`.
- **Fix:** Make `provider-aware-airport-priority.md` the SSOT. Remove airport rules from `source-boundaries.md` and SKILL.md, keep one-line pointers.

### 2. Dead/misleading references
- `direct-date-window.md`: documented a proposed `route direct-window` command that doesn't exist. **Patched** with warning.
- `cli-maintenance.md`: mentions `route kb-assemble` as conditional — it exists as compat alias. Document explicitly or remove.
- **Fix:** Patched direct-window warning. For kb-assemble: document as compat alias or remove entirely.

### 3. No RZD test coverage
`rail-rzd-live-pricing.md` describes the pass.rzd.ru endpoint and Python probe, but 0 of 255 tests cover RZD parsing. API response format changes would break silently.
- **Fix:** Add `tests/test_rzd_pricing.py` with mock fixtures for station suggester, RID workflow, and `cars[]`/`tp[]` parsing.

### 4. 60% of doc volume serves maintenance, not traveler
`cli-maintenance.md` (227 lines) + `debug-playbook.md` (197) + `report-contract.md` (162) = 586/997 lines. Traveler-relevant content is buried.
- **Fix:** Shrink `report-contract.md` to traveler-relevant read order, answer shape, caveat discipline, v3 catalog. Move retired surfaces, MCP outputSchema, renderer implementation ownership to `cli-maintenance.md`. Move version-bump checklist and generated-artifact cleanup to a CONTRIBUTING section.

### 5. `--agent-mode` legacy flag with no deprecation timeline
Still active in CLI (`apply_agent_mode_defaults`). Sets aggregate-control-limit=10 and other defaults. No deprecation warning, no removal plan.
- **Fix:** Add stderr warning: `--agent-mode is deprecated; use --agent-report + explicit --aggregate-control-limit`. Remove after 2 release cycles.

### 6. No `--no-cache`/freshness rule in SKILL.md
Default TTL = 30 min. No guidance on when to use `--no-cache`. Dynamic pricing makes this decision-critical.
- **Fix:** **Patched** into pitfall #10.

### 7. Weak v3 catalog semantic test coverage
Semantic validator checks contiguous numbering (line 684) but only one test with `[1, 2]`. Missing: empty catalog, gaps, zero-based, duplicates, single-item (valid), 10+ items, round-trip without return, `detail_status=missing` in catalog.
- **Fix:** Add 8-10 negative test cases to `test_catalog_answer_contract.py`.

### 8. No FLI round-trip probe
`kb-roundtrip` exists for RU. `fli-search`/`fli-dates` are one-way only. Non-RU round-trip evidence is weaker.
- **Fix:** Document in SKILL.md: for non-RU round-trips, run `fli-search` for each direction separately and label as separate one-way evidence with unproven through-fare.

### 9. FLI MCP: no retry on transient failures
`fetch_fli_mcp_search` makes 1 HTTP request, no retry on 503/429/timeout. KupiBilet has cached search with retry; FLI does not.
- **Fix:** Add exponential backoff (2 retries) for transient errors in `fli_mcp.py`. Do not retry 4xx client errors.

### 10. `route kb-assemble` undocumented compat alias
Exists in CLI as `COMPATIBILITY_COMMANDS = ("route kb-assemble",)`. Not documented in SKILL.md or debug-playbook.
- **Fix:** Document as compat alias in pitfall #13, or remove from CLI surface entirely.

### 11. Cache TTL not documented for agent
`--cache-ttl-seconds` (default 30 min) and `--live-cache-ttl-seconds` are CLI flags but not mentioned in SKILL.md. Different flags for subcommands vs route.
- **Fix:** **Patched** into pitfall #10.

### 12. `--agent-brief` trim semantics undocumented
`--agent-brief` strips JSON to only `agent_report`. Raw `evidence`/`frontier`/`diagnostics` are not included. No doc on what's trimmed or when to use `--agent-report` instead.
- **Fix:** **Patched** into pitfall #9.

### 13. Schema vs semantic validation gap
v3 schema validates JSON structure; semantic rules (contiguous numbering, answer_mode inference, round-trip direction requirement) are in `final_answer_contract.py` not in schema. Tests only cover happy paths.
- **Fix:** Add contract test maturity matrix to `report-contract.md`.

### 14. Profile trade-offs not documented
`business` penalizes LTN/STN/SAW/LGW 4-14 points; `cheap` penalizes 0. No guidance in SKILL.md on when to pick which.
- **Fix:** **Patched** into Decision Rules and pitfall #11.

## Test Coverage Summary (255 tests)

| File | Tests | Lines |
|------|-------|-------|
| test_route_workflows.py | 20 | 1094 |
| test_kupibilet.py | 23 | 1078 |
| test_agent_report_contract.py | 29 | 939 |
| test_provider_aggregate_candidates.py | 14 | 707 |
| test_agent_report_builder.py | 12 | 642 |
| test_final_answer_contract.py | 18 | 560 |
| test_airport_priority_policy.py | 11 | 360 |
| test_fli_mcp.py | 12 | 357 |
| test_cli_contract.py | 14 | 345 |
| test_human_answer_renderer.py | 7 | 336 |
| test_coverage_controls.py | 8 | 218 |
| test_probe_dispatcher.py | 6 | 215 |
| Others (13 files) | 89 | ~1700 |
| **Total** | **255** | **~9200** |

## CLI Surface

Root commands: `doctor`, `maintenance`, `catalog`, `cities`, `airports`, `kb-search`, `kb-roundtrip`, `fli-search`, `fli-dates`, `route`, `metrics`
Route subcommands: `plan`, `validate`, `rank`, `assemble`, `kb-assemble` (compat), `live-assemble`
Profiles: `balanced` (default), `business`, `cheap`, `safe`
Cache: `--cache-ttl-seconds` (default 30min), `--no-cache` for probes; `--live-cache-ttl-seconds`, `--no-live-cache` for live-assemble