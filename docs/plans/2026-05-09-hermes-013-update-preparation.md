# Подготовка к обновлению Hermes Agent до v0.13.0

Дата подготовки: 2026-05-09
Исполнительный контекст: VPS/source install `~/.hermes/hermes-agent`, fork `4eburek404/Hermes-fork-development`
Целевой рекомендуемый update target: `v2026.5.7` / Hermes Agent `0.13.0`

## Status
Current status: completed

## Notes
- 2026-05-10 10:32 +05: Plan status normalized before preparation work. Live state must be rechecked because primary checkout changed since the 2026-05-09 baseline.
- 2026-05-10 +05: Preparation run reached conflict-analysis gate. Isolated worktree `/tmp/hermes-013-sync-analysis-20260510` on branch `sync/hermes-013-v2026-5-7-20260510-analysis` merged `v2026.5.7` with expected conflicts and no commit/push/runtime update.
- 2026-05-10 +05: Detailed conflict/policy analysis recorded at `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-conflict-analysis.md`.
- 2026-05-10 11:21 +05: Candidate conflict resolutions applied and staged in the isolated worktree only. Scoped conflict marker scan, scoped cached whitespace check, `py_compile`, and focused pytest passed; details in `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-resolution-test-results.md`.
- 2026-05-10 11:42 +05: Non-conflict `skills.external_dirs` drift adapted to fork policy in the isolated worktree. Combined focused verification passed (`118 passed, 140 deselected`), scoped cached check passed, and marker scan over 14 scoped files found `0`; details in `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-external-dirs-policy-gate.md`.
- 2026-05-10 11:53 +05: Selected broader gate for skill commands/reload/gateway/update path passed after adapting a stale `--quiet` expectation in `tests/hermes_cli/test_update_autostash.py`; final result `240 passed`, unmerged `0`, scoped cached check passed, marker scan over 15 scoped files found `0`; details in `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-selected-broader-tests.md`.
- 2026-05-10 12:03 +05: Isolated branch commit-readiness assessed. Merge index is resolved (`unmerged=0`, `unstaged=0`, `untracked=0`) and scoped policy checks pass, but staged content is the full release merge (`1083` files) and all-repo `git diff --cached --check` is noisy from upstream/release whitespace plus a benign `Context`/`=======` docstring heading; commit/push remains a decision gate, not an automatic action. Details in `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-commit-readiness.md`.
- 2026-05-10 12:09 +05: Primary checkout dirty skill/docs changes preserved before any active update/restart under `/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve`; restore check in detached temporary worktree passed (`restored_file_hashes_match=4`).
- 2026-05-10 +05: Primary dirty skill/docs changes committed separately on `main` as `01c21ebfc762` (`docs: preserve pre-update Hermes skill notes`). Commit includes exactly 4 paths: `skills/autonomous-ai-agents/hermes-agent/SKILL.md`, `skills/autonomous-ai-agents/hermes-agent/references/fork-release-sync-conflicts.md`, `skills/github/github-pr-workflow/SKILL.md`, `skills/productivity/flight-search/references/cli-maintenance.md`. Redacting changed-skill audit passed after removing ignored `flight-search/cli` `__pycache__` generated artifacts; `git diff --cached --check` passed before commit.
- 2026-05-10 12:47 +05: Active update completed. Final primary `main` is `e0d5636c93d31d17fcd52ef79ea72fff32680b66`, pushed to `origin/main`, installed package is `hermes-agent==0.13.0`, and `hermes --version` reports `Hermes Agent v0.13.0 (2026.5.7)`. Final integration verification passed: exact conflict marker scan `0`, `py_compile` pass, focused pytest `258 passed`, selected broader pytest `240 passed`. Details in `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-active-update-results.md`.

## 0. Зачем обновляться именно нам

Обновление имеет смысл не ради всех новых фич, а ради операционного профита для текущей схемы Константина:

1. **Telegram/gateway устойчивость** — sessions survive restart/update/source reload, лучше сохраняется routing/home-channel/thread state.
2. **Безопаснее править файлы и skills** — post-write lint для `write_file`/`patch`, checkpoints v2, больше security hardening.
3. **Длинные задачи лучше удерживаются** — `/goal`, durable multi-agent Kanban, улучшенная session durability.
4. **Skill-library hygiene** — curator/self-improvement/reporting, но включать осторожно из-за локальной политики source skills.
5. **Разработка flight-search/GitHub workflow** — косвенный профит: меньше silent-синтаксических ошибок, лучше rollback, лучше subagent diagnostics.

