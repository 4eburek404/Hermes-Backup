---
name: github-pr-workflow
description: "Use when managing GitHub PR lifecycle work: branch, commit, push, open PRs, monitor/fix CI, merge, or resolve PR conflicts while preserving dirty worktree scope."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Automation, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

## Overview

Complete guide for managing the PR lifecycle. Each section shows the `gh` way first, then the `git` + `curl` fallback for machines without `gh`. The workflow is scoped for real repositories with forks, dirty worktrees, CI gates, and external side effects: verify provenance first, stage only intended paths, pass explicit repository/base/head to GitHub commands, and verify remote SHA/PR/check state before reporting success.

## When to Use

Use this skill when the user asks to:

- create, push, or update a GitHub branch;
- open, view, update, or merge a PR;
- monitor or fix PR CI/check failures;
- resolve PR conflicts against `main`/base branches;
- preserve unrelated dirty worktree changes while committing or pushing a scoped change.

Do not use it for GitHub authentication setup alone; load `github-auth` for that. For code review of PR diffs, load `github-code-review` or `requesting-code-review` as appropriate.

## Prerequisites

- Authenticated with GitHub (see `github-auth` skill)
- Inside a git repository with a GitHub remote

### Quick Auth Detection

```bash
# Determine which method to use throughout this workflow
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="git"
  # Ensure we have a token for API calls
  if [ -z "$GITHUB_TOKEN" ]; then
    if [ -f ~/.hermes/.env ] && grep -q "^GITHUB_TOKEN=" ~/.hermes/.env; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    fi
  fi
fi
GITHUB_AUTH_HEADER="Bearer ${GITHUB_TOKEN}"
echo "Using: $AUTH"
```

### Extracting Owner/Repo from the Git Remote

Many `curl` commands need `owner/repo`. Extract it from the git remote:

```bash
# Works for both HTTPS and SSH remote URLs
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
echo "Owner: $OWNER, Repo: $REPO"
```

---

## 1. Branch Creation

This part is pure `git` — identical either way:

```bash
# Make sure you're up to date
git fetch origin
git checkout main && git pull origin main

# Create and switch to a new branch
git checkout -b feat/add-user-authentication
```

Branch naming conventions:
- `feat/description` — new features
- `fix/description` — bug fixes
- `refactor/description` — code restructuring
- `docs/description` — documentation
- `ci/description` — CI/CD changes

## 2. Making Commits

Use the agent's file tools (`write_file`, `patch`) to make changes, then commit. In a dirty worktree, stage only the intended paths and leave unrelated modified/untracked files alone.

```bash
# Inspect scope before staging
git status --short --branch --untracked-files=all

# Stage specific files only
git add src/auth.py src/models/user.py tests/test_auth.py

# Confirm exactly what will be committed
git diff --cached --name-status
git diff --cached --check

# Commit with a conventional commit message
git commit -m "feat: add JWT-based user authentication

- Add login/register endpoints
- Add User model with password hashing
- Add auth middleware for protected routes
- Add unit tests for auth flow"
```

Commit message format (Conventional Commits):
```
type(scope): short description

Longer explanation if needed. Wrap at 72 characters.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `perf`

## 3. Pushing and Creating a PR

### Resolve the target repository first

In forked checkouts, do not rely on bare `gh repo view` or bare `gh pr create`: `gh` can resolve the canonical upstream repo while `origin` is the fork you actually push to. Derive `OWNER_REPO` from the push remote and pass `--repo` explicitly to every `gh` PR command.

```bash
REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=${OWNER_REPO%%/*}
BRANCH=$(git branch --show-current)
gh repo view "$OWNER_REPO" --json nameWithOwner,defaultBranchRef,url
```

For the full dirty-worktree/fork flow, use `references/fork-pr-targeting-and-ci-verification.md`.

### Push the Branch (same either way)

```bash
git push -u origin HEAD
```

Verify that the remote branch points to the local commit before reporting push success:

```bash
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/$(git branch --show-current) | awk '{print $1}')
printf 'local=%s\nremote=%s\n' "$LOCAL" "$REMOTE"
test "$LOCAL" = "$REMOTE"
```

### Create the PR

**With gh:**

```bash
gh pr create \
  --repo "$OWNER_REPO" \
  --base main \
  --head "$OWNER:$BRANCH" \
  --title "feat: add JWT-based user authentication" \
  --body "## Summary
- Adds login and register API endpoints
- JWT token generation and validation

## Test Plan
- [ ] Unit tests pass

Closes #42"
```

Options: `--draft`, `--reviewer user1,user2`, `--label "enhancement"`, `--base develop`

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

curl -s -X POST \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/$OWNER/$REPO/pulls \
  -d "{
    \"title\": \"feat: add JWT-based user authentication\",
    \"body\": \"## Summary\nAdds login and register API endpoints.\n\nCloses #42\",
    \"head\": \"$BRANCH\",
    \"base\": \"main\"
  }"
```

The response JSON includes the PR `number` — save it for later commands.

To create as a draft, add `"draft": true` to the JSON body.

## 4. Monitoring CI Status

### Check CI Status

**With gh:**

```bash
# One-shot check
gh pr checks

# Watch until all checks finish (polls every 10s)
gh pr checks --watch
```

**With git + curl:**

```bash
# Get the latest commit SHA on the current branch
SHA=$(git rev-parse HEAD)

# Query the combined status
curl -s \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Overall: {data['state']}\")
for s in data.get('statuses', []):
    print(f\"  {s['context']}: {s['state']} - {s.get('description', '')}\")"

# Also check GitHub Actions check runs (separate endpoint)
curl -s \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/check-runs \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cr in data.get('check_runs', []):
    print(f\"  {cr['name']}: {cr['status']} / {cr['conclusion'] or 'pending'}\")"
```

### Poll Until Complete (git + curl)

```bash
# Simple polling loop — check every 30 seconds, up to 10 minutes
SHA=$(git rev-parse HEAD)
for i in $(seq 1 20); do
  STATUS=$(curl -s \
    -H "Authorization: ${GITHUB_AUTH_HEADER}" \
    https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['state'])")
  echo "Check $i: $STATUS"
  if [ "$STATUS" = "success" ] || [ "$STATUS" = "failure" ] || [ "$STATUS" = "error" ]; then
    break
  fi
  sleep 30
done
```

## 5. Auto-Fixing CI Failures

When CI fails, diagnose and fix. This loop works with either auth method.

If the failing check is `check-attribution` with `New contributor email(s) not in AUTHOR_MAP`, use `references/check-attribution-author-map.md`: add the requested `scripts/release.py` `AUTHOR_MAP` entry, verify locally, stage only that file, commit, push, and re-check the PR.

### Step 1: Get Failure Details

**With gh:**

```bash
# List recent workflow runs on this branch
gh run list --branch $(git branch --show-current) --limit 5

# View failed logs
gh run view <RUN_ID> --log-failed
```

**With git + curl:**

```bash
BRANCH=$(git branch --show-current)

# List workflow runs on this branch
curl -s \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  "https://api.github.com/repos/$OWNER/$REPO/actions/runs?branch=$BRANCH&per_page=5" \
  | python3 -c "
import sys, json
runs = json.load(sys.stdin)['workflow_runs']
for r in runs:
    print(f\"Run {r['id']}: {r['name']} - {r['conclusion'] or r['status']}\")"

# Get failed job logs (download as zip, extract, read)
RUN_ID=<run_id>
curl -s -L \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/logs \
  -o /tmp/ci-logs.zip
cd /tmp && unzip -o ci-logs.zip -d ci-logs && cat ci-logs/*.txt
```

### Step 2: Fix and Push

After identifying the issue, use file tools (`patch`, `write_file`) to fix it:

```bash
git add <fixed_files>
git commit -m "fix: resolve CI failure in <check_name>"
git push
```

### Step 3: Verify

Re-check CI status using the commands from Section 4 above. After every push, discard stale conclusions from previous runs and read the current PR `statusCheckRollup` again. If `gh pr checks --watch` is interrupted by a local timeout while checks remain `pending`/`in_progress`, report those checks as still running, not failed.

### Auto-Fix Loop Pattern

When asked to auto-fix CI, follow this loop:

1. Check CI status → identify failures
2. Read failure logs → understand the error
3. Use `read_file` + `patch`/`write_file` → fix the code
4. Stage only files touched by the fix, then `git commit -m "fix: ..." && git push`
5. Wait for CI → re-check status
6. Repeat if still failing (up to 3 attempts, then ask the user)

## 6. Resolving PR Conflicts

When the user asks to resolve PR conflicts on an already-pushed branch, first verify branch/base/dirty state and preserve unrelated work. In a dirty worktree, do **not** use broad `git add .`; stage only the conflict/base-update scope. Prefer `git merge --no-ff --no-commit origin/main` for pushed branches unless the user explicitly asks for rebase/history rewrite. After resolving, run domain-specific tests and diff checks, commit, push, and verify local/remote SHA match.

See `references/conflict-resolution-dirty-worktree.md` for the full dirty-worktree conflict-resolution pattern, including scoped audit interpretation.

## 6b. Opening a PR After Conflict Resolution

After resolving merge conflicts on a branch and pushing, you may need to open (or reopen) a PR. **Check for an existing PR first** — the push already updated it:

```bash
# Check for an existing PR on this branch before attempting creation
gh pr list --head <branch-name> --state open

# If a PR exists, the push already updated it — just verify:
gh pr view <number>
```

**Pitfall:** `gh pr create` on a branch that already has an open PR returns a misleading error like `"No commits between main and <branch>"` instead of suggesting you view the existing PR. Always check `gh pr list --head <branch>` first.

If no PR exists yet, proceed with Section 3 (`gh pr create`).

## 7. Merging

**With gh:**

```bash
# Squash merge + delete branch (cleanest for feature branches)
gh pr merge --squash --delete-branch

# Enable auto-merge (merges when all checks pass)
gh pr merge --auto --squash --delete-branch
```

**With git + curl:**

```bash
PR_NUMBER=<number>

# Merge the PR via API (squash)
curl -s -X PUT \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/merge \
  -d "{
    \"merge_method\": \"squash\",
    \"commit_title\": \"feat: add user authentication (#$PR_NUMBER)\"
  }"

# Delete the remote branch after merge
BRANCH=$(git branch --show-current)
git push origin --delete $BRANCH

# Switch back to main locally
git checkout main && git pull origin main
git branch -d $BRANCH
```

Merge methods: `"merge"` (merge commit), `"squash"`, `"rebase"`

### Enable Auto-Merge (curl)

```bash
# Auto-merge requires the repo to have it enabled in settings.
# This uses the GraphQL API since REST doesn't support auto-merge.
PR_NODE_ID=$(curl -s \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['node_id'])")

curl -s -X POST \
  -H "Authorization: ${GITHUB_AUTH_HEADER}" \
  https://api.github.com/graphql \
  -d "{\"query\": \"mutation { enablePullRequestAutoMerge(input: {pullRequestId: \\\"$PR_NODE_ID\\\", mergeMethod: SQUASH}) { clientMutationId } }\"}"
```

## 8. Complete Workflow Example

```bash
# 1. Start from clean main
git checkout main && git pull origin main

# 2. Branch
git checkout -b fix/login-redirect-bug

# 3. (Agent makes code changes with file tools)

# 4. Commit
git add src/auth/login.py tests/test_login.py
git commit -m "fix: correct redirect URL after login

Preserves the ?next= parameter instead of always redirecting to /dashboard."

# 5. Push
git push -u origin HEAD

# 6. Create PR (picks gh or curl based on what's available)
# ... (see Section 3)

# 7. Monitor CI (see Section 4)

# 8. Merge when green (see Section 7)
```

## Common Pitfalls

1. **Bare `gh` PR commands in a fork checkout.** `gh` may resolve upstream instead of the push remote. Derive `OWNER_REPO` from `git remote get-url origin` and pass `--repo` explicitly to every `gh` PR command. Omitting `--repo` (or `--head OWNER:BRANCH`) in a fork produces a misleading GraphQL error like `"No commits between main and <branch>", "Head sha can't be blank", "Head ref must be a branch"` — which looks like an empty branch but is actually a targeting failure. Always include `--repo OWNER/REPO` and `--head OWNER:BRANCH` in fork PRs.
2. **Opening a duplicate PR.** Check `gh pr list --repo "$OWNER_REPO" --head "$BRANCH" --state open` before `gh pr create`.
3. **Using broad add-all commands in dirty worktrees.** Stage only intended paths and report unrelated dirty files separately.
4. **Reporting push success without SHA verification.** Compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/$BRANCH`.
5. **Treating local watch timeout as CI failure.** Re-read `statusCheckRollup`; pending checks are still running, failed checks need logs.
6. **Misdiagnosing `check-attribution`.** `AUTHOR_MAP` failures are release metadata gaps, not unit-test failures; fix with a scoped `scripts/release.py` mapping.
7. **Assuming a local follow-up commit is in the PR.** After a CI fix, documentation distillation, or skill update on the PR branch, decide whether that new commit belongs in the open PR. If yes, push and verify remote SHA/PR commit list; if no, explicitly report that the branch is ahead/unpushed so the user does not assume the PR includes it.

## Verification Checklist

- [ ] Branch, HEAD, remotes, default branch, and dirty status checked.
- [ ] Commit/stage scope excludes unrelated dirty files.
- [ ] Push remote SHA equals local `HEAD`, or an intentional unpushed/ahead state is reported with the reason.
- [ ] PR created or found with explicit `--repo`, `--base`, and `--head`.
- [ ] PR `baseRefName`, `headRefName`, head owner, commits, and mergeability verified.
- [ ] CI checks classified as passed/failed/pending from current `statusCheckRollup`.
- [ ] Failed check logs inspected before applying fixes.
- [ ] Any CI fix is committed with scoped staging and pushed with SHA verification.

## References

- `references/fork-pr-targeting-and-ci-verification.md` — explicit `--repo`/`--head` fork PR flow, push SHA verification, CI watch timeout handling, and dirty-worktree reporting.
- `references/check-attribution-author-map.md` — fixing `check-attribution` / `AUTHOR_MAP` CI failures with a scoped `scripts/release.py` commit.
- `references/conflict-resolution-dirty-worktree.md` — resolving PR conflicts without staging unrelated dirty files.
- `references/ci-troubleshooting.md` — common CI failure signatures and diagnosis paths.

## Useful PR Commands Reference

| Action | gh | git + curl |
|--------|-----|-----------|
| List my PRs | `gh pr list --author @me` | `curl -s -H "Authorization: ${GITHUB_AUTH_HEADER}" "https://api.github.com/repos/$OWNER/$REPO/pulls?state=open"` |
| View PR diff | `gh pr diff` | `git diff main...HEAD` (local) or `curl -H "Accept: application/vnd.github.diff" ...` |
| Add comment | `gh pr comment N --body "..."` | `curl -X POST .../issues/N/comments -d '{"body":"..."}'` |
| Request review | `gh pr edit N --add-reviewer user` | `curl -X POST .../pulls/N/requested_reviewers -d '{"reviewers":["user"]}'` |
| Close PR | `gh pr close N` | `curl -X PATCH .../pulls/N -d '{"state":"closed"}'` |
| Check out someone's PR | `gh pr checkout N` | `git fetch origin pull/N/head:pr-N && git checkout pr-N` |
