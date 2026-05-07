# Local `knowledge` CLI

Session-derived reference for using Konstantin's local read-only knowledge architecture CLI.

## Verified locations

- CLI project: `/home/konstantin/code/clis/knowledge/`
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
knowledge --json memory metrics
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
- `scan secrets` reports pattern names, paths, and line numbers only, not matched secret values.
- `report --all` aggregates doctor/docs/plans/memory/secrets checks.
- Tests live at `/home/konstantin/code/clis/knowledge/tests/test_offline.py` and cover plan drift, no memory content leak, and offline distillation default.

## Verification recipe

```bash
cd /home/konstantin/code/clis/knowledge
make test
knowledge --json doctor
knowledge --json report --all
```

Expected test result as of 2026-05-03: `Ran 5 tests ... OK`.

## Pitfalls

1. Do not infer absence from one search helper returning zero results. In this session `search_files` missed `/home/konstantin/code/clis/knowledge`; direct filesystem traversal found it. For important existence checks, verify with `stat`, `find`, or Python `Path.rglob`.
2. Do not use `--hermes-home` against Docker/guest Hermes unless the user explicitly asks. Default CLI target is main Hermes (`/home/konstantin/.hermes`).
3. Do not treat `knowledge --json report --all` findings as approval to edit files. Apply normal knowledge-architecture mutation rules.
4. `doctor --check-hermes` and `distill --live-models` are explicit opt-in checks; do not run them when the user requested read-only/offline local inspection only.