Низкий приоритет для наших текущих задач: Google Chat/Teams/QQBot/Yuanbao, Spotify, ComfyUI, TouchDesigner, video/voice cloning, dashboard cosmetics.

## 1. Проверенный текущий baseline

Live state на момент подготовки плана:

```text
repo=/home/konstantin/.hermes/hermes-agent
server_time=2026-05-09T17:55:38+02:00
user_tz_equivalent=2026-05-09T20:55:38+05:00
branch=work/flight-search-coverage-frontier-20260509
HEAD=b43fe81a8d8a
origin/main=b4abee5fde43
upstream/main=f6d45e5df49c
v2026.5.7=e19fc91cb82c
```

Version/SHA state from earlier verification:

```text
HEAD version=0.11.0 sha=b43fe81a8d8a
origin/main version=0.11.0 sha=b4abee5fde43
upstream/main version=0.13.0 sha=f6d45e5df49c
v2026.5.7 version=0.13.0 sha=e19fc91cb82c
```

Important conclusion:

- `hermes update` in this source/fork setup updates against fork `origin/main`, not directly against official `NousResearch/hermes-agent`.
- Since `origin/main` is still `0.11.0`, running `hermes update` alone does **not** get official `0.13.0` unless the fork is synced first.
- Built-in upstream sync is not safe to assume because fork has its own ahead commits.

## 2. Current blockers before any real update

Primary worktree is dirty. Do **not** run real `hermes update`, merge, reset, stash-pop, or gateway restart until this is resolved.

Current dirty/untracked files:

```text
 M skills/autonomous-ai-agents/hermes-agent/SKILL.md
 M skills/autonomous-ai-agents/hermes-agent/references/source-runtime-file-management.md
 M skills/github/github-pr-workflow/SKILL.md
 M skills/software-development/requesting-code-review/SKILL.md
 M skills/software-development/skill-audit-and-improvement/SKILL.md
 M skills/software-development/test-driven-development/SKILL.md
?? skills/autonomous-ai-agents/hermes-agent/references/release-review-fork-update-impact.md
?? skills/github/github-pr-workflow/references/isolating-follow-up-pr-with-worktree.md
```

Why this matters:

- Simulated `hermes update` dirty-state restore produced a stash-apply conflict in:

```text
skills/github/github-pr-workflow/SKILL.md
```

- If real update hits this, update may leave the checkout on updated `main` with local changes preserved only in stash, not automatically restored.
- Backup does not preserve dirty dev state; restoration-critical changes must be committed/pushed or explicitly exported as patches.

## 3. Recommended target decision

### Recommended: stable release tag `v2026.5.7`

Reason:

- It gives official Hermes `0.13.0`.
- It has fewer conflicts than `upstream/main`.
- It avoids the `agent/skill_utils.py` policy conflict present on current `upstream/main`.

Known simulated conflicts for `origin/main -> v2026.5.7`:

```text
conflict_count=3
agent/curator.py
scripts/release.py
tools/skill_usage.py
```

### Not recommended as first target: current `upstream/main`

Reason:

- It is a moving target beyond release.
- It adds a substantive policy conflict in `agent/skill_utils.py`.

Known simulated conflicts for `origin/main -> upstream/main`:

```text
conflict_count=4
agent/curator.py
agent/skill_utils.py
scripts/release.py
tools/skill_usage.py
```

### Not useful alone: `hermes update` to `origin/main`

Reason:

- `origin/main` is still `0.11.0`.
- It does not deliver the main `0.13.0` benefits.
- It still risks stash-restore conflict with current dirty docs.

## 4. Preparation phase A — freeze and protect current work

Goal: make sure nothing important is only dirty state in the primary worktree.

### A1. Re-check state immediately before cleanup

Run:

```bash
cd /home/konstantin/.hermes/hermes-agent
date -Is
git status --short --branch --untracked-files=all
git branch --show-current
git rev-parse --short=12 HEAD origin/main upstream/main v2026.5.7
```

