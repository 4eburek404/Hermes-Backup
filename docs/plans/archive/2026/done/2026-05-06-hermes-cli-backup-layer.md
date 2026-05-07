# Plan: Hermes CLI backup layer

## Goal
Add a reproducible CLI backup layer to `https://github.com/4eburek404/Hermes` so the backup can restore not only the Hermes overlay, but also the active Hermes CLI/source state and local skill-related CLIs from `[legacy CLI path removed; current source is the development repo skills tree]`.

## Context
The bootstrap Hermes overlay backup intentionally excluded `/home/konstantin/.hermes/hermes-agent` as upstream code. Konstantin pointed out that this misses CLI/source state. Current requirement: add CLI backup plus local CLIs from `[legacy CLI path removed; current source is the development repo skills tree]` that support skills.

Safety constraints:
- Do not run `hermes update`, `git pull` in upstream Hermes Agent, `/restart`, or config/cron changes.
- Do not commit raw secrets, tokens, private keys, runtime DBs, raw sessions, `.git`, venvs, caches, or generated build artifacts.
- Prefer reproducible manifest + patches for upstream Hermes CLI instead of copying the whole upstream repo.
- Copy local `[legacy CLI path removed; current source is the development repo skills tree]` source trees after excluding caches/build artifacts and running secret scan.

## Non-goals
- Do not update Hermes Agent itself.
- Do not normalize or commit local Hermes Agent patches upstream.
- Do not create scheduled backup cron.
- Do not restore from backup in this task.
- Do not add Git LFS unless GitHub hard limits force it.

## Steps
- [x] Inventory active Hermes CLI executable/source path, version, branch, HEAD, remote, dirty status, tracked diff, and untracked files without printing secret values.
- [x] Inventory `[legacy CLI path removed; current source is the development repo skills tree]` and classify safe source files versus caches/build artifacts.
- [x] Update `scripts/collect-hermes-backup.py` to create `cli/hermes-agent/` manifest, tracked patch, untracked safe files, and `skills/<category>/<skill>/cli/` source snapshots.
- [x] Update `.gitignore`, README/restore docs, and `scripts/verify-hermes-backup.py` so CLI backup is required and scanned.
- [x] Run collector and verifier; verify DB integrity, age test-decrypt, secret scan, GitHub hard file limit, and git status.
- [x] Commit and push to branch `backup/bootstrap-2026-05-06`.
- [x] Update durable docs/skill/fact hook if the new CLI backup scope should persist beyond this plan.
- [x] Mark plan done and archive under `archive/2026/done/`.

## Verification
- `python3 -m py_compile scripts/collect-hermes-backup.py scripts/verify-hermes-backup.py` passes.
- `python3 scripts/collect-hermes-backup.py` succeeds without printing raw secrets.
- `python3 scripts/verify-hermes-backup.py` returns `ok: true`.
- Backup repo contains `cli/hermes-agent/manifest.json`, a tracked patch when dirty changes exist, and safe `[legacy CLI path removed; current source is the development repo skills tree]` snapshots.
- Plaintext secret scan findings are zero.
- No committed regular file is >= GitHub hard 100 MiB limit.
- Commit is pushed and remote branch SHA is verified.
- Plan is archived after completion; root plans remain clean.

## Risks / pitfalls
- Hermes Agent source has dirty local modifications; storing only version/HEAD would be insufficient for restore.
- `git diff` may contain token-shaped examples; run sanitizer/secret scan before commit.
- `[legacy CLI path removed; current source is the development repo skills tree]` may contain caches, pyc files, `.pytest_cache`, build metadata, or downloaded research artifacts; copy source but exclude generated noise.
- Private GitHub is not a substitute for encryption; if a CLI directory contains real credentials, it must be excluded or encrypted, not committed plaintext.
- Untracked files in Hermes Agent source may be backup files/noise; include only source/test/docs-like files that pass secret scan.

## Status
Current status: done

## Notes
- 2026-05-06: Created after Konstantin explicitly requested CLI backup layer.

- 2026-05-06: CLI backup layer implemented and pushed in commit `f8b770a3cb44fd6fbe6b827baa641664a28fc077`; verifier passed with `plaintext_secret_findings: 0`, `forbidden_plaintext_paths: 0`, and no files over GitHub hard limit.
