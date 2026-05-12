# Plan: flight-search skill audit remediation

## Status
Current status: planned

## Goal
Bring `skills/productivity/flight-search` to a clean, secure, auditable state without breaking the working `flights_cli` operational workflow.

## Context
- Created: 2026-05-08.
- Source repo: `/home/konstantin/.hermes/hermes-agent`.
- Branch at plan update: `improve/flight-search-skill-audit`.
- HEAD at plan update: `0f4a0a9476cc`.
- Target skill: `/home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search`.
- This is Konstantin's important flight-search skill; prefer conservative, test-first changes over broad rewrites.
- No real credentials, credential fragments, raw logs, or token-shaped values belong in this plan.

## Latest verified evidence
- `make test` under `skills/productivity/flight-search/cli`: 86 tests pass.
- `make smoke` under `skills/productivity/flight-search/cli`: passes.
- `python3 -m flights_cli --json doctor`: returns `ok: true`.
- `audit_skill.py --skill flight-search --json`: currently fails with 76 blockers and 2 warnings.
- Main focused audit classes:
  - generated artifacts under the skill tree;
  - secret-like scanner hits in docs/tests/code;
  - missing `## Common Pitfalls` in `SKILL.md`;
  - unexpected support directory `agents/`.
- Current dirty repo state relevant to this work:
  - modified: `skills/productivity/flight-search/SKILL.md`;
  - modified: `skills/software-development/skill-audit-and-improvement/SKILL.md`;
  - untracked: `skills/productivity/flight-search/cli/flights_cli.egg-info/*`;
  - untracked: `skills/productivity/flight-search/references/audit-distillation-cli-extraction-2026-05-08.md`;
  - untracked: `skills/productivity/flight-search/references/audit-remediation-2026-05-08.md`;
  - untracked: `skills/productivity/flight-search/references/deep-audit-2026-05-08.md`.

## Deep analysis update — audit, knowledge, web, CLI extraction

Verified after running the focused skill audit, the knowledge CLI, web documentation lookup, and static CLI inventory:

- `audit_skill.py --skill flight-search --json` fails with 76 blockers and 2 warnings.
- `audit_skill.py --skill knowledge-architecture --json` fails only because generated Python bytecode exists in the knowledge skill tree; the knowledge skill contract itself is otherwise clean.
- `knowledge --json doctor` returns `ok: true`.
- `knowledge --json report --all` returns findings in docs/plans/memory policy/secret scans, but they are mostly global knowledge-hygiene issues, not blockers for `flight-search` implementation.
- `knowledge --json skill audit` reports generated artifacts for `knowledge-architecture`; clean them separately after knowledge CLI runs.
- `knowledge distill candidates` on `flight-search` produced durable rules that should remain in the skill, not be promoted blindly to global memory: normal path uses `agent_report`; provider failures must be surfaced; cached absence is not proof; priority controls and through-fare caveats must be shown; `--include-candidates` is debug-only.
- Live-model distillation returned no additional candidates; offline deterministic distillation was more useful for this input.
- Context7/Travelpayouts docs confirm Data API auth can be supplied through `X-Access-Token` header or auth query parameter. For this CLI, header auth is the safer implementation because URL auth can leak via logs/traces.
- Direct HTTP fetch of Travelpayouts support pages from this runtime returned HTTP 403; use Context7-cached docs plus code-level tests as the current web evidence layer.
- Current CLI surface already includes: `doctor`, `catalog update/manifest`, `cities search`, `airports explain`, `u6-prices`, `kb-search`, `fli-search`, `fli-dates`, `route plan/validate/rank/assemble/kb-assemble/live-assemble`, `results parse`, `request search/prices-for-dates/grouped-prices`, `metrics workflow`.

Additional CLI actions worth extracting from prose/manual workflow:

1. `flights audit` or `flights doctor --strict`
   - Purpose: one command for runtime provenance, auth presence by provider, generated-artifact detection, provider URL policy, cache staleness, and agent-report contract sanity.
   - Why: today this is split between `doctor`, skill audit, grep/manual checks, and tests.