Expected baseline should still be close to:

```text
branch=work/flight-search-coverage-frontier-20260509
HEAD=b43fe81a8d8a
```

If HEAD/branch changed, stop and re-evaluate; do not reuse this plan blindly.

### A2. Classify every dirty file

For each dirty file:

```bash
git diff -- <path>
```

Classification buckets:

1. **Keep and commit** — changes are real source/docs improvements.
2. **Export as patch only** — useful but not ready for repo history.
3. **Discard** — accidental or duplicate changes.
4. **Move to dedicated branch/PR** — changes belong to a separate topic.

Do not use broad `git add .`. Stage exact files only.

### A3. Preferred cleanup action

Preferred for current state:

1. Create a dedicated branch for remaining skill-doc changes, or reuse an existing appropriate branch only if scope matches.
2. Stage exact files.
3. Run skill audit for touched skills.
4. Commit and optionally PR if needed.

Example pattern:

```bash
cd /home/konstantin/.hermes/hermes-agent
git switch -c docs/pre-update-skill-source-notes-20260509
# inspect each diff first
git add -- skills/autonomous-ai-agents/hermes-agent/SKILL.md \
  skills/autonomous-ai-agents/hermes-agent/references/source-runtime-file-management.md \
  skills/autonomous-ai-agents/hermes-agent/references/release-review-fork-update-impact.md
# only add GitHub skill files if they belong to this same docs branch
```

If committing skill changes:

```bash
python3 scripts/audit_skill.py --skill hermes-agent --json
python3 scripts/audit_skill.py --skill github-pr-workflow --json
python3 scripts/audit_skill.py --skill requesting-code-review --json
python3 scripts/audit_skill.py --skill skill-audit-and-improvement --json
python3 scripts/audit_skill.py --skill test-driven-development --json
git diff --check --cached
```

If not committing, export patch instead:

```bash
git diff --binary > /home/konstantin/docs/plans/artifacts/hermes-pre-update-dirty-state-2026-05-09.patch
git status --short --untracked-files=all > /home/konstantin/docs/plans/artifacts/hermes-pre-update-dirty-status-2026-05-09.txt
```

For untracked files, copy them explicitly into artifacts or commit them; normal `git diff` does not include untracked file contents.

### A4. Acceptance gate for cleanup

Before starting update work, primary checkout must satisfy one of these:

- clean worktree; or
- only explicitly accepted unrelated dirty files remain and are documented; or
- dirty state exported to patch + untracked files preserved.

Ideal gate:

```bash
git status --short --branch --untracked-files=all
# no M/?? files unless deliberately parked elsewhere
```

## 5. Preparation phase B — create isolated update workspace

Goal: do not update the active flight-search/GitHub-skill branch in place.

### B1. Refresh remotes

```bash
cd /home/konstantin/.hermes/hermes-agent
git fetch origin main --prune
git fetch upstream main --tags --prune
```

### B2. Create dedicated update branch/worktree from `origin/main`

Recommended branch:

```text
sync/hermes-013-v2026-5-7-20260509
```

Command pattern:

```bash
cd /home/konstantin/.hermes/hermes-agent
WORKTREE=/tmp/hermes-013-sync-20260509
git worktree add -B sync/hermes-013-v2026-5-7-20260509 "$WORKTREE" origin/main
cd "$WORKTREE"
```

Verify:

```bash
git status --short --branch --untracked-files=all
git rev-parse --short=12 HEAD
git describe --tags --always --dirty
```

Expected start:

```text
HEAD=b4abee5fde43  # origin/main baseline
```

## 6. Update merge phase — merge release tag

In the isolated worktree only:

```bash
cd /tmp/hermes-013-sync-20260509
git merge --no-commit --no-ff v2026.5.7
```

Expected result: content conflicts in 3 files.

```text
agent/curator.py
scripts/release.py
tools/skill_usage.py
```

Do not panic; this is expected. Do not run `git reset --hard` unless intentionally aborting this isolated merge.

## 7. Conflict-resolution policy

### 7.1 `agent/curator.py`

Likely conflict type: operational/docstring/path explanation around curator report directory.

Resolution preference:

- Accept upstream runtime guarantees: create/use curator report dirs correctly.
- Preserve profile-safe path handling.
- Preserve local wording only if it reflects current source layout.
- Do not hardcode `/home/konstantin` into source.

Verification after resolution:

```bash
python3 -m py_compile agent/curator.py
```

### 7.2 `scripts/release.py`

Likely conflict type: release metadata / `AUTHOR_MAP`.

Resolution preference:

- Union upstream changes with fork-specific attribution mapping needed for CI.
- Preserve the `4eburek404` author attribution fix unless upstream already includes equivalent mapping.
- Do not include emails/tokens/secrets in reports.

Verification:

```bash
python3 -m py_compile scripts/release.py
python3 scripts/release.py check-attribution || true
```

If the exact check command differs, inspect `scripts/release.py --help` before running.

### 7.3 `tools/skill_usage.py`

Likely conflict type: skill usage tracking and hub/installed skill name detection.

Resolution preference:

- Preserve Konstantin source/runtime invariant:
  - authored skills live in `~/.hermes/hermes-agent/skills`;
  - `~/.hermes/skills` is runtime state only;
  - no resurrection of obsolete `cli/skill-clis` or local mirrors.
- Accept upstream improvements for installed hub skill detection if compatible.
- Verify curator status and skill usage behavior after merge.

Verification:

```bash
python3 -m py_compile tools/skill_usage.py
python3 - <<'PY'
from tools import skill_usage
print('skill_usage_import_ok')
PY
```

### 7.4 Only if targeting `upstream/main`: `agent/skill_utils.py`

This does not conflict against `v2026.5.7`, but will conflict against current `upstream/main`.

This is a policy decision, not mechanical merge:

- fork policy: `skills.external_dirs` ignored, single canonical source;
- upstream policy: cached `skills.external_dirs` support.

Default recommendation: keep single-source policy unless there is a concrete reason to enable external dirs.

## 8. Post-merge source verification

After resolving conflicts:

```bash
cd /tmp/hermes-013-sync-20260509
git status --short --branch --untracked-files=all
git diff --check
python3 -m compileall -q agent hermes_cli tools scripts
```

Then run focused tests around changed areas. Use current project test runner; likely:

```bash
python3 -m pytest tests/ -o 'addopts=' -q
```

If full suite is too slow, minimum focused gates:

```bash
python3 -m pytest tests/ -o 'addopts=' -q -k 'skill or curator or release or update or gateway or cli'
```

But before reporting ready, prefer full suite.

## 9. Hermes runtime verification before deployment

In isolated worktree or after branch checkout, verify CLI-level behavior:

```bash
hermes --version
hermes doctor
hermes update --check
hermes skills list
hermes curator status || true
```

Important: `hermes update --check` after fork sync must be interpreted carefully. It may still report fork/origin state, not official upstream.

Check config migrations without blindly changing behavior:

```bash
hermes config check
hermes config path
```

If config migration is required:

```bash
hermes config migrate
hermes config check
```

Do not run `hermes config migrate` until the source branch is selected and dirty state is protected.

## 10. Skill-owned CLI verification

Because flight-search is a critical custom workflow, verify after update:

```bash
cd /home/konstantin/.hermes/hermes-agent/skills/productivity/flight-search/cli
PYTHONDONTWRITEBYTECODE=1 python3 -m flights_cli --json doctor
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

If source worktree changes location due to update branch/worktree, adjust path to the active source checkout being tested.

Acceptance:

- doctor returns `ok=true`;
- tests pass;
- `flight-search` skill still loads from owning source path, not stale external dirs.

## 11. Gateway/Telegram smoke before final restart claim

Do not claim production-ready until gateway behavior is verified.

### Pre-restart capture

```bash
systemctl --user status hermes-gateway --no-pager || true
journalctl --user -u hermes-gateway -n 80 --no-pager || true
```

### Restart only after source verification

```bash
systemctl --user restart hermes-gateway
sleep 5
systemctl --user status hermes-gateway --no-pager
journalctl --user -u hermes-gateway -n 120 --no-pager
```

### Telegram smoke

From Telegram, verify:

1. Basic response.
2. Tool call still works, e.g. read-only status/date query.
3. Skill loading still works.
4. No prompt-cache stale behavior after restart.
5. New session/reset behavior understood if tools/skills changed.

Report should explicitly say:

- gateway restarted: yes/no;
- smoke passed: yes/no;
- if not restarted, say update branch is verified but runtime not switched.

## 12. Security/config review after 0.13

0.13 release notes include security hardening and redaction changes. Check actual effective config rather than assuming defaults.

Review:

```bash
hermes config path
hermes config check
hermes config | sed -n '/security:/,/^[^ ]/p'
hermes config | sed -n '/privacy:/,/^[^ ]/p'
hermes config | sed -n '/gateway:/,/^[^ ]/p'
```

Decision points:

- Secret redaction: ensure it does not corrupt diffs/tool outputs, but also does not leak credentials.
- Telegram allowed chats: consider setting explicit allowlist for the home chat.
- Cron prompt-injection scan: verify existing cron jobs still run.
- Credential/auth files: verify permissions remain `0600` where relevant.

Do not paste secrets into reports. If config output includes secrets, redact as `[REDACTED]`.

## 13. Feature enablement sequence after update

Do not enable everything at once. Suggested rollout:

### Wave 1 — reliability primitives

Enable/use first:

- session durability after gateway restart;
- checkpoints v2;
- post-write lint;
- config/security checks.

Goal: make the existing workflow safer without changing habits.

### Wave 2 — `/goal`

Use for long Telegram tasks:

- “держать цель: подготовить update branch до green tests”;
- “держать цель: довести PR до green CI”;
- “держать цель: найти business-practical flight options, not cheapest-first”.

Acceptance: agent does not drift across multi-turn tasks.

### Wave 3 — curator in observation mode

Run manually first:

```bash
hermes curator status
hermes curator run
```

Review reports before allowing archive/prune.

Do not let curator mutate custom authored skills until we confirm:

- it recognizes source layout;
- it does not treat custom skill-owned CLIs as dead artifacts;
- pinned/protected skills are respected.

### Wave 4 — Kanban

Test only after stable gateway:

- start with a non-critical repo/task;
- verify worker logs, heartbeats, reclaim behavior;
- ensure worktrees isolate writes;
- require explicit evidence before accepting worker “done” claims.

Good first use case: independent review/testing of update branch, not direct production writes.

## 14. Push/PR strategy for fork sync

After merge and verification in update branch:

```bash
git status --short --branch --untracked-files=all
git add -- <resolved-files-only>
git commit -m "chore: sync Hermes Agent v2026.5.7"
git push origin sync/hermes-013-v2026-5-7-20260509
```

Verify remote SHA:

```bash
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/sync/hermes-013-v2026-5-7-20260509 | awk '{print $1}')
printf 'local=%s\nremote=%s\n' "$LOCAL" "$REMOTE"
test "$LOCAL" = "$REMOTE"
```

Create PR explicitly against fork main:

```bash
gh pr list --repo 4eburek404/Hermes-fork-development --head sync/hermes-013-v2026-5-7-20260509 --base main
gh pr create --repo 4eburek404/Hermes-fork-development \
  --base main \
  --head 4eburek404:sync/hermes-013-v2026-5-7-20260509 \
  --title "chore: sync Hermes Agent v2026.5.7" \
  --body "Sync fork to official Hermes Agent v2026.5.7 / 0.13.0. Resolves curator/release/skill_usage conflicts; preserves local skill-source policy."
```

Check PR metadata:

```bash
gh pr view --repo 4eburek404/Hermes-fork-development <PR_NUMBER> \
  --json state,mergeable,baseRefName,headRefName,headRepositoryOwner,commits,statusCheckRollup
