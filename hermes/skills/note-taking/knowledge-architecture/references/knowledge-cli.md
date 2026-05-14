# Local `knowledge` CLI

Session-derived reference for using Konstantin's local read-only knowledge architecture CLI.

## Verified locations

- CLI project: `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli/`
- Installed command: `/home/konstantin/.local/bin/knowledge`
- Codex companion skill: `/home/konstantin/.codex/skills/knowledge-cli/SKILL.md`
- Main Hermes companion/umbrella: this `knowledge-architecture` skill should treat the CLI as the first deterministic evidence collector.

## Purpose

`knowledge` is a read-only evidence collector for the local Hermes knowledge architecture. It gathers deterministic local state before an agent proposes edits to docs, plans, memory, skills, config, or cron.

It is intentionally not an editor. CLI output is evidence, not permission to mutate durable state.

## Safe first commands

```bash
command -v knowledge
knowledge --json doctor
knowledge --json report --all
```

Targeted reads:

```bash
knowledge --json docs inventory
knowledge --json docs audit
knowledge --json plans inventory
knowledge --json plans audit
knowledge --json paths audit
knowledge --json skill audit
knowledge --json distill worker-check
knowledge --json memory metrics
knowledge --json memory policy audit
knowledge --json scan secrets --path /home/konstantin/docs
knowledge --json distill candidates --input snippets.txt
```

Distillation is offline by default. Live model calls require explicit opt-in:

```bash
knowledge --json distill candidates --input snippets.txt --live-models
```

## Current verified behavior

- JSON stdout uses stable envelopes: `{ "ok": true, "command": ..., "data": ... }`.
- Error envelopes are emitted to stderr.
- `memory metrics` reports counts/consistency and memory file pressure without dumping fact content.
- `memory policy audit` reports fact IDs, hashes, counts, and finding classes for stale paths, secret-like facts, procedural facts, volatile stale facts, duplicates, and low-trust unhelpful facts; it opens SQLite read-only and omits fact content.
- `scan secrets` reports pattern names, paths, and line numbers only, not matched secret values.
- `report --all` aggregates doctor/paths/docs/plans/memory/memory-policy/secrets/skill/worker checks.
- `paths audit` reports canonical path presence and obsolete live path existence without reading file contents.
- `skill audit` reports router-size pressure, missing `## When to Use`, generated artifacts, and stale path markers without dumping full skill bodies.
- `distill worker-check` checks the worker contract without importing it or calling models.
- Tests live at `/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli/tests/test_offline.py` and cover plan drift, no memory content leak, offline distillation default, P0 path regressions, P2 deterministic audit rollups, and P3 memory policy read-only/redaction behavior.

## Verification recipe

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli
make test
knowledge --json doctor
knowledge --json report --all
```

Expected test result as of 2026-05-08 P3: `18 passed` under `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests/test_offline.py`.

## Pitfalls

1. Do not infer absence from one search helper returning zero results. For important existence checks, verify with `stat`, `find`, or Python `Path.rglob` against the canonical repo path.
2. Do not use `--hermes-home` against Docker/guest Hermes unless the user explicitly asks. Default CLI target is main Hermes (`/home/konstantin/.hermes`).
3. Do not treat `knowledge --json report --all` findings as approval to edit files. Apply normal knowledge-architecture mutation rules.
4. `doctor --check-hermes` and `distill --live-models` are explicit opt-in checks; do not run them when the user requested read-only/offline local inspection only.
