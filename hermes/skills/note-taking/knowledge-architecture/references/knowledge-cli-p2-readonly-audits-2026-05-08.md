# Knowledge CLI P2 Read-only Audits — 2026-05-08

## Purpose

Capture the reusable pattern from the P2 `knowledge` CLI slice: move recurring manual knowledge-architecture checks from prose into deterministic, read-only CLI evidence while keeping human approval and semantic judgment outside the CLI.

## Implemented pattern

Added three read-only audit surfaces and report rollups:

```bash
knowledge --json paths audit
knowledge --json skill audit
knowledge --json distill worker-check
knowledge --json report --all
```

Design boundary:

- `paths audit` reports canonical path presence/type and stale-path existence; it does not read sensitive file contents.
- `skill audit` reports health booleans/counts/findings for the main `SKILL.md`, required sections, read-only contract, stale-path markers, and generated artifacts; it does not dump full skill text.
- `distill worker-check` is static only: no import of the worker, no live model calls, no `ollama run`, no `ollama pull`; it exposes `live_model_calls: false`.
- `report --all` includes compact rollups for paths, skill, and worker health alongside docs/plans/memory/secrets checks.

## Reusable implementation lessons

- Keep skill-owned CLIs as evidence collectors, not editors or permission sources.
- Prefer deterministic checks that can return counts/classes/locations without preserving secret values.
- Add tests before implementation when introducing CLI contracts, including no-content-dump and no-live-call assertions.
- For skill-owned CLI tests/smokes, always use:

```bash
PYTHONDONTWRITEBYTECODE=1
```

and clean `__pycache__` / `*.pyc` before final audit.

- Verify both source invocation and installed wrapper when the CLI has an entry point:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json paths audit
knowledge --json paths audit
```

- Separate intended skill findings from unrelated dirty-tree baseline. `audit_skill.py --changed --json` may fail for unrelated skill-library files; summarize by file/class and do not treat it as a P2 regression unless intended files appear.

## Verification bundle used

Minimum useful bundle for future `knowledge` CLI read-only audit slices:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 - <<'PY'
from pathlib import Path
import ast
ast.parse(Path('knowledge_cli/__main__.py').read_text(encoding='utf-8'))
print('syntax_ok')
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json paths audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json skill audit
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json distill worker-check
PYTHONDONTWRITEBYTECODE=1 python3 -m knowledge_cli --json report --all
knowledge --json paths audit
knowledge --json skill audit
knowledge --json distill worker-check
git diff --check -- skills/note-taking/knowledge-architecture/
python3 ../../software-development/skill-audit-and-improvement/scripts/audit_skill.py --skill knowledge-architecture --json
```

Then remove any generated artifacts and confirm zero `__pycache__` / `*.pyc` under the skill tree.

## Final observed baseline from this slice

- Unit tests: 15/15 passing.
- `paths audit`, `skill audit`, `distill worker-check`: findings `0` for intended scope.
- `distill worker-check`: `live_model_calls: false`.
- `audit_skill.py --skill knowledge-architecture --json`: issues/warnings `0`.
- Existing docs audit baseline remained: 23 findings, including `secret_risk: 5`; secret values were not printed.

## When to reuse this reference

Use this when extending `knowledge` CLI with another deterministic read-only audit such as memory policy audit, plans policy audit, local CLI audit, stale-reference scans, or worker doctor enhancements.
