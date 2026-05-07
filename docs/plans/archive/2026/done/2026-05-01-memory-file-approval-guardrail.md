# Plan: Guardrail before modifying core Hermes memory files

## Goal
Add a programmatic guardrail that prevents an agent from modifying these files without explicit user approval:

- `~/.hermes/memories/MEMORY.md`
- `~/.hermes/memories/USER.md`
- `~/.hermes/SOUL.md`

## Context
This is a Hermes Agent safety change. The protected files are core prompt/memory control surfaces; accidental edits can change agent behavior across future sessions.

Scope:

- File tools: `write_file`, `patch` / V4A patch.
- Memory tool: `memory(action=add|replace|remove)` for `memory`/`user` targets.
- Terminal commands that target those files via common write primitives/redirection should require approval through the existing dangerous-command approval system.

## Non-goals
- Do not edit the protected memory files themselves.
- Do not create a broad immutable filesystem policy outside Hermes.
- Do not block unrelated file writes or normal read-only inspection.

## Steps
- [x] Inspect existing approval and file/memory write paths.
- [x] Add a shared approval helper for protected Hermes context files.
- [x] Call the helper from file write/patch paths and memory mutation paths.
- [x] Extend terminal dangerous-command detection for these paths.
- [x] Add tests for direct tool writes, memory writes, approvals, and terminal detection.
- [x] Run targeted tests and syntax checks.
- [x] Report exact files changed and verification results.

## Verification
- [x] Protected direct file writes are blocked without approval.
- [x] Session-approved protected writes are allowed.
- [x] Memory add/replace/remove is blocked without approval and allowed after approval.
- [x] Terminal write to protected paths is detected as dangerous.
- [x] Unrelated file writes still work.

## Risks / pitfalls
- A too-broad guardrail could block legitimate writes outside the protected context files.
- Terminal dangerous-command detection is heuristic; it must catch common write primitives/redirection without pretending to be a complete shell sandbox.
- Approval state must be scoped tightly enough that one approval does not silently authorize unrelated future memory-file edits.
- Do not test by modifying the real protected memory files unless that exact write is explicitly approved and reversible.

## Status
Current status: done


## Notes
2026-05-05: active-plan audit — verified complete and archived.
Evidence:
- Shared helper exists in `tools/approval.py`: `protected_context_file_for_path()` + `check_protected_context_file_write()` for `MEMORY.md`, `USER.md`, `SOUL.md`.
- `tools/file_tools.py` calls the helper for `write_file` and `patch`.
- `tools/memory_tool.py` calls the helper before add/replace/remove mutations.
- `tests/tools/test_protected_context_file_guard.py` covers direct writes, session approval, memory writes, and terminal dangerous-command detection.
- `python -m pytest tests/tools/test_protected_context_file_guard.py -q -o addopts=`: 6 passed.
- `python -m py_compile tools/approval.py tools/file_tools.py tools/memory_tool.py tests/tools/test_protected_context_file_guard.py`: passed.
Caveat: implementation is local/uncommitted in `/home/konstantin/.hermes/hermes-agent` branch `fix/stale-sessiondb-cleanup`; current live gateway process also runs from this checkout.

- 2026-05-05: normalized to `/home/konstantin/docs/plans/README.md` canonical shape; no implementation status was changed.
