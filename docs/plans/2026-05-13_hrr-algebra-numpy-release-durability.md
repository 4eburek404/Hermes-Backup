# HRR algebra + numpy release durability

Created: 2026-05-13 22:14 CEST (+0200)

## Goal

Enable real HRR algebra for Hermes fact_store by installing numpy in the active Hermes runtime and making the dependency durable for future release builds.

## Plan

1. Capture baseline: active release symlink, source repo/branch/HEAD, dirty state, active venv Python, numpy availability, and HRR fallback state.
2. Locate HRR/fact_store code and the dependency declaration used by release/preflight builds.
3. Add numpy to the durable package dependency source, not only to the active venv.
4. Install numpy into the active release venv using `venv/bin/python -m pip`.
5. Run focused verification: import checks, fact_store HRR mode checks, and relevant tests/preflight checks.
6. Restart gateway only if runtime verification shows the running process needs reload; verify after restart if performed.

## Constraints

- Do not edit protected context files (MEMORY.md, USER.md, SOUL.md).
- Do not touch secrets or tokens.
- Preserve release-dir deployment invariants: active symlink under `~/.hermes/releases/`, systemd should point to symlink paths.
- If a source repo is unavailable, document exactly what is made durable and what remains dependent on upstream/source release workflow.
