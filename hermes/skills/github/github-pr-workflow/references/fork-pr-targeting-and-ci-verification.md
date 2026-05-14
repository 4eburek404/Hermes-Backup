# Fork PR targeting and CI verification

Use when pushing a local branch and opening a PR from a fork or a checkout with both `origin` and `upstream`, especially when the worktree has unrelated dirty files.

## Why this exists

In forked checkouts, bare `gh repo view` / `gh pr create` can resolve the canonical upstream repository instead of the push remote. The safe source of truth for a PR opened from the current branch is the Git remote you actually push to, normally `origin`. Always pass `--repo` explicitly and verify base/head after creation.

## Safe sequence

1. Prove local provenance and preserve unrelated work:

```bash
cd /path/to/repo
git branch --show-current
git rev-parse --short=12 HEAD
git remote -v
git remote show origin | sed -n 's/.*HEAD branch: //p'
git status --short --branch --untracked-files=all
git diff --cached --name-status
```

If the worktree is dirty, map the dirty paths. Stage/commit only the task scope; do not use broad add-all commands in a dirty worktree unless the requested scope is the whole repo.

2. Derive the PR repository from the push remote, not from bare `gh repo view`:

```bash
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=${OWNER_REPO%%/*}
BRANCH=$(git branch --show-current)
printf 'owner_repo=%s\nowner=%s\nbranch=%s\n' "$OWNER_REPO" "$OWNER" "$BRANCH"
gh repo view "$OWNER_REPO" --json nameWithOwner,defaultBranchRef,url
```

3. Push and verify that the remote branch points to local `HEAD`:

```bash
git push -u origin HEAD
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin "refs/heads/$BRANCH" | awk '{print $1}')
printf 'local=%s\nremote=%s\n' "$LOCAL" "$REMOTE"
test "$LOCAL" = "$REMOTE"
```

4. Check for an existing PR before creating a new one:

```bash
gh pr list --repo "$OWNER_REPO" --head "$BRANCH" --state open \
  --json number,url,title,baseRefName,headRefName
```

If there is no open PR, create one with explicit repo/head/base:

```bash
gh pr create --repo "$OWNER_REPO" \
  --base main \
  --head "$OWNER:$BRANCH" \
  --title "feat(scope): short title" \
  --body "$(cat /tmp/pr-body.md)"
```

5. Verify the PR object, not just command success:

```bash
gh pr view <number> --repo "$OWNER_REPO" \
  --json number,url,state,baseRefName,headRefName,headRepositoryOwner,mergeable,isDraft,commits,statusCheckRollup \
  --jq '{number,url,state,baseRefName,headRefName,headOwner:.headRepositoryOwner.login,mergeable,isDraft,commits:[.commits[].oid],checks:[.statusCheckRollup[]? | {name:.name,status:.status,conclusion:.conclusion}]}'
```

Confirm:

- `baseRefName` is the requested base, usually `main`.
- `headRefName` is the pushed branch.
- `headOwner` is the fork owner when using a fork.
- PR commits include the pushed `HEAD`.
- `mergeable` is not conflicted.

6. Watch CI, but do not overclaim on timeouts:

```bash
timeout 180 gh pr checks <number> --repo "$OWNER_REPO" --watch || true
gh pr view <number> --repo "$OWNER_REPO" --json statusCheckRollup,mergeable,state,url \
  --jq '{url,state,mergeable,checks:[.statusCheckRollup[]? | {name:.name,status:.status,conclusion:.conclusion}]}'
```

If the watch command times out while checks are still running, report exactly which checks passed, failed, and remain pending. A timeout with pending checks is not itself a CI failure. If a check failed, inspect the failed log and fix the named cause; for `check-attribution` / `AUTHOR_MAP`, use `references/check-attribution-author-map.md`.

## Report shape

Keep the final chat report short:

- PR URL and number.
- Branch, remote, pushed SHA.
- Base/head verification.
- Mergeability.
- Checks: passed/failed/pending.
- Dirty worktree paths that remain unrelated and intentionally uncommitted.

## Pitfalls

- Bare `gh repo view` may show the upstream repo while `origin` points to a fork. Always pass `--repo "$OWNER_REPO"` after deriving it from the push remote.
- `gh pr create` can create against the wrong repository or fail misleadingly if a PR already exists. Check `gh pr list --repo ... --head ...` first.
- A new push invalidates or supersedes old check runs. Re-read the current PR `statusCheckRollup` after every push.
- CI `check-attribution` is a metadata gate, not a unit-test failure. Fix `scripts/release.py` `AUTHOR_MAP` with a scoped commit.
- In a dirty worktree, a successful push/PR does not make unrelated dirty files safe to ignore forever. Mention them separately; do not stage or revert them as part of the PR task.