2. `flights route explain-report --input result.json`
   - Purpose: deterministic rendering of `agent_report` into the exact human answer order: best option, mandatory controls, provider failures, through-fare caveats, verification before purchase.
   - Why: too much answer-shaping still lives in skill prose; this should become testable CLI behavior.

3. `flights route check-through-fare --input result.json` or `flights route through-fare-checks`
   - Purpose: extract same-carrier / same-hub / Aeroflot-SU controls and emit airline/GDS verification checklist.
   - Why: the CLI already computes `through_fare_checks`, but a focused command would prevent agents from treating segment sums as protected fares.

4. `flights providers doctor`
   - Purpose: provider-by-provider readiness: Kupibilet reachability/cache, FLI MCP URL safety/reachability, Travelpayouts Data API auth mode, U6 public endpoint status.
   - Why: `doctor` is broad; provider root cause should be explicit before route-search conclusions.

5. `flights cache inspect|cleanup`
   - Purpose: show live/static cache inventory, TTL, staleness, and remove generated/runtime artifacts from the skill tree.
   - Why: audits fail after tests/local installs create generated artifacts; cache/staleness is operationally important.

6. `flights route controls ORIGIN DEST --date YYYY-MM-DD [--return-date ...]`
   - Purpose: emit mandatory control searches for direct, SVO/Aeroflot, same-carrier, and business-airport controls without running the full assembly.
   - Why: the skill requires priority controls; making them explicit reduces missed operational-frontier options.

7. `flights route compare-providers --input result.json`
   - Purpose: summarize provider disagreements, missing providers, cached-vs-live boundary, and why a source cannot prove absence.
   - Why: source-boundary prose should be machine-checkable and visible in JSON/human output.

8. `flights route validate-report --input result.json`
   - Purpose: run schema + semantic validation for an existing `agent_report` and fail if answer lines omit priority options, provider failures, source boundaries, or through-fare verification.
   - Why: validator exists internally; exposing it prevents regressions and supports CI/manual debugging.

9. `flights request data-api-url --endpoint prices-for-dates|grouped-prices ...`
   - Purpose: build a sanitized request preview that proves auth is in headers and never in the URL.
   - Why: safe debugging for Data API request construction.

10. `flights docs sync-check`
    - Purpose: compare live `--help` output against SKILL.md/README claims for stale flags such as `--agent-mode` vs `--agent-brief`, provider-policy docs, and dependency claims.
    - Why: current docs drift is a major quality risk for this skill.

These candidates should not all be implemented immediately. First implement the security/audit blockers; then add the smallest high-leverage commands: `providers doctor`, `route validate-report`, and `docs sync-check`.

## Updated analysis of the earlier critical-token claim
Earlier report said `output.py:325` definitely prints the real Travelpayouts token. Current source review makes that statement too strong.

Verified current state:
- `travelpayouts_data.request_payload()` returns only redacted/missing auth state for the request metadata it constructs.
- A dry-run human output check printed redacted/missing auth state, not a real credential.
- Therefore, the `output.py` line is best classified as a dangerous credential-rendering sink and audit blocker, not a currently proven real-secret leak through the normal dry-run path.

Still required:
- Remove any renderer behavior that prints a credential field/value shape.
- Do not show credential prefixes.
- Use only boolean/status wording such as `present`, `missing`, or `redacted`.
- Add a sentinel-output regression test proving stdout/stderr do not contain a fake credential string.

Confirmed separate security issue:
- `travelpayouts_data.call_data_api()` currently sends Travelpayouts Data API auth in URL query parameters for live fetches.
- That is a real high-priority risk because URLs can be captured by access logs, proxies, error traces, shell history, and debugging output.
- The fix is to keep the request URL free of auth query params and send auth via `X-Access-Token` header.

## Refactor decision update — duplicates, garbage, stale docs

User-approved direction after a separate skill/refactor review:

- Keep **one** current audit/refactor reference inside the skill and actualize it.
  - Default keep target: `skills/productivity/flight-search/references/audit-distillation-cli-extraction-2026-05-08.md`, because it is already compact and least stale.
  - If renaming is worth the churn, rename it to `references/audit-findings-2026-05-08.md`; otherwise keep the existing filename and update its title/scope.
