# Flight Search CLI Redesign Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Разобрать перегруженный flight-search CLI/report path на понятные слои: пользовательский поиск, evidence/probe execution, decision/frontier, canonical user answer, agent/debug contract.

**Architecture:** Публичный путь должен быть одним тонким wrapper-ом над общим pipeline: `SearchRequest -> ProbeIntent ledger -> provider ports -> assembled/ranked frontier -> user_answer -> renderer`. Не вводим новую башню публичных режимов/флагов. Agent/debug поведение — внутренний контракт и legacy compatibility; output не должен скрыто менять provider calls. Если нужен больший evidence budget, это явное внутреннее evidence policy/plan, а не “человеку показать JSON”.

**Tech Stack:** Python 3.11, argparse, JSON Schema Draft 2020-12, pytest/unittest, existing `flights_cli` package under `hermes/skills/productivity/flight-search/cli`.

---

## Проверенные факты на момент плана

- Source checkout: `/home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search`.
- Runtime skill: `/home/konstantin/.hermes/skills/productivity/flight-search`.
- Source git before plan branch: branch `main`, HEAD `301f2f18648f`, dirty `False`.
- Runtime/source parity from `python3 -m flights_cli --json maintenance check`: `different`, `changed_count=2`; differences are `SKILL.md` and `references/cli-maintenance.md` only.
- Current branch for this plan file: `flight-search-cli-redesign-plan`.
- Current public maintenance skill already says `--agent-mode` is overloaded and coverage/aggregate controls should compile to common `ProbeIntent`/ledger.

## Current problem map

### Agent flags are overloaded

Current parser has:

- `--agent-report` in `flights_cli/cli.py`: attach and validate `data.agent_report`.
- `--agent-mode` in `flights_cli/cli.py`: enables `agent_report`, changes output caps, and if `aggregate_control_limit <= 0` sets `aggregate_control_limit = 10`.
- `--agent-brief` in `flights_cli/cli.py`: implies `agent_mode`, then trims JSON to `{ "agent_report": ... }`.

Therefore the word `agent` currently means three different things:

1. Add structured report.
2. Compact output.
3. Increase evidence/control budget through aggregate controls.

Target: stop using one “agent mode” as a semantic bucket.

### `agent_report.v1` is too wide

Measured schema facts:

- `agent_report.v1.schema.json` top-level required fields: 17.
- Top-level required list: `schema_version`, `route`, `status`, `source_boundaries`, `hub_viability`, `segment_searches`, `provider_failures`, `recommended_options`, `priority_options`, `aggregate_controls`, `coverage_diagnostics`, `offer_graph`, `through_fare_checks`, `rejected_pair_warnings`, `answer_lines`, `display`, `human_answer`.
- Total nested required count: 179.

Meaning of `179 nested required`: this is the sum of every `required` list across the whole JSON schema, not 179 top-level fields. It includes top-level requirements plus nested object requirements such as `route` 8, `option` 16, `connection` 11, `aggregate_control` 11, `coverage_diagnostics` 11, `flight_display_option` 7, `human_answer` 3, etc. It is a maintenance-risk metric: one catch-all schema is enforcing many unrelated layers at once.

### User-facing outputs are duplicated

Current runtime references show multiple output/prose paths:

- `reporting/answer_line_renderer.py::build_answer_lines(report)` builds diagnostic/action lines.
- `reporting/human_answer_renderer.py::build_human_answer(agent_report)` builds `human_answer.text` and sections.
- `reporting/flight_display.py::build_flight_display(report)` builds `display.text/options`.
- `reporting/final_answer_contract.py::build_user_answer_contract(agent_report)` builds `flight_search_user_answer.v1`, but current references show it is used by tests and not yet the main runtime output path.
- `output.py::render_agent_report_human(report)` prefers `human_answer.text`, then falls back to `display.text`, then `answer_lines`.

Target: one canonical user answer contract. `human_answer`, `answer_lines`, and `display` must either be projections from it or debug artifacts, not parallel final-answer sources.

### Provider port abstraction exists but is not fully integrated

Current code has:

- `ports/providers.py`: `ProviderCapabilities`, `ProviderProbeResult`, `FlightProviderPort` protocol.
- `adapters/providers/registry.py`: provider descriptors/capabilities for `kupibilet` and `fli`.
- `execution/probe_dispatcher.py`: still branches directly on `if provider == "kupibilet"` / `elif provider == "fli"`.
- `execution/aggregate_control_runner.py`: separate mini-dispatcher for Kupibilet aggregate controls.

Target: do not delete the port pattern. Complete it and make it the only provider execution path for segment and aggregate probes.

