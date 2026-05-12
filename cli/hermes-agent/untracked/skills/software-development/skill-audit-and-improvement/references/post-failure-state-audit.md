# Post-failure state audit

Use this when a task failed or went off the rails and you need to understand what was *actually* done before deciding on rollback or continuation.

## Read-only snapshot to capture

Run these from the live repo root:

```bash
pwd
git status --short --branch --untracked-files=all
git diff --stat
git diff --name-only
```

Then inspect only the files that exist in the repo and are relevant to the failed task:

- analyzer scripts
- tests / fixtures
- docs notes
- session-index artifacts, if present

## What to treat as non-errors

- `request_dump_*` files may be absent. Absence is normal and should not be reported as a failure.
- A repo-local `find .` result that shows `.git/logs` is only Git metadata; it is not the user's real `~/.hermes` runtime logs.
- Do not infer the presence of real `~/.hermes` session/log files from repository paths alone.

## What to call out explicitly

- untracked files vs tracked diffs
- whether any runtime-affecting files were touched
- whether the task appears partial, scaffold-only, or hallucinated
- whether rollback is actually needed, or the tree is already clean enough to continue

## Decision rule

If the tree shows only scaffolding and no runtime/config changes, prefer continuation from the narrow baseline rather than rollback.
If tracked diffs exist in runtime/config/state files, stop and assess rollback scope first.