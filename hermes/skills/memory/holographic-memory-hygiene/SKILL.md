---
name: holographic-memory-hygiene
description: "Minimal R15A recovery placeholder for the SOUL.md holographic-memory-hygiene skill reference. Use for basic fact_store retrieval/hygiene reminders only."
version: 0.1.0-r15a-placeholder
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [memory, holographic, fact-store, recovery-placeholder]
---

# Holographic Memory Hygiene — R15A placeholder

Minimal runtime placeholder created during R15A recovery because `SOUL.md` references this skill and no original skill file was found on disk.

Use this only as a short reminder:

- For questions about Konstantin, the environment, past decisions, stable preferences, or cross-domain conclusions, use `fact_store` `probe`, `search`, or `reason` before answering.
- After using retrieved facts, rate them with `fact_feedback` when available.
- Before adding facts, search first; update existing facts instead of creating duplicates.
- Do not save operational noise, temporary progress, raw logs, or one-off session details.
- If unsure, search memory/session/docs/skills before answering or mutating durable state.

Full workflow should live in `knowledge-architecture` / `references/memory-hygiene.md` if available.

## HRR / release durability checks

When HRR or `fact_store` retrieval seems to have “silently disappeared”, check both code provenance and runtime dependency state before concluding the database is broken:

1. Verify active release and source commits:
   - `readlink -f ~/.hermes/hermes-agent`
   - source repo branch/HEAD under the primary Hermes checkout
   - release `release_metadata.json`
2. Compare fork patches against upstream for:
   - `plugins/memory/holographic/store.py` — Cyrillic/single-word/backtick entity extraction
   - `plugins/memory/holographic/retrieval.py` — FTS5 OR fallback
   - `pyproject.toml` — NumPy in base dependencies, not only optional `voice`
   - `scripts/hermes_release_preflight.py` — HRR algebra probe
3. Verify runtime, not just code:
   - active venv can `import numpy`
   - `plugins.memory.holographic.holographic._HAS_NUMPY` is true
   - `hrr.encode_text(..., dim=32)` works
   - `~/.hermes/memory_store.db` has non-null `facts.hrr_vector`
4. Distinguish states:
   - patch present in fork/source ≠ active production switched to that release;
   - package installed manually in active venv ≠ durable in next release;
   - `probe/reason/related` returning results can still be FTS fallback if NumPy is unavailable.

Verified case 2026-05-13: commit `2b723489c` preserved FTS5 OR + entity extraction in the fork and active `d04c50f2f614`; upstream/main lacked those patches. Commits `2512a8dbd`/`6beda5f84` added durable NumPy/base/preflight checks but were inactive RCs until production switch.
