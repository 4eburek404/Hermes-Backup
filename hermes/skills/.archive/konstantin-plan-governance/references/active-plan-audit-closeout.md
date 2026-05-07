# Active plan audit and closeout

Use this when Konstantin asks whether active plans may already be complete (e.g. “Смотри активные планы. По одному проверяй, может там уже все выполнено?!”).

## Procedure

1. Load `konstantin-plan-governance` and read `/home/konstantin/docs/plans/README.md` before mutating plans.
2. Inventory only root active plans (`/home/konstantin/docs/plans/*.md`, excluding `README.md`). Capture each plan’s `Current status`, `Steps`, and `Verification` sections.
3. For each plan, verify against live evidence rather than trusting the plan status:
   - code indicators: functions, parser branches, schemas, tests, removed legacy commands;
   - skill/runbook indicators: current workflow mentions, absence of deprecated commands;
   - live commands: targeted unit tests, syntax checks, smoke CLI/API calls;
   - process/config state only if relevant to the plan’s completion criteria.
4. Classify each plan:
   - **done**: every meaningful step/verification criterion is satisfied or has a dated source-side caveat;
   - **active**: at least one material blocker remains;
   - **superseded/cancelled**: only with explicit evidence and note.
5. For done plans, mutate before reporting:
   - mark checkboxes in `## Steps` and `## Verification` done when evidence supports them;
   - set first status line to `Current status: done`;
   - add a dated `## Notes` audit note listing exact evidence and commands;
   - move to `archive/<year>/done/`.
6. For active plans, update the plan with a dated note: what was verified, what is already done, and the exact remaining blockers. Do not archive.
7. Verify the ledger after mutation:
   - root contains only `README.md` plus active `planned|in_progress|blocked` plans;
   - archived closeouts have `Current status: done`;
   - required sections remain present;
   - secret-risk scan returns zero hits.
8. Final report should be short and decision-oriented: closed/archived, still active, verification results, caveats.

## Evidence examples from 2026-05-05

- Flights CLI closeout used both offline tests and live smoke:
  - `PYTHONPATH=/home/konstantin/code/clis/flights python3 -m unittest discover -s tests -v` → 30 tests passed.
  - `python3 -m py_compile flights_cli/__main__.py tests/test_offline.py` → passed.
  - `flights --json kb-search SVX MOW --depart-date 2026-07-19 --only-carrier SU --direct-only --limit 20 --timeout 90` → `ok=true`, `offer_count=11`.
- Legacy command removal was verified by positive and negative CLI checks:
  - `flights --help` lists `kb-search` and not `su-flights`.
  - `flights su-flights --help` exits non-zero with argparse `invalid choice`.
- Hermes guardrail closeout used targeted tests and code-path checks:
  - helper in `tools/approval.py`;
  - guards wired from `tools/file_tools.py` and `tools/memory_tool.py`;
  - `python -m pytest tests/tools/test_protected_context_file_guard.py -q -o addopts=` → 6 passed.

## Pitfalls

- Do not close a plan just because its status says `in_progress` or an earlier note says DONE for a phase. Verify every remaining blocker.
- Do not leave completed plans in root after closeout.
- Do not rewrite the historical archive unless the user explicitly asks; focus on active root ledger.
- Do not preserve secrets, tokens, raw logs, or full transcripts in audit notes. Redact as `[REDACTED]` if encountered.
