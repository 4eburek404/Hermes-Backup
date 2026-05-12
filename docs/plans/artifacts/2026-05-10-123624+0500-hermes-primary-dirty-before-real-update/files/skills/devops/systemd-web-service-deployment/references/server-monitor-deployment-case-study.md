# Server Monitor Deployment Case Study

Consolidated reference from the `server_monitor_iOS_app` dashboard deployment sessions (2026-04-30). Covers auth restoration, Tailscale Funnel enablement, holographic metrics integration, and Docker bind-mount diagnosis.

## Context

- Repository: `/home/konstantin/github_repo/server_monitor_iOS_app`
- Production path: `/home/konstantin/dashboard`
- Service: `server-monitor.service`
- Public endpoint: `https://175557-1.tail52935a.ts.net/dashboard`
- Source metrics DB: `/home/konstantin/.hermes/memory_store.db`
- Holographic metrics are aggregate-only; do not expose fact `content`.
- Cache default: `SERVER_MONITOR_HOLOGRAPHIC_REFRESH_SECONDS=21600` seconds, minimum 300 seconds.

## Key Discoveries

1. **Current host was already production** — `hostname=175557.ip-ptr.tech`. Older docs mentioned an `ssh vps` alias that no longer existed in `~/.ssh/config`.
2. **Tailscale Serve ≠ Funnel** — `tailnet only` still requires Tailscale login. Public non-tailnet access requires `tailscale funnel --bg --yes 8080`.
3. **Auth restoration required both app and validation script updates** — When auth is restored, update `scripts/validate_live_transport.py` to send Basic Auth headers from `SERVER_MONITOR_USERNAME` and `SERVER_MONITOR_PASSWORD`.
4. **Docker bind-mount ownership resets after VPS reboot** — `/home/konstantin/n8n/data` recreated as `root:root`, causing EACCES crash loop. Fix: `sudo chown -R 1000:1000 /home/konstantin/n8n/data && docker restart n8n`.

## Auth + Funnel Deployment Pattern

Created an env file on the production host:

```text
/home/konstantin/dashboard/server-monitor.env
```

Connected via systemd drop-in:

```text
/etc/systemd/system/server-monitor.service.d/auth.conf
```

Env file shape (secret values redacted):

```text
SERVER_MONITOR_REQUIRE_AUTH=true
SERVER_MONITOR_USERNAME=<non-secret username>
SERVER_MONITOR_PASSWORD=[REDACTED]
SERVER_MONITOR_SESSION_SECRET=[REDACTED]
SERVER_MONITOR_COOKIE_SECURE=auto
```

Funnel enablement:

```bash
sudo tailscale funnel --bg --yes 8080
tailscale funnel status  # Confirm "Funnel on"
```

Rollback public exposure:

```bash
sudo tailscale funnel --https=443 off
```

If `Access denied: serve config denied`, either run with `sudo` or:

```bash
sudo tailscale set --operator=$USER
```

## Validation Matrix

Both auth/Funnel and holographic metrics deployments passed this matrix:

```text
service=active
local_dashboard_noauth=401
local_api_noauth=401
local_login=200
local_api_auth=200
public_dashboard_noauth=401
public_api_auth=200
browser_dashboard_follow_login=200
login_marker_follow=yes
auth_dashboard=200
content_marker=holographic-growth (present)
holographic.available=true
holographic.total_facts=44 (at deploy time)
holographic.cache.ttl_seconds=21600
no fact content exposed
live_transport=snapshot+resume+reset ok
```

## Narrow Deployment Steps

1. Create timestamped backup: `/home/konstantin/dashboard/backups/<stamp>`
2. Deploy only intended artifacts with `install -m 0644`
3. Production syntax checks: `python3 -m py_compile`, import check
4. Restart and verify via validation matrix above

## VPS Incident Recovery Checklist

After ungraceful reboot or VPS provider incident:

1. Check `last reboot`, `uptime`, previous boot logs.
2. Check all service states: `systemctl`, `docker ps -a`, listening ports.
3. Diagnose Docker bind-mount ownership before assuming app corruption.
4. Verify data integrity and whether bind-mount dirs are stale/empty.
5. Verify backup jobs and contents; local-only backups on the same VPS are useless if the instance was wiped.
6. Remove stale crons/scripts for retired services.
7. Check disk space and alerting after recovery.

## Lessons

- **"Without Tailscale login" means Funnel, not just app auth.** Check `tailscale funnel status`, not only app auth.
- **A failing SSH alias is not necessarily a blocker** — the agent may already be on the target host.
- **When auth is restored, update both the app and validation scripts.**
- **Systemd drop-ins connect runtime env cleanly** without editing the main unit or committing secrets.
- **Deploy or verify the live runtime**, don't stop at commit/push. Report URL, backup path, and checks.
- **After ungraceful reboot, always check Docker bind-mount ownership for non-root containers.**
- **Report storage path and local reveal command for secrets, never the values.**