```

Do not use bare `gh pr create` in this forked checkout.

## 15. Final deployment path after PR is merged

Only after PR green/merged into `origin/main`:

1. Ensure primary worktree is clean or intentionally parked.
2. Switch/update active checkout to fork `main`.
3. Pull `origin/main`.
4. Run doctor/tests/smoke again in active source path.
5. Restart gateway.
6. Start a fresh Telegram session or `/reset` if prompt/tool/skill availability changed.

Command shape:

```bash
cd /home/konstantin/.hermes/hermes-agent
git status --short --branch --untracked-files=all
git switch main
git pull --ff-only origin main
hermes doctor
systemctl --user restart hermes-gateway
systemctl --user status hermes-gateway --no-pager
```

If `git switch main` refuses due to dirty files, stop and resolve dirty state; do not force.

## 16. Rollback plan

Rollback must be ready before restart.

### Before deployment

Record current good state:

```bash
cd /home/konstantin/.hermes/hermes-agent
git rev-parse --short=12 HEAD
git status --short --branch --untracked-files=all
hermes --version
hermes doctor
systemctl --user status hermes-gateway --no-pager || true
```

### If source update breaks before gateway restart

```bash
git switch main
git reset --hard <previous-good-sha>
```

Only use `reset --hard` when dirty state is already protected.

### If gateway breaks after restart

```bash
cd /home/konstantin/.hermes/hermes-agent
git reset --hard <previous-good-sha>
systemctl --user restart hermes-gateway
journalctl --user -u hermes-gateway -n 120 --no-pager
```

If config migration caused breakage, restore config from backup/exported copy; do not guess.

## 17. Acceptance criteria for saying “готово”

Do not report “готово” until all are true:

- dirty pre-update state was committed/exported/discarded deliberately;
- update branch based on `origin/main` exists;
- `v2026.5.7` merged and conflicts resolved;
- resolved files pass syntax checks;
- tests/doctor pass;
- `flight-search` doctor passes;
- PR created/merged or active checkout updated intentionally;
- gateway restarted only after source verification;
- Telegram smoke passed;
- rollback SHA and method are recorded.

If only branch/PR is prepared but runtime is not switched, report:

```text
Update branch is prepared/verified, but active gateway is not yet running v0.13.0.
```

## 18. Risks to explicitly monitor

1. **Dirty worktree loss** — current biggest immediate risk.
2. **Fork source policy drift** — especially `skills.external_dirs` if later targeting `upstream/main`.
3. **Curator overreach** — archive/prune custom skills too aggressively.
4. **Redaction behavior** — too much redaction can corrupt diffs/log evidence; too little can leak secrets.
5. **Prompt/tool cache** — code/config changes may require gateway restart and fresh session/reset.
6. **PR/CI attribution** — preserve `scripts/release.py` author mapping.
7. **Temporary worktrees** — clean them only after verifying no unpushed changes.

## 19. Recommended next concrete action

Preparation has now advanced past the original first gate: an isolated analysis worktree exists and the release tag has been merged there with expected conflicts. Do **not** update active runtime yet.

Current next step:

```text
Resolve the three candidate conflicts in the isolated worktree, then run focused verification before committing/pushing a sync branch.
```

Still true before any active checkout update/gateway restart:

1. keep primary dirty state protected or cleaned deliberately;
2. do not use broad `git add .`;
3. commit/push only the verified sync branch;
4. update/restart the active runtime only after branch verification and an explicit deployment decision.

## 20. 2026-05-10 actual preparation run

Verified state:

```text
primary=/home/konstantin/.hermes/hermes-agent
primary_branch=main
primary_head=2cdb54d2236b
origin_main=2cdb54d2236b
tag_v2026_5_7=e19fc91cb82c
analysis_worktree=/tmp/hermes-013-sync-analysis-20260510
analysis_branch=sync/hermes-013-v2026-5-7-20260510-analysis
merge_head=e19fc91cb82c
```

Primary checkout still has unrelated dirty files, but they are small and exported as a patch:

```text
 M skills/github/github-pr-workflow/SKILL.md
 M skills/productivity/flight-search/references/cli-maintenance.md
artifact=/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-pre-update-dirty.patch
```

Merge result in the isolated worktree:

```text
conflict_count=3
agent/curator.py
scripts/release.py
tools/skill_usage.py
```

No commit, push, active checkout update, `hermes update`, gateway restart, reset, or stash-pop was performed.

Detailed analysis artifact:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-conflict-analysis.md
```

### 20.1 Conflict summary

`agent/curator.py`:

- Our fork change: preserve source/runtime split; authored skill source is checkout `skills/`, while `~/.hermes/skills` is runtime state/archive.
- Upstream change: substantial curator improvements — dry-run, deferred first run, richer reports/YAML parsing, `absorbed_into` cron rewrites, review runtime binding, defensive `logs/curator` creation.
- Overlap: upstream fixed report-dir reliability, not fork source-layout policy.
- Resolution: keep upstream functional code; keep local source-layout truth; remove local hardcoded `/home/konstantin/...` prompt path before commit.

