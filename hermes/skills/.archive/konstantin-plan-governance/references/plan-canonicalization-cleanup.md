# Plan canonicalization cleanup reference

Use when Konstantin asks to "update plans", "bring plans to canonical", or clean `/home/konstantin/docs/plans/` root.

Session-derived pattern from 2026-05-05:

1. Load `konstantin-plan-governance` and read `/home/konstantin/docs/plans/README.md` before mutation.
2. Inventory root only first: `*.md` directly under `/home/konstantin/docs/plans/`, excluding `README.md`. Do not treat archive drift as blocking current root cleanup unless the user explicitly asks for archive normalization.
3. For each root plan:
   - active work stays in root with `Current status: planned|in_progress|blocked`;
   - completed/cancelled/superseded work gets a canonical status and moves to `archive/<year>/<status>/`;
   - files that are implementation notes or architecture notes but are intended active work should be reshaped into full plans, not deleted.
4. Canonical active plan sections to verify:
   - `## Goal`
   - `## Context`
   - `## Non-goals`
   - `## Steps`
   - `## Verification`
   - `## Risks / pitfalls`
   - `## Status`
   - `## Notes`
5. The first non-empty line after `## Status` must be exactly one of:
   - `Current status: planned`
   - `Current status: in_progress`
   - `Current status: blocked`
   - archived only: `Current status: done|cancelled|superseded`
6. Preserve original substance when normalizing:
   - convert freeform task lists to checkboxes;
   - move `Scope`, `Architecture`, `Tech Stack`, and current-state notes into `Context`;
   - convert "not doing" text into `Non-goals`;
   - convert commands/expected outputs into `Verification`;
   - add `Risks / pitfalls` and `Notes` only with concise durable value.
7. Do not imply implementation progress merely because a plan was normalized. If only the document shape changed, write that in `Notes`.
8. After mutation, run a verification pass that checks root layout, required sections, exact status line, archived moved files, and secret-risk patterns. Report exact paths changed and moved.

Minimal Python verification skeleton:

```python
from pathlib import Path
import re
root = Path('/home/konstantin/docs/plans')
allowed = {'planned', 'in_progress', 'blocked'}
required = ['Goal','Context','Non-goals','Steps','Verification','Risks / pitfalls','Status','Notes']
errors = []
for p in sorted(root.glob('*.md')):
    if p.name == 'README.md':
        continue
    text = p.read_text(encoding='utf-8')
    m = re.search(r'(?ms)^## Status\s*\n([^\n]+)', text)
    status_line = m.group(1).strip() if m else None
    sm = re.fullmatch(r'Current status: (planned|in_progress|blocked|done|cancelled|superseded)', status_line or '')
    status = sm.group(1) if sm else None
    if status not in allowed:
        errors.append(f'{p.name}: bad active status {status_line!r}')
    missing = [sec for sec in required if not re.search(rf'^## {re.escape(sec)}\s*$', text, re.M)]
    if missing:
        errors.append(f'{p.name}: missing {missing}')
print('\n'.join(errors) or 'OK')
```

Pitfalls:

- Do not mass-rewrite historical archive plans during a root canonicalization unless asked; archived legacy status formats are lower priority and can create unnecessary churn.
- Do not leave `Current status: in_progress (commentary...)`; keep commentary in `Notes`, not on the machine-readable status line.
- Do not move active but malformed notes out of root; normalize them into active plans if the user asked for canonical plans.
- If a cleanup plan itself is actively being executed, move its status from `planned` to `in_progress` and record the performed cleanup in `Notes`.
