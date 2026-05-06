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
  - `cli/skill-clis/` — source snapshots from `/home/konstantin/code/clis` for local skill-related CLIs, excluding caches/build artifacts.

## What is backed up encrypted only

Raw secrets, OAuth tokens, service account files, raw `state.db`, and raw session transcripts are not committed in plaintext. They are stored only as `*.tar.zst.age` artifacts or split `*.tar.zst.age.partNNN` files under:

- `secrets-encrypted/`
- `session-history-encrypted/`

Encryption uses `age` to the SSH public key recorded in the artifact manifests. Restore requires the matching SSH private key.

## What is intentionally excluded

- Upstream Hermes Agent source checkout as a full vendored repo. Only manifest + patch + safe untracked source files are stored under `cli/hermes-agent/`.
- Logs, caches, media caches, screenshots/videos, locks, pids, live SQLite WAL/SHM sidecars.
- Raw credentials and raw runtime DB/session files in plaintext.

## Verification

Run:

```bash
python3 scripts/verify-hermes-backup.py
```

The verifier checks manifest presence, GitHub file-size limits, SQLite integrity for the plaintext memory snapshot, and scans plaintext files for high-risk secret patterns without printing secret values.
