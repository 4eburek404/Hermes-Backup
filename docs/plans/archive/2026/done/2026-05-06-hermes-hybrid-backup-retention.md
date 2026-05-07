# Plan: Hermes hybrid backup retention

## Goal
Implement a safer and smaller Hermes personal backup policy: daily Git diffs for plaintext/redacted overlay state, weekly encrypted refresh for heavy/private runtime state, and on-change encrypted refresh when secrets/credential metadata changes.

The result should keep `/home/konstantin/code/Hermes` on `main` as the latest restoreable backup snapshot while avoiding daily growth from new `age` ciphertext bundles.

## Context
- User direction: "Если encrypted раз в неделю проверять, а остальное diff?" → recommendation accepted as a hybrid design; then "Делай план, тщательно анализируй".
- Backup repo: `/home/konstantin/code/Hermes`.
- Remote: `https://github.com/4eburek404/Hermes.git`.
- Current branch verified: `main`, clean against `origin/main` at `c259445`.
- Current backup cron job verified from `~/.hermes/cron/jobs.json`:
  - job id: `0849e94b782d`
  - name: `Hermes personal backup — nightly`
  - schedule: `0 0 * * *` host timezone, currently `CEST +0200`; this is `03:00` Asia/Yekaterinburg for Konstantin.
  - workdir: `/home/konstantin/code/Hermes`
  - enabled toolsets: `terminal`
  - prompt already runs `collect-hermes-backup.py` and `verify-hermes-backup.py`, but does not encode a hybrid encrypted policy.
- Current collector behavior verified in `scripts/collect-hermes-backup.py`:
  - `collect_plaintext()` always refreshes docs/Hermes overlay/CLI manifests/holographic memory snapshot.
  - `collect_encrypted()` always creates new `secrets-encrypted/*` and `session-history-encrypted/*` artifacts.
  - `main()` always runs plaintext + encrypted.
- Current verifier behavior verified in `scripts/verify-hermes-backup.py`:
  - chooses latest manifest in `secrets-encrypted/` and `session-history-encrypted/`.
  - checks artifact checksums, age decrypt/listing, state DB integrity, plaintext secret scan, GitHub file-size limit, forbidden raw paths, CLI layer.
  - does not currently enforce "single active encrypted generation" or encrypted artifact freshness age.
- Current encrypted artifact state verified:
  - `secrets-encrypted/` has two timestamp generations: `20260506-133627`, `20260506-140011`; secrets artifacts are tiny (~19 KB each).
  - `session-history-encrypted/` has two timestamp generations; each state/session generation is split into 4 parts and totals ~153–154 MiB.
- Storage implication from current state size:
  - daily encrypted: about `55.04 GiB/year` at current 154.40 MiB/day.
  - weekly encrypted: about `7.86 GiB/year` at current size.
  - keeping 4 weekly generations visible in HEAD would be about `0.60 GiB` checkout size, but Git history would still retain older encrypted blobs unless history/LFS/external backend is introduced.

## Decision / target design
Use one existing nightly cron job, not daily branch-per-backup and not two competing cron jobs.

The collector becomes policy-aware:

- Daily run:
  - refresh plaintext/redacted overlay;
  - reuse the latest valid encrypted manifests/artifacts;
  - do not create new `age` ciphertext unless policy says encrypted refresh is due.
- Weekly encrypted run:
  - default day: Sunday night in the existing nightly job window (`03:00` Asia/Yekaterinburg / `00:00` current host time);
  - refresh both secrets and state/session encrypted bundles;
  - test-decrypt/list via verifier before commit/push.
- On-change secrets run:
  - if secret source metadata changes compared with latest encrypted secrets manifest, refresh encrypted bundles before the next weekly date.
  - Metadata means path presence, file type, size, mode, mtime, and provider/key inventory already present in safe manifests/inventories; do not commit raw secret values or plaintext content hashes of secrets.
- Catch-up guard:
  - if latest encrypted generation is missing or older than the allowed window, daily backup must fail safe rather than silently committing stale plaintext with unusable encrypted state.

Recommended first implementation policy:

- HEAD contains only one active encrypted generation per encrypted directory:
  - one `secrets-encrypted/manifest-*.json` and its referenced artifact(s);
  - one `session-history-encrypted/manifest-*.json` and its referenced artifact parts.
- Historical encrypted snapshots may still exist in Git history by commit date. This is acceptable for the first version because weekly growth is much lower than daily growth.
- Do not auto-force-push or rewrite Git history for storage cleanup. That is a separate high-risk operation.
- Do not introduce restic/borg/kopia in this plan. Mention as future option only if GitHub history growth becomes unacceptable.

## Non-goals
- Do not expose raw `.env`, `auth.json`, OAuth tokens, private keys, raw `state.db`, raw session transcripts, or plaintext secret hashes.
- Do not vendor the upstream `~/.hermes/hermes-agent` repo wholesale.
- Do not change unrelated cron jobs.
- Do not change Hermes Agent runtime code outside the backup repo unless a verified need appears.
- Do not implement Git history rewrite, Git LFS migration, restic/borg/kopia, or external storage in this plan.
- Do not create daily backup branches or branch-per-snapshot.
- Do not restart the Telegram gateway unless required for cron metadata changes to take effect and after writes are verified.

## Steps

### Phase 0 — safety preflight
- [x] Verify `/home/konstantin/code/Hermes` is clean and on `main`; fetch `origin/main` and fail if local/remote diverged.
- [x] Create an implementation branch before code changes, e.g. `backup/hybrid-retention-2026-05-06`, preserving the current production `main` until tests pass.
- [x] Confirm no relevant active plan already supersedes this one.
- [x] Snapshot current encrypted artifact inventory and latest manifest timestamps without printing secret values.

### Phase 1 — collector policy modes
- [x] Add command-line options to `scripts/collect-hermes-backup.py`:
  - `--encrypted-mode auto|always|never`, default `auto`.
  - `--weekly-encrypted-dow`, default Sunday (`6` if using Python Monday=0 convention).
  - `--max-encrypted-age-days`, default `8`.
  - `--retention latest`, default enabled for encrypted artifacts in HEAD.
- [x] Split current `main()` flow into explicit steps:
  - always run `collect_plaintext()` and `sanitize_plaintext_tree()`;
  - decide whether encrypted refresh is due;
  - if due: cleanup old active encrypted artifacts, run `collect_encrypted()`;
  - if not due: load latest encrypted manifests and write current top-level `MANIFEST.json`/`MANIFEST.md` that references the latest encrypted artifacts and records `encrypted_refreshed: false`.
- [x] Implement encrypted refresh decision:
  - refresh if `--encrypted-mode always`;
  - skip if `--encrypted-mode never`, but only if latest encrypted manifests/artifacts exist and verifier freshness passes;
  - in `auto`, refresh when:
    - latest encrypted manifests/artifacts are missing;
    - current date is configured weekly encrypted day;
    - latest encrypted generation is older than `--max-encrypted-age-days`;
    - secret source metadata differs from the latest secrets manifest.
- [x] Ensure the secret change detector does not store raw values or new plaintext secret hashes. It compares safe metadata against the latest secrets manifest and excludes high-churn non-credential `channel_directory.json` from on-change refresh while still encrypting it weekly.
- [x] Make cleanup precise and deny-by-default:
  - delete only generated encrypted files matching known patterns in `secrets-encrypted/` and `session-history-encrypted/`;
  - never delete README files or unrelated files;
  - after cleanup/create, assert the active manifest references all remaining generated artifacts.

### Phase 2 — verifier guardrails
- [x] Add verifier options to `scripts/verify-hermes-backup.py`:
  - `--max-encrypted-age-days 8` to fail if latest encrypted manifests are too old;
  - `--require-single-active-generation` to fail if old `manifest-*` or old `*.tar.zst.age*` artifacts remain in HEAD outside the latest manifest references.
- [x] Keep existing checks:
  - SQLite integrity for holographic memory snapshot;
  - encrypted artifact sha256/size;
  - age decrypt + tar listing;
  - extracted `state.db` integrity;
  - plaintext high-risk secret scan;
  - forbidden raw/cache path scan;
  - GitHub 100 MiB file limit;
  - CLI backup manifest checks.