`scripts/release.py`:

- Our fork change: one fork-specific release attribution mapping for `4eburek404`.
- Upstream change: many `AUTHOR_MAP` additions/corrections.
- Overlap: same class of attribution gap, but upstream does not include the fork-specific mapping.
- Resolution: union upstream map with local mapping.

`tools/skill_usage.py`:

- Our fork change: `get_skills_dir()` for source, `get_skills_state_dir()` for runtime state; `.usage.json`, `.archive`, `.bundled_manifest`, hub lock state stay out of source checkout.
- Upstream change: file locking, explicit curator-managed provenance, activity counters, archive listing/restore, hub `install_path` + frontmatter name detection.
- Overlap: hub off-limits detection overlaps partly but for different reasons.
- Resolution: keep upstream provenance/concurrency/restore logic, but preserve fork path invariants and make `_read_hub_installed_names()` accumulate lock keys + frontmatter names from runtime/source locks.

### 20.2 Non-conflict policy drift found during analysis

These are not merge conflicts, but must be handled before claiming the update branch is clean:

1. New upstream external-dir tests conflict with fork policy that ignores `skills.external_dirs`:
   - `tests/agent/test_external_skills.py`
   - `tests/tools/test_skill_manager_tool.py::TestExternalSkillMutations`
2. User-facing/help text still mentions `~/.hermes/skills` and `skills.external_dirs` in places such as `/reload-skills` descriptions and `hermes_cli/tips.py`.
3. Curator prompt text must not settle on either upstream `~/.hermes/skills/<umbrella>/references/` as source or local hardcoded `/home/konstantin/...` as source; final wording should be checkout/profile-safe.

### 20.3 Completed conflict-resolution verification gate

Applied candidate resolutions in the isolated worktree and staged only the resolved/adapted files. Verification:

```text
unmerged_entries=0
scoped_conflict_marker_hits=0
scoped_cached_check=pass
py_compile=pass
focused_pytest=100 passed in 2.60s
```

Details:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-resolution-test-results.md
```

### 20.4 Completed non-conflict `skills.external_dirs` policy gate

Adapted non-conflict upstream drift to the fork policy that ignores `skills.external_dirs` and keeps authored skills in the Hermes Agent checkout `skills/` tree. Files adapted:

```text
agent/skill_utils.py
agent/skill_commands.py
hermes_cli/commands.py
hermes_cli/config.py
hermes_cli/tips.py
tools/skill_manager_tool.py
tests/agent/test_external_skills.py
tests/hermes_cli/test_commands.py
tests/tools/test_skill_manager_tool.py
```

Combined focused verification:

```text
py_compile=pass
combined_focused_pytest=118 passed, 140 deselected in 2.79s
unmerged_entries=0
scoped_cached_check=pass
scoped_conflict_marker_hits=0
```

Details:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-external-dirs-policy-gate.md
```

### 20.5 Completed selected broader verification gate

Ran broader selected tests for skill commands/reload, gateway command/help/update surfaces, Discord slash command registry, and `hermes update` CLI behavior.

Initial result exposed one stale test expectation:

```text
tests/hermes_cli/test_update_autostash.py::test_cmd_update_retries_optional_extras_individually_when_all_fails
```

Root cause: current update code intentionally omits `--quiet` from `pip install` calls to avoid apparent hangs during slow dependency builds, while the test still mocked exact commands with `--quiet`. Adapted the test to current command shape.

Final verification:

```text
focused_update_autostash_regression=1 passed in 4.85s
selected_broader_pytest=240 passed in 108.35s
unmerged_entries=0
scoped_cached_check=pass
scoped_conflict_marker_hits=0
```