---

## Target CLI semantics

### Public command surface

Preferred end state:

```bash
flights search ORIGIN DEST --depart-date YYYY-MM-DD [--return-date YYYY-MM-DD]
```

Minimal public flags:

- `--depart-date`
- `--return-date`
- `--currency`
- `--only-carrier` / possible later alias `--carrier`
- `--exclude-carrier`
- `--prefer-carrier`
- `--avoid-carrier`
- `--stops business|direct-one-stop|debug` or keep `--stop-policy` only as advanced if naming is not ready
- existing global `--json` only when machine-readable output is explicitly required

No new public `--format`, `--report-level`, `--agent-json`, `--evidence`, `none/user/agent/debug`, or similar taxonomy flags. Internal code may use small booleans/objects for clarity, but CLI surface stays narrow.

Everything else becomes advanced/debug:

- candidate pool and include limits;
- raw/rejected/segment-result inclusion;
- provider policy;
- cache TTLs;
- direct-route-intel toggles;
- day-offset fanout;
- fail-fast;
- explicit coverage controls;
- aggregate-control internals.

### Agent-mode replacement

Remove “agent mode” as a conceptual primitive. Do **not** replace it with a menu of new public flags like `none/user/agent/debug/human/json`. That would just move the confusion.

Target behavior:

- There is one normal user path and one canonical `user_answer`.
- `--json` remains the existing machine-output switch; we do not add `--format human|json|agent-json`.
- `--agent-report` is a narrow compatibility flag: attach structured report, no search/evidence mutation.
- `--agent-brief` is a narrow compatibility flag for tools: output only the compact report/user-answer payload, no search/evidence mutation.
- `--agent-mode` is legacy. During migration it may keep old behavior behind tests, but it must not be a design foundation or golden-path flag.
- Evidence expansion belongs in the planning/probe layer. If aggregate/full-route controls are needed, the pipeline should plan them from request/evidence needs, not because output is “agent”.

Final merge gate: no new public agent-mode taxonomy. Old `--agent-mode` is removed from documentation or left only as explicitly deprecated compatibility; preferred public future is `flights search ...` plus existing `--json` when machine output is required.

---

## Schema target

Avoid long-lived v1/v2 dual support. Use a feature-branch cutover with explicit cleanup.

Target files:

- `contracts/common.v2.schema.json`
  - route, price, normalized segment, provider/source/cache enums, common error shape.
- `contracts/search_evidence.v2.schema.json`
  - planned probes, executed probes, terminal states, cache/source status, provider failures, source exhausted, budget expired, completeness.
- `contracts/offer_frontier.v2.schema.json`
  - recommended option, alternatives, cheapest/fastest/direct/frontier representatives, decision stability, missing evidence.
- `contracts/flight_search_user_answer.v2.schema.json`
  - canonical user-facing answer: route, primary recommendation, alternatives, evidence status, stop policy status, required caveats, rendered sections/lines.
- `contracts/agent_report.v2.schema.json`
  - wrapper only: route, evidence, frontier, user_answer, diagnostics.

Legacy cleanup rule:

- `agent_report.v1.schema.json` may coexist only inside the feature branch while tests are migrated.
- Before final implementation branch is considered done, either remove v1 runtime output entirely or leave v1 only in explicit legacy fixtures/tests with no production builder path.
- Add a test that fails if production code still builds both v1 and v2 reports by default.

---

## Canonical user-answer rule

Target data flow:

```text
frontier + evidence + stop_policy
  -> build_user_answer(...)
  -> validate_user_answer(...)
  -> render_human(user_answer)
  -> optional agent_report.user_answer
```

Rules:

- `user_answer` is the only user-facing contract.
- `human_answer.text` should become either `user_answer.rendered_text` or disappear as a separate schema object.
- `answer_lines` should become `user_answer.lines` or `diagnostics.answer_lines`; it must not be a separate semantic validator source.
- `display` should become a debug/display projection under `diagnostics.display` or be generated only by renderer tests; it should not be a required core report field.
- `output.py` should render from `user_answer`, not directly from `agent_report` internals.

---

## Stop-policy contract rule

Policy пересадок must be part of the contract, not an optional text add-on.

Required contract fields should include:

- `policy_name`
- `preferred_max_connections`
- `fallback_max_connections`
- `hard_max_connections`
- `two_stop_fallback_allowed`
- `two_stop_fallback_used`
- `three_plus_suppressed_count`
- `two_stop_suppressed_because_preferred_exists`
- `garbage_options_suppressed`
- per-option fields:
  - `stop_tier`
  - `max_connections_per_journey`
  - `reportable_by_stop_policy`
  - `stop_policy_reason`