- [x] Add clear JSON output fields:
  - `encrypted_freshness_days` or per-kind `age_days`;
  - `single_active_generation: true`;
  - `encrypted_refreshed` from `MANIFEST.json` if present;
  - `latest_secret_timestamp` and `latest_state_timestamp`.

### Phase 3 — docs/runbook updates
- [x] Update `/home/konstantin/code/Hermes/README.md` to describe the hybrid policy:
  - daily plaintext/redacted overlay;
  - weekly/on-change encrypted artifacts;
  - HEAD has latest active encrypted generation;
  - Git history still grows weekly unless a separate storage strategy is added.
- [x] Add or update a short runbook section in the backup repo for manual commands:
  - daily-style run: `python3 scripts/collect-hermes-backup.py --encrypted-mode auto`
  - force encrypted run: `python3 scripts/collect-hermes-backup.py --encrypted-mode always`
  - verification: `python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation`
- [x] If implementation produces reusable backup-retention workflow beyond this repo, patch the installed `hermes-agent` skill backup section with the learned policy. Do this only after successful verification, not before.

### Phase 4 — local verification before cron mutation
- [x] Run syntax checks:
  - `python3 -m py_compile scripts/collect-hermes-backup.py scripts/verify-hermes-backup.py`
- [x] Run verifier against current repo before collector changes to record baseline. Expected current finding: likely fails `--require-single-active-generation` because two encrypted generations exist.
- [x] Run collector in auto mode on the implementation branch.
- [x] Verify that daily/auto behavior does one of two correct things:
  - if encrypted refresh is due, it creates one fresh active generation and removes old active generated artifacts from HEAD;
  - if encrypted refresh is not due, it updates plaintext and reuses latest encrypted manifests without creating a new ciphertext generation.
- [x] Run verifier with strict flags:
  - `python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation`
- [x] Confirm no raw secrets or forbidden paths appear in plaintext output.
- [x] Confirm no file exceeds GitHub hard 100 MiB limit.
- [x] Confirm `git status` contains only intended script/docs/backup snapshot changes.

### Phase 5 — merge/deploy backup policy
- [x] Merge implementation branch to `main` only after strict verifier passes.
- [x] Commit with a clear message, e.g. `backup: add hybrid encrypted retention policy`.
- [x] Push `main` to GitHub.
- [x] Verify remote `origin/main` matches local HEAD.

### Phase 6 — cron update and smoke test
- [x] Update cron job `0849e94b782d` prompt to run the new hybrid collector command and strict verifier flags.
- [x] Preserve unrelated cron fields:
  - schedule `0 0 * * *`;
  - delivery `origin`;
  - workdir `/home/konstantin/code/Hermes`;
  - enabled toolsets `['terminal']`;
  - model/provider pin unless the task explicitly changes it.
- [x] Trigger a manual cron run or run the same command path from the backup repo.
- [x] Poll cron status/output if using `cronjob(action="run")` because cron execution is asynchronous.
- [x] Verify `last_status: ok`, `last_delivery_error: null`, strict verifier output, and clean git status after the run.

### Phase 7 — closeout and durable knowledge
- [x] Update this plan's checkboxes and Notes with verified commit IDs, cron metadata, and strict verifier output summary.
- [x] Promote durable current-state facts to `fact_store` and, if needed, `/home/konstantin/docs/infrastructure.md` or `/home/konstantin/docs/runbooks.md`.
- [x] If the skill was patched or should be patched, verify the skill content after patching.
- [x] Mark this plan `Current status: done` and archive it under `archive/2026/done/` only after implementation + verification are complete.

## Verification
Implementation is complete only when all of the following are true:

- `/home/konstantin/code/Hermes` is on `main`, clean, and `origin/main` matches local HEAD.
- `python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation` returns `ok: true`.
- `secrets-encrypted/` contains exactly one active generated manifest and only the artifact(s) referenced by it, plus allowed README/docs.
- `session-history-encrypted/` contains exactly one active generated manifest and only the artifact part(s) referenced by it, plus allowed README/docs.
- A non-weekly daily run does not create a new state/session ciphertext when encrypted refresh is not due.
- A forced run with `--encrypted-mode always` creates a fresh encrypted generation and still passes decrypt/listing and `state.db` integrity checks.
- Secret metadata change logic can be tested without revealing secret values; if tested by touching/copying a non-secret fixture, the result is documented.
- The nightly cron job `0849e94b782d` uses the new hybrid command/prompt and strict verifier flags while preserving schedule/delivery/workdir/toolsets/model pin.
- Cron smoke test or equivalent direct command path passes and leaves the repo clean after commit/push.
- No raw secret values, raw sessions, raw `state.db`, live WAL/SHM files, caches, logs, or credential sidecars appear in plaintext Git-tracked files.

