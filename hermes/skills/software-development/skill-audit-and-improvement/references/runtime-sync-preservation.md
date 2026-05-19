# Runtime Sync Preservation Pattern

Use this note when planning or performing a source-to-runtime skill sync, especially when the proposed command uses `rsync --delete` from a git skill tree into the runtime skill directory.

## Pattern

1. Treat the git branch, expected HEAD, clean tree, and ahead/behind state as the provenance gate. Stop before any copy/sync if the gate fails.
2. Build source and runtime manifests before syncing. Exclude generated artifacts only: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.DS_Store`, `*.tmp`, and `*.log`.
3. Classify differences before recommending `rsync --delete`:
   - LOW: source and runtime match, or differ only by generated artifacts.
   - MEDIUM: runtime source files differ, but the differences are expected branch cleanup.
   - HIGH: runtime has source files absent from git, runtime-only edits, or unexpected source differences.
4. If runtime has source files absent from git, inspect them before sync. Do not assume they are disposable just because the branch is newer.
5. Preserve durable runtime-only references/scripts/templates in git first, preferably as a separate small commit, then rerun sync planning against the new HEAD.
6. Treat preservation as iterative: after each preservation commit and push, rerun the full manifest compare from scratch. If another runtime-only source file appears, classify the plan as HIGH again and stop before sync; do not assume the first preserved file was the only blocker.
7. For nested checkouts that store skills under `hermes/skills/`, verify static self-audit with a temporary top-level `skills/` repo. Keep it static unless the task explicitly allows runtime execution.
8. After future sync, verify generated artifacts, unit tests, syntax/JSON checks, and static self-audit. Confirm `cli_contract.execution_performed=false` when no deep CLI or audited skill CLI execution is in scope.

## Pitfalls

- Do not let a planning step create backups, run `rsync`, restart Hermes, push, or execute audited skill CLIs unless explicitly authorized.
- Do not use `rsync --delete` while runtime-only source files are unexplained; it can delete durable knowledge that has not yet been preserved in git.
- Do not collapse “no blockers” into “no warnings”; warnings can be acceptable for sync readiness only when report validation passes and blockers are zero.
- Do not report the old expected HEAD after a preservation commit. Capture HEAD before and after, then rerun sync planning against the new expected commit.
