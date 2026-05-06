# Branch-first history restore workflow

Use this when a user asks to restore behavior that existed in earlier commits and explicitly says to create a new branch first.

## Session signal

Konstantin asked to remove a Tailscale-login dependency and restore authorization, then said: “Посмотри в коммитах, там раннее было. Сначала создай новую ветку.”

## Procedure

1. **Create the branch before investigation or edits.**
   ```bash
   git status --short
   git fetch origin --prune
   git checkout main
   git pull --ff-only origin main
   git checkout -b feat/<short-description>
   ```
   If the working tree is dirty, stop and report rather than mixing unrelated edits.

2. **Find the removal commit and the last-known-good parent.**
   ```bash
   git log --all --oneline --grep='auth\|login\|tailscale\|password\|basic' --regexp-ignore-case
   git log --all --oneline -- <relevant-files>
   git show <suspect-removal-commit> -- <relevant-files>
   git show <suspect-removal-commit>^:<path>
   ```

3. **Compare old behavior to current architecture.**
   - Identify web routes, API routes, WebSocket routes, native clients, and credential storage.
   - Do not blindly revert broad commits; reintroduce the minimal behavior compatible with current code.

4. **Implement with auth-specific verification.**
   - Add explicit smoke checks for unauthenticated denial and authenticated success.
   - Validate syntax/lint for all touched runtimes available on the host.
   - If a compiler/toolchain is unavailable, state that explicitly.

5. **Report branch, base, verification, and deployment status.**
   - Distinguish local changes, commits, pushed branch, PR, and deployment.
   - Do not deploy or push unless requested/clearly in scope.

## Pitfalls

- “Create branch first” is an ordering requirement, not just a final state requirement.
- History search by commit message may be empty; search by affected files and `git show <commit>^:<path>`.
- App auth restored from history may conflict with docs that were updated for a Tailscale-only decision; update docs to remove contradictions without storing secrets.