`--include-stop-policy-diagnostics` should not survive as a confusing public flag. The contract should always include compact stop-policy status; detailed diagnostics belong to debug/internal output only.

---

## Implementation plan

### Task 0: Provenance and runtime/source decision

**Objective:** Ensure the implementation starts from a known source/runtime state.

**Files:** none unless a sync is explicitly approved.

**Steps:**

1. Run source provenance:

```bash
cd /home/konstantin/src/Hermes-Backup
printf 'branch=' && git branch --show-current
git status --short --branch
git rev-parse --short HEAD
```

2. Run maintenance check:

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maintenance check
```

3. If runtime/source still differ only in docs, decide explicitly whether to sync runtime docs into source before code work. Do not overwrite either side silently.

**Validation:** Report branch, HEAD, dirty state, runtime/source parity, and whether sync is skipped or approved.

**Commit:** none unless a sync is performed. If sync is performed, commit only the synchronized files.

---

### Task 1: Add intent taxonomy tests before implementation

**Objective:** Freeze the desired separation of output/report/evidence semantics before touching production code.

**Files:**

- Modify/create tests under `hermes/skills/productivity/flight-search/cli/tests/`, likely `tests/test_cli_contract.py` or new `tests/test_cli_intent_profiles.py`.

**Test cases:**

- `--agent-report` attaches report but leaves output and aggregate-control defaults unchanged.
- `--agent-brief` trims JSON to the compact report payload but leaves aggregate-control defaults unchanged.
- old `--agent-mode` is explicitly legacy; if retained temporarily, tests must name its side effects so it cannot masquerade as normal output behavior.
- No new public `--format`, `--evidence`, `--report-level`, or `--output-profile` flags are introduced by this task.

**RED command:**

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest tests/test_cli_contract.py -q
```

Expected: fail because current `--agent-brief` still implies `--agent-mode` and `aggregate_control_limit=10`, and/or because no guard exists against new public taxonomy flags.

**Commit after RED if doing strict step commits:**

```bash
git add hermes/skills/productivity/flight-search/cli/tests/test_cli_contract.py
git commit -m "test: define flight search CLI intent taxonomy"
```

---

### Task 2: Decouple agent brief/report from evidence side effects

**Objective:** Replace ad-hoc `apply_agent_mode_defaults` mutation with narrow compatibility behavior, without adding a new public mode taxonomy.

**Files:**

- Modify: `hermes/skills/productivity/flight-search/cli/flights_cli/cli.py`
- Test: `tests/test_cli_contract.py` / `tests/test_cli_intent_profiles.py`

**Implementation notes:**

- Keep existing global `--json`; do not add `--format` or similar.
- Keep `--agent-report` as report attachment only.
- Change `--agent-brief` so it implies report attachment and output trimming only; it must not imply aggregate controls.
- Treat `--agent-mode` as legacy compatibility only. If retained temporarily, isolate and document its current output/evidence side effects in tests.
- Prefer small helper functions/booleans over new enum taxonomies unless a later task proves they are necessary.

**GREEN command:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest tests/test_cli_contract.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/cli.py \
        hermes/skills/productivity/flight-search/cli/tests/test_cli_contract.py
git diff --cached --check
git commit -m "refactor: decouple flight search agent brief output"
```

---

### Task 3: Make `user_answer` the canonical user output

**Objective:** Integrate `flight_search_user_answer` into the runtime output path, not just tests.

**Files:**

- Rename/repurpose: `reporting/final_answer_contract.py` -> likely `reporting/user_answer_builder.py` or keep file but rename symbols.
- Modify: `reporting/agent_report_builder.py`
- Modify: `output.py`
- Modify: `contracts/flight_search_user_answer.v1.schema.json` or create v2 in Task 5.
- Tests: `tests/test_final_answer_contract.py`, `tests/test_human_answer_renderer.py`, `tests/test_agent_report_contract.py`.

**Behavior:**

- Builder produces `user_answer` as runtime field before rendering.
- Human output renders from `user_answer`.
- `human_answer`, `answer_lines`, and `display` are not independently authoritative.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_final_answer_contract.py \
  tests/test_human_answer_renderer.py \
  tests/test_agent_report_contract.py \
  tests/test_flight_display.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/reporting \
        hermes/skills/productivity/flight-search/cli/flights_cli/output.py \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "refactor: make user answer the canonical flight output"
```

---

### Task 4: Create v2 schema split and migrate builders/tests

