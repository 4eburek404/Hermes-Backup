# Plan: Hermes skill dirty cleanup

## Goal
Bring the Hermes Agent skill-library working tree into a clean, reproducible state after the scoped knowledge CLI commit: classify remaining dirty skill/reference changes, fix audit blockers, split intentional work into logical commits, push if verification passes, and archive/close this cleanup plan.

## Context
User asked to "приведи в порядок" after the repo remained dirty. Live source repo: `/home/konstantin/.hermes/hermes-agent`, branch `fix/ollama-native-auxiliary-routing`, current HEAD before cleanup `7abf4b7d6178`. Remaining dirty paths are skill/reference documentation changes, including Ollama routing notes, skill workflow hardening, MCP examples, and a dirty-worktree provenance reference.

## Non-goals
- Do not edit protected core files `USER.md`, `MEMORY.md`, or `SOUL.md`.
- Do not reset/clean blindly or discard unreviewed user work.
- Do not reveal secret-like values from scanners; report only paths/classes/counts.
- Do not turn skill audit CLIs into mutators.
- Do not restart/reset Hermes while writes are pending.

## Steps
- [x] Re-check live git status, branch, HEAD, and exact dirty paths.
- [x] Review dirty diffs by logical workstream and classify intended scope.
- [x] Fix true/new audit blockers in changed skills without broad unrelated rewrites.
- [x] Run changed-skill audit, diff checks, and focused syntax/tests where scripts are involved.
- [x] Commit intentional changes in logical scoped commits, verifying staged paths before each commit.
- [x] Push branch and verify local SHA equals remote branch SHA.
- [x] Update/close this cleanup plan and archive it.

## Verification
- `git diff --check` passes.
- `python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --repo /home/konstantin/.hermes/hermes-agent --changed --json` passes or any remaining findings are clearly baseline/out-of-scope with no dirty files.
- If Python scripts are changed, syntax/tests run with `PYTHONDONTWRITEBYTECODE=1` and generated artifacts are absent.
- `git status --short --branch --untracked-files=all` is clean after commits/push, excluding no known intentional dirty files.
- Remote branch SHA matches local HEAD after push.

## Risks / pitfalls
- Secret-like examples can leak if raw scanner output is copied; keep summaries redacted.
- A broad `git add -A` could mix unrelated dirty paths; stage only logical groups.
- Fixing one audit warning may reveal another; re-run audit after each fix group.
- Docs plans live outside the Hermes Agent git repo and must be archived separately.

## Status
Current status: done

## Notes
- 2026-05-08 start: cleanup begins after P3 knowledge CLI commit/push `7abf4b7d6178`; remaining dirty appears to be skill/reference documentation from older workstreams, not the committed P3 scope.
- 2026-05-08 done: fixed changed-skill audit blockers without exposing secret-like values; committed three logical docs groups (`9ab557893ff9`, `60ff6c96bfd9`, `7f67984844bf`); pushed `fix/ollama-native-auxiliary-routing` and verified local SHA equals remote SHA. Final Hermes Agent repo status is clean against origin.
