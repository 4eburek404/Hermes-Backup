# Hermes hybrid backup retention — Konstantin, 2026-05-06

Use this reference when maintaining `/home/konstantin/code/Hermes` backup policy or answering design questions about daily plaintext diffs vs encrypted artifacts.

## Session learning

Konstantin asked whether encrypted artifacts could be checked weekly while everything else uses normal Git diff. The recommended design is a hybrid policy:

- **Daily:** refresh plaintext/redacted overlay only: docs, skills, plugins, cron jobs, SOUL/USER/MEMORY, redacted config/env/auth inventory, CLI manifests/patches, holographic memory SQLite snapshot.
- **Weekly:** refresh encrypted bundles for heavy/private runtime state: `state.db`, raw sessions, session history.
- **Secrets:** refresh weekly **and on safe metadata change** for `.env`, `auth.json`, credential pools, raw config, OAuth/Codex/Himalaya credential files. Do not wait a full week after credential changes.
- **HEAD retention:** keep exactly one active encrypted generation in the current tree: one latest manifest plus referenced artifact(s) per encrypted directory. Old encrypted blobs may remain in Git history; do not rewrite history automatically.
- **Verifier:** fail if latest encrypted artifacts are missing, too old (initial threshold: 8 days), checksum/decrypt/list fails, extracted `state.db` integrity fails, or more than one active generated encrypted generation remains in HEAD.

## Why this is better than daily encrypted Git commits

`age` encryption produces fresh high-entropy ciphertext on every run. Git text diffs and binary deltas do not meaningfully compress encrypted `tar.zst.age` bundles. The improvement comes from **lower refresh frequency**, not from better diffs.

Measured in the session from current state/session artifact size (~154.40 MiB):

- Daily encrypted: about **55.04 GiB/year** of new encrypted blobs.
- Weekly encrypted: about **7.86 GiB/year** of new encrypted blobs.
- Four weekly generations visible in HEAD would be about **0.60 GiB**, but the selected first policy is stricter: one active generation in HEAD.

## Target script behavior

`collect-hermes-backup.py` should support policy modes:

```bash
python3 scripts/collect-hermes-backup.py --encrypted-mode auto
python3 scripts/collect-hermes-backup.py --encrypted-mode always
python3 scripts/collect-hermes-backup.py --encrypted-mode never
```

Recommended options/semantics:

- `--encrypted-mode auto` default.
- `--weekly-encrypted-dow 6` if using Python Monday=0 convention; Sunday refresh in the existing nightly window.
- `--max-encrypted-age-days 8` freshness guard.
- `--retention latest` for generated encrypted artifacts in HEAD.
- Always run plaintext collection + sanitization.
- In auto mode, refresh encrypted artifacts when:
  - latest encrypted manifests/artifacts are missing;
  - today is the configured weekly encrypted day;
  - latest encrypted generation is older than max age;
  - safe credential/source metadata differs from the latest secrets manifest/inventory.
- Keep high-churn non-credential private metadata inside the weekly encrypted bundle, but do not let it force daily encrypted refreshes. For Konstantin's current setup, `~/.hermes/channel_directory.json` can get a new mtime from ordinary gateway/chat activity; exclude it from on-change detection while still encrypting it weekly.
- If not refreshing encrypted artifacts, top-level `MANIFEST.json`/`MANIFEST.md` must still reference the latest encrypted artifacts and record that encrypted refresh was skipped/reused.

## Target verifier behavior

`verify-hermes-backup.py` should support strict retention/freshness flags:

```bash
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation
```

Strict verifier should report JSON fields such as:

- `single_active_generation: true`
- `latest_secret_timestamp`
- `latest_state_timestamp`
- per-kind encrypted age/freshness
- `encrypted_refreshed` from `MANIFEST.json` when present

It must keep existing checks: plaintext secret scan, raw forbidden path scan, GitHub 100 MiB limit, encrypted artifact size/sha256, age decrypt/listing, extracted state DB integrity, and CLI layer verification.

## Cron implications

Use the existing nightly job rather than adding a second cron job:

- job id: `0849e94b782d`
- repo: `/home/konstantin/code/Hermes`
- branch: `main`
- schedule at the time of analysis: `0 0 * * *` host timezone (`03:00` Asia/Yekaterinburg at CEST +0200)

After script implementation, audit the embedded cron prompt. Updating scripts alone is not enough because cron prompts can retain stale instructions.

The cron prompt should run:

```bash
python3 scripts/collect-hermes-backup.py --encrypted-mode auto
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation
```

Preserve unrelated cron fields: schedule, delivery, workdir, enabled toolsets, and model/provider pin unless the change explicitly targets them.

## Pitfalls

- Do **not** create daily branch-per-backup; branches do not solve encrypted blob growth and complicate restore/cleanup.
- Do **not** store plaintext diffs or hashes of raw secrets/state/sessions.
- Do **not** assume removing old encrypted artifacts from HEAD reclaims Git object storage; history still retains prior blobs unless a separate Git LFS/history rewrite/external backend plan is approved.
- Do **not** weaken the secret scanner to make docs/examples pass; sanitize plaintext backup copies instead.
- Do **not** force-push or rewrite history as part of normal backup retention.
- Do **not** leave old generated `manifest-*`/`*.tar.zst.age*` files in HEAD while the verifier only checks latest manifest.

## Plan created

The detailed implementation plan was written to:

```text
/home/konstantin/docs/plans/2026-05-06-hermes-hybrid-backup-retention.md
```

At creation it was `Current status: planned`; implementation had not yet mutated scripts, repo, or cron.
