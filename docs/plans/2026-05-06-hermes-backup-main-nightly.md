# Plan: Hermes backup branch rename and nightly schedule

## Goal
Rename the personal Hermes backup repository branch from `backup/bootstrap-2026-05-06` to `main`, make GitHub default branch `main`, and move the daily backup cron job to nighttime for Konstantin.

## Context
- User request: "1. Переименуй ветку в main, чтоли 2. Бэкап делай ночью, а не когда я пользуюсь".
- Backup repo: `/home/konstantin/code/Hermes` / `https://github.com/4eburek404/Hermes`.
- Current branch before work: `backup/bootstrap-2026-05-06`.
- Current daily backup job: `0849e94b782d`, schedule `every 1440m`, next run was afternoon for Konstantin.
- Host timezone checked: `CEST +0200`; Konstantin timezone: `Asia/Yekaterinburg` / `+0500`.
- Night default: run at `03:00` Asia/Yekaterinburg, which is `00:00` host time, so cron expression should be `0 0 * * *` on this host.

## Non-goals
- Do not update Hermes Agent.
- Do not pull or modify the upstream Hermes Agent checkout `~/.hermes/hermes-agent`.
- Do not restart the gateway.
- Do not expose raw secrets, raw sessions, or raw `state.db` contents.
- Do not change unrelated cron jobs.

## Steps
- [ ] Verify backup repo is clean and remote/default state is known.
- [ ] Rename local backup branch to `main`, push `main`, set GitHub default branch to `main`, and remove the old remote branch if safe.
- [ ] Update backup cron job `0849e94b782d`: schedule to nightly host cron `0 0 * * *`, prompt branch guard to `main`, and name to nightly wording.
- [ ] Update durable reference/fact metadata so future agents know branch/schedule changed.
- [ ] Run collector + verifier on `main`, commit/push updated backup snapshot.
- [ ] Verify GitHub default branch/head, cron metadata/next_run_at, and clean git status.
- [ ] Mark this plan done and archive it.

## Verification
- `git branch --show-current` in `/home/konstantin/code/Hermes` returns `main`.
- GitHub repo default branch is `main`.
- Remote `refs/heads/main` points to latest local commit; old `backup/bootstrap-2026-05-06` remote branch is absent or intentionally documented.
- Cron job `0849e94b782d` is enabled with schedule `0 0 * * *`, workdir `/home/konstantin/code/Hermes`, toolset `terminal`, model pin `ollama-local` / `glm-5.1:cloud`.
- Cron next run maps to nighttime for Konstantin (`03:00` Asia/Yekaterinburg).
- `python3 scripts/verify-hermes-backup.py` returns `ok: true`.
- Working tree is clean after commit/push.

## Risks / pitfalls
- Cron scheduler uses host timezone, not necessarily Konstantin's timezone; conversion must be explicit.
- Deleting the old remote branch before changing GitHub default branch can fail or break default branch.
- Cron prompt can retain stale branch names even if metadata schedule changes.
- Backup collector may regenerate encrypted artifacts; verifier must pass before push.

## Status
Current status: in_progress

## Notes
- 2026-05-06: Plan created before mutating GitHub branch and live cron metadata.