**Objective:** Replace catch-all `agent_report.v1` production contract with v2 wrapper contracts.

**Files:**

- Create:
  - `contracts/common.v2.schema.json`
  - `contracts/search_evidence.v2.schema.json`
  - `contracts/offer_frontier.v2.schema.json`
  - `contracts/flight_search_user_answer.v2.schema.json`
  - `contracts/agent_report.v2.schema.json`
- Modify:
  - `services/agent_report_contract.py`
  - `reporting/agent_report_builder.py`
  - `reporting/offer_graph_projector.py` if it remains as frontier projector.
- Tests:
  - `tests/test_agent_report_contract.py`
  - `tests/test_final_answer_contract.py`
  - new schema split tests if useful.

**Required cleanup gate:**

- Add a test that production `build_agent_report` emits `schema_version == "agent_report.v2"` only.
- Remove production dependency on v1 schema before final branch completion.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_agent_report_contract.py \
  tests/test_final_answer_contract.py \
  tests/test_coverage_diagnostics.py \
  tests/test_agent_report_p0_completeness.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/contracts \
        hermes/skills/productivity/flight-search/cli/flights_cli/services/agent_report_contract.py \
        hermes/skills/productivity/flight-search/cli/flights_cli/reporting \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "refactor: split flight search report schemas"
```

---

### Task 5: Complete provider port pattern

**Objective:** Make provider execution go through concrete provider adapters implementing `FlightProviderPort`.

**Files:**

- Modify: `ports/providers.py`
- Modify: `adapters/providers/registry.py`
- Create or modify:
  - `adapters/providers/kupibilet_adapter.py`
  - `adapters/providers/fli_adapter.py`
- Modify: `execution/probe_dispatcher.py`
- Tests: provider dispatch and registry tests.

**Behavior:**

- Registry returns adapter object, not only descriptor.
- `dispatch_segment_probe` calls `provider_adapter.search_segment(query)`.
- Provider-specific cache, normalization, summary, source boundary, and errors are inside adapters.
- `ProviderProbeResult` becomes the common result shape used by contract projection.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_provider_policy.py \
  tests/test_route_workflows.py \
  tests/test_kupibilet.py \
  tests/test_fli_mcp.py -q
```

Use exact existing test filenames after checking repository names.

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/ports \
        hermes/skills/productivity/flight-search/cli/flights_cli/adapters/providers \
        hermes/skills/productivity/flight-search/cli/flights_cli/execution/probe_dispatcher.py \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "refactor: route flight probes through provider ports"
```

---

### Task 6: Unify aggregate controls into `ProbeIntent` / ledger path

**Objective:** Remove separate aggregate-control mini-dispatcher behavior from the evidence path.

**Files:**

- Modify: `execution/probe_ledger.py`
- Modify/create: `execution/probe_intent.py`
- Modify: `execution/probe_dispatcher.py`
- Modify: `execution/aggregate_control_runner.py` or delete after migration.
- Modify: `orchestrators/live_assemble.py`
- Modify: `reporting/coverage_projector.py`
- Modify: `reporting/provider_aggregate_projector.py`

**Behavior:**

- `segment_direct`, `segment_hub_leg`, `full_route_aggregate`, `carrier_aggregate`, and `city_pair_direct` all become planned probe intents.
- Every intent has terminal state: `searched`, `failed`, `skipped`, `not_supported`, `deduped`, `budget_expired`, `source_exhausted`.
- Coverage diagnostics project ledger state; reporting does not invent planned/not_executed controls post-hoc.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_coverage_controls.py \
  tests/test_probe_ledger.py \
  tests/test_provider_aggregate_candidates.py \
  tests/test_agent_report_p0_completeness.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/execution \
        hermes/skills/productivity/flight-search/cli/flights_cli/orchestrators/live_assemble.py \
        hermes/skills/productivity/flight-search/cli/flights_cli/reporting \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "refactor: unify aggregate controls with probe ledger"
```

---

### Task 7: Integrate stop policy into contracts and remove confusing public diagnostics flag

**Objective:** Make stop policy always structured in user/frontier/report contracts.

**Files:**

- Modify: `domain/stop_policy.py` if payload needs fields.
- Modify: `reporting/agent_report_builder.py`
- Modify: `reporting/user_answer_builder.py` or `final_answer_contract.py`
- Modify schemas from Task 4.
- Modify: `cli.py` to remove or hide `--include-stop-policy-diagnostics`.

**Behavior:**

- Compact stop-policy status is always present in `user_answer` and `offer_frontier`.
- Detailed stop diagnostics appear only in debug/internal output.
- No public `--include-stop-policy-diagnostics` flag in golden path.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_answer_lines_stop_policy.py \
  tests/test_agent_report_contract.py \
  tests/test_final_answer_contract.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/domain/stop_policy.py \
        hermes/skills/productivity/flight-search/cli/flights_cli/reporting \
        hermes/skills/productivity/flight-search/cli/flights_cli/contracts \
        hermes/skills/productivity/flight-search/cli/flights_cli/cli.py \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "refactor: integrate stop policy into flight contracts"
```

---

### Task 8: Add public `flights search` wrapper and demote old commands to advanced/debug

**Objective:** Implement the big redesign carefully without deleting working internals prematurely.

**Files:**

- Modify: `cli.py`
- Create/modify: `commands/search.py` or route wrapper command.
- Modify docs/skill references after tests pass.
- Tests: CLI parser/subprocess contract.

**Behavior:**

- `flights search` calls the same live assembly pipeline.
- `route live-assemble` remains advanced/internal.
- `route kb-assemble` becomes an alias/wrapper for `route live-assemble --provider-policy kupibilet` or is marked deprecated with test coverage.
- Provider-specific commands stay diagnostics.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest tests/test_cli_contract.py tests/test_route_workflows.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search/cli/flights_cli/cli.py \
        hermes/skills/productivity/flight-search/cli/flights_cli/commands \
        hermes/skills/productivity/flight-search/cli/tests
git diff --cached --check
git commit -m "feat: add simplified flight search command"
```

---

### Task 9: Cleanup and legacy removal gate

**Objective:** Prevent temporary compatibility from becoming permanent debris.

**Files:**

- Remove production v1 builders/validators if no longer used.
- Remove unused imports, especially in `services/agent_report.py`.
- Remove or explicitly deprecate old agent flags from docs.
- Update `SKILL.md`, `references/report-contract.md`, `references/cli-maintenance.md`, `references/debug-playbook.md`.

**Required checks:**

- Search production code for stale references:

```bash
rg "agent_report\.v1|build_human_answer\(|build_answer_lines\(|include_stop_policy_diagnostics|agent_mode" hermes/skills/productivity/flight-search/cli/flights_cli
```

Expected: only approved compatibility aliases or tests; no default production v1 path.

- Run import/lint-ish cleanup by tests and `git diff --check`.

**Validation:**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest \
  tests/test_architecture.py \
  tests/test_cli_contract.py \
  tests/test_agent_report_contract.py \
  tests/test_final_answer_contract.py -q
```

**Commit:**

```bash
git add hermes/skills/productivity/flight-search \
        docs/plans/2026-06-03-flight-search-cli-redesign.md
git diff --cached --check
git commit -m "chore: remove legacy flight search report paths"
```

---

### Task 10: Full validation and source-to-runtime sync

**Objective:** Prove the source branch works, then deploy to runtime only after approval/sync gate.

**Validation commands:**

```bash
cd /home/konstantin/src/Hermes-Backup/hermes/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -m pytest tests -q
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json maintenance check
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json search SVX MOW --depart-date 2026-06-10
```

The last command should be converted to an offline/mock smoke if live providers are not intended for validation.

**Runtime sync:** Follow `references/cli-maintenance.md` Source-to-Runtime Gate. Back up runtime, dry-run rsync, sync with generated-artifact excludes, run runtime doctor/smoke/tests, then verify source/runtime parity.

**Commit:** source code already committed task-by-task. Runtime sync is not a git commit unless source docs/version changes are made after validation.

---

## Updated recommendations

1. Do not keep “agent mode” as a single concept, and do not replace it with a public mode taxonomy. Keep only narrow legacy report/brief behavior while the future public path becomes one `flights search` command.
2. Do not make output flags secretly change provider calls. Evidence expansion belongs to the planning/probe layer, not to `--agent-*` output flags.
3. Prefer hard schema cutover to v2, but do it on a feature branch with a mandatory legacy-removal gate before merge.
4. Make `user_answer` the canonical user contract and render all human/prose output from it.
5. Complete provider port integration; do not delete the port pattern.
6. Use `flights search` as the final public command; keep old route/provider commands as advanced/debug surfaces until migration is validated.
7. Keep public flags minimal; hide 100500 debug knobs from golden path.
8. Integrate stop policy into `user_answer`, `offer_frontier`, and `agent_report` contracts. Remove confusing public `--include-stop-policy-diagnostics` or make it debug-only.
9. Clean unused imports and stale re-export seams.
10. Move aggregate controls into the same `ProbeIntent`/ledger/provider-port execution path as segment probes.
