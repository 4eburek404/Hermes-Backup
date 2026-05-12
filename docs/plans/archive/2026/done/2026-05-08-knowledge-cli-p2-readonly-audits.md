# Plan: Knowledge CLI P2 Read-Only Audits

## Goal
Add the first practical P2 slice to the bundled `knowledge` CLI: deterministic read-only audits that reduce manual prose checking without turning the CLI into an editor or approval channel.

## Context
Konstantin said “Go ahead” after P0 CLI hardening and P1 skill shrink were completed. The P2 roadmap from `references/knowledge-skill-refactor-audit-2026-05-08.md` recommends deterministic checks such as skill audit, paths audit, memory policy audit, plans policy audit, local CLI audit, and worker doctor. Current branch verified before work: `fix/ollama-native-auxiliary-routing` at `6ac6367f196e`. Working tree was already dirty; intended changes were kept scoped and unrelated dirty state is reported separately.

## Non-goals
- No edits to protected core files `USER.md`, `MEMORY.md`, `SOUL.md`.
- No mutating CLI commands, no `--apply`, no auto-fix.
- No commit/push unless explicitly requested later.
- No disclosure of secret-scan match values.
- No broad all-repo cleanup of unrelated dirty files.

## Steps
- [x] Inspect current CLI parser/data helpers/tests and choose a bounded P2 first slice.
- [x] Add RED tests for new deterministic read-only commands.
- [x] Implement minimal code for the commands.
- [x] Update CLI README / knowledge references with new command examples.
- [x] Run focused tests and source/installed smokes with `PYTHONDONTWRITEBYTECODE=1`.
- [x] Run `git diff --check`, `audit_skill.py --skill knowledge-architecture --json`, `audit_skill.py --changed --json`, and generated-artifact cleanup/check.
- [x] Run independent blocker-only review of intended P2 diff.
- [x] Mark plan done and archive after verification.

## Verification
- Full CLI test suite: `Ran 15 tests ... OK`.
- New source command smokes: `paths audit`, `skill audit`, `distill worker-check`, `report --all` returned JSON `ok: true`.
- Installed wrapper smokes: `knowledge --json paths audit`, `knowledge --json skill audit`, `knowledge --json distill worker-check` returned JSON `ok: true`.
- `distill worker-check` reports `live_model_calls: false` and does not import the worker.
- `report --all` includes P2 rollups: paths findings `0`, skill findings `0`, worker findings `0`; docs findings remain existing `23`, secret-risk count `5` with values not printed.
- `git diff --check -- skills/note-taking/knowledge-architecture/`: `rc 0`.
- `audit_skill.py --skill knowledge-architecture --json`: `ok true`, issue/warning count `0`.
- `audit_skill.py --changed --json`: still fails because unrelated dirty non-knowledge files have findings; no intended knowledge P2 blocker was found.
- Generated artifacts after cleanup: `__pycache__ = 0`, `*.pyc = 0`.
- Independent blocker-only review: no blockers.

## Risks / pitfalls
- P2 scope can sprawl; this pass intentionally implemented a first slice only.
- Existing dirty files under and outside the skill tree were not normalized globally.
- CLI examples were smoke-tested with the actual parser.

## Status
Current status: done

## Notes
- Added read-only commands: `knowledge --json paths audit`, `knowledge --json skill audit`, `knowledge --json distill worker-check`.
- `knowledge --json report --all` now includes compact paths/skill/worker health rollups.
- Protected core files were not edited.
- No commit/push was performed.
