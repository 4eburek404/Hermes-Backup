# Knowledge Skill Refactor Audit — 2026-05-08

Session-specific evidence and refactor guidance for `knowledge-architecture` and its bundled `knowledge` CLI.

## Context

The user requested a read-only audit of the `knowledge-architecture` skill: refactor/optimization analysis and what should move from prose into the CLI.

## Verified evidence collected

- Main skill path: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/SKILL.md`.
- Installed CLI wrapper: `/home/konstantin/.local/bin/knowledge`.
- CLI source: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli/`.
- `knowledge --json doctor` succeeded.
- `knowledge --json report --all` succeeded.
- `knowledge --json docs audit` succeeded and returned 23 findings by class: `dead_log` 3, `missing_index` 2, `secret_risk` 5, `plan_status_drift` 13. Do not expose sensitive finding paths/details unless sanitized.
- CLI tests completed successfully in the session, but exact passing count was not preserved after context compaction.
- Repo context reported by delegate: branch `fix/ollama-native-auxiliary-routing`, HEAD `6ac6367f196e`, dirty files included `SKILL.md`, `references/local-cli-audit.md`, `references/plan-governance.md`, and `scripts/distillation_worker.py`.

## Refactor diagnosis

`SKILL.md` should be a compact router/architecture contract, not a full operating manual. Target shape: keep activation rules, routing, guardrails, evidence-first CLI entrypoints, and reference map in the main file; move detailed procedures and dated evidence into references.

Known main-file issues found during the audit:

- Missing explicit `## When to Use` section.
- Large main file: about 227 lines / 21,120 characters at audit time.
- Duplicated anti-pollution/core-file guardrails.
- MEMORY architecture wording conflict:
  - `SKILL.md` says exactly four types.
  - `references/memory-hygiene.md` had wording implying only three types.
  - `SKILL.md` quick reference omitted holographic hygiene in one place.
  - `references/memory-refactoring-2026-05.md` records the final four-entry architecture.
- Volatile multi-instance inventory in the main file can drift and should move to a reference or docs infrastructure note.
- Generated `__pycache__` under the CLI tree blocks clean skill audits.

## CLI correctness issues found

Fix these before expanding CLI surface:

1. Default distillation worker path was stale/nonexistent:
   - stale: `/home/konstantin/.hermes/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py`
   - actual: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/scripts/distillation_worker.py`
2. SOUL path detection checked a stale path:
   - stale: `/home/konstantin/.hermes/memories/SOUL.md`
   - actual: `/home/konstantin/.hermes/SOUL.md`
3. Companion skill contained stale escape-hatch path: `/home/konstantin/code/clis/knowledge`.
4. `skill companion` YAML frontmatter parsing did not handle folded `>-` descriptions cleanly.
5. README dependency wording should distinguish default/offline stdlib-only CLI from live distillation worker dependencies such as `aiohttp`.
6. `report --all` did not fully include the same detail as `docs audit`; either include a skill/docs health summary or document that it is a high-level report.

## What belongs in SKILL.md

Keep only durable activation-level material:

- Frontmatter and concise overview.
- `## When to Use` trigger list.
- Knowledge-layer routing matrix: USER/MEMORY/SOUL, fact_store, docs, skills, session_search.
- Non-negotiable guardrails: read-only evidence first, no secret storage, core-file diff+approval, explicit mutation mode, operational current-state verification.
- CLI-first evidence instruction with pointer to `references/knowledge-cli.md`.
- Reference loading map for distillation, docs review, memory hygiene, plan governance, local CLI audit, SOUL governance.
- Known pitfalls short list only.
- Verification checklist.

## What should move/remain in references

- MEMORY composition details and conflict history → `references/memory-hygiene.md` and `references/memory-refactoring-2026-05.md`.
- Distillation model pool, JSON mode, benchmark evidence → `references/distillation.md`, `references/json-schema-benchmark.md`, `references/deepseek-native-distillation-benchmark-2026-05-07.md`, `references/verification-claims-2026-05-07.md`.
- Plan lifecycle rules → `references/plan-governance.md` plus `/home/konstantin/docs/plans/README.md`.
- Multi-instance inventory → a dedicated reference or infrastructure docs note, not volatile main-file prose.
- Local CLI audit procedures → `references/local-cli-audit.md`.

## What should move into `knowledge` CLI

Only deterministic read-only evidence collection should move to the CLI. Do not make the CLI approve or perform mutations.

Recommended additions:

- `knowledge skill audit` / `knowledge skill lint`: required headings, size pressure, stale paths, generated artifacts, broken script refs, duplicate/conflicting claims, companion-contract checks.
- `knowledge paths audit`: canonical path existence and stale path references for Hermes home, skill source, docs root, SOUL, worker scripts, companion skills.
- `knowledge memory audit`: fact counts, duplicate candidates, volatile/canonical tag inventory, reality-asserting fact candidates; no auto-merge/remove.
- `knowledge docs audit --deep`: stale current claims, wrong-layer docs, duplicate-with-skill/fact_store candidates, raw logs, secret-risk candidates with redaction.
- `knowledge plans audit --policy`: status/path convention, archive placement, required sections, verification gaps, unchecked items in closed plans.
- `knowledge local-cli audit`: skill-bundled CLI inventory, installed wrapper correctness, pyproject/package drift, generated artifacts, redaction-code checks.
- `knowledge distill worker-check`: worker path/defaults, offline/live contract, dependency availability, model-pool tags, `json_object` vs `json_schema`, DeepSeek production exclusion.
- `knowledge report --all`: include a compact skill-health/CLI-health summary or clearly remain a high-level report.

## Priority order

1. P0 CLI correctness/hardening: stale paths, SOUL detection, YAML parsing, generated artifacts, read-only SQLite mode, tests.
2. P1 main skill shrink: add `When to Use`, collapse duplicates, resolve MEMORY 3-vs-4 wording, move volatile inventory to references.
3. P1 references cleanup: align memory-hygiene, plan-governance, local-cli-audit, and companion skill wording.
4. P2 CLI expansion: add deterministic audits listed above with tests.
5. Final verification: `audit_skill.py --skill knowledge-architecture --json`, `knowledge --json report --all`, CLI test suite, AST syntax, no generated artifacts, review git diff before reporting done.
