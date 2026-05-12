# Dirty worktree checkpoint commit pattern

Use this when the repository already has unrelated modified/untracked files and you need a safe checkpoint commit for a narrow baseline or doc update.

## Pattern
1. Inspect scope first:
   - `git status --short --branch --untracked-files=all`
   - `git diff --stat`
   - `git diff --name-only`
2. Verify the worktree contains only the intended files for the checkpoint commit.
3. Run the requested safety checks before staging:
   - syntax/compile checks
   - relevant focused tests
   - secret/token grep on the diff
4. Stage only the allowlisted files; never use broad add-all in a dirty tree.
5. Confirm the staged set with:
   - `git diff --cached --stat`
   - `git diff --cached --name-only`
   - `git diff --cached | grep -Ei 'api[_-]?key|secret|password|authorization|bearer' || true`
6. Commit only after the staged diff matches the expected checkpoint scope.
7. After commit, verify the commit itself, not just the worktree:
   - `git diff-tree --no-commit-id --name-only -r HEAD`
   - `git log -1 --oneline`
   Compare the committed file list and commit message against the user's requested checkpoint label/scope before reporting success.
8. After commit, re-run `git status` and report any remaining untracked files explicitly.

## Pitfalls
- After a model switch, context compaction, todo carry-over, or interrupted commit flow, re-anchor on the latest explicit user request before staging or reporting. Compare the requested release/checkpoint label, commit message, allowlisted files, and test list against the live staged/committed diff. A final report whose checkpoint name or file list comes from an earlier turn is a workflow failure even if Git commands succeeded.
- Backup copies (`*.backup*`, `*.bak*`, `*.orig`, `*.base`, `*.step*`) often appear after iterative repairs. Leave them untracked unless the user explicitly asks to clean them up.
- If an allowlisted tracked file shows as deleted (` D path`) during the pre-commit snapshot, stop before staging/committing. Treat it as a live-state regression even if the previous turn said tests passed: inspect the deletion diff, restore or reconstruct only that expected file in scope, then rerun the full requested validation sequence and allowlist check before `git add`.
- If a required file is tracked in the repo but unchanged, it should not be added just because it is mentioned in a task description.
- If the user explicitly allowlists a test file for the checkpoint but `pytest <that-file>` reports `no tests ran` and the file is absent/untracked, stop the validation sequence, inspect the surrounding tests/source, create only that allowlisted test file if it is clearly part of the requested scope, then rerun the full requested compile/test/secret-grep sequence before staging. Do not commit a checkpoint whose requested regression test never collected.
- A passing checkpoint commit is not proof that the whole repo is clean; report remaining untracked work separately.
- If the user’s commit scope includes docs plus code, make sure all expected docs are actually tracked before staging; do not assume a path exists from the task description alone.

## Verification examples
- `python -m py_compile <file>` for Python syntax baselines.
- `pytest <focused-test-file> -q` for the smallest relevant test slice.
- `git diff --cached --name-only` before commit, and `git diff-tree --no-commit-id --name-only -r HEAD` after commit.
