---
name: systemd-web-service-deployment
description: "Use when deploying a Linux web service managed by systemd, especially Flask/Gunicorn services behind local reverse proxies, Tailscale Serve/Funnel, or similar ingress. Covers safe backups, env files, systemd drop-ins, restarts, and public/private validation without leaking secrets."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [devops, systemd, deployment, web-service, tailscale, flask, gunicorn]
    related_skills: [github-pr-workflow, systematic-debugging]
---

# Systemd Web Service Deployment

## Overview

Use this skill for small production deployments where the app is a Linux service managed by `systemd` and exposed through a local proxy, reverse proxy, Tailscale Serve/Funnel, or HTTPS ingress. The goal is to make the deployment reproducible and reversible: identify the live host/path, back up current files, deploy only intended artifacts, configure runtime secrets outside git, restart safely, and verify the exact public behavior the user cares about.

For Konstantin: if the work is only meaningful when he can check it in production, do not stop at commit/push/PR unless he explicitly asked for Git-only work. Deploy, validate the live URL/API, then report how to verify. Treat “как я проверю?” as a deployment requirement, not merely a request for a PR link.

This is not a cloud-platform-specific skill. It applies to services like Flask/Gunicorn, FastAPI/Uvicorn, Node apps, and static+API dashboards where systemd owns the runtime.

## When to Use

Use when the user asks to:

- deploy a web dashboard/API/service to a Linux host;
- restart or modify a `systemd` service;
- add runtime environment variables or secrets to a deployed service;
- expose a local service through Tailscale Serve/Funnel;
- verify a deployment through public and local URLs;
- roll back a small file-based service deployment.

Do not use for Kubernetes orchestration, serverless deployments, or GitHub-only PR work. Docker containers on the same host are in scope — Konstantin's server runs both systemd services and plain Docker containers, and the same verify/rollback discipline applies.

## Mandatory Workflow

### 1. Confirm where production actually runs

Do not assume an SSH alias or documented hostname is current. Check live signals:

Command snippet moved to `references/deployment-command-cookbook.md` → section 1, “1. Confirm where production actually runs”.

If docs say `ssh vps` but the alias fails, inspect current local state before declaring the deploy blocked. In gateway/server sessions, the execution host may already be the production host.

### 2. Inspect service and ingress before changing files

Command snippet moved to `references/deployment-command-cookbook.md` → section 2, “2. Inspect service and ingress before changing files”.

For Tailscale ingress:

Command snippet moved to `references/deployment-command-cookbook.md` → section 3, “2. Inspect service and ingress before changing files”.

Important distinction:

- `tailscale serve` / status showing `(tailnet only)` means users must be logged into the tailnet.
- `tailscale funnel` with `Funnel on` makes the URL reachable from the public internet; app-level auth must then protect the service.

### 3. Back up before overwriting

For file-based deploys, create a timestamped backup directory under the app path:

Command snippet moved to `references/deployment-command-cookbook.md` → section 4, “3. Back up before overwriting”.

Report the backup path in the final response.

### 4. Put secrets in runtime env, not git

Use a root-readable or service-user-readable env file with restrictive permissions, and connect it through a systemd drop-in:

Command snippet moved to `references/deployment-command-cookbook.md` → section 5, “4. Put secrets in runtime env, not git”.

Never print secret values in chat, logs, commits, docs, or skill references. If the user needs a password, tell them the path/command to reveal it locally rather than echoing it yourself.

### 5. Deploy artifacts narrowly

Copy only the files intended for production, preserving the service layout:

Command snippet moved to `references/deployment-command-cookbook.md` → section 6, “5. Deploy artifacts narrowly”.

Avoid `git pull` directly in production unless that is the documented deployment model. File-based deploys are easier to roll back when current service files are not a git checkout.

### 6. Validate before and after restart

Before restart:

Command snippet moved to `references/deployment-command-cookbook.md` → section 7, “6. Validate before and after restart”.

Restart and verify:

Command snippet moved to `references/deployment-command-cookbook.md` → section 8, “6. Validate before and after restart”.

### 7. Verify local and public behavior

Check the behavior matrix, not just `active`:

- local health/API endpoint;
- public URL through ingress;
- unauthenticated denial/redirect if auth was added;
- authenticated success;
- live/WebSocket/SSE path if the app has a realtime transport;
- content marker in rendered HTML if UI changed.

Example auth checks without printing credentials:

Command snippet moved to `references/deployment-command-cookbook.md` → section 9, “7. Verify local and public behavior”.

### 8. If public access should not require tailnet login, enable Funnel explicitly

For Tailscale-backed public access, `serve` alone is not enough:

Command snippet moved to `references/deployment-command-cookbook.md` → section 10, “8. If public access should not require tailnet login, enable Funnel explicitly”.