- Delete old/stale audit notes after their valid facts are merged:
  - `skills/productivity/flight-search/references/audit-remediation-2026-05-08.md`;
  - `skills/productivity/flight-search/references/deep-audit-2026-05-08.md`.
- Update `SKILL.md` references so it points only to the single canonical audit/refactor reference, plus stable operational references (`report-contract`, `source-boundaries`, `debug-playbook`).
- Remove or rewrite stale claims before saving the canonical reference:
  - old `9 blockers + 2 warnings` count; current focused audit is 76 blockers / 2 warnings before cleanup;
  - overclaim that `output.py:325` definitely leaks the real token in the normal dry-run path; current classification is dangerous credential-rendering sink + audit blocker;
  - claim that `u6-prices` needs `TRAVELPAYOUTS_TOKEN`; current understanding: U6 public endpoint does not need Travelpayouts auth;
  - claim that FLI failure automatically degrades to Kupibilet-only; correct behavior is to read `provider_failures` and rerun with explicit `--provider-policy` when needed.
- Remove obvious garbage/unused artifacts as part of the cleanup phase:
  - tracked scrape directory `cli/aeroflot_research/`;
  - generated `cli/flights_cli.egg-info/`;
  - `__pycache__/` and `*.pyc` under the skill tree.
- Fix wrong support path:
  - move `agents/openai.yaml` to `assets/openai.yaml`, or delete it if unused;
  - do not leave both paths documented.

Verification for this refactor slice:

```bash
cd /home/konstantin/.hermes/hermes-agent
git grep -n "audit-remediation-2026-05-08\|deep-audit-2026-05-08\|9 blockers\|u6-prices.*TRAVELPAYOUTS_TOKEN\|agents/openai.yaml\|aeroflot_research" -- skills/productivity/flight-search || true
```

```bash
cd /home/konstantin/.hermes/hermes-agent
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill flight-search --json
```

## Non-goals
- Do not redesign the route search algorithm.
- Do not replace Travelpayouts/Kupibilet/FLI/U6 providers.
- Do not book or purchase tickets.
- Do not store or print real credentials or credential fragments.
- Do not claim production/live provider behavior unless verified by live commands.
- Do not commit/push until tests, smoke, doctor, and focused skill audit are green.

## Implementation steps

### Phase 0 — Guardrails and baseline
- [ ] Re-check branch, HEAD, and dirty status before editing.
- [ ] Re-run focused audit and save only counts/classes, not raw secret-like lines.
- [ ] Confirm `flights_cli` import/test path uses the skill-local CLI, not a stale installed copy.
- [ ] Keep existing modified/untracked files unless intentionally superseded; do not discard prior work silently.

Verification:
```bash
git branch --show-current
```

```bash
git rev-parse --short=12 HEAD
```

```bash
git status --short --branch --untracked-files=all
```

```bash
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill flight-search --json
```

### Phase 1 — Runtime/security fixes with tests
- [ ] Add or update tests for Travelpayouts Data API live-fetch request construction:
  - request URL must not contain an auth query parameter;
  - request headers must include `X-Access-Token` when live fetch is requested;
  - missing auth still raises the existing missing-credentials error.
- [ ] Modify `skills/productivity/flight-search/cli/flights_cli/providers/travelpayouts_data.py`:
  - do not copy auth into query params;
  - construct URL from non-sensitive params only;
  - add `X-Access-Token` to request headers.
- [ ] Add or update tests for human/JSON output redaction using a sentinel fake credential.
- [ ] Modify `skills/productivity/flight-search/cli/flights_cli/output.py`:
  - remove credential-value rendering from request output;
  - print only status wording, or omit auth details entirely.
- [ ] Add tests for FLI MCP URL policy.
- [ ] Modify `skills/productivity/flight-search/cli/flights_cli/providers/fli_mcp.py`:
  - allow `http://localhost`, `http://127.0.0.1`, and loopback IPv6;
  - allow `https://` remote URLs;
  - reject remote cleartext HTTP;
  - reject unsupported schemes and URL-embedded credentials.

Verification after each sub-step:
```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ --tb=short -q
```

### Phase 2 — Remove dead/support-file blockers
- [ ] Delete tracked scrape/research artifact directory:
  - `skills/productivity/flight-search/cli/aeroflot_research/`.
