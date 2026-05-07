# Plan: Hermes daily backup cron

## Goal
Create a Hermes cron job that runs Konstantin's personal Hermes backup once every 24 hours and pushes the verified snapshot to the private GitHub repo.

## Context
- User request: "делай cron бэкап раз в 24 часа".
- Backup repo: `/home/konstantin/code/Hermes`.
- Remote: `https://github.com/4eburek404/Hermes`.
- Branch: `backup/bootstrap-2026-05-06`.
- Existing backup scripts:
  - `scripts/collect-hermes-backup.py`
  - `scripts/verify-hermes-backup.py`
- Scope already includes overlay docs/memory/skills/plugins/cron, encrypted secrets/state/sessions, Hermes CLI manifest/patch, and `[legacy CLI path removed; current source is the development repo skills tree]` skill CLI snapshots.

## Non-goals
- Do not update Hermes Agent.
- Do not run `git pull` in `/home/konstantin/.hermes/hermes-agent`.
- Do not restart the gateway.
- Do not edit Hermes config except creating the requested cron job.
- Do not print or commit raw secrets, raw sessions, raw `state.db`, or private keys.

## Steps
- [x] Read Hermes cron/backup skill context and plan governance.
- [x] Check existing cron jobs for backup duplicates.
- [x] Verify backup repo branch is present and scripts exist.
- [x] Create daily cron job with a self-contained safe prompt.
- [x] Verify cron metadata/listing and next run.
- [x] Record durable cron metadata in skill/fact_store.
- [x] Archive this plan after verification.
- [x] Run one immediate backup after creating the cron job so the new cron config is captured in GitHub.

## Verification
- `cronjob(action="list")` shows a new enabled job for Hermes personal backup.
- Schedule is every 24 hours.
- Delivery goes to the origin Telegram chat.
- Enabled toolsets are restricted to `terminal`.
- Future cron prompt forbids `hermes update`, Hermes Agent `git pull`, `/restart`, raw secret output, and recursive cron scheduling.
- Immediate backup run passes `python3 scripts/verify-hermes-backup.py`.
- Backup repo pushes successfully to `origin/backup/bootstrap-2026-05-06`.

## Risks / pitfalls
- If the backup repo is dirty before a scheduled run, the cron should fail safe and report instead of overwriting unknown changes.
- If encrypted artifacts grow toward GitHub limits, reduce split size further or configure Git LFS later.
- Restore of encrypted artifacts depends on the matching local SSH private key for the configured `age` recipient.
- If remote branch diverges, the job should report divergence instead of pulling/merging automatically.

## Status
Current status: done

## Notes
- Host timezone at plan creation: `2026-05-06 15:26:13 CEST +0200`.
- No existing backup cron was present in the initial cron list.
- Created cron job `0849e94b782d`: name `Hermes personal backup — every 24h`, schedule `every 1440m`, delivery `origin`, workdir `/home/konstantin/code/Hermes`, enabled toolsets `terminal`, model pin `ollama-local` / `glm-5.1:cloud`.
- Next run reported by scheduler: `2026-05-07T15:28:35.129322+02:00`.

- Immediate backup after cron creation passed verifier: `ok: true`, `memory_store_integrity: ok`, `state_db_integrity: ok`, `plaintext_secret_findings: 0`, `forbidden_plaintext_paths: 0`, `files_over_github_limit: 0`.
- Immediate backup commit pushed: `dfc67eec33e23402a239e54f7128d637c82b18c1` (`backup: daily hermes snapshot 2026-05-06T13:36Z`).

- Cron model/provider pinned after creation: `ollama-local` / `glm-5.1:cloud`, matching existing successful Hermes cron jobs and keeping the backup job independent of chat-model drift.
