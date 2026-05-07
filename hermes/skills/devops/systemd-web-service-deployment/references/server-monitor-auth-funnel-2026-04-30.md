# Server Monitor auth + Tailscale Funnel deployment (2026-04-30)

Session-specific reference for the class-level `systemd-web-service-deployment` skill.

## Context

Konstantin's `server_monitor_iOS_app` dashboard had been simplified to Tailscale-only access. The user reported Tailscale login was unstable and asked to remove the Tailscale-login dependency, restore authorization from history, create a branch first, commit/push, and deploy.

Repository:

```text
/home/konstantin/github_repo/server_monitor_iOS_app
```

Production app path:

```text
/home/konstantin/dashboard
```

Service:

```text
server-monitor.service
```

Public URL:

```text
https://175557-1.tail52935a.ts.net/dashboard
```

## Important discoveries

- The current execution host was already production (`hostname=175557.ip-ptr.tech`), even though older docs mentioned an `ssh vps` alias.
- `~/.ssh/config` did not contain the `vps` alias; direct SSH to `89.23.103.246:2222` failed with public-key auth from the current environment.
- `systemctl cat server-monitor.service` showed a local Gunicorn service:
  ```text
  WorkingDirectory=/home/konstantin/dashboard
  ExecStart=/home/konstantin/dashboard/.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 1 --threads 16 --timeout 0 server_monitor:app
  ```
- Tailscale status initially showed `tailnet only`; enabling app auth alone would not satisfy “open without Tailscale login”. The fix required Tailscale Funnel.

## Git/history workflow

Branch was created before investigation:

```bash
git checkout -b feat/auth-without-tailscale-login
```

Prior auth implementation was found in the parent of commit `74f0281`, the commit that removed app auth in favor of Tailscale-only access.

The final pushed branch was:

```text
feat/auth-without-tailscale-login
```

Final head after deployment docs:

```text
018146e
```

## Runtime auth deployment pattern

Created an env file on the production host:

```text
/home/konstantin/dashboard/server-monitor.env
```

Connected it via systemd drop-in:

```text
/etc/systemd/system/server-monitor.service.d/auth.conf
```

The env file contains keys like:

```text
SERVER_MONITOR_REQUIRE_AUTH=1
SERVER_MONITOR_USERNAME=...
SERVER_MONITOR_PASSWORD=...
SERVER_MONITOR_SESSION_SECRET=...
SERVER_MONITOR_COOKIE_SECURE=auto
```

Secret values were not printed or written to repository docs.

## Deployment commands shape

Backed up current production files under:

```text
/home/konstantin/dashboard/backups/20260430150929
```

Deployed only intended files with `install -m 0644`, then:

```bash
sudo systemctl daemon-reload
cd /home/konstantin/dashboard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile server_monitor.py scripts/validate_live_transport.py
sudo systemctl restart server-monitor.service
systemctl is-active server-monitor.service
```

## Funnel step

Initial status:

```text
https://175557-1.tail52935a.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8080
```

Enabling Funnel needed sudo:

```bash
sudo tailscale funnel --bg --yes 8080
```

Expected status after:

```text
# Funnel on:
#     - https://175557-1.tail52935a.ts.net

https://175557-1.tail52935a.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:8080
```

## Validation matrix that passed

Local/public HTTP checks:

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
```

Live transport validation had to be updated to send Basic Auth headers from `SERVER_MONITOR_USERNAME` and `SERVER_MONITOR_PASSWORD`. After that it passed locally and through the public URL:

```text
snapshot_sample_id=...
collector_state=live
live_first=snapshot:...
resume_event=sample|heartbeat:...
reset_event=reset:...
```

## Lessons

- If the user says “without Tailscale login,” check `tailscale funnel status`, not only app auth. Tailscale Serve is still tailnet-gated.
- A failing documented SSH alias is not necessarily a blocker; the agent may already be running on the target host.
- When auth is restored, update both the app and validation scripts; otherwise deployment verification may fail even when the app works.
- Systemd drop-ins are a clean way to reintroduce runtime env without editing the main unit or committing secrets.
