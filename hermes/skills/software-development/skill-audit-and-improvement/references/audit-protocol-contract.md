# Stable Audit Protocol Contract

Use this reference when skill-library work raises questions about JSON reports, skill-owned CLIs, CI gates, or where to store audit rules.

## Core Decision

Do **not** spread stable JSON reports or CLI contracts across every skill by default. Use one stable audit protocol owned by `skill-audit-and-improvement` and implemented through `scripts/audit_skill.py`.

Every skill should be machine-auditable, but every skill does not need its own JSON artifact or CLI.

## Layering

- `skill-audit-and-improvement/SKILL.md` owns the procedure and routing rule.
- `references/audit-protocol-contract.md` owns the design rationale and contract notes.
- `schemas/` should own JSON Schema files once implemented.
- `scripts/audit_skill.py` should emit the stable machine-readable audit report.
- `fact_store` may keep a compact retrieval pointer to the canonical skill/reference.
- `USER.md` is not the right layer: this is project architecture, not a personal communication preference.
- `MEMORY.md` is not the right layer unless the rule becomes a true always-on self-protection pointer; prefer skill routing first.

## JSON Contract Policy

JSON is mandatory for:

- `audit_skill.py --json`;
- `audit_skill.py --changed --json`;
- secret/redaction scanners;
- stale-path scanners;
- repository-wide skills inventory;
- CI reports;
- `doctor --json` for owning CLIs that have a real machine consumer.

JSON is optional/useful for deterministic scripts that return findings or evidence.

JSON is not needed by default for:

- ordinary instructional `SKILL.md` files;
- `references/*.md`;
- `templates/*.md`;
- short one-off helper scripts with no downstream machine consumer.

## CLI Policy

A skill-owned CLI is justified only when the workflow has repeated executable logic, live checks, redaction requirements, multiple subcommands, CI integration, stateful/multi-file validation, or a mature tool contract.

For most skills, prefer:

```text
SKILL.md
references/
templates/
scripts/
```

Add a CLI only when scripts become too large or when humans/agents/CI need a stable command interface.

## Degradation Gate Shape

The target enforcement loop is:

```text
schema → audit_skill.py → baseline/no-regression compare → CI required check → branch protection → blocker-only review
```

The goal is that degradation becomes hard because the repository rejects bad changes, not because an agent remembers a preference.

## Session Lessons (consolidated from 2026-05-07 and 2026-05-08 audit sessions)

### Provenance Before Editing

Branch, HEAD, status, and target diffs must be checked before modifying skill files. This prevents stale assumptions about runtime paths, old CLI layouts, and dirty development state. Always verify live repo state — do not rely on memory of what files look like.

### Dirty Worktree Provenance

After a verified scoped commit, remaining dirty files are not automatically failed cleanup or safe to commit. Classify each dirty path as:
1. committed-work leftovers that should be finished or separately committed;
2. active-plan work that should stay dirty or move to its own branch;
3. completed-but-unarchived plan notes;
4. unrelated or pre-existing changes that must not be staged.

Run `audit_skill.py --changed --json` before recommending commit; do not print secret-like values from findings.

### Audit Script Hardening Lessons

- `audit_skill.py` must remain read-only: no `git add/commit/checkout/reset`, no destructive shell commands, no permission-changing commands, no mutation of audited skills.
- Reject report outputs inside the repo (`OUTPUT_INSIDE_REPO`).
- Avoid repo-local caches/artifacts during tests (`PYTHONDONTWRITEBYTECODE=1`, `pytest -p no:cacheprovider`).
- Redact entire rest-of-line after sensitive keys, not just the first token. Also redact generic `Bearer ...` segments even when the YAML key is not in the sensitive-key allowlist.
- For deleted nested `SKILL.md` files, derive the affected skill dir from `path.parent`, not from fixed-depth assumptions.

### Master Plan Synthesis Pattern

When a skill-audit task has multiple overlapping plans:
1. Treat existing plans as inputs, not automatically current truth. Reconcile into one master execution map.
2. Preserve companion plans unless the user explicitly approves lifecycle changes.
3. For each phase, include practical profit/benefit, not only tasks.
4. Save durable multi-step synthesized plans under `/home/konstantin/docs/plans/` with machine-readable status.
5. Verify after saving: file exists, `Current status: ...` is present, code fences balanced, no secret-like values, `knowledge --json plans audit` can detect the plan.

## Protected Context Pitfall

Before trying to store this kind of rule in `USER.md`, `MEMORY.md`, or `SOUL.md`, show the proposed diff and analyze whether the rule belongs there. If the write is rejected or would exceed capacity, report that no protected context file changed and route the rule to the correct canonical layer instead.