- [ ] Move or delete unsupported support directory content:
  - from `skills/productivity/flight-search/agents/openai.yaml`;
  - to `skills/productivity/flight-search/assets/openai.yaml` if still useful;
  - otherwise remove the config and all references to it.
- [ ] Update references so no stale path mentions `agents/openai.yaml` unless it is explicitly listed as deleted history in the canonical audit reference.
- [ ] Remove generated packaging artifact if it is not intentionally tracked:
  - `skills/productivity/flight-search/cli/flights_cli.egg-info/`.
- [ ] Remove generated Python artifacts after tests/smoke:
  - `__pycache__/`;
  - `*.pyc`.

Verification:
```bash
git grep -n "agents/openai.yaml\|aeroflot_research" -- skills/productivity/flight-search || true
```

```bash
git status --short --untracked-files=all -- skills/productivity/flight-search
```

### Phase 3 — Reference consolidation and scanner false-positive cleanup
- [ ] Keep and actualize one canonical audit/refactor reference:
  - default: `skills/productivity/flight-search/references/audit-distillation-cli-extraction-2026-05-08.md`;
  - optional rename: `skills/productivity/flight-search/references/audit-findings-2026-05-08.md` only if the rename improves clarity enough to justify path churn.
- [ ] Merge only still-valid facts from:
  - `skills/productivity/flight-search/references/audit-remediation-2026-05-08.md`;
  - `skills/productivity/flight-search/references/deep-audit-2026-05-08.md`.
- [ ] Delete the two stale audit reference files after merge.
- [ ] Rewrite the canonical reference so it contains no credential-shaped examples, raw scanner lines, or stale blocker counts.
- [ ] Rename test placeholder values such as fake file credentials to clearly harmless placeholders.
- [ ] Where scanner flags non-secret parser/local variables, prefer clearer names if that does not harm readability.
- [ ] Keep env var names documented only where useful; never include values or fragments.
- [ ] Update `SKILL.md` reference list to point to the single canonical audit/refactor reference, not to deleted historical notes.

Verification:
```bash
git grep -n "audit-remediation-2026-05-08\|deep-audit-2026-05-08\|9 blockers\|definitely prints the real\|u6-prices.*TRAVELPAYOUTS_TOKEN" -- skills/productivity/flight-search || true
```

```bash
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill flight-search --json
```

Expected after this phase: no `secret_like_value` blockers for `flight-search` that come from docs/reference prose.


### Phase 4 — Documentation correction
- [ ] Ensure `skills/productivity/flight-search/SKILL.md` has a concise, exact `## When to Use` section and that it still matches the current CLI scope.
- [ ] Add `## Common Pitfalls` to `SKILL.md`:
  - cached absence is not proof of no flight;
  - provider failures must be surfaced;
  - separate segment sums are not protected through-fares;
  - `--agent-brief` is normal path, `--agent-mode` is debug-only/stale unless deliberately retained;
  - tests/local installs can recreate generated artifacts before final audit.
- [ ] Add a short `## Verification Checklist` if the audit helper or peer-style review still flags structure/readiness gaps.
- [ ] Correct provider auth docs:
  - Travelpayouts live fetch requires Travelpayouts auth;
  - U6 public endpoint does not require Travelpayouts auth;
  - Kupibilet/FLI availability is independent from Travelpayouts auth.
- [ ] Correct fallback/degradation docs:
  - FLI failure does not automatically become Kupibilet-only under current code;
  - operator should re-run with the appropriate `--provider-policy` when needed.
- [ ] Reconcile `--agent-brief` vs `--agent-mode` across `SKILL.md`, README, and debug docs:
  - either keep `--agent-mode` as debug-only if current `--help` lists it;
  - or deprecate/remove it consistently.
- [ ] Fix README dependency claim if it still says standard-library-only while `jsonschema` is required.
- [ ] Document Data API header auth and MCP remote HTTP policy.

Verification:
```bash
python3 -m flights_cli --help
```

```bash
git grep -n "agent-mode\|agent-brief\|standard library\|provider-policy\|u6-prices" -- skills/productivity/flight-search
```

