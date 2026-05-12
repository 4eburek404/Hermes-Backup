# Knowledge CLI P3 Memory Policy Audit Implementation Plan

> **For Hermes:** implement directly with strict TDD and independent review before reporting done.

**Goal:** Add a deterministic, read-only `knowledge` CLI audit for holographic memory policy drift, starting with `memory policy audit`, and include compact rollups in `report --all`.

**Architecture:** Keep `knowledge` as an evidence collector only. The new command should inspect memory DB metadata/read-only rows and classify candidate findings such as stale path markers, procedure-like facts, volatile old facts, long facts, missing categories, and low-trust/unhelpful candidates without mutating fact_store or dumping secrets/raw sensitive values.

**Tech Stack:** Python stdlib CLI under `skills/note-taking/knowledge-architecture/cli/knowledge_cli/__main__.py`; unittest suite under `cli/tests/test_offline.py`; docs/references under the owning skill.

---

## Scope

### In scope
- Add RED tests for `knowledge --json memory policy audit`.
- Implement static/read-only SQLite-backed audit function using read-only URI.
- Add compact `memory_policy` rollup to `knowledge --json report --all`.
- Update CLI README, `references/knowledge-cli.md`, `references/knowledge-cli-maintenance.md`, and main `SKILL.md` examples.
- Verify source + installed wrapper smokes, audit skill health, and generated artifacts.

### Out of scope
- No automatic fact updates/removals.
- No edits to `USER.md`, `MEMORY.md`, or `SOUL.md`.
- No secret-value printing.
- No commit/push unless separately requested.
- No broad cleanup of unrelated dirty-tree files.

## Tasks

### Task 1: Provenance and baseline

**Objective:** Confirm branch, dirty state, current parser shape, and baseline command behavior.

**Files:** read-only initially.

**Verification:**
```bash
cd /home/konstantin/.hermes/hermes-agent
git status --short --branch --untracked-files=all
git rev-parse HEAD
git branch --show-current
cd skills/note-taking/knowledge-architecture/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json memory metrics
```

### Task 2: RED tests

**Objective:** Define expected memory policy audit behavior before implementation.

**Files:**
- Modify: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli/tests/test_offline.py`

**Expected tests:**
- fixture SQLite DB with `facts` table can be audited read-only;
- stale path markers are flagged with IDs/metadata but no secret/raw content dump;
- procedure-like facts are classified as `procedure_in_fact` candidates;
- old volatile facts are classified as `volatile_stale` candidates;
- `report --all` includes `memory_policy_finding_count`.

**Verification:** focused unittest fails before implementation.

### Task 3: Implementation

**Objective:** Add command/data/render/parser support.

**Files:**
- Modify: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli/knowledge_cli/__main__.py`

**Behavior:**
```bash
knowledge --json memory policy audit
```

Return JSON with:
- `ok` boolean;
- `command: "memory policy audit"`;
- `db.exists`, `db.path`, read-only metadata;
- `fact_count`;
- `finding_count`;
- `findings_by_code`;
- redacted findings with fact IDs/category/tags/trust/helpful/updated_at/content_length only;
- `mutations_performed: false`.

### Task 4: Docs update

**Objective:** Make examples accurate and smoke-tested.

**Files:**
- Modify: `SKILL.md`
- Modify: `cli/README.md`
- Modify: `references/knowledge-cli.md`
- Modify: `references/knowledge-cli-maintenance.md`

### Task 5: Verification and independent review

**Objective:** Prove no regressions and no generated artifacts.

**Commands:**
```bash
cd /home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json memory policy audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json report --all
knowledge --json memory policy audit
cd /home/konstantin/.hermes/hermes-agent
git diff --check -- skills/note-taking/knowledge-architecture/
PYTHONDONTWRITEBYTECODE=1 python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill knowledge-architecture --json
```

Then run independent review limited to knowledge-architecture intended files.

### Task 6: Close plan

**Objective:** Archive this plan as done after verification.

**Destination:**
`/home/konstantin/docs/plans/archive/2026/done/2026-05-08-knowledge-cli-p3-memory-policy-audit.md`

## Status
Current status: done

## Notes
Closed 2026-05-08 after local tests, source/wrapper smokes, generated-artifact cleanup, `git diff --check`, `audit_skill.py --skill knowledge-architecture`, and an independent blocker-only review passed.

No commit/push was requested or performed. The Hermes Agent repo still has unrelated dirty-tree changes outside this P3 scope.
