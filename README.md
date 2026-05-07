# Hermes backup for Konstantin

This private repository stores Konstantin's personal Hermes overlay on top of the upstream Hermes Agent checkout.

## What is backed up in plaintext

- Curated docs from `/home/konstantin/docs/`.
- Hermes behavior/memory docs: `SOUL.md`, `memories/USER.md`, `memories/MEMORY.md`.
- Installed/custom skills and plugins.
- Cron job definitions (`cron/jobs.json`) without cron output/locks.
- Redacted configuration inventories.
- Consistent SQLite snapshot of holographic memory: `hermes/holographic-memory/memory_store.sqlite`.
- CLI backup layer:
  - `cli/hermes-agent/` — active Hermes CLI/source manifest, tracked patch, and safe untracked source files; not a full upstream repo vendor.
  - `cli/skill-clis/` — source snapshots from `/home/konstantin/.hermes/hermes-agent/local/skill-clis` for local skill-related CLIs, excluding caches/build artifacts. `/home/konstantin/code/clis` is a compatibility symlink to that location.

## What is backed up encrypted only

Raw secrets, OAuth tokens, service account files, raw `state.db`, and raw session transcripts are not committed in plaintext. They are stored only as `*.tar.zst.age` artifacts or split `*.tar.zst.age.partNNN` files under:

- `secrets-encrypted/`
- `session-history-encrypted/`

Encryption uses `age` to all SSH public keys listed in `backup/age-recipients.txt`, currently including the VPS-local verifier key and Konstantin's MacBook key. Restore requires any one matching SSH private key; do not copy the MacBook private key to the VPS.

## Hybrid retention policy

This repo uses a hybrid policy rather than creating a new encrypted archive on every nightly run:

- **Every nightly run:** refresh plaintext/redacted overlay files so Git can show normal diffs for docs, skills, plugins, cron metadata, redacted inventories, memory snapshot, and CLI manifests/patches.
- **Weekly / due runs:** refresh encrypted `state.db`, sessions, and secrets bundles.
- **Secrets on-change:** refresh encrypted bundles earlier when safe credential/source metadata changes. Raw secret values and plaintext secret hashes are never committed.
- **HEAD retention:** keep exactly one active encrypted generation in the current tree. Older encrypted blobs may still exist in Git history; reclaiming historical Git storage would require a separate explicit LFS/history-rewrite/external-backup plan.

Manual commands:

```bash
python3 scripts/collect-hermes-backup.py --encrypted-mode auto --max-encrypted-age-days 8 --retention latest
python3 scripts/collect-hermes-backup.py --encrypted-mode always --max-encrypted-age-days 8 --retention latest
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation
python3 scripts/verify-hermes-backup.py --identity-file ~/.ssh/id_ed25519 --max-encrypted-age-days 8 --require-single-active-generation
```

`--encrypted-mode auto` is the normal cron path. `always` is for forced encrypted refresh / restore drills. `never` reuses existing encrypted artifacts only when they are fresh and secret metadata is unchanged; otherwise it fails safe.

## What is intentionally excluded

- Upstream Hermes Agent source checkout as a full vendored repo. Only manifest + patch + safe untracked source files are stored under `cli/hermes-agent/`.
- Logs, caches, media caches, screenshots/videos, locks, pids, live SQLite WAL/SHM sidecars.
- Raw credentials and raw runtime DB/session files in plaintext.

## Verification

Run:

```bash
python3 scripts/verify-hermes-backup.py --max-encrypted-age-days 8 --require-single-active-generation
```

The verifier checks manifest presence, encrypted freshness, single active encrypted generation in HEAD, GitHub file-size limits, SQLite integrity for plaintext and encrypted DB snapshots, `age` decrypt/listing with the selected identity file, CLI layer presence, and scans plaintext files for high-risk secret patterns without printing secret values.
