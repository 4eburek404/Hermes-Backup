# Knowledge CLI Maintenance Notes

Use this reference when modifying the bundled read-only `knowledge` CLI under `skills/note-taking/knowledge-architecture/cli/` or its companion skill.

## 2026-05-08 P0 maintenance lessons

Scope that proved safe:
- CLI source: `skills/note-taking/knowledge-architecture/cli/knowledge_cli/__main__.py`
- Offline tests: `skills/note-taking/knowledge-architecture/cli/tests/test_offline.py`
- CLI README: `skills/note-taking/knowledge-architecture/cli/README.md`
- Companion skill: `/home/konstantin/.codex/skills/knowledge-cli/SKILL.md`
- Plan control surface: `/home/konstantin/docs/plans/YYYY-MM-DD-knowledge-cli-p0-refactor.md`

Do not edit protected core files (`USER.md`, `MEMORY.md`, `SOUL.md`) as part of CLI maintenance unless the user explicitly approves a shown diff.

## Regression cases to preserve

When fixing `knowledge` CLI correctness, add or maintain tests for:
- Bundled worker path is derived from the skill source tree, not stale `~/.hermes/skills/...`.
- `memory metrics` finds root `~/.hermes/SOUL.md` and still supports fallback paths.
- SQLite memory DB is opened read-only via `file:` URI with `mode=ro` and `uri=True`.
- `memory policy audit` never exposes fact content or matched secret values; it reports fact IDs, hashes, counts, and finding classes only.
- Test fixtures for redaction/stale-path detection should construct secret-shaped strings and obsolete paths from safe fragments instead of embedding scanner-trigger literals directly; this keeps `audit_skill.py` clean while preserving no-leak assertions.
- Companion skill frontmatter supports folded/literal YAML descriptions (`>-`, `|`) instead of treating them as literal values.
- `report --all` includes docs audit findings, secret-scan counts, and plan-finding counts.
- `report --all --max-depth N` respects `--max-depth`; this was caught by independent review after the first implementation.
- Secret scan outputs only pattern/path/line/count metadata, never matched secret values.
- Any CLI command example added to `SKILL.md`, README, or references is smoke-tested with the real parser. In the P1 shrink pass, independent review caught an invalid example: `knowledge --json scan secrets /home/konstantin/docs`; the supported syntax is `knowledge --json scan secrets --path /home/konstantin/docs`.

## 2026-05-08 P2 first-slice additions

The first P2 expansion deliberately stayed read-only and deterministic:
- `knowledge --json paths audit` — canonical path presence, obsolete live path existence, no file-body reads.
- `knowledge --json skill audit` — main `SKILL.md` size/section/artifact/stale-marker metadata, no full body dump.
- `knowledge --json distill worker-check` — worker script existence and `run_distillation(text)` contract, no import and no model calls.
- `knowledge --json report --all` now includes compact rollups for paths, skill, and distillation worker health.

Regression tests should preserve that these commands do not expose memory file contents or secret-like values.

## 2026-05-08 P3 memory policy first-slice

The P3 first slice added one more deterministic read-only check:
- `knowledge --json memory policy audit` — opens `memory_store.db` read-only and reports stale path references, secret-like facts, procedural facts, volatile stale facts, exact duplicate facts, and low-trust unhelpful facts without exposing fact content.
- `knowledge --json report --all` now includes a `memory_policy` rollup.

Regression tests should preserve read-only SQLite URI use, redaction/no content leak, and `report --all` inclusion.

## Verification recipe

Run with bytecode disabled and clean generated artifacts afterwards:

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli
PYTHONDONTWRITEBYTECODE=1 make test
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

From repo root:

```bash
cd /home/konstantin/.hermes/hermes-agent
git diff --check -- skills/note-taking/knowledge-architecture/cli/README.md skills/note-taking/knowledge-architecture/cli/knowledge_cli/__main__.py skills/note-taking/knowledge-architecture/cli/tests/test_offline.py
PYTHONDONTWRITEBYTECODE=1 python3 skills/software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill knowledge-architecture --json
```

Smoke the CLI from source and installed wrapper:

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json doctor
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json paths audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json skill companion
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json skill audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json distill worker-check
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json memory policy audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json docs audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json report --all
knowledge --json doctor
```

Then remove generated bytecode if tests created it, scoped only to the knowledge skill tree:

```bash
python3 - <<'PY'
from pathlib import Path
import shutil
root = Path('/home/konstantin/.hermes/hermes-agent/skills/note-taking/knowledge-architecture')
for path in list(root.rglob('__pycache__')):
    shutil.rmtree(path)
for path in list(root.rglob('*.pyc')):
    path.unlink(missing_ok=True)
PY
```

## Independent review pitfall

After implementation, run an independent diff review or explicitly simulate one. In the 2026-05-08 pass, review caught a silent option regression: replacing `docs_inventory_data(..., max_depth=args.max_depth)` with `docs_audit_data(docs_root)` caused `report --all --max-depth 1` to scan deeper files. Fix by threading `max_depth` through the audit function and adding a focused regression test.

## Reporting

Final reports should include:
- touched files;
- what was fixed;
- verification commands and pass/fail summary;
- remaining baseline findings, clearly separated from new regressions;
- whether commit/push was intentionally not done.