Expected status includes `Funnel on`. If the command says `Access denied: serve config denied`, run with `sudo` or configure an operator with `sudo tailscale set --operator=$USER`.

## Rollback Pattern

If validation fails:

Command snippet moved to `references/deployment-command-cookbook.md` → section 11, “Rollback Pattern”.

If a systemd drop-in caused failure:

Command snippet moved to `references/deployment-command-cookbook.md` → section 12, “Rollback Pattern”.

If Tailscale Funnel must be disabled:

Command snippet moved to `references/deployment-command-cookbook.md` → section 13, “Rollback Pattern”.

## Post-VPS-Incident Recovery Checklist

After a VPS provider incident (hack, power loss, forced rebuild, ungraceful reboot):

1. **Identify what happened**: check `last reboot`, `uptime`, `journalctl -b -1` (if accessible), `/var/log/syslog.1` for the last boot session. Absence of graceful shutdown messages = VPS killed externally.
2. **Check all service status**: `docker ps -a` (crash loops?), `systemctl list-units --state=running` (missing services?), check ports.
3. **Docker bind-mount ownership**: see "Docker Container Crash-Loop Diagnosis" below — after reboot, Docker recreates host dirs as `root:root`.
4. **Verify data integrity**: check bind-mount dirs for stale/empty state. A container that crashed before writing data may have created an empty dir that the next start treats as fresh.
5. **Review backup status**: check if local backup crons ran (`/var/log/…`), verify backup directory contents (`/backup/…`). If provider wiped the VPS, local backups are gone.
6. **Clean up stale crons**: if a service or backup strategy is retired, remove its cron entries (`sudo crontab -l`, `/etc/cron.d/`) and scripts (`/opt/…`).
7. **Confirm disk space**: `df -h /` — after recovery, confirm enough space for normal ops.

## Common Pitfalls

1. **Confusing Tailscale Serve with Funnel.** `tailnet only` still requires Tailscale login. If the requirement is “open without Tailscale login,” enable Funnel and rely on app auth.
2. **Assuming `ssh vps` works.** SSH aliases can be absent in the current execution environment. Check whether the current host is already production before blocking.
3. **Restarting without an env file.** If auth is enabled but required credentials are missing, Gunicorn/import-time config may fail or every route may deny access. Create the env file and drop-in before restart.
4. **Printing generated passwords.** Report where the credential is stored and how the user can reveal it locally; do not paste it into chat.
5. **Only checking `systemctl is-active`.** A service can be active while public ingress, auth redirects, API, or WebSocket are broken. Verify the behavior matrix.
6. **Leaving verification scripts unauthenticated.** If deployment adds Basic Auth, update health/live validation scripts to read credentials from env and send the correct headers.
7. **Documenting secrets in project docs.** Docs should record env file paths and config keys, never values.

## Verification Checklist

- [ ] Live service path, service unit, and ingress status were inspected.
- [ ] Current production files were backed up with a timestamp.
- [ ] Runtime secrets are in an env file or secret store, not committed.
- [ ] systemd daemon was reloaded if unit/drop-ins changed.
- [ ] Service restarted and is `active`.
- [ ] Logs were checked for startup errors.
- [ ] Local endpoint and public endpoint were tested.
- [ ] Auth behavior was tested both unauthenticated and authenticated.
- [ ] Realtime endpoint was tested if present.
- [ ] Tailscale `Funnel on` was confirmed if public non-tailnet access was required.
- [ ] Final response includes URL, branch/commit if relevant, backup path, and how the user can verify.

## Docker Container Crash-Loop Diagnosis

On hosts running Docker containers alongside systemd services, a host reboot can reset bind-mount directory ownership to `root:root`, causing non-root containers to fail with `EACCES`. Key steps:

Command snippet moved to `references/deployment-command-cookbook.md` → section 14, “Docker Container Crash-Loop Diagnosis”.

See `references/docker-bind-mount-permissions-after-reboot.md` for full procedure and n8n example.

## References

- `references/server-monitor-auth-funnel-2026-04-30.md` — example deployment restoring app-level auth behind Tailscale Funnel for a Flask/Gunicorn dashboard.
- `references/server-monitor-holographic-metrics-2026-04-30.md` — example deploy of slow-refresh aggregate dashboard metrics from a local SQLite memory DB, including public/auth/API/live validation.
- `references/docker-bind-mount-permissions-after-reboot.md` — Docker bind mount ownership reset after host reboot: diagnosis, fix, prevention.
- `references/vps-provider-incident-recovery-2026-05-03.md` — Full incident report: VPS provider hack, ungraceful reboot, crash-loop fix, backup cleanup.
- `references/deployment-command-cookbook.md` — executable shell snippets extracted from the instruction core.
