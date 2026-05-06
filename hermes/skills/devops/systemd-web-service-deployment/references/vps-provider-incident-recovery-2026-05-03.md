# VPS Provider Incident Recovery (2026-05-03)

## Incident

VPS provider was compromised by hackers; server disappeared from the network. Returned/rebuilt with no graceful shutdown. Provider confirmed: "power was cut or server had no bootloader."

## What Was Found

- No graceful shutdown messages in logs — VPS was killed externally.
- Boot at 2026-05-03 16:43 (CEST). Previous stable boot was 2026-04-23.
- **n8n container**: crash loop (`Restarting (1)`, exit code 1). Bind mount `/home/konstantin/n8n/data` recreated as `root:root`. Error: `EACCES: permission denied, open '/home/node/.n8n/config'`.
- **hermes-guest / hermes-guest-dashboard**: started normally.
- **watchtower**: started normally.
- **hermes-gateway (systemd)**: started normally via gunicorn on :8080.
- **n8n-sync cron** (`/root/sync-n8n-inbox.sh`): ran every 5 min, wrote to `/var/log/n8n-sync.log`. Sync was regular until 2026-05-02 06:25, gap until reboot.
- **nimb-backup cron** (`/opt/backup-nimb.sh`): ran daily at 03:00, wrote tarballs to `/backup/nimb/`. Last run: 2026-05-02.

## Fixes Applied

1. `sudo chown -R 1000:1000 /home/konstantin/n8n/data && docker restart n8n` — fixed crash loop.
2. Removed both root crontab entries (n8n-sync + nimb-backup) — no longer needed.
3. Deleted `/backup/nimb/` contents (n8n + openclaw tarballs).
4. Deleted `/opt/backup-nimb.sh` and `/opt/nimb/nimb-heartbeat.sh`.

## Lessons

- After ungraceful reboot, always check Docker bind-mount ownership for non-root containers.
- Local-only backups on the same VPS are useless if the provider wipes/rebuilds the instance. Off-site backup (S3, B2, Git) is essential.
- n8n data was blank (new install, no workflows). Had there been data, the `/backup/nimb/` tarballs would have been the recovery source.