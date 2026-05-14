# Resolving PR conflicts in a dirty worktree

Use this when a pushed feature branch has PR conflicts and the repo also contains unrelated dirty files. Goal: make the PR mergeable without staging/reverting unrelated work or force-pushing unless explicitly chosen.

## Pattern

1. Verify live provenance first:

```bash
git fetch origin
git branch --show-current
git status --short --branch --untracked-files=all
git rev-list --left-right --count HEAD...origin/main
git diff --name-status HEAD..origin/main
```

2. If the feature branch is already pushed, prefer a normal merge commit over rebase unless the user explicitly asks for history rewrite:

```bash
git merge --no-ff --no-commit origin/main
```

3. Resolve only actual conflict files (`git diff --name-only --diff-filter=U`). Keep both sides' intended behavior when conflicts combine independent changes. For documentation conflicts, merge the two rule sets instead of choosing one side blindly.

4. Stage only the intended conflict/base-update scope. In a dirty worktree, do **not** use broad add-all commands unless the task scope is truly the whole repo.

```bash
git add -- <resolved-paths>  # example after user-approved conflict fix
git diff --cached --name-status
git diff --cached --check
```

5. Run domain-specific verification before committing. For skill-owned CLIs, use `PYTHONDONTWRITEBYTECODE=1`, focused regression tests, full suite, doctor/smoke command, `git diff --check`, and generated-artifact cleanup.

6. If the repo has an audit helper, run both target-scope audit and changed-file audit. Interpret changed-file audit by scope: unrelated dirty files may still have findings, but they must not be reported as regressions for the PR-conflict task.

7. Commit and push, then verify remote SHA:

```bash
git commit -m "chore(<scope>): resolve main merge conflicts"  # example after verification
git push origin HEAD
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/$(git branch --show-current) | awk '{print $1}')
test "$LOCAL" = "$REMOTE"
```

## Pitfalls

- `git status` after a merge shows upstream file changes as staged; still verify they came from the base branch and are in task scope.
- A clean target path can coexist with unrelated dirty files. Report both separately.
- `audit --changed` may fail because of unrelated dirty paths. Parse/summarize by path scope rather than printing raw scanner evidence or treating all findings as blockers.
- Do not expose tokens or credential-shaped scanner evidence in conflict reports; summarize counts/classes/paths only.
- If docs/plans live outside the git repo, update them for continuity but do not include them in the commit unless they are in the repo.
