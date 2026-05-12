# Plan: Knowledge Architecture Skill P1 Shrink

## Goal
Shrink and harden `knowledge-architecture/SKILL.md` into a compact activation/router skill while preserving detailed procedures in references and keeping the bundled `knowledge` CLI read-only.

## Context
User asked to continue after P0 CLI correctness/hardening was completed. P1 from the audit was: add `## When to Use`, remove duplicated/stale prose from the main skill, align MEMORY composition wording, and move volatile multi-instance inventory into a reference. Branch verified before work: `fix/ollama-native-auxiliary-routing` at `6ac6367f196e`. Working tree was already dirty; edits stayed scoped and unrelated dirty files remain separate.

## Non-goals
- No edits to protected core files `USER.md`, `MEMORY.md`, `SOUL.md`.
- No commit or push.
- No conversion of `knowledge` CLI into a mutating editor.
- No disclosure of secret-scan match values.

## Steps
- [x] Re-run focused evidence: `knowledge --json report --all`, `audit_skill.py --skill knowledge-architecture --json`, target diff/status.
- [x] Rewrite `knowledge-architecture/SKILL.md` as compact router with required sections: Overview, When to Use, workflow map, pitfalls, verification checklist.
- [x] Move volatile multi-instance inventory from main skill into a reference file and point to it.
- [x] Align `references/memory-hygiene.md` MEMORY composition wording with the canonical four-type model.
- [x] Run validation: `git diff --check`, `audit_skill.py --skill knowledge-architecture --json`, CLI tests/smokes with `PYTHONDONTWRITEBYTECODE=1`, generated-artifact check.
- [x] Run diff review / blocker scan. Independent review caught one invalid CLI example; fixed `knowledge --json scan secrets --path /home/konstantin/docs` and re-verified.
- [x] Mark this plan `done` and archive it.

## Verification
- `git diff --check`: OK.
- `PYTHONDONTWRITEBYTECODE=1 make test` in bundled CLI: 11 tests OK.
- `audit_skill.py --skill knowledge-architecture --json`: rc 0, ok true, finding_count 0.
- `audit_skill.py --changed --json`: rc 1 due unrelated dirty files, intended findings 0.
- Source CLI smokes: `doctor`, `skill companion`, `docs audit`, `report --all`, and corrected `scan secrets --path /home/konstantin/docs`: OK.
- `docs audit`: finding_count 23. `scan secrets`: finding_count 5. Secret values not printed or preserved.
- Generated artifacts under knowledge skill: 0.
- Main skill shape after P1: 11,343 bytes / 146 lines; `## When to Use`, `## Common Pitfalls`, and `## Verification Checklist` present.

## Risks / pitfalls
- Existing dirty tree includes unrelated changes; do not stage or overwrite them.
- New and pre-existing untracked references must be handled intentionally if committing later.
- Archived plan is audit trail, not source of current operational truth.

## Status
Current status: done

## Notes
- Mode used: Normal approved maintenance under user's “Продолжай”.
- Protected core files were not edited.
- Commit/push intentionally not done.