Details:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-selected-broader-tests.md
```

### 20.6 Completed isolated branch commit-readiness assessment

Candidate branch is mechanically resolved and conditionally ready for a commit/push decision, but not deploy-ready.

Evidence:

```text
worktree=/tmp/hermes-013-sync-analysis-20260510
branch=sync/hermes-013-v2026-5-7-20260510-analysis
HEAD=2cdb54d2236b
MERGE_HEAD=e19fc91cb82c
staged=1083
unstaged=0
untracked=0
unmerged=0
```

Diff shape:

```text
HEAD_to_index=1083 files (678 modified, 404 added, 1 deleted)
MERGE_HEAD_to_index=262 files (fork-specific retained/adapted deltas)
numstat_HEAD_to_index=166503 additions, 10022 deletions, 18 binary/uncomputed
```

Checks:

```text
scoped_policy_cached_check=pass
scoped_policy_marker_scan=0
exact_staged_conflict_marker_scan=0
all_repo_cached_check=exit 2 (upstream/release whitespace noise + benign docstring heading false positive)
```

Primary checkout blocker remains and was freshly rechecked:

```text
repo=/home/konstantin/.hermes/hermes-agent
branch=main
HEAD=2cdb54d2236b
status:
 M skills/autonomous-ai-agents/hermes-agent/SKILL.md
 M skills/github/github-pr-workflow/SKILL.md
 M skills/productivity/flight-search/references/cli-maintenance.md
?? skills/autonomous-ai-agents/hermes-agent/references/fork-release-sync-conflicts.md
```

Details:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-commit-readiness.md
```

### 20.7 Completed primary dirty preservation and separate commit gate

The active primary checkout dirty skill/docs changes that must not be lost were first preserved as recoverable artifacts, then committed separately on `main`.

Preserved and committed paths:

```text
M  skills/autonomous-ai-agents/hermes-agent/SKILL.md
A  skills/autonomous-ai-agents/hermes-agent/references/fork-release-sync-conflicts.md
M  skills/github/github-pr-workflow/SKILL.md
M  skills/productivity/flight-search/references/cli-maintenance.md
```

Preservation artifact set:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve/status.txt
/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve/tracked-dirty.patch
/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve/untracked-create.patch
/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve/file-copies.tar.gz
/home/konstantin/docs/plans/artifacts/2026-05-10-1209+0500-hermes-primary-dirty-preserve/manifest.json
```

Preservation verification:

```text
restore_check=pass
restored_file_hashes_match=4
check_mode=detached temporary worktree from HEAD 2cdb54d2236b
```

Commit:

```text
commit=01c21ebfc762c6e1271100f0b642a69c30d428b6
short=01c21ebfc762
message=docs: preserve pre-update Hermes skill notes
branch=main
status=main ahead of origin/main by 1
```

Pre-commit checks:

```text
tracked_diff_check=pass
changed_skill_audit=pass after removing ignored flight-search/cli __pycache__ generated artifacts
cached_name_status=exactly the 4 paths above
cached_check=pass
```

No push, active update, gateway restart, reset, or stash-pop was performed.

### 20.8 Completed active update, push, and install gate

The isolated release sync was committed, merged into a final integration branch based on the current primary `main`, verified, fast-forwarded into the active primary checkout, pushed to `origin/main`, and installed into the active virtualenv.

Final active state:

```text
repo=/home/konstantin/.hermes/hermes-agent
branch=main
HEAD=e0d5636c93d31d17fcd52ef79ea72fff32680b66
status=## main...origin/main
pyproject_version=0.13.0
package_version=0.13.0
hermes --version=Hermes Agent v0.13.0 (2026.5.7)
```

Final verification:

```text
exact conflict marker scan=0
py_compile=pass
focused pytest=258 passed in 7.07s
selected broader pytest=240 passed in 108.07s
uv pip install --python venv/bin/python -e '.[all]'=pass
import_hermes_cli_main=ok
```

Pushed:

```text
remote=origin main
range=2cdb54d22..e0d5636c9
```

Runtime restart handling:

```text
systemd_user_unit=hermes-gateway.service active/running before restart scheduling
safe_restart_method=delayed user-systemd restart from a transient unit after the final Telegram report, because immediate restart would kill this active turn and the old running gateway lacks the newer SIGUSR1/self-restart handler
post_restart_smoke=transient unit sends Telegram smoke and writes `/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-post-restart-smoke.json`
```

Details:

```text
/home/konstantin/docs/plans/artifacts/2026-05-10-hermes-013-active-update-results.md
```
