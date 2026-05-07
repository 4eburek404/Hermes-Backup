# GitHub CLI PR/API token repair

Session-derived reference for cases where git operations work but GitHub PR API calls fail.

## Symptoms

- `git push` works over HTTPS.
- `gh pr create` / `gh pr list` fails with GraphQL `repository.pullRequests` or REST `403`.
- A later stale/bad token can show `HTTP 401: Bad credentials`.

## Key distinction

Successful git push proves repository write over git only. It does not prove GitHub API scopes for Pull Requests.

## Scopes that worked on Konstantin's host

Classic PAT scopes verified after repair:

- `repo`
- `workflow`
- `read:org`

## Safe login command

Use a prompt-wrapper command so the user sees where to paste the token:

```bash
read -rsp "GitHub token: " GH_PAT; echo; printf '%s\n' "$GH_PAT" | gh auth login --with-token && unset GH_PAT && gh auth setup-git
```

For Konstantin, send that command as a separate bare plain-text message if he needs to copy it.

## Verification

```bash
gh auth status
gh api user --jq .login
gh pr list --repo 4eburek404/server_monitor_iOS_app --limit 3 --json number,title,state,isDraft,url
```

Expected repaired state observed 2026-04-30:

- login: `4eburek404`
- scopes: `read:org`, `repo`, `workflow`
- PR list returns JSON (`[]` is OK)

## Secret handling

If a token appears in chat/transcript, treat it as compromised and tell the user to revoke/delete it and generate a new one. Do not reuse it from context.