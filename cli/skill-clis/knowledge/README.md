# knowledge CLI

Read-only evidence collector for the local Hermes knowledge architecture.

The CLI is designed for agent workflows: stable JSON envelopes, deterministic
local audits, and no hidden writes to docs, memory, skills, config, cron, or
credentials.

## Install

```bash
make install-local
command -v knowledge
knowledge --help
knowledge --json doctor
```

This project uses only the Python standard library.

## JSON Policy

With `--json`, stdout is always an envelope:

```json
{
  "ok": true,
  "command": "plans audit",
  "data": {}
}
```

Errors are emitted to stderr:

```json
{
  "ok": false,
  "error": {
    "type": "read_error",
    "message": "Cannot read ...",
    "details": "..."
  }
}
```

Secret scans report pattern names, paths, and line numbers only. Matched secret
values are intentionally omitted.

## Paths

Defaults:

- docs root: `~/docs`
- Hermes home: `~/.hermes`
- memory DB: `~/.hermes/memory_store.db`

Override paths:

```bash
knowledge --json --docs-root /path/to/docs docs inventory
knowledge --json --hermes-home /path/to/.hermes memory metrics
```

## Commands

Offline path check:

```bash
knowledge --json doctor
```

Optional local Hermes check:

```bash
knowledge --json doctor --check-hermes
```

Companion skill contract check:

```bash
knowledge --json skill companion
knowledge skill companion --format md
knowledge --json skill companion --path /path/to/knowledge-cli/SKILL.md
```

This command is intentionally read-only and does not dump the full skill body. It reports companion path, metadata, a content hash, contract booleans, gaps, and a recommended command sequence for agents.

Docs inventory:

```bash
knowledge --json docs inventory
knowledge --json docs inventory --max-depth 2
```

Docs audit:

```bash
knowledge --json docs audit
```

Plans:

```bash
knowledge --json plans inventory
knowledge --json plans audit
```

Memory metrics:

```bash
knowledge --json memory metrics
knowledge --json memory metrics --db ~/.hermes/memory_store.db
```

Secret scan:

```bash
knowledge --json scan secrets --path ~/docs
```

Distillation candidates:

```bash
knowledge --json distill candidates --input snippets.txt
knowledge distill candidates --input snippets.txt --format md
```

By default, `distill candidates` uses an offline heuristic and does not call
Ollama Cloud or any model API. Live model extraction requires an explicit flag:

```bash
knowledge --json distill candidates --input snippets.txt --live-models
```

Aggregate report:

```bash
knowledge report --all --format md
knowledge --json report --all
```

## Non-Goals

The first version intentionally does not expose:

- `fix`
- `clean`
- `memory remove`
- automatic edits to `USER.md`, `MEMORY.md`, `SOUL.md`
- cron/config/fact_store mutations

The CLI gathers evidence. The agent decides what to change and asks for approval
when durable state would be mutated.
