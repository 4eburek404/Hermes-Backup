# Memory architecture optimization session — 2026-05-03

Context: Konstantin asked to analyze and then execute a plan to compact Hermes always-on memory layers (`MEMORY.md`, `USER.md`, `SOUL.md`). The first review was too verbose; user explicitly said he read only the beginning and practical conclusion. Future memory/plan reviews should lead with the actionable verdict and keep the main answer compact.

Useful outcome:

- Protected files were backed up before mutation:
  `/home/konstantin/.hermes/backups/memory-architecture-optimization-20260503-193937`
- `MEMORY.md` was revised to 3 compact guardrail/routing sections:
  - DO-NOT-EDIT + no restart/reset while writes unfinished;
  - MEMORY is always-on guardrails + pointers, not facts; Gate: «нужно на КАЖДОМ ходу?»;
  - routing cues + holographic trigger and hygiene pointer.
- `USER.md` was compacted while preserving high-impact answer-quality triggers.
- `SOUL.md` was compacted while retaining behavioral enforcement: 6 principles, routing trigger, holographic trigger, skills/docs/plans, communication discipline, permission model, activation boundary.
- Existing skills `holographic-memory-hygiene` and `daily-knowledge-distillation` already existed; do not recreate them.
- Duplicate/superseded active plan handling mattered: old plan `2026-05-01-memory-architecture-optimization.md` was marked `superseded` and archived; current completed plan was archived under `archive/2026/done/`.

Reusable lessons:

1. Do not equate text duplication with enforcement duplication. Full procedures belong in skills/docs, but short triggers must remain always-on when they cause the agent to load the right on-demand layer.
2. Size targets are secondary. Optimizing bytes by deleting safety-critical triggers is a regression.
3. Before editing protected memory files, prepare diffs, get explicit approval, create backups, write, reread, scan for token-like strings, verify referenced skills, update/close/archive plans.
4. After SOUL changes, do not claim current-session behavior changed until fresh session/reset/restart verification; prompt snapshots may be cached.