## Risks / pitfalls
- Git retention vs HEAD retention: deleting old encrypted artifacts from the current tree reduces checkout size and daily diffs, but old encrypted blobs remain in Git history. Weekly encrypted history is acceptable short-term (~7.86 GiB/year at current size), but true storage pruning requires Git LFS/history rewrite/external dedup backup and is outside this plan.
- Secret change detection must not commit raw values or strong plaintext hashes of secrets. Use safe metadata already exposed in manifests/inventories, not file contents.
- Current verifier uses latest manifest only; without a new single-generation guard, old encrypted artifacts can keep accumulating invisibly.
- If the collector writes a new top-level manifest while skipping encrypted refresh, it must still reference latest encrypted artifacts correctly; otherwise restore documentation becomes misleading.
- Cron prompt drift is likely: updating scripts alone is not enough. The embedded cron prompt must be audited and updated.
- Weekly day/time depends on host timezone. Current host timezone is `CEST +0200`; current nightly cron `0 0 * * *` maps to `03:00` Asia/Yekaterinburg now, but DST changes can shift the local mapping unless the host timezone or cron expression is revisited.
- `age` encryption produces high-entropy new blobs; Git diff/delta remains poor. The improvement comes from lower frequency, not better binary diffs.
- Running the collector mutates the backup repo and may generate large artifacts; implementation should branch first and verify before merging/pushing.
- Force-pushing or history rewriting to reclaim old encrypted blobs is dangerous and must not be automated in this plan.

## Status
Current status: done

## Notes
- 2026-05-06: Plan created after verifying plan governance, backup repo state, current collector/verifier behavior, cron metadata summary, and current encrypted artifact inventory. No collector/verifier/cron implementation changes had been made yet under this plan.
- 2026-05-06: Implementation approved by user (`Go`). Preflight passed on `main` at `c259445859f46bac804d72ae9addb503711d32e5`; created branch `backup/hybrid-retention-2026-05-06`. Current HEAD inventory before cleanup: two encrypted generations in each encrypted directory (`20260506-133627`, `20260506-140011`), no raw secret values inspected or printed.
- 2026-05-06: Implementation merged and pushed to `main`: `41ccd9b7fd25b89d679e3adf29178e65476595da` (`backup: implement hybrid encrypted retention`). Strict verifier passed on `main`; `origin/main` matched local HEAD.
- 2026-05-06: Existing cron job `0849e94b782d` updated in place, preserving schedule `0 0 * * *`, delivery `origin`, workdir `/home/konstantin/code/Hermes`, enabled toolsets `['terminal']`, and model/provider pin `ollama-local` / `glm-5.1:cloud`. Prompt now runs collector `--encrypted-mode auto --max-encrypted-age-days 8 --retention latest` and strict verifier `--max-encrypted-age-days 8 --require-single-active-generation`.
- 2026-05-06: Cron smoke test passed. First smoke run produced commit `7f79ee9eefea66ab2ff54f6f0bab61a50b3d2c72`; prompt then hardened to avoid Telegram pipe tables and accidental `[SILENT]` suffix. Second smoke run passed with `last_status: ok`, `last_delivery_error: null`, and pushed commit `6818449832b3ebcac3608716e3142b652d329eff`; `origin/main` matched local HEAD and repo was clean.
- 2026-05-06: Final strict verifier summary: `ok: true`, `single_active_generation: true`, `latest_secret_timestamp: 20260506-151544`, `latest_state_timestamp: 20260506-151544`, `plaintext_secret_findings: 0`, `forbidden_plaintext_paths: 0`, `files_over_github_limit: 0`, `state_db_integrity: ok`, `memory_store_integrity: ok`.