### Phase 4.5 — Small high-leverage CLI extraction after blockers
Do this only after Phase 1-4 are green or in a separate follow-up commit.

- [ ] Add `providers doctor` or extend `doctor --strict` for provider readiness and URL/auth policy.
- [ ] Add `route validate-report --input result.json` exposing the existing `agent_report` schema + semantic validator.
- [ ] Add `docs sync-check` to compare live `--help` and CLI dependencies against SKILL.md/README claims.
- [ ] Defer larger commands (`route explain-report`, `route controls`, `route compare-providers`, `cache cleanup`) unless a test or real route-search failure proves immediate need.

Acceptance for this phase:
- commands are read-only by default;
- JSON envelope is stable;
- every new command has unit or subprocess tests;
- docs mention the command only after `--help` confirms it exists.

### Phase 5 — Test, smoke, cleanup, final audit
- [ ] Run tests with bytecode disabled.
- [ ] Run smoke with bytecode disabled.
- [ ] Run doctor with bytecode disabled.
- [ ] Remove generated artifacts after tests/smoke.
- [ ] Run focused audit for `flight-search`.
- [ ] Run changed-file audit and separate `flight-search` issues from unrelated audit-skill baseline warnings.

Verification commands:
```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 make test
```

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 make smoke
```

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
```

```bash
cd /home/konstantin/.hermes/hermes-agent
python3 - <<'PY'
from pathlib import Path
import shutil
root = Path('skills/productivity/flight-search')
for path in list(root.rglob('__pycache__')):
    shutil.rmtree(path)
for path in root.rglob('*.pyc'):
    path.unlink()
for path in root.rglob('*.egg-info'):
    if path.is_dir():
        shutil.rmtree(path)
PY
```

```bash
cd /home/konstantin/.hermes/hermes-agent
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill flight-search --json
```

```bash
cd /home/konstantin/.hermes/hermes-agent
python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --changed --json
```

Acceptance criteria:
- focused `flight-search` audit: 0 blockers;
- ideally 0 warnings for `flight-search`;
- all CLI tests pass;
- smoke passes;
- doctor returns `ok: true`;
- no generated artifacts remain under the skill tree;
- no credential-shaped value appears in saved docs or CLI output.

### Phase 6 — Commit/PR only after green gates
- [ ] Review final diff.
- [ ] Ensure no unrelated dirty files are staged accidentally.
- [ ] Commit scoped changes if requested/in scope.
- [ ] Push/open PR only after explicit go-ahead or if already in approved execution scope.

Suggested commit split:
- security/runtime fixes and tests;
- audit artifact cleanup;
- docs/skill contract correction.

## Risks / pitfalls
- Tests can recreate generated artifacts; final cleanup must happen after test/smoke runs.
- Audit docs can self-trigger secret-like scanners if they contain credential-shaped examples.
- Showing even a credential prefix is unnecessary and can remain sensitive.
- `--changed` audit may include unrelated warnings from `skill-audit-and-improvement`; do not misreport those as `flight-search` failures.
- Current docs may describe behavior that code does not implement; live source wins until code/docs are reconciled.
- Do not treat cached Travelpayouts/Aviasales data as purchase-ready; prices/seats must be rechecked upstream.

## Open decisions
- Should `--agent-mode` remain as a debug-only documented interface, or be deprecated/removed in favor of `--agent-brief`?
- Should the generated `flights_cli.egg-info/` be permanently ignored if local editable installs keep recreating it?
- For `agents/openai.yaml`: move to `assets/openai.yaml` if the agent-interface config is still used, otherwise delete it.

## Decisions already made
- Keep one canonical audit/refactor reference, actualize it, and delete the two stale audit-note files after merging useful facts.
- Delete tracked `cli/aeroflot_research/` scrape debris during cleanup.
- Remove generated artifacts after tests/smoke and before final audit.

## Notes
- The earlier “definite real token leak at output.py:325” finding is now corrected: current normal dry-run evidence shows redacted/missing auth state, but the renderer still needs hardening because it handles credential-shaped fields and fails audit.
- The Data API URL auth issue remains a confirmed high-priority security fix.
- This plan is intentionally not marked done; no implementation changes from this plan have been applied yet